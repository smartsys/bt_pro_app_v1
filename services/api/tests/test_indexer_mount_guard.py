"""Tests für den Mount-Guard im Vault-Indexer (Ticket 31).

Prüft, dass reindex() bei nicht erreichbarem vault_root oder leerer
Dateiliste einen RuntimeError wirft — ohne die DB anzutasten.

Kein PostgreSQL erforderlich: _get_engine und die Lazy-Imports (chunker,
embedding) werden vollständig über sys.modules gemockt. Die DB-Chunk-
Invarianz wird über Call-Count-Prüfungen auf _delete_chunks_for_path
und _insert_chunks sichergestellt.
"""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Projekt-Root für alle Importe
_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))


# ============================================================================
# sys.modules-Stubs für Lazy-Imports in reindex() (yaml fehlt in Windows-venv)
# ============================================================================

def _register_chunker_stub(fake_chunk_markdown=None):
    """Registriert einen minimalen chunker-Stub in sys.modules."""
    chunker_mod = types.ModuleType("services.vbt.knowledge.chunker")
    if fake_chunk_markdown is None:
        fake_chunk_markdown = MagicMock(return_value=[])
    chunker_mod.chunk_markdown = fake_chunk_markdown
    sys.modules.setdefault("services.vbt.knowledge.chunker", chunker_mod)
    return chunker_mod


def _register_embedding_stub(fake_embed=None):
    """Registriert einen minimalen embedding-Stub in sys.modules."""
    embed_mod = types.ModuleType("services.vbt.knowledge.embedding")
    if fake_embed is None:
        fake_embed = MagicMock(return_value=[0.0] * 1024)
    embed_mod.embed = fake_embed
    sys.modules.setdefault("services.vbt.knowledge.embedding", embed_mod)
    return embed_mod


# Stubs einmalig registrieren — bevor indexer importiert wird.
# setdefault() ist idempotent; spezifische Tests können die Stubs mit
# patch() temporär überschreiben.
_chunker_stub = _register_chunker_stub()
_embedding_stub = _register_embedding_stub()


# ============================================================================
# Hilfsfunktionen
# ============================================================================

def _make_mock_engine() -> MagicMock:
    """Erstellt eine minimale Mock-Engine, die keine DB-Verbindung benötigt."""
    engine = MagicMock()
    conn_ctx = MagicMock()
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = []
    conn_ctx.__enter__ = MagicMock(return_value=conn)
    conn_ctx.__exit__ = MagicMock(return_value=False)
    engine.connect.return_value = conn_ctx
    engine.begin.return_value = conn_ctx
    return engine


# ============================================================================
# Tests
# ============================================================================

class TestMountGuardSchritt_A:
    """Schritt A: vault_root existiert nicht."""

    def test_nonexistent_vault_root_raises_runtime_error(self):
        """vault_root existiert nicht → RuntimeError, kein DB-Zugriff."""
        nonexistent = Path("/definitely/nonexistent/vault")

        with patch("services.vbt.knowledge.indexer._get_engine") as mock_engine, \
             patch("services.vbt.knowledge.indexer._delete_chunks_for_path") as mock_delete, \
             patch("services.vbt.knowledge.indexer._insert_chunks") as mock_insert:

            mock_engine.return_value = _make_mock_engine()

            with pytest.raises(RuntimeError, match="vault_root nicht erreichbar"):
                from services.vbt.knowledge.indexer import reindex
                reindex(vault_root=nonexistent)

            # DB darf nicht angefasst worden sein
            mock_delete.assert_not_called()
            mock_insert.assert_not_called()

    def test_nonexistent_vault_root_with_target_path_raises_runtime_error(self):
        """vault_root weg + target_path gesetzt: RuntimeError aus Schritt A, nicht ValueError."""
        nonexistent = Path("/definitely/nonexistent/vault")
        target = nonexistent / "strategies/teststrategie/STATUS.md"

        with patch("services.vbt.knowledge.indexer._get_engine") as mock_engine, \
             patch("services.vbt.knowledge.indexer._delete_chunks_for_path") as mock_delete, \
             patch("services.vbt.knowledge.indexer._insert_chunks") as mock_insert:

            mock_engine.return_value = _make_mock_engine()

            with pytest.raises(RuntimeError, match="vault_root nicht erreichbar"):
                from services.vbt.knowledge.indexer import reindex
                reindex(vault_root=nonexistent, target_path=target)

            mock_delete.assert_not_called()
            mock_insert.assert_not_called()


class TestMountGuardSchritt_B:
    """Schritt B: vault_root vorhanden, aber keine .md-Dateien (leerer Mount)."""

    def test_empty_vault_root_raises_runtime_error(self, tmp_path):
        """vault_root existiert, enthält aber keine .md-Dateien → RuntimeError."""
        # tmp_path ist ein leeres Verzeichnis — simuliert montierten aber leeren Mount
        with patch("services.vbt.knowledge.indexer._get_engine") as mock_engine, \
             patch("services.vbt.knowledge.indexer._delete_chunks_for_path") as mock_delete, \
             patch("services.vbt.knowledge.indexer._insert_chunks") as mock_insert:

            mock_engine.return_value = _make_mock_engine()

            with pytest.raises(RuntimeError, match="Mount vermutlich weg"):
                from services.vbt.knowledge.indexer import reindex
                reindex(vault_root=tmp_path)

            mock_delete.assert_not_called()
            mock_insert.assert_not_called()


class TestSingleFileCleanup:
    """Single-File-Pfad: vault_root da, Datei selbst verschwunden → normaler Cleanup."""

    def test_single_file_cleanup_no_raise(self, tmp_path):
        """target_path zeigt auf nicht existente Datei → kein Raise, files_deleted=1."""
        missing_target = tmp_path / "strategies" / "teststrategie" / "STATUS.md"
        # missing_target existiert NICHT — Schritt B greift nur beim Voll-Reindex

        mock_engine = _make_mock_engine()

        with patch("services.vbt.knowledge.indexer._get_engine", return_value=mock_engine), \
             patch("services.vbt.knowledge.indexer._delete_chunks_for_path", return_value=1) as mock_delete, \
             patch("services.vbt.knowledge.indexer._get_db_file_state_map", return_value={}) as mock_state, \
             patch("services.vbt.knowledge.indexer._insert_chunks") as mock_insert:

            from services.vbt.knowledge.indexer import reindex
            result = reindex(vault_root=tmp_path, target_path=missing_target)

        assert result["files_deleted"] == 1
        assert result["files_reindexed"] == 0
        mock_delete.assert_called_once()
        mock_insert.assert_not_called()


class TestNormalfall:
    """Regression-Check: vault_root mit .md-Dateien → reindex läuft normal."""

    def test_normal_reindex_does_not_raise(self, tmp_path):
        """vault_root existiert + enthält .md → kein Raise, Embedding wird aufgerufen."""
        md_file = tmp_path / "strategies" / "teststrategie" / "STATUS.md"
        md_file.parent.mkdir(parents=True)
        md_file.write_text("# Teststrategie Status\n\nTestinhalt für Embedding-Mock.")

        fake_embedding = [0.1] * 1024
        mock_engine = _make_mock_engine()

        # Fake-Chunk — der chunker_stub und embedding_stub sind bereits in sys.modules
        # registriert; chunk_markdown-Attribut wird hier temporär überschrieben
        fake_chunk = MagicMock()
        fake_chunk.chunk_index = 0
        fake_chunk.heading_path = "Teststrategie Status"
        fake_chunk.content = "Testinhalt für Embedding-Mock."
        fake_chunk.frontmatter = {}

        _chunker_stub.chunk_markdown = MagicMock(return_value=[fake_chunk])
        _embedding_stub.embed = MagicMock(return_value=fake_embedding)

        with patch("services.vbt.knowledge.indexer._get_engine", return_value=mock_engine), \
             patch("services.vbt.knowledge.indexer._get_db_file_state_map", return_value={}) as mock_state, \
             patch("services.vbt.knowledge.indexer._delete_chunks_for_path", return_value=0), \
             patch("services.vbt.knowledge.indexer._insert_chunks", return_value=1) as mock_insert:

            from services.vbt.knowledge.indexer import reindex
            result = reindex(vault_root=tmp_path)

        # Kein Fehler, mindestens eine Datei gescannt
        assert result["files_scanned"] >= 1
        assert result["files_reindexed"] >= 1
        assert "duration_seconds" in result
