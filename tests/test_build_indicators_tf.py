"""Integrationstests fuer den Per-Indikator-Timeframe (tf) in build_indicators (Paket B).

Prueft das scharf geschaltete tf-Verhalten des echten Runners:
  - Indikator mit groeberem tf rechnet auf resampled OHLC, Output landet look-ahead-sicher
    am Basis-Index (Multi-Combo-Spalten erhalten) und ist in einen _RealignedIndicator gekapselt
  - Chaining ueber TF-Grenzen (RSI@4h -> EMA@1d) liefert Output am Basis-Index
  - tf gleich Basis = No-Op (echte Instanz, bit-identisch zu tf='same')
  - tf feiner als Basis -> ValueError (Downsampling abgelehnt)
  - tf 'same' = expliziter Sentinel fuer "gleicher tf wie Basis" (kein Wrapper)
  - fehlender tf -> ValueError (kein implizites "gleich" mehr)
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

from user_data.strategies.generic.indicator_factory import (
    build_indicators,
    _RealignedIndicator,
)


@pytest.fixture
def base_data() -> vbt.Data:
    """5min-Basis-Daten (3 Tage, lueckenlos) als konfiguriertes vbt.Data."""
    idx = pd.date_range("2020-01-01", periods=3 * 24 * 12, freq="5min", tz="UTC")
    n = len(idx)
    rng = np.random.default_rng(3)
    close = pd.Series(100 + np.cumsum(rng.normal(0, 0.1, n)), index=idx, name="Close")
    df = pd.DataFrame({
        "Open": close.shift(1).bfill(),
        "High": close + 0.5,
        "Low": close - 0.5,
        "Close": close,
        "Volume": pd.Series(rng.uniform(1, 5, n), index=idx),
    })
    data = vbt.Data.from_data({"X": df})
    data.use_feature_config_of(vbt.BinanceData)
    return data


class TestPerIndicatorTf:
    def test_coarser_tf_output_on_base_index(self, base_data):
        base_index = base_data.wrapper.index
        spec = {"rsi": {"indicator": "talib:RSI", "tf": "4h",
                        "close": "close", "timeperiod": [7, 14]}}
        res = build_indicators(spec, base_data)
        inst = res["rsi"]
        assert isinstance(inst, _RealignedIndicator)
        out = inst.real
        assert isinstance(out, pd.DataFrame) and out.shape[1] == 2, "Multi-Combo erhalten"
        assert out.index.equals(base_index), "Output am Basis-Index"
        # Look-ahead-sicher: fruehe Bars (vor erster abgeschlossener 4h-Kerze) NaN
        assert bool(np.isnan(np.asarray(out)[3]).all())

    def test_chaining_across_tf(self, base_data):
        base_index = base_data.wrapper.index
        spec = {
            "rsi": {"indicator": "talib:RSI", "tf": "4h",
                    "close": "close", "timeperiod": 14},
            "ema": {"indicator": "talib:EMA", "tf": "1d",
                    "close": "indicator:rsi:real", "timeperiod": 5},
        }
        res = build_indicators(spec, base_data)
        assert isinstance(res["ema"], _RealignedIndicator)
        out = res["ema"].real
        assert out.index.equals(base_index)

    def test_tf_equal_base_is_noop(self, base_data):
        """tf == Basis liefert eine echte Instanz, bit-identisch zu tf='same'."""
        spec_tf = {"rsi": {"indicator": "talib:RSI", "tf": "5min",
                           "close": "close", "timeperiod": 14}}
        # GEÄNDERT: Vergleichsbasis ist der explizite Sentinel 'same' (kein fehlender tf mehr)
        spec_same = {"rsi": {"indicator": "talib:RSI", "tf": "same",
                             "close": "close", "timeperiod": 14}}
        res_tf = build_indicators(spec_tf, base_data)["rsi"]
        res_same = build_indicators(spec_same, base_data)["rsi"]
        assert not isinstance(res_tf, _RealignedIndicator), "kein Wrapper bei gleichem tf"
        a = np.asarray(res_tf.real)
        b = np.asarray(res_same.real)
        assert np.array_equal(a, b, equal_nan=True)

    def test_finer_tf_rejected(self, base_data):
        spec = {"rsi": {"indicator": "talib:RSI", "tf": "1min",
                        "close": "close", "timeperiod": 14}}
        with pytest.raises(ValueError, match="feiner"):
            build_indicators(spec, base_data)

    def test_tf_same_is_noop(self, base_data):
        # GEÄNDERT: expliziter Sentinel 'same' rechnet unveraendert auf dem Basis-Raster
        spec = {"rsi": {"indicator": "talib:RSI", "tf": "same",
                        "close": "close", "timeperiod": 14}}
        inst = build_indicators(spec, base_data)["rsi"]
        assert not isinstance(inst, _RealignedIndicator)
        assert inst.real.index.equals(base_data.wrapper.index)

    def test_missing_tf_raises(self, base_data):
        # GEÄNDERT: fehlender tf ist kein implizites "gleich" mehr, sondern ein Fehler
        spec = {"rsi": {"indicator": "talib:RSI",
                        "close": "close", "timeperiod": 14}}
        with pytest.raises(ValueError, match="fehlt"):
            build_indicators(spec, base_data)

    def test_base_tf_string_detects_noop_without_wrapper(self, base_data):
        """Objekt ohne .wrapper (z.B. Test-Wrapper): tf==base_tf via String -> kein Resample.

        Sichert den realen Pfad: gespeicherte Specs tragen oft tf==Basis-Timeframe, der
        frueher ignoriert wurde. Ohne ohlc_data.wrapper.freq muss der base_tf-String die
        No-Op-Erkennung tragen, sonst kracht .resample() auf einem Objekt ohne diese Methode.
        """
        class _MinimalOhlc:
            def __init__(self, data):
                self._data = data

            def get(self, key):
                return self._data.get(key)

        minimal = _MinimalOhlc(base_data)
        spec = {"rsi": {"indicator": "talib:RSI", "tf": "5min",
                        "close": "close", "timeperiod": 14}}
        # base_tf='5min' == spec-tf -> No-Op, kein .resample()/.wrapper noetig
        inst = build_indicators(spec, minimal, base_tf="5min")["rsi"]
        assert not isinstance(inst, _RealignedIndicator)
