"""Tests für den Pfad-Ausschluss im Vault-Indexer (Whole-Vault-Index).

Prüft, dass _is_excluded() Obsidian-App-Verzeichnisse (.obsidian, .trash) und
alle Template-Verzeichnisse aussortiert, echte Wissens-Notizen aber durchlässt.
Zusätzlich ein reindex()-Lauf, der belegt, dass ausgeschlossene Dateien gar
nicht erst gescannt werden.

Kein PostgreSQL erforderlich: _get_engine und die Lazy-Imports (chunker,
embedding) werden über sys.modules-Stubs gemockt (gleiches Muster wie
test_indexer_mount_guard).
"""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Projekt-Root für alle Importe
_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))


# sys.modules-Stubs für Lazy-Imports in reindex() (yaml fehlt im Windows-venv)
@pytest.fixture(autouse=True)
def _stub_lazy_imports():
    """Installiert chunker-/embedding-Stubs nur während dieser Tests.

    reindex() importiert chunker und embedding lazy; hier durch MagicMock-Module
    ersetzt. Die Stubs werden nach jedem Test wieder aus sys.modules entfernt bzw.
    ein zuvor vorhandenes echtes Modul wiederhergestellt — sonst würde ein echter
    Import von services.vbt.knowledge.chunker (z.B. in tests/test_chunker.py) den
    Stub sehen und scheitern. Registrierung zur Test-Laufzeit statt beim Import,
    damit die Collection anderer Testmodule nicht vergiftet wird.
    """
    names = ("services.vbt.knowledge.chunker", "services.vbt.knowledge.embedding")
    saved = {name: sys.modules.get(name) for name in names}

    chunker_mod = types.ModuleType("services.vbt.knowledge.chunker")
    chunker_mod.chunk_markdown = MagicMock(return_value=[])
    sys.modules["services.vbt.knowledge.chunker"] = chunker_mod
    embed_mod = types.ModuleType("services.vbt.knowledge.embedding")
    embed_mod.embed = MagicMock(return_value=[0.0] * 1024)
    sys.modules["services.vbt.knowledge.embedding"] = embed_mod

    yield

    for name, prev in saved.items():
        if prev is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = prev


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


class TestIsExcluded:
    """Reine Pfad-Logik von _is_excluded()."""

    @pytest.mark.parametrize("rel_path", [
        ".obsidian/plugins/foo/README.md",
        ".trash/gelöschte-notiz.md",
        "00_Inbox/raw/roher-artikel.md",
        "00_Inbox/transcripts/video.md",
        "Clippings/web-mitschnitt.md",
        "30_Trading/templates/trading-concept.md",
        "99_Meta/templates/daily.md",
        "30_Trading/strategies/_templates/iter.md",
        "10_Clients/_template/kunde.md",
    ])
    def test_excluded_paths(self, tmp_path, rel_path):
        """App-Verzeichnisse und Template-Ordner werden ausgeschlossen."""
        from services.vbt.knowledge.indexer import _is_excluded
        full = tmp_path / rel_path
        assert _is_excluded(full, tmp_path) is True

    @pytest.mark.parametrize("rel_path", [
        "30_Trading/strategies/teststrategie/concept.md",
        "99_Meta/example/note.md",
        "40_Knowledge/sources/web/quant-stack.md",
        # Dateiname enthält "template" — darf NICHT ausgeschlossen werden (nur Verzeichnisse zählen)
        "60_Ideas/templating-strategie.md",
    ])
    def test_included_paths(self, tmp_path, rel_path):
        """Echte Wissens-Notizen bleiben drin; 'template' im Dateinamen zählt nicht."""
        from services.vbt.knowledge.indexer import _is_excluded
        full = tmp_path / rel_path
        assert _is_excluded(full, tmp_path) is False


class TestReindexSkipsExcluded:
    """reindex() darf ausgeschlossene Dateien nicht scannen."""

    def test_excluded_files_not_scanned(self, tmp_path):
        """Nur die echte Notiz wird gescannt, .obsidian- und templates-Datei nicht."""
        # Echte Notiz
        good = tmp_path / "30_Trading" / "strategies" / "teststrategie" / "concept.md"
        good.parent.mkdir(parents=True)
        good.write_text("# Teststrategie\n\nInhalt.")
        # Auszuschließende Dateien
        obs = tmp_path / ".obsidian" / "plugins" / "x" / "README.md"
        obs.parent.mkdir(parents=True)
        obs.write_text("# Plugin\n\nConfig.")
        tpl = tmp_path / "30_Trading" / "templates" / "concept.md"
        tpl.parent.mkdir(parents=True)
        tpl.write_text("# {{ title }}\n\nPlatzhalter.")

        mock_engine = _make_mock_engine()

        with patch("services.vbt.knowledge.indexer._get_engine", return_value=mock_engine), \
             patch("services.vbt.knowledge.indexer._get_db_file_state_map", return_value={}), \
             patch("services.vbt.knowledge.indexer._delete_chunks_for_path", return_value=0), \
             patch("services.vbt.knowledge.indexer._insert_chunks", return_value=1):

            from services.vbt.knowledge.indexer import reindex
            result = reindex(vault_root=tmp_path)

        # Genau eine Datei (die echte Notiz) gescannt
        assert result["files_scanned"] == 1

    def test_existing_excluded_file_is_purged(self, tmp_path):
        """Eine ausgeschlossene Datei, die noch auf der Platte liegt, wird aus der DB entfernt."""
        # Echte Notiz, damit md_files nicht leer ist (sonst Mount-Guard-Raise)
        good = tmp_path / "30_Trading" / "strategies" / "teststrategie" / "concept.md"
        good.parent.mkdir(parents=True)
        good.write_text("# Teststrategie\n\nInhalt.")
        # Ausgeschlossene, aber existierende Inbox-Datei
        inbox = tmp_path / "00_Inbox" / "raw" / "note.md"
        inbox.parent.mkdir(parents=True)
        inbox.write_text("# Roh\n\nUnsortiert.")

        # Engine, dessen DISTINCT-vault_path-Query die Inbox-Datei zurückliefert
        excluded_vp = "00_Inbox/raw/note.md"
        row = types.SimpleNamespace(vault_path=excluded_vp)
        engine = _make_mock_engine()
        engine.connect.return_value.__enter__.return_value.execute.return_value.fetchall.return_value = [row]

        with patch("services.vbt.knowledge.indexer._get_engine", return_value=engine), \
             patch("services.vbt.knowledge.indexer._get_db_file_state_map", return_value={}), \
             patch("services.vbt.knowledge.indexer._delete_chunks_for_path", return_value=1) as mock_delete, \
             patch("services.vbt.knowledge.indexer._insert_chunks", return_value=1):

            from services.vbt.knowledge.indexer import reindex
            result = reindex(vault_root=tmp_path)

        # Die Inbox-Datei wurde trotz Existenz bereinigt
        mock_delete.assert_any_call(engine, excluded_vp)
        assert result["files_deleted"] == 1
        assert excluded_vp in result["deleted_paths"]
