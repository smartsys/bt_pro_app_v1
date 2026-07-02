"""Tests für die Indikator-Katalog-Filterung der Objekt-Toolbox (Ticket 50).

Prüft die reinen Funktionen `_filter_indicators` und `_format_indicator_line`
aus `.claude/skills/ds-strategie-session/scripts/toolbox.py` — ohne Netzwerk-
Zugriff und ohne DB, da die Toolbox ein stdlib-only CLI-Skript ist.
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


@pytest.fixture
def sample_groups():
    """Kleiner Katalog-Ausschnitt nach dem Schema von GET /api/chart-playground/indicators."""
    return [
        {
            "name": "talib",
            "indicators": [
                {
                    "id": "talib:EMA",
                    "name": "EMA",
                    "group": "talib",
                    "inputs": ["close"],
                    "params": [{"name": "timeperiod", "default": 30}],
                    "outputs": ["real"],
                },
                {
                    "id": "talib:AD",
                    "name": "AD",
                    "group": "talib",
                    "inputs": ["high", "low", "close", "volume"],
                    "params": [],
                    "outputs": ["real"],
                },
            ],
        },
        {
            "name": "ta",
            "indicators": [
                {
                    "id": "ta:EMAIndicator",
                    "name": "EMAIndicator",
                    "group": "ta",
                    "inputs": ["close"],
                    "params": [{"name": "window", "default": 14}, {"name": "fillna", "default": False}],
                    "outputs": ["ema_indicator"],
                },
            ],
        },
    ]


def test_filter_by_group_only(toolbox, sample_groups):
    matches = toolbox._filter_indicators(sample_groups, group_filter="talib", search="")
    assert [m["id"] for m in matches] == ["talib:EMA", "talib:AD"]


def test_filter_by_search_only_case_insensitive(toolbox, sample_groups):
    matches = toolbox._filter_indicators(sample_groups, group_filter=None, search="EMA")
    ids = {m["id"] for m in matches}
    assert ids == {"talib:EMA", "ta:EMAIndicator"}


def test_filter_combined_group_and_search(toolbox, sample_groups):
    matches = toolbox._filter_indicators(sample_groups, group_filter="talib", search="ema")
    assert [m["id"] for m in matches] == ["talib:EMA"]


def test_filter_no_match(toolbox, sample_groups):
    matches = toolbox._filter_indicators(sample_groups, group_filter=None, search="nichtvorhanden")
    assert matches == []


def test_filter_without_filters_returns_all(toolbox, sample_groups):
    matches = toolbox._filter_indicators(sample_groups, group_filter=None, search="")
    assert len(matches) == 3


def test_format_indicator_line_with_params(toolbox, sample_groups):
    ind = sample_groups[0]["indicators"][0]
    line = toolbox._format_indicator_line(ind)
    assert line == (
        "- **talib:EMA** — inputs: close | params: timeperiod | outputs: real"
    )


def test_format_indicator_line_without_params(toolbox, sample_groups):
    ind = sample_groups[0]["indicators"][1]
    line = toolbox._format_indicator_line(ind)
    assert line == (
        "- **talib:AD** — inputs: high, low, close, volume | params: — | outputs: real"
    )


def test_print_data_truncation_hint(toolbox, capsys):
    """_print_data muss bei Kürzung die Original-Größe sichtbar ausweisen (Ticket 50, Anforderung 3)."""
    big_payload = {"data": {"items": ["x" * 100 for _ in range(100)]}}
    toolbox._print_data("test-verb", big_payload)
    out = capsys.readouterr().out
    assert "gekürzt" in out
    assert "4000 von" in out


def test_print_data_no_hint_when_short(toolbox, capsys):
    """Kurze Antworten bleiben unverändert — kein Kürzungs-Hinweis."""
    small_payload = {"data": {"a": 1}}
    toolbox._print_data("test-verb", small_payload)
    out = capsys.readouterr().out
    assert "gekürzt" not in out
