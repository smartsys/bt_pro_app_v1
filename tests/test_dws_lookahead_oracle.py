"""Tests für den Custom-Indikator dwsLookaheadOracle (Zukunfts-Einstieg, Positivkontrolle).

Geprüft werden die definierenden Eigenschaften: `skill=0` reproduziert dwsRandomEntry
bit-genau, `skill=1` feuert exakt dann, wenn die Zukunftsbedingung zutrifft, das Ergebnis
ist über den Seed deterministisch, die letzten `lookahead` Balken haben kein Zukunftsfenster
und liefern sauber kein Signal, und jeder Parameter ist als Sweep-Achse nutzbar.
Synthetische Daten, keine Abhängigkeit von OHLCV-Dateien.
"""
import numpy as np
import pandas as pd
import pytest

from user_data.utils.indicators.custom import dwsLookaheadOracle, dwsRandomEntry


@pytest.fixture
def price_series() -> pd.Series:
    """Ansteigende Preisreihe mit Schwingung — Standard-Eingabe der Tests."""
    idx = pd.date_range("2024-01-01", periods=2000, freq="4h")
    values = 100 + np.linspace(0, 50, 2000) + np.sin(np.linspace(0, 60, 2000)) * 5
    return pd.Series(values, index=idx, name="close")


def _oracle(
    source: pd.Series,
    seed: int = 1,
    prob: float = 0.05,
    skill: float = 0.0,
    lookahead: int = 6,
    threshold: float = 0.0,
) -> np.ndarray:
    result = dwsLookaheadOracle.run(
        source, seed=seed, prob=prob, skill=skill, lookahead=lookahead, threshold=threshold
    ).result
    return np.asarray(result).ravel()


def test_zero_skill_reproduces_random_entry(price_series: pd.Series) -> None:
    """Ohne Zukunftsanteil ist das Signal bit-genau das der Negativkontrolle."""
    for seed in (1, 7, 42):
        oracle = _oracle(price_series, seed=seed, prob=0.03, skill=0.0)
        reference = np.asarray(
            dwsRandomEntry.run(price_series, seed=seed, prob=0.03).result
        ).ravel()
        assert np.array_equal(oracle, reference)


def test_full_skill_matches_future_condition(price_series: pd.Series) -> None:
    """Bei skill=1 feuert das Signal genau dann, wenn die Zukunftsbedingung zutrifft."""
    lookahead = 6
    threshold = 0.01
    signal = _oracle(price_series, seed=5, skill=1.0, lookahead=lookahead, threshold=threshold)

    values = price_series.to_numpy()
    expected = np.zeros(len(values), dtype=float)
    expected[: len(values) - lookahead] = (
        values[lookahead:] > values[: len(values) - lookahead] * (1.0 + threshold)
    ).astype(float)
    assert np.array_equal(signal, expected)


def test_full_skill_ignores_seed(price_series: pd.Series) -> None:
    """Ein perfektes Orakel hängt nicht mehr vom Zufall ab — alle Seeds sind gleich."""
    first = _oracle(price_series, seed=1, skill=1.0, threshold=0.01)
    second = _oracle(price_series, seed=999, skill=1.0, threshold=0.01)
    assert np.array_equal(first, second)


def test_same_seed_is_deterministic(price_series: pd.Series) -> None:
    """Zweimal derselbe Seed liefert bei teilweisem Zukunftsanteil dasselbe Signal."""
    first = _oracle(price_series, seed=42, skill=0.3, threshold=0.01)
    second = _oracle(price_series, seed=42, skill=0.3, threshold=0.01)
    assert np.array_equal(first, second)


def test_different_seeds_differ_at_partial_skill(price_series: pd.Series) -> None:
    """Bei teilweisem Zukunftsanteil streuen die Seeds — Voraussetzung für die Sharpe-Varianz."""
    first = _oracle(price_series, seed=1, skill=0.3, threshold=0.01)
    second = _oracle(price_series, seed=2, skill=0.3, threshold=0.01)
    assert not np.array_equal(first, second)


def test_last_bars_without_future_window_stay_silent(price_series: pd.Series) -> None:
    """Die letzten `lookahead` Balken haben kein Zukunftsfenster: kein Signal, kein NaN."""
    lookahead = 10
    signal = _oracle(price_series, seed=3, skill=1.0, lookahead=lookahead, threshold=-1.0)
    assert not np.isnan(signal).any()
    assert signal[-lookahead:].sum() == 0.0
    # Gegenprobe: mit threshold=-1.0 feuert jeder Balken MIT Fenster (Preise sind positiv).
    assert signal[: len(signal) - lookahead].all()


def test_nan_in_future_window_produces_no_signal(price_series: pd.Series) -> None:
    """Eine Lücke in der Reihe erzeugt kein Signal und leckt keinen NaN durch."""
    gapped = price_series.copy()
    gapped.iloc[100:110] = np.nan
    signal = _oracle(gapped, seed=3, skill=1.0, lookahead=5, threshold=-1.0)
    assert not np.isnan(signal).any()
    assert set(np.unique(signal)).issubset({0.0, 1.0})
    # Balken 95..109 schauen in die Lücke oder liegen selbst darin -> kein Signal.
    assert signal[95:110].sum() == 0.0


def test_signal_values_are_binary(price_series: pd.Series) -> None:
    """Das Ergebnis besteht ausschließlich aus 0.0 und 1.0 — keine NaN, kein Warmup."""
    signal = _oracle(price_series, seed=3, skill=0.5, threshold=0.01)
    assert len(signal) == len(price_series)
    assert set(np.unique(signal)).issubset({0.0, 1.0})


def test_threshold_controls_oracle_frequency(price_series: pd.Series) -> None:
    """Ein höherer Schwellwert macht das Zukunftssignal seltener."""
    loose = _oracle(price_series, seed=1, skill=1.0, threshold=0.0).sum()
    strict = _oracle(price_series, seed=1, skill=1.0, threshold=0.05).sum()
    assert strict < loose


def test_runs_without_explicit_params(price_series: pd.Series) -> None:
    """Ohne Parameter-Angabe greifen die Factory-Defaults (skill=0 -> reiner Zufall)."""
    default_run = np.asarray(dwsLookaheadOracle.run(price_series).result).ravel()
    reference = np.asarray(dwsRandomEntry.run(price_series, seed=1, prob=0.05).result).ravel()
    assert np.array_equal(default_run, reference)


@pytest.mark.parametrize(
    "param_name, values",
    [
        ("seed", [1, 2, 3]),
        ("prob", [0.02, 0.05, 0.10]),
        ("skill", [0.0, 0.5, 1.0]),
        ("lookahead", [3, 6, 12]),
        ("threshold", [0.0, 0.05, 0.10]),
    ],
)
def test_every_param_is_sweepable(
    price_series: pd.Series, param_name: str, values: list
) -> None:
    """Jeder Parameter erzeugt als Liste eigene Spalten — Voraussetzung für den Sweep."""
    kwargs = {"seed": 4, "prob": 0.05, "skill": 0.5, "lookahead": 6, "threshold": 0.01}
    kwargs[param_name] = values
    result = dwsLookaheadOracle.run(price_series, **kwargs).result
    assert result.shape[1] == len(values)
    columns = np.asarray(result)
    assert not np.array_equal(columns[:, 0], columns[:, -1])
