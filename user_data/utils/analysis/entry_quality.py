"""Entry-Qualität exit-frei bewerten (MFE/MAE, First-Touch-Geometrie).

Bewertet einen Einstiegszeitpunkt **ohne jede Exit-Regel**: Für jedes Entry-Signal
wird gemessen, was der Kurs in den folgenden N Balken tut. Damit lässt sich der
Entry vom Exit trennen — die Frage „trägt der Einstieg überhaupt?" ist sonst nicht
beantwortbar, weil Entry und Exit im Backtest immer gemeinsam gemessen werden.

Zwei Kennzahlen-Familien:

1. **Exkursionen** — MFE (maximale Bewegung ins Plus) und MAE (maximale Bewegung
   ins Minus) je Signal. Aus ihrer Verteilung liest man die Asymmetrie ab.
2. **First-Touch-Geometrie** — für ein Paar (Take-Profit, Stop-Loss) der Anteil der
   Signale, die das Ziel erreichen, *bevor* sie den Verlust erreichen. Das IST die
   erreichbare Win-Rate dieser Exit-Geometrie, ohne einen einzigen Backtest.

Konventionen (an die Engine angelehnt, siehe rules_engine/spec_runner):

- **Einstandspreis = Close des Signalbalkens.** `Portfolio.from_signals` bekommt im
  Spec-Runner kein `price=`-Argument, der VBT-Default ist Close.
- **Vorwärtsfenster ab t+1.** Der Signalbalken selbst ist zum Fill-Zeitpunkt bereits
  gelaufen und damit nicht mehr handelbar.
- **MFE über High, MAE über Low.** Die Stops der Engine triggern intrabar (from_signals
  bekommt open/high/low); eine Messung auf Close-Basis würde eine andere Welt messen
  als der Backtest.
- **Balken-Kollision zählt als Verlust.** Erreicht ein Balken sowohl das Ziel (High)
  als auch den Stop (Low), ist die Reihenfolge innerhalb des Balkens unbekannt. Wir
  zählen konservativ den Stop — pessimistisch raten ist die einzige ehrliche Wahl.

Alle Renditen sind dimensionslose Faktoren (0.05 = 5 Prozent), nicht Prozentpunkte.
"""

from typing import Optional

import numpy as np
import pandas as pd

# Ergebnis-Codes der First-Touch-Auswertung
OUTCOME_TP = 1      # Ziel zuerst erreicht
OUTCOME_SL = -1     # Stop zuerst erreicht (inkl. Balken-Kollision)
OUTCOME_OPEN = 0    # weder noch innerhalb des Horizonts


def first_touch_entries(mask: pd.Series) -> pd.Series:
    """Reduziert eine Signal-Maske auf den ersten Balken jeder zusammenhängenden Serie.

    Der VWMA-Entry ist zustandsbasiert: Er feuert auf jeder Kerze, solange der Kurs
    unter dem Band liegt. Diese Folge-Signale sind fast identische Beobachtungen und
    würden eine Verteilungs-Statistik künstlich aufblähen. Diese Funktion liefert die
    Ereignis-Variante (nur der Übertritt) — dieselbe Konstruktion wie Iteration v7.

    Args:
        mask: Boolean-Serie der Entry-Signale.

    Returns:
        Boolean-Serie, die nur an den Übertritts-Balken True ist.
    """
    prev = mask.shift(1, fill_value=False).astype(bool)
    return mask.astype(bool) & ~prev


def signal_positions(mask: pd.Series, horizon: int) -> np.ndarray:
    """Positionen der Signale, für die ein volles Vorwärtsfenster verfügbar ist.

    Signale in den letzten `horizon` Balken werden verworfen — ihr Fenster wäre
    abgeschnitten und die Exkursionen damit systematisch zu klein.

    Args:
        mask: Boolean-Serie der Entry-Signale.
        horizon: Länge des Vorwärtsfensters in Balken.

    Returns:
        Integer-Array der Signal-Positionen (Index-Positionen, nicht Zeitstempel).
    """
    if horizon < 1:
        raise ValueError(f"horizon muss >= 1 sein, ist {horizon}")
    values = np.asarray(mask.fillna(False).astype(bool).values)
    positions = np.flatnonzero(values)
    limit = len(values) - horizon
    return positions[positions < limit]


def forward_paths(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    positions: np.ndarray,
    horizon: int,
) -> tuple:
    """Baut die Vorwärtspfade je Signal als Renditen relativ zum Einstandspreis.

    Args:
        high: High-Serie.
        low: Low-Serie.
        close: Close-Serie (liefert den Einstandspreis).
        positions: Signal-Positionen aus `signal_positions`.
        horizon: Länge des Vorwärtsfensters in Balken.

    Returns:
        Tupel (high_path, low_path), je ein Array der Form (n_signale, horizon) mit
        Renditen gegenüber dem Einstandspreis. Leere Arrays, wenn keine Signale.
    """
    if len(positions) == 0:
        empty = np.empty((0, horizon), dtype=float)
        return empty, empty

    high_values = np.asarray(high.values, dtype=float)
    low_values = np.asarray(low.values, dtype=float)
    close_values = np.asarray(close.values, dtype=float)

    offsets = np.arange(1, horizon + 1)
    window = positions[:, None] + offsets[None, :]

    entry_price = close_values[positions][:, None]
    high_path = high_values[window] / entry_price - 1.0
    low_path = low_values[window] / entry_price - 1.0
    return high_path, low_path


def excursions(high_path: np.ndarray, low_path: np.ndarray) -> tuple:
    """Berechnet MFE und MAE je Signal aus den Vorwärtspfaden.

    Args:
        high_path: Array (n_signale, horizon) der High-Renditen.
        low_path: Array (n_signale, horizon) der Low-Renditen.

    Returns:
        Tupel (mfe, mae) als Arrays der Länge n_signale. MFE ist das Maximum der
        High-Renditen, MAE das Minimum der Low-Renditen (also in der Regel negativ).
    """
    if high_path.shape[0] == 0:
        return np.empty(0), np.empty(0)
    return high_path.max(axis=1), low_path.min(axis=1)


def excursion_asymmetry(mfe: np.ndarray, mae: np.ndarray) -> np.ndarray:
    """Skalenfreies Asymmetrie-Mass je Signal: (MFE - |MAE|) / (MFE + |MAE|).

    **Warum nicht einfach die MFE vergleichen:** MFE und MAE wachsen gemeinsam mit der
    Volatilität. Ein Entry, der nach einem tiefen Pullback feuert, sitzt per Konstruktion
    in einem volatileren Zustand — seine MFE ist höher als die eines Zufallsbalkens, seine
    MAE aber ebenso. Ein reiner MFE-Vergleich gegen das Null-Modell misst dann Volatilität
    und nennt sie Kante.

    Dieses Mass teilt die Skala heraus: Es liegt in [-1, 1] und sagt allein, ob der Kurs
    nach dem Einstieg weiter nach oben als nach unten läuft. 0 heisst symmetrisch (keine
    Kante), positive Werte heissen Übergewicht ins Plus.

    Args:
        mfe: MFE je Signal.
        mae: MAE je Signal (negativ).

    Returns:
        Array der Asymmetrie je Signal. Signale ohne jede Bewegung (MFE = MAE = 0)
        ergeben 0.
    """
    if len(mfe) == 0:
        return np.empty(0)

    mae_abs = np.abs(mae)
    total = mfe + mae_abs
    return np.divide(mfe - mae_abs, total, out=np.zeros_like(total, dtype=float), where=total > 0)


def summarize_excursions(mfe: np.ndarray, mae: np.ndarray) -> dict:
    """Verdichtet die Exkursions-Verteilung zu Kennzahlen.

    Die Verteilung ist schief, deshalb Median und Quartile statt nur Mittelwerten.
    Die Edge-Ratio (mittlere MFE geteilt durch mittlere absolute MAE) ist das
    Asymmetrie-Maß: Werte über 1 heissen, der Kurs läuft im Mittel weiter ins Plus
    als ins Minus.

    Args:
        mfe: MFE je Signal.
        mae: MAE je Signal (negativ).

    Returns:
        Dict mit Kennzahlen. Alle Renditen als Faktoren. `n` = Anzahl Signale.
    """
    n = int(len(mfe))
    if n == 0:
        return {'n': 0}

    mae_abs = np.abs(mae)
    mean_mae_abs = float(mae_abs.mean())
    asym = excursion_asymmetry(mfe, mae)
    return {
        'n': n,
        # Skalenfreie Asymmetrie — die eigentliche Entry-Kennzahl (siehe excursion_asymmetry)
        'asym_median': float(np.median(asym)),
        'asym_mean': float(asym.mean()),
        'mfe_median': float(np.median(mfe)),
        'mfe_mean': float(mfe.mean()),
        'mfe_q25': float(np.quantile(mfe, 0.25)),
        'mfe_q75': float(np.quantile(mfe, 0.75)),
        'mae_median': float(np.median(mae)),
        'mae_mean': float(mae.mean()),
        'mae_q25': float(np.quantile(mae, 0.25)),
        'mae_q75': float(np.quantile(mae, 0.75)),
        # Edge-Ratio: > 1 bedeutet Asymmetrie zugunsten des Plus
        'edge_ratio': float(mfe.mean() / mean_mae_abs) if mean_mae_abs > 0 else float('nan'),
        # Asymmetrie auf Median-Basis (robuster gegen einzelne Ausreisser)
        'edge_ratio_median': (
            float(np.median(mfe) / np.median(mae_abs)) if np.median(mae_abs) > 0 else float('nan')
        ),
    }


def first_touch(
    high_path: np.ndarray,
    low_path: np.ndarray,
    tp: float,
    sl: float,
) -> np.ndarray:
    """Entscheidet je Signal, ob Ziel oder Stop zuerst erreicht wird.

    Bei Balken-Kollision (Ziel und Stop im selben Balken) gewinnt der Stop — die
    Reihenfolge innerhalb des Balkens ist aus OHLC nicht rekonstruierbar.

    Args:
        high_path: Array (n_signale, horizon) der High-Renditen.
        low_path: Array (n_signale, horizon) der Low-Renditen.
        tp: Take-Profit als positiver Faktor (0.02 = 2 Prozent).
        sl: Stop-Loss als positiver Faktor (0.15 = 15 Prozent).

    Returns:
        Array der Länge n_signale mit OUTCOME_TP / OUTCOME_SL / OUTCOME_OPEN.
    """
    if tp <= 0 or sl <= 0:
        raise ValueError(f"tp und sl müssen positiv sein, sind tp={tp}, sl={sl}")

    n = high_path.shape[0]
    if n == 0:
        return np.empty(0, dtype=int)

    horizon = high_path.shape[1]
    tp_hit = high_path >= tp
    sl_hit = low_path <= -sl

    # Erster Treffer je Zeile; kein Treffer wird auf horizon gesetzt (= nie erreicht),
    # damit der Vergleich unten ohne Sonderfall auskommt.
    tp_first = np.where(tp_hit.any(axis=1), tp_hit.argmax(axis=1), horizon)
    sl_first = np.where(sl_hit.any(axis=1), sl_hit.argmax(axis=1), horizon)

    outcome = np.full(n, OUTCOME_OPEN, dtype=int)
    # Stop gewinnt bei Gleichstand (Balken-Kollision) — daher <= zuerst prüfen.
    outcome[(sl_first < horizon) & (sl_first <= tp_first)] = OUTCOME_SL
    outcome[(tp_first < horizon) & (tp_first < sl_first)] = OUTCOME_TP
    return outcome


def geometry_stats(
    outcome: np.ndarray,
    tp: float,
    sl: float,
    fees: float = 0.001,
    open_return: Optional[np.ndarray] = None,
) -> dict:
    """Bewertet eine TP/SL-Geometrie aus den First-Touch-Ergebnissen.

    Die Win-Rate ist der Anteil der Signale, die das Ziel zuerst erreichen. Der
    Erwartungswert rechnet Gebühren für Ein- und Ausstieg mit (2 x fees).

    Trades, die im Horizont weder Ziel noch Stop erreichen, werden über
    `open_return` bewertet (Rendite am Fensterende) — das entspricht einem
    Zeitstopp der Länge des Horizonts. Fehlt `open_return`, gehen sie mit 0 ein.

    Args:
        outcome: Ergebnis-Codes aus `first_touch`.
        tp: Take-Profit als positiver Faktor.
        sl: Stop-Loss als positiver Faktor.
        fees: Gebühr je Order (0.001 = 0,1 Prozent).
        open_return: Optionale Renditen am Fensterende je Signal (für OUTCOME_OPEN).

    Returns:
        Dict mit Win-Rate, Anteilen und Erwartungswert je Trade.
    """
    n = int(len(outcome))
    if n == 0:
        return {'n': 0, 'tp': tp, 'sl': sl}

    is_tp = outcome == OUTCOME_TP
    is_sl = outcome == OUTCOME_SL
    is_open = outcome == OUTCOME_OPEN

    returns = np.zeros(n, dtype=float)
    returns[is_tp] = tp
    returns[is_sl] = -sl
    if open_return is not None:
        returns[is_open] = open_return[is_open]

    # Gebühren fallen zweimal an (Einstieg + Ausstieg)
    returns = returns - 2.0 * fees

    decided = int(is_tp.sum() + is_sl.sum())
    return {
        'n': n,
        'tp': tp,
        'sl': sl,
        # Win-Rate über alle Signale (Zeitstopp-Fälle zählen als nicht gewonnen)
        'win_rate': float(is_tp.mean()),
        # Win-Rate nur unter den entschiedenen Trades (Ziel oder Stop erreicht)
        'win_rate_decided': float(is_tp.sum() / decided) if decided > 0 else float('nan'),
        'share_tp': float(is_tp.mean()),
        'share_sl': float(is_sl.mean()),
        'share_open': float(is_open.mean()),
        'expectancy': float(returns.mean()),
        'expectancy_median': float(np.median(returns)),
    }


def geometry_grid(
    high_path: np.ndarray,
    low_path: np.ndarray,
    tp_values: list,
    sl_values: list,
    fees: float = 0.001,
) -> pd.DataFrame:
    """Wertet ein ganzes TP/SL-Gitter auf denselben Signalen aus.

    Args:
        high_path: Array (n_signale, horizon) der High-Renditen.
        low_path: Array (n_signale, horizon) der Low-Renditen.
        tp_values: Take-Profit-Werte als positive Faktoren.
        sl_values: Stop-Loss-Werte als positive Faktoren.
        fees: Gebühr je Order.

    Returns:
        DataFrame mit einer Zeile je (tp, sl)-Paar.
    """
    # Rendite am Fensterende (Close-Näherung über den letzten Balken des Fensters):
    # Für nicht entschiedene Trades ist das die Bewertung des Zeitstopps. Wir nutzen
    # den Mittelpunkt von High und Low des letzten Balkens, weil der Close im Pfad
    # nicht mitgeführt wird — die Näherung wirkt nur auf die offenen Trades.
    if high_path.shape[0] > 0:
        open_return = (high_path[:, -1] + low_path[:, -1]) / 2.0
    else:
        open_return = np.empty(0)

    rows = []
    for tp in tp_values:
        for sl in sl_values:
            outcome = first_touch(high_path, low_path, tp, sl)
            rows.append(geometry_stats(outcome, tp, sl, fees=fees, open_return=open_return))
    return pd.DataFrame(rows)


def baseline_positions(n_bars: int, horizon: int) -> np.ndarray:
    """Positionen des Null-Modells: jeder Balken mit vollem Vorwärtsfenster.

    Das Null-Modell ist der unbedingte Einstieg. Ohne diesen Vergleich misst eine
    MFE/MAE-Studie im Bullenmarkt nur die Marktdrift und nennt sie Edge.

    Args:
        n_bars: Anzahl Balken der Zeitreihe.
        horizon: Länge des Vorwärtsfensters.

    Returns:
        Integer-Array aller zulässigen Positionen.
    """
    return np.arange(0, max(0, n_bars - horizon))


def bootstrap_lift(
    baseline_values: np.ndarray,
    n_signals: int,
    observed: float,
    n_rounds: int = 2000,
    seed: int = 42,
    statistic: str = 'median',
) -> dict:
    """Prüft, ob ein beobachteter Wert aus dem Null-Modell heraus erklärbar ist.

    Zieht `n_rounds` mal eine Zufallsstichprobe der Grösse `n_signals` aus den
    Werten des Null-Modells und vergleicht die beobachtete Statistik mit dieser
    Verteilung. Ein hoher Perzentil-Rang heisst: Der Entry ist besser als der
    Zufall im selben Markt.

    Args:
        baseline_values: Werte des Null-Modells (z.B. alle MFE über alle Balken).
        n_signals: Grösse der beobachteten Signalmenge.
        observed: Beobachtete Statistik der Signalmenge.
        n_rounds: Anzahl Ziehungen.
        seed: Startwert des Zufallsgenerators (Reproduzierbarkeit).
        statistic: 'median' oder 'mean'.

    Returns:
        Dict mit Perzentil-Rang des beobachteten Werts und dem 5/95-Prozent-Band
        des Null-Modells.
    """
    if len(baseline_values) == 0 or n_signals == 0:
        return {'percentile': float('nan')}
    if statistic not in ('median', 'mean'):
        raise ValueError(f"statistic muss 'median' oder 'mean' sein, ist {statistic}")

    rng = np.random.default_rng(seed)
    func = np.median if statistic == 'median' else np.mean

    draws = np.empty(n_rounds, dtype=float)
    for i in range(n_rounds):
        sample = rng.choice(baseline_values, size=n_signals, replace=True)
        draws[i] = func(sample)

    return {
        'percentile': float((draws < observed).mean()),
        'baseline_p05': float(np.quantile(draws, 0.05)),
        'baseline_p50': float(np.quantile(draws, 0.50)),
        'baseline_p95': float(np.quantile(draws, 0.95)),
        'observed': float(observed),
        # Signifikant heisst hier: beobachteter Wert liegt oberhalb des 95-Prozent-Bands
        'above_baseline_band': bool(observed > np.quantile(draws, 0.95)),
    }
