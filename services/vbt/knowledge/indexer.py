"""
Vault-Indexer — inkrementeller Reindex des Trading-Vaults nach vault_chunks.

Lädt alle Markdown-Dateien aus dem Vault-Root, vergleicht mtime und SHA1-Hash
gegen DB, chunked und embedded nur Dateien mit echtem Content-Change, löscht
Chunks von gelöschten Dateien.

Öffentliche API:
    reindex(vault_root, target_path) -> dict

CLI:
    python -m services.vbt.knowledge.indexer --target=<path>
    python -m services.vbt.knowledge.indexer  # ganzer Vault
"""

import argparse
import hashlib
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)


def _get_engine():
    """Holt die SQLAlchemy-Engine (Import hier, damit Modul ohne DB-Config importierbar bleibt)."""
    from user_data.utils.database.db import get_engine
    return get_engine()


def _vault_path_relative(path: Path, vault_root: Path) -> str:
    """Berechnet den relativen Pfad ab vault_root als String.

    Args:
        path: Absoluter Dateipfad.
        vault_root: Basis-Verzeichnis des Vaults.

    Returns:
        Relativer Pfad als String, z.B. 'strategies/teststrategie/status.md'.
    """
    return str(path.relative_to(vault_root))


# GEÄNDERT: Whole-Vault-Index — Verzeichnisse, die kein indexierbares Wissen enthalten:
#   .obsidian/.trash = App-intern; 00_Inbox + Clippings = unsortierte Roheingänge (Staging,
#   werden später in echte Ordner sortiert und dann indexiert). Template-Ordner zusätzlich
#   per Substring-Check (enthalten {{ }}-Platzhalter).
_EXCLUDED_DIR_NAMES = {".obsidian", ".trash", "00_Inbox", "Clippings"}


def _is_excluded(path: Path, vault_root: Path) -> bool:
    """Prüft, ob eine Datei vom Index ausgeschlossen werden soll.

    Beim Whole-Vault-Index wird der ganze Vault gescannt. Ausgeschlossen werden
    App-/Staging-Verzeichnisse (siehe _EXCLUDED_DIR_NAMES) und alle Template-
    Verzeichnisse. Geprüft werden nur die Verzeichnis-Komponenten des relativen
    Pfads, nicht der Dateiname selbst.

    Args:
        path: Absoluter Dateipfad.
        vault_root: Basis-Verzeichnis des Vaults.

    Returns:
        True, wenn die Datei nicht indiziert werden soll.
    """
    dir_parts = path.relative_to(vault_root).parts[:-1]
    for part in dir_parts:
        if part in _EXCLUDED_DIR_NAMES:
            return True
        if "template" in part.lower():
            return True
    return False


def _compute_file_hash(path: Path) -> str:
    """SHA1 über den Datei-Inhalt als Hex-String.

    Args:
        path: Dateipfad.

    Returns:
        40-stelliger Hex-String des SHA1-Hashes.
    """
    h = hashlib.sha1()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(65536), b''):
            h.update(block)
    return h.hexdigest()


def _get_db_file_state_map(engine, vault_path: Optional[str] = None) -> dict[str, tuple[datetime, str]]:
    """Liest mtime und file_sha1 pro vault_path aus der DB (chunk_index=0 als Quelle).

    Verwendet explizit chunk_index=0 als Hash-Quelle — nicht MAX(file_sha1) —
    da bei einem abgebrochenen Vorgänger-Lauf nur Chunk 0 garantiert konsistent ist.

    Args:
        engine: SQLAlchemy-Engine.
        vault_path: Wenn gesetzt, nur für diesen Pfad abfragen.

    Returns:
        Dict von vault_path -> (mtime, file_sha1).
    """
    query = "SELECT vault_path, mtime, file_sha1 FROM vault_chunks WHERE chunk_index = 0"
    params: dict = {}
    if vault_path:
        query += " AND vault_path = :vp"
        params["vp"] = vault_path

    with engine.connect() as conn:
        rows = conn.execute(text(query), params).fetchall()
    return {row.vault_path: (row.mtime, row.file_sha1) for row in rows}


def _bump_mtime_only(engine, vault_path: str, new_mtime: datetime) -> None:
    """Aktualisiert mtime auf allen Chunks eines vault_path, ohne Embeddings zu berühren.

    Args:
        engine: SQLAlchemy-Engine.
        vault_path: Relativer Vault-Pfad.
        new_mtime: Neuer mtime-Wert.
    """
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE vault_chunks SET mtime = :m WHERE vault_path = :vp"),
            {"m": new_mtime, "vp": vault_path},
        )


def _delete_chunks_for_path(engine, vault_path: str) -> int:
    """Löscht alle Chunks für einen vault_path.

    Args:
        engine: SQLAlchemy-Engine.
        vault_path: Relativer Vault-Pfad.

    Returns:
        Anzahl gelöschter Rows.
    """
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM vault_chunks WHERE vault_path = :vp"),
            {"vp": vault_path},
        )
    return result.rowcount


def _insert_sentinel(engine, vault_path: str, mtime: datetime, file_hash: str) -> None:
    """Schreibt eine Marker-Row für Dateien ohne chunkbaren Content.

    Vor dem Insert werden eventuell bestehende Rows für den vault_path gelöscht
    (gleiche Semantik wie _insert_chunks: full replace pro Datei).

    Sentinel-Rows haben chunk_index=0, text='', embedding=NULL. Der Content-Hash-Skip
    aus Ticket 32 erkennt sie über chunk_index=0 und file_sha1 und überspringt
    die Datei beim nächsten Lauf.

    Args:
        engine: SQLAlchemy-Engine.
        vault_path: Relativer Vault-Pfad.
        mtime: mtime der Quelldatei.
        file_hash: SHA1-Hash des Datei-Inhalts.
    """
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM vault_chunks WHERE vault_path = :vp"),
            {"vp": vault_path},
        )
        conn.execute(
            text(
                "INSERT INTO vault_chunks "
                "(vault_path, chunk_index, content, embedding, mtime, file_sha1, indexed_at) "
                "VALUES (:vp, 0, '', NULL, :m, :h, NOW())"
            ),
            {"vp": vault_path, "m": mtime, "h": file_hash},
        )
    logger.debug("[INDEXER] Sentinel-Row geschrieben: %s", vault_path)


def _insert_chunks(engine, vault_path: str, file_mtime: datetime, chunks_data: list[dict], file_hash: str) -> int:
    """Fügt neue Chunk-Rows in vault_chunks ein.

    Args:
        engine: SQLAlchemy-Engine.
        vault_path: Relativer Vault-Pfad.
        file_mtime: mtime der Quelldatei.
        chunks_data: Liste von Dicts mit den Chunk-Feldern inkl. 'embedding'.
        file_hash: SHA1-Hash des Datei-Inhalts (wird in jede Row als file_sha1 eingetragen).

    Returns:
        Anzahl eingefügter Rows.
    """
    if not chunks_data:
        return 0

    import json as _json
    import datetime as _dt

    def _json_default(obj):
        """Serialisiert Typen die json nicht kennt (date, datetime)."""
        if isinstance(obj, (_dt.date, _dt.datetime)):
            return obj.isoformat()
        raise TypeError(f"Nicht serialisierbar: {type(obj)}")

    rows = []
    for c in chunks_data:
        fm = c.get("frontmatter") or {}
        embedding = c["embedding"]
        # pgvector erwartet einen Cast-Ausdruck via ::vector
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
        rows.append({
            "vault_path": vault_path,
            "chunk_index": c["chunk_index"],
            "heading_path": c.get("heading_path"),
            "content": c["content"],
            "frontmatter_json": _json.dumps(fm, ensure_ascii=False, default=_json_default),
            "mtime": file_mtime,
            "file_sha1": file_hash,
            "embedding": embedding_str,
            "indexed_at": datetime.now(),
        })

    # Hinweis: psycopg2 interpretiert '::' als Cast-Syntax, was mit :param-Platzhaltern
    # kollidiert. Lösung: Cast-Ausdrucke in separate CAST()-Aufrufe umwandeln oder
    # die Werte bereits als korrekte Python-Typen übergeben und psycopg2 den Typ
    # selbst bestimmen lassen. Für embedding und frontmatter_json nutzen wir
    # explizite Wrapper-Objekte aus psycopg2/psycopg2.extras.
    import psycopg2.extras as _pg_extras  # noqa: F401

    with engine.begin() as conn:
        # Rohe psycopg2-Connection für direkten INSERT ohne SQLAlchemy-Text-Parsing
        raw_conn = conn.connection
        cur = raw_conn.cursor()
        for row in rows:
            cur.execute(
                "INSERT INTO vault_chunks "
                "(vault_path, chunk_index, heading_path, content, frontmatter_json, mtime, file_sha1, embedding, indexed_at) "
                "VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s::vector, %s)",
                (
                    row["vault_path"],
                    row["chunk_index"],
                    row["heading_path"],
                    row["content"],
                    row["frontmatter_json"],
                    row["mtime"],
                    row["file_sha1"],
                    row["embedding"],
                    row["indexed_at"],
                ),
            )
        # Commit erfolgt durch den engine.begin()-Context-Manager
    return len(rows)


def reindex(vault_root: Path, target_path: Optional[Path] = None) -> dict:
    """Inkrementeller Reindex des Vaults.

    Scannt alle Markdown-Dateien unter vault_root (oder nur target_path),
    vergleicht die Datei-mtime und den SHA1-Hash gegen die in der DB gespeicherten
    Werte und reindiziert nur Dateien mit echtem Content-Change. Löscht Chunks
    von Dateien die nicht mehr auf dem Dateisystem existieren.

    Args:
        vault_root: Wurzelverzeichnis des Vaults (z.B. Path('/vault/trading')).
        target_path: Optional — wenn gesetzt, wird nur diese Datei verarbeitet.

    Returns:
        Dict mit Statistiken:
        {
            'files_scanned': N,
            'files_reindexed': M,
            'files_deleted': K,
            'chunks_written': L,
            'files_unchanged': U,
            'duration_seconds': float,
        }
    """
    start_ts = time.monotonic()
    engine = _get_engine()

    # GEÄNDERT: Ticket 31 — Mount-Guard Schritt A: vault_root-Existenz prüfen
    if not vault_root.exists() or not vault_root.is_dir():
        logger.critical(
            "[INDEXER] vault_root nicht erreichbar: %s — Abbruch ohne Cleanup", vault_root,
        )
        raise RuntimeError(f"vault_root nicht erreichbar: {vault_root}")

    files_scanned = 0
    files_reindexed = 0
    files_deleted = 0
    chunks_written = 0
    # GEÄNDERT: Ticket 32 — Counter für Dateien mit gleichem Content (nur mtime-Änderung)
    files_unchanged = 0
    # GEÄNDERT: Ticket 34 — Pfad-Listen für files_changed JSONB
    reindexed_paths: list[str] = []
    deleted_paths: list[str] = []

    # --- 1. Dateien bestimmen ---
    if target_path is not None:
        if not target_path.is_absolute():
            target_path = vault_root / target_path
        md_files = [target_path] if target_path.exists() else []
        vault_paths_to_check = [_vault_path_relative(target_path, vault_root)] if target_path.exists() else []
    else:
        # GEÄNDERT: Whole-Vault-Index — Nicht-Wissens-Pfade (.obsidian, .trash, templates) ausschließen
        md_files = [f for f in vault_root.rglob("*.md") if not _is_excluded(f, vault_root)]
        vault_paths_to_check = None  # alle aus DB prüfen

    # GEÄNDERT: Ticket 31 — Mount-Guard Schritt B: leere Dateiliste beim Voll-Reindex
    if target_path is None and not md_files:
        logger.critical(
            "[INDEXER] vault_root erreichbar, aber keine .md-Dateien gefunden "
            "(%s) — Mount vermutlich gerade weg. Abbruch ohne Cleanup.", vault_root,
        )
        raise RuntimeError(
            f"vault_root liefert keine .md-Dateien, Mount vermutlich weg: {vault_root}"
        )

    # --- 2. Gelöschte Dateien aufraumen ---
    if vault_paths_to_check is None:
        # Alle DB-Einträge holen und gegen Dateisystem prüfen
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT DISTINCT vault_path FROM vault_chunks")
            ).fetchall()
        existing_vault_paths = {_vault_path_relative(f, vault_root) for f in md_files}
        for row in rows:
            vp = row.vault_path
            full_path = vault_root / vp
            # GEÄNDERT: Whole-Vault-Index — auch neu ausgeschlossene (aber noch existierende)
            # Dateien bereinigen, damit Änderungen an _EXCLUDED_DIR_NAMES rückwirkend greifen.
            if not full_path.exists() or _is_excluded(full_path, vault_root):
                deleted = _delete_chunks_for_path(engine, vp)
                if deleted > 0:
                    files_deleted += 1
                    deleted_paths.append(vp)
                    logger.info("[INDEXER] Datei bereinigt (fehlt oder ausgeschlossen): %s (%d Chunks entfernt)", vp, deleted)
    elif target_path and not target_path.exists():
        # Einzelne Datei wurde angegeben aber existiert nicht mehr
        vp = _vault_path_relative(target_path, vault_root)
        deleted = _delete_chunks_for_path(engine, vp)
        if deleted > 0:
            files_deleted += 1
            deleted_paths.append(vp)
            logger.info("[INDEXER] Gelöschte Datei bereinigt: %s (%d Chunks entfernt)", vp, deleted)

    # GEÄNDERT: Ticket 32 — _get_db_mtime_map durch _get_db_file_state_map ersetzt
    # --- 3. Datei-State-Map aus DB laden (mtime + SHA1-Hash) ---
    if target_path is not None and target_path.exists():
        db_state_map = _get_db_file_state_map(
            engine,
            vault_path=_vault_path_relative(target_path, vault_root),
        )
    else:
        db_state_map = _get_db_file_state_map(engine)

    # GEÄNDERT: Ticket 31 — Lazy-Imports erst hier, nach den Guards (nicht am Funktions-Anfang)
    from services.vbt.knowledge.chunker import chunk_markdown
    from services.vbt.knowledge.embedding import embed

    # --- 4. Dateien reindizieren ---
    for md_file in md_files:
        files_scanned += 1
        vp = _vault_path_relative(md_file, vault_root)

        # GEÄNDERT: Ticket 32 — Content-Hash-Skip statt reiner mtime-Vergleich
        file_mtime = datetime.fromtimestamp(md_file.stat().st_mtime)
        db_state = db_state_map.get(vp)

        if db_state is not None:
            db_mtime, db_hash = db_state
            # Fast-Path: mtime unverändert -> sicher überspringen
            if file_mtime <= db_mtime:
                logger.debug("[INDEXER] Fast-Path (mtime unverändert): %s", vp)
                continue
            # mtime neuer -> Hash prüfen ob Content wirklich geändert
            file_hash = _compute_file_hash(md_file)
            if file_hash and db_hash and file_hash == db_hash:
                # Inhalt identisch, nur Touch -> mtime nachziehen, kein Reindex
                _bump_mtime_only(engine, vp, file_mtime)
                files_unchanged += 1
                logger.debug("[INDEXER] Touch ohne Content-Change (mtime aktualisiert): %s", vp)
                continue
        else:
            file_hash = _compute_file_hash(md_file)

        # Reindex-Pfad — Fehler einer Datei sollen den Gesamtlauf nicht abbrechen
        try:
            # Alte Chunks löschen
            _delete_chunks_for_path(engine, vp)

            # Chunken
            chunks = chunk_markdown(md_file)
            # GEÄNDERT: Ticket 33 — Sentinel-Row für Dateien ohne chunkbaren Content
            if not chunks:
                logger.debug("[INDEXER] Keine Chunks aus: %s — Sentinel-Row schreiben", vp)
                _insert_sentinel(engine, vp, file_mtime, file_hash)
                files_reindexed += 1
                reindexed_paths.append(vp)
                continue

            # Embedden und einfügen
            chunks_data = []
            for chunk in chunks:
                embedding = embed(chunk.content)
                chunks_data.append({
                    "chunk_index": chunk.chunk_index,
                    "heading_path": chunk.heading_path,
                    "content": chunk.content,
                    "frontmatter": chunk.frontmatter,
                    "embedding": embedding,
                })

            # GEÄNDERT: Ticket 32 — file_hash an _insert_chunks weiterreichen
            n_written = _insert_chunks(engine, vp, file_mtime, chunks_data, file_hash)
            chunks_written += n_written
            files_reindexed += 1
            reindexed_paths.append(vp)
            logger.debug("[INDEXER] Reindiziert: %s (%d Chunks)", vp, n_written)

        except Exception as exc:
            logger.error("[INDEXER] Fehler bei Datei %s: %s", vp, exc, exc_info=True)
            continue

    duration = time.monotonic() - start_ts
    result = {
        "files_scanned": files_scanned,
        "files_reindexed": files_reindexed,
        "files_deleted": files_deleted,
        "chunks_written": chunks_written,
        "files_unchanged": files_unchanged,
        "duration_seconds": round(duration, 2),
        # GEÄNDERT: Ticket 34 — Pfad-Listen für files_changed JSONB
        "reindexed_paths": reindexed_paths,
        "deleted_paths": deleted_paths,
    }
    logger.info("[INDEXER] Reindex abgeschlossen: %s", result)
    return result


def _setup_logging() -> None:
    """Konfiguriert Logging für den CLI-Aufruf."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )


def _main() -> None:
    """CLI-Einstiegspunkt für manuellen Reindex.

    Beispiel:
        python -m services.vbt.knowledge.indexer --target=strategies/teststrategie/status.md
        python -m services.vbt.knowledge.indexer
    """
    _setup_logging()

    # Projekt-Root in sys.path eintragen (für Containeraufruf und lokalen Aufruf)
    project_root = str(Path(__file__).resolve().parents[3])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # .env laden
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(project_root) / ".env")
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="Vault-Reindex (Ticket 25)")
    parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="Relativer Pfad ab vault_root, z.B. strategies/teststrategie/status.md",
    )
    parser.add_argument(
        "--vault-root",
        type=str,
        default=os.environ.get("VAULT_ROOT", "/obsidian_vault"),
        help="Vault-Root-Verzeichnis (Default: $VAULT_ROOT oder /obsidian_vault)",
    )
    args = parser.parse_args()

    vault_root = Path(args.vault_root)
    if not vault_root.exists():
        logger.error("Vault-Root nicht gefunden: %s", vault_root)
        sys.exit(1)

    target_path: Optional[Path] = None
    if args.target:
        target_path = vault_root / args.target
        if not target_path.exists():
            logger.error("Target-Datei nicht gefunden: %s", target_path)
            sys.exit(1)

    result = reindex(vault_root=vault_root, target_path=target_path)
    print(result)


if __name__ == "__main__":
    _main()
