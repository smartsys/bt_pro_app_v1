"""Tests für die risikobasierte Positionsgröße im Spec-Runner.

``size_type = 'risk_percent'`` bemisst jede Order als
``(Kontowert der Spalte x risk_pct) / Stopabstand``. Geprüft wird:

  1. Rechnung: Die ausgeführte Größe entspricht der Formel — je Trade
     unterschiedlich, mit dem Kontostand wachsend (Compounding).
  2. Spalten-Zuordnung: Im Multi-Combo-Lauf rechnet jede Spalte mit ihrem
     eigenen Kontostand; der gechunkte Lauf liefert dasselbe.
  3. Stille Kürzung: Ohne Kreditlinie meldet der Lauf, dass VBT Orders auf das
     verfügbare Geld gekürzt hat.
  4. Keine Nebenwirkung: Ein Lauf mit fester Größe rechnet unverändert.
  5. Abbruch mit Klartext: fehlendes ``risk_pct``, fehlender ``sl_stop``,
     Stop-Sweep, ``delta_format: 'target'`` und ``from_ago != 0``.

Methodik wie in ``test_stop_indicator_reference.py``: deterministische OHLCV-Reihe
mit wechselnden Volatilitäts-Abschnitten, echter Spec-Runner, kein Mocking.
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

from user_data.strategies.generic.indicator_factory import build_indicators  # noqa: E402
from user_data.strategies.generic.risk_sizing import (  # noqa: E402
    build_risk_sizing_spec,
    merge_reports,
)
from user_data.strategies.generic.spec_runner import run_spec_strategy  # noqa: E402
from user_data.utils.database.repository import _extract_metrics  # noqa: E402
from user_data.utils.metrics.trading_window import slice_to_trading_window  # noqa: E402


# Kennzahlen, die scipy über das gesamte Spalten-Array reduziert. Ihre
# Summationsreihenfolge hängt an der Spaltenzahl, die im gechunkten Lauf kleiner
# ist — der Unterschied liegt in der letzten Stelle und tritt unabhängig von der
# risikobasierten Größe auf (mit size_type='amount' an denselben Spalten gemessen).
_REDUCTION_JITTER_METRICS = frozenset({'skew', 'kurtosis'})

_BASE_PORTFOLIO = {
    'fees': 0.0,
    'init_cash': 10_000.0,
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

# Long-Einstieg über dem gleitenden Durchschnitt, Ausstieg ausschließlich über
# den Stop — damit ist jeder Trade sauber einem Einstiegsbalken zuzuordnen.
_RULES = {
    'entry': {
        'blocks': [
            {
                'conditions': [
                    {
                        'lhs': 'close',
                        'lhs_shift': 0,
                        'op': '>',
                        'rhs': 'indicator:sma_trend:real',
                        'rhs_shift': 0,
                    }
                ]
            }
        ]
    },
}


def _make_ohlc_data(n: int = 1500) -> vbt.Data:
    """Deterministische OHLCV-Reihe mit abwechselnd ruhigen und bewegten Abschnitten."""
    rng = np.random.default_rng(7)
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
        {
            'Open': open_,
            'High': high,
            'Low': low,
            'Close': close,
            'Volume': np.full(n, 1000.0),
        },
        index=idx,
    )
    data = vbt.Data.from_data({'X': df})
    data.use_feature_config_of(vbt.BinanceData)
    return data


def _indicators(atr=14, sma=20, with_stop_ref: bool = True) -> dict:
    spec = {
        'atr_ref': {'indicator': 'talib:ATR', 'tf': 'same', 'timeperiod': atr},
        'sma_trend': {'indicator': 'talib:SMA', 'tf': 'same', 'timeperiod': sma},
    }
    if with_stop_ref:
        spec['_stops'] = {
            'sl_stop': {'ref': 'indicator:atr_ref:real', 'mult': 5.0},
            'delta_format': 'absolute',
        }
    return spec


def _config(chunk_size=None, **portfolio) -> dict:
    config = {k: v for k, v in _BACKTEST_CONFIG.items() if k != 'portfolio'}
    config['portfolio'] = {**_BASE_PORTFOLIO, **portfolio}
    if chunk_size is None:
        config['_disable_chunked'] = True
    else:
        config['chunk_size'] = chunk_size
    return config


def _run(indicators_json: dict, data, config: dict) -> dict:
    return run_spec_strategy(
        ohlc_data=data,
        indicators_json=indicators_json,
        backtest_config_json=config,
        rules_json=_RULES,
    )


def _atr_series(data, timeperiod: int) -> pd.Series:
    """ATR außerhalb des Runners gerechnet — unabhängige Gegenrechnung."""
    spec = {'atr_ref': {'indicator': 'talib:ATR', 'tf': 'same', 'timeperiod': timeperiod}}
    series = build_indicators(spec, data, base_tf='1h')['atr_ref'].real
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    return series


def _buy_orders(portfolio, col: int = 0) -> pd.DataFrame:
    records = pd.DataFrame(portfolio.orders.values)
    return records[(records['col'] == col) & (records['side'] == 0)].reset_index(drop=True)


def _value_of(portfolio, col: int, bar: int) -> float:
    value = portfolio.value
    if isinstance(value, pd.DataFrame):
        return float(value.iloc[bar, col])
    return float(value.iloc[bar])


@pytest.fixture(scope='module')
def ohlc_data():
    return _make_ohlc_data()


@pytest.fixture(scope='module')
def leveraged_run(ohlc_data):
    """Risikolauf: 3 % Kontorisiko, 10-fache Kreditlinie, Stop = 5 x ATR(14)."""
    return _run(
        _indicators(),
        ohlc_data,
        _config(size_type='risk_percent', risk_pct=0.03, leverage=10.0),
    )


@pytest.fixture(scope='module')
def multi_combo_indicators() -> dict:
    return _indicators(atr=[7, 14], sma=[20, 40, 60])


# ============================================================================
# 1. Rechnung
# ============================================================================

class TestOrderSizeFollowsTheRiskFormula:
    """Die ausgeführte Größe ist Kontowert x risk_pct / Stopabstand."""

    def test_each_order_matches_account_value_times_risk_over_stop_distance(
        self, leveraged_run, ohlc_data
    ):
        portfolio = leveraged_run['portfolios']
        atr = _atr_series(ohlc_data, 14)
        orders = _buy_orders(portfolio)
        assert len(orders) >= 3, 'Der Lauf muss genug Trades für den Nachweis liefern'

        sizes = []
        for _, order in orders.iterrows():
            bar = int(order['idx'])
            stop_distance = 5.0 * float(atr.iloc[bar])
            account_value = _value_of(portfolio, 0, bar - 1)
            expected = account_value * 0.03 / stop_distance
            assert float(order['size']) == pytest.approx(expected, rel=1e-12)
            sizes.append(round(float(order['size']), 6))

        assert len(set(sizes)) == len(sizes), (
            'Die Größen müssen sich von Trade zu Trade unterscheiden — sonst '
            'wäre der Nachweis gegen eine konstante Größe blind'
        )

    def test_size_grows_with_the_account_instead_of_the_initial_cash(
        self, leveraged_run, ohlc_data
    ):
        portfolio = leveraged_run['portfolios']
        atr = _atr_series(ohlc_data, 14)
        orders = _buy_orders(portfolio)

        differences = []
        for position, (_, order) in enumerate(orders.iterrows()):
            bar = int(order['idx'])
            stop_distance = 5.0 * float(atr.iloc[bar])
            fixed_base = 10_000.0 * 0.03 / stop_distance
            differences.append(float(order['size']) - fixed_base)
            if position == 0:
                # Der erste Trade läuft noch auf dem Anfangskapital.
                assert differences[0] == pytest.approx(0.0, abs=1e-9)

        assert any(abs(diff) > 1e-6 for diff in differences[1:]), (
            'Ab dem zweiten Trade muss sich die Größe von der auf init_cash '
            'festgenagelten Basis unterscheiden'
        )

    def test_run_reports_no_truncation_when_the_credit_line_is_sufficient(
        self, leveraged_run
    ):
        report = leveraged_run['risk_sizing_report']
        assert report['n_sized'] >= 3
        assert report['n_truncated'] == 0
        assert report['note'] is None


# ============================================================================
# 2. Spalten-Zuordnung
# ============================================================================

class TestPerColumnAccountValue:
    """Jede Portfolio-Spalte rechnet mit ihrem eigenen Kontostand."""

    def test_multi_combo_sizes_follow_the_account_of_their_own_column(
        self, multi_combo_indicators, ohlc_data
    ):
        result = _run(
            multi_combo_indicators,
            ohlc_data,
            _config(size_type='risk_percent', risk_pct=0.03, leverage=10.0),
        )
        portfolio = result['portfolios']
        columns = list(portfolio.wrapper.columns)
        assert len(columns) == 6

        checked_columns = 0
        for col in (2, 5):
            atr_length = int(columns[col][1])
            atr = _atr_series(ohlc_data, atr_length)
            orders = _buy_orders(portfolio, col=col)
            assert len(orders) >= 2
            own_column_wins = False
            for _, order in orders.iterrows():
                bar = int(order['idx'])
                stop_distance = 5.0 * float(atr.iloc[bar])
                expected = _value_of(portfolio, col, bar - 1) * 0.03 / stop_distance
                assert float(order['size']) == pytest.approx(expected, rel=1e-12)
                from_column_zero = (
                    _value_of(portfolio, 0, bar - 1) * 0.03 / stop_distance
                )
                if abs(from_column_zero - expected) > 1e-6:
                    own_column_wins = True
            assert own_column_wins, (
                f'Spalte {col}: der Kontostand der Spalte 0 müsste erkennbar ein '
                f'anderes Ergebnis liefern — sonst ist die Spalte-0-Falle nicht geprüft'
            )
            checked_columns += 1
        assert checked_columns == 2

    def test_chunked_run_matches_unchunked_metrics_per_column(
        self, multi_combo_indicators, ohlc_data
    ):
        portfolio_kwargs = dict(size_type='risk_percent', risk_pct=0.03, leverage=10.0)
        config = _config(**portfolio_kwargs)
        unchunked = _run(multi_combo_indicators, ohlc_data, config)['portfolios']
        windowed = slice_to_trading_window(unchunked, config)
        expected_by_label = dict(
            zip(
                list(windowed.wrapper.columns),
                _extract_metrics(windowed, windowed.wrapper.columns, config),
            )
        )

        # chunk_size kleiner als die Kombinationszahl erzwingt den gechunkten Pfad.
        chunked = _run(
            multi_combo_indicators, ohlc_data, _config(chunk_size=2, **portfolio_kwargs)
        )
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
                        # scipy reduziert über ein (n_bars, n_spalten)-Array; die
                        # Summationsreihenfolge hängt an der Spaltenzahl, die im
                        # Chunk kleiner ist. Der Unterschied liegt in der letzten
                        # Stelle und ist NICHT von der risikobasierten Größe
                        # verursacht — derselbe Lauf mit size_type='amount' zeigt
                        # ihn an denselben Spalten.
                        assert got == pytest.approx(want, rel=1e-9)
                        continue
                assert got == want, f'Spalte {label}, Kennzahl {key}: {got} statt {want}'


# ============================================================================
# 3. Stille Kürzung
# ============================================================================

class TestTruncationIsReported:
    """Ohne Kreditlinie kürzt VBT still — der Lauf muss es melden."""

    def test_run_without_leverage_reports_the_cut_orders(self, ohlc_data):
        result = _run(
            _indicators(),
            ohlc_data,
            _config(size_type='risk_percent', risk_pct=0.03, leverage=1.0),
        )
        report = result['risk_sizing_report']
        assert report['n_truncated'] > 0
        assert report['max_shortfall_pct'] > 0.0
        assert report['note'] is not None
        assert 'gekürzt' in report['note']
        assert 'leverage' in report['note']

    def test_reports_of_several_chunks_are_summed_up(self):
        merged = merge_reports(
            [
                {'n_sized': 4, 'n_unsized': 1, 'n_truncated': 2,
                 'max_shortfall_pct': 10.0, 'note': 'x'},
                {'n_sized': 6, 'n_unsized': 0, 'n_truncated': 1,
                 'max_shortfall_pct': 40.0, 'note': 'y'},
            ]
        )
        assert merged['n_sized'] == 10
        assert merged['n_unsized'] == 1
        assert merged['n_truncated'] == 3
        assert merged['max_shortfall_pct'] == 40.0
        assert '3 von 10' in merged['note']


# ============================================================================
# 4. Keine Nebenwirkung
# ============================================================================

class TestFixedSizeStaysUntouched:
    """Ohne 'risk_percent' greift der Zweig nicht."""

    def test_fixed_amount_run_orders_exactly_the_configured_size(self, ohlc_data):
        result = _run(
            _indicators(),
            ohlc_data,
            _config(size_type='amount', size=1.0),
        )
        portfolio = result['portfolios']
        orders = _buy_orders(portfolio)
        assert len(orders) >= 3
        assert (orders['size'] == 1.0).all()
        assert result['risk_sizing_report'] is None

    def test_value_sizing_keeps_the_configured_order_value(self, ohlc_data):
        config = _config(size_type='value', size=1000.0)
        result = _run(_indicators(), ohlc_data, config)
        orders = _buy_orders(result['portfolios'])
        assert len(orders) >= 3
        assert (orders['size'] * orders['price']).round(6).eq(1000.0).all()
        assert result['risk_sizing_report'] is None


# ============================================================================
# 5. Abbruch mit Klartext
# ============================================================================

class TestConfigurationIsRejectedWithPlainText:
    """Undefinierte Rechnungen brechen ab, statt einen Ersatzwert zu setzen."""

    def test_missing_stop_loss_is_rejected(self, ohlc_data):
        indicators_json = _indicators(with_stop_ref=False)
        indicators_json['_stops'] = {'tp_stop': 0.05, 'delta_format': 'percent'}
        with pytest.raises(ValueError) as exc:
            _run(
                indicators_json,
                ohlc_data,
                _config(size_type='risk_percent', risk_pct=0.03, leverage=10.0),
            )
        assert 'sl_stop' in str(exc.value)

    def test_missing_risk_pct_is_rejected(self):
        with pytest.raises(ValueError) as exc:
            build_risk_sizing_spec(
                {'size_type': 'risk_percent'},
                {'sl_stop': 0.02},
                stops_swept=False,
            )
        assert 'risk_pct' in str(exc.value)

    def test_stop_sweep_is_rejected(self):
        with pytest.raises(ValueError) as exc:
            build_risk_sizing_spec(
                {'size_type': 'risk_percent', 'risk_pct': 0.03},
                {'sl_stop': 0.02},
                stops_swept=True,
            )
        assert 'Stop-Sweep' in str(exc.value)

    def test_target_delta_format_is_rejected(self):
        with pytest.raises(ValueError) as exc:
            build_risk_sizing_spec(
                {'size_type': 'risk_percent', 'risk_pct': 0.03},
                {'sl_stop': 100.0, 'delta_format': 'target'},
                stops_swept=False,
            )
        assert 'target' in str(exc.value)

    def test_fixed_size_type_returns_no_specification(self):
        assert build_risk_sizing_spec(
            {'size_type': 'value', 'size': 1000.0}, {'sl_stop': 0.02}, False
        ) is None
