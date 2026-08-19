"""Tests für den Custom-Indikator dwsRandomEntry (Zufalls-Einstieg, Negativkontrolle).

Geprüft wird die definierende Eigenschaft des Bausteins: das Signal ist deterministisch
über den Seed reproduzierbar, unterscheidet sich zwischen Seeds, trifft die vorgegebene
Signalrate und ist vollständig unabhängig von den Werten der übergebenen Preisreihe.
Synthetische Daten, keine Abhängigkeit von OHLCV-Dateien.
"""
import numpy as np
import pandas as pd
import pytest

from user_data.utils.indicators.custom import dwsRandomEntry


@pytest.fixture
def price_series() -> pd.Series:
    """Ansteigende Preisreihe mit Schwingung — Standard-Eingabe der Tests."""
    idx = pd.date_range("2024-01-01", periods=2000, freq="4h")
    values = 100 + np.linspace(0, 50, 2000) + np.sin(np.linspace(0, 60, 2000)) * 5
    return pd.Series(values, index=idx, name="close")


@pytest.fixture
def other_price_series(price_series: pd.Series) -> pd.Series:
    """Völlig andere Preisreihe, gleicher Index und gleiche Länge."""
    values = 7000 - np.linspace(0, 3000, len(price_series))
    return pd.Series(values, index=price_series.index, name="close")


def _signal(source: pd.Series, seed: int, prob: float = 0.05) -> np.ndarray:
    return np.asarray(dwsRandomEntry.run(source, seed=seed, prob=prob).result).ravel()


def test_same_seed_is_deterministic(price_series: pd.Series) -> None:
    """Zweimal derselbe Seed liefert bit-genau dasselbe Signal."""
    first = _signal(price_series, seed=42)
    second = _signal(price_series, seed=42)
    assert np.array_equal(first, second)


def test_different_seeds_differ(price_series: pd.Series) -> None:
    """Verschiedene Seeds liefern verschiedene Signale."""
    first = _signal(price_series, seed=1)
    second = _signal(price_series, seed=2)
    assert not np.array_equal(first, second)


def test_signal_rate_matches_prob(price_series: pd.Series) -> None:
    """Die tatsächliche Signalrate trifft `prob` im Rahmen des Stichprobenfehlers.

    Toleranz: vier Standardfehler der Binomialverteilung — bei n=2000 und prob=0.05
    rund 1,95 Prozentpunkte. Der Seed ist fest, der Test damit nicht flatterig.
    """
    prob = 0.05
    signal = _signal(price_series, seed=7, prob=prob)
    rate = float(signal.mean())
    tolerance = 4.0 * np.sqrt(prob * (1.0 - prob) / len(signal))
    assert abs(rate - prob) < tolerance


def test_signal_values_are_binary(price_series: pd.Series) -> None:
    """Das Ergebnis besteht ausschließlich aus 0.0 und 1.0 — keine NaN, kein Warmup."""
    signal = _signal(price_series, seed=3)
    assert len(signal) == len(price_series)
    assert set(np.unique(signal)).issubset({0.0, 1.0})


def test_independent_of_price_values(
    price_series: pd.Series, other_price_series: pd.Series
) -> None:
    """Zwei völlig verschiedene Preisreihen ergeben bei gleichem Seed dasselbe Signal."""
    assert not np.allclose(price_series.to_numpy(), other_price_series.to_numpy())
    from_price = _signal(price_series, seed=99)
    from_other = _signal(other_price_series, seed=99)
    assert np.array_equal(from_price, from_other)


def test_prob_controls_frequency(price_series: pd.Series) -> None:
    """Höheres `prob` erzeugt bei gleichem Seed mehr Signale."""
    sparse = _signal(price_series, seed=11, prob=0.02).sum()
    dense = _signal(price_series, seed=11, prob=0.20).sum()
    assert dense > sparse


def test_runs_without_explicit_params(price_series: pd.Series) -> None:
    """Ohne Parameter-Angabe greifen die Factory-Defaults (seed=1, prob=0.05)."""
    default_run = np.asarray(dwsRandomEntry.run(price_series).result).ravel()
    explicit = _signal(price_series, seed=1, prob=0.05)
    assert np.array_equal(default_run, explicit)


def test_seed_is_sweepable_as_param_axis(price_series: pd.Series) -> None:
    """Eine Seed-Liste erzeugt mehrere Spalten — Voraussetzung für den Sweep."""
    result = dwsRandomEntry.run(price_series, seed=[1, 2, 3], prob=0.05).result
    assert result.shape[1] == 3
    columns = np.asarray(result)
    assert not np.array_equal(columns[:, 0], columns[:, 1])
