"""Tests für die SIGNUM-Breakout-Bausteine dwsSignumPivot / dwsSignumLevel / dwsSignumRange.

Geprüft wird:
  - Pivots erscheinen erst am Bestätigungsbalken (kein Blick in die Zukunft)
  - das Alter eines Pivots zählt ab seiner Bestätigung
  - ein Niveau qualifiziert sich erst ab `min_tests` Treffern im Toleranzband
  - das Toleranzband greift an seiner Kante
  - Deckel und Boden klammern den Vorbalken-Schlusskurs ein
  - eine Range gilt nur bei zulässiger Höhe und erreichter Mindestdauer
  - die Zonen-Ausgabe beschreibt dieselbe Formation wie die Serien
  - unbrauchbare Parameter werden abgewiesen
"""

import sys
from pathlib import Path

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from user_data.utils.indicators.signum import (
    signum_level_inc,
    signum_pivot_inc,
    signum_range_inc,
    signum_range_zones,
)


@pytest.fixture
def zacken() -> tuple:
    """Kursreihe mit drei gleich hohen Spitzen auf 110 und drei Tälern auf 90.

    Aufbau je Zacke: sieben Balken, in der Mitte die Spitze. Damit ist jede Spitze
    ein sauberes Pivot(3,3) und alle drei liegen exakt auf demselben Niveau.
    """
    muster = [100.0, 102.0, 105.0, 110.0, 105.0, 102.0, 100.0]
    tal = [100.0, 98.0, 95.0, 90.0, 95.0, 98.0, 100.0]
    reihe = []
    for _ in range(3):
        reihe.extend(muster)
        reihe.extend(tal)
    high = np.array(reihe, dtype=np.float64)
    low = high - 5.0
    close = high - 2.5
    return high, low, close


def test_pivot_erscheint_erst_am_bestaetigungsbalken(zacken):
    """Ein Pivot(3,3) darf frühestens drei Balken nach seinem Hochpunkt sichtbar sein."""
    high, low, _ = zacken
    high_level, _, high_age, _ = signum_pivot_inc(high, low, left=3, right=3)

    spitze = 3                      # Index des ersten Hochs (110)
    bestaetigung = spitze + 3

    assert np.all(np.isnan(high_level[:bestaetigung])), (
        'Vor dem Bestätigungsbalken darf kein Pivot-Niveau stehen — sonst rechnet '
        'der Backtest mit Wissen aus der Zukunft.')
    assert high_level[bestaetigung] == pytest.approx(110.0)
    assert high_age[bestaetigung] == pytest.approx(0.0)


def test_pivot_alter_zaehlt_ab_bestaetigung(zacken):
    """Das Alter wächst je Balken um eins, bis ein neuer Pivot bestätigt wird."""
    high, low, _ = zacken
    _, _, high_age, _ = signum_pivot_inc(high, low, left=3, right=3)

    bestaetigung = 6
    assert high_age[bestaetigung] == pytest.approx(0.0)
    assert high_age[bestaetigung + 1] == pytest.approx(1.0)
    assert high_age[bestaetigung + 2] == pytest.approx(2.0)


def test_pivot_haelt_niveau_bis_zum_naechsten_pivot(zacken):
    """Zwischen zwei Pivots bleibt das zuletzt bestätigte Niveau stehen."""
    high, low, _ = zacken
    high_level, low_level, _, _ = signum_pivot_inc(high, low, left=3, right=3)

    gesetzt = high_level[~np.isnan(high_level)]
    assert np.all(gesetzt == pytest.approx(110.0))
    tiefs = low_level[~np.isnan(low_level)]
    assert np.all(tiefs == pytest.approx(85.0))     # low = high - 5, Tal-Hoch 90


def test_level_braucht_mindestzahl_an_tests(zacken):
    """Mit min_tests=3 qualifiziert sich das Niveau erst ab der dritten Spitze."""
    high, low, close = zacken

    _, _, tests_drei, _ = signum_level_inc(
        high, low, close, left=3, right=3, window=80, tolerance=0.05, min_tests=3)
    _, _, tests_vier, _ = signum_level_inc(
        high, low, close, left=3, right=3, window=80, tolerance=0.05, min_tests=4)

    assert tests_drei.max() >= 3.0, 'drei gleich hohe Spitzen müssen ein Niveau tragen'
    assert tests_vier.max() == 0.0, 'bei vier geforderten Tests gibt es kein Niveau'


def test_level_toleranzband_greift_an_der_kante():
    """Ein zweites Hoch knapp innerhalb des Bands zählt als Test, knapp außerhalb nicht.

    Die Flanken liegen bewusst tief: Senkt man nur die Mittelspitze ab, werden die
    Flanken selbst zu Pivots und verfälschen die Zählung.
    """
    def reihe(zweite_spitze: float) -> tuple:
        erste = [80.0, 85.0, 95.0, 110.0, 95.0, 85.0, 80.0]
        zweite = [80.0, 85.0, 95.0, zweite_spitze, 95.0, 85.0, 80.0]
        high = np.array(erste + zweite, dtype=np.float64)
        return high, high - 5.0, high - 2.5

    # 104.5 liegt exakt 5,0 Prozent unter 110 — gerade noch im Band
    high, low, close = reihe(104.5)
    _, _, tests_innen, _ = signum_level_inc(
        high, low, close, left=3, right=3, window=80, tolerance=0.05, min_tests=2)

    # 100.5 liegt rund 8,6 Prozent darunter — außerhalb
    high, low, close = reihe(100.5)
    _, _, tests_aussen, _ = signum_level_inc(
        high, low, close, left=3, right=3, window=80, tolerance=0.05, min_tests=2)

    assert tests_innen.max() >= 2.0, 'ein Hoch an der Bandkante muss als Test zählen'
    assert tests_aussen.max() == 0.0, 'jenseits des Bands trägt das Niveau nicht'


def test_level_klammert_den_vorbalken_schlusskurs_ein(zacken):
    """Der Deckel liegt nie unter, der Boden nie über dem Schlusskurs des Vorbalkens."""
    high, low, close = zacken
    resistance, support, _, _ = signum_level_inc(
        high, low, close, left=3, right=3, window=80, tolerance=0.05, min_tests=2)

    ref = np.full(len(close), np.nan)
    ref[1:] = close[:-1]

    hat_deckel = ~np.isnan(resistance)
    assert np.all(resistance[hat_deckel] >= ref[hat_deckel])
    hat_boden = ~np.isnan(support)
    assert np.all(support[hat_boden] <= ref[hat_boden])


def test_range_verwirft_zu_hohe_formation(zacken):
    """Überschreitet die Range die zulässige Höhe, ist sie ungültig."""
    high, low, close = zacken

    _, _, valid_weit, hoehe, _ = signum_range_inc(
        high, low, close, left=3, right=3, window=80, tolerance=0.05, min_tests=2,
        max_height=0.30, min_duration=1)
    _, _, valid_eng, _, _ = signum_range_inc(
        high, low, close, left=3, right=3, window=80, tolerance=0.05, min_tests=2,
        max_height=0.01, min_duration=1)

    assert valid_weit.max() == 1.0, 'die Formation passt in ein 30-Prozent-Fenster'
    gemessen = hoehe[~np.isnan(hoehe)]
    assert gemessen.max() > 0.01
    assert valid_eng.max() == 0.0, 'bei 1 Prozent Höhengrenze bleibt nichts übrig'


def test_range_verwirft_zu_kurze_formation(zacken):
    """Vor Erreichen der Mindestdauer ist die Formation ungültig."""
    high, low, close = zacken

    _, _, valid, _, dauer = signum_range_inc(
        high, low, close, left=3, right=3, window=80, tolerance=0.05, min_tests=2,
        max_height=0.30, min_duration=1)
    _, _, valid_lang, _, _ = signum_range_inc(
        high, low, close, left=3, right=3, window=80, tolerance=0.05, min_tests=2,
        max_height=0.30, min_duration=500)

    assert valid.max() == 1.0
    assert valid_lang.max() == 0.0, 'eine 500-Balken-Mindestdauer kann die Reihe nicht erfüllen'
    gemessen = dauer[~np.isnan(dauer)]
    assert np.all(gemessen >= 0.0)


def test_range_zonen_passen_zu_den_serien(zacken):
    """Jede Zone trägt Deckel und Boden der Formation und liegt in der Reihe."""
    high, low, close = zacken
    top, bottom, valid, _, _ = signum_range_inc(
        high, low, close, left=3, right=3, window=80, tolerance=0.05, min_tests=2,
        max_height=0.30, min_duration=1)
    zonen = signum_range_zones(
        high, low, close, left=3, right=3, window=80, tolerance=0.05, min_tests=2,
        max_height=0.30, min_duration=1)

    assert zonen, 'zu einer gültigen Formation muss es auch eine Zone geben'
    for z in zonen:
        assert 0 <= z['start_index'] <= z['end_index'] < len(high)
        assert z['top'] > z['bottom']
        assert valid[z['end_index']] == 1.0
        assert top[z['end_index']] == pytest.approx(z['top'])
        assert bottom[z['end_index']] == pytest.approx(z['bottom'])


def test_ausbruch_ist_erster_schlusskurs_ueber_dem_deckel():
    """Steigt der Schlusskurs über den Deckel, ist genau dieser Balken der Ausbruch."""
    muster = [100.0, 102.0, 105.0, 110.0, 105.0, 102.0, 100.0]
    high = np.array(muster * 3 + [112.0, 115.0, 118.0, 120.0], dtype=np.float64)
    low = high - 5.0
    close = high - 2.5

    top, _, valid, _, _ = signum_range_inc(
        high, low, close, left=3, right=3, window=80, tolerance=0.05, min_tests=2,
        max_height=0.30, min_duration=1)

    ausbrueche = [
        t for t in range(1, len(close))
        if valid[t] and not np.isnan(top[t]) and not np.isnan(top[t - 1])
        and close[t] > top[t] and close[t - 1] <= top[t - 1]
    ]
    assert ausbrueche, 'der Anstieg über die dreifach getestete 110 muss ein Ausbruch sein'
    for t in ausbrueche:
        assert close[t] > top[t]
        assert close[t - 1] <= top[t - 1]


@pytest.mark.parametrize('kwargs, text', [
    ({'left': 0}, 'left und right'),
    ({'right': 0}, 'left und right'),
    ({'window': 1}, 'window'),
    ({'tolerance': 0.0}, 'tolerance'),
    ({'tolerance': 1.5}, 'tolerance'),
    ({'min_tests': 0}, 'min_tests'),
])
def test_level_weist_unbrauchbare_parameter_ab(zacken, kwargs, text):
    """Unbrauchbare Parameter scheitern sichtbar statt still zu rechnen."""
    high, low, close = zacken
    with pytest.raises(ValueError, match=text):
        signum_level_inc(high, low, close, **kwargs)


@pytest.mark.parametrize('kwargs, text', [
    ({'max_height': 0.0}, 'max_height'),
    ({'min_duration': 0}, 'min_duration'),
])
def test_range_weist_unbrauchbare_parameter_ab(zacken, kwargs, text):
    """Auch Höhe und Dauer werden geprüft, bevor gerechnet wird."""
    high, low, close = zacken
    with pytest.raises(ValueError, match=text):
        signum_range_inc(high, low, close, **kwargs)


def test_pivot_weist_unbrauchbare_parameter_ab(zacken):
    """left und right müssen mindestens 1 sein."""
    high, low, _ = zacken
    with pytest.raises(ValueError, match='left und right'):
        signum_pivot_inc(high, low, left=0, right=3)
