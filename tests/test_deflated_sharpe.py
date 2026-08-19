"""Tests für die eigene, korrigierte Deflated-Sharpe-Ratio-Rechnung (Ticket 54).

Geprüft wird:
- Eine feste, von Hand (mit scipy.stats.norm direkt, nicht über die getestete Funktion)
  nachgerechnete Eingabe liefert exakt den vorab notierten Wert.
- Der Sonderfall Schiefe=0 / rohe Wölbung=3 (Normalverteilung) zeigt, dass der Nenner
  `sqrt(1 + 0,5*SR^2)` ergibt — das ist der gezielte Test gegen Defekt 2 (Excess- statt
  roher Wölbung im VBT-Original).
- Der defekte Zusammenhang der alten Formel ist widerlegt: verschiedene
  Kandidaten-Sharpes bei festem var_sharpe/N/T ergeben verschiedene DSR-Werte, ein
  Kandidat mit hohem Sharpe übersteigt 0,5 (mit der alten Formel strukturell
  unmöglich, weil sich der Kandidat dort aus dem Zähler herauskürzte).
- Die beiden Randfälle aus Anforderung 7: N <= 1 (nicht definiert -> NaN) und
  var_sharpe = 0 (alle Kombinationen identisch -> SR0 = 0, kein Absturz).

Alle Erwartungswerte sind vorab per Python/scipy einmalig offline gerechnet und hier als
Literale mit Herleitung im Kommentar hinterlegt — sie entstehen nicht durch einen
zweiten Aufruf der getesteten Funktion.
"""

import warnings

import numpy as np
import pytest

from user_data.utils.metrics.deflated_sharpe import deflated_sharpe_ratio


def test_matches_hand_calculated_formula_for_fixed_input():
    """Feste Eingabe, Erwartungswert von Hand aus der Formel hergeleitet.

    sharpe = [0.5, 1.0, 1.5], skew = kurtosis = konstant, N = 3, T = 100.

    Herleitung (siehe Modul-Docstring für die Formel):
      var_sharpe = Stichprobenvarianz([0.5, 1.0, 1.5], ddof=1) = 0.25
      sr0 = sqrt(0.25) * ((1-gamma)*Phi^-1(1 - 1/3) + gamma*Phi^-1(1 - 1/(3*e)))
          = 0.42640224807534743
      denom_i = sqrt(1 - 0.2*SR_i + ((3.5-1)/4)*SR_i^2)
      num_i   = (SR_i - sr0) * sqrt(100 - 1)
      dsr_i   = Phi(num_i / denom_i)
    """
    sharpe = np.array([0.5, 1.0, 1.5])
    skew = np.array([0.2, 0.2, 0.2])
    kurtosis = np.array([3.5, 3.5, 3.5])

    result = deflated_sharpe_ratio(sharpe, skew, kurtosis, n=3, t=np.full(3, 100.0))

    expected = np.array([0.7619294608166983, 0.9999991278188296, 0.9999999999999084])
    assert result == pytest.approx(expected, abs=1e-9)


def test_denominator_uses_raw_kurtosis_not_excess():
    """Bei Schiefe=0 und roher Wölbung=3 (Normalverteilung) muss der Nenner
    `sqrt(1 + 0,5*SR^2)` ergeben — das ist Defekt 2 aus Ticket 54: VBT setzt dort
    fälschlich die Excess-Wölbung ein (Normalverteilung dort = 0 statt 3), was den
    Nenner strukturell verfälscht bzw. für realistische Eingaben negativ werden lassen
    kann. Der Test prüft das indirekt über den Endwert: würde die Funktion Excess-
    statt roher Wölbung erwarten, wichen die Ergebnisse von den hier hinterlegten,
    mit `sqrt(1 + 0,5*SR^2)` als Nenner gerechneten Werten ab.

    sharpe = [0.3, 0.8, 1.3], skew = 0, kurtosis = 3 (roh), N = 3, T = 50.

    Herleitung:
      var_sharpe = Stichprobenvarianz([0.3, 0.8, 1.3], ddof=1) = 0.25
      sr0 = 0.42640224807534743  (gleiche var_sharpe und N wie im ersten Test)
      denom_i = sqrt(1 - 0*SR_i + ((3-1)/4)*SR_i^2) = sqrt(1 + 0.5*SR_i^2)
      num_i   = (SR_i - sr0) * sqrt(50 - 1)
      dsr_i   = Phi(num_i / denom_i)
    """
    sharpe = np.array([0.3, 0.8, 1.3])
    skew = np.array([0.0, 0.0, 0.0])
    kurtosis_normal = np.array([3.0, 3.0, 3.0])

    result = deflated_sharpe_ratio(sharpe, skew, kurtosis_normal, n=3, t=np.full(3, 50.0))

    # Erwartungswerte oben mit Nenner sqrt(1 + 0.5*SR^2) hergeleitet (siehe Docstring) —
    # dieser Vergleich prüft direkt die Funktion, nicht nur die Nenner-Arithmetik.
    expected = np.array([0.19336710835057253, 0.9885837487324628, 0.9999966351149866])
    assert result == pytest.approx(expected, abs=1e-9)


def test_different_candidate_sharpes_yield_different_dsr_values():
    """Widerlegt den defekten Zusammenhang der alten Formel.

    In VBTs Original kürzt sich der bewertete Kandidat aus dem Zähler heraus
    (`sharpe_ratio - (sharpe_ratio + sqrt(var_sharpe)*(...))`), sodass alle
    Kombinationen bei festem var_sharpe/N/T rechnerisch denselben Abstand zum
    Nenner-Term hätten und das Ergebnis strukturell auf 0,5 gedeckelt bliebe. Die
    korrigierte Formel behält den Kandidaten im Zähler (`SR - SR0` statt
    `SR - (SR + SR0)`) — verschiedene Kandidaten müssen deshalb verschiedene DSR-Werte
    ergeben, und ein deutlich überdurchschnittlicher Kandidat muss über 0,5 kommen
    können.
    """
    # var_sharpe, N und T sind für alle Kandidaten gleich, weil sie aus demselben
    # Aufruf (derselben Rastergröße) stammen — nur SR unterscheidet sich je Kombination.
    sharpe = np.array([-1.0, 0.0, 0.3, 0.6, 1.0, 2.5])
    skew = np.zeros(6)
    kurtosis = np.full(6, 3.0)

    result = deflated_sharpe_ratio(sharpe, skew, kurtosis, n=6, t=np.full(6, 30.0))

    # Monoton steigend in SR (fixierter var_sharpe/N/T-Kontext) -> alle Werte sind
    # paarweise verschieden, das Ergebnis hängt vom Kandidaten ab.
    assert np.all(np.diff(result) > 0)
    # Der beste Kandidat (SR=2.5) übersteigt 0,5 - mit der alten Formel strukturell
    # unmöglich (dort war das Ergebnis durch norm.cdf(negativer_Wert) auf <=0,5 gedeckelt).
    assert result[-1] > 0.5
    # Der schlechteste Kandidat bleibt deutlich darunter.
    assert result[0] < 0.5


def test_var_sharpe_zero_yields_sr0_zero_without_special_case():
    """Randfall aus Anforderung 7: identische Sharpes über alle Kombinationen ergeben
    var_sharpe = 0 und damit SR0 = 0 - ohne Sonderbehandlung im Code (sqrt(0) ist
    definiert). Das Ergebnis bleibt eine reguläre Zahl, keine NaN, kein Absturz.

    sharpe = [0.7, 0.7, 0.7] (identisch), skew = 0.1, kurtosis = 4.0 (roh), N = 3, T = 100.

    Herleitung (SR0 angenommen exakt 0, da var_sharpe = 0):
      denom = sqrt(1 - 0.1*0.7 + ((4.0-1)/4)*0.7^2) = 1.1390785749894516
      num   = (0.7 - 0) * sqrt(100 - 1) = 6.965910...
      dsr   = Phi(num / denom) = 0.9999999995157421
    """
    sharpe = np.array([0.7, 0.7, 0.7])
    skew = np.array([0.1, 0.1, 0.1])
    kurtosis = np.array([4.0, 4.0, 4.0])

    result = deflated_sharpe_ratio(sharpe, skew, kurtosis, n=3, t=np.full(3, 100.0))

    assert not np.any(np.isnan(result))
    expected = np.full(3, 0.9999999995157421)
    assert result == pytest.approx(expected, abs=1e-9)


def test_n_less_equal_one_returns_nan():
    """N <= 1 bedeutet kein Mehrfachvergleich - die Kennzahl ist nicht definiert und
    muss NaN sein statt eines rechnerischen Artefakts (Phi^-1(1 - 1/1) = Phi^-1(0) = -inf).
    """
    sharpe = np.array([0.5, 0.8])
    skew = np.array([0.0, 0.0])
    kurtosis = np.array([3.0, 3.0])

    result = deflated_sharpe_ratio(sharpe, skew, kurtosis, n=1, t=np.full(2, 100.0))

    assert result.shape == sharpe.shape
    assert np.all(np.isnan(result))


def test_n_zero_returns_nan():
    """N = 0 (kein einziger Lauf) ist ebenfalls kein definierter Mehrfachvergleich."""
    sharpe = np.array([0.5])
    skew = np.array([0.0])
    kurtosis = np.array([3.0])

    result = deflated_sharpe_ratio(sharpe, skew, kurtosis, n=0, t=np.full(1, 100.0))

    assert np.all(np.isnan(result))


def test_denominator_zero_at_moment_equality_boundary_yields_defined_cdf_limit():
    """Grenzfall der Diskriminante: `kurt_roh = skew^2 + 1` (hier skew=2,0, kurt_roh=5,0)
    macht den Nenner-Radikand bei SR=1,0 exakt 0 — der Scheitel der quadratischen Form
    (siehe Kommentar an der Nenner-Zeile in `deflated_sharpe.py`). Gewähltes Verhalten:
    Division durch 0 wird zugelassen, `norm.cdf(+-inf)` liefert einen definierten
    Grenzwert (hier 1,0, da der Zähler an dieser Stelle positiv ist) statt NaN oder
    eines stillen Crashs.

    Aufbau: sharpe = [1.0, 1.0, 1.0] (identisch -> var_sharpe = 0 -> SR0 = 0), n=3,
    t=100 -> Zähler = (1.0 - 0) * sqrt(99) > 0, Nenner bei SR=1.0 mit skew=2.0/kurt=5.0
    exakt 0 -> Quotient +inf -> cdf(+inf) = 1.0.
    """
    sharpe = np.array([1.0, 1.0, 1.0])
    skew = np.array([2.0, 2.0, 2.0])
    kurtosis = np.array([5.0, 5.0, 5.0])

    with warnings.catch_warnings():
        # Beweist, dass keine unerklärte RuntimeWarning durchläuft (gezielt unterdrückt,
        # nicht versteckt) — jede andere Warnung ließe den Test bewusst durchfallen.
        warnings.simplefilter('error')
        result = deflated_sharpe_ratio(sharpe, skew, kurtosis, n=3, t=np.full(3, 100.0))

    assert result == pytest.approx(np.full(3, 1.0))


def test_denominator_stays_positive_for_extreme_calibration_moments():
    """Die Momente der Kalibrierungsläufe sind extrem (Schiefe zweistellig, rohe Wölbung
    dreistellig — Modul-Docstring). Diskriminante = skew^2 - (kurt_roh - 1) muss auch
    dort deutlich negativ bleiben, sonst würde der Nenner-Radikand doch negativ:

      skew=7.7,  kurt_roh=138.0 -> Diskriminante = 7.7^2 - 137.0  = -77.71
      skew=19.9, kurt_roh=563.0 -> Diskriminante = 19.9^2 - 562.0 = -165.99

    Beide sind (deutlich) negativ -> der Radikand bleibt positiv, das Ergebnis ist eine
    reguläre, endliche DSR statt NaN.
    """
    sharpe = np.array([0.05, 0.05])
    skew = np.array([7.7, 19.9])
    kurtosis = np.array([138.0, 563.0])

    result = deflated_sharpe_ratio(sharpe, skew, kurtosis, n=50, t=np.full(2, 500.0))

    assert np.all(np.isfinite(result))
