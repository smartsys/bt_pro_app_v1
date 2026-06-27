"""Unit-Tests fuer user_data/strategies/generic/tf_resample.py.

Prueft die geteilte Per-Indikator-tf-Mechanik (Runner + Preview):
  - normalize_tf: leer / None / gleich Basis -> None; abweichend -> getrimmt
  - validate_tf: feiner als Basis -> ValueError; gleich/groeber/None-Basis -> ok
  - resampled_ohlc + realign_to_index: Multi-Combo-DataFrame ueberlebt tf->Basis (alle
    Param-Spalten), look-ahead-sicher; Basis->tf (Chaining) trifft exakt den tf-Index
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

from user_data.strategies.generic.tf_resample import (
    normalize_tf,
    realign_to_index,
    resampled_ohlc,
    tf_to_timedelta,
    validate_tf,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def base_data() -> vbt.Data:
    """5min-Basis-Daten (3 Tage, lueckenlos) als konfiguriertes vbt.Data."""
    idx = pd.date_range("2020-01-01", periods=3 * 24 * 12, freq="5min", tz="UTC")
    n = len(idx)
    rng = np.random.default_rng(7)
    close = pd.Series(100 + np.cumsum(rng.normal(0, 0.1, n)), index=idx, name="Close")
    df = pd.DataFrame({
        "Open": close.shift(1).fillna(close.iloc[0]),
        "High": close + 0.5,
        "Low": close - 0.5,
        "Close": close,
        "Volume": pd.Series(rng.uniform(1, 5, n), index=idx),
    })
    data = vbt.Data.from_data({"X": df})
    data.use_feature_config_of(vbt.BinanceData)
    return data


# ============================================================================
# normalize_tf
# ============================================================================

class TestNormalizeTf:
    def test_empty_string_to_none(self):
        assert normalize_tf("", "4h") is None
        assert normalize_tf("   ", "4h") is None

    def test_none_to_none(self):
        assert normalize_tf(None, "4h") is None

    def test_equal_to_base_to_none(self):
        assert normalize_tf("4h", "4h") is None
        assert normalize_tf("4H", "4h") is None  # case-insensitiv

    def test_different_returns_trimmed(self):
        assert normalize_tf(" 1d ", "4h") == "1d"

    def test_no_base_returns_value(self):
        assert normalize_tf("4h", None) == "4h"


# ============================================================================
# validate_tf
# ============================================================================

class TestValidateTf:
    def test_finer_than_base_raises(self):
        base = pd.Timedelta("4h")
        with pytest.raises(ValueError, match="feiner"):
            validate_tf("1h", base)

    def test_equal_ok(self):
        validate_tf("4h", pd.Timedelta("4h"))  # kein Fehler

    def test_coarser_ok(self):
        validate_tf("1d", pd.Timedelta("4h"))  # kein Fehler

    def test_none_base_skips(self):
        validate_tf("1min", None)  # kein Fehler

    def test_tf_to_timedelta_parses_common_strings(self):
        assert tf_to_timedelta("4h") == pd.Timedelta("4h")
        assert tf_to_timedelta("1d") == pd.Timedelta("1d")
        assert tf_to_timedelta("15min") == pd.Timedelta("15min")
        assert tf_to_timedelta("1w") == pd.Timedelta("7d")


# ============================================================================
# resampled_ohlc + realign_to_index
# ============================================================================

class TestResampleRealign:
    def test_multi_combo_dataframe_survives_realign(self, base_data):
        base_index = base_data.wrapper.index
        res = resampled_ohlc(base_data, "4h")
        # talib RSI mit zwei timeperiods -> DataFrame mit Param-MultiIndex
        rsi = vbt.talib("RSI").run(res.get("Close"), timeperiod=[7, 14], param_product=True)
        out = rsi.real
        assert isinstance(out, pd.DataFrame) and out.shape[1] == 2

        realigned = realign_to_index(out, base_index)
        assert isinstance(realigned, pd.DataFrame)
        assert realigned.shape[1] == 2, "beide Param-Spalten erhalten"
        assert len(realigned) == len(base_index), "auf Basis-Laenge realignt"
        assert list(realigned.columns.names) == list(out.columns.names)

    def test_realign_is_look_ahead_safe(self, base_data):
        base_index = base_data.wrapper.index
        res = resampled_ohlc(base_data, "4h")
        tf_index = res.wrapper.index
        rsi = vbt.talib("RSI").run(res.get("Close"), timeperiod=[14], param_product=True)
        out = rsi.real
        realigned = realign_to_index(out, base_index)

        out_col = out.iloc[:, 0] if isinstance(out, pd.DataFrame) else out
        re_col = realigned.iloc[:, 0] if isinstance(realigned, pd.DataFrame) else realigned

        # An jedem Basis-Bar darf nur ein bereits abgeschlossener tf-Wert anliegen.
        tf_freq = pd.Timedelta(res.wrapper.freq)
        tf_closes = tf_index + tf_freq
        for probe in (50, 200, 500, 800):
            ts = base_index[probe]
            valid = tf_index[tf_closes <= ts]
            expected = out_col.loc[valid[-1]] if len(valid) else np.nan
            got = re_col.iloc[probe]
            assert (np.isnan(got) and np.isnan(expected)) or abs(got - expected) < 1e-9

    def test_base_to_tf_hits_exact_index(self, base_data):
        """Chaining-Richtung: eine Basis-Serie auf den tf-Index bringen."""
        base_index = base_data.wrapper.index
        res = resampled_ohlc(base_data, "4h")
        tf_index = res.wrapper.index
        a_base = base_data.get("Close")  # Serie am Basis-Index
        a_on_tf = realign_to_index(a_base, tf_index)
        assert a_on_tf.index.equals(tf_index)
