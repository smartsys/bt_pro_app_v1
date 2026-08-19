"""Korrelation zwischen Symbolen und daraus abgeleitete effektive Symbolzahl.

Reine Rechenlogik auf pandas/numpy — keine FastAPI-, DB- oder VBT-Abhängigkeit,
damit sie eigenständig testbar bleibt. Das Laden und das Resamplen der OHLCV-Daten
auf Tagesbasis passiert beim Aufrufer (Route); hier kommen fertige Tagesschlusskurse
an.

Fachliche Festlegungen:

- Gerechnet wird auf **Log-Renditen der Tagesschlusskurse**, nicht auf Preisen.
  Preisniveaus trenden gemeinsam und erzeugen Scheinkorrelationen nahe 1.
- Je Paar wird **nur der gemeinsame Zeitraum** verglichen. Die Länge dieses
  Zeitraums wird mit ausgegeben — ein Wert aus drei Monaten Überlappung ist etwas
  anderes als einer aus drei Jahren.
- Zusätzlich zum Gesamtwert wird **rollierend** gerechnet (Default 90 Tage) und je
  Paar Minimum, Median und Maximum ausgewiesen. Korrelation steigt in Stressphasen;
  ein Gesamtwert verdeckt genau den Fall, auf den es ankommt.
- Die **effektive Symbolzahl** wird auf zwei Wegen berechnet (mittlere Paarkorrelation
  und Eigenwerte der Korrelationsmatrix). Weichen beide stark ab, ist das selbst eine
  Information.

NaN-Behandlung (bewusst explizit, kein stilles Auffüllen): Fehlende Tagesschlusskurse
bleiben NaN. Es wird weder vorwärts gefüllt noch interpoliert. Eine Rendite entsteht
nur, wenn der Tag und sein Vortag beide einen Kurs haben. Paarweise wird auf die
Zeilen eingeschränkt, in denen beide Symbole eine Rendite haben. Lücken werden pro
Symbol als `missing_days` gemeldet.
"""

import math
from typing import List, Optional

import numpy as np
import pandas as pd

# Rollendes Fenster in Tagen (Beobachtungen der Tagesreihe)
DEFAULT_WINDOW = 90
# Mindestlänge der Überlappung eines Paares in Tagen; darunter gibt es eine Fehlermeldung
# statt einer Zahl, die niemand einordnen kann.
DEFAULT_MIN_OVERLAP = 30


def daily_log_returns(daily_close: pd.DataFrame) -> pd.DataFrame:
    """Berechnet Log-Renditen aus Tagesschlusskursen.

    Args:
        daily_close: Tagesschlusskurse, Index = Tage, je Spalte ein Symbol.

    Returns:
        DataFrame gleicher Form mit Log-Renditen. Die erste Zeile ist NaN, ebenso
        jede Zeile, deren Kurs oder Vortageskurs fehlt. Es wird nichts aufgefüllt.

    Raises:
        ValueError: Wenn Kurse kleiner oder gleich null vorkommen (Logarithmus
            nicht definiert).
    """
    numeric = daily_close.astype('float64')
    if bool((numeric <= 0).any().any()):
        raise ValueError('Tagesschlusskurse enthalten Werte <= 0 — Log-Rendite nicht definiert.')
    return np.log(numeric).diff()


def _coverage(daily_close: pd.DataFrame) -> List[dict]:
    """Beschreibt je Symbol den abgedeckten Zeitraum und die Datenlücken darin."""
    coverage: List[dict] = []
    for symbol in daily_close.columns:
        series = daily_close[symbol].dropna()
        if series.empty:
            coverage.append({
                'symbol': str(symbol),
                'start': None,
                'end': None,
                'days': 0,
                'missing_days': None,
            })
            continue
        start, end = series.index[0], series.index[-1]
        span_days = int((end - start).days) + 1
        coverage.append({
            'symbol': str(symbol),
            'start': start.isoformat(),
            'end': end.isoformat(),
            'days': int(len(series)),
            'missing_days': max(span_days - int(len(series)), 0),
        })
    return coverage


def _rolling_extremes(a: pd.Series, b: pd.Series, window: int) -> dict:
    """Minimum, Median und Maximum der rollierenden Korrelation eines Paares.

    Args:
        a: Renditereihe des ersten Symbols, bereits auf die Überlappung eingeschränkt.
        b: Renditereihe des zweiten Symbols, gleicher Index wie `a`.
        window: Fensterlänge in Beobachtungen.

    Returns:
        Dict mit `rolling_min`, `rolling_median`, `rolling_max` und `rolling_windows`
        (Anzahl auswertbarer Fenster). Reicht die Überlappung nicht für ein volles
        Fenster, sind die drei Werte None und `rolling_windows` ist 0.
    """
    rolling = a.rolling(window).corr(b)
    rolling = rolling.replace([np.inf, -np.inf], np.nan).dropna()
    if rolling.empty:
        return {
            'rolling_min': None,
            'rolling_median': None,
            'rolling_max': None,
            'rolling_windows': 0,
        }
    return {
        'rolling_min': float(rolling.min()),
        'rolling_median': float(rolling.median()),
        'rolling_max': float(rolling.max()),
        'rolling_windows': int(len(rolling)),
    }


def pair_statistics(returns: pd.DataFrame, window: int, min_overlap: int) -> List[dict]:
    """Rechnet je Symbolpaar die Korrelation über den gemeinsamen Zeitraum.

    Args:
        returns: Log-Renditen, Index = Tage, je Spalte ein Symbol.
        window: Fensterlänge der rollierenden Korrelation in Beobachtungen.
        min_overlap: Mindestanzahl gemeinsamer Tage je Paar.

    Returns:
        Liste je Paar mit Korrelation, Überlappungszeitraum und rollierenden Extremwerten.

    Raises:
        ValueError: Wenn ein Paar weniger als `min_overlap` gemeinsame Tage hat.
    """
    symbols = list(returns.columns)
    pairs: List[dict] = []
    too_short: List[str] = []
    for i, first in enumerate(symbols):
        for second in symbols[i + 1:]:
            both = returns[[first, second]].dropna()
            overlap = int(len(both))
            if overlap < min_overlap:
                too_short.append(f'{first}/{second}: {overlap} gemeinsame Tage')
                continue
            a, b = both[first], both[second]
            entry = {
                'a': str(first),
                'b': str(second),
                'correlation': float(a.corr(b)),
                'overlap_days': overlap,
                'overlap_start': both.index[0].isoformat(),
                'overlap_end': both.index[-1].isoformat(),
            }
            entry.update(_rolling_extremes(a, b, window))
            pairs.append(entry)
    if too_short:
        raise ValueError(
            'Zu wenig gemeinsamer Zeitraum (Mindestmaß '
            f'{min_overlap} Tage) — {"; ".join(too_short)}'
        )
    return pairs


def effective_symbols_from_mean_correlation(n: int, mean_correlation: float) -> float:
    """Effektive Symbolzahl aus der mittleren Paarkorrelation.

    Formel: `N_eff = n / (1 + (n-1) * rho_quer)`.

    Args:
        n: Anzahl der Symbole.
        mean_correlation: Mittlere Paarkorrelation über alle Paare.

    Returns:
        Effektive Symbolzahl. Bei vollständiger Unkorreliertheit gleich `n`, bei
        identischen Reihen gleich 1.

    Raises:
        ValueError: Wenn der Nenner null oder negativ wird (mittlere Korrelation
            stark negativ) — dann ist die Formel nicht anwendbar.
    """
    denominator = 1.0 + (n - 1) * mean_correlation
    if denominator <= 0:
        raise ValueError(
            f'Mittlere Korrelation {mean_correlation:.4f} macht die Formel unbrauchbar '
            f'(Nenner {denominator:.4f} <= 0).'
        )
    return n / denominator


def effective_symbols_from_eigenvalues(correlation: pd.DataFrame) -> float:
    """Effektive Symbolzahl aus den Eigenwerten der Korrelationsmatrix.

    Formel: `N_eff = (Summe lambda)^2 / Summe(lambda^2)`.

    Args:
        correlation: Quadratische, symmetrische Korrelationsmatrix.

    Returns:
        Effektive Symbolzahl. Bei einer Einheitsmatrix gleich `n`, bei durchgehend
        perfekter Korrelation gleich 1.
    """
    eigenvalues = np.linalg.eigvalsh(correlation.to_numpy(dtype='float64'))
    return float(eigenvalues.sum() ** 2 / (eigenvalues ** 2).sum())


def eigenvalues_of(correlation: pd.DataFrame) -> List[float]:
    """Eigenwerte der Korrelationsmatrix, absteigend sortiert."""
    eigenvalues = np.linalg.eigvalsh(correlation.to_numpy(dtype='float64'))
    return [float(v) for v in sorted(eigenvalues, reverse=True)]


def analyze_symbol_correlation(
    daily_close: pd.DataFrame,
    window: int = DEFAULT_WINDOW,
    min_overlap: int = DEFAULT_MIN_OVERLAP,
) -> dict:
    """Vollständige Korrelations-Auswertung über eine Symbolmenge.

    Args:
        daily_close: Tagesschlusskurse, Index = Tage, je Spalte ein Symbol.
        window: Fensterlänge der rollierenden Korrelation in Tagen.
        min_overlap: Mindestanzahl gemeinsamer Tage je Paar.

    Returns:
        Dict mit Abdeckung je Symbol, Korrelationsmatrix, Paar-Statistiken,
        mittlerer Paarkorrelation, beiden effektiven Symbolzahlen und den Eigenwerten.

    Raises:
        ValueError: Bei weniger als zwei Symbolen, unbrauchbaren Kursen, zu kurzer
            Überlappung eines Paares oder unbrauchbarem Nenner der einfachen Formel.
    """
    if daily_close.shape[1] < 2:
        raise ValueError('Für eine Korrelation braucht es mindestens zwei Symbole.')
    if window < 2:
        raise ValueError('Das rollende Fenster muss mindestens 2 Tage umfassen.')

    returns = daily_log_returns(daily_close)
    pairs = pair_statistics(returns, window=window, min_overlap=min_overlap)

    # Paarweise Korrelationsmatrix: pandas verwendet je Spaltenpaar nur die Zeilen,
    # in denen beide Werte vorhanden sind — dieselbe Überlappungslogik wie oben.
    correlation = returns.corr(min_periods=min_overlap)

    n = int(daily_close.shape[1])
    mean_correlation = float(np.mean([p['correlation'] for p in pairs]))
    return {
        'symbols': [str(c) for c in daily_close.columns],
        'window': int(window),
        'min_overlap': int(min_overlap),
        'coverage': _coverage(daily_close),
        'correlation_matrix': {
            str(row): {str(col): _none_if_nan(correlation.at[row, col]) for col in correlation.columns}
            for row in correlation.index
        },
        'pairs': pairs,
        'mean_correlation': mean_correlation,
        'effective_symbols_mean_corr': effective_symbols_from_mean_correlation(n, mean_correlation),
        'effective_symbols_eigenvalues': effective_symbols_from_eigenvalues(correlation),
        'eigenvalues': eigenvalues_of(correlation),
    }


def _none_if_nan(value: float) -> Optional[float]:
    """Wandelt NaN in None, damit die Antwort gültiges JSON bleibt."""
    number = float(value)
    return None if math.isnan(number) else number
