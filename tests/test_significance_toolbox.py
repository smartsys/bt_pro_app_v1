"""Tests der Toolbox-Verben zum Signifikanztest.

Geprüft werden `significance_start`, `significance_read`, `significance_list` und
`_print_significance` aus
`.claude/skills/ds-strategie-session/scripts/toolbox.py` — ohne Netzwerk-Zugriff
(`fetch`/`post` werden ersetzt), da die Toolbox ein stdlib-only CLI-Skript ist. Die
Server-Logik steht in tests/test_significance_api.py.

Kernregel der Ausgabe: **ein p-Wert erscheint nie ohne seine Null-Verteilung** —
und es gibt kein Bestanden-Feld und keine Sortierung nach p-Wert.
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


_PERMUTATION_TEST = {
    "id": 12, "result_id": 2706026, "run_id": 1812, "iteration_id": 41,
    "params_json": {"actual_params": {"vwma_length": 20}, "indicators": {}},
    "config_snapshot_json": {
        "symbol": "FETUSDT", "exchange": "binance", "timeframe": "4h",
        "start": "2022-01-01", "end": "2023-01-01",
    },
    "method": "permutation", "n_iterations": 300, "seed": 42, "status": "completed",
    "error_message": None, "created_at": "2026-08-14T12:00:00", "duration_seconds": 187.4,
    "real_values_json": {"sharpe_ratio": 2.07, "profit_factor": 6.12, "total_return_pct": 288.1},
    "distribution_json": {
        "sharpe_ratio": [0.1, 0.2, None], "profit_factor": [1.0, None, 1.2],
        "total_return_pct": [3.0, -2.0, 1.0],
    },
    "summary_json": {
        "metrics": {
            "sharpe_ratio": {
                "real_value": 2.07, "p_value": 0.0033, "p_value_missing_reason": None,
                "n_iterations": 300, "n_ge_real": 0, "n_non_finite": 12,
                "null_distribution": {
                    "mean": 0.15, "median": 0.11, "p05": -1.2, "p95": 1.5, "max": 1.9,
                    "n_total": 300, "n_finite": 288,
                },
            },
            "profit_factor": {
                "real_value": None, "p_value": None,
                "p_value_missing_reason": "echter Wert ist nicht endlich",
                "n_iterations": 300, "n_ge_real": 0, "n_non_finite": 300,
                "null_distribution": {
                    "mean": None, "median": None, "p05": None, "p95": None, "max": None,
                    "n_total": 300, "n_finite": 0,
                },
            },
        },
        "no_trade_runs": {"count": 12, "share": 0.04, "note": "mitgezählt"},
        "reference_check": {
            "tolerance": 1e-09,
            "compared": {"sharpe_ratio": {"stored": 2.07, "reference": 2.07, "matches": True}},
            "unchecked": {"profit_factor": "am Result nicht gespeichert (NULL)"},
        },
        "metric_names": ["sharpe_ratio", "profit_factor"],
        "metric_groups": ["returns", "risk_ratios"],
    },
}

_BOOTSTRAP_TEST = {
    **_PERMUTATION_TEST,
    "id": 13, "method": "bootstrap", "n_iterations": 2000, "duration_seconds": 1.2,
    "real_values_json": {"mean_return_pct": 0.23, "median_return_pct": 0.1,
                         "profit_factor": 1.4},
    "distribution_json": {"trade_return_pct": [1.0, -0.5, 2.0]},
    "summary_json": {
        "n_trades": 767, "n_rounds": 2000, "seed": 42,
        "observed": {"mean_return_pct": 0.23, "median_return_pct": 0.1,
                     "profit_factor": 1.4},
        "bands": {
            "mean_return_pct": {"p05": 0.05, "p50": 0.23, "p95": 0.42, "n_non_finite": 0},
            "median_return_pct": {"p05": -0.1, "p50": 0.1, "p95": 0.3, "n_non_finite": 0},
            "profit_factor": {"p05": 1.1, "p50": 1.4, "p95": 1.8, "n_non_finite": 0},
        },
        "share_pf_le_one": 0.021,
        "share_pf_le_one_note": "Bootstrap-Anteil, KEIN p-Wert eines Nullmodells",
        "profit_factor_basis": "Trade-Renditen (return_pct)",
    },
}


# ---------------------------------------------------------------------------
# Ausgabe: p-Wert nie ohne Null-Verteilung
# ---------------------------------------------------------------------------

def test_permutation_output_shows_p_value_next_to_its_null_distribution(toolbox, capsys):
    """Jede p-Wert-Zeile trägt zugleich die Kennwerte ihrer Null-Verteilung."""
    toolbox._print_significance(_PERMUTATION_TEST)
    out = capsys.readouterr().out
    header_line = next(line for line in out.splitlines() if line.startswith("| Metrik"))
    assert "echter Wert" in header_line
    assert "Null-Verteilung" in header_line
    assert "p-Wert" in header_line
    assert header_line.index("Null-Verteilung") < header_line.index("p-Wert"), (
        "Die Null-Verteilung steht vor dem p-Wert"
    )

    sharpe_line = next(line for line in out.splitlines() if line.startswith("| sharpe_ratio"))
    assert "0.0033" in sharpe_line, "p-Wert steht in der Zeile"
    for value in ("0.1500", "0.1100", "-1.2000", "1.5000", "1.9000"):
        assert value in sharpe_line, f"Kennwert {value} fehlt in derselben Zeile"


def test_permutation_output_names_the_reason_when_a_p_value_is_missing(toolbox, capsys):
    """Ohne endlichen echten Wert steht der Grund statt eines Platzhalters."""
    toolbox._print_significance(_PERMUTATION_TEST)
    out = capsys.readouterr().out
    pf_line = next(line for line in out.splitlines() if line.startswith("| profit_factor"))
    assert "nicht endlich" in pf_line


def test_permutation_output_reports_no_trade_share_and_self_check(toolbox, capsys):
    """No-Trade-Anteil und Selbstprüfung erscheinen samt ungeprüfter Kennzahl."""
    toolbox._print_significance(_PERMUTATION_TEST)
    out = capsys.readouterr().out
    assert "Läufe ohne Trades: 12" in out
    assert "4.0 %" in out
    assert "mitgezählt, nicht verworfen" in out
    assert "Selbstprüfung: 1 Kennzahl(en)" in out
    assert "ungeprüft: profit_factor" in out


def test_permutation_output_contains_no_verdict_wording(toolbox, capsys):
    """Kein Bestanden/Signifikant-Urteil in der Ausgabe — Report, kein Filter."""
    toolbox._print_significance(_PERMUTATION_TEST)
    out = capsys.readouterr().out.lower()
    for forbidden in ("bestanden", "passed", "verdict", "ampel"):
        assert forbidden not in out
    assert "report, kein filter" in out


def test_bootstrap_output_shows_bands_and_no_p_value(toolbox, capsys):
    """Der Bootstrap zeigt Konfidenzbänder und benennt den Anteil als Anteil."""
    toolbox._print_significance(_BOOTSTRAP_TEST)
    out = capsys.readouterr().out
    assert "Bootstrap-Runden" in out
    assert "Trades: 767" in out
    assert "| mean_return_pct |" in out
    assert "Profitfaktor <= 1" in out
    assert "2.1 %" in out
    assert "KEIN p-Wert" in out
    assert "p-Wert |" not in out, "Bootstrap hat keine p-Wert-Spalte"


def test_failed_test_output_shows_the_error(toolbox, capsys):
    """Ein gescheiterter Test zeigt seine Fehlermeldung."""
    failed = {
        **_PERMUTATION_TEST, "status": "failed", "summary_json": None,
        "error_message": "Selbstprüfung fehlgeschlagen: sharpe_ratio abweichend",
    }
    toolbox._print_significance(failed)
    out = capsys.readouterr().out
    assert "**failed**" in out
    assert "Selbstprüfung fehlgeschlagen" in out


# ---------------------------------------------------------------------------
# signifikanz-start
# ---------------------------------------------------------------------------

def test_start_sends_method_seed_and_n(toolbox, capsys):
    """Die Flags landen unverändert im POST-Body."""
    calls = []

    def _post(path, body=None, timeout=None):
        calls.append((path, body, timeout))
        return {"data": {"test_id": 12, "test": {**_PERMUTATION_TEST, "status": "queued"}}}

    with patch.object(toolbox, "post", _post):
        rc = toolbox.significance_start(
            ["--result", "2706026", "--method", "permutation", "--n", "50", "--seed", "7"]
        )
    assert rc == 0
    path, body, _timeout = calls[0]
    assert path == "/api/backtest/results/2706026/significance"
    assert body == {"method": "permutation", "seed": 7, "n": 50}
    assert "Test-ID 12" in capsys.readouterr().out


def test_start_defaults_to_permutation(toolbox):
    """Ohne --method wird der Permutationstest gestartet."""
    calls = []

    def _post(path, body=None, timeout=None):
        calls.append(body)
        return {"data": {"test_id": 1, "test": {**_PERMUTATION_TEST, "status": "queued"}}}

    with patch.object(toolbox, "post", _post):
        toolbox.significance_start(["--result", "5"])
    assert calls[0]["method"] == "permutation"
    assert "n" not in calls[0], "ohne --n entscheidet der Server über den Default"


def test_start_forwards_metric_selection_as_list(toolbox):
    """--metrics wird zur Liste zerlegt."""
    calls = []

    def _post(path, body=None, timeout=None):
        calls.append(body)
        return {"data": {"test_id": 1, "test": {**_PERMUTATION_TEST, "status": "queued"}}}

    with patch.object(toolbox, "post", _post):
        toolbox.significance_start(
            ["--result", "5", "--metrics", "sharpe_ratio, profit_factor"]
        )
    assert calls[0]["metrics"] == ["sharpe_ratio", "profit_factor"]


def test_start_rejects_unknown_method(toolbox):
    """Eine unbekannte Methode bricht ab, bevor ein Request rausgeht."""
    with pytest.raises(ValueError, match="permutation oder bootstrap"):
        toolbox.significance_start(["--result", "5", "--method", "monte-carlo"])


def test_start_requires_result_flag(toolbox):
    """Ohne --result bricht das Verb mit Hinweis ab."""
    with pytest.raises(ValueError, match="--result"):
        toolbox.significance_start(["--method", "bootstrap"])


def test_start_bootstrap_prints_the_finished_record(toolbox, capsys):
    """Der synchron gerechnete Bootstrap wird direkt ausgegeben, ohne --wait."""
    def _post(path, body=None, timeout=None):
        return {"data": {"test_id": 13, "test": _BOOTSTRAP_TEST}}

    with patch.object(toolbox, "post", _post):
        rc = toolbox.significance_start(["--result", "5", "--method", "bootstrap"])
    assert rc == 0
    assert "| profit_factor |" in capsys.readouterr().out


def test_wait_polls_until_completed(toolbox, capsys):
    """--wait pollt bis completed und gibt dann den vollen Bericht aus (Exit 0)."""
    states = [
        {"data": {**_PERMUTATION_TEST, "status": "running", "summary_json": None}},
        {"data": _PERMUTATION_TEST},
    ]

    def _post(path, body=None, timeout=None):
        return {"data": {"test_id": 12, "test": {**_PERMUTATION_TEST, "status": "queued"}}}

    with patch.object(toolbox, "post", _post), \
         patch.object(toolbox, "fetch", lambda path: states.pop(0)), \
         patch("time.sleep", lambda _s: None):
        rc = toolbox.significance_start(["--result", "5", "--wait"])
    assert rc == 0
    assert "| sharpe_ratio |" in capsys.readouterr().out


def test_wait_reports_timeout_with_exit_code_two(toolbox, capsys):
    """Der Timeout meldet sich als Timeout (Exit 2), nicht als Fehlschlag."""
    def _post(path, body=None, timeout=None):
        return {"data": {"test_id": 12, "test": {**_PERMUTATION_TEST, "status": "queued"}}}

    with patch.object(toolbox, "post", _post), \
         patch.object(toolbox, "fetch",
                      lambda path: {"data": {**_PERMUTATION_TEST, "status": "running"}}), \
         patch("time.sleep", lambda _s: None):
        rc = toolbox.significance_start(["--result", "5", "--wait", "--timeout", "0"])
    assert rc == 2
    assert "TIMEOUT" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# signifikanz / signifikanz-list
# ---------------------------------------------------------------------------

def test_read_verb_fetches_by_id(toolbox, capsys):
    """`signifikanz --id` liest genau diesen Test."""
    with patch.object(toolbox, "fetch", lambda path: {"data": _PERMUTATION_TEST}):
        rc = toolbox.significance_read(["--id", "12"])
    assert rc == 0
    assert "Signifikanztest 12" in capsys.readouterr().out


def test_read_verb_requires_id(toolbox):
    """Ohne --id bricht das Verb ab."""
    with pytest.raises(ValueError, match="--id"):
        toolbox.significance_read([])


def test_read_verb_supports_json_output(toolbox, capsys):
    """--json gibt die rohen Daten aus (für Folge-Analysen)."""
    import json

    with patch.object(toolbox, "fetch", lambda path: {"data": _PERMUTATION_TEST}):
        toolbox.significance_read(["--id", "12", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == 12


def test_list_verb_keeps_server_order(toolbox, capsys):
    """Die Historie wird in Server-Reihenfolge ausgegeben (chronologisch, kein Sortieren)."""
    items = [
        {**_PERMUTATION_TEST, "id": 1},
        {**_BOOTSTRAP_TEST, "id": 2},
        {**_PERMUTATION_TEST, "id": 3},
    ]
    with patch.object(toolbox, "fetch",
                      lambda path: {"data": {"items": items, "total": len(items)}}):
        rc = toolbox.significance_list(["--result", "2706026"])
    assert rc == 0
    out = capsys.readouterr().out
    positions = [out.index(f"Signifikanztest {i} ") for i in (1, 2, 3)]
    assert positions == sorted(positions), "Reihenfolge unverändert übernommen"
    assert "chronologisch" in out


def test_list_verb_handles_empty_history(toolbox, capsys):
    """Ohne Tests meldet die Liste das ausdrücklich."""
    with patch.object(toolbox, "fetch", lambda path: {"data": {"items": [], "total": 0}}):
        rc = toolbox.significance_list(["--result", "9"])
    assert rc == 0
    assert "keine Tests vorhanden" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Verdrahtung
# ---------------------------------------------------------------------------

def test_verbs_are_registered_and_documented(toolbox):
    """Die drei Verben sind aufrufbar und im --help-Docstring beschrieben."""
    for verb, handler in (
        ("signifikanz-start", toolbox.significance_start),
        ("signifikanz", toolbox.significance_read),
        ("signifikanz-list", toolbox.significance_list),
    ):
        assert toolbox.SINGLE_VERBS[verb] is handler
        assert verb in toolbox.__doc__


def test_help_text_states_the_p_value_rule(toolbox):
    """Der Docstring nennt die Regel, dass ein p-Wert nie ohne Verteilung erscheint."""
    assert "NIE ohne" in toolbox.__doc__
    assert "KEIN p-Wert" in toolbox.__doc__
