"""Tests der Ketten-Aggregation (Anforderung 4).

Die Gesamtbewertung entsteht aus den balkengenauen Kapitalkurven der
Testfenster-Läufe, chronologisch verkettet und je Fold auf das Startkapital
normiert. Geprüft wird gegen eine **unabhängige Nachrechnung** auf kleinen
Kunstdaten:

* Die verkettete Gesamtrendite ist wertgleich mit dem Produkt der
  Fold-Verhältnisse (Endwert je Startwert) — ein Rechenweg, der die
  Renditereihe gar nicht erst bildet.
* Sharpe und maximaler Rückgang stimmen mit der von Hand gerechneten Formel
  überein; der Rückgang wird wie an ``backtest_results`` negativ ausgewiesen.
* Der Startwert eines Folds ist ohne Einfluss (Normierung).
* Profitfaktor und Trade-Zahl kommen aus den zusammengelegten Trade-Listen.
* Ein Fold ohne Sieger wird ausgewiesen statt verschluckt und geht nicht in die
  Kurve ein.
"""

import math
import statistics
from datetime import datetime, timedelta

import pytest

from services.api.utils.walk_forward_aggregation import (
    build_chain_aggregate,
    chain_metrics,
    fold_returns,
)
from user_data.utils.database.models import BacktestEquity, BacktestTrade

_ANN_FACTOR = 2190.0  # 4h-Balken: 365 * 6

_PLAN = {
    'selection_metric': 'sharpe_ratio',
    'selection_direction': 'max',
    'trade_floor': 5,
}


def _add_equity(session, result_id: int, values: list) -> None:
    """Schreibt eine Kapitalkurve mit stündlichem Abstand."""
    base = datetime(2021, 1, 1) + timedelta(days=result_id)
    for offset, value in enumerate(values):
        session.add(BacktestEquity(
            result_id=result_id,
            timestamp=base + timedelta(hours=4 * offset),
            value=value,
        ))
    session.commit()


def _add_trades(session, result_id: int, pnls: list, open_pnls: list = None) -> None:
    """Schreibt geschlossene (und optional offene) Trades eines Results."""
    for index, pnl in enumerate(pnls):
        session.add(BacktestTrade(
            result_id=result_id, exit_trade_id=index, direction='Long',
            status='Closed', size=1.0, entry_index=datetime(2021, 1, 1),
            avg_entry_price=100.0, pnl=pnl,
        ))
    for index, pnl in enumerate(open_pnls or []):
        session.add(BacktestTrade(
            result_id=result_id, exit_trade_id=100 + index, direction='Long',
            status='Open', size=1.0, entry_index=datetime(2021, 1, 1),
            avg_entry_price=100.0, pnl=pnl,
        ))
    session.commit()


def _fold(fold_index: int, result_id=None, is_value=None, oos_return=None, reason=None) -> dict:
    """Baut einen Fold-Block, wie ihn die Fold-Route ablegt."""
    if result_id is None:
        return {
            'fold_index': fold_index, 'winner': None, 'no_winner_reason': reason,
            'is_window': {'start': '2020-01-01', 'end': '2021-01-01'},
            'oos_window': None, 'oos_run_id': None, 'oos_result_id': None,
            'oos_metrics': None, 'ann_factor': None,
        }
    return {
        'fold_index': fold_index,
        'winner': {'result_id': result_id * 10, 'selection_value': is_value},
        'no_winner_reason': None,
        'is_window': {'start': '2020-01-01', 'end': '2021-01-01'},
        'oos_window': {'start': '2021-01-01', 'end': '2021-04-01'},
        'oos_run_id': result_id, 'oos_result_id': result_id,
        'oos_metrics': {
            'total_return_pct': oos_return, 'sharpe_ratio': is_value,
        },
        'ann_factor': _ANN_FACTOR,
    }


# ---------------------------------------------------------------------------
# Bausteine
# ---------------------------------------------------------------------------

def test_fold_returns_normalise_away_the_start_capital():
    small = fold_returns([100.0, 110.0, 99.0])
    large = fold_returns([1000.0, 1100.0, 990.0])
    assert small == pytest.approx(large)
    assert small == pytest.approx([0.1, -0.1])


def test_chain_metrics_match_a_hand_rolled_recomputation():
    returns = [0.02, -0.01, 0.03, -0.04, 0.015]
    metrics = chain_metrics(returns, _ANN_FACTOR)

    expected_total = math.prod(1 + r for r in returns) - 1
    expected_sharpe = (
        statistics.mean(returns) / statistics.stdev(returns) * math.sqrt(_ANN_FACTOR)
    )
    equity = []
    level = 1.0
    for r in returns:
        level *= (1 + r)
        equity.append(level)
    peak = 1.0
    expected_mdd = 0.0
    for value in equity:
        peak = max(peak, value)
        expected_mdd = min(expected_mdd, value / peak - 1)

    assert metrics['total_return_pct'] == pytest.approx(expected_total * 100)
    assert metrics['sharpe_ratio'] == pytest.approx(expected_sharpe)
    assert metrics['max_drawdown_pct'] == pytest.approx(expected_mdd * 100)
    assert metrics['max_drawdown_pct'] <= 0
    assert metrics['bar_count'] == len(returns)


def test_chain_metrics_without_ann_factor_report_no_sharpe():
    metrics = chain_metrics([0.01, -0.02, 0.03], None)
    assert metrics['sharpe_ratio'] is None
    assert metrics['total_return_pct'] is not None


def test_chain_metrics_on_empty_returns():
    metrics = chain_metrics([], _ANN_FACTOR)
    assert metrics == {
        'total_return_pct': None, 'sharpe_ratio': None,
        'max_drawdown_pct': None, 'bar_count': 0,
    }


# ---------------------------------------------------------------------------
# Gesamtaggregation
# ---------------------------------------------------------------------------

def test_chained_total_return_equals_product_of_fold_ratios(test_session):
    curves = {
        1: [100.0, 110.0, 99.0, 108.9],
        2: [500.0, 525.0, 498.75],
        3: [80.0, 76.0, 83.6],
    }
    for result_id, values in curves.items():
        _add_equity(test_session, result_id, values)

    folds = [
        _fold(1, result_id=1, is_value=2.0, oos_return=8.9),
        _fold(2, result_id=2, is_value=1.5, oos_return=-0.25),
        _fold(3, result_id=3, is_value=1.1, oos_return=4.5),
    ]
    aggregate = build_chain_aggregate(test_session, _PLAN, folds)

    # Unabhängiger Rechenweg: Endwert je Startwert, multipliziert.
    expected_total = math.prod(
        values[-1] / values[0] for values in curves.values()
    ) - 1
    assert aggregate['total_return_pct'] == pytest.approx(expected_total * 100)
    assert aggregate['bar_count'] == sum(len(v) - 1 for v in curves.values())
    assert aggregate['folds_total'] == 3
    assert aggregate['folds_with_winner'] == 3
    assert aggregate['folds_in_curve'] == 3
    assert aggregate['ann_factor'] == _ANN_FACTOR


def test_aggregate_sharpe_and_drawdown_match_the_chained_series(test_session):
    curves = {1: [100.0, 110.0, 99.0], 2: [200.0, 190.0, 209.0]}
    for result_id, values in curves.items():
        _add_equity(test_session, result_id, values)

    folds = [
        _fold(1, result_id=1, is_value=2.0, oos_return=-1.0),
        _fold(2, result_id=2, is_value=1.5, oos_return=4.5),
    ]
    aggregate = build_chain_aggregate(test_session, _PLAN, folds)

    chained = []
    for values in curves.values():
        for previous, current in zip(values, values[1:]):
            chained.append(current / previous - 1)
    expected = chain_metrics(chained, _ANN_FACTOR)

    assert aggregate['sharpe_ratio'] == pytest.approx(expected['sharpe_ratio'])
    assert aggregate['max_drawdown_pct'] == pytest.approx(expected['max_drawdown_pct'])


def test_profit_factor_and_trade_count_come_from_the_merged_trade_lists(test_session):
    _add_equity(test_session, 1, [100.0, 110.0])
    _add_equity(test_session, 2, [100.0, 95.0])
    _add_trades(test_session, 1, [10.0, -4.0, 6.0])
    _add_trades(test_session, 2, [-2.0, 3.0], open_pnls=[1.0])

    folds = [
        _fold(1, result_id=1, is_value=2.0, oos_return=10.0),
        _fold(2, result_id=2, is_value=1.5, oos_return=-5.0),
    ]
    aggregate = build_chain_aggregate(test_session, _PLAN, folds)

    assert aggregate['profit_factor'] == pytest.approx((10.0 + 6.0 + 3.0) / (4.0 + 2.0))
    assert aggregate['total_trades'] == 6
    assert aggregate['closed_trades'] == 5
    assert aggregate['open_trades'] == 1


def test_fold_without_winner_is_reported_and_left_out_of_the_curve(test_session):
    _add_equity(test_session, 1, [100.0, 110.0])
    _add_equity(test_session, 3, [100.0, 105.0])

    folds = [
        _fold(1, result_id=1, is_value=2.0, oos_return=10.0),
        _fold(2, reason='Kein Kandidat über dem Trade-Floor (30 Trades).'),
        _fold(3, result_id=3, is_value=1.2, oos_return=5.0),
    ]
    aggregate = build_chain_aggregate(test_session, _PLAN, folds)

    assert aggregate['folds_total'] == 3
    assert aggregate['folds_with_winner'] == 2
    assert aggregate['folds_without_winner'] == 1
    assert aggregate['folds_in_curve'] == 2
    assert aggregate['bar_count'] == 2
    assert any('Fold 2' in note for note in aggregate['notes'])

    entry = [d for d in aggregate['degradation'] if d['fold_index'] == 2][0]
    assert entry['has_winner'] is False
    assert entry['is_value'] is None
    assert 'Trade-Floor' in entry['no_winner_reason']


def test_degradation_shows_is_value_next_to_oos_value(test_session):
    _add_equity(test_session, 1, [100.0, 120.0])
    folds = [_fold(1, result_id=1, is_value=2.4, oos_return=20.0)]
    folds[0]['oos_metrics']['sharpe_ratio'] = 0.8

    aggregate = build_chain_aggregate(test_session, _PLAN, folds)
    entry = aggregate['degradation'][0]

    assert entry['is_value'] == pytest.approx(2.4)
    assert entry['oos_value'] == pytest.approx(0.8)
    assert aggregate['selection_metric'] == 'sharpe_ratio'
    # Kein Verdict: das Aggregat bewertet die Degradation nicht.
    assert 'passed' not in aggregate and 'verdict' not in aggregate


def test_equity_outside_the_test_window_is_cut_off(test_session):
    """Balken vor dem Testfenster und ab seinem Ende gehen nicht in die Kurve ein.

    Die gespeicherte Kapitalkurve reicht über die geladene OHLC-Spanne: davor
    liegt der Indikator-Vorlauf, in dem der Motor jedes Entry maskiert — die Kurve
    ist dort flach, und zeitlich liegt dieser Vorlauf im Testfenster des vorigen
    Folds. Ungefiltert verwässert er die verkettete Reihe.
    """
    rows = [
        (datetime(2020, 12, 30), 100.0),  # Vorlauf, flach
        (datetime(2020, 12, 31), 100.0),  # Vorlauf, flach
        (datetime(2021, 1, 1), 100.0),    # Testfenster beginnt
        (datetime(2021, 2, 1), 110.0),
        (datetime(2021, 3, 1), 99.0),
        (datetime(2021, 4, 1), 300.0),    # Fenster-Ende: gehört dem nächsten Fold
    ]
    for timestamp, value in rows:
        test_session.add(BacktestEquity(result_id=1, timestamp=timestamp, value=value))
    test_session.commit()

    folds = [_fold(1, result_id=1, is_value=2.0, oos_return=-1.0)]
    aggregate = build_chain_aggregate(test_session, _PLAN, folds)

    assert aggregate['bar_count'] == 2, 'nur die Renditen innerhalb des Testfensters'
    assert aggregate['total_return_pct'] == pytest.approx(-1.0)


def test_missing_equity_curve_is_reported_instead_of_silently_dropped(test_session):
    folds = [_fold(1, result_id=42, is_value=2.0, oos_return=1.0)]
    aggregate = build_chain_aggregate(test_session, _PLAN, folds)

    assert aggregate['folds_with_winner'] == 1
    assert aggregate['folds_in_curve'] == 0
    assert aggregate['total_return_pct'] is None
    assert any('42' in note for note in aggregate['notes'])
