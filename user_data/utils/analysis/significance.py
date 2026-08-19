"""Statistische Auswertung eines einzelnen Kandidaten.

Zwei Verfahren, die **verschiedene Fragen** beantworten — die Ausgabe sagt das
jeweils selbst, damit die Zahlen nicht verwechselt werden:

1. **Permutations-p-Wert** (``permutation_p_value``): „Wie oft entsteht ein so
   gutes Ergebnis aus strukturlosen Daten?" Vergleicht den echten Wert mit einer
   Null-Verteilung aus N Läufen auf permutierten Preisreihen
   (``synthetic_series``). Das ist ein echter Test gegen ein Nullmodell.

2. **Bootstrap-Band** (``bootstrap_trade_returns``): „Wie unsicher ist diese Zahl,
   gegeben genau diese Trades?" Resampling der eigenen Trade-Renditen mit
   Zurücklegen. Es gibt hier **kein Nullmodell** und deshalb **keinen p-Wert** —
   der Anteil der Resamples mit Profitfaktor <= 1 heißt darum
   ``share_pf_le_one`` und ist ausdrücklich ein Bootstrap-Anteil.

Abgrenzung zur DSR: Die ist eine **rasterweite**
Mehrfachvergleichs-Korrektur — sie fragt „ist der beste Wert mehr als das
erwartete Maximum aus N Versuchen?". Beide Verfahren hier betrachten dagegen
genau **einen** Kandidaten.

**Kalibrierungs-Stand** (Tickets 79 und 80 — Zahlen und Begründung in
``documentation/knowledge/signifikanztest.md``, Abschnitt 5): **Beide Kontrollen sind
bestanden.** Negativkontrolle (``dwsRandomEntry``, 10 unabhängige Indikator-Seeds,
N = 99): 0 von 10 p-Werten unter 0,10, Streuung 0,19 bis 0,94. Positivkontrolle
(synthetische Reihe mit eingebautem, driftfreiem Momentum aus
:mod:`user_data.utils.analysis.momentum_series` plus SMA-Trendfolge, 3 Daten- und 3
Permutations-Seeds, N = 99): p = 0,01 in jeder Messung, auf allen drei Metriken; die
Gegenproben (30 Reihen ohne Momentum, ``dwsRandomEntry`` auf der Momentum-Reihe) bleiben
unauffällig.

Der **erste** Positiv-Versuch mit ``dwsLookaheadOracle`` (skill 0,10) ist strukturell
gescheitert und bleibt als Lehre stehen: Ein Look-ahead-Vorteil ist invariant unter der
Bar-Permutation, weil die Strategie auf jeder synthetischen Reihe neu gerechnet wird und
dort in die *synthetische* Zukunft schaut.
**Folge für die Nutzung: Der Test prüft nicht auf Look-ahead-Bias.**

Das Modul ist reine Numerik: kein DB-Zugriff, kein vectorbtpro, keine Seiteneffekte.
Die Profitfaktor-Formel ist bewusst von vbt übernommen
(``vectorbtpro.portfolio.nb.records.profit_factor_reduce_nb``, am Quelltext
abgelesen): Summe der Gewinne / Summe der Betragsverluste, ``inf`` ohne Verlust,
``NaN`` bei leerer Menge. Angewandt auf die Trade-Renditen entspricht das vbts
``Trades.get_profit_factor(use_returns=True)`` — nicht der PnL-Variante, die in
``backtest_results.profit_factor`` steht. Der Unterschied steht in der Ausgabe
(``profit_factor_basis``), damit die Zahlen nicht als identisch gelesen werden.
"""

from typing import Dict, List, Optional, Sequence

import numpy as np

# Standard-Metriken des Permutationstests. Ein Durchlauf liefert alle drei; je
# Metrik entsteht ein eigener p-Wert.
DEFAULT_PERMUTATION_METRICS: tuple = ('sharpe_ratio', 'profit_factor', 'total_return_pct')

# Standard-Rundenzahl des Trade-Level-Bootstraps.
DEFAULT_BOOTSTRAP_ROUNDS: int = 2000

# Perzentile des Konfidenzbands. p50 ist der Median, nicht der Punktschätzer der
# Originalstichprobe — der steht separat als ``observed``.
BAND_QUANTILES: tuple = (0.05, 0.50, 0.95)


def profit_factor(values: Sequence[float]) -> float:
    """Profitfaktor einer Werteliste nach vbt-Formel.

    Args:
        values: Renditen oder PnL-Werte. NaN-Werte werden übersprungen.

    Returns:
        Summe der positiven Werte geteilt durch die Summe der Betragsverluste.
        ``inf`` wenn es keinen Verlust gibt, ``NaN`` bei leerer Menge.
    """
    array = np.asarray(values, dtype=float)
    array = array[~np.isnan(array)]
    if array.size == 0:
        return float('nan')
    win_sum = float(array[array > 0.0].sum())
    loss_sum = float(np.abs(array[array < 0.0]).sum())
    if loss_sum == 0.0:
        return float('inf')
    return win_sum / loss_sum


def _finite(values: Sequence[float]) -> np.ndarray:
    """Filtert eine Werteliste auf endliche Zahlen.

    Args:
        values: Beliebige Zahlenfolge, auch mit None/NaN/inf.

    Returns:
        Float-Array nur mit endlichen Werten.
    """
    array = np.asarray([np.nan if v is None else v for v in values], dtype=float)
    return array[np.isfinite(array)]


def null_distribution_summary(values: Sequence[float]) -> Dict[str, Optional[float]]:
    """Kennwerte einer Null-Verteilung (mean, median, p05, p95, max).

    Nicht-endliche Werte (None/NaN/inf) fließen nicht in die Kennwerte ein, werden
    aber gezählt und ausgewiesen — ein Lauf ohne Trades liefert z.B. NaN als
    Profitfaktor und darf nicht stillschweigend verschwinden.

    Args:
        values: Werte der Null-Verteilung, in Lauf-Reihenfolge.

    Returns:
        Dict mit ``mean``, ``median``, ``p05``, ``p95``, ``max``, ``n_total``
        (alle Läufe) und ``n_finite`` (in die Kennwerte eingegangene Läufe). Sind
        keine endlichen Werte vorhanden, stehen die Kennwerte auf None.
    """
    finite = _finite(values)
    if finite.size == 0:
        return {
            'mean': None, 'median': None, 'p05': None, 'p95': None, 'max': None,
            'n_total': len(values), 'n_finite': 0,
        }
    return {
        'mean': float(finite.mean()),
        'median': float(np.median(finite)),
        'p05': float(np.quantile(finite, 0.05)),
        'p95': float(np.quantile(finite, 0.95)),
        'max': float(finite.max()),
        'n_total': len(values),
        'n_finite': int(finite.size),
    }


def permutation_p_value(
    real_value: Optional[float],
    null_values: Sequence[float],
) -> Dict[str, object]:
    """Einseitiger Permutations-p-Wert mit Plus-eins-Korrektur.

    Gezählt wird, wie viele **synthetische** Läufe den echten Wert erreichen oder
    übertreffen (``>=``, also einseitig „so gut oder besser"). Der p-Wert ist
    ``(k + 1) / (N + 1)``: der echte Lauf zählt als eigene Beobachtung mit. Ohne
    diese Korrektur käme p = 0 heraus, sobald kein synthetischer Lauf mitkommt —
    und p = 0 behauptet eine Sicherheit, die N Ziehungen nicht hergeben. Der
    kleinste erreichbare p-Wert ist damit ``1 / (N + 1)``.

    Nicht-endliche synthetische Werte (Lauf ohne Trades: NaN) zählen **nicht** als
    Treffer, bleiben aber in ``n_iterations`` enthalten. Sie zu verwerfen würde N
    verkleinern und den p-Wert künstlich verschärfen; sie als Treffer zu zählen
    würde ihn künstlich entschärfen. Die Zahl steht als ``n_non_finite`` daneben.

    Ist der echte Wert selbst nicht endlich, gibt es keinen sinnvollen Vergleich:
    ``p_value`` bleibt None und ``p_value_missing_reason`` nennt den Grund.

    Args:
        real_value: Kennzahl des echten Kandidaten.
        null_values: Kennzahlen der N synthetischen Läufe, in Lauf-Reihenfolge.

    Returns:
        Dict mit ``real_value``, ``p_value``, ``p_value_missing_reason``,
        ``n_iterations``, ``n_ge_real`` (k), ``n_non_finite`` und den Kennwerten
        der Null-Verteilung (``null_distribution``).

    Raises:
        ValueError: Wenn die Null-Verteilung leer ist.
    """
    n_iterations = len(null_values)
    if n_iterations == 0:
        raise ValueError(
            'Die Null-Verteilung ist leer — ein p-Wert braucht mindestens einen '
            'synthetischen Lauf.'
        )

    array = np.asarray([np.nan if v is None else v for v in null_values], dtype=float)
    finite_mask = np.isfinite(array)
    n_non_finite = int((~finite_mask).sum())

    real_is_finite = real_value is not None and np.isfinite(float(real_value))
    if real_is_finite:
        n_ge_real = int((array[finite_mask] >= float(real_value)).sum())
        p_value: Optional[float] = (n_ge_real + 1) / (n_iterations + 1)
        missing_reason: Optional[str] = None
    else:
        n_ge_real = 0
        p_value = None
        missing_reason = (
            'echter Wert ist nicht endlich (kein Trade oder von vbt als NaN/inf '
            'geliefert) — ein Vergleich mit der Null-Verteilung ist nicht definiert'
        )

    return {
        'real_value': float(real_value) if real_is_finite else None,
        'p_value': p_value,
        'p_value_missing_reason': missing_reason,
        'n_iterations': n_iterations,
        'n_ge_real': n_ge_real,
        'n_non_finite': n_non_finite,
        'null_distribution': null_distribution_summary(null_values),
    }


def build_permutation_summary(
    real_values: Dict[str, Optional[float]],
    distributions: Dict[str, List[float]],
    n_no_trade_runs: int,
    n_runs: int,
) -> Dict[str, object]:
    """Baut die Zusammenfassung des Permutationstests je Metrik.

    Der p-Wert steht in derselben Struktur wie die Kennwerte seiner
    Null-Verteilung — ein p-Wert darf strukturell nicht ohne sie zitiert werden
    (Regel analog „DSR nie ohne N und SR0").

    Args:
        real_values: Echter Wert je Metrik.
        distributions: Vollständige Null-Verteilung je Metrik, in Lauf-Reihenfolge.
        n_no_trade_runs: Anzahl synthetischer Läufe ohne einen einzigen Trade.
        n_runs: Anzahl gerechneter synthetischer Läufe.

    Returns:
        Dict mit ``metrics`` (je Metrik das Ergebnis aus ``permutation_p_value``)
        und ``no_trade_runs`` (Anzahl, Anteil und Erläuterung).

    Raises:
        ValueError: Wenn eine Metrik keine Null-Verteilung hat.
    """
    metrics: Dict[str, object] = {}
    for metric, real_value in real_values.items():
        if metric not in distributions:
            raise ValueError(
                f"Metrik '{metric}' hat keine Null-Verteilung — echter Wert und "
                f"Verteilung müssen zusammen entstehen."
            )
        metrics[metric] = permutation_p_value(real_value, distributions[metric])

    return {
        'metrics': metrics,
        'no_trade_runs': {
            'count': n_no_trade_runs,
            'share': (n_no_trade_runs / n_runs) if n_runs else None,
            'note': (
                'Synthetische Läufe ohne Trades werden mitgezählt, nicht verworfen: '
                'dass die Regeln auf strukturlosen Daten gar nicht auslösen, ist '
                'selbst ein Befund.'
            ),
        },
    }


def _band(draws: np.ndarray) -> Dict[str, float]:
    """Konfidenzband (p05/p50/p95) einer Bootstrap-Ziehungsreihe.

    Args:
        draws: Statistik-Werte der Resamples.

    Returns:
        Dict mit ``p05``, ``p50``, ``p95``. Nicht-endliche Ziehungen bleiben außen
        vor; ihre Anzahl steht als ``n_non_finite`` dabei.
    """
    finite = draws[np.isfinite(draws)]
    if finite.size == 0:
        return {'p05': None, 'p50': None, 'p95': None,
                'n_non_finite': int(draws.size)}
    p05, p50, p95 = (float(np.quantile(finite, q)) for q in BAND_QUANTILES)
    return {'p05': p05, 'p50': p50, 'p95': p95,
            'n_non_finite': int(draws.size - finite.size)}


def bootstrap_trade_returns(
    return_pct_values: Sequence[float],
    n_rounds: int = DEFAULT_BOOTSTRAP_ROUNDS,
    seed: int = 42,
) -> Dict[str, object]:
    """Konfidenzbänder der Kernkennzahlen aus den Trade-Renditen eines Kandidaten.

    Zieht ``n_rounds`` mal eine Stichprobe derselben Größe wie die Originalmenge
    **mit Zurücklegen** und rechnet je Ziehung Mittelwert, Median und Profitfaktor.
    Das Ergebnis ist ein Unsicherheitsband um die eigenen Zahlen — es sagt, wie
    stark das Ergebnis an einzelnen Trades hängt.

    **Kein Nullmodell, kein p-Wert.** ``share_pf_le_one`` ist der Anteil der
    Resamples mit Profitfaktor <= 1 und heißt deshalb bewusst nicht p-Wert: er
    beantwortet nicht die Frage „entsteht das auch aus strukturlosen Daten?" — das
    macht der Permutationstest.

    Args:
        return_pct_values: Trade-Renditen in Prozent (Spalte ``return_pct``).
        n_rounds: Anzahl der Resampling-Runden.
        seed: Startwert des Zufallsgenerators — gleicher Seed, gleiches Ergebnis.

    Returns:
        Dict mit ``n_trades``, ``n_rounds``, ``seed``, ``observed`` (die Kennzahlen
        der Originalmenge), ``bands`` (je Kennzahl p05/p50/p95),
        ``share_pf_le_one`` samt Erläuterung und ``profit_factor_basis``.

    Raises:
        ValueError: Wenn keine verwendbare Trade-Rendite vorliegt oder n_rounds
            kleiner als 1 ist.
    """
    if n_rounds < 1:
        raise ValueError(f'n_rounds muss >= 1 sein, ist {n_rounds}')

    values = _finite(return_pct_values)
    if values.size == 0:
        raise ValueError(
            'Keine verwendbaren Trade-Renditen vorhanden. Der Bootstrap rechnet aus '
            'den gespeicherten Trades eines Results (Tabelle backtest_result_trades); '
            'die entstehen erst beim Recompute. Recompute-Weg: Analyse für den Lauf '
            'starten bzw. das Chart des Results öffnen — danach den Bootstrap erneut '
            'aufrufen. Es wird bewusst nicht automatisch nachgerechnet.'
        )

    rng = np.random.default_rng(seed)
    n_trades = int(values.size)
    mean_draws = np.empty(n_rounds, dtype=float)
    median_draws = np.empty(n_rounds, dtype=float)
    pf_draws = np.empty(n_rounds, dtype=float)

    for i in range(n_rounds):
        sample = rng.choice(values, size=n_trades, replace=True)
        mean_draws[i] = float(sample.mean())
        median_draws[i] = float(np.median(sample))
        pf_draws[i] = profit_factor(sample)

    finite_pf = pf_draws[np.isfinite(pf_draws)]
    share_pf_le_one = (
        float((finite_pf <= 1.0).mean()) if finite_pf.size else None
    )

    return {
        'n_trades': n_trades,
        'n_rounds': n_rounds,
        'seed': seed,
        'observed': {
            'mean_return_pct': float(values.mean()),
            'median_return_pct': float(np.median(values)),
            'profit_factor': profit_factor(values),
        },
        'bands': {
            'mean_return_pct': _band(mean_draws),
            'median_return_pct': _band(median_draws),
            'profit_factor': _band(pf_draws),
        },
        'share_pf_le_one': share_pf_le_one,
        'share_pf_le_one_note': (
            'Anteil der Resamples mit Profitfaktor <= 1. Das ist ein '
            'Bootstrap-Anteil, KEIN p-Wert eines Nullmodells: er sagt, wie stark '
            'das Ergebnis an einzelnen Trades hängt, nicht ob es aus '
            'strukturlosen Daten entstehen kann. Letzteres beantwortet der '
            'Permutationstest.'
        ),
        'profit_factor_basis': (
            'Trade-Renditen (return_pct), entspricht vbts '
            'Trades.get_profit_factor(use_returns=True). Das Feld '
            'backtest_results.profit_factor rechnet dagegen über PnL — die beiden '
            'Zahlen sind ähnlich, aber nicht identisch.'
        ),
    }
