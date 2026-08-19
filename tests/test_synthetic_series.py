"""Tests für die Bar-Permutation (synthetische Preisreihen als Nullmodell).

Sichert die vier zugesagten Eigenschaften des Moduls
`user_data/utils/analysis/synthetic_series.py` ab:

1. OHLC-Konsistenz je Balken (High >= max(O, C) >= min(O, C) >= Low)
2. Identische Länge und identischer Zeitindex wie die echte Reihe
3. Erhaltene Randverteilung (sortierte Log-Bar-Renditen identisch)
4. Determinismus je Seed; verschiedene Seeds -> verschiedene Reihen

Dazu die Ausgabeform: Der synthetische Zwilling ist ein echtes `vbt.Data`-Objekt, auf dem
`get(...)` und `resample(tf)` nativ laufen — und den `run_spec_strategy` inklusive
abweichendem Per-Indikator-Timeframe ohne Sonderweg durchrechnet (Rauchtest am Ende).
"""

import numpy as np
import pandas as pd
import pytest
import vectorbtpro as vbt

from user_data.utils.analysis.synthetic_series import (
    bar_log_returns,
    decompose_bars,
    iter_synthetic_data,
    make_synthetic_data,
    permutation_order,
    permute_frame,
    reconstruct_frame,
)


# ---------------------------------------------------------------------------
# Fixtures / Helfer
# ---------------------------------------------------------------------------

def _make_real_frame(n: int = 600, seed: int = 11, freq: str = '4h') -> pd.DataFrame:
    """Baut eine plausible, konsistente OHLCV-Reihe als 'echte' Eingabe.

    Bewusst mit Trend und Volatilitäts-Clustern, damit die Permutation überhaupt etwas
    zu zerstören hat.
    """
    rng = np.random.default_rng(seed)
    # Volatilitäts-Cluster: die Streuung schwankt langsam über die Zeit.
    vol = 0.004 + 0.004 * (1.0 + np.sin(np.linspace(0.0, 8.0, n))) / 2.0
    steps = rng.normal(0.0002, 1.0, size=n) * vol
    close = 100.0 * np.exp(np.cumsum(steps))
    open_ = np.empty(n)
    open_[0] = 100.0
    open_[1:] = close[:-1] * np.exp(rng.normal(0.0, 0.0005, size=n - 1))
    body_top = np.maximum(open_, close)
    body_bottom = np.minimum(open_, close)
    high = body_top * np.exp(rng.uniform(0.0, 0.004, size=n))
    low = body_bottom * np.exp(-rng.uniform(0.0, 0.004, size=n))
    volume = rng.uniform(1000.0, 10000.0, size=n)
    index = pd.date_range('2020-01-01', periods=n, freq=freq, tz='UTC')
    return pd.DataFrame(
        {'Open': open_, 'High': high, 'Low': low, 'Close': close, 'Volume': volume},
        index=index,
    )


def _make_real_data(n: int = 600, seed: int = 11, symbols=('BTCUSDT',)) -> vbt.Data:
    """Baut ein konfiguriertes vbt.Data wie `load_ohlc_data` es liefert."""
    data = vbt.Data.from_data({
        symbol: _make_real_frame(n=n, seed=seed + offset)
        for offset, symbol in enumerate(symbols)
    })
    data.use_feature_config_of(vbt.BinanceData)
    return data


def _assert_ohlc_consistent(frame: pd.DataFrame) -> None:
    """Prüft die OHLC-Ordnung je Balken."""
    open_ = frame['Open'].to_numpy()
    high = frame['High'].to_numpy()
    low = frame['Low'].to_numpy()
    close = frame['Close'].to_numpy()
    body_top = np.maximum(open_, close)
    body_bottom = np.minimum(open_, close)
    assert np.all(high >= body_top), 'High muss >= max(Open, Close) sein'
    assert np.all(body_top >= body_bottom), 'max(Open, Close) muss >= min(Open, Close) sein'
    assert np.all(body_bottom >= low), 'min(Open, Close) muss >= Low sein'
    assert np.all(np.isfinite(frame.to_numpy())), 'keine NaN/Inf in der synthetischen Reihe'


# ---------------------------------------------------------------------------
# Zugesagte Eigenschaft 1: OHLC-Konsistenz
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('seed', [1, 7, 42, 1234])
def test_ohlc_stays_consistent_per_bar(seed):
    """Jeder synthetische Balken erfüllt High >= max(O, C) >= min(O, C) >= Low."""
    real = _make_real_frame()
    synthetic = permute_frame(real, seed=seed)
    _assert_ohlc_consistent(synthetic)


def test_ohlc_stays_consistent_with_extreme_wicks():
    """Auch bei Doji-Balken (Open == Close) und riesigen Dochten bleibt die Ordnung."""
    index = pd.date_range('2021-01-01', periods=200, freq='1h', tz='UTC')
    price = np.full(200, 50.0)
    frame = pd.DataFrame(
        {
            'Open': price,
            'High': price * 1.5,
            'Low': price * 0.5,
            'Close': price,
            'Volume': np.ones(200),
        },
        index=index,
    )
    synthetic = permute_frame(frame, seed=3)
    _assert_ohlc_consistent(synthetic)


# ---------------------------------------------------------------------------
# Zugesagte Eigenschaft 2: Länge und Zeitindex
# ---------------------------------------------------------------------------

def test_length_and_index_are_identical():
    """Die synthetische Reihe hat dieselbe Länge, denselben Index und dieselben Spalten."""
    real = _make_real_frame()
    synthetic = permute_frame(real, seed=5)
    assert len(synthetic) == len(real)
    assert synthetic.index.equals(real.index)
    assert list(synthetic.columns) == list(real.columns)


def test_first_bar_and_start_price_are_real():
    """Balken 0 wird unverändert übernommen — die Reihe startet beim echten Preis."""
    real = _make_real_frame()
    synthetic = permute_frame(real, seed=9)
    for column in ('Open', 'High', 'Low', 'Close', 'Volume'):
        assert synthetic[column].iloc[0] == pytest.approx(real[column].iloc[0], rel=0, abs=0)


# ---------------------------------------------------------------------------
# Zugesagte Eigenschaft 3: erhaltene Randverteilung
# ---------------------------------------------------------------------------

def test_marginal_distribution_of_bar_returns_is_preserved():
    """Die sortierten Log-Bar-Renditen sind identisch — nur ihre Reihenfolge ändert sich."""
    real = _make_real_frame()
    synthetic = permute_frame(real, seed=17)

    real_returns = np.sort(bar_log_returns(real))
    synthetic_returns = np.sort(bar_log_returns(synthetic))
    np.testing.assert_allclose(synthetic_returns, real_returns, rtol=1e-11, atol=1e-14)

    # Gegenprobe: die unsortierten Renditen unterscheiden sich deutlich, sonst wäre
    # der Test durch eine Identitäts-Permutation trivial erfüllt.
    assert not np.allclose(bar_log_returns(synthetic), bar_log_returns(real))


def test_wick_and_gap_ratios_are_preserved_as_a_unit():
    """Die vier Innenverhältnisse bleiben als Balken-Einheit zusammen."""
    real = _make_real_frame()
    synthetic = permute_frame(real, seed=23)

    real_components = decompose_bars(real)
    synthetic_components = decompose_bars(synthetic)
    for field in ('gap', 'body', 'upper_wick', 'lower_wick'):
        np.testing.assert_allclose(
            np.sort(getattr(synthetic_components, field)),
            np.sort(getattr(real_components, field)),
            rtol=1e-10,
            atol=1e-14,
            err_msg=f'Randverteilung von {field} nicht erhalten',
        )


def test_volume_travels_with_its_bar():
    """Volume wird nur umsortiert, nicht neu erzeugt."""
    real = _make_real_frame()
    synthetic = permute_frame(real, seed=31)
    np.testing.assert_array_equal(
        np.sort(synthetic['Volume'].to_numpy()),
        np.sort(real['Volume'].to_numpy()),
    )
    assert synthetic['Volume'].sum() == pytest.approx(real['Volume'].sum())


def test_non_price_columns_follow_the_same_permutation_as_the_bar():
    """Eine Marker-Spalte zeigt, dass Zusatzspalten den Balken-Wechsel mitmachen."""
    real = _make_real_frame(n=300)
    real = real.assign(BarMarker=np.arange(len(real), dtype=float))
    synthetic = permute_frame(real, seed=4)

    marker = synthetic['BarMarker'].to_numpy().astype(int)
    assert marker[0] == 0, 'Balken 0 bleibt stehen'
    assert sorted(marker) == list(range(len(real))), 'jeder Balken kommt genau einmal vor'

    # Die Bar-Rendite am Zielplatz muss die Rendite des Quell-Balkens sein.
    real_returns = bar_log_returns(real)
    synthetic_returns = bar_log_returns(synthetic)
    expected = real_returns[marker[1:] - 1]
    np.testing.assert_allclose(synthetic_returns, expected, rtol=1e-10, atol=1e-14)


# ---------------------------------------------------------------------------
# Zugesagte Eigenschaft 4: Determinismus
# ---------------------------------------------------------------------------

def test_same_seed_produces_identical_series():
    """Gleicher Seed, gleiches Ergebnis — bit-genau."""
    real = _make_real_frame()
    first = permute_frame(real, seed=99)
    second = permute_frame(real, seed=99)
    pd.testing.assert_frame_equal(first, second)


def test_different_seeds_produce_different_series():
    """Verschiedene Seeds liefern verschiedene Reihen."""
    real = _make_real_frame()
    first = permute_frame(real, seed=100)
    second = permute_frame(real, seed=101)
    assert not first['Close'].equals(second['Close'])
    assert not np.allclose(first['Close'].to_numpy(), second['Close'].to_numpy())


def test_permutation_order_is_a_full_permutation():
    """Die Reihenfolge deckt genau die n-1 permutierbaren Einheiten ab."""
    order = permutation_order(500, seed=8)
    assert order.shape == (499,)
    assert sorted(order.tolist()) == list(range(499))
    np.testing.assert_array_equal(order, permutation_order(500, seed=8))


# ---------------------------------------------------------------------------
# Eingabe-Prüfungen (sichtbarer Abbruch statt stiller Reparatur)
# ---------------------------------------------------------------------------

def test_series_that_is_too_short_is_rejected():
    real = _make_real_frame(n=2)
    with pytest.raises(ValueError, match='mindestens 3 Balken'):
        decompose_bars(real)


def test_missing_price_column_is_rejected():
    real = _make_real_frame(n=50).drop(columns=['High'])
    with pytest.raises(ValueError, match="'high'"):
        decompose_bars(real)


def test_nan_in_price_column_is_rejected():
    real = _make_real_frame(n=50)
    real.iloc[10, real.columns.get_loc('Close')] = np.nan
    with pytest.raises(ValueError, match='NaN'):
        decompose_bars(real)


def test_non_positive_price_is_rejected():
    real = _make_real_frame(n=50)
    real.iloc[10, real.columns.get_loc('Low')] = 0.0
    with pytest.raises(ValueError, match='<= 0'):
        decompose_bars(real)


def test_inconsistent_real_bar_is_rejected():
    """Ein defekter echter Balken bricht ab, statt den Defekt weiterzutragen."""
    real = _make_real_frame(n=50)
    real.iloc[10, real.columns.get_loc('High')] = real['Low'].iloc[10] * 0.5
    with pytest.raises(ValueError, match='inkonsistente Balken'):
        decompose_bars(real)


def test_order_length_mismatch_is_rejected():
    real = _make_real_frame(n=50)
    components = decompose_bars(real)
    with pytest.raises(ValueError, match='order hat die Länge'):
        reconstruct_frame(real, components, np.arange(10))


# ---------------------------------------------------------------------------
# Ausgabeform: vbt.Data-Klon
# ---------------------------------------------------------------------------

def test_synthetic_data_is_a_vbt_data_clone():
    """Der Zwilling behält Typ, Symbole, Feature-Config, Index und Frequenz."""
    real = _make_real_data()
    synthetic = make_synthetic_data(real, seed=13)

    assert type(synthetic) is type(real)
    assert synthetic.symbols == real.symbols
    assert list(synthetic.features) == list(real.features)
    assert synthetic.wrapper.index.equals(real.wrapper.index)
    assert synthetic.wrapper.freq == real.wrapper.freq
    assert synthetic.feature_config == real.feature_config
    # Die echte Reihe darf nicht verändert worden sein.
    assert not np.allclose(
        synthetic.get('Close').to_numpy(), real.get('Close').to_numpy()
    )


def test_synthetic_data_get_returns_consistent_ohlcv():
    """`get(...)` liefert dieselben Serien wie ein direkter Frame-Zugriff."""
    real = _make_real_data()
    synthetic = make_synthetic_data(real, seed=13)

    frame = pd.DataFrame({
        'Open': synthetic.get('Open'),
        'High': synthetic.get('High'),
        'Low': synthetic.get('Low'),
        'Close': synthetic.get('Close'),
        'Volume': synthetic.get('Volume'),
    })
    assert frame.index.equals(real.wrapper.index)
    _assert_ohlc_consistent(frame)


def test_synthetic_data_resamples_natively():
    """`resample(tf)` aggregiert korrekt — Voraussetzung für Per-Indikator-Timeframes."""
    real = _make_real_data(n=600)  # 600 x 4h = 100 Tage
    synthetic = make_synthetic_data(real, seed=13)

    resampled = synthetic.resample('1D')
    assert len(resampled.wrapper.index) == 100

    daily_high = resampled.get('High')
    daily_open = resampled.get('Open')
    base_high = synthetic.get('High')
    base_open = synthetic.get('Open')

    first_day = base_high.index.normalize() == daily_high.index[0]
    assert daily_high.iloc[0] == pytest.approx(base_high[first_day].max())
    assert daily_open.iloc[0] == pytest.approx(base_open[first_day].iloc[0])
    _assert_ohlc_consistent(pd.DataFrame({
        'Open': daily_open,
        'High': daily_high,
        'Low': resampled.get('Low'),
        'Close': resampled.get('Close'),
    }))


def test_all_symbols_share_one_permutation():
    """Mehrere Symbole tauschen ihre Balken gemeinsam (Querschnitt bleibt zusammen)."""
    frame_a = _make_real_frame(n=300, seed=1)
    frame_b = _make_real_frame(n=300, seed=2)
    marker = np.arange(300, dtype=float)
    real = vbt.Data.from_data({
        'AAA': frame_a.assign(BarMarker=marker),
        'BBB': frame_b.assign(BarMarker=marker),
    })

    synthetic = make_synthetic_data(real, seed=77)
    marker_a = synthetic.data['AAA']['BarMarker'].to_numpy()
    marker_b = synthetic.data['BBB']['BarMarker'].to_numpy()
    np.testing.assert_array_equal(marker_a, marker_b)
    # Beide Symbole bleiben je für sich konsistent.
    _assert_ohlc_consistent(synthetic.data['AAA'])
    _assert_ohlc_consistent(synthetic.data['BBB'])


def test_feature_oriented_data_is_rejected():
    """Feature-orientierte Data-Objekte brechen mit klarer Meldung ab."""
    real = _make_real_data().to_feature_oriented()
    with pytest.raises(ValueError, match='symbol-orientiertes vbt.Data'):
        make_synthetic_data(real, seed=1)


# ---------------------------------------------------------------------------
# Generator über N Reihen
# ---------------------------------------------------------------------------

def test_iter_synthetic_data_yields_n_distinct_series_with_sequential_seeds():
    """N Reihen, Seeds `seed`..`seed+N-1`, jede Reihe anders."""
    real = _make_real_data(n=300)
    produced = list(iter_synthetic_data(real, n_series=4, seed=200))

    assert [seed for seed, _ in produced] == [200, 201, 202, 203]
    closes = [data.get('Close').to_numpy() for _, data in produced]
    for i in range(len(closes)):
        for j in range(i + 1, len(closes)):
            assert not np.allclose(closes[i], closes[j])

    # Reproduzierbar über den Generator hinweg.
    again = list(iter_synthetic_data(real, n_series=4, seed=200))
    for (_, first), (_, second) in zip(produced, again):
        np.testing.assert_array_equal(
            first.get('Close').to_numpy(), second.get('Close').to_numpy()
        )


def test_iter_synthetic_data_rejects_zero_series():
    real = _make_real_data(n=100)
    with pytest.raises(ValueError, match='n_series muss >= 1 sein'):
        list(iter_synthetic_data(real, n_series=0))


# ---------------------------------------------------------------------------
# Rauchtest: die Ausgabeform taugt als Eingang für run_spec_strategy
# ---------------------------------------------------------------------------

def _smoke_indicators_json() -> dict:
    """RSI auf 1d bei 4h-Basis — erzwingt `ohlc_data.resample('1d')` im Runner."""
    return {
        'rsi_daily': {
            'indicator': 'talib:RSI',
            'tf': '1d',
            'enabled': True,
            'close': 'close',
            'timeperiod': 14,
        },
        'sma_base': {
            'indicator': 'custom:dwsFastSMA',
            'tf': 'same',
            'enabled': True,
            'source': 'close',
            'length': 20,
            'multiplier': 1,
        },
    }


def _smoke_rules_json() -> dict:
    return {
        'entry': {'blocks': [{'conditions': [
            {'lhs': 'indicator:rsi_daily:real', 'op': '<', 'rhs': 55},
            {'lhs': 'close', 'op': '>', 'rhs': 'indicator:sma_base:result'},
        ]}]},
        'exit': {'blocks': [{'conditions': [
            {'lhs': 'indicator:rsi_daily:real', 'op': '>', 'rhs': 60},
        ]}]},
    }


def _smoke_backtest_config() -> dict:
    return {
        'start': '2020-01-01',
        'end': '2020-12-31',
        'timeframe': '4h',
        'chunk_size': 9999,
        'portfolio': {
            'fees': 0.001,
            'size': 100.0,
            'size_type': 'value',
            'init_cash': 100.0,
            'tp_stop': None,
            'sl_stop': None,
            'tsl_th': None,
            'tsl_stop': None,
            'td_stop': None,
            'delta_format': None,
            'time_delta_format': None,
        },
    }


def test_run_spec_strategy_accepts_synthetic_data_with_coarser_indicator_tf():
    """Rauchtest: echte und synthetische Reihe laufen durch denselben Runner.

    Belegt zweierlei: Die Ausgabeform taugt als Eingang (kein Sonderweg), und der
    Per-Indikator-Timeframe '1d' greift auch auf dem Zwilling — `resample` wird also
    tatsächlich angefasst. Die Kennzahlen müssen sich unterscheiden, sonst hätte die
    Permutation nichts bewirkt.
    """
    from user_data.strategies.generic.spec_runner import run_spec_strategy
    from user_data.utils.database.repository import _extract_metrics

    real = _make_real_data(n=1200, seed=21)
    synthetic = make_synthetic_data(real, seed=555)
    config = _smoke_backtest_config()

    def _metrics(data) -> dict:
        result = run_spec_strategy(
            ohlc_data=data,
            indicators_json=_smoke_indicators_json(),
            backtest_config_json=config,
            rules_json=_smoke_rules_json(),
        )
        assert 'portfolios' in result, 'eine Kombination darf nicht chunken'
        pf = result['portfolios']
        rows = _extract_metrics(pf, pf.wrapper.columns, config)
        assert len(rows) == 1
        return rows[0]

    real_metrics = _metrics(real)
    synthetic_metrics = _metrics(synthetic)

    for field in ('total_return_pct', 'total_trades'):
        assert field in real_metrics and field in synthetic_metrics

    assert real_metrics['total_trades'] > 0, 'die echte Reihe muss handeln, sonst misst der Test nichts'
    assert real_metrics['total_return_pct'] != synthetic_metrics['total_return_pct'], (
        'echte und permutierte Reihe dürfen nicht dasselbe Ergebnis liefern'
    )
