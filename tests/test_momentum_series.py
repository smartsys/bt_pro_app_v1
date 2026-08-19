"""Tests für die Momentum-Reihe (Positivkontrolle des Permutationstests, Ticket 80).

Sichert die Zusagen des Moduls `user_data/utils/analysis/momentum_series.py` ab:

1. OHLC-Konsistenz je Balken (High >= max(O, C) >= min(O, C) >= Low)
2. Index, Spalten und Dtypes der Vorlage bleiben erhalten
3. Driftfreiheit: die Summe der erzeugten Log-Renditen ist exakt null
4. Determinismus je Seed; verschiedene Seeds -> verschiedene Reihen
5. Der eingebaute Vorteil ist **Reihenfolge** und nichts sonst: Die Trendstärke erzeugt
   Autokorrelation, und die Bar-Permutation des Nullmodells nimmt sie wieder weg,
   während die Randverteilung erhalten bleibt. Genau darauf beruht die Positivkontrolle
   — und genau darin unterscheidet sie sich von der Orakel-Falle aus Ticket 79.
"""

import numpy as np
import pandas as pd
import pytest

from user_data.utils.analysis.momentum_series import (
    CONTROL_SYMBOLS,
    CONTROL_TREND_STRENGTH,
    make_momentum_frame,
)
from user_data.utils.analysis.synthetic_series import bar_log_returns, permute_frame


def _template(n: int = 3000, freq: str = '4h') -> pd.DataFrame:
    """Vorlage mit dem Spalten-Layout der HDF5-Quelle (inkl. Integer-Spalte)."""
    index = pd.date_range('2020-01-01', periods=n, freq=freq, tz='UTC')
    frame = pd.DataFrame(
        {
            'Open': np.linspace(10.0, 20.0, n),
            'High': np.linspace(11.0, 21.0, n),
            'Low': np.linspace(9.0, 19.0, n),
            'Close': np.linspace(10.5, 20.5, n),
            'Volume': np.linspace(100.0, 200.0, n),
            'Trade count': np.arange(n),
        },
        index=index,
    )
    return frame.astype({'Trade count': 'int64'})


def _variance_ratio(frame: pd.DataFrame, span: int = 50) -> float:
    """Varianzverhältnis der Log-Renditen über `span` Balken.

    Ohne zeitliche Struktur wächst die Varianz linear mit dem Horizont, das
    Verhältnis liegt also bei 1. Momentum lässt sie schneller wachsen (> 1). Das ist
    der belastbare Nachweis der eingebauten Reihenfolge: Die Trendkomponente ist
    langsam (rho = 0,99) und verteilt sich über viele Lags, die Autokorrelation bei
    Lag 1 allein ist dafür zu verrauscht.
    """
    returns = bar_log_returns(frame)
    usable = len(returns) // span * span
    aggregated = returns[:usable].reshape(-1, span).sum(axis=1)
    return float(aggregated.var(ddof=1) / (span * returns.var(ddof=1)))


def test_ohlc_consistency_per_bar():
    frame = make_momentum_frame(_template(), seed=1, trend_strength=CONTROL_TREND_STRENGTH)
    body_top = np.maximum(frame['Open'].to_numpy(), frame['Close'].to_numpy())
    body_bottom = np.minimum(frame['Open'].to_numpy(), frame['Close'].to_numpy())
    assert (frame['High'].to_numpy() >= body_top).all()
    assert (frame['Low'].to_numpy() <= body_bottom).all()
    assert (frame[['Open', 'High', 'Low', 'Close', 'Volume']].to_numpy() > 0).all()


def test_layout_of_template_is_kept():
    template = _template()
    frame = make_momentum_frame(template, seed=2, trend_strength=CONTROL_TREND_STRENGTH)
    assert frame.index.equals(template.index)
    assert list(frame.columns) == list(template.columns)
    assert frame.dtypes.to_dict() == template.dtypes.to_dict()


def test_generated_log_returns_sum_to_zero():
    """Driftfrei: sonst verdiente ein Long-Kandidat auch auf der permutierten Reihe."""
    frame = make_momentum_frame(_template(), seed=3, trend_strength=CONTROL_TREND_STRENGTH)
    close = frame['Close'].to_numpy(dtype=float)
    generated = np.diff(np.log(np.concatenate([[100.0], close])))
    assert generated.sum() == pytest.approx(0.0, abs=1e-9)


def test_same_seed_is_deterministic_and_other_seed_differs():
    template = _template()
    first = make_momentum_frame(template, seed=7, trend_strength=CONTROL_TREND_STRENGTH)
    again = make_momentum_frame(template, seed=7, trend_strength=CONTROL_TREND_STRENGTH)
    other = make_momentum_frame(template, seed=8, trend_strength=CONTROL_TREND_STRENGTH)
    pd.testing.assert_frame_equal(first, again)
    assert not np.allclose(first['Close'].to_numpy(), other['Close'].to_numpy())


@pytest.mark.parametrize('seed', [1, 5, 9, 42])
def test_trend_strength_creates_momentum(seed):
    template = _template()
    flat = make_momentum_frame(template, seed=seed, trend_strength=0.0)
    trending = make_momentum_frame(template, seed=seed, trend_strength=CONTROL_TREND_STRENGTH)
    assert _variance_ratio(flat) < 1.5
    assert _variance_ratio(trending) > 1.6
    assert _variance_ratio(trending) > _variance_ratio(flat)


@pytest.mark.parametrize('seed', [1, 5, 9, 42])
def test_permutation_removes_the_advantage_but_keeps_the_distribution(seed):
    """Der Kern der Positivkontrolle: der Vorteil ist NICHT permutations-invariant."""
    frame = make_momentum_frame(_template(), seed=seed, trend_strength=CONTROL_TREND_STRENGTH)
    permuted = permute_frame(frame, seed=4242)
    assert _variance_ratio(frame) > 1.6
    assert _variance_ratio(permuted) < 1.4
    # Randverteilung unverändert — die Zahlen wechseln nur den Platz.
    np.testing.assert_allclose(
        np.sort(bar_log_returns(frame)), np.sort(bar_log_returns(permuted)),
        rtol=1e-7, atol=1e-12,
    )


def test_invalid_parameters_are_rejected():
    template = _template(n=100)
    with pytest.raises(ValueError):
        make_momentum_frame(template, seed=1, trend_strength=-0.1)
    with pytest.raises(ValueError):
        make_momentum_frame(template, seed=1, trend_strength=0.2, rho=1.0)


def test_control_symbols_cover_flat_and_momentum():
    """Die vorregistrierte Symbol-Tabelle: Gegenprobe, Staffel und Kontrolle."""
    strengths = {strength for _, strength in CONTROL_SYMBOLS.values()}
    assert 0.0 in strengths
    assert CONTROL_TREND_STRENGTH in strengths
    control = [name for name, (_, s) in CONTROL_SYMBOLS.items() if s == CONTROL_TREND_STRENGTH]
    assert len(control) >= 3, 'Die Positivkontrolle braucht mindestens 3 Daten-Seeds.'
