"""Deflated Sharpe Ratio (DSR) nach Bailey/López de Prado — korrigierte Eigenrechnung.

Reine Rechenlogik auf numpy/scipy — keine FastAPI-, DB- oder VBT-Abhängigkeit, damit
sie eigenständig testbar bleibt und aus jedem Worker-Kontext heraus aufrufbar ist
(Ticket 54). VBTs `ReturnsAccessor.deflated_sharpe_ratio` wird nicht mehr verwendet:
ihr Quelltext enthält zwei Formelfehler (siehe unten) und ist zudem je Block/Spalte
verdrahtet, obwohl die DSR eine rasterweite Kennzahl ist. Der VBT-Quelltext selbst
wird nicht angefasst — er ist eine installierte Fremdbibliothek.

Korrigierte Formel (Ticket 54, Anforderung 1):

    SR0 = sqrt(var_sharpe) * ((1-γ)·Φ⁻¹(1 - 1/N) + γ·Φ⁻¹(1 - 1/(N·e)))
    DSR = Φ( (SR - SR0)·sqrt(T-1) / sqrt(1 - skew·SR + ((kurt_roh - 1)/4)·SR²) )

mit `γ` = Euler-Mascheroni-Konstante und `var_sharpe = nanvar(SR über alle N
Kombinationen, ddof=1)`. Gegenüber VBTs Quelltext sind zwei Fehler behoben:

1. VBT addiert im Zähler fälschlich `sharpe_ratio +` vor `SR0`. Dadurch kürzt sich der
   bewertete Kandidat aus `sharpe_ratio - SR0` heraus, und das Ergebnis ist unabhängig
   vom Kandidaten strukturell auf 0,5 gedeckelt. Hier steht korrekt nur `SR0` im
   Abzug — ohne führendes `sharpe_ratio +`.
2. VBT setzt im Nenner die **Excess**-Wölbung ein (`scipy_stats.kurtosis()` liefert per
   Default `fisher=True`), obwohl die Formel die **rohe** Wölbung erwartet
   (Normalverteilung ≈ 3, nicht ≈ 0). Diese Funktion erwartet deshalb ausdrücklich die
   **rohe** Wölbung als `kurtosis`-Parameter (`scipy.stats.kurtosis(..., fisher=False)`
   bzw. äquivalent) — **keine** Excess-Wölbung übergeben, sonst wird der Nenner falsch
   und kann für schiefe, aber ansonsten harmlose Verteilungen negativ werden.

Die Kennzahl ist rasterweit: `var_sharpe` und `N` beziehen sich auf **alle** Kombinationen
eines Laufs, nicht auf die einzelne Kombination, deren `SR`/`skew`/`kurtosis`/`T` sie
bewertet. Deshalb nimmt die Funktion `sharpe`/`skew`/`kurtosis`/`t` als Arrays (ein Eintrag
je Kombination) entgegen und liefert ein Array gleicher Länge zurück — `var_sharpe` wird
einmal über das gesamte `sharpe`-Array gebildet und danach auf jede Kombination angewandt.
`N` kommt bewusst als eigener Parameter und nicht aus `len(sharpe)`: Ist ein Lauf auf
einzelne Ergebnisse ausgedünnt, bleibt `N` die tatsächlich gelaufene Rastergröße
(`backtest_runs.n_combinations`), während `len(sharpe)` kleiner sein kann.

Extreme Momente in der Praxis: In den Kalibrierungsläufen dieses Projekts sind Schiefe
und rohe Wölbung extrem (Schiefe im zweistelligen, Wölbung im dreistelligen Bereich) —
Folge eines Portfolios, das die meiste Zeit flach ist und nur an wenigen Balken Rendite
zeigt. Die Formel arbeitet dort weit außerhalb des Bereichs, für den sie ursprünglich
hergeleitet wurde. Der **Vergleich zwischen Läufen** (informationsfreies Signal vs.
geprüfte Strategie, kleines vs. großes Raster) trägt trotzdem, weil er dieselbe
Verzerrung auf beiden Seiten hat. Der **absolute Wert** einer einzelnen DSR ist unter
diesen Bedingungen mit Vorsicht zu lesen.
"""

import numpy as np
from scipy import stats as scipy_stats


def noise_floor_sr0(var_sharpe: float, n: int) -> float:
    """Rauschlatte SR0 eines Rasters — der Sharpe, den reines Rauschen erwarten lässt.

    Eigene Funktion, weil die Latte auch **ohne** die DSR gebraucht wird: eine DSR
    ohne `N` und `SR0` daneben ist nicht lesbar (Ticket 56), und der Befund eines
    Testset-Laufs weist die drei Werte deshalb gemeinsam aus. Damit es nur eine
    Definition der Latte gibt, rechnet `deflated_sharpe_ratio` sie über genau diese
    Funktion.

    Die Latte trägt die Einheit von `var_sharpe`: wird die Varianz der **annualisierten**
    Sharpes übergeben, ist das Ergebnis die annualisierte Latte; wird die Varianz der
    Sharpes **je Balken** übergeben, ist es die Latte je Balken. Beides ist derselbe
    Wert bis auf den Faktor `sqrt(ann_factor)`.

    Args:
        var_sharpe: Stichprobenvarianz der Sharpes über alle Kombinationen des
            Rasters (`ddof=1`).
        n: Rastergröße des Laufs (`backtest_runs.n_combinations`).

    Returns:
        SR0. `NaN`, wenn `n <= 1` — dann gibt es keinen Mehrfachvergleich, gegen den
        abgesichert werden könnte (siehe `deflated_sharpe_ratio`).
    """
    if n <= 1:
        return float('nan')
    gamma = np.euler_gamma
    return float(
        np.sqrt(var_sharpe) * (
            (1 - gamma) * scipy_stats.norm.ppf(1 - 1 / n)
            + gamma * scipy_stats.norm.ppf(1 - 1 / (n * np.e))
        )
    )


def deflated_sharpe_ratio(
    sharpe: np.ndarray,
    skew: np.ndarray,
    kurtosis: np.ndarray,
    n: int,
    t: np.ndarray,
) -> np.ndarray:
    """Rechnet die Deflated Sharpe Ratio je Kombination eines Multiparameter-Laufs.

    Args:
        sharpe: Nicht annualisierter Sharpe je Kombination — der Wert **vor** der
            Multiplikation mit `sqrt(ann_factor)`, nicht der annualisierte
            `backtest_results.sharpe_ratio`. Array der Länge N (bzw. der Länge des
            tatsächlich vorliegenden Ausschnitts, siehe `n`).
        skew: Schiefe der Renditen je Kombination, gleiche Länge wie `sharpe`.
        kurtosis: **Rohe** Wölbung der Renditen je Kombination (nicht Excess/Fisher —
            siehe Modul-Docstring), gleiche Länge wie `sharpe`.
        n: Rastergröße des Laufs (`backtest_runs.n_combinations`), **nicht**
            `len(sharpe)`. Ein ausgedünnter Lauf hat weniger vorliegende Ergebnisse als
            tatsächlich gelaufene Kombinationen; `n` bleibt die volle Rastergröße.
        t: Balkenzahl (`bar_count`) je Kombination, gleiche Länge wie `sharpe`
            (typischerweise für alle Kombinationen eines Laufs identisch, da dieselbe
            OHLCV-Historie zugrunde liegt).

    Returns:
        Array gleicher Länge wie `sharpe` mit der DSR je Kombination (Werte in [0, 1]).
        `NaN`, wenn `n <= 1` (siehe unten) oder wenn die Eingaben selbst schon `NaN`
        enthalten (NaN propagiert durch alle Rechenschritte).

    Randfälle (Anforderung 7 aus Ticket 54 — kommentiert, kein stummer Auffang):
        - `n <= 1`: Kein Mehrfachvergleich möglich. `Φ⁻¹(1 - 1/n)` würde für `n = 1`
          `Φ⁻¹(0) = -inf` liefern und die Formel unbrauchbar machen. Die Kennzahl ist in
          diesem Fall fachlich nicht definiert (es gibt nichts, wogegen der Kandidat
          abgesichert werden könnte) — die Funktion liefert deshalb explizit `NaN` statt
          eines rechnerischen Artefakts.
        - `var_sharpe == 0` (alle vorliegenden Kombinationen haben denselben Sharpe):
          Braucht **keine** Sonderbehandlung. `sqrt(0)` ist mathematisch definiert und
          ergibt `SR0 = 0` — die Formel bleibt ohne Eingriff korrekt. Der Fall ist hier
          nur dokumentiert, damit niemand versehentlich einen überflüssigen Guard
          nachträgt.
        - Nenner-Radikand `== 0` (Grenzfall `kurt_roh = skew² + 1`, z. B. bei
          zweipunktverteilten Renditen): Der Radikand kann mit roher Wölbung nicht
          negativ werden (siehe Kommentar an der Nenner-Zeile), wird an diesem Rand aber
          exakt 0. Division durch 0 wird hier bewusst zugelassen: `norm.cdf(±inf)` ist
          `0` bzw. `1` — ein sinnvoller Grenzwert, der besagt, dass die Kombination mit
          Sicherheit über/unter der Deflationsschwelle liegt. Die zugehörige
          numpy-Warnung wird gezielt unterdrückt, damit sie nicht unerklärt im Log
          auftaucht.
    """
    sharpe_arr = np.asarray(sharpe, dtype='float64')
    skew_arr = np.asarray(skew, dtype='float64')
    kurtosis_arr = np.asarray(kurtosis, dtype='float64')
    t_arr = np.asarray(t, dtype='float64')

    # Randfall N <= 1: kein Mehrfachvergleich, Kennzahl nicht definiert (siehe Docstring).
    if n <= 1:
        return np.full(sharpe_arr.shape, np.nan, dtype='float64')

    # var_sharpe ist rasterweit: eine einzelne Varianz über ALLE vorliegenden Sharpes,
    # nicht je Kombination. ddof=1 (Stichprobenvarianz), wie bei Bailey/López de Prado.
    var_sharpe = np.nanvar(sharpe_arr, ddof=1)

    # Randfall var_sharpe == 0 (identische Sharpes): kein Guard nötig, siehe Docstring —
    # sqrt(0) = 0 ergibt SR0 = 0 ohne Sonderfall.
    sr0 = noise_floor_sr0(var_sharpe, n)

    # Der Radikand ist eine quadratische Form in SR: ((kurt_roh-1)/4)*SR^2 - skew*SR + 1.
    # Diskriminante = skew^2 - (kurt_roh - 1). Für jede Verteilung — auch für
    # Stichprobenmomente — gilt kurt_roh >= skew^2 + 1 (Ungleichung von Momenten), die
    # Diskriminante ist also strukturell <= 0 und der Radikand wird nie negativ. Mit der
    # (falschen) Excess-Wölbung wäre diese Ungleichung verletzt gewesen — genau das war
    # der Grund für den Negativ-Guard im alten Code (Symptom von Defekt 2, keine
    # eigenständige Lösung). Einziger verbleibender Grenzfall: Gleichheit
    # (kurt_roh = skew^2 + 1, z. B. bei zweipunktverteilten Renditen) macht den Radikand
    # am Scheitel exakt 0 — dieser Fall ist im Docstring dokumentiert und unten bewusst
    # zugelassen statt abgefangen.
    denominator = np.sqrt(
        1 - skew_arr * sharpe_arr + ((kurtosis_arr - 1) / 4) * sharpe_arr ** 2
    )
    numerator = (sharpe_arr - sr0) * np.sqrt(t_arr - 1)
    # Denominator == 0 (siehe Kommentar oben) führt zu +-inf im Quotienten bzw. bei
    # gleichzeitig exakt 0 werdendem Zähler zu 0/0 = NaN. Beides ist ein gültiges,
    # fachlich sinnvolles Ergebnis (norm.cdf(+-inf) = 1 bzw. 0; NaN wenn unbestimmbar) —
    # die numpy-Warnung dafür wird deshalb gezielt unterdrückt statt versteckt
    # durchzulaufen.
    with np.errstate(divide='ignore', invalid='ignore'):
        return scipy_stats.norm.cdf(numerator / denominator)
