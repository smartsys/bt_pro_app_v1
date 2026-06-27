"""Tests für den Custom-Indikator dwsSMI (Stochastic Momentum Index, Blau).

Synthetische, deterministische Daten — keine Abhängigkeit von OHLCV-Dateien.
Geprüft werden Skala (~+-100), Richtungs-Verhalten (überkauft im Aufwärts-,
überverkauft im Abwärtstrend) und sauberer Warmup.
"""
import numpy as np
import pandas as pd
import pytest

from user_data.utils.indicators.custom import dwsSMI


def _ohlc_from_close(close: np.ndarray) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(close), freq="4h")
    return pd.DataFrame(
        {"High": close * 1.002, "Low": close * 0.998, "Close": close},
        index=idx,
    )


def _run(df: pd.DataFrame):
    return dwsSMI.run(
        df["High"], df["Low"], df["Close"],
        k_length=10, smooth1=3, smooth2=3, signal=3,
    )


def test_output_shapes():
    df = _ohlc_from_close(100 + np.sin(np.linspace(0, 20, 300)) * 10)
    ind = _run(df)
    for out in (ind.smi, ind.signal):
        assert len(np.asarray(out).ravel()) == len(df)


def test_scale_bounded():
    """SMI bleibt grob im Band [-120, 120] (Skala ~+-100)."""
    df = _ohlc_from_close(100 + np.sin(np.linspace(0, 40, 500)) * 15)
    smi = np.asarray(_run(df).smi).ravel()
    finite = smi[~np.isnan(smi)]
    assert finite.size > 0
    assert finite.min() >= -120.0
    assert finite.max() <= 120.0


def test_uptrend_is_overbought():
    """Monotoner Aufwärtstrend -> Close stets am Range-Hoch -> SMI deutlich positiv."""
    df = _ohlc_from_close(np.linspace(100, 200, 300))
    smi = np.asarray(_run(df).smi).ravel()
    tail = smi[~np.isnan(smi)][-50:]
    assert np.median(tail) > 40.0


def test_downtrend_is_oversold():
    """Monotoner Abwärtstrend -> Close stets am Range-Tief -> SMI deutlich negativ."""
    df = _ohlc_from_close(np.linspace(200, 100, 300))
    smi = np.asarray(_run(df).smi).ravel()
    tail = smi[~np.isnan(smi)][-50:]
    assert np.median(tail) < -40.0


def test_warmup_then_finite():
    """Nach dem Warmup keine NaN-Brüche mehr."""
    df = _ohlc_from_close(100 + np.cos(np.linspace(0, 30, 400)) * 8)
    smi = np.asarray(_run(df).smi).ravel()
    assert np.all(~np.isnan(smi[80:]))
