"""Tests für die Trade-Anzahl-Anzeige der Objekt-Toolbox.

Prüft die reine Funktion `trades_str` aus
`.claude/skills/ds-strategie-session/scripts/toolbox.py` — ohne Netzwerk-Zugriff
und ohne DB, da die Toolbox ein stdlib-only CLI-Skript ist. `trades_str` fasst
die Long/Short-Aufteilung und die am Fensterende offenen Positionen in einer Textzeile zusammen.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_TOOLBOX_PATH = (
    Path(__file__).resolve().parent.parent
    / ".claude" / "skills" / "ds-strategie-session" / "scripts" / "toolbox.py"
)


def _load_toolbox():
    """Lädt toolbox.py als Modul (Ordnername enthält Bindestriche -> kein Package-Import)."""
    spec = importlib.util.spec_from_file_location("toolbox", _TOOLBOX_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["toolbox"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def toolbox():
    return _load_toolbox()


def test_plain_total_without_extra_fields(toolbox):
    """Alt-Result ohne open_trades/long_trades/short_trades: reine Zahl."""
    assert toolbox.trades_str({"total_trades": 53}) == "53"


def test_none_total_shows_dash(toolbox):
    """Kein total_trades (None): Platzhalter statt Zahl."""
    assert toolbox.trades_str({"total_trades": None}) == "—"


def test_open_trades_appended_when_present(toolbox):
    """open_trades > 0 wird als 'offen' angehängt."""
    assert toolbox.trades_str({"total_trades": 53, "open_trades": 1}) == "53 (1 offen)"


def test_zero_open_trades_not_appended(toolbox):
    """open_trades = 0 zählt als 'keine offene Position' und wird nicht angehängt."""
    assert toolbox.trades_str({"total_trades": 53, "open_trades": 0}) == "53"


def test_long_short_split_appended_when_both_present(toolbox):
    """long_trades/short_trades werden als 'NL/MS' angehängt."""
    result = toolbox.trades_str({"total_trades": 53, "long_trades": 21, "short_trades": 32})
    assert result == "53 (21L/32S)"


def test_long_short_and_open_trades_combined(toolbox):
    """Long/Short-Aufteilung und offene Positionen erscheinen zusammen, komma-getrennt."""
    result = toolbox.trades_str({
        "total_trades": 317, "open_trades": 1, "long_trades": 166, "short_trades": 151,
    })
    assert result == "317 (166L/151S, 1 offen)"


def test_long_short_absent_when_only_one_field_present(toolbox):
    """Nur long_trades ohne short_trades (unvollständige Daten): keine Aufteilung anzeigen."""
    result = toolbox.trades_str({"total_trades": 53, "long_trades": 21})
    assert result == "53"


def test_custom_total_key_used_for_kreuztest_pairs(toolbox):
    """total_key erlaubt abweichende Schlüssel (z.B. beim Kreuztest-Zeilenpaar)."""
    assert toolbox.trades_str({"trades_b": 10}, total_key="trades_b") == "10"
