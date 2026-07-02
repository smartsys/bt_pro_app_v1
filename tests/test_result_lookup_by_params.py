"""Tests für den Result-Lookup per Parameter-Werten.

Testet die Query-Logik der Route GET /api/backtest/runs/{run_id}/results/lookup
direkt über lookup_result_rows_by_params und get_run_param_names
(user_data/utils/database/repository.py) gegen die PostgreSQL-Test-DB (Port 5562).
db_engine und session kommen aus tests/conftest.py.
"""

import hashlib
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from user_data.utils.database.repository import (
    get_run_param_names,
    get_scope_param_names,
    lookup_result_rows_by_params,
    lookup_results_across_runs,
)
from user_data.utils.database.models import BacktestParam, BacktestResult, BacktestRun


# ============================================================================
# Hilfsfunktionen und Fixtures
# ============================================================================

def _make_run(session) -> BacktestRun:
    """Minimaler BacktestRun."""
    run = BacktestRun(
        strategy_family='teststrategie',
        strategy_name='v1',
        symbol='BTCUSDT',
        exchange='binance',
        timeframe='4h',
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
        backtest_config_json={},
        indicators_config_json={},
        n_combinations=0,
        status='completed',
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _add_result(session, run: BacktestRun, params: Dict[str, float],
                total_return_pct: float) -> BacktestResult:
    """Result mit Parameter-Zeilen in backtest_result_params anlegen."""
    result = BacktestResult(
        run_id=run.id,
        params_hash=hashlib.md5(f'{run.id}:{sorted(params.items())}'.encode()).hexdigest(),
        actual_params_json=params,
        total_return_pct=total_return_pct,
    )
    session.add(result)
    session.commit()
    session.refresh(result)
    for name, value in params.items():
        session.add(BacktestParam(result_id=result.id, param_name=name, param_value=value))
    session.commit()
    return result


@pytest.fixture(scope='function')
def lookup_setup(session) -> Tuple[BacktestRun, List[BacktestResult]]:
    """Run mit drei Kombinationen plus Schwester-Run mit identischer Kombination."""
    run = _make_run(session)
    results = [
        _add_result(session, run, {'length': 10.0, 'mult': 2.0}, 50.0),
        _add_result(session, run, {'length': 12.0, 'mult': 2.0}, 80.0),
        _add_result(session, run, {'length': 20.0, 'mult': 3.0}, 30.0),
    ]
    # Schwester-Run mit gleichen Parameterwerten — darf nie mitgefunden werden
    other = _make_run(session)
    _add_result(session, other, {'length': 12.0, 'mult': 2.0}, 999.0)
    return run, results


# ============================================================================
# Tests
# ============================================================================

def test_exact_lookup_finds_single_combination(db_engine, lookup_setup):
    """Exakter Lookup (tolerance=0) liefert genau das eine Result der Kombination."""
    run, results = lookup_setup
    items, total = lookup_result_rows_by_params(
        db_engine, run.id, {'length': 12.0, 'mult': 2.0}, tolerance=0.0, limit=100)
    assert total == 1
    assert items[0]['id'] == results[1].id
    assert items[0]['total_return_pct'] == 80.0


def test_exact_lookup_absorbs_float_artifacts(db_engine, session):
    """Gespeicherte arange-Float-Artefakte (2.5000000000000004) matchen die Eingabe 2.5."""
    run = _make_run(session)
    stored = _add_result(session, run, {'mult': 2.5000000000000004}, 10.0)
    items, total = lookup_result_rows_by_params(
        db_engine, run.id, {'mult': 2.5}, tolerance=0.0, limit=100)
    assert total == 1
    assert items[0]['id'] == stored.id


def test_subset_match_orders_by_total_return(db_engine, lookup_setup):
    """Subset-Filter (nur mult) trifft mehrere Results, sortiert nach Total Return desc."""
    run, results = lookup_setup
    items, total = lookup_result_rows_by_params(
        db_engine, run.id, {'mult': 2.0}, tolerance=0.0, limit=100)
    assert total == 2
    assert [i['id'] for i in items] == [results[1].id, results[0].id]


def test_tolerance_mode_finds_neighborhood(db_engine, lookup_setup):
    """Nachbarschafts-Modus: length=11 ±1 trifft die Kombinationen 10 und 12."""
    run, results = lookup_setup
    items, total = lookup_result_rows_by_params(
        db_engine, run.id, {'length': 11.0}, tolerance=1.0, limit=100)
    assert total == 2
    assert {i['id'] for i in items} == {results[0].id, results[1].id}


def test_lookup_is_run_isolated(db_engine, lookup_setup):
    """Die identische Kombination im Schwester-Run wird nicht mitgefunden."""
    run, results = lookup_setup
    items, _ = lookup_result_rows_by_params(
        db_engine, run.id, {'length': 12.0, 'mult': 2.0}, tolerance=0.0, limit=100)
    assert all(i['run_id'] == run.id for i in items)


def test_lookup_no_match_returns_empty(db_engine, lookup_setup):
    """Nicht existierende Kombination liefert leere Treffermenge."""
    run, _ = lookup_setup
    items, total = lookup_result_rows_by_params(
        db_engine, run.id, {'length': 99.0}, tolerance=0.0, limit=100)
    assert total == 0
    assert items == []


def test_limit_caps_items_but_counts_total(db_engine, lookup_setup):
    """Bei vollem Limit werden Items gedeckelt, total zählt alle Treffer."""
    run, _ = lookup_setup
    items, total = lookup_result_rows_by_params(
        db_engine, run.id, {'mult': 2.0}, tolerance=0.0, limit=1)
    assert len(items) == 1
    assert total == 2


def test_run_param_names_lists_sorted_names(db_engine, lookup_setup):
    """_run_param_names liefert die Parameter-Namen des Runs sortiert."""
    run, _ = lookup_setup
    assert get_run_param_names(db_engine, run.id) == ['length', 'mult']


# ============================================================================
# Kombinations-Verfolgung über mehrere Runs (combo-trace)
# ============================================================================

def test_across_runs_finds_combination_per_run(db_engine, session):
    """Dieselbe Kombination wird in jedem Run des Scopes gefunden, sortiert nach run_id."""
    run_a = _make_run(session)
    run_b = _make_run(session)
    res_a = _add_result(session, run_a, {'length': 12.0, 'mult': 2.0}, 80.0)
    res_b = _add_result(session, run_b, {'length': 12.0, 'mult': 2.0}, 40.0)
    _add_result(session, run_b, {'length': 20.0, 'mult': 3.0}, 70.0)

    items, total = lookup_results_across_runs(
        db_engine, [run_a.id, run_b.id], {'length': 12.0, 'mult': 2.0},
        tolerance=0.0, limit=100)
    assert total == 2
    assert [i['id'] for i in items] == [res_a.id, res_b.id]
    assert all(i['symbol'] == 'BTCUSDT' and i['timeframe'] == '4h' for i in items)


def test_across_runs_excludes_runs_outside_scope(db_engine, session):
    """Runs außerhalb der run_ids-Liste bleiben unberücksichtigt."""
    run_a = _make_run(session)
    outside = _make_run(session)
    _add_result(session, run_a, {'length': 12.0, 'mult': 2.0}, 80.0)
    _add_result(session, outside, {'length': 12.0, 'mult': 2.0}, 999.0)

    items, total = lookup_results_across_runs(
        db_engine, [run_a.id], {'length': 12.0}, tolerance=0.0, limit=100)
    assert total == 1
    assert items[0]['run_id'] == run_a.id


def test_scope_param_names_union_over_runs(db_engine, session):
    """get_scope_param_names vereinigt die Parameter-Namen der Run-Menge sortiert."""
    run_a = _make_run(session)
    run_b = _make_run(session)
    _add_result(session, run_a, {'length': 12.0, 'mult': 2.0}, 80.0)
    _add_result(session, run_b, {'atr_window': 14.0}, 10.0)
    assert get_scope_param_names(db_engine, [run_a.id, run_b.id]) == ['atr_window', 'length', 'mult']
