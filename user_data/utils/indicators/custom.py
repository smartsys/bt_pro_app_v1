"""
Custom Technical Indicators

Custom VectorBT PRO indicators and dataframe utilities.
"""

from vectorbtpro import *
from numba import njit
import numpy as np
import talib


def align_dataframes(dataframes):
    """
    Align multiple dataframes to same index.

    Args:
        dataframes: List of pandas DataFrames

    Returns:
        List of aligned DataFrames

    Raises:
        ValueError: If dataframes list is empty
    """
    if not dataframes:
        raise ValueError("Die Liste der DataFrames darf nicht leer sein.")

    # Beginne mit dem ersten DataFrame in der Liste
    aligned_df = dataframes[0]

    # Iteriere über die restlichen DataFrames und richte sie am ersten aus
    for df in dataframes[1:]:
        aligned_df, df = aligned_df.align(df, join='inner')

    # Richte alle DataFrames an den Indizes und Spalten des ausgerichteten DataFrames aus
    aligned_list = [aligned_df]
    for df in dataframes[1:]:
        aligned_df, df = aligned_df.align(df, join='inner')
        aligned_list.append(df)

    return aligned_list


def dws_fast_sma_inc(src, length=2, multiplier=2):
    """
    Custom Fast SMA indicator implementation.

    Args:
        src: Source data array
        length: SMA length period (default: 2)
        multiplier: Multiplikator (default: 2)

    Returns:
        numpy array with WSMA values
    """
    r_values = []
    wsma_values = []

    # SMA
    sma_values = talib.SMA(src, timeperiod=length)

    for i in range(len(src)):
        if i < length:
            r_values.append(np.nan)
            wsma_values.append(np.nan)
        else:
            s = 0.0
            for j in range(length):
                s += ((length - (j * 2 + 1)) / 2) * src[i - j]
            r_value = multiplier * s / (length * (length + 1))
            r_values.append(r_value)

            # WSM berechnen
            wsma_value = r_value + sma_values[i]
            wsma_values.append(wsma_value)

    # Gebe numpy array zurück - VBT handled den Index automatisch
    return np.array(wsma_values)


# Erstelle den dwsFastSMA Indikator
dwsFastSMA = vbt.IF(
    class_name='dwsFASTSMA',
    input_names=['source'],
    param_names=['length', 'multiplier'],
    output_names=['result'],
).with_apply_func(dws_fast_sma_inc, takes_1d=True)


def vwma_pct_below_talib_inc(src_series, volume_series, vwma_len=10, below_pct=3):
    """
    Volume Weighted Moving Average with percentage below.

    Args:
        src_series: Source price data
        volume_series: Volume data
        vwma_len: VWMA length (default: 10)
        below_pct: Percentage below VWMA (default: 3)

    Returns:
        VWMA adjusted by percentage
    """
    vwma = talib.SUM(src_series * volume_series, timeperiod=vwma_len) / talib.SUM(volume_series, timeperiod=vwma_len)
    return vwma - vwma * (below_pct / 100)


# Erstelle den dwsVWMA Indikator
dwsVWMA = vbt.IF(
    class_name='dwsVWMA',
    input_names=['source', 'volume'],
    param_names=['length', 'below_pct'],
    output_names=['result'],
).with_apply_func(vwma_pct_below_talib_inc, takes_1d=True)


def vwma_band_inc(src_series, volume_series, below_series, length=10):
    """Volume Weighted Moving Average mit dynamischer Threshold-Serie.

    Im Unterschied zu dwsVWMA ist der Abstand unter dem VWMA keine Konstante,
    sondern eine Zeitreihe (z.B. ATR oder eine feste Prozent-Serie). Damit
    lässt sich der Entry-Threshold im Playground per Indikator-Chaining
    dynamisch berechnen, ohne die Factory-Parameter zu ändern.

    Args:
        src_series: Preis-Serie (typischerweise Close oder der Output eines
            geglätteten Indikators wie Fast SMA).
        volume_series: Volumen-Serie.
        below_series: Zeitreihe, die pro Bar den absoluten Abstand unterhalb
            des VWMA definiert. Gleicher Einheit wie src.
        length: VWMA-Fensterlänge in Bars (Default 10).

    Returns:
        numpy-Array mit der Threshold-Serie `vwma - below_series`.
    """
    vwma = talib.SUM(src_series * volume_series, timeperiod=length) / talib.SUM(volume_series, timeperiod=length)
    return vwma - below_series


# Erstelle den dwsVWMABand Indikator — below_pct wandert von Param zu Input
dwsVWMABand = vbt.IF(
    class_name='dwsVWMABand',
    input_names=['source', 'volume', 'below_series'],
    param_names=['length'],
    output_names=['result'],
).with_apply_func(vwma_band_inc, takes_1d=True)


def asset_dd_inc(src_series, window=200):
    """Drawdown einer Zeitreihe vom rollenden Peak.

    Args:
        src_series: Preisserie (typischerweise Close).
        window: Lookback-Fenster für den rollenden Peak (Default 200 Balken).

    Returns:
        numpy-Array mit Drawdown in Prozent (0.0 = am Peak, -0.30 = 30% unter Peak).
        Werte sind immer <= 0.
    """
    series = np.asarray(src_series, dtype=float)
    n = len(series)
    result = np.full(n, np.nan)
    if n == 0:
        return result
    for i in range(n):
        start = max(0, i - window + 1)
        peak = np.max(series[start:i + 1])
        if peak > 0:
            result[i] = (series[i] - peak) / peak
        else:
            result[i] = 0.0
    return result


# dwsAssetDD — Drawdown eines Assets vom rollenden Peak
# Nützlich als Regime-Filter: "handle nur, wenn Asset nicht zu weit unter seinem Hoch"
dwsAssetDD = vbt.IF(
    class_name='dwsAssetDD',
    input_names=['source'],
    param_names=['window'],
    output_names=['result'],
).with_apply_func(asset_dd_inc, takes_1d=True)


def volume_ratio_inc(volume_series, window=20):
    """Verhältnis des aktuellen Volumens zum rollenden Durchschnitt.

    Nützlich als Confirmation-Filter: "Entry nur wenn Volumen über dem
    N-Balken-Durchschnitt liegt". Ein Wert > 1.0 heißt "überdurchschnittliches
    Volumen", < 1.0 heißt "unterdurchschnittlich".

    Args:
        volume_series: Volumen-Zeitreihe.
        window: Lookback-Fenster für den rollenden Durchschnitt (Default 20).

    Returns:
        numpy-Array mit dem Volumen-Ratio pro Balken. NaN in den ersten
        `window` Balken (Warmup).
    """
    series = np.asarray(volume_series, dtype=float)
    n = len(series)
    result = np.full(n, np.nan)
    for i in range(n):
        start = max(0, i - window + 1)
        avg = np.mean(series[start:i + 1])
        if avg > 0:
            result[i] = series[i] / avg
        else:
            result[i] = np.nan
    return result


# dwsVolumeRatio — Verhältnis des aktuellen Volumens zum rollenden Durchschnitt
# Nützlich als Confirmation-Filter: Entry nur bei überdurchschnittlichem Volumen
dwsVolumeRatio = vbt.IF(
    class_name='dwsVolumeRatio',
    input_names=['volume'],
    param_names=['window'],
    output_names=['result'],
).with_apply_func(volume_ratio_inc, takes_1d=True)


def crossover_inc(series_a, series_b):
    """Bidirektionale Cross-Detektion zweier Zeitreihen.

    Emuliert Pines `ta.cross(a, b)`: feuert an jedem Bar an dem die beiden
    Serien das Vorzeichen ihrer Differenz wechseln — also sowohl wenn a über
    b kreuzt als auch wenn a unter b kreuzt. Nützlich als Entry-Primitive
    für Mean-Reversion-Strategien, die sowohl das Dip-Signal (Preis fällt
    unter Schwelle) als auch das Bounce-Signal (Preis steigt von unten
    zurück über Schwelle) mitnehmen wollen.

    Args:
        series_a: Erste Zeitreihe.
        series_b: Zweite Zeitreihe (typischerweise der Schwellwert).

    Returns:
        numpy-Array mit 1.0 an Bars wo ein Crossover stattgefunden hat,
        0.0 sonst. Der erste Bar ist immer 0.0 (kein Vorbar-Vergleich möglich).
    """
    a = np.asarray(series_a, dtype=float)
    b = np.asarray(series_b, dtype=float)
    n = len(a)
    result = np.zeros(n, dtype=float)
    for i in range(1, n):
        if np.isnan(a[i]) or np.isnan(b[i]) or np.isnan(a[i-1]) or np.isnan(b[i-1]):
            continue
        diff_prev = a[i-1] - b[i-1]
        diff_now = a[i] - b[i]
        # Vorzeichenwechsel = Crossover (in beide Richtungen)
        if (diff_prev > 0 and diff_now <= 0) or (diff_prev < 0 and diff_now >= 0):
            result[i] = 1.0
    return result


# dwsCrossover — Bidirektionaler Cross-Detektor, emuliert Pine ta.cross
# Output 1.0 an Cross-Bars, 0.0 sonst. Beide Richtungen (up und down) zählen.
dwsCrossover = vbt.IF(
    class_name='dwsCrossover',
    input_names=['series_a', 'series_b'],
    param_names=[],
    output_names=['result'],
).with_apply_func(crossover_inc, takes_1d=True)


@njit
def _pine_ema_nb(x, length):
    """EMA exakt wie TradingView Pine `ta.ema`.

    alpha = 2/(length+1), ema = alpha*src + (1-alpha)*ema[1]. Der erste gültige
    Wert wird mit dem Quellwert selbst geseedet (NICHT mit SMA wie talib.EMA) —
    dadurch stimmt das Ergebnis ab dem ersten Balken mit Pine überein. NaN-Werte
    werden übersprungen (wie Pine `na`-Handling).
    """
    n = x.shape[0]
    out = np.full(n, np.nan)
    alpha = 2.0 / (length + 1.0)
    prev = np.nan
    for i in range(n):
        v = x[i]
        if np.isnan(v):
            out[i] = np.nan
            continue
        prev = v if np.isnan(prev) else alpha * v + (1.0 - alpha) * prev
        out[i] = prev
    return out


def smi_inc(high, low, close, k_length=10, smooth1=3, smooth2=3, signal=3):
    """Stochastic Momentum Index (SMI) nach William Blau.

    Misst, wo der Schlusskurs relativ zur Mitte der High-Low-Range der letzten
    k_length Balken liegt — doppelt EMA-geglättet. Skaliert auf etwa [-100, 100]:
    > +40 gilt als überkauft, < -40 als überverkauft (TAP-Filter). Glatter als
    der klassische Stochastik-Oszillator.

    Formel und Defaults entsprechen dem TradingView-Standard-SMI:
    SMI = 100 * EMA(EMA(close - Mitte, D), D) / (0.5 * EMA(EMA(Range, D), D)),
    mit Percent-K-Length = 10 und Glättung D = 3.

    Args:
        high: High-Serie.
        low: Low-Serie.
        close: Close-Serie.
        k_length: Lookback für Highest-High / Lowest-Low (Percent K Length, Default 10).
        smooth1: Erste EMA-Glättung von Distanz und Range (Default 3).
        smooth2: Zweite EMA-Glättung (Default 3).
        signal: EMA-Länge der Signallinie auf dem SMI (Default 3).

    Returns:
        Tuple (smi, signal_line). SMI in etwa [-100, 100], Signallinie als EMA davon.
    """
    high = np.ascontiguousarray(np.asarray(high, dtype=np.float64))
    low = np.ascontiguousarray(np.asarray(low, dtype=np.float64))
    close = np.ascontiguousarray(np.asarray(close, dtype=np.float64))

    hh = talib.MAX(high, timeperiod=int(k_length))
    ll = talib.MIN(low, timeperiod=int(k_length))
    center = (hh + ll) / 2.0
    rel = close - center          # Distanz zur Range-Mitte
    rng = hh - ll                 # Spannweite

    # Doppelte Pine-EMA-Glättung (ta.ema-Seed) — exakt wie der TradingView-SMI
    smooth_rel = _pine_ema_nb(_pine_ema_nb(rel, int(smooth1)), int(smooth2))
    smooth_rng = _pine_ema_nb(_pine_ema_nb(rng, int(smooth1)), int(smooth2))

    with np.errstate(divide='ignore', invalid='ignore'):
        smi = 100.0 * smooth_rel / (0.5 * smooth_rng)
    smi = np.where(smooth_rng > 0.0, smi, np.nan)

    sig = _pine_ema_nb(np.ascontiguousarray(smi), int(signal))
    return smi, sig


# dwsSMI — Stochastic Momentum Index nach Blau (High/Low-Range-basiert, Skala ~+-100).
# Oszillator (Subplot). Output smi (Hauptlinie) + signal (EMA-Signallinie).
# Für den TAP-Filter: smi > 40 (überkauft -> Short) bzw. smi < -40 (überverkauft -> Long).
dwsSMI = vbt.IF(
    class_name='dwsSMI',
    input_names=['high', 'low', 'close'],
    param_names=['k_length', 'smooth1', 'smooth2', 'signal'],
    output_names=['smi', 'signal'],
).with_apply_func(smi_inc, takes_1d=True)


def const_inc(source, value=0.0):
    """Konstanter Indikator: liefert für jeden Balken denselben Wert.

    Der Input `source` dient ausschließlich als Längen-/Index-Vorlage — sein
    Inhalt geht nicht in die Berechnung ein. Zweck: eine Regel-Schwelle, die
    heute eine feste rhs-Konstante ist (z.B. `adx > 20`), wird über den
    Umweg `indicator:adx > indicator:const` sweep-fähig, indem `value` als
    Parameter-Achse (vbt.Param) im Multiparameter-Lauf variiert wird.

    Args:
        source: Beliebige Zeitreihe (typischerweise Close), nur für Länge/Index.
        value: Der konstante Wert, den jeder Balken erhält (Default 0.0).

    Returns:
        numpy-Array der Länge len(source), komplett gefüllt mit `value`.
    """
    return np.full(len(source), float(value))


# dwsConst — generischer Konstanten-Indikator. Macht Regel-Schwellen sweep-fähig:
# statt fester rhs-Konstante `adx > 20` schreibt man `adx > const` und variiert
# const.value im IndicatorConfig-Raster (z.B. [15, 20, 25]). Ein Baustein deckt
# alle Schwellen ab (ADX, AssetDD, ...). Struktur wie dwsAssetDD: ein Längen-Input
# plus ein Param, Output `result`.
dwsConst = vbt.IF(
    class_name='dwsConst',
    input_names=['source'],
    param_names=['value'],
    output_names=['result'],
).with_apply_func(const_inc, takes_1d=True)
