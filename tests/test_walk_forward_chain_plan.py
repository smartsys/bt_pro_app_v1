"""Tests der Fold-Plan-Rechnung und der Plan-Validierung (Ticket 82).

Reine Datums- und Prüflogik ohne DB. Geprüft wird:

* Die Fensterfolge rollt um die OOS-Länge nach vorn; ohne ausdrückliche IS-Länge
  ist das IS-Fenster von Fold 1 exakt das Anker-Fenster (der Anker-Lauf ist dann
  der IS-Lauf und rechnet nicht doppelt).
* Der Indikator-Vorlauf (Abstand ohlc_start → start) bleibt in **jedem** Fenster
  erhalten — IS wie OOS.
* ``set_backtest_window`` setzt explizite Grenzen und behält den Vorlauf.
* Ungültige Eckdaten laufen auf, bevor irgendetwas entsteht.
* Ein Fold-Fenster außerhalb der vorhandenen OHLC-Abdeckung wird abgewiesen — an
  beiden Rändern und bei ganz fehlenden Daten.
"""

from datetime import datetime

import pytest

from services.api.utils.walk_forward import (
    DATE_FORMAT,
    set_backtest_window,
    shift_backtest_window,
    warmup_span,
)
from services.api.utils.walk_forward_plan import (
    build_fold_plan,
    plan_fold,
    validate_plan_coverage,
)

# Anker: ein Jahr Handelsfenster mit 31 Tagen Indikator-Vorlauf.
_ANCHOR = {
    'strategy_family': 'testkonzept',
    'strategy_name': 'v1',
    'symbols': ['BTCUSDT'],
    'exchange': 'binance',
    'timeframe': '4h',
    'start': '2020-01-01',
    'end': '2021-01-01',
    'ohlc_start': '2019-12-01',
    'ohlc_end': '2021-01-01',
}


def _days(date_a: str, date_b: str) -> int:
    """Abstand zweier Datumsangaben in Tagen."""
    return (
        datetime.strptime(date_a, DATE_FORMAT) - datetime.strptime(date_b, DATE_FORMAT)
    ).days


def test_first_is_window_equals_anchor_window_without_explicit_is_length():
    plan = build_fold_plan(_ANCHOR, n_folds=3, oos_months=3)

    first = plan['folds'][0]
    assert first['is_window']['start'] == '2020-01-01'
    assert first['is_window']['end'] == '2021-01-01'


def test_windows_roll_forward_by_the_oos_length():
    plan = build_fold_plan(_ANCHOR, n_folds=3, oos_months=3)
    folds = plan['folds']

    # Testfenster schließt unmittelbar an das Optimierfenster an.
    assert folds[0]['oos_window']['start'] == '2021-01-01'
    assert folds[0]['oos_window']['end'] == '2021-04-01'
    # Nächstes Optimierfenster endet am Ende des vorigen Testfensters.
    assert folds[1]['is_window']['end'] == '2021-04-01'
    assert folds[1]['oos_window']['start'] == '2021-04-01'
    assert folds[1]['oos_window']['end'] == '2021-07-01'
    assert folds[2]['is_window']['end'] == '2021-07-01'
    assert folds[2]['oos_window']['end'] == '2021-10-01'
    assert [fold['fold_index'] for fold in folds] == [1, 2, 3]


def test_rolling_is_window_keeps_its_length():
    plan = build_fold_plan(_ANCHOR, n_folds=3, oos_months=3)
    lengths = {
        _days(fold['is_window']['end'], fold['is_window']['start'])
        for fold in plan['folds']
    }
    assert lengths == {_days('2021-01-01', '2020-01-01')}


def test_explicit_is_length_anchors_at_the_anchor_end():
    plan = build_fold_plan(_ANCHOR, n_folds=2, oos_months=3, is_months=6)
    folds = plan['folds']

    assert folds[0]['is_window']['start'] == '2020-07-01'
    assert folds[0]['is_window']['end'] == '2021-01-01'
    assert folds[1]['is_window']['start'] == '2020-10-01'
    assert folds[1]['is_window']['end'] == '2021-04-01'


def test_warmup_is_preserved_in_every_window():
    plan = build_fold_plan(_ANCHOR, n_folds=3, oos_months=3)
    warmup_days = warmup_span(_ANCHOR).days
    assert warmup_days == 31

    for fold in plan['folds']:
        for window in (fold['is_window'], fold['oos_window']):
            assert _days(window['start'], window['ohlc_start']) == warmup_days
            assert window['ohlc_end'] == window['end']
    assert plan['warmup_days'] == warmup_days


def test_required_span_covers_first_warmup_and_last_end():
    plan = build_fold_plan(_ANCHOR, n_folds=3, oos_months=3)

    assert plan['required_span']['ohlc_start'] == plan['folds'][0]['is_window']['ohlc_start']
    assert plan['required_span']['end'] == plan['folds'][-1]['oos_window']['end']


def test_plan_keeps_the_registered_criterion():
    plan = build_fold_plan(
        _ANCHOR, n_folds=2, oos_months=3,
        selection_metric='sharpe_ratio', selection_direction='min',
        trade_floor=30, metrics_level='kern',
    )
    assert plan['selection_metric'] == 'sharpe_ratio'
    assert plan['selection_direction'] == 'min'
    assert plan['trade_floor'] == 30
    assert plan['metrics_level'] == 'kern'
    # Kein Verdict-Feld im Plan.
    assert 'passed' not in plan and 'verdict' not in plan


@pytest.mark.parametrize('kwargs', [
    {'n_folds': 0, 'oos_months': 3},
    {'n_folds': 2, 'oos_months': 0},
    {'n_folds': 2, 'oos_months': 3, 'is_months': 0},
    {'n_folds': 2, 'oos_months': 3, 'selection_direction': 'hoch'},
    {'n_folds': 2, 'oos_months': 3, 'trade_floor': -1},
])
def test_invalid_plan_inputs_are_rejected(kwargs):
    with pytest.raises(ValueError):
        build_fold_plan(_ANCHOR, **kwargs)


def test_backwards_anchor_window_is_rejected():
    anchor = dict(_ANCHOR, start='2021-01-01', end='2020-01-01')
    with pytest.raises(ValueError):
        build_fold_plan(anchor, n_folds=2, oos_months=3)


def test_plan_fold_rejects_unknown_index():
    plan = build_fold_plan(_ANCHOR, n_folds=2, oos_months=3)
    assert plan_fold(plan, 2)['fold_index'] == 2
    with pytest.raises(ValueError):
        plan_fold(plan, 3)


# ---------------------------------------------------------------------------
# Explizite Fenstergrenzen
# ---------------------------------------------------------------------------

def test_set_backtest_window_keeps_warmup_and_leaves_source_untouched():
    windowed = set_backtest_window(_ANCHOR, '2021-04-01', '2021-07-01')

    assert windowed['start'] == '2021-04-01'
    assert windowed['end'] == '2021-07-01'
    assert windowed['ohlc_start'] == '2021-03-01'
    assert windowed['ohlc_end'] == '2021-07-01'
    assert _ANCHOR['start'] == '2020-01-01'


def test_set_backtest_window_rejects_empty_window():
    with pytest.raises(ValueError):
        set_backtest_window(_ANCHOR, '2021-04-01', '2021-04-01')


def test_shift_and_set_agree_on_the_same_window():
    shifted = shift_backtest_window(_ANCHOR, months=3)
    explicit = set_backtest_window(_ANCHOR, shifted['start'], shifted['end'])
    assert explicit['ohlc_start'] == shifted['ohlc_start']
    assert explicit['ohlc_end'] == shifted['ohlc_end']


# ---------------------------------------------------------------------------
# Plan-Validierung gegen die Datenabdeckung
# ---------------------------------------------------------------------------

def test_coverage_validation_passes_when_data_spans_the_plan():
    plan = build_fold_plan(_ANCHOR, n_folds=3, oos_months=3)
    coverage = {'BTCUSDT': ('2019-01-01T00:00:00', '2022-01-01T00:00:00')}
    validate_plan_coverage(plan, coverage)


def test_coverage_validation_rejects_missing_data_at_the_end():
    plan = build_fold_plan(_ANCHOR, n_folds=3, oos_months=3)
    coverage = {'BTCUSDT': ('2019-01-01T00:00:00', '2021-08-01T00:00:00')}
    with pytest.raises(ValueError, match='2021-10-01'):
        validate_plan_coverage(plan, coverage)


def test_coverage_validation_rejects_missing_warmup_at_the_start():
    plan = build_fold_plan(_ANCHOR, n_folds=2, oos_months=3)
    coverage = {'BTCUSDT': ('2019-12-15T00:00:00', '2022-01-01T00:00:00')}
    with pytest.raises(ValueError, match='2019-12-01'):
        validate_plan_coverage(plan, coverage)


def test_coverage_validation_rejects_symbol_without_data():
    plan = build_fold_plan(_ANCHOR, n_folds=2, oos_months=3)
    with pytest.raises(ValueError, match='BTCUSDT'):
        validate_plan_coverage(plan, {'BTCUSDT': None})
