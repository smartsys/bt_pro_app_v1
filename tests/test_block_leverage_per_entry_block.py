"""Tests für den Hebel je Entry-Block im Spec-Runner.

Ein Entry-Block darf ein Feld ``leverage`` tragen (Default 1). Feuert er, bekommt
die Order seinen Hebel; feuern mehrere Blöcke im selben Balken, gilt der höchste.
Geprüft wird:

  1. Wirkung: Die ausgeführte Größe ist die Basisgröße mal dem Hebel des
     feuernden Blocks.
  2. Höchster Hebel gewinnt — und zwar unabhängig von der Reihenfolge der Blöcke.
  3. Keine Nebenwirkung: Ohne Feld und mit ``leverage: 1`` überall rechnet der
     Lauf bit-genau wie vorher, und es entsteht kein Bericht.
  4. Spalten-Zuordnung: Im Multi-Combo-Lauf trägt jede Spalte den Hebel des in
     dieser Spalte feuernden Blocks; der gechunkte Lauf liefert dasselbe.
  5. Abbruch mit Klartext: Stop-Sweep, ``from_ago != 0``, Config-``leverage``
     ungleich 1 und ein ``leverage`` an einem Exit-Block.
  6. Unterdeckung wird gemeldet, nicht verschluckt.

Methodik wie in ``test_risk_based_position_size.py``: deterministische OHLCV-Reihe,
echter Spec-Runner, kein Mocking.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import vectorbtpro as vbt

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from user_data.strategies.generic.block_leverage import (  # noqa: E402
    BLOCK_LEVERAGE_MODE,
    build_block_leverage_spec,
    describe_block_leverage,
    merge_reports,
)
from user_data.strategies.generic.indicator_factory import build_indicators  # noqa: E402
from user_data.strategies.generic.spec_runner import run_spec_strategy  # noqa: E402
from user_data.utils.database.repository import _extract_metrics  # noqa: E402
from user_data.utils.metrics.trading_window import slice_to_trading_window  # noqa: E402


# Kennzahlen, die scipy über das gesamte Spalten-Array reduziert. Ihre
# Summationsreihenfolge hängt an der Spaltenzahl, die im gechunkten Lauf kleiner
# ist — der Unterschied liegt in der letzten Stelle und tritt unabhängig vom
# Block-Hebel auf (dieselbe Ausnahme wie in Ticket 104).
_REDUCTION_JITTER_METRICS = frozenset({'skew', 'kurtosis'})

_BASE_PORTFOLIO = {
    'fees': 0.0,
    'init_cash': 100_000.0,
    'size': 1.0,
    'size_type': 'amount',
    'stop_exit_price': 'hardstop',
}

_BACKTEST_CONFIG = {
    'timeframe': '1h',
    'start': '2023-01-05',
    'end': '2023-03-01',
    'portfolio': dict(_BASE_PORTFOLIO),
}

# Der schmale Block ist eine echte Teilmenge des breiten: an seinen Balken feuern
# beide, und genau dort muss der höhere Hebel gewinnen.
_BROAD_BLOCK = {
    'conditions': [
        {'lhs': 'close', 'lhs_shift': 0, 'op': '>',
         'rhs': 'indicator:sma_fast:real', 'rhs_shift': 0},
    ]
}
_NARROW_BLOCK = {
    'conditions': [
        {'lhs': 'close', 'lhs_shift': 0, 'op': '>',
         'rhs': 'indicator:sma_fast:real', 'rhs_shift': 0},
        {'lhs': 'close', 'lhs_shift': 0, 'op': '>',
         'rhs': 'indicator:sma_gate:real', 'rhs_shift': 0},
    ]
}


def _rules(broad_leverage=None, narrow_leverage=None, swap: bool = False) -> dict:
    """Baut die Regeln; ``None`` lässt das Hebel-Feld ganz weg."""
    broad = dict(_BROAD_BLOCK)
    narrow = dict(_NARROW_BLOCK)
    if broad_leverage is not None:
        broad = {**broad, 'leverage': broad_leverage}
    if narrow_leverage is not None:
        narrow = {**narrow, 'leverage': narrow_leverage}
    blocks = [narrow, broad] if swap else [broad, narrow]
    return {'entry': {'blocks': blocks}}


def _make_ohlc_data(n: int = 1500) -> vbt.Data:
    """Deterministische OHLCV-Reihe mit abwechselnd ruhigen und bewegten Abschnitten."""
    rng = np.random.default_rng(11)
    idx = pd.date_range('2023-01-01', periods=n, freq='1h', tz='UTC')
    volatility = np.where((np.arange(n) // 120) % 2 == 0, 0.20, 1.10)
    steps = rng.normal(0, 1, n) * volatility
    close = 300.0 + np.cumsum(steps)
    open_ = np.empty(n)
    open_[0] = close[0]
    open_[1:] = close[:-1]
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 1, n)) * volatility
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 1, n)) * volatility
    df = pd.DataFrame(
        {'Open': open_, 'High': high, 'Low': low, 'Close': close,
         'Volume': np.full(n, 1000.0)},
        index=idx,
    )
    data = vbt.Data.from_data({'X': df})
    data.use_feature_config_of(vbt.BinanceData)
    return data


def _indicators(fast=20, gate=5) -> dict:
    # Enger Stop (0,5 %): die Trades enden schnell, der Lauf liefert viele
    # Einstiege — nur so kommen beide Blöcke oft genug zum Zug.
    return {
        'sma_fast': {'indicator': 'talib:SMA', 'tf': 'same', 'timeperiod': fast},
        'sma_gate': {'indicator': 'talib:SMA', 'tf': 'same', 'timeperiod': gate},
        '_stops': {'sl_stop': 0.005, 'delta_format': 'percent'},
    }


def _config(chunk_size=None, **portfolio) -> dict:
    config = {k: v for k, v in _BACKTEST_CONFIG.items() if k != 'portfolio'}
    config['portfolio'] = {**_BASE_PORTFOLIO, **portfolio}
    if chunk_size is None:
        config['_disable_chunked'] = True
    else:
        config['chunk_size'] = chunk_size
    return config


def _run(rules: dict, indicators_json: dict, data, config: dict) -> dict:
    return run_spec_strategy(
        ohlc_data=data,
        indicators_json=indicators_json,
        backtest_config_json=config,
        rules_json=rules,
    )


def _sma(data, timeperiod: int) -> pd.Series:
    """SMA außerhalb des Runners gerechnet — unabhängige Gegenrechnung."""
    spec = {'s': {'indicator': 'talib:SMA', 'tf': 'same', 'timeperiod': timeperiod}}
    series = build_indicators(spec, data, base_tf='1h')['s'].real
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    return series


def _buy_orders(portfolio, col: int = 0) -> pd.DataFrame:
    records = pd.DataFrame(portfolio.orders.values)
    return records[(records['col'] == col) & (records['side'] == 0)].reset_index(drop=True)


@pytest.fixture(scope='module')
def ohlc_data():
    return _make_ohlc_data()


@pytest.fixture(scope='module')
def close_series(ohlc_data) -> pd.Series:
    series = ohlc_data.get('Close')
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    return series


# ============================================================================
# 1. Wirkung
# ============================================================================

class TestLeverageOfTheFiringBlockReachesTheOrder:
    """Die Order trägt den Hebel des Blocks, der sie ausgelöst hat."""

    def test_order_size_is_the_base_size_times_the_block_leverage(
        self, ohlc_data, close_series
    ):
        result = _run(
            _rules(narrow_leverage=3.0), _indicators(), ohlc_data, _config()
        )
        portfolio = result['portfolios']
        orders = _buy_orders(portfolio)
        assert len(orders) >= 6, 'Der Lauf muss genug Einstiege für den Nachweis liefern'

        fast = _sma(ohlc_data, 20)
        gate = _sma(ohlc_data, 5)
        seen_levels = set()
        for _, order in orders.iterrows():
            bar = int(order['idx'])
            narrow_fired = (
                close_series.iloc[bar] > fast.iloc[bar]
                and close_series.iloc[bar] > gate.iloc[bar]
            )
            expected = 3.0 if narrow_fired else 1.0
            seen_levels.add(expected)
            assert float(order['size']) == pytest.approx(expected, rel=1e-12), (
                f'Balken {bar}: Größe {order["size"]} statt {expected}'
            )
        assert seen_levels == {1.0, 3.0}, (
            'Der Nachweis braucht beide Fälle — sonst prüft er nur eine Hälfte'
        )

    def test_report_names_the_levered_blocks_and_the_replaced_mode(self, ohlc_data):
        result = _run(
            _rules(narrow_leverage=3.0), _indicators(), ohlc_data, _config()
        )
        report = result['block_leverage_report']
        assert report is not None
        assert report['blocks'] == [
            {'index': 1, 'is_short': False, 'leverage': 3.0}
        ]
        assert report['leverage_mode'] == BLOCK_LEVERAGE_MODE
        assert report['n_truncated'] == 0
        assert report['note'] is None


# ============================================================================
# 2. Höchster Hebel gewinnt
# ============================================================================

class TestHighestLeverageWins:
    """Feuern mehrere Blöcke im selben Balken, zählt der höchste Hebel."""

    def test_block_order_does_not_change_the_result(self, ohlc_data):
        forward = _run(
            _rules(broad_leverage=1.0, narrow_leverage=3.0),
            _indicators(), ohlc_data, _config(),
        )
        reversed_ = _run(
            _rules(broad_leverage=1.0, narrow_leverage=3.0, swap=True),
            _indicators(), ohlc_data, _config(),
        )
        forward_orders = forward['portfolios'].orders.values
        reversed_orders = reversed_['portfolios'].orders.values
        assert len(forward_orders) == len(reversed_orders)
        for field in ('col', 'idx', 'size', 'price', 'side'):
            np.testing.assert_array_equal(
                forward_orders[field], reversed_orders[field],
                err_msg=f'Feld {field} hängt an der Reihenfolge der Blöcke',
            )

    def test_the_higher_leverage_wins_where_both_blocks_fire(
        self, ohlc_data, close_series
    ):
        # Der breite Block trägt hier den höheren Hebel: an den Balken des
        # schmalen Blocks feuern beide, und die Order muss die 3 tragen, nicht
        # die 1 des schmalen Blocks.
        result = _run(
            _rules(broad_leverage=3.0, narrow_leverage=1.0),
            _indicators(), ohlc_data, _config(),
        )
        fast = _sma(ohlc_data, 20)
        gate = _sma(ohlc_data, 5)
        orders = _buy_orders(result['portfolios'])
        both = [
            int(o['idx']) for _, o in orders.iterrows()
            if close_series.iloc[int(o['idx'])] > gate.iloc[int(o['idx'])]
            and close_series.iloc[int(o['idx'])] > fast.iloc[int(o['idx'])]
        ]
        assert both, 'Es muss Balken geben, an denen beide Blöcke feuern'
        for _, order in orders.iterrows():
            assert float(order['size']) == pytest.approx(3.0, rel=1e-12)


# ============================================================================
# 3. Keine Nebenwirkung
# ============================================================================

class TestNoEffectWithoutLeverage:
    """Ohne Hebel und mit Hebel 1 überall bleibt der Lauf, was er war."""

    def test_explicit_leverage_one_matches_the_run_without_the_field(self, ohlc_data):
        without = _run(_rules(), _indicators(), ohlc_data, _config())
        with_ones = _run(
            _rules(broad_leverage=1.0, narrow_leverage=1.0),
            _indicators(), ohlc_data, _config(),
        )
        assert without['block_leverage_report'] is None
        assert with_ones['block_leverage_report'] is None

        config = _config()
        left = slice_to_trading_window(without['portfolios'], config)
        right = slice_to_trading_window(with_ones['portfolios'], config)
        assert _extract_metrics(left, left.wrapper.columns, config) == _extract_metrics(
            right, right.wrapper.columns, config
        )

    def test_a_disabled_block_with_leverage_does_not_arm_the_mechanism(self, ohlc_data):
        rules = _rules(narrow_leverage=3.0)
        rules['entry']['blocks'][1] = {**rules['entry']['blocks'][1], 'enabled': False}
        result = _run(rules, _indicators(), ohlc_data, _config())
        assert result['block_leverage_report'] is None, (
            'Ein abgeschalteter Block feuert nie — sein Hebel ist gegenstandslos'
        )


# ============================================================================
# 4. Multi-Combo und Chunk-Pfad
# ============================================================================

class TestMultiComboAndChunking:
    """Je Spalte der Hebel des in dieser Spalte feuernden Blocks."""

    @staticmethod
    def _expected_sizes(ohlc_data, close, fast_period: int) -> dict:
        fast = _sma(ohlc_data, fast_period)
        gate = _sma(ohlc_data, 5)
        return {
            bar: (3.0 if (close.iloc[bar] > fast.iloc[bar]
                          and close.iloc[bar] > gate.iloc[bar]) else 1.0)
            for bar in range(len(close))
        }

    def test_each_column_carries_the_leverage_of_its_own_firing_block(
        self, ohlc_data, close_series
    ):
        indicators = {
            'sma_fast': {'indicator': 'talib:SMA', 'tf': 'same',
                         'timeperiod': [10, 20, 40]},
            'sma_gate': {'indicator': 'talib:SMA', 'tf': 'same', 'timeperiod': 5},
            '_stops': {'sl_stop': 0.005, 'delta_format': 'percent'},
        }
        result = _run(
            _rules(narrow_leverage=3.0), indicators, ohlc_data, _config()
        )
        portfolio = result['portfolios']
        periods = [
            int(label[0]) if isinstance(label, tuple) else int(label)
            for label in portfolio.wrapper.columns
        ]
        assert len(periods) == 3

        # Bewusst nicht nur Spalte 0 — die Multi-Combo-Falle des Projekts.
        checked_columns = []
        for col in (1, 2):
            expected_by_bar = self._expected_sizes(ohlc_data, close_series, periods[col])
            orders = _buy_orders(portfolio, col=col)
            assert len(orders) >= 2, f'Spalte {col} braucht Einstiege für den Nachweis'
            levels = set()
            for _, order in orders.iterrows():
                want = expected_by_bar[int(order['idx'])]
                levels.add(want)
                assert float(order['size']) == pytest.approx(want, rel=1e-12), (
                    f'Spalte {col}, Balken {int(order["idx"])}: '
                    f'{order["size"]} statt {want}'
                )
            checked_columns.append(levels)
        assert any(3.0 in levels for levels in checked_columns), (
            'Mindestens eine der geprüften Spalten muss den gehebelten Block zeigen'
        )

    def test_chunked_run_matches_the_unchunked_one(self, ohlc_data):
        indicators = {
            'sma_fast': {'indicator': 'talib:SMA', 'tf': 'same',
                         'timeperiod': [10, 20, 40]},
            'sma_gate': {'indicator': 'talib:SMA', 'tf': 'same', 'timeperiod': 5},
            '_stops': {'sl_stop': 0.005, 'delta_format': 'percent'},
        }
        rules = _rules(narrow_leverage=3.0)
        config = _config()
        unchunked = _run(rules, indicators, ohlc_data, config)
        windowed = slice_to_trading_window(unchunked['portfolios'], config)
        expected_by_label = dict(
            zip(
                list(windowed.wrapper.columns),
                _extract_metrics(windowed, windowed.wrapper.columns, config),
            )
        )

        chunked = _run(rules, indicators, ohlc_data, _config(chunk_size=2))
        labels = list(chunked['columns'])
        assert set(labels) == set(expected_by_label)
        for row, label in zip(chunked['metrics_table'], labels):
            expected = expected_by_label[label]
            for key in sorted(set(row) | set(expected)):
                got, want = row.get(key), expected.get(key)
                if isinstance(got, float) and isinstance(want, float):
                    if np.isnan(got) and np.isnan(want):
                        continue
                    if key in _REDUCTION_JITTER_METRICS:
                        assert got == pytest.approx(want, rel=1e-9)
                        continue
                assert got == want, f'Spalte {label}, Kennzahl {key}: {got} statt {want}'

        merged = chunked['block_leverage_report']
        assert merged is not None
        assert merged['blocks'] == [{'index': 1, 'is_short': False, 'leverage': 3.0}]


# ============================================================================
# 5. Riegel mit Klartext
# ============================================================================

class TestGuards:
    """Jede unverträgliche Kombination bricht mit Klartext ab."""

    _PORTFOLIO = {'size': 1.0, 'size_type': 'amount', 'leverage': 1.0}
    _RULES_LEVERED = {'entry': {'blocks': [{**_BROAD_BLOCK, 'leverage': 2.0}]}}

    def test_stop_sweep_together_with_a_block_leverage_is_rejected(self):
        with pytest.raises(ValueError) as exc:
            build_block_leverage_spec(
                self._RULES_LEVERED, self._PORTFOLIO, stops_swept=True
            )
        message = str(exc.value)
        assert 'Stop-Sweep' in message
        assert 'leverage-Array' in message

    def test_from_ago_together_with_a_block_leverage_is_rejected(self):
        with pytest.raises(ValueError) as exc:
            build_block_leverage_spec(
                self._RULES_LEVERED, {**self._PORTFOLIO, 'from_ago': 1},
                stops_swept=False,
            )
        message = str(exc.value)
        assert 'from_ago' in message
        assert '_state_exit_signal_func_nb' in message, (
            'Die Meldung muss die anzupassende Stelle nennen'
        )

    def test_config_leverage_together_with_a_block_leverage_is_rejected(self):
        with pytest.raises(ValueError) as exc:
            build_block_leverage_spec(
                self._RULES_LEVERED, {**self._PORTFOLIO, 'leverage': 3.0},
                stops_swept=False,
            )
        message = str(exc.value)
        assert 'BacktestConfig' in message
        assert 'schließen sich aus' in message

    def test_leverage_on_an_exit_block_is_rejected(self):
        rules = {
            'entry': {'blocks': [dict(_BROAD_BLOCK)]},
            'exit': {'blocks': [{'conditions': [
                {'lhs': 'close', 'lhs_shift': 0, 'op': '<',
                 'rhs': 'indicator:sma_fast:real', 'rhs_shift': 0}
            ], 'leverage': 2.0}]},
        }
        with pytest.raises(ValueError) as exc:
            build_block_leverage_spec(rules, self._PORTFOLIO, stops_swept=False)
        message = str(exc.value)
        assert 'Exit-Block' in message
        assert 'Einstieg' in message

    def test_a_non_numeric_leverage_is_rejected(self):
        rules = {'entry': {'blocks': [{**_BROAD_BLOCK, 'leverage': {'range': [1, 3]}}]}}
        with pytest.raises(ValueError) as exc:
            build_block_leverage_spec(rules, self._PORTFOLIO, stops_swept=False)
        assert 'Zahl' in str(exc.value)

    def test_the_guards_fire_through_the_runner_as_well(self, ohlc_data):
        indicators = dict(_indicators())
        indicators['_stops'] = {
            'sl_stop': {'type': 'arange', 'start': 0.01, 'stop': 0.031,
                        'step': 0.01, 'dtype': 'float'},
            'delta_format': 'percent',
        }
        with pytest.raises(ValueError) as exc:
            _run(_rules(narrow_leverage=3.0), indicators, ohlc_data, _config())
        assert 'Stop-Sweep' in str(exc.value)


# ============================================================================
# 6. Unterdeckung
# ============================================================================

class TestUndercoverageIsReported:
    """Kürzt VBT auf Konto x Hebel, muss der Lauf es melden."""

    def test_a_fixed_sum_above_the_account_is_reported_as_cut(self, ohlc_data):
        result = _run(
            _rules(broad_leverage=2.0, narrow_leverage=2.0),
            _indicators(),
            ohlc_data,
            _config(size=30_000.0, size_type='value', init_cash=10_000.0),
        )
        report = result['block_leverage_report']
        assert report['checked'] is True
        assert report['n_entries'] > 0
        assert report['n_truncated'] > 0
        assert report['max_shortfall_pct'] > 0.0
        assert 'gekürzt' in report['note']
        assert 'Block-Hebel' in report['note']

    def test_a_fitting_fixed_sum_is_not_reported(self, ohlc_data):
        result = _run(
            _rules(broad_leverage=2.0, narrow_leverage=2.0),
            _indicators(),
            ohlc_data,
            _config(size=1_000.0, size_type='value', init_cash=100_000.0),
        )
        report = result['block_leverage_report']
        assert report['checked'] is True
        assert report['n_truncated'] == 0
        assert report['note'] is None

    def test_a_percent_size_says_that_it_was_not_checked(self, ohlc_data):
        result = _run(
            _rules(narrow_leverage=2.0),
            _indicators(),
            ohlc_data,
            _config(size=20.0, size_type='percent100'),
        )
        report = result['block_leverage_report']
        assert report['checked'] is False
        assert 'nicht geprüft' in report['check_note']
        assert report['note'] is None


# ============================================================================
# 7. Ausweis und Chunk-Zusammenfassung
# ============================================================================

class TestReportPlumbing:
    """Ausweis-Text und Zusammenfassung mehrerer Chunks."""

    def test_description_names_blocks_values_and_the_replaced_mode(self):
        spec = build_block_leverage_spec(
            {'entry': {'blocks': [
                dict(_BROAD_BLOCK),
                {**_NARROW_BLOCK, 'leverage': 4.0},
            ]}},
            {'leverage': 1.0, 'leverage_mode': 'lazy'},
            stops_swept=False,
        )
        text = describe_block_leverage(spec, 'lazy')
        # GEÄNDERT: Ticket 106 — der gehebelte Block steht an Position 1 (0-basiert)
        # und heißt in der Beschriftung deshalb 'Block 2', wie in der Toolbox.
        assert 'Block 2' in text
        assert 'Hebel 4' in text
        assert BLOCK_LEVERAGE_MODE in text
        assert 'ersetzt' in text

    def test_reports_of_several_chunks_are_summed_up(self):
        merged = merge_reports([
            {'blocks': [{'index': 0, 'is_short': False, 'leverage': 2.0}],
             'leverage_mode': BLOCK_LEVERAGE_MODE, 'checked': True,
             'check_note': None, 'n_entries': 10, 'n_truncated': 2,
             'max_shortfall_pct': 10.0, 'note': 'x'},
            {'blocks': [{'index': 0, 'is_short': False, 'leverage': 2.0}],
             'leverage_mode': BLOCK_LEVERAGE_MODE, 'checked': True,
             'check_note': None, 'n_entries': 6, 'n_truncated': 1,
             'max_shortfall_pct': 25.0, 'note': 'y'},
        ])
        assert merged['n_entries'] == 16
        assert merged['n_truncated'] == 3
        assert merged['max_shortfall_pct'] == 25.0
        assert '3 von 16' in merged['note']

    def test_merging_nothing_is_an_error_instead_of_an_empty_report(self):
        with pytest.raises(ValueError):
            merge_reports([])
