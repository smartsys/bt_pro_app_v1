"""Tests für Sentinel-Row-Logik im Vault-Indexer (Ticket 33, Teil A).

Prüft, dass Stub-Dateien (0 Chunks) eine Sentinel-Row in vault_chunks
erhalten und beim nächsten Lauf korrekt als unverändert erkannt werden.

Verwendet PostgreSQL Test-DB (Port 5562) via db_engine/session-Fixtures
aus tests/conftest.py.
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
# Hilfsfunktionen und Stubs
# ============================================================================

class EmbedCallCounter:
    """Embed-Mock der Aufrufe zählt."""

    def __init__(self):
        self.call_count = 0

    def __call__(self, content: str) -> list[float]:
        self.call_count += 1
        return [0.0] * 1024


def _make_fake_chunk(chunk_index: int = 0, content: str = "Testinhalt") -> MagicMock:
    chunk = MagicMock()
    chunk.chunk_index = chunk_index
    chunk.heading_path = "Testüberschrift"
    chunk.content = content
    chunk.frontmatter = {}
    return chunk


def _register_chunker_stub(chunks: list) -> None:
    """Registriert einen chunker-Stub in sys.modules."""
    chunker_mod = types.ModuleType("services.vbt.knowledge.chunker")
    chunker_mod.chunk_markdown = MagicMock(return_value=chunks)
    sys.modules["services.vbt.knowledge.chunker"] = chunker_mod


def _register_embed_stub(counter: EmbedCallCounter) -> None:
    """Registriert einen embedding-Stub in sys.modules."""
    embed_mod = types.ModuleType("services.vbt.knowledge.embedding")
    embed_mod.embed = counter
    sys.modules["services.vbt.knowledge.embedding"] = embed_mod


def _run_reindex(vault_root: Path, embed_counter: EmbedCallCounter, target_path: Path | None = None) -> dict:
    """Führt reindex() mit frischen Stubs aus."""
    _register_embed_stub(embed_counter)
    from services.vbt.knowledge.indexer import reindex
    return reindex(vault_root=vault_root, target_path=target_path)


def _get_sentinel_rows(engine, vault_path: str) -> list:
    """Liest alle Rows für einen vault_path aus vault_chunks."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT chunk_index, content, embedding, file_sha1, mtime "
                "FROM vault_chunks WHERE vault_path = :vp ORDER BY chunk_index"
            ),
            {"vp": vault_path},
        ).fetchall()
    return rows


# ============================================================================
# Tests
# ============================================================================

class TestSentinelRowAnlegen:
    """Stub-Datei → Sentinel-Row wird angelegt."""

    def test_stub_datei_erzeugt_sentinel_row(self, db_engine, tmp_path):
        """Stub (0 Chunks) → eine Row mit chunk_index=0, content='', embedding=NULL."""
        md_file = tmp_path / "stub.md"
        md_file.write_text("---\ntitle: Stub\n---\n")

        vault_path = "stub.md"
        counter = EmbedCallCounter()
        _register_chunker_stub([])  # Kein Chunk

        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            result = _run_reindex(tmp_path, counter)

        assert result["files_reindexed"] == 1, f"files_reindexed erwartet 1, war: {result['files_reindexed']}"

        rows = _get_sentinel_rows(db_engine, vault_path)
        assert len(rows) == 1, f"Erwartet 1 Sentinel-Row, war: {len(rows)}"
        row = rows[0]
        assert row.chunk_index == 0, f"chunk_index erwartet 0, war: {row.chunk_index}"
        assert row.content == '' or row.content is None, f"content muss leer sein, war: {row.content!r}"
        assert row.embedding is None, "embedding muss NULL sein für Sentinel-Row"
        assert row.file_sha1 != '', "file_sha1 muss gesetzt sein"

    def test_embed_nicht_aufgerufen_bei_stub(self, db_engine, tmp_path):
        """embed() darf bei Stub-Datei nicht aufgerufen werden."""
        md_file = tmp_path / "stub_noembed.md"
        md_file.write_text("---\ntitle: Kein Content\n---\n")

        counter = EmbedCallCounter()
        _register_chunker_stub([])

        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            _run_reindex(tmp_path, counter)

        assert counter.call_count == 0, f"embed() darf nicht aufgerufen werden, war: {counter.call_count}"


class TestSentinelRowSkip:
    """Folge-Reindex erkennt Stub als unverändert."""

    def test_zweiter_reindex_stub_unveraendert(self, db_engine, tmp_path):
        """Zweiter Reindex direkt nach Sentinel-Insert → files_unchanged=1, files_reindexed=0."""
        md_file = tmp_path / "stub_skip.md"
        md_file.write_text("---\ntitle: Skip-Test\n---\n")

        vault_path = "stub_skip.md"
        counter1 = EmbedCallCounter()
        _register_chunker_stub([])

        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            result1 = _run_reindex(tmp_path, counter1)

        assert result1["files_reindexed"] == 1

        # Zweiter Lauf — Datei unverändert, mtime identisch
        counter2 = EmbedCallCounter()
        _register_chunker_stub([])

        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            result2 = _run_reindex(tmp_path, counter2)

        assert result2["files_reindexed"] == 0, f"Zweiter Lauf darf nicht reindizieren, war: {result2['files_reindexed']}"
        assert result2["files_unchanged"] == 0, "Fast-Path (mtime unverändert) zählt nicht als unchanged"
        assert counter2.call_count == 0, "embed() darf nicht aufgerufen werden"

    def test_touch_stub_loest_nur_mtime_update(self, db_engine, tmp_path):
        """Touch der Stub-Datei → nur _bump_mtime_only, kein Embedding-Aufruf."""
        md_file = tmp_path / "stub_touch.md"
        md_file.write_text("---\ntitle: Touch-Test\n---\n")

        vault_path = "stub_touch.md"
        counter1 = EmbedCallCounter()
        _register_chunker_stub([])

        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            result1 = _run_reindex(tmp_path, counter1)
        assert result1["files_reindexed"] == 1

        # Datei touchen (mtime ändern, Hash bleibt gleich)
        os.utime(str(md_file), (time.time() + 10, time.time() + 10))

        counter2 = EmbedCallCounter()
        _register_chunker_stub([])

        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            result2 = _run_reindex(tmp_path, counter2)

        assert counter2.call_count == 0, "embed() darf nicht aufgerufen werden (nur Touch)"
        assert result2["files_unchanged"] == 1, f"files_unchanged erwartet 1, war: {result2['files_unchanged']}"
        assert result2["files_reindexed"] == 0, "files_reindexed muss 0 sein nach Touch-Skip"


class TestStubZuEchtemContent:
    """Wechsel Stub → echter Content und umgekehrt."""

    def test_stub_zu_echtem_content(self, db_engine, tmp_path):
        """Stub → echter Content beim nächsten Reindex → Sentinel-Row durch echte Chunks ersetzt."""
        md_file = tmp_path / "stub_to_content.md"
        md_file.write_text("---\ntitle: Test\n---\n")

        vault_path = "stub_to_content.md"
        counter1 = EmbedCallCounter()
        _register_chunker_stub([])

        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            result1 = _run_reindex(tmp_path, counter1)
        assert result1["files_reindexed"] == 1

        # Datei mit echtem Content überschreiben
        time.sleep(0.05)
        md_file.write_text("---\ntitle: Test\n---\n\n## Abschnitt\n\nEchter Text hier.")

        counter2 = EmbedCallCounter()
        _register_chunker_stub([_make_fake_chunk(0, "Echter Text hier.")])

        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            result2 = _run_reindex(tmp_path, counter2)

        assert result2["files_reindexed"] == 1
        assert counter2.call_count >= 1, "embed() muss aufgerufen werden"

        rows = _get_sentinel_rows(db_engine, vault_path)
        assert len(rows) >= 1
        # Mindestens eine Row muss embedding != NULL haben
        non_null_emb = [r for r in rows if r.embedding is not None]
        assert len(non_null_emb) >= 1, "Nach Content-Hinzufügen muss embedding != NULL sein"

    def test_echter_content_zu_stub(self, db_engine, tmp_path):
        """Echter Content → Stub → Sentinel-Row ersetzt echte Chunk-Rows."""
        md_file = tmp_path / "content_to_stub.md"
        md_file.write_text("# Überschrift\n\nInhalt der Datei.")

        vault_path = "content_to_stub.md"
        counter1 = EmbedCallCounter()
        _register_chunker_stub([_make_fake_chunk(0, "Inhalt der Datei.")])

        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            result1 = _run_reindex(tmp_path, counter1)
        assert result1["files_reindexed"] == 1
        assert counter1.call_count >= 1

        # Datei zu reinem Stub machen
        time.sleep(0.05)
        md_file.write_text("---\ntitle: Stub jetzt\n---\n")

        counter2 = EmbedCallCounter()
        _register_chunker_stub([])  # Keine Chunks mehr

        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            result2 = _run_reindex(tmp_path, counter2)

        assert result2["files_reindexed"] == 1
        assert counter2.call_count == 0, "embed() darf nicht aufgerufen werden"

        rows = _get_sentinel_rows(db_engine, vault_path)
        assert len(rows) == 1, f"Nur eine Sentinel-Row erwartet, war: {len(rows)}"
        assert rows[0].embedding is None, "Sentinel-Row muss embedding=NULL haben"


class TestSentinelRowCleanup:
    """Löschen einer Stub-Datei wird vom Cleanup-Pfad erfasst."""

    def test_stub_datei_loeschen_wird_erkannt(self, db_engine, tmp_path):
        """Stub-Datei löschen → nächster Reindex entfernt Sentinel-Row, files_deleted=1.

        Hinweis: Mount-Guard verhindert Voll-Reindex ohne .md-Dateien. Daher bleibt eine
        zweite .md-Datei im vault_root erhalten, damit der Guard nicht anschlägt.
        """
        md_file = tmp_path / "stub_delete.md"
        md_file.write_text("---\ntitle: Wird gelöscht\n---\n")

        # Zweite Datei damit Mount-Guard beim zweiten Lauf nicht anschlägt
        md_anchor = tmp_path / "anchor.md"
        md_anchor.write_text("# Anker-Datei\n\nBleibt im Vault.")

        vault_path = "stub_delete.md"
        counter1 = EmbedCallCounter()
        _register_chunker_stub([])

        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            result1 = _run_reindex(tmp_path, counter1)
        assert result1["files_reindexed"] >= 1

        # Stub löschen, Anchor bleibt
        md_file.unlink()

        counter2 = EmbedCallCounter()
        _register_chunker_stub([])

        with patch("services.vbt.knowledge.indexer._get_engine", return_value=db_engine):
            result2 = _run_reindex(tmp_path, counter2)

        assert result2["files_deleted"] == 1, f"files_deleted erwartet 1, war: {result2['files_deleted']}"

        rows = _get_sentinel_rows(db_engine, vault_path)
        assert len(rows) == 0, "Sentinel-Row muss nach Löschen der Datei entfernt sein"


class TestSentinelRowSuchfilter:
    """Sentinel-Rows tauchen nicht in API-Suchergebnissen auf."""

    def test_search_filtert_sentinel_rows(self, db_engine, monkeypatch):
        """GET /api/knowledge/search darf keine Sentinel-Rows zurückgeben.

        Verwendet minimale FastAPI-App mit gemocktem embed und Test-DB.
        """
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import user_data.utils.database.db as _db_module

        # Minimale App aufbauen (ohne rq-Abhängigkeiten aus api_backtest)
        from services.api.routes.api_knowledge import router as knowledge_router
        test_app = FastAPI()
        test_app.include_router(knowledge_router)

        vault_path = "sentinel_search_test/stub_search.md"

        # Sentinel-Row direkt in Test-DB schreiben
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO vault_chunks "
                    "(vault_path, chunk_index, content, embedding, mtime, file_sha1, indexed_at) "
                    "VALUES (:vp, 0, '', NULL, NOW(), 'searchtest123', NOW())"
                ),
                {"vp": vault_path},
            )

        # Test-DB-Session und Mocks setzen
        monkeypatch.setattr('services.api.routes.api_knowledge.embed', lambda t: [0.0] * 1024)
        monkeypatch.setattr(_db_module, '_engine', None)
        monkeypatch.setattr(_db_module, '_session_factory', None)

        with TestClient(test_app) as c:
            response = c.get("/api/knowledge/search?q=Such-Stub&k=50")

        assert response.status_code == 200
        results = response.json().get("results", [])
        sentinel_in_results = [r for r in results if r["vault_path"] == vault_path]
        assert len(sentinel_in_results) == 0, (
            "Sentinel-Row darf nicht in Suchergebnissen erscheinen"
        )
