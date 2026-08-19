"""Synthetische Preisreihen durch Bar-Permutation (Nullmodell für den Permutationstest).

Erzeugt aus einer echten OHLCV-Reihe beliebig viele strukturlose Zwillinge: Die
Randverteilung der Bar-Renditen bleibt exakt erhalten, ihre **Reihenfolge** wird
zerstört. Damit misst ein Backtest auf diesen Reihen genau das, was eine Strategie
aus Volatilität, Drift und Verteilungsform allein herausholt — ohne jede zeitliche
Struktur (Trend, Mean Reversion, Autokorrelation, Volatilitäts-Cluster).

**Zerlegung je Bar** (Log-Innenverhältnisse, dimensionslos):

- ``gap`` = log(Open / Vor-Close) — der Übergang zum vorherigen Balken
- ``body`` = log(Close / Open) — die Bewegung innerhalb des Balkens
- ``upper_wick`` = log(High / max(Open, Close)) — immer >= 0
- ``lower_wick`` = log(Low / min(Open, Close)) — immer <= 0

Diese vier Werte bilden **eine Einheit**: Permutiert wird der ganze Balken, nie ein
einzelnes Verhältnis. Deshalb bleibt die Bar-Rendite ``log(Close_t / Close_{t-1})``
= ``gap + body`` als Zahl unversehrt und wechselt nur ihren Platz — die Randverteilung
ist erhalten, nicht bloß angenähert.

**Rekonstruktion** startet beim echten ersten Balken. Bei n Balken sind nur n-1
Einheiten permutierbar (der erste Balken hat keinen Vor-Close), Balken 0 bleibt also
unverändert stehen. Alle weiteren Balken entstehen multiplikativ aus dem jeweils
vorhergehenden synthetischen Close.

**Garantien** (jede in tests/test_synthetic_series.py abgesichert):

1. OHLC-Konsistenz je Balken: High >= max(O, C) >= min(O, C) >= Low. Folgt direkt aus
   den Vorzeichen der Docht-Verhältnisse.
2. Identische Länge und identischer Zeitindex wie die echte Reihe.
3. Erhaltene Randverteilung: die sortierten Log-Bar-Renditen sind identisch (bis auf
   Gleitkomma-Rundung aus log/exp, relativ ~1e-12).
4. Determinismus je Seed; verschiedene Seeds liefern verschiedene Reihen.

Nicht-Preis-Spalten (Volume und alles Weitere) wandern mit ihrem Balken mit — sie
werden nicht neu berechnet, sondern nur umsortiert.

**Ausgabeform** ist ein Klon des Eingabe-``vbt.Data`` (via ``replace(data=...)``, das
Idiom, das ``Data.resample`` selbst benutzt). Der Klon behält Wrapper, Zeitindex,
Feature-Config und Symbol-Struktur — dadurch funktionieren ``get('Close')`` und
``resample(tf)`` ohne Sonderweg, und der Spec-Runner nimmt die Reihe wie echte Daten.

Bei mehreren Symbolen wird **dieselbe** Permutation auf alle Symbole angewandt. Der
gleichzeitige Querschnitt bleibt damit zusammen (Symbol A und B tauschen ihren
Balken 500 gemeinsam gegen Balken 17); nur die Zeitachse wird zerstört.

Das Modul importiert absichtlich kein vectorbtpro: es spricht das Data-Objekt nur über
``dict_type``/``replace`` an und bleibt damit für die reine Numerik ohne vbt testbar.

**Zwei Vorbehalte, die in jede Deutung gehören** (Belege und Zahlen in
``documentation/knowledge/signifikanztest.md``):

1. **Balken 0 bleibt unpermutiert** (siehe „Rekonstruktion" oben). Bei den üblichen
   Reihenlängen von Tausenden Balken ist das ein Anteil unter 0,1 Prozent und ohne Belang;
   bei sehr kurzen Reihen wäre es zu bedenken.
2. **Das Nullmodell sieht Look-ahead-Bias nicht.** Eine Strategie, die in die Zukunft
   schaut, wird auf jeder synthetischen Reihe neu gerechnet und schaut dort in die
   *synthetische* Zukunft — ihr Vorteil wandert vollständig in die Null-Verteilung. Bei
   der Kalibrierung bestätigt: ``dwsLookaheadOracle`` liegt mit seinem echten Sharpe
   im Mittelfeld der Null-Verteilung und wird nicht als signifikant ausgewiesen.

**Kalibrierung: beide Kontrollen bestanden.** Negativkontrolle ``dwsRandomEntry``
(10 Indikator-Seeds, N = 99): 0 von 10 p-Werten unter 0,10. Positivkontrolle
mit eingebautem Momentum (:mod:`user_data.utils.analysis.momentum_series` plus
SMA-Trendfolge, 3 Daten- und 3 Permutations-Seeds, N = 99): p = 0,01 in jeder Messung,
auf allen drei Metriken. Beide Gegenproben unauffällig.
"""

from typing import Any, Iterator, NamedTuple, Optional, Tuple

import numpy as np
import pandas as pd

# Kanonische Preis-Spalten. Die Suche im DataFrame läuft case-insensitiv, weil die
# HDF5-Quelle 'Open'/'High'/... liefert, andere Quellen aber kleingeschrieben.
PRICE_FEATURES = ('open', 'high', 'low', 'close')

# Toleranz für die Konsistenzprüfung der ECHTEN Reihe (Log-Skala). Ein exakt
# anliegender Docht ergibt 0.0; nur Gleitkomma-Rauschen darf darunter liegen.
CONSISTENCY_TOLERANCE = 1e-12


class BarComponents(NamedTuple):
    """Die Log-Innenverhältnisse aller permutierbaren Balken.

    Alle vier Arrays haben die Länge n-1 und sind positionsgleich indiziert: Element i
    gehört zu Balken i+1 der Originalreihe (Balken 0 hat keinen Vor-Close und ist damit
    nicht permutierbar).
    """

    gap: np.ndarray
    body: np.ndarray
    upper_wick: np.ndarray
    lower_wick: np.ndarray


def _resolve_price_columns(frame: pd.DataFrame) -> dict:
    """Ordnet den kanonischen Preis-Namen die echten Spalten-Labels zu.

    Args:
        frame: OHLCV-DataFrame.

    Returns:
        Dict kanonischer Name ('open', ...) -> Spalten-Label im DataFrame.

    Raises:
        ValueError: Wenn eine Preis-Spalte fehlt oder mehrfach vorkommt.
    """
    mapping: dict = {}
    for feature in PRICE_FEATURES:
        matches = [col for col in frame.columns if str(col).strip().lower() == feature]
        if len(matches) != 1:
            raise ValueError(
                f"Preis-Spalte '{feature}' ist nicht eindeutig auffindbar "
                f"(gefunden: {matches}). Vorhandene Spalten: {list(frame.columns)}"
            )
        mapping[feature] = matches[0]
    return mapping


def _price_array(frame: pd.DataFrame, column: Any, label: str) -> np.ndarray:
    """Holt eine Preis-Spalte als float-Array und prüft sie auf Verwendbarkeit.

    Args:
        frame: OHLCV-DataFrame.
        column: Spalten-Label im DataFrame.
        label: Kanonischer Name für die Fehlermeldung.

    Returns:
        Float-Array der Spalte.

    Raises:
        ValueError: Bei NaN oder nicht-positiven Preisen — der Logarithmus wäre dort
            nicht definiert. Sichtbarer Abbruch statt stillem Überspringen.
    """
    values = np.asarray(frame[column].values, dtype=float)
    n_nan = int(np.isnan(values).sum())
    if n_nan > 0:
        raise ValueError(
            f"Preis-Spalte '{label}' enthält {n_nan} NaN-Werte. Die Bar-Zerlegung "
            f"braucht eine lückenlose Reihe (Lücken vorher bereinigen)."
        )
    n_bad = int((values <= 0.0).sum())
    if n_bad > 0:
        raise ValueError(
            f"Preis-Spalte '{label}' enthält {n_bad} Werte <= 0. Die Log-Zerlegung "
            f"setzt strikt positive Preise voraus."
        )
    return values


def decompose_bars(frame: pd.DataFrame) -> BarComponents:
    """Zerlegt eine OHLCV-Reihe in die Log-Innenverhältnisse je Balken.

    Prüft zugleich die Konsistenz der **echten** Reihe: Ein Balken mit High unter
    max(Open, Close) oder Low über min(Open, Close) würde negative bzw. positive
    Docht-Verhältnisse liefern und die Konsistenz-Garantie der synthetischen Reihe
    aushebeln. Solche Balken brechen den Aufruf ab, statt den Defekt weiterzutragen.

    Args:
        frame: OHLCV-DataFrame mit den Spalten Open/High/Low/Close (case-insensitiv).

    Returns:
        BarComponents mit je n-1 Werten.

    Raises:
        ValueError: Bei zu kurzer Reihe, fehlenden Spalten, unbrauchbaren Preisen oder
            inkonsistenten Balken in der echten Reihe.
    """
    n_bars = len(frame)
    if n_bars < 3:
        raise ValueError(
            f"Die Reihe hat nur {n_bars} Balken. Für eine Permutation braucht es "
            f"mindestens 3 Balken (Balken 0 bleibt als Startpunkt stehen)."
        )

    columns = _resolve_price_columns(frame)
    open_values = _price_array(frame, columns['open'], 'open')
    high_values = _price_array(frame, columns['high'], 'high')
    low_values = _price_array(frame, columns['low'], 'low')
    close_values = _price_array(frame, columns['close'], 'close')

    log_open = np.log(open_values)
    log_high = np.log(high_values)
    log_low = np.log(low_values)
    log_close = np.log(close_values)

    body_top = np.maximum(log_open, log_close)
    body_bottom = np.minimum(log_open, log_close)
    upper_all = log_high - body_top
    lower_all = log_low - body_bottom

    n_broken = int((upper_all < -CONSISTENCY_TOLERANCE).sum() + (lower_all > CONSISTENCY_TOLERANCE).sum())
    if n_broken > 0:
        raise ValueError(
            f"Die echte Reihe enthält {n_broken} inkonsistente Balken (High unter "
            f"max(Open, Close) oder Low über min(Open, Close)). Aus solchen Balken "
            f"lässt sich keine konsistente synthetische Reihe bauen."
        )

    # Ab Balken 1: gap braucht den Vor-Close, deshalb entfällt Balken 0 überall.
    return BarComponents(
        gap=log_open[1:] - log_close[:-1],
        body=log_close[1:] - log_open[1:],
        # Dochte auf 0 begrenzt, damit Gleitkomma-Rauschen die Vorzeichen-Garantie
        # (und damit die OHLC-Konsistenz der Rekonstruktion) nicht kippt.
        upper_wick=np.maximum(upper_all[1:], 0.0),
        lower_wick=np.minimum(lower_all[1:], 0.0),
    )


def permutation_order(n_bars: int, seed: int) -> np.ndarray:
    """Zieht die Permutation der n-1 permutierbaren Balken-Einheiten.

    Args:
        n_bars: Anzahl Balken der echten Reihe.
        seed: Startwert des Zufallsgenerators (gleicher Seed = gleiche Reihenfolge).

    Returns:
        Integer-Array der Länge n_bars-1: eine Permutation von 0 .. n_bars-2. Element i
        nennt die Quell-Einheit für den synthetischen Balken i+1.

    Raises:
        ValueError: Wenn n_bars kleiner als 3 ist.
    """
    if n_bars < 3:
        raise ValueError(f"n_bars muss >= 3 sein, ist {n_bars}")
    rng = np.random.default_rng(seed)
    return rng.permutation(n_bars - 1)


def reconstruct_frame(
    frame: pd.DataFrame,
    components: BarComponents,
    order: np.ndarray,
) -> pd.DataFrame:
    """Baut die synthetische OHLCV-Reihe aus permutierten Balken-Einheiten.

    Balken 0 wird unverändert übernommen (echter Startpreis). Ab Balken 1 wird
    multiplikativ fortgeschrieben: Open aus dem Vor-Close plus Gap, Close aus Open plus
    Body, die Dochte an den Körper angehängt. Nicht-Preis-Spalten (Volume und weitere)
    übernehmen den Wert ihres Quell-Balkens.

    Args:
        frame: Echte OHLCV-Reihe (liefert Startpreis, Zeitindex, Spalten-Layout).
        components: Zerlegung aus `decompose_bars`.
        order: Permutation aus `permutation_order`.

    Returns:
        DataFrame mit identischem Index, identischen Spalten und identischen dtypes der
        Nicht-Preis-Spalten.

    Raises:
        ValueError: Wenn `order` nicht zur Reihenlänge passt.
    """
    n_bars = len(frame)
    order = np.asarray(order, dtype=np.int64)
    if order.shape != (n_bars - 1,):
        raise ValueError(
            f"order hat die Länge {order.shape}, erwartet wird ({n_bars - 1},) "
            f"— eine Einheit je Balken ab Balken 1."
        )

    columns = _resolve_price_columns(frame)
    close_start = float(frame[columns['close']].iloc[0])

    gap = components.gap[order]
    body = components.body[order]
    upper = components.upper_wick[order]
    lower = components.lower_wick[order]

    # Log-Preise vektorisiert fortschreiben: der Close-Pfad ist die Kumulierte der
    # Bar-Renditen (gap + body) ab dem echten Start-Close.
    log_close_start = np.log(close_start)
    log_close = log_close_start + np.cumsum(gap + body)
    log_prev_close = np.concatenate(([log_close_start], log_close[:-1]))
    log_open = log_prev_close + gap
    log_high = np.maximum(log_open, log_close) + upper
    log_low = np.minimum(log_open, log_close) + lower

    def _with_first_bar(canonical: str, tail_log: np.ndarray) -> np.ndarray:
        """Setzt den echten Balken 0 vor den rekonstruierten Rest."""
        head = float(frame[columns[canonical]].iloc[0])
        return np.concatenate(([head], np.exp(tail_log)))

    # Quell-Zeile je Ausgabe-Balken: Balken 0 bleibt sich selbst, ab 1 folgt die
    # Permutation (Einheit i entspricht Original-Balken i+1).
    source_rows = np.concatenate(([0], order + 1))

    result = {}
    for column in frame.columns:
        canonical = str(column).strip().lower()
        if canonical == 'open':
            result[column] = _with_first_bar('open', log_open)
        elif canonical == 'high':
            result[column] = _with_first_bar('high', log_high)
        elif canonical == 'low':
            result[column] = _with_first_bar('low', log_low)
        elif canonical == 'close':
            result[column] = _with_first_bar('close', log_close)
        else:
            # Volume und alle weiteren Spalten wandern mit ihrem Balken mit.
            result[column] = np.asarray(frame[column].values)[source_rows]

    return pd.DataFrame(result, index=frame.index, columns=frame.columns)


def permute_frame(frame: pd.DataFrame, seed: int, order: Optional[np.ndarray] = None) -> pd.DataFrame:
    """Erzeugt eine synthetische OHLCV-Reihe aus einem einzelnen DataFrame.

    Args:
        frame: Echte OHLCV-Reihe.
        seed: Startwert des Zufallsgenerators.
        order: Optional eine bereits gezogene Permutation. Wird gesetzt, wenn mehrere
            Symbole dieselbe Reihenfolge benutzen sollen; dann ist `seed` unbenutzt.

    Returns:
        Synthetische OHLCV-Reihe mit identischem Index und Spalten-Layout.
    """
    components = decompose_bars(frame)
    if order is None:
        order = permutation_order(len(frame), seed)
    return reconstruct_frame(frame, components, order)


def make_synthetic_data(ohlc_data: Any, seed: int) -> Any:
    """Erzeugt einen synthetischen Zwilling eines `vbt.Data`-Objekts.

    Der Rückgabewert ist ein Klon der Eingabe mit ausgetauschten Werten — gleicher Typ,
    gleicher Wrapper, gleicher Zeitindex, gleiche Feature-Config. Damit laufen
    `get('Close')` und `resample(tf)` unverändert, und `run_spec_strategy` nimmt das
    Objekt ohne Sonderbehandlung an.

    Bei mehreren Symbolen bekommen alle Symbole dieselbe Permutation (siehe
    Modul-Docstring).

    Args:
        ohlc_data: Echtes, symbol-orientiertes `vbt.Data` (z.B. aus `load_ohlc_data`).
        seed: Startwert des Zufallsgenerators.

    Returns:
        Ein `vbt.Data`-Objekt desselben Typs mit synthetischen Werten.

    Raises:
        ValueError: Wenn das Data-Objekt nicht symbol-orientiert ist oder ein Symbol
            keinen OHLCV-DataFrame liefert.
    """
    if not getattr(ohlc_data, 'symbol_oriented', False):
        raise ValueError(
            "make_synthetic_data erwartet ein symbol-orientiertes vbt.Data "
            "(so liefert es load_ohlc_data). Feature-orientierte Objekte vorher mit "
            "to_symbol_oriented() umstellen."
        )

    order: Optional[np.ndarray] = None
    new_data = ohlc_data.dict_type()
    for symbol in ohlc_data.symbols:
        frame = ohlc_data.data[symbol]
        if not isinstance(frame, pd.DataFrame):
            raise ValueError(
                f"Symbol {symbol!r} liefert kein DataFrame (Typ {type(frame).__name__}). "
                f"Die Bar-Zerlegung braucht die vollen OHLCV-Spalten."
            )
        if order is None:
            order = permutation_order(len(frame), seed)
        new_data[symbol] = permute_frame(frame, seed, order=order)

    # Idiom aus Data.resample: Werte tauschen, alles andere behalten. Der Wrapper bleibt
    # gültig, weil der Zeitindex per Konstruktion unverändert ist.
    return ohlc_data.replace(data=new_data)


def iter_synthetic_data(
    ohlc_data: Any,
    n_series: int,
    seed: int = 42,
) -> Iterator[Tuple[int, Any]]:
    """Liefert N synthetische Zwillinge als Generator (Seeds `seed` .. `seed + n - 1`).

    Generator statt Liste, damit bei N = 300 nie mehr als eine synthetische Reihe im
    Speicher liegt.

    Args:
        ohlc_data: Echtes, symbol-orientiertes `vbt.Data`.
        n_series: Anzahl der zu erzeugenden Reihen.
        seed: Startwert der Seed-Folge.

    Yields:
        Tupel (verwendeter Seed, synthetisches `vbt.Data`).

    Raises:
        ValueError: Wenn n_series kleiner als 1 ist.
    """
    if n_series < 1:
        raise ValueError(f"n_series muss >= 1 sein, ist {n_series}")
    for i in range(n_series):
        current_seed = seed + i
        yield current_seed, make_synthetic_data(ohlc_data, current_seed)


def bar_log_returns(frame: pd.DataFrame) -> np.ndarray:
    """Log-Bar-Renditen log(Close_t / Close_{t-1}) einer OHLCV-Reihe.

    Hilfsfunktion für die Randverteilungs-Prüfung: Diese Werte sind in der synthetischen
    Reihe dieselbe Menge wie in der echten, nur anders angeordnet.

    Args:
        frame: OHLCV-Reihe.

    Returns:
        Float-Array der Länge n-1.
    """
    columns = _resolve_price_columns(frame)
    close_values = _price_array(frame, columns['close'], 'close')
    return np.diff(np.log(close_values))
