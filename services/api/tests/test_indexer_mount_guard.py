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

@pytest.fixture(autouse=True)
def stub_lazy_imports():
    """Installiert chunker-/embedding-Stubs nur während dieser Tests.

    reindex() importiert chunker und embedding lazy; hier durch MagicMock-Module
    ersetzt (yaml/Embedding-Server nicht nötig). Die Stubs werden nach jedem Test
    wieder aus sys.modules entfernt bzw. ein zuvor vorhandenes echtes Modul
    wiederhergestellt — sonst würde ein echter Import von
    services.vbt.knowledge.chunker (z.B. in tests/test_chunker.py) den Stub sehen
    und scheitern. Registrierung zur Test-Laufzeit statt beim Import, damit die
    Collection anderer Testmodule nicht vergiftet wird.

    Gibt die beiden Stub-Module zurück, damit einzelne Tests chunk_markdown/embed
    temporär mit eigenem Verhalten überschreiben können.
    """
    names = ("services.vbt.knowledge.chunker", "services.vbt.knowledge.embedding")
    saved = {name: sys.modules.get(name) for name in names}

    chunker_mod = types.ModuleType("services.vbt.knowledge.chunker")
    chunker_mod.chunk_markdown = MagicMock(return_value=[])
    sys.modules["services.vbt.knowledge.chunker"] = chunker_mod
    embed_mod = types.ModuleType("services.vbt.knowledge.embedding")
    embed_mod.embed = MagicMock(return_value=[0.0] * 1024)
    sys.modules["services.vbt.knowledge.embedding"] = embed_mod

    yield types.SimpleNamespace(chunker=chunker_mod, embedding=embed_mod)

    for name, prev in saved.items():
        if prev is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = prev


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

    def test_normal_reindex_does_not_raise(self, tmp_path, stub_lazy_imports):
        """vault_root existiert + enthält .md → kein Raise, Embedding wird aufgerufen."""
        md_file = tmp_path / "strategies" / "teststrategie" / "STATUS.md"
        md_file.parent.mkdir(parents=True)
        md_file.write_text("# Teststrategie Status\n\nTestinhalt für Embedding-Mock.")

        fake_embedding = [0.1] * 1024
        mock_engine = _make_mock_engine()

        # Fake-Chunk — der chunker- und embedding-Stub aus der Fixture sind bereits
        # in sys.modules registriert; chunk_markdown/embed werden hier überschrieben
        fake_chunk = MagicMock()
        fake_chunk.chunk_index = 0
        fake_chunk.heading_path = "Teststrategie Status"
        fake_chunk.content = "Testinhalt für Embedding-Mock."
        fake_chunk.frontmatter = {}

        stub_lazy_imports.chunker.chunk_markdown = MagicMock(return_value=[fake_chunk])
        stub_lazy_imports.embedding.embed = MagicMock(return_value=fake_embedding)

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
