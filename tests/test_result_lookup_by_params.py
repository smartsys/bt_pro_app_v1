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
    get_run_param_steps,
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


# ============================================================================
# Schrittweiter Nachbarschafts-Modus (tolerance_steps) — ungleiche Raster
# ============================================================================

# Zentrum des Test-Rasters (ungleiche Schrittweiten je Achse, vwma eingefroren).
CENTER = {'ema_fast': 15.0, 'ema_slow': 75.0, 'adx_th': 22.5, 'vwma': 14.0}


@pytest.fixture(scope='function')
def step_setup(session) -> Tuple[BacktestRun, Dict[str, BacktestResult]]:
    """Run mit ungleichen Schrittweiten je Achse plus eingefrorener Achse.

    ema_fast Schritt 5, ema_slow Schritt 25, adx_th Schritt 2.5, vwma eingefroren
    (14). Zentrum + je ein ±1-Schritt-Nachbar pro Achse + ein Weit-weg-Punkt.
    """
    run = _make_run(session)
    grid = {
        'center':  ({'ema_fast': 15.0, 'ema_slow': 75.0,  'adx_th': 22.5, 'vwma': 14.0}, 100.0),
        'fast_lo': ({'ema_fast': 10.0, 'ema_slow': 75.0,  'adx_th': 22.5, 'vwma': 14.0}, 90.0),
        'fast_hi': ({'ema_fast': 20.0, 'ema_slow': 75.0,  'adx_th': 22.5, 'vwma': 14.0}, 91.0),
        'slow_lo': ({'ema_fast': 15.0, 'ema_slow': 50.0,  'adx_th': 22.5, 'vwma': 14.0}, 80.0),
        'slow_hi': ({'ema_fast': 15.0, 'ema_slow': 100.0, 'adx_th': 22.5, 'vwma': 14.0}, 81.0),
        'adx_lo':  ({'ema_fast': 15.0, 'ema_slow': 75.0,  'adx_th': 20.0, 'vwma': 14.0}, 70.0),
        'adx_hi':  ({'ema_fast': 15.0, 'ema_slow': 75.0,  'adx_th': 25.0, 'vwma': 14.0}, 71.0),
        'far':     ({'ema_fast': 20.0, 'ema_slow': 125.0, 'adx_th': 25.0, 'vwma': 14.0}, 60.0),
    }
    results = {k: _add_result(session, run, p, ret) for k, (p, ret) in grid.items()}
    return run, results


def test_get_run_param_steps_derives_smallest_gap(db_engine, step_setup):
    """Schrittweite je Achse = kleinster positiver Abstand der distinct-Werte; eingefroren -> 0."""
    run, _ = step_setup
    steps = get_run_param_steps(db_engine, run.id, ['ema_fast', 'ema_slow', 'adx_th', 'vwma'])
    assert steps['ema_fast'] == 5.0
    assert steps['ema_slow'] == 25.0
    assert steps['adx_th'] == 2.5
    assert steps['vwma'] == 0.0


def test_step_mode_spans_true_one_step_neighborhood(db_engine, step_setup):
    """tolerance_steps=1 trifft je Achse genau ±1 Schritt trotz ungleicher Schrittweiten."""
    run, results = step_setup
    items, total = lookup_result_rows_by_params(
        db_engine, run.id, dict(CENTER), tolerance=0.0, limit=100, tolerance_steps=1)
    ids = {i['id'] for i in items}
    expected = {results[k].id for k in
                ('center', 'fast_lo', 'fast_hi', 'slow_lo', 'slow_hi', 'adx_lo', 'adx_hi')}
    assert total == 7
    assert ids == expected
    assert results['far'].id not in ids


def test_scalar_tolerance_one_misses_unequal_steps(db_engine, step_setup):
    """Belegt die Lücke: skalare tolerance=1 findet bei ungleichen Rastern nur das Zentrum."""
    run, results = step_setup
    items, total = lookup_result_rows_by_params(
        db_engine, run.id, dict(CENTER), tolerance=1.0, limit=100)
    assert total == 1
    assert items[0]['id'] == results['center'].id


def test_frozen_axis_matches_exactly_in_step_mode(db_engine, step_setup):
    """Eingefrorene Achse (vwma, Schritt 0) matcht exakt — ein abweichender vwma fällt raus."""
    run, _ = step_setup
    off = dict(CENTER)
    off['vwma'] = 15.0
    items, total = lookup_result_rows_by_params(
        db_engine, run.id, off, tolerance=0.0, limit=100, tolerance_steps=1)
    assert total == 0
    assert items == []


def test_step_mode_n_scales_window(db_engine, step_setup):
    """tolerance_steps skaliert das Fenster: N=2 zieht den Weit-weg-Punkt (ema_slow 125) herein."""
    run, results = step_setup
    _, total1 = lookup_result_rows_by_params(
        db_engine, run.id, {'ema_slow': 75.0}, tolerance=0.0, limit=100, tolerance_steps=1)
    items2, total2 = lookup_result_rows_by_params(
        db_engine, run.id, {'ema_slow': 75.0}, tolerance=0.0, limit=100, tolerance_steps=2)
    assert total1 == 7  # ±1 Schritt (25) um 75 -> [50,100]
    assert total2 == 8  # ±2 Schritte (50) um 75 -> [25,125] inkl. far
    assert results['far'].id in {i['id'] for i in items2}


def test_step_mode_absorbs_arange_float_steps(db_engine, session):
    """Schrittweite wird aus arange-Float-Werten mit Artefakten sauber als 0.1 abgeleitet."""
    run = _make_run(session)
    vals = [1.0, 1.1, 1.2000000000000002, 1.3000000000000003]
    made = [_add_result(session, run, {'th': v}, 10.0 * i) for i, v in enumerate(vals)]
    steps = get_run_param_steps(db_engine, run.id, ['th'])
    assert abs(steps['th'] - 0.1) < 1e-6
    items, total = lookup_result_rows_by_params(
        db_engine, run.id, {'th': 1.1}, tolerance=0.0, limit=100, tolerance_steps=1)
    assert total == 3  # ±1 Schritt (0.1) um 1.1 -> {1.0, 1.1, 1.2}
    assert {i['id'] for i in items} == {made[0].id, made[1].id, made[2].id}


def test_across_runs_step_mode_uses_per_run_steps(db_engine, session):
    """Schritt-Modus über mehrere Runs leitet die Schrittweite je Run einzeln ab (Raster differieren)."""
    # Run A: ema_slow-Raster Schritt 25 -> ±1 Schritt um 75 = [50,100], 100 IST Nachbar
    run_a = _make_run(session)
    _add_result(session, run_a, {'ema_slow': 75.0}, 80.0)
    a_100 = _add_result(session, run_a, {'ema_slow': 100.0}, 40.0)
    _add_result(session, run_a, {'ema_slow': 50.0}, 30.0)
    # Run B: feineres Raster Schritt 10 -> ±1 Schritt um 75 = [65,85], 100 ist NICHT Nachbar
    run_b = _make_run(session)
    _add_result(session, run_b, {'ema_slow': 75.0}, 70.0)
    _add_result(session, run_b, {'ema_slow': 85.0}, 35.0)
    _add_result(session, run_b, {'ema_slow': 65.0}, 20.0)
    b_100 = _add_result(session, run_b, {'ema_slow': 100.0}, 10.0)

    items, total = lookup_results_across_runs(
        db_engine, [run_a.id, run_b.id], {'ema_slow': 75.0},
        tolerance=0.0, limit=100, tolerance_steps=1)
    ids = {i['id'] for i in items}
    assert total == 6                 # Run A: 50,75,100 (3) + Run B: 65,75,85 (3)
    assert a_100.id in ids            # 100 ist bei Schritt 25 ein ±1-Nachbar
    assert b_100.id not in ids        # 100 ist bei Schritt 10 KEIN ±1-Nachbar
