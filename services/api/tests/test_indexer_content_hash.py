"""Tests für den Content-Hash-Skip im Vault-Indexer (Ticket 32).

Prüft, dass reindex() nur dann Embeddings berechnet und Chunks neu schreibt,
wenn sich der Datei-Inhalt tatsächlich geändert hat. Reine mtime-Änderungen
(Touch) lösen keinen Embedding-Aufruf mehr aus.

Verwendet PostgreSQL Test-DB (Port 5562) via db_engine/session-Fixtures
aus tests/conftest.py.

Embedding-Mock-Strategie: services.vbt.knowledge.embedding.embed wird per
monkeypatch durch eine Funktion ersetzt, die einen Call-Counter hochzählt
und einen Dummy-Vektor (Liste mit 1024 Nullen) zurückgibt.
"""

import os
import sys
import time
import types
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

# Projekt-Root für alle Importe
_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))


# ============================================================================
# sys.modules-Stubs für Lazy-Imports in reindex()
# ============================================================================

def _make_fake_chunk(chunk_index: int = 0, content: str = "Testinhalt") -> MagicMock:
    """Erzeugt einen minimalen Fake-Chunk."""
    chunk = MagicMock()
    chunk.chunk_index = chunk_index
    chunk.heading_path = "Testüberschrift"
    chunk.content = content
    chunk.frontmatter = {}
    return chunk


def _register_chunker_stub_with_chunks(chunks: list) -> types.ModuleType:
    """Registriert einen chunker-Stub, der die übergebenen Chunks zurückgibt."""
    chunker_mod = types.ModuleType("services.vbt.knowledge.chunker")
    chunker_mod.chunk_markdown = MagicMock(return_value=chunks)
    sys.modules["services.vbt.knowledge.chunker"] = chunker_mod
    return chunker_mod


class EmbedCallCounter:
    """Embed-Mock der Aufrufe zählt und Dummy-Vektor zurückgibt."""

    def __init__(self):
        self.call_count = 0

    def __call__(self, text: str) -> list[float]:
        self.call_count += 1
        return [0.0] * 1024


def _make_embed_stub_in_modules(counter: EmbedCallCounter) -> types.ModuleType:
    """Registriert einen embedding-Stub in sys.modules."""
    embed_mod = types.ModuleType("services.vbt.knowledge.embedding")
    embed_mod.embed = counter
    sys.modules["services.vbt.knowledge.embedding"] = embed_mod
    return embed_mod


# ============================================================================
# Hilfsfunktionen
# ============================================================================

def _get_chunks_mtime_and_hash(engine, vault_path: str) -> list[tuple]:
    """Liest alle (mtime, file_sha1) für einen vault_path aus der DB."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT mtime, file_sha1 FROM vault_chunks WHERE vault_path = :vp ORDER BY chunk_index"),
            {"vp": vault_path},
        ).fetchall()
    return [(row.mtime, row.file_sha1) for row in rows]


def _run_reindex(vault_root: Path, embed_counter: EmbedCallCounter, target_path: Path | None = None) -> dict:
    """Führt reindex() mit frischen Stubs aus und gibt das Result-Dict zurück."""
    # Stubs erneuern damit embed_counter korrekt verlinkt ist
    _make_embed_stub_in_modules(embed_counter)

    from services.vbt.knowledge.indexer import reindex
    return reindex(vault_root=vault_root, target_path=target_path)


# ============================================================================
# Tests
# ============================================================================

class TestTouchOhneContentChange:
    """Touch ohne Content-Change: kein Embedding-Aufruf, mtime in DB aktualisiert."""

    def test_touch_skip_no_embed_call(self, db_engine, tmp_path):
        """Datei touchen ohne Content-Change → zweiter Reindex ruft embed() nicht auf."""
        # Datei erstellen
        md_file = tmp_path / "test_touch.md"
        md_file.write_text("# Testüberschrift\n\nTestinhalt Zeile 1.")

        vault_path = "test_touch.md"

        # Ersten Reindex durchführen
        counter1 = EmbedCallCounter()
        _register_chunker_stub_with_chunks([_make_fake_chunk(0, "Testinhalt Zeile 1.")])

        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            result1 = _run_reindex(tmp_path, counter1)

        assert result1["files_reindexed"] == 1, "Erster Lauf muss Datei reindizieren"
        assert counter1.call_count == 1, "Erster Lauf muss embed() aufrufen"

        # mtime erhöhen ohne Content zu ändern
        now_plus_10 = time.time() + 10
        os.utime(str(md_file), (now_plus_10, now_plus_10))

        # Zweiten Reindex durchführen
        counter2 = EmbedCallCounter()
        _register_chunker_stub_with_chunks([_make_fake_chunk(0, "Testinhalt Zeile 1.")])

        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            result2 = _run_reindex(tmp_path, counter2)

        # Embedding darf nicht aufgerufen worden sein
        assert counter2.call_count == 0, (
            f"embed() wurde {counter2.call_count}x aufgerufen — erwartet: 0 (Content unverändert)"
        )
        assert result2["files_unchanged"] == 1, f"files_unchanged erwartet 1, war: {result2['files_unchanged']}"

    def test_touch_skip_mtime_updated_in_db(self, db_engine, tmp_path):
        """Nach Touch-Skip muss mtime in der DB auf den neuen Wert aktualisiert worden sein."""
        md_file = tmp_path / "test_mtime_update.md"
        md_file.write_text("# Testüberschrift\n\nInhalt für mtime-Update-Test.")

        vault_path = "test_mtime_update.md"

        # Erster Reindex
        counter = EmbedCallCounter()
        _register_chunker_stub_with_chunks([_make_fake_chunk(0, "Inhalt für mtime-Update-Test.")])

        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            _run_reindex(tmp_path, counter)

        # mtime erhöhen
        new_ts = time.time() + 20
        os.utime(str(md_file), (new_ts, new_ts))
        expected_mtime = datetime.fromtimestamp(new_ts)

        # Zweiter Reindex (Touch-Skip)
        counter2 = EmbedCallCounter()
        _register_chunker_stub_with_chunks([_make_fake_chunk(0, "Inhalt für mtime-Update-Test.")])

        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            _run_reindex(tmp_path, counter2)

        # DB-mtime muss auf neuen Wert gesetzt sein
        rows = _get_chunks_mtime_and_hash(db_engine, vault_path)
        assert len(rows) == 1, "Chunk muss noch in DB vorhanden sein"
        db_mtime, db_hash = rows[0]

        # mtime-Vergleich: DB-Wert muss näher am erwarteten Wert liegen als am alten
        mtime_diff = abs((db_mtime - expected_mtime).total_seconds())
        assert mtime_diff < 2.0, (
            f"DB-mtime {db_mtime} weicht mehr als 2s vom erwarteten Wert {expected_mtime} ab"
        )

    def test_touch_skip_sha1_unchanged_in_db(self, db_engine, tmp_path):
        """Nach Touch-Skip muss file_sha1 in DB unverändert geblieben sein."""
        md_file = tmp_path / "test_sha1_unchanged.md"
        md_file.write_text("# SHA1-Test\n\nDer Inhalt bleibt identisch.")

        vault_path = "test_sha1_unchanged.md"

        # Erster Reindex
        counter = EmbedCallCounter()
        _register_chunker_stub_with_chunks([_make_fake_chunk(0, "Der Inhalt bleibt identisch.")])

        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            _run_reindex(tmp_path, counter)

        # SHA1 nach erstem Lauf merken
        rows_after_first = _get_chunks_mtime_and_hash(db_engine, vault_path)
        sha1_after_first = rows_after_first[0][1]
        assert sha1_after_first != "", "file_sha1 muss nach erstem Reindex gesetzt sein"

        # Touch ohne Content-Change
        os.utime(str(md_file), (time.time() + 15, time.time() + 15))

        # Zweiter Reindex (Touch-Skip)
        counter2 = EmbedCallCounter()
        _register_chunker_stub_with_chunks([_make_fake_chunk(0, "Der Inhalt bleibt identisch.")])

        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            _run_reindex(tmp_path, counter2)

        rows_after_second = _get_chunks_mtime_and_hash(db_engine, vault_path)
        sha1_after_second = rows_after_second[0][1]

        assert sha1_after_first == sha1_after_second, (
            f"file_sha1 hat sich nach Touch-Skip geändert: {sha1_after_first} -> {sha1_after_second}"
        )


class TestMtimeStabilitaetNachTouchSkip:
    """Dritter Lauf direkt nach Touch-Skip: Fast-Path greift, kein Hash-Compute."""

    def test_third_run_uses_fast_path(self, db_engine, tmp_path):
        """Dritter Lauf nach Touch-Skip: file_mtime <= db_mtime → Fast-Path, kein UPDATE."""
        md_file = tmp_path / "test_fast_path.md"
        md_file.write_text("# Fast-Path-Test\n\nInhalt für Fast-Path.")

        # Erster Reindex
        counter1 = EmbedCallCounter()
        _register_chunker_stub_with_chunks([_make_fake_chunk(0, "Inhalt für Fast-Path.")])
        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            _run_reindex(tmp_path, counter1)

        # Touch → zweiter Reindex (Touch-Skip, mtime wird in DB aktualisiert)
        os.utime(str(md_file), (time.time() + 10, time.time() + 10))
        counter2 = EmbedCallCounter()
        _register_chunker_stub_with_chunks([_make_fake_chunk(0, "Inhalt für Fast-Path.")])
        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            result2 = _run_reindex(tmp_path, counter2)
        assert result2["files_unchanged"] == 1

        # Dritter Lauf — mtime soll unverändert sein → Fast-Path
        counter3 = EmbedCallCounter()
        _register_chunker_stub_with_chunks([_make_fake_chunk(0, "Inhalt für Fast-Path.")])
        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            result3 = _run_reindex(tmp_path, counter3)

        assert counter3.call_count == 0, "Dritter Lauf darf kein Embedding berechnen (Fast-Path)"
        assert result3["files_unchanged"] == 0, "Fast-Path zählt nicht als unchanged (continue vor Hash)"
        assert result3["files_reindexed"] == 0, "Keine Reindizierung beim Fast-Path"


class TestEchteContentAenderung:
    """Echte Content-Änderung löst Reindex aus, SHA1 wird neu gesetzt."""

    def test_content_change_triggers_reindex(self, db_engine, tmp_path):
        """Datei inhaltlich ändern → Reindex erfolgt, neuer file_sha1 in DB."""
        md_file = tmp_path / "test_content_change.md"
        md_file.write_text("# Strategie\n\nVersion 1 — Inhalt.")

        vault_path = "test_content_change.md"

        # Erster Reindex
        counter1 = EmbedCallCounter()
        _register_chunker_stub_with_chunks([_make_fake_chunk(0, "Version 1 — Inhalt.")])
        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            result1 = _run_reindex(tmp_path, counter1)
        assert result1["files_reindexed"] == 1

        sha1_v1 = _get_chunks_mtime_and_hash(db_engine, vault_path)[0][1]
        assert sha1_v1 != "", "file_sha1 muss nach erstem Reindex gesetzt sein"

        # Content ändern (mtime ändert sich dadurch automatisch)
        time.sleep(0.05)  # sicherstellen dass mtime wechselt
        md_file.write_text("# Strategie\n\nVersion 2 — Neuer Inhalt komplett verändert!")

        # Zweiter Reindex
        counter2 = EmbedCallCounter()
        _register_chunker_stub_with_chunks([_make_fake_chunk(0, "Version 2 — Neuer Inhalt komplett verändert!")])
        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            result2 = _run_reindex(tmp_path, counter2)

        assert result2["files_reindexed"] == 1, "Content-Änderung muss Reindex auslösen"
        assert result2["chunks_written"] > 0, "Neue Chunks müssen geschrieben worden sein"
        assert counter2.call_count >= 1, "embed() muss bei Content-Änderung aufgerufen werden"

        sha1_v2 = _get_chunks_mtime_and_hash(db_engine, vault_path)[0][1]
        assert sha1_v2 != sha1_v1, f"file_sha1 muss sich geändert haben: {sha1_v1} -> {sha1_v2}"


class TestErstesIndexieren:
    """Erste Indizierung: Hash wird berechnet und in DB gespeichert."""

    def test_first_index_stores_sha1(self, db_engine, tmp_path):
        """Neue Datei ohne DB-Eintrag → file_sha1 wird gesetzt und ist nicht leer."""
        md_file = tmp_path / "test_first_index.md"
        md_file.write_text("# Erstes Indexieren\n\nDiese Datei wird zum ersten Mal indexiert.")

        vault_path = "test_first_index.md"

        counter = EmbedCallCounter()
        _register_chunker_stub_with_chunks([_make_fake_chunk(0, "Diese Datei wird zum ersten Mal indexiert.")])
        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            result = _run_reindex(tmp_path, counter)

        assert result["files_reindexed"] == 1

        rows = _get_chunks_mtime_and_hash(db_engine, vault_path)
        assert len(rows) == 1, "Chunk muss in DB eingetragen sein"
        _, sha1 = rows[0]
        assert sha1 != "", "file_sha1 darf nicht leer sein nach erstem Indexieren"
        assert len(sha1) == 40, f"SHA1 muss 40 Zeichen lang sein, war: {len(sha1)}"


class TestBackwardsCompat:
    """Pre-existing Rows mit file_sha1='' werden korrekt durch Reindex ersetzt."""

    def test_empty_sha1_triggers_reindex_on_touch(self, db_engine, tmp_path):
        """Vorhandene Row mit file_sha1='' → Touch löst Reindex aus, danach Hash nicht mehr leer."""
        md_file = tmp_path / "test_backwards.md"
        md_file.write_text("# Backwards-Compat\n\nVorhandene Row mit leerem Hash.")

        vault_path = "test_backwards.md"

        # Pre-existing Row mit file_sha1='' direkt in DB einfügen (simuliert Bestand vor Ticket 32)
        # Hinweis: ::vector-Cast kollidiert mit SQLAlchemy-Parameterformat — rohe psycopg2-Connection verwenden
        old_mtime = datetime.fromtimestamp(md_file.stat().st_mtime - 100)
        emb_str = "[" + ",".join(["0.0"] * 1024) + "]"
        with db_engine.begin() as conn:
            raw_conn = conn.connection
            cur = raw_conn.cursor()
            cur.execute(
                "INSERT INTO vault_chunks "
                "(vault_path, chunk_index, heading_path, content, frontmatter_json, mtime, file_sha1, embedding, indexed_at) "
                "VALUES (%s, 0, NULL, %s, '{}', %s, '', %s::vector, %s)",
                (vault_path, "Alter Inhalt (pre-Ticket-32)", old_mtime, emb_str, datetime.now()),
            )

        # Datei touchen (mtime ist jetzt neuer als DB-mtime)
        os.utime(str(md_file), (time.time() + 5, time.time() + 5))

        # Reindex ausführen — wegen db_hash='' darf kein Skip passieren
        counter = EmbedCallCounter()
        _register_chunker_stub_with_chunks([_make_fake_chunk(0, "Backwards-Compat\n\nVorhandene Row mit leerem Hash.")])
        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            result = _run_reindex(tmp_path, counter)

        # Reindex-Pfad muss gewählt worden sein
        assert result["files_reindexed"] == 1, (
            "Pre-existing Row mit file_sha1='' muss Reindex auslösen, kein fälschlicher Skip"
        )
        assert counter.call_count >= 1, "embed() muss aufgerufen werden"

        # SHA1 darf danach nicht mehr leer sein
        rows = _get_chunks_mtime_and_hash(db_engine, vault_path)
        assert len(rows) >= 1
        _, sha1_after = rows[0]
        assert sha1_after != "", "Nach Reindex muss file_sha1 in DB gesetzt sein"
