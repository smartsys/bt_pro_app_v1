"""Tests der Rechenkerne des Signifikanztests (Ticket 79).

Reine Numerik, kein DB- und kein vectorbtpro-Bezug. Abgesichert wird:

* p-Wert mit Plus-eins-Korrektur — kein p = 0, kleinster Wert 1/(N+1)
* Zählrichtung: gezählt wird ``synthetisch >= echt`` (einseitig „so gut oder besser")
* Läufe ohne Trades werden mitgezählt und als Anteil ausgewiesen, nicht verworfen
* Bootstrap: deterministisch je Seed, klare Fehlermeldung ohne Trades, und der
  Bootstrap-Anteil heißt ausdrücklich nicht p-Wert
"""

import math

import numpy as np
import pytest

from user_data.utils.analysis.significance import (
    DEFAULT_PERMUTATION_METRICS,
    bootstrap_trade_returns,
    build_permutation_summary,
    null_distribution_summary,
    permutation_p_value,
    profit_factor,
)


# ---------------------------------------------------------------------------
# p-Wert: Plus-eins-Korrektur
# ---------------------------------------------------------------------------

def test_p_value_never_reaches_zero_even_when_no_synthetic_run_matches():
    """Schlägt kein synthetischer Lauf den echten Wert, ist p = 1/(N+1), nicht 0."""
    null_values = [0.1] * 100
    outcome = permutation_p_value(real_value=5.0, null_values=null_values)
    assert outcome['n_ge_real'] == 0
    assert outcome['p_value'] == pytest.approx(1 / 101)
    assert outcome['p_value'] > 0.0


def test_p_value_is_one_when_every_synthetic_run_matches_or_beats():
    """Erreichen alle N synthetischen Läufe den echten Wert, ist p = (N+1)/(N+1) = 1."""
    outcome = permutation_p_value(real_value=1.0, null_values=[1.0] * 49)
    assert outcome['n_ge_real'] == 49
    assert outcome['p_value'] == pytest.approx(1.0)


def test_p_value_counts_synthetic_values_greater_or_equal_to_real():
    """Die Zählrichtung ist `>=`: Gleichstand zählt als Treffer, kleinere Werte nicht."""
    null_values = [0.5, 1.0, 1.5, 2.0]
    outcome = permutation_p_value(real_value=1.0, null_values=null_values)
    assert outcome['n_ge_real'] == 3, 'gezählt werden 1.0, 1.5 und 2.0'
    assert outcome['p_value'] == pytest.approx(4 / 5)


def test_p_value_keeps_n_when_synthetic_values_are_not_finite():
    """NaN-Läufe (kein Trade) verkleinern N nicht und zählen nicht als Treffer."""
    null_values = [0.2, float('nan'), None, 0.3]
    outcome = permutation_p_value(real_value=1.0, null_values=null_values)
    assert outcome['n_iterations'] == 4, 'N bleibt die Zahl der gerechneten Läufe'
    assert outcome['n_non_finite'] == 2
    assert outcome['n_ge_real'] == 0
    assert outcome['p_value'] == pytest.approx(1 / 5)


def test_p_value_missing_with_reason_when_real_value_is_not_finite():
    """Ohne endlichen echten Wert gibt es keinen p-Wert — mit genanntem Grund."""
    outcome = permutation_p_value(real_value=float('nan'), null_values=[0.1, 0.2])
    assert outcome['p_value'] is None
    assert outcome['p_value_missing_reason']
    assert outcome['real_value'] is None


def test_p_value_requires_a_non_empty_null_distribution():
    """Eine leere Null-Verteilung bricht sichtbar ab statt still p = 1 zu liefern."""
    with pytest.raises(ValueError, match='Null-Verteilung ist leer'):
        permutation_p_value(real_value=1.0, null_values=[])


# ---------------------------------------------------------------------------
# Kennwerte der Null-Verteilung
# ---------------------------------------------------------------------------

def test_null_distribution_summary_reports_expected_key_figures():
    """mean/median/p05/p95/max stimmen mit der direkten numpy-Rechnung überein."""
    values = list(np.linspace(-1.0, 3.0, 41))
    summary = null_distribution_summary(values)
    assert summary['mean'] == pytest.approx(float(np.mean(values)))
    assert summary['median'] == pytest.approx(float(np.median(values)))
    assert summary['p05'] == pytest.approx(float(np.quantile(values, 0.05)))
    assert summary['p95'] == pytest.approx(float(np.quantile(values, 0.95)))
    assert summary['max'] == pytest.approx(3.0)
    assert summary['n_total'] == 41 and summary['n_finite'] == 41


def test_null_distribution_summary_separates_total_from_finite_count():
    """Nicht-endliche Werte fließen nicht in die Kennwerte, bleiben aber gezählt."""
    summary = null_distribution_summary([1.0, float('inf'), None, 3.0])
    assert summary['n_total'] == 4
    assert summary['n_finite'] == 2
    assert summary['mean'] == pytest.approx(2.0)


def test_null_distribution_summary_without_any_finite_value():
    """Ohne einen einzigen endlichen Wert bleiben die Kennwerte None, nicht 0."""
    summary = null_distribution_summary([None, float('nan')])
    assert summary['mean'] is None and summary['max'] is None
    assert summary['n_finite'] == 0


# ---------------------------------------------------------------------------
# Zusammenfassung: p-Wert nie ohne Null-Verteilung, No-Trade-Anteil
# ---------------------------------------------------------------------------

def test_summary_pairs_every_p_value_with_its_null_distribution():
    """Strukturell: jeder p-Wert steht im selben Objekt wie seine Verteilungs-Kennwerte."""
    summary = build_permutation_summary(
        real_values={'sharpe_ratio': 2.0, 'profit_factor': 1.8},
        distributions={'sharpe_ratio': [0.1, 0.2, 0.3], 'profit_factor': [1.0, 1.1, 2.0]},
        n_no_trade_runs=0,
        n_runs=3,
    )
    for metric in ('sharpe_ratio', 'profit_factor'):
        entry = summary['metrics'][metric]
        assert entry['p_value'] is not None
        assert entry['null_distribution']['median'] is not None


def test_summary_reports_share_of_runs_without_trades():
    """Der No-Trade-Anteil wird ausgewiesen, die Läufe bleiben in N enthalten."""
    summary = build_permutation_summary(
        real_values={'sharpe_ratio': 1.0},
        distributions={'sharpe_ratio': [0.1, None, None, 0.4]},
        n_no_trade_runs=2,
        n_runs=4,
    )
    assert summary['no_trade_runs']['count'] == 2
    assert summary['no_trade_runs']['share'] == pytest.approx(0.5)
    assert summary['metrics']['sharpe_ratio']['n_iterations'] == 4


def test_summary_rejects_metric_without_distribution():
    """Ein echter Wert ohne Null-Verteilung bricht ab — kein p-Wert ohne Verteilung."""
    with pytest.raises(ValueError, match='keine Null-Verteilung'):
        build_permutation_summary(
            real_values={'sharpe_ratio': 1.0},
            distributions={},
            n_no_trade_runs=0,
            n_runs=1,
        )


def test_default_metric_selection_covers_the_three_reported_figures():
    """Die Standard-Auswahl ist Sharpe, Profitfaktor und Gesamtrendite."""
    assert DEFAULT_PERMUTATION_METRICS == (
        'sharpe_ratio', 'profit_factor', 'total_return_pct',
    )


# ---------------------------------------------------------------------------
# Profitfaktor-Formel (von vbt übernommen)
# ---------------------------------------------------------------------------

def test_profit_factor_matches_vbt_reduction():
    """Summe der Gewinne / Summe der Betragsverluste, wie profit_factor_reduce_nb."""
    assert profit_factor([2.0, -1.0, 3.0, -4.0]) == pytest.approx(5.0 / 5.0)
    assert profit_factor([1.0, 2.0]) == math.inf, 'ohne Verlust: inf'
    assert math.isnan(profit_factor([]))
    assert profit_factor([1.0, float('nan'), -0.5]) == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def _sample_returns() -> list:
    """Eine gemischte Trade-Rendite-Menge in Prozent."""
    rng = np.random.default_rng(7)
    return list(rng.normal(0.4, 2.0, size=120))


def test_bootstrap_is_deterministic_per_seed():
    """Gleicher Seed liefert bitgleiche Bänder, ein anderer Seed andere."""
    returns = _sample_returns()
    first = bootstrap_trade_returns(returns, n_rounds=200, seed=42)
    second = bootstrap_trade_returns(returns, n_rounds=200, seed=42)
    other = bootstrap_trade_returns(returns, n_rounds=200, seed=43)
    assert first['bands'] == second['bands']
    assert first['share_pf_le_one'] == second['share_pf_le_one']
    assert first['bands']['mean_return_pct'] != other['bands']['mean_return_pct']


def test_bootstrap_band_brackets_the_observed_value():
    """Das p05/p95-Band schließt den beobachteten Mittelwert ein."""
    returns = _sample_returns()
    outcome = bootstrap_trade_returns(returns, n_rounds=500, seed=11)
    band = outcome['bands']['mean_return_pct']
    observed = outcome['observed']['mean_return_pct']
    assert band['p05'] <= observed <= band['p95']
    assert outcome['n_trades'] == len(returns)


def test_bootstrap_share_is_named_as_share_and_not_as_p_value():
    """Der Anteil der Resamples mit PF <= 1 ist ausdrücklich kein p-Wert."""
    outcome = bootstrap_trade_returns(_sample_returns(), n_rounds=200, seed=5)
    assert 'p_value' not in outcome
    assert 0.0 <= outcome['share_pf_le_one'] <= 1.0
    assert 'KEIN p-Wert' in outcome['share_pf_le_one_note']
    assert 'return_pct' in outcome['profit_factor_basis']


def test_bootstrap_without_trades_names_the_recompute_path():
    """Ohne Trades bricht der Bootstrap ab und nennt den Recompute-Weg."""
    with pytest.raises(ValueError) as excinfo:
        bootstrap_trade_returns([], n_rounds=100, seed=1)
    message = str(excinfo.value)
    assert 'backtest_result_trades' in message
    assert 'Recompute' in message


def test_bootstrap_rejects_non_positive_round_count():
    """n_rounds unter 1 bricht ab statt still nichts zu rechnen."""
    with pytest.raises(ValueError, match='n_rounds'):
        bootstrap_trade_returns([1.0, -1.0], n_rounds=0, seed=1)


def test_bootstrap_handles_all_winning_trades_without_crashing():
    """Ohne Verlust-Trade ist der Profitfaktor unendlich — das Band bleibt lesbar."""
    outcome = bootstrap_trade_returns([1.0, 2.0, 3.0], n_rounds=50, seed=3)
    assert outcome['observed']['profit_factor'] == math.inf
    assert outcome['bands']['profit_factor']['n_non_finite'] == 50
    assert outcome['share_pf_le_one'] is None, 'ohne endliche Ziehung kein Anteil'
