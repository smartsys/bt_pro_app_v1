"""Tests für Worker-Pfad: Rules aus iteration.spec_json (Ticket 12, bereinigt Ticket 21).

Prüft:
- run_backtest_job lädt rules_json aus run.iteration.spec_json.
- run_backtest_job leitet rules_json explizit an die Strategie-Funktion weiter.
- Fehlende iteration -> ValueError (kein Legacy-Fallback mehr seit Ticket 21).
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock


_SAMPLE_SPEC_JSON = {
    'indicators': {'fast_sma': {'length': 6}},
    'rules': {'entry': {'logic': 'AND', 'conditions': []}, 'exit': None},
}


def _make_run(iteration_id=1, indicators_config=None, has_iteration=True, testset_run_id=None):
    """Erstellt einen Mock-BacktestRun."""
    run = MagicMock()
    run.id = 42
    # GEÄNDERT: Ticket 15 — _json-Suffix
    run.backtest_config_json = {
        'strategy_family': 'playground',
        'strategy_name': 'pg_spec_20260525',
        'import_path': 'user_data.strategies.generic.spec_runner.run_spec_strategy',
        'exchange': 'binance',
        'symbols': ['BTCUSDT'],
        'timeframe': '4h',
        'start': '2022-01-01',
        'end': '2022-06-01',
        'ohlc_start': '2022-01-01',
        'ohlc_end': '2022-06-01',
        'portfolio': {'size': 100, 'init_cash': 100, 'fees': 0.001},
    }
    run.indicators_config_json = indicators_config or {'fast_sma': {'length': 6}}
    run.iteration_id = iteration_id
    run.testset_run_id = testset_run_id

    if has_iteration and iteration_id is not None:
        run.iteration = MagicMock()
        run.iteration.spec_json = _SAMPLE_SPEC_JSON
    else:
        run.iteration = None

    return run


def _make_fake_session(run):
    """Erstellt eine Mock-Session die den gegebenen Run zurückgibt."""
    mock_query = MagicMock()
    mock_query.filter.return_value.first.return_value = run
    session = MagicMock()
    session.query.return_value = mock_query
    return session


def _patch_worker_internals(run, strategy_fn=None):
    """Kontextmanager-Hilfsfunktion: patcht alle lokalen Imports in run_backtest_job."""
    from contextlib import ExitStack

    def fake_load_strategy(path):
        return strategy_fn if strategy_fn else MagicMock()

    # Alle lokal importierten Symbole auf die Quell-Module patchen
    stack = ExitStack()
    stack.enter_context(patch('services.api.worker_tasks.get_session', return_value=_make_fake_session(run)))
    stack.enter_context(patch('services.api.recompute.load_strategy_function', side_effect=fake_load_strategy))
    stack.enter_context(patch('user_data.utils.ohlc.loader.load_ohlc_data', return_value=MagicMock()))
    stack.enter_context(patch('user_data.utils.database.repository.save_strategy_results', return_value=1))
    stack.enter_context(patch('user_data.utils.database.repository.update_backtest_run_status', MagicMock()))
    return stack


def test_worker_laedt_rules_aus_iteration():
    """Worker übergibt rules_json aus iteration.spec_json an die Strategie."""
    run = _make_run()
    received_kwargs = {}

    def fake_strategy_fn(ohlc, indicators_json=None, backtest_config_json=None, rules_json=None):
        received_kwargs['rules_json'] = rules_json
        pf = MagicMock()
        pf.total_return = 0.1
        return {
            'portfolios': pf,
            'indicators_results': {},
            'signals': {'entries': MagicMock(), 'exits': MagicMock()},
            'analysis_results_dict': None,
        }

    import services.api.worker_tasks as wt
    with _patch_worker_internals(run, strategy_fn=fake_strategy_fn):
        result = wt.run_backtest_job(42)

    assert result is True
    assert received_kwargs.get('rules_json') == _SAMPLE_SPEC_JSON['rules']


def test_worker_indicators_json_enthaelt_keinen_rules_key():
    """indicators_json an Strategie enthält keinen '_rules'-Key.

    Auch wenn indicators_config keine _rules enthält, darf das Ergebnis keinen
    solchen Key haben (Ticket 21: kein Legacy-Key mehr in der DB).
    """
    # GEÄNDERT: Ticket 21 — kein _rules in indicators_config, Rules kommen aus iteration.spec_json
    run = _make_run(indicators_config={'fast_sma': {'length': 6}})
    received_indicators = {}

    def fake_strategy_fn(ohlc, indicators_json=None, backtest_config_json=None, rules_json=None):
        received_indicators.update(indicators_json or {})
        return {
            'portfolios': MagicMock(),
            'indicators_results': {},
            'signals': {'entries': MagicMock(), 'exits': MagicMock()},
            'analysis_results_dict': None,
        }

    import services.api.worker_tasks as wt
    with _patch_worker_internals(run, strategy_fn=fake_strategy_fn):
        wt.run_backtest_job(42)

    assert '_rules' not in received_indicators


def test_worker_ohne_iteration_wirft_exception():
    """Fehlende Iteration -> ValueError (kein Legacy-Fallback mehr seit Ticket 21)."""
    # GEÄNDERT: Ticket 21 — kein stilles False, sondern Exception
    run = _make_run(iteration_id=None, has_iteration=False)

    import services.api.worker_tasks as wt
    with patch('services.api.worker_tasks.get_session', return_value=_make_fake_session(run)):
        with pytest.raises(ValueError, match="iteration_id fehlt"):
            wt.run_backtest_job(42)
