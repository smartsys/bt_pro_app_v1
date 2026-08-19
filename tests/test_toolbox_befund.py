"""Tests für das Toolbox-Verb `befund` (Ticket 56, Teilaufgabe 3).

Prüft `befund_read`/`_print_befund` aus
`.claude/skills/ds-strategie-session/scripts/toolbox.py` — ohne Netzwerk-Zugriff
(`fetch` wird gemockt), da die Toolbox ein stdlib-only CLI-Skript ist. Die
Server-Logik der Routen selbst steht in tests/test_testset_run_findings_api.py.
"""

import importlib.util
import json
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


# Ein offener Befund (Phase 1 abgeschlossen, Phase 2 noch nicht) — Form entspricht
# TestSetRunFindingOut aus services/api/routes/api_testset_run_findings.py.
_OPEN_FINDING = {
    "id": 42, "testset_run_id": 501, "iteration_id": 7, "concept_id": 3, "testset_id": 11,
    "indicator_config_id": 22, "spec_runner_version": "4.0.0", "created_at": "2026-08-14T10:00:00",
    "goal_snapshot_json": {"sharpe_min": 1.2}, "goal_missing_reason": None,
    "best_criteria_json": ["max_return", "winrate_band", "sharpe_band", "pf_min30"],
    "planned_n_runs": 2, "planned_combos_per_run": 9, "planned_combos_total": 18,
    "planned_grid_reason": None,
    "scope_json": None, "candidates_json": None, "robustness_json": None,
    "benchmarks_json": None, "warnings_json": None, "holdout_touched": None,
    "closed_at": None,
    "interpretation": {"text": None, "interpreted_at": None},
}

# Ein geschlossener Befund mit allen fünf Ist-Gruppen inkl. leeren Feldern mit Grund.
_CLOSED_FINDING = {
    **_OPEN_FINDING,
    "id": 43, "closed_at": "2026-08-14T11:00:00",
    "goal_snapshot_json": None, "goal_missing_reason": "kein Ziel am Konzept hinterlegt",
    "planned_combos_per_run": None, "planned_combos_total": None,
    "planned_grid_reason": "Rastergröße nicht ermittelbar: Beispiel",
    "scope_json": {
        "n_runs": 1, "n_runs_completed": 1, "symbols": ["BTCUSDT"], "combos_total": 9,
        "n_eff": None, "n_eff_reason": "N_eff ist am Testset nicht ausgewiesen",
        "runs": [{
            "run_id": 900, "symbol": "BTCUSDT", "timeframe": "4h",
            "n_combinations": 9, "n_results": 9, "metrics_selection": None,
            "metric_groups_skipped": [],
        }],
    },
    "candidates_json": {
        "per_run": [{
            "run_id": 900, "symbol": "BTCUSDT",
            "criteria": {
                "max_return": {
                    "winner": {
                        "result_id": 1001,
                        "metrics": {
                            "total_return_pct": 200.0, "sharpe_ratio": 0.8, "profit_factor": 9.0,
                            "win_rate_pct": 45.0, "total_trades": 5, "max_drawdown_pct": -10.0,
                        },
                        "metrics_missing_reason": None,
                    },
                    "reason": None,
                },
                "winrate_band": {"winner": None, "reason": "kein Result erfüllt dieses Kriterium"},
            },
        }],
    },
    "robustness_json": {
        "dsr": [{
            "run_id": 900, "symbol": "BTCUSDT", "n": 9, "sr0": 1.13,
            "best": {"result_id": 1001, "deflated_sharpe_ratio": 0.62}, "best_reason": None,
        }],
        "plateau": [{
            "run_id": 900,
            "neighborhoods": [{
                "criterion": "max_return",
                "summary": {"n": 3, "return_median": 150.0, "anteil_profitabel_pct": 66.7},
                "reason": None,
            }],
        }],
        "symbol_dispersion": {
            "n_eff": None, "n_eff_reason": "N_eff ist am Testset nicht ausgewiesen",
            "spitzen_total_return_pct": {"spanne": 25.0},
        },
    },
    "benchmarks_json": {
        "buy_and_hold": [{
            "run_id": 900, "buy_and_hold_return_pct": 40.0, "buy_and_hold_reason": None,
            "best_total_return_pct": 200.0, "differenz_pct": 160.0,
        }],
        "concept_benchmark_line": None,
        "concept_benchmark_line_reason": "keine maschinenlesbare Benchmark-Linie vorhanden",
        "goal": {
            "soll": None, "soll_reason": "kein Ziel am Konzept hinterlegt",
            "hinweis": "Gegenüberstellung ohne Auswertung.",
        },
    },
    "warnings_json": {
        "items": [{"text": "Kandidat des Kriteriums max_return hat 5 Trades — unter dem Trade-Floor."}],
        "not_evaluated": [{"code": "holdout_touched", "reason": "kein markierter Holdout-Zeitraum"}],
    },
    "interpretation": {
        "text": "Signal wirkt robust, Trade-Zahl ist knapp.",
        "interpreted_at": "2026-08-14T12:00:00",
    },
}


def test_befund_read_requires_id_or_iteration(toolbox):
    """Ohne --id und ohne --iteration bricht das Verb mit klarer Meldung ab."""
    with pytest.raises(ValueError):
        toolbox.befund_read([])


def test_befund_read_by_id_calls_correct_route(toolbox, capsys):
    with patch.object(toolbox, "fetch", return_value={"data": _OPEN_FINDING}) as mock_fetch:
        rc = toolbox.befund_read(["--id", "42"])

    assert rc == 0
    mock_fetch.assert_called_once_with("/api/testset-run-findings/42")
    out = capsys.readouterr().out
    assert "Befund 42" in out


def test_befund_read_by_testset_run_calls_correct_route_and_reports_total(toolbox, capsys):
    """Ticket 77/A: --testset-run löst serverseitig zum jüngsten Befund auf und
    nennt die Gesamtzahl der Befunde dieses Testset-Laufs."""
    payload = {"finding": _OPEN_FINDING, "total_for_testset_run": 3}
    with patch.object(toolbox, "fetch", return_value={"data": payload}) as mock_fetch:
        rc = toolbox.befund_read(["--testset-run", "100"])

    assert rc == 0
    mock_fetch.assert_called_once_with("/api/testset-run-findings/by-testset-run/100")
    out = capsys.readouterr().out
    assert "Befund 42" in out
    assert "3" in out


def test_befund_read_id_and_testset_run_together_raises(toolbox):
    """--id und --testset-run schließen sich aus (Ticket 77/A)."""
    with pytest.raises(ValueError, match="--id und --testset-run schließen sich aus"):
        toolbox.befund_read(["--id", "42", "--testset-run", "100"])


def test_befund_read_by_iteration_calls_history_route(toolbox, capsys):
    with patch.object(
        toolbox, "fetch", return_value={"data": {"items": [_OPEN_FINDING], "total": 1}},
    ) as mock_fetch:
        rc = toolbox.befund_read(["--iteration", "7"])

    assert rc == 0
    mock_fetch.assert_called_once_with("/api/testset-run-findings/by-iteration/7")
    out = capsys.readouterr().out
    assert "Befund-Historie Iteration 7" in out
    assert "chronologisch" in out


def test_befund_read_json_flag_prints_raw_payload(toolbox, capsys):
    with patch.object(toolbox, "fetch", return_value={"data": _OPEN_FINDING}):
        rc = toolbox.befund_read(["--id", "42", "--json"])

    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["id"] == 42


def test_open_finding_shows_context_and_soll_without_ist(toolbox, capsys):
    toolbox._print_befund(_OPEN_FINDING)
    out = capsys.readouterr().out

    assert "### Soll" in out
    assert '"sharpe_min": 1.2' in out
    assert "noch offen" in out
    assert "noch nicht abgeschlossen" in out


def test_closed_finding_shows_all_five_ist_groups(toolbox, capsys):
    toolbox._print_befund(_CLOSED_FINDING)
    out = capsys.readouterr().out

    assert "### Ist — Umfang der Suche" in out
    assert "### Ist — Kandidaten" in out
    assert "### Ist — Robustheit" in out
    assert "### Ist — Vergleichsanker" in out
    assert "### Ist — Warnhinweise" in out


def test_dsr_never_printed_without_n_and_sr0(toolbox, capsys):
    """N und SR0 stehen in derselben Zeile wie die DSR — nie isoliert."""
    toolbox._print_befund(_CLOSED_FINDING)
    out = capsys.readouterr().out

    dsr_line = next(line for line in out.splitlines() if "DSR" in line and "run:900" in line)
    assert "N=9" in dsr_line
    assert "SR0=1.1300" in dsr_line


def test_empty_fields_show_reason_not_zero_or_omission(toolbox, capsys):
    """Leere Felder (goal, Rastergröße, N_eff, Benchmark-Linie) tragen ihren Grund."""
    toolbox._print_befund(_CLOSED_FINDING)
    out = capsys.readouterr().out

    assert "kein Ziel am Konzept hinterlegt" in out
    assert "Rastergröße nicht ermittelbar" in out
    assert "N_eff ist am Testset nicht ausgewiesen" in out
    assert "keine maschinenlesbare Benchmark-Linie vorhanden" in out


def test_interpretation_marked_and_separated_from_numbers(toolbox, capsys):
    toolbox._print_befund(_CLOSED_FINDING)
    out = capsys.readouterr().out

    assert "### Deutung (Interpretation" in out
    assert "Signal wirkt robust, Trade-Zahl ist knapp." in out
    # Die Deutung steht nach den Ist-Gruppen, nicht dazwischen.
    assert out.index("### Deutung") > out.index("### Ist — Warnhinweise")


def test_no_verdict_language_in_output(toolbox, capsys):
    """Kein Verdict — weder 'bestanden' noch 'passed' noch eine Ampel-Formulierung."""
    toolbox._print_befund(_CLOSED_FINDING)
    out = capsys.readouterr().out.lower()

    for forbidden in ("bestanden", "durchgefallen", "passed", "verdict", "ampel"):
        assert forbidden not in out
