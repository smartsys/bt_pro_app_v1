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
  ``pg_restore`` in einer einzigen Transaktion zurück, rechnet die
  Planner-Statistiken neu (``ANALYZE``) und verwirft die gecachte Engine. Ohne
  Stack-Neustart; gebrochene Verbindungen fängt ``pool_pre_ping``.

Der Restore läuft als Hintergrund-Thread — der Aufrufer startet ihn und fragt
den Fortschritt über ``import_status`` ab (Basis für die Fortschrittsanzeige).

ACHTUNG: Der Import überschreibt die komplette DB.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import time
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
    # GEÄNDERT: copyfile statt copy2 — die bestehende seed.dump kann einem
    # anderen Nutzer (root aus dem Bind-Mount) gehören; copy2 ruft am Ende
    # copystat/chmod auf und scheitert dann mit EPERM, obwohl der Inhalt
    # (Datei ist world-writable) längst geschrieben ist. copyfile kopiert
    # nur den Inhalt, ohne die Metadaten anzufassen.
    shutil.copyfile(dated, POINTER)
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
    _run_psql(sql, params, "Schema-Reset")


def _run_psql(sql: str, params: dict[str, str], label: str) -> None:
    """Führt eine SQL-Anweisung per psql aus; bricht bei Fehler mit Klartext ab."""
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
        raise RuntimeError(f"{label} fehlgeschlagen (exit {proc.returncode}): {stderr}")


def _analyze(params: dict[str, str]) -> None:
    """Rechnet die Tabellen-Statistiken neu.

    pg_restore stellt die Planner-Statistiken nicht mit her. Ohne ANALYZE plant
    Postgres auf einer leeren Schätzung und wählt bei den großen Result-Tabellen
    grottige Pläne — die Runs-Liste braucht dann Sekunden statt Millisekunden.
    """
    _run_psql("ANALYZE;", params, "ANALYZE")


def _count_toc_entries(dump: Path, params: dict[str, str]) -> int:
    """Zählt die Objekte im Dump (Inhaltsverzeichnis) — Nenner der Fortschrittsanzeige.

    ``pg_restore -l`` listet je Objekt eine Zeile; Kommentarzeilen beginnen mit
    ``;``. Schlägt der Aufruf fehl, liefert die Funktion 0 — der Import läuft
    dann ohne Prozentwert weiter (die Anzeige zeigt nur die Objektzahl).
    """
    args = ["pg_restore", "-l", str(dump)]
    proc = subprocess.run(
        args, env=_subprocess_env(params["password"]), capture_output=True
    )
    if proc.returncode != 0:
        return 0
    listing = proc.stdout.decode("utf-8", errors="replace").splitlines()
    return sum(1 for line in listing if line.strip() and not line.startswith(";"))


# Meldungen, die pg_restore --verbose je abgearbeitetem Objekt auf stderr schreibt.
# Sie sind der Zähler der Fortschrittsanzeige.
_PROGRESS_MARKERS = ("creating ", "processing data for table ", "executing ")


def _run_pg_restore(dump: Path, params: dict[str, str], total: int) -> None:
    """Spielt den Dump in einer einzigen Transaktion zurück und meldet den Fortschritt.

    ``--single-transaction`` ist hier nicht Kosmetik, sondern verhindert einen
    echten Fehlerfall: Ohne die Transaktion sind die wiederhergestellten
    Tabellen für andere Verbindungen (Worker, Scheduler-Reindex) schon sichtbar,
    während ``pg_restore`` seine Primär- und Unique-Constraints erst ganz zum
    Schluss anlegt. Ein nebenläufiger Schreiber trifft dann auf ungeschützte
    Tabellen, und der Restore scheitert am Ende an doppelten Schlüsseln. In der
    Transaktion sind die Tabellen bis zum Commit unsichtbar — und ein Fehler
    lässt keine halb gefüllte DB zurück, sondern rollt komplett zurück.

    Raises:
        RuntimeError: Wenn pg_restore mit einem Fehler endet.
    """
    args = [
        "pg_restore",
        "-h", params["host"],
        "-p", params["port"],
        "-U", params["user"],
        "-d", params["dbname"],
        "--no-owner", "--no-privileges",
        "--single-transaction",
        "--verbose",
        str(dump),
    ]
    proc = subprocess.Popen(
        args,
        env=_subprocess_env(params["password"]),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
    )
    done = 0
    errors: list[str] = []
    for line in proc.stderr:
        message = line.strip()
        if not message:
            continue
        body = message[len("pg_restore: "):] if message.startswith("pg_restore: ") else message
        if body.startswith("error:"):
            errors.append(body)
        elif body.startswith(_PROGRESS_MARKERS):
            done += 1
            _set_status(done=done, total=total)
    proc.wait()
    if proc.returncode != 0:
        detail = " ".join(errors[:3]) or f"exit {proc.returncode}"
        raise RuntimeError(f"pg_restore fehlgeschlagen: {detail}")


# Zustand des laufenden bzw. zuletzt gelaufenen Imports (ein Import zur Zeit).
_status_lock = threading.Lock()
_status: dict = {
    "running": False,
    "phase": "idle",
    "done": 0,
    "total": 0,
    "percent": 0,
    "started_at": None,
    "finished_at": None,
    "ok": None,
    "message": "",
}


def _set_status(**fields) -> None:
    """Schreibt Felder in den Import-Zustand und hält den Prozentwert nach.

    Ein mitgegebener ``percent``-Wert gewinnt (Abschlussmeldung); sonst wird er
    aus done/total berechnet.
    """
    with _status_lock:
        _status.update(fields)
        if "percent" in fields:
            return
        total = _status["total"]
        done = _status["done"]
        # Bis zum Commit bewusst bei 99 deckeln — 100 erst, wenn wirklich fertig.
        _status["percent"] = min(99, int(done / total * 100)) if total else 0


def import_status() -> dict:
    """Aktueller Stand des Imports (für das Polling der Fortschrittsanzeige)."""
    with _status_lock:
        status = dict(_status)
    if status["running"] and status["started_at"]:
        status["elapsed_seconds"] = time.time() - status["started_at"]
    return status


def start_import() -> None:
    """Startet den Import im Hintergrund. Kehrt sofort zurück.

    Der Fortschritt ist über ``import_status`` abrufbar.

    Raises:
        RuntimeError: Wenn kein Snapshot vorhanden ist oder bereits ein Import läuft.
    """
    if not POINTER.exists():
        raise RuntimeError(
            f"Kein gespeicherter Snapshot unter {POINTER}. Erst über "
            "DB Exportieren einen Snapshot speichern."
        )
    with _status_lock:
        if _status["running"]:
            raise RuntimeError("Es läuft bereits ein Import.")
        _status.update(
            running=True,
            phase="prepare",
            done=0,
            total=0,
            percent=0,
            started_at=time.time(),
            finished_at=None,
            ok=None,
            message="",
        )
    threading.Thread(target=_import_worker, name="seed-import", daemon=True).start()


def _import_worker() -> None:
    """Führt Schema-Reset und Restore aus und schreibt das Ergebnis in den Zustand."""
    try:
        params = _db_params()
        total = _count_toc_entries(POINTER, params)
        _set_status(phase="reset", total=total)
        _reset_schema(params)
        _set_status(phase="restore")
        _run_pg_restore(POINTER, params, total)
        _set_status(phase="analyze")
        _analyze(params)
        _dispose_engine()
        _set_status(
            running=False,
            phase="done",
            ok=True,
            percent=100,
            finished_at=time.time(),
            message=f"Import abgeschlossen. Die DB entspricht jetzt dem "
                    f"gespeicherten Snapshot ({POINTER.name}).",
        )
    except Exception as exc:  # noqa: BLE001 — Fehler landet sichtbar in der Anzeige
        _set_status(
            running=False,
            phase="error",
            ok=False,
            finished_at=time.time(),
            message=f"Import fehlgeschlagen: {exc}",
        )


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
