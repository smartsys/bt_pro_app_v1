"""Tests für das Preflight-Verb der Objekt-Toolbox (Anforderung 5).

Prüft die reine Funktion `preflight_run` aus
`.claude/skills/ds-strategie-session/scripts/toolbox.py` — ohne Netzwerk-Zugriff
(`post` wird gemockt), da die Toolbox ein stdlib-only CLI-Skript ist. Die
Server-Logik der Route selbst steht in tests/test_preflight_endpoint.py.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

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


# Realistische Server-Antwort (Form entspricht services/api/routes/api_chart_playground.py::preflight,
# Werte wie am 13.08.2026 real gegen iteration:12 + indicator-config:56 + backtest-config:918 gemessen).
_SAMPLE_RESPONSE = {
    "data": {
        "iteration_id": 12, "indicator_config_id": 56, "backtest_config_id": 918,
        "n_combinations": 240,
        "warmup": {
            "level": "warning",
            "note": "Kein Vorlauf: ohlc_start (2022-01-01) fällt mit start (2022-01-01) zusammen.",
            "warmup_bars": 0, "required_bars": 14, "available_bars": 540, "source": "vwma.length",
        },
        "entry_signals": {"count": 84, "first_time": "2022-01-03 20:00:00+00:00",
                           "last_time": "2022-03-31 20:00:00+00:00", "note": None},
        "exit_signals": {"count": 0, "first_time": None, "last_time": None,
                          "note": "keine Exit-Regeln konfiguriert (spec_json.rules.exit ist leer)"},
        "indicator_nan_ratio": {"fast_sma.result": 0.0037, "vwma.result": 0.0056},
        "single_combo_duration_ms": 63,
        "estimated_full_runtime_ms": 15120,
        "estimated_full_runtime_note": "Grobe lineare Hochrechnung.",
    },
    "error": None,
}


def test_preflight_verlangt_alle_drei_flags(toolbox):
    """Fehlt eine der drei Pflicht-IDs, bricht das Verb mit klarer Meldung ab."""
    with pytest.raises(ValueError):
        toolbox.preflight_run(["--iteration", "12", "--indicator-config", "56"])


def test_preflight_gibt_kombinationszahl_und_signale_aus(toolbox, capsys):
    """Preflight druckt Rastergröße, Entry-/Exit-Signale und Vorlauf-Notiz."""
    with patch.object(toolbox, "post", return_value=_SAMPLE_RESPONSE) as mock_post:
        rc = toolbox.preflight_run(
            ["--iteration", "12", "--indicator-config", "56", "--backtest-config", "918"]
        )

    assert rc == 0
    mock_post.assert_called_once()
    call_path, call_body = mock_post.call_args[0][0], mock_post.call_args[0][1]
    assert call_path == "/api/chart-playground/preflight"
    assert call_body == {"iteration_id": 12, "indicator_config_id": 56, "backtest_config_id": 918}

    out = capsys.readouterr().out
    assert "**240**" in out
    assert "Entry-Signale: 84" in out
    assert "Exit-Signale: 0" in out
    assert "Kein Vorlauf" in out
    assert "63 ms" in out


def test_preflight_warnt_bei_null_entry_signalen(toolbox, capsys):
    """Null Entry-Signale lösen die explizite Warnung aus (der teuerste Fehler)."""
    resp = {**_SAMPLE_RESPONSE, "data": {**_SAMPLE_RESPONSE["data"],
            "entry_signals": {"count": 0, "first_time": None, "last_time": None, "note": None}}}
    with patch.object(toolbox, "post", return_value=resp):
        toolbox.preflight_run(
            ["--iteration", "918", "--indicator-config", "76", "--backtest-config", "2"]
        )

    out = capsys.readouterr().out
    assert "WARNUNG" in out
    assert "0 Trades" in out


def test_preflight_ohne_null_signale_keine_warnung(toolbox, capsys):
    """Gegenprobe: Entry-Signale vorhanden -> keine Warnzeile."""
    with patch.object(toolbox, "post", return_value=_SAMPLE_RESPONSE):
        toolbox.preflight_run(
            ["--iteration", "12", "--indicator-config", "56", "--backtest-config", "918"]
        )

    out = capsys.readouterr().out
    assert "WARNUNG" not in out
