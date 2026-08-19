"""Tests für das Toolbox-Verb `result-delete-all`.

Prüft `result_delete_all` aus
`.claude/skills/ds-strategie-session/scripts/toolbox.py` — ohne Netzwerk-Zugriff
(`request` wird gemockt), da die Toolbox ein stdlib-only CLI-Skript ist. Die
Server-Logik der eingegrenzten Löschung selbst steht in
tests/test_delete_all_results_scoped.py.
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


def test_result_delete_all_without_flag_calls_unscoped_route(toolbox, capsys):
    """Ohne Flag bleibt das globale Verhalten unverändert — kein Query-String."""
    with patch.object(toolbox, "request", return_value={"status": "queued", "job_id": "abc"}) as mock_request:
        rc = toolbox.result_delete_all([])

    assert rc == 0
    mock_request.assert_called_once_with("DELETE", "/api/backtest/results")
    assert "result-delete-all" in capsys.readouterr().out


def test_result_delete_all_with_run_flag_scopes_the_query(toolbox):
    with patch.object(toolbox, "request", return_value={"status": "ok"}) as mock_request:
        toolbox.result_delete_all(["--run", "608"])

    mock_request.assert_called_once_with("DELETE", "/api/backtest/results?run_id=608")


def test_result_delete_all_with_testset_run_flag_scopes_the_query(toolbox):
    with patch.object(toolbox, "request", return_value={"status": "ok"}) as mock_request:
        toolbox.result_delete_all(["--testset-run", "6"])

    mock_request.assert_called_once_with("DELETE", "/api/backtest/results?testset_run_id=6")


def test_result_delete_all_run_and_testset_run_together_raises(toolbox):
    with pytest.raises(ValueError, match="--run und --testset-run schließen sich aus"):
        toolbox.result_delete_all(["--run", "608", "--testset-run", "6"])


def test_result_delete_all_prints_deleted_run_ids(toolbox, capsys):
    """Die Antwort benennt deleted_run_ids."""
    response = {"status": "ok", "deleted_results": 3, "deleted_runs": 1, "deleted_run_ids": [608]}
    with patch.object(toolbox, "request", return_value=response):
        toolbox.result_delete_all(["--testset-run", "6"])

    out = capsys.readouterr().out
    assert "deleted_run_ids" in out
    assert "608" in out
