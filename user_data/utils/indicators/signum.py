"""SIGNUM-Breakout-Bausteine — Pivot, Level und Range als getrennte Indikatoren.

Nachbau der Struktur, die der SIGNUM Trend Radar unter `indicators.bo` ausweist
(`resistance`, `support`, `resistanceLineStart`, `supportLineStart`, `breakoutDate`).
Die Parameter sind an 54 Referenzzeilen des Radars kalibriert, bei denen SIGNUM
selbst Binance als Kursquelle nennt:

- Die gemeldeten Niveaus sind ausnahmslos (54 von 54) Hochs bzw. Tiefs eines
  Pivots mit Lookback/Lookforward 3.
- Das Toleranzband um ein Niveau erreicht als Maximum exakt 5,00 Prozent.
- Ein Niveau wird vor dem Ausbruch von mindestens 2, meist genau 3 Pivots getestet.
- Das Suchfenster liegt bei rund 80 Balken, die Formation dauert 14 bis 72 Balken,
  die Range ist höchstens 29,5 Prozent hoch.

Nicht nachgebildet ist SIGNUMs Auswahlregel, welche von mehreren gleichzeitig
gültigen Formationen gemeldet wird — die geht aus den gelieferten Daten nicht
hervor. Hier gilt stattdessen eine eigene, bewusst gesetzte Regel: die engste
noch gültige Range (tiefster qualifizierter Deckel über dem höchsten
qualifizierten Boden).

**Kausalität:** Ein Pivot steht erst `right` Balken nach seinem Extrempunkt fest.
Alle Ausgaben dieser Bausteine gelten deshalb ab dem Bestätigungsbalken, nicht ab
dem Extrempunkt — im Chart beginnt eine Linie sichtbar `right` Kerzen rechts vom
Hoch. Das ist gewollt und kein Darstellungsfehler; ohne diese Verzögerung würde
der Backtest mit Wissen aus der Zukunft rechnen.

Der Ausbruch selbst hat hier bewusst keinen Code — er ist eine Regel:
    close > indicator:range:top UND close[1] <= indicator:range:top[1]
    UND indicator:range:valid > 0

`dwsSignumRange` liefert zusätzlich `breakout_age`: die Zahl der Balken seit dem
letzten Ausbruch nach oben (`close[t] > top[t]` UND `valid[t] > 0`, ohne die
Vorbalken-Bedingung der Regel oben). 0 am Ausbruchsbalken, danach je Balken +1,
bis der nächste Ausbruch den Zähler wieder auf 0 setzt. Vor dem ersten Ausbruch
NaN, danach lückenlos — auch wenn `valid` zwischendurch 0 ist.
"""

from typing import Tuple

import numpy as np
import vectorbtpro as vbt
from numba import njit


@njit(cache=True)
def _pivot_confirm_nb(high: np.ndarray, low: np.ndarray, left: int,
                      right: int) -> Tuple[np.ndarray, np.ndarray]:
    """Markiert je Balken den dort BESTÄTIGTEN Pivot-Wert.

    Ein Pivot am Index p wird erst bei p + right sichtbar. Das Ergebnis steht
    deshalb am Bestätigungsbalken, nicht am Extrempunkt.

    Args:
        high: High-Serie.
        low: Low-Serie.
        left: Balken links des Extrempunkts.
        right: Balken rechts des Extrempunkts (Bestätigungsverzögerung).

    Returns:
        Tuple (conf_high, conf_low) — je Balken der Wert des dort bestätigten
        Pivot-Hochs bzw. -Tiefs, sonst NaN.
    """
    n = len(high)
    conf_high = np.full(n, np.nan)
    conf_low = np.full(n, np.nan)
    for t in range(n):
        p = t - right
        if p < left:
            continue
        ist_hoch = True
        ist_tief = True
        for k in range(p - left, p + right + 1):
            if high[k] > high[p]:
                ist_hoch = False
            if low[k] < low[p]:
                ist_tief = False
            if not ist_hoch and not ist_tief:
                break
        if ist_hoch:
            conf_high[t] = high[p]
        if ist_tief:
            conf_low[t] = low[p]
    return conf_high, conf_low


@njit(cache=True)
def _step_and_age_nb(conf: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Führt bestätigte Pivot-Werte als Treppenlinie fort und zählt ihr Alter.

    Args:
        conf: Je Balken der dort bestätigte Pivot-Wert, sonst NaN.

    Returns:
        Tuple (level, age) — fortgeschriebener Wert und Balken seit seiner
        Bestätigung (0 am Bestätigungsbalken selbst), vor dem ersten Pivot NaN.
    """
    n = len(conf)
    level = np.full(n, np.nan)
    age = np.full(n, np.nan)
    aktuell = np.nan
    alter = -1.0
    for t in range(n):
        if not np.isnan(conf[t]):
            aktuell = conf[t]
            alter = 0.0
        elif alter >= 0.0:
            alter += 1.0
        if alter >= 0.0:
            level[t] = aktuell
            age[t] = alter
    return level, age


@njit(cache=True)
def _tested_levels_nb(conf_high: np.ndarray, conf_low: np.ndarray, ref: np.ndarray,
                      window: int, tolerance: float, min_tests: int
                      ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray,
                                 np.ndarray, np.ndarray]:
    """Sucht je Balken die mehrfach getesteten Pivot-Niveaus im Rückblickfenster.

    Ein Niveau qualifiziert sich, wenn im Fenster mindestens `min_tests` Pivots
    innerhalb des Toleranzbands um seinen Wert liegen. Aus den qualifizierten
    Niveaus wird die engste Klammer um den Referenzkurs gewählt: der tiefste
    Deckel über ihm und der höchste Boden unter ihm.

    Der Referenzkurs ist der Schlusskurs des VORBALKENS. Nur so bleibt das Niveau
    von der laufenden Kerze unberührt und ein Schlusskurs kann es überhaupt
    überschreiten — richtete man es am aktuellen Schlusskurs aus, läge der Deckel
    per Konstruktion immer über dem Kurs und ein Ausbruch wäre nie messbar.

    Args:
        conf_high: Je Balken bestätigter Pivot-Hoch-Wert, sonst NaN.
        conf_low: Je Balken bestätigter Pivot-Tief-Wert, sonst NaN.
        ref: Referenzkurs je Balken (Schlusskurs des Vorbalkens), sonst NaN.
        window: Länge des Rückblickfensters in Balken.
        tolerance: Halbe Bandbreite als Anteil, z.B. 0.05 für 5 Prozent.
        min_tests: Mindestzahl der Pivots im Band.

    Returns:
        Tuple (resistance, support, res_tests, sup_tests, res_start, sup_start) —
        Niveaus, Zahl ihrer Tests und Balkenindex des ältesten Tests im Band.
    """
    n = len(conf_high)
    resistance = np.full(n, np.nan)
    support = np.full(n, np.nan)
    res_tests = np.zeros(n)
    sup_tests = np.zeros(n)
    res_start = np.full(n, np.nan)
    sup_start = np.full(n, np.nan)

    for t in range(n):
        if np.isnan(ref[t]):
            continue
        von = t - window + 1
        if von < 0:
            von = 0
        # Deckel: tiefstes qualifiziertes Niveau auf oder über dem Referenzkurs
        bester = np.nan
        bester_tests = 0
        bester_start = np.nan
        for i in range(von, t + 1):
            if np.isnan(conf_high[i]):
                continue
            wert = conf_high[i]
            if wert < ref[t]:
                continue
            treffer = 0
            aeltester = np.nan
            for j in range(von, t + 1):
                if np.isnan(conf_high[j]):
                    continue
                if abs(conf_high[j] - wert) / wert <= tolerance:
                    treffer += 1
                    if np.isnan(aeltester):
                        aeltester = j
            if treffer >= min_tests and (np.isnan(bester) or wert < bester):
                bester = wert
                bester_tests = treffer
                bester_start = aeltester
        resistance[t] = bester
        res_tests[t] = bester_tests
        res_start[t] = bester_start

        # Boden: höchstes qualifiziertes Niveau auf oder unter dem Referenzkurs
        bester = np.nan
        bester_tests = 0
        bester_start = np.nan
        for i in range(von, t + 1):
            if np.isnan(conf_low[i]):
                continue
            wert = conf_low[i]
            if wert > ref[t]:
                continue
            treffer = 0
            aeltester = np.nan
            for j in range(von, t + 1):
                if np.isnan(conf_low[j]):
                    continue
                if abs(conf_low[j] - wert) / wert <= tolerance:
                    treffer += 1
                    if np.isnan(aeltester):
                        aeltester = j
            if treffer >= min_tests and (np.isnan(bester) or wert > bester):
                bester = wert
                bester_tests = treffer
                bester_start = aeltester
        support[t] = bester
        sup_tests[t] = bester_tests
        sup_start[t] = bester_start

    return resistance, support, res_tests, sup_tests, res_start, sup_start


def _ref_close(close) -> np.ndarray:
    """Schlusskurs des Vorbalkens als Referenzkurs — der erste Balken hat keinen."""
    close = np.asarray(close, dtype=np.float64)
    ref = np.full(len(close), np.nan)
    ref[1:] = close[:-1]
    return np.ascontiguousarray(ref)


def signum_pivot_inc(high, low, left: int = 3, right: int = 3):
    """Pivot-Hochs und -Tiefs als fortgeschriebene Treppenlinien.

    Die unterste Stufe der SIGNUM-Mechanik: Wo liegt das jeweils letzte
    bestätigte Pivot-Hoch bzw. -Tief, und wie alt ist es?

    Args:
        high: High-Serie.
        low: Low-Serie.
        left: Balken links des Extrempunkts (Vorgabe 3).
        right: Balken rechts des Extrempunkts (Vorgabe 3).

    Returns:
        Tuple (high_level, low_level, high_age, low_age) — letztes bestätigtes
        Pivot-Hoch/-Tief und dessen Alter in Balken.

    Raises:
        ValueError: Wenn left oder right kleiner als 1 ist.
    """
    left = int(left)
    right = int(right)
    if left < 1 or right < 1:
        raise ValueError(
            f'dwsSignumPivot: left und right müssen mindestens 1 sein, sind {left}/{right}')

    high = np.ascontiguousarray(np.asarray(high, dtype=np.float64))
    low = np.ascontiguousarray(np.asarray(low, dtype=np.float64))

    conf_high, conf_low = _pivot_confirm_nb(high, low, left, right)
    high_level, high_age = _step_and_age_nb(conf_high)
    low_level, low_age = _step_and_age_nb(conf_low)
    return high_level, low_level, high_age, low_age


def signum_level_inc(high, low, close, left: int = 3, right: int = 3, window: int = 80,
                     tolerance: float = 0.05, min_tests: int = 3):
    """Mehrfach getestete Kursniveaus aus Pivot-Punkten.

    Zweite Stufe: Nicht jedes Pivot-Hoch ist ein Widerstand — erst ein Niveau,
    das im Rückblickfenster mehrfach angelaufen wurde, zählt als solcher.

    Args:
        high: High-Serie.
        low: Low-Serie.
        close: Close-Serie; ihr Vorbalken-Wert klammert die beiden Niveaus ein.
        left: Balken links des Extrempunkts (Vorgabe 3).
        right: Balken rechts des Extrempunkts (Vorgabe 3).
        window: Rückblickfenster in Balken (Vorgabe 80).
        tolerance: Halbe Bandbreite als Anteil (Vorgabe 0.05 = 5 Prozent).
        min_tests: Mindestzahl der Pivots im Band (Vorgabe 3).

    Returns:
        Tuple (resistance, support, res_tests, sup_tests) — die beiden Niveaus
        und die Zahl der Pivots, die sie jeweils getestet haben.

    Raises:
        ValueError: Bei unbrauchbarem Fenster, Toleranz oder Testzahl.
    """
    left = int(left)
    right = int(right)
    window = int(window)
    min_tests = int(min_tests)
    tolerance = float(tolerance)
    if left < 1 or right < 1:
        raise ValueError(
            f'dwsSignumLevel: left und right müssen mindestens 1 sein, sind {left}/{right}')
    if window < 2:
        raise ValueError(f'dwsSignumLevel: window muss mindestens 2 sein, ist {window}')
    if not 0.0 < tolerance < 1.0:
        raise ValueError(
            f'dwsSignumLevel: tolerance muss zwischen 0 und 1 liegen, ist {tolerance}')
    if min_tests < 1:
        raise ValueError(f'dwsSignumLevel: min_tests muss mindestens 1 sein, ist {min_tests}')

    high = np.ascontiguousarray(np.asarray(high, dtype=np.float64))
    low = np.ascontiguousarray(np.asarray(low, dtype=np.float64))

    conf_high, conf_low = _pivot_confirm_nb(high, low, left, right)
    resistance, support, res_tests, sup_tests, _, _ = _tested_levels_nb(
        conf_high, conf_low, _ref_close(close), window, tolerance, min_tests)
    return resistance, support, res_tests, sup_tests


def _range_arrays(high, low, close, left: int, right: int, window: int, tolerance: float,
                  min_tests: int, max_height: float, min_duration: int):
    """Gemeinsame Rechnung für Range-Serien und Range-Zonen.

    Returns:
        Tuple (top, bottom, valid, height, duration, start_index, breakout_age)
        — start_index ist der Balkenindex des Formationsbeginns (NaN, wenn
        ungültig), breakout_age die Zahl der Balken seit dem letzten Ausbruch
        nach oben (`close[t] > top[t]` UND `valid[t] > 0`).
    """
    high = np.ascontiguousarray(np.asarray(high, dtype=np.float64))
    low = np.ascontiguousarray(np.asarray(low, dtype=np.float64))
    close_arr = np.ascontiguousarray(np.asarray(close, dtype=np.float64))

    conf_high, conf_low = _pivot_confirm_nb(high, low, left, right)
    resistance, support, _, _, res_start, sup_start = _tested_levels_nb(
        conf_high, conf_low, _ref_close(close), window, tolerance, min_tests)

    n = len(high)
    top = np.full(n, np.nan)
    bottom = np.full(n, np.nan)
    valid = np.zeros(n)
    height = np.full(n, np.nan)
    duration = np.full(n, np.nan)
    start_index = np.full(n, np.nan)

    for t in range(n):
        r, s = resistance[t], support[t]
        if np.isnan(r) or np.isnan(s) or r <= s:
            continue
        beginn = min(res_start[t], sup_start[t])
        if np.isnan(beginn):
            continue
        h = r / s - 1.0
        d = t - beginn
        top[t] = r
        bottom[t] = s
        height[t] = h
        duration[t] = d
        if h <= max_height and d >= min_duration:
            valid[t] = 1.0
            start_index[t] = beginn

    # Ausbruchsalter: Balken seit dem letzten Ausbruch nach oben. Eigener
    # Durchlauf, weil top/valid erst nach der Schleife oben feststehen —
    # top[t]/valid[t] hängen nur von Daten bis t ab, bleiben also kausal.
    breakout_age = np.full(n, np.nan)
    alter = -1.0
    for t in range(n):
        ausbruch = valid[t] > 0.0 and not np.isnan(close_arr[t]) and close_arr[t] > top[t]
        if ausbruch:
            alter = 0.0
        elif alter >= 0.0:
            alter += 1.0
        if alter >= 0.0:
            breakout_age[t] = alter

    return top, bottom, valid, height, duration, start_index, breakout_age


def signum_range_inc(high, low, close, left: int = 3, right: int = 3, window: int = 80,
                     tolerance: float = 0.05, min_tests: int = 3,
                     max_height: float = 0.30, min_duration: int = 14):
    """Die Konsolidierungs-Range aus Deckel und Boden.

    Dritte Stufe: Deckel und Boden spannen eine Range auf. Sie gilt erst als
    handelbare Formation, wenn sie nicht zu hoch ist und lange genug steht —
    beide Schwellen stammen aus den SIGNUM-Referenzdaten.

    Args:
        high: High-Serie.
        low: Low-Serie.
        close: Close-Serie; ihr Vorbalken-Wert klammert Deckel und Boden ein.
        left: Balken links des Extrempunkts (Vorgabe 3).
        right: Balken rechts des Extrempunkts (Vorgabe 3).
        window: Rückblickfenster in Balken (Vorgabe 80).
        tolerance: Halbe Bandbreite als Anteil (Vorgabe 0.05 = 5 Prozent).
        min_tests: Mindestzahl der Pivots im Band (Vorgabe 3).
        max_height: Größte zulässige Range-Höhe als Anteil (Vorgabe 0.30).
        min_duration: Mindestdauer der Formation in Balken (Vorgabe 14).

    Returns:
        Tuple (top, bottom, valid, height, duration, breakout_age) — Deckel,
        Boden, 1/0 für eine gültige Formation, Höhe als Anteil, Dauer in Balken
        und die Zahl der Balken seit dem letzten Ausbruch nach oben (NaN vor
        dem ersten Ausbruch, danach lückenlos).

    Raises:
        ValueError: Bei unbrauchbarer Höhe oder Dauer.
    """
    left = int(left)
    right = int(right)
    window = int(window)
    min_tests = int(min_tests)
    tolerance = float(tolerance)
    max_height = float(max_height)
    min_duration = int(min_duration)
    if left < 1 or right < 1:
        raise ValueError(
            f'dwsSignumRange: left und right müssen mindestens 1 sein, sind {left}/{right}')
    if window < 2:
        raise ValueError(f'dwsSignumRange: window muss mindestens 2 sein, ist {window}')
    if not 0.0 < tolerance < 1.0:
        raise ValueError(
            f'dwsSignumRange: tolerance muss zwischen 0 und 1 liegen, ist {tolerance}')
    if min_tests < 1:
        raise ValueError(f'dwsSignumRange: min_tests muss mindestens 1 sein, ist {min_tests}')
    if max_height <= 0.0:
        raise ValueError(f'dwsSignumRange: max_height muss größer als 0 sein, ist {max_height}')
    if min_duration < 1:
        raise ValueError(
            f'dwsSignumRange: min_duration muss mindestens 1 sein, ist {min_duration}')

    top, bottom, valid, height, duration, _, breakout_age = _range_arrays(
        high, low, close, left, right, window, tolerance, min_tests, max_height, min_duration)
    return top, bottom, valid, height, duration, breakout_age


def signum_range_zones(high, low, close, left: int = 3, right: int = 3, window: int = 80,
                       tolerance: float = 0.05, min_tests: int = 3,
                       max_height: float = 0.30, min_duration: int = 14) -> list:
    """Gültige Ranges als Zonen-Rechtecke für den Chart.

    Jede zusammenhängende Strecke, auf der dieselbe Formation gültig bleibt, wird
    zu einem Rechteck vom Formationsbeginn bis zum letzten Balken ihrer Gültigkeit.

    Args:
        high: High-Serie.
        low: Low-Serie.
        close: Close-Serie; ihr Vorbalken-Wert klammert Deckel und Boden ein.
        left: Balken links des Extrempunkts (Vorgabe 3).
        right: Balken rechts des Extrempunkts (Vorgabe 3).
        window: Rückblickfenster in Balken (Vorgabe 80).
        tolerance: Halbe Bandbreite als Anteil (Vorgabe 0.05 = 5 Prozent).
        min_tests: Mindestzahl der Pivots im Band (Vorgabe 3).
        max_height: Größte zulässige Range-Höhe als Anteil (Vorgabe 0.30).
        min_duration: Mindestdauer der Formation in Balken (Vorgabe 14).

    Returns:
        Liste von Dicts mit start_index, end_index, top, bottom und bullish.
    """
    top, bottom, valid, _, _, start_index, _ = _range_arrays(
        high, low, close, int(left), int(right), int(window), float(tolerance), int(min_tests),
        float(max_height), int(min_duration))

    zonen = []
    offen = None
    for t in range(len(top)):
        if valid[t] > 0.0:
            kennung = (start_index[t], top[t], bottom[t])
            if offen is None or offen['kennung'] != kennung:
                if offen is not None:
                    zonen.append(offen)
                offen = {
                    'kennung': kennung,
                    'start_index': int(start_index[t]),
                    'end_index': t,
                    'top': float(top[t]),
                    'bottom': float(bottom[t]),
                    'bullish': True,
                }
            else:
                offen['end_index'] = t
        elif offen is not None:
            zonen.append(offen)
            offen = None
    if offen is not None:
        zonen.append(offen)
    for z in zonen:
        z.pop('kennung')
    return zonen


# dwsSignumPivot — bestätigte Pivot-Hochs und -Tiefs als Treppenlinien.
# Preisskaliert (Overlay). Die Defaults hängen zusätzlich an with_apply_func,
# damit run() ohne explizite Parameter durchläuft.
dwsSignumPivot = vbt.IF(
    class_name='dwsSignumPivot',
    input_names=['high', 'low'],
    param_names=['left', 'right'],
    output_names=['high_level', 'low_level', 'high_age', 'low_age'],
).with_apply_func(
    signum_pivot_inc,
    takes_1d=True,
    left=3,
    right=3,
)


# dwsSignumLevel — mehrfach getestete Widerstands- und Unterstützungsniveaus.
# Preisskaliert (Overlay), res_tests/sup_tests sind Zähler und gehören in ein Subplot.
dwsSignumLevel = vbt.IF(
    class_name='dwsSignumLevel',
    input_names=['high', 'low', 'close'],
    param_names=['left', 'right', 'window', 'tolerance', 'min_tests'],
    output_names=['resistance', 'support', 'res_tests', 'sup_tests'],
).with_apply_func(
    signum_level_inc,
    takes_1d=True,
    left=3,
    right=3,
    window=80,
    tolerance=0.05,
    min_tests=3,
)


# dwsSignumRange — die Konsolidierungs-Range als handelbare Formation.
# Preisskaliert (Overlay); valid/height/duration/breakout_age sind Kennzahlen
# fürs Subplot. Beispiel-Regel „Ausbruch nach oben":
#   close > indicator:range:top UND close[1] <= indicator:range:top[1]
#   UND indicator:range:valid > 0
dwsSignumRange = vbt.IF(
    class_name='dwsSignumRange',
    input_names=['high', 'low', 'close'],
    param_names=['left', 'right', 'window', 'tolerance', 'min_tests',
                 'max_height', 'min_duration'],
    output_names=['top', 'bottom', 'valid', 'height', 'duration', 'breakout_age'],
).with_apply_func(
    signum_range_inc,
    takes_1d=True,
    left=3,
    right=3,
    window=80,
    tolerance=0.05,
    min_tests=3,
    max_height=0.30,
    min_duration=14,
)
