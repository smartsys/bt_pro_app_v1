"""Tests für die exit-freie Entry-Bewertung (MFE/MAE, First-Touch-Geometrie).

Arbeitet auf synthetischen OHLC-Serien mit von Hand nachgerechneten Erwartungswerten —
keine VBT- oder DB-Abhängigkeit.
"""

import numpy as np
import pandas as pd
import pytest

from user_data.utils.analysis.entry_quality import (
    OUTCOME_OPEN,
    OUTCOME_SL,
    OUTCOME_TP,
    baseline_positions,
    bootstrap_lift,
    excursions,
    first_touch,
    first_touch_entries,
    forward_paths,
    geometry_grid,
    geometry_stats,
    signal_positions,
    summarize_excursions,
)


@pytest.fixture
def index():
    """Zeitindex mit 10 Balken im 4h-Raster."""
    return pd.date_range('2020-01-01', periods=10, freq='4h', tz='UTC')


@pytest.fixture
def ohlc(index):
    """OHLC mit bekanntem Verlauf: Close konstant 100, High/Low von Hand gesetzt."""
    close = pd.Series(100.0, index=index)
    high = pd.Series([100.0, 110.0, 105.0, 102.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0], index=index)
    low = pd.Series([100.0, 99.0, 95.0, 90.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0], index=index)
    return high, low, close


def test_first_touch_entries_reduziert_serie_auf_uebertritt(index):
    """Eine zusammenhängende Signalserie wird auf ihren ersten Balken reduziert."""
    mask = pd.Series([False, True, True, True, False, False, True, True, False, False], index=index)
    result = first_touch_entries(mask)
    expected = pd.Series([False, True, False, False, False, False, True, False, False, False], index=index)
    pd.testing.assert_series_equal(result, expected)


def test_first_touch_entries_signal_auf_erstem_balken(index):
    """Ein Signal direkt auf dem ersten Balken gilt als Übertritt."""
    mask = pd.Series([True] + [False] * 9, index=index)
    assert bool(first_touch_entries(mask).iloc[0]) is True


def test_signal_positions_verwirft_signale_ohne_volles_fenster(index):
    """Signale in den letzten `horizon` Balken haben kein volles Fenster und fallen raus."""
    mask = pd.Series([False] * 10, index=index)
    mask.iloc[0] = True   # Fenster passt
    mask.iloc[6] = True   # Fenster passt gerade noch (6+3 = 9, letzter Index)
    mask.iloc[7] = True   # Fenster ragt über das Ende hinaus
    result = signal_positions(mask, horizon=3)
    np.testing.assert_array_equal(result, np.array([0, 6]))


def test_signal_positions_lehnt_horizont_null_ab(index):
    """Ein Horizont unter einem Balken ist keine gültige Messung."""
    mask = pd.Series([True] + [False] * 9, index=index)
    with pytest.raises(ValueError):
        signal_positions(mask, horizon=0)


def test_forward_paths_startet_erst_nach_dem_signalbalken(ohlc):
    """Der Signalbalken selbst ist zum Fill-Zeitpunkt gelaufen und darf nicht zählen.

    Signal auf Balken 0 (Close 100), Horizont 3 → Balken 1..3.
    High 110/105/102 → +10 / +5 / +2 Prozent; Low 99/95/90 → -1 / -5 / -10 Prozent.
    Der High von Balken 0 selbst taucht nicht auf.
    """
    high, low, close = ohlc
    positions = np.array([0])
    high_path, low_path = forward_paths(high, low, close, positions, horizon=3)

    np.testing.assert_allclose(high_path[0], [0.10, 0.05, 0.02])
    np.testing.assert_allclose(low_path[0], [-0.01, -0.05, -0.10])


def test_excursions_liefert_maximum_und_minimum(ohlc):
    """MFE ist das Maximum der High-Renditen, MAE das Minimum der Low-Renditen."""
    high, low, close = ohlc
    high_path, low_path = forward_paths(high, low, close, np.array([0]), horizon=3)
    mfe, mae = excursions(high_path, low_path)

    np.testing.assert_allclose(mfe, [0.10])
    np.testing.assert_allclose(mae, [-0.10])


def test_excursions_ohne_signale_liefert_leere_arrays():
    """Keine Signale ist ein gültiger Zustand, kein Fehler."""
    empty = np.empty((0, 3))
    mfe, mae = excursions(empty, empty)
    assert len(mfe) == 0 and len(mae) == 0


def test_first_touch_erkennt_ziel_vor_stop():
    """Ziel wird auf Balken 0 erreicht, Stop erst auf Balken 2 → Ziel gewinnt."""
    high_path = np.array([[0.05, 0.00, 0.00]])
    low_path = np.array([[0.00, 0.00, -0.20]])
    assert first_touch(high_path, low_path, tp=0.02, sl=0.15)[0] == OUTCOME_TP


def test_first_touch_erkennt_stop_vor_ziel():
    """Stop wird auf Balken 0 erreicht, Ziel erst auf Balken 2 → Stop gewinnt."""
    high_path = np.array([[0.00, 0.00, 0.05]])
    low_path = np.array([[-0.20, 0.00, 0.00]])
    assert first_touch(high_path, low_path, tp=0.02, sl=0.15)[0] == OUTCOME_SL


def test_first_touch_balken_kollision_zaehlt_als_stop():
    """Ziel und Stop im selben Balken: Die Reihenfolge ist unbekannt, der Stop gewinnt.

    Das ist die konservative Regel — sie darf nicht still zum Ziel kippen, sonst
    wird die erreichbare Win-Rate systematisch zu gut ausgewiesen.
    """
    high_path = np.array([[0.05]])
    low_path = np.array([[-0.20]])
    assert first_touch(high_path, low_path, tp=0.02, sl=0.15)[0] == OUTCOME_SL


def test_first_touch_ohne_treffer_bleibt_offen():
    """Wird im Horizont weder Ziel noch Stop erreicht, ist der Trade offen."""
    high_path = np.array([[0.01, 0.01]])
    low_path = np.array([[-0.01, -0.01]])
    assert first_touch(high_path, low_path, tp=0.02, sl=0.15)[0] == OUTCOME_OPEN


def test_first_touch_lehnt_negative_schwellen_ab():
    """tp und sl sind als positive Faktoren definiert — ein Vorzeichenfehler muss knallen."""
    high_path = np.array([[0.05]])
    low_path = np.array([[-0.05]])
    with pytest.raises(ValueError):
        first_touch(high_path, low_path, tp=0.02, sl=-0.15)


def test_geometry_stats_rechnet_win_rate_und_erwartungswert():
    """Zwei Ziel-Treffer, ein Stop, ein offener Trade — von Hand nachgerechnet.

    TP 0.10, SL 0.20, fees 0.001 → Gebühren 0.002 je Trade.
    Renditen: 0.10, 0.10, -0.20, 0.00 (offen ohne open_return)
    minus 0.002 → 0.098, 0.098, -0.202, -0.002 → Mittel = -0.002.
    """
    outcome = np.array([OUTCOME_TP, OUTCOME_TP, OUTCOME_SL, OUTCOME_OPEN])
    stats = geometry_stats(outcome, tp=0.10, sl=0.20, fees=0.001)

    assert stats['n'] == 4
    assert stats['win_rate'] == pytest.approx(0.5)
    # Unter den entschiedenen Trades (der offene zählt hier nicht mit): 2 von 3
    assert stats['win_rate_decided'] == pytest.approx(2 / 3)
    assert stats['share_open'] == pytest.approx(0.25)
    assert stats['expectancy'] == pytest.approx(-0.002)


def test_geometry_stats_bewertet_offene_trades_ueber_open_return():
    """Offene Trades werden am Fensterende bewertet (entspricht einem Zeitstopp)."""
    outcome = np.array([OUTCOME_OPEN, OUTCOME_OPEN])
    open_return = np.array([0.05, -0.03])
    stats = geometry_stats(outcome, tp=0.10, sl=0.20, fees=0.0, open_return=open_return)

    assert stats['expectancy'] == pytest.approx(0.01)


def test_geometry_grid_deckt_alle_paare_ab():
    """Das Gitter liefert eine Zeile je (tp, sl)-Kombination."""
    high_path = np.array([[0.03, 0.01], [0.00, 0.00]])
    low_path = np.array([[0.00, 0.00], [-0.05, -0.20]])
    grid = geometry_grid(high_path, low_path, tp_values=[0.02, 0.05], sl_values=[0.03, 0.15])

    assert len(grid) == 4
    assert set(grid.columns) >= {'tp', 'sl', 'win_rate', 'expectancy'}


def test_excursion_asymmetry_ist_null_bei_symmetrie():
    """Gleich weit hoch wie runter heisst keine Kante."""
    from user_data.utils.analysis.entry_quality import excursion_asymmetry
    result = excursion_asymmetry(np.array([0.10]), np.array([-0.10]))
    assert result[0] == pytest.approx(0.0)


def test_excursion_asymmetry_ist_skalenfrei():
    """Der Kern der Methodik: Volatilität allein darf die Kennzahl nicht bewegen.

    Ein Signal mit MFE 0.10 / MAE -0.05 und eines mit MFE 0.20 / MAE -0.10 stehen in
    exakt derselben Asymmetrie — das zweite sitzt nur in einem doppelt so volatilen
    Markt. Genau diese Verwechslung würde ein reiner MFE-Vergleich als Kante ausweisen.
    """
    from user_data.utils.analysis.entry_quality import excursion_asymmetry
    ruhig = excursion_asymmetry(np.array([0.10]), np.array([-0.05]))
    wild = excursion_asymmetry(np.array([0.20]), np.array([-0.10]))
    assert ruhig[0] == pytest.approx(wild[0])
    assert ruhig[0] == pytest.approx(1 / 3)


def test_excursion_asymmetry_negativ_bei_uebergewicht_nach_unten():
    """Läuft der Kurs weiter runter als hoch, ist die Asymmetrie negativ."""
    from user_data.utils.analysis.entry_quality import excursion_asymmetry
    result = excursion_asymmetry(np.array([0.05]), np.array([-0.15]))
    assert result[0] == pytest.approx(-0.5)


def test_excursion_asymmetry_bewegungsloses_signal_ergibt_null():
    """Ein Signal ohne jede Bewegung darf keine Division durch null auslösen."""
    from user_data.utils.analysis.entry_quality import excursion_asymmetry
    result = excursion_asymmetry(np.array([0.0]), np.array([0.0]))
    assert result[0] == pytest.approx(0.0)


def test_summarize_excursions_enthaelt_asymmetrie():
    """Die Asymmetrie gehört in die Standard-Verdichtung, nicht als Extra-Aufruf."""
    stats = summarize_excursions(np.array([0.10, 0.20]), np.array([-0.05, -0.10]))
    assert stats['asym_median'] == pytest.approx(1 / 3)


def test_summarize_excursions_edge_ratio():
    """Edge-Ratio ist mittlere MFE geteilt durch mittlere absolute MAE."""
    mfe = np.array([0.10, 0.20])
    mae = np.array([-0.05, -0.05])
    stats = summarize_excursions(mfe, mae)

    assert stats['n'] == 2
    assert stats['edge_ratio'] == pytest.approx(0.15 / 0.05)
    assert stats['mfe_median'] == pytest.approx(0.15)


def test_summarize_excursions_ohne_signale():
    """Keine Signale liefert n=0 statt einer Division durch null."""
    assert summarize_excursions(np.empty(0), np.empty(0)) == {'n': 0}


def test_baseline_positions_laesst_kein_abgeschnittenes_fenster_zu():
    """Das Null-Modell nutzt jeden Balken, dessen Vorwärtsfenster vollständig ist."""
    result = baseline_positions(n_bars=10, horizon=3)
    np.testing.assert_array_equal(result, np.arange(0, 7))


def test_bootstrap_lift_erkennt_wert_ueber_dem_band():
    """Ein Wert weit über dem Null-Modell landet über dem 95-Prozent-Band."""
    baseline_values = np.random.default_rng(0).normal(0.0, 0.01, size=5000)
    result = bootstrap_lift(baseline_values, n_signals=100, observed=0.05, n_rounds=200)

    assert result['above_baseline_band'] is True
    assert result['percentile'] == pytest.approx(1.0)


def test_bootstrap_lift_erkennt_wert_im_rauschen():
    """Ein Wert mitten im Null-Modell ist nicht signifikant — genau der Fall, den die Studie treffen muss."""
    baseline_values = np.random.default_rng(0).normal(0.02, 0.01, size=5000)
    result = bootstrap_lift(baseline_values, n_signals=100, observed=0.02, n_rounds=200)

    assert result['above_baseline_band'] is False
    assert 0.2 < result['percentile'] < 0.8


def test_bootstrap_lift_ist_reproduzierbar():
    """Gleicher Seed, gleiches Ergebnis — sonst ist die Studie nicht nachvollziehbar."""
    baseline_values = np.random.default_rng(0).normal(0.0, 0.01, size=1000)
    first = bootstrap_lift(baseline_values, n_signals=50, observed=0.01, n_rounds=100, seed=7)
    second = bootstrap_lift(baseline_values, n_signals=50, observed=0.01, n_rounds=100, seed=7)

    assert first == second
