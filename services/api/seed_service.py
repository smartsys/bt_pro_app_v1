"""
DB-Snapshot: Export/Import über die GUI.

Repliziert das Verhalten der CLI-Skripte unter ``db_snapshot/`` (db_export.py /
db_import.py), nur GUI-getriggert und direkt aus dem App-Container per TCP gegen
die DB — kein ``docker exec``, kein ``docker compose down/up``.

- Export schreibt einen datierten Snapshot nach ``db_snapshot/data/`` und
  aktualisiert ``seed.dump`` als Pointer auf den zuletzt gespeicherten Stand
  (identisch zum CLI-Export). Der Ordner ist per Bind-Mount auch auf dem Host
  sichtbar.
- Import liest ``db_snapshot/data/seed.dump``, kappt fremde Verbindungen, setzt
  das ``public``-Schema neu auf (TimescaleDB-Extension), spielt per
  ``pg_restore`` zurück und verwirft die gecachte Engine. Ohne Stack-Neustart;
  gebrochene Verbindungen fängt ``pool_pre_ping``.

ACHTUNG: Der Import überschreibt die komplette DB.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path


# Ablageort der Snapshots — im Container per Bind-Mount auf ./db_snapshot/data
SNAPSHOT_DIR = Path(os.getenv("PROJECT_ROOT", "/app")) / "db_snapshot" / "data"
# Pointer auf den zuletzt gespeicherten Stand (den der Import liest) — Name wie CLI
POINTER = SNAPSHOT_DIR / "seed.dump"


def _require_env(name: str) -> str:
    """Liest eine Pflicht-Umgebungsvariable; bricht hart ab, wenn sie fehlt."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Pflicht-Umgebungsvariable {name} fehlt oder ist leer "
            "(muss in .env bzw. der Container-Umgebung gesetzt sein)"
        )
    return value


def _db_params() -> dict[str, str]:
    """DB-Verbindungsparameter aus der Umgebung (identisch zu db.get_engine)."""
    return {
        "host": _require_env("POSTGRES_SERVER"),
        "port": _require_env("POSTGRES_PORT"),
        "dbname": _require_env("POSTGRES_DB"),
        "user": _require_env("POSTGRES_USER"),
        "password": _require_env("POSTGRES_PASSWORD"),
    }


def _subprocess_env(password: str) -> dict[str, str]:
    """Kopie der aktuellen Umgebung mit gesetztem PGPASSWORD (kein Passwort im Argv)."""
    env = os.environ.copy()
    env["PGPASSWORD"] = password
    return env


def _run_pg_dump(target: Path, params: dict[str, str]) -> None:
    """Dumpt die komplette DB per pg_dump -Fc in die Zieldatei."""
    args = [
        "pg_dump",
        "-h", params["host"],
        "-p", params["port"],
        "-U", params["user"],
        "-d", params["dbname"],
        "-Fc", "--no-owner", "--no-privileges",
        "-f", str(target),
    ]
    proc = subprocess.run(
        args, env=_subprocess_env(params["password"]), capture_output=True
    )
    if proc.returncode != 0:
        target.unlink(missing_ok=True)
        stderr = proc.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"pg_dump fehlgeschlagen (exit {proc.returncode}): {stderr}")


def export_to_store() -> Path:
    """Speichert einen Snapshot im Ordner und aktualisiert den seed.dump-Pointer.

    Verhalten identisch zum CLI-Export: datierter Snapshot
    ``db_snapshot/data/seed-YYYY-MM-DD.dump`` plus Kopie auf ``seed.dump``.

    Returns:
        Pfad zum datierten Snapshot.

    Raises:
        RuntimeError: Wenn pg_dump fehlschlägt.
    """
    params = _db_params()
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    dated = SNAPSHOT_DIR / f"seed-{date.today().isoformat()}.dump"
    _run_pg_dump(dated, params)
    # Pointer auf den zuletzt gespeicherten Stand aktualisieren.
    shutil.copy2(dated, POINTER)
    return dated


def export_temp_dump() -> Path:
    """Erzeugt einen Dump in einer temporären Datei (für den Download-Button).

    Der Aufrufer ist dafür verantwortlich, die Datei nach dem Ausliefern zu
    löschen.
    """
    params = _db_params()
    fd, tmp_path = tempfile.mkstemp(prefix="seed-download-", suffix=".dump")
    os.close(fd)
    target = Path(tmp_path)
    _run_pg_dump(target, params)
    return target


def snapshot_filename() -> str:
    """Vorschlagsname für den Download: seed-YYYY-MM-DD.dump."""
    return f"seed-{date.today().isoformat()}.dump"


def stored_snapshot_info() -> dict | None:
    """Metadaten zum aktuell gespeicherten Snapshot (seed.dump) oder None.

    Returns:
        Dict mit ``size_mb`` und ``mtime`` (Datei-Änderungszeit) oder None,
        wenn noch kein Snapshot gespeichert wurde.
    """
    if not POINTER.exists():
        return None
    stat = POINTER.stat()
    return {
        "name": POINTER.name,
        "size_mb": stat.st_size / 1024 / 1024,
        "mtime": stat.st_mtime,
    }


def _reset_schema(params: dict[str, str]) -> None:
    """Kappt fremde Verbindungen und setzt das public-Schema neu auf.

    Ersetzt das ``docker compose down`` des CLI-Skripts: statt den Stack neu zu
    starten, werden alle anderen DB-Verbindungen (Worker, weitere Requests)
    getrennt, damit ``DROP SCHEMA`` nicht blockiert. Die TimescaleDB-Extension
    hängt am gedroppten Schema und wird neu geladen.
    """
    user = params["user"]
    sql = (
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname = current_database() AND pid <> pg_backend_pid(); "
        "DROP SCHEMA public CASCADE; "
        "CREATE SCHEMA public; "
        f"GRANT ALL ON SCHEMA public TO {user}; "
        "GRANT ALL ON SCHEMA public TO public; "
        "CREATE EXTENSION IF NOT EXISTS timescaledb;"
    )
    args = [
        "psql",
        "-h", params["host"],
        "-p", params["port"],
        "-U", params["user"],
        "-d", params["dbname"],
        "-v", "ON_ERROR_STOP=1",
        "-c", sql,
    ]
    proc = subprocess.run(
        args, env=_subprocess_env(params["password"]), capture_output=True
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"Schema-Reset fehlgeschlagen (exit {proc.returncode}): {stderr}")


def import_from_store() -> str:
    """Spielt den gespeicherten Snapshot (seed.dump) zurück — überschreibt die DB.

    Returns:
        Name der eingespielten Datei (für die Erfolgsmeldung).

    Raises:
        RuntimeError: Wenn kein Snapshot vorhanden ist oder der Restore fehlschlägt.
    """
    if not POINTER.exists():
        raise RuntimeError(
            f"Kein gespeicherter Snapshot unter {POINTER}. Erst über "
            "DB Exportieren einen Snapshot speichern."
        )
    params = _db_params()
    _reset_schema(params)

    args = [
        "pg_restore",
        "-h", params["host"],
        "-p", params["port"],
        "-U", params["user"],
        "-d", params["dbname"],
        "--no-owner", "--no-privileges",
        str(POINTER),
    ]
    proc = subprocess.run(
        args, env=_subprocess_env(params["password"]), capture_output=True
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"pg_restore fehlgeschlagen (exit {proc.returncode}): {stderr}")

    _dispose_engine()
    return POINTER.name


def _dispose_engine() -> None:
    """Verwirft die modul-gecachte SQLAlchemy-Engine nach dem Restore."""
    try:
        from user_data.utils.database import db

        if db._engine is not None:
            db._engine.dispose()
            db._engine = None
            db._session_factory = None
    except Exception:
        # Kein harter Abbruch: pool_pre_ping fängt gebrochene Verbindungen auch so.
        pass
