"""
Custom Technical Indicators

Custom VectorBT PRO indicators and dataframe utilities.
"""

from vectorbtpro import *
from vectorbtpro.indicators.nb import pivot_info_1d_nb
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
def _kuhle_ok(base_val, base_idx, slope, opp_idx, opp_val, lo_idx, hi_idx,
              peak_sign, dip_min_atr, atr_i):
    """Prueft, ob die Kuhle (Gegen-Pivot) zwischen zwei Touches tief genug ist.

    base_val/base_idx/slope definieren die Linie, opp_idx/opp_val ist der zuletzt
    bestätigte Gegen-Pivot (Boden/Decke des Rücksetzers). Der Gegen-Pivot muss im
    offenen Intervall (lo_idx, hi_idx) zwischen den beiden Touch-Pivots liegen.
    Tiefe = Abstand des Gegen-Pivots zur Linie in Preis-Einheiten; gefordert
    >= dip_min_atr * ATR. dip_min_atr <= 0 schaltet den Filter aus.
    """
    if dip_min_atr <= 0.0:
        return True
    if not (lo_idx < opp_idx < hi_idx):
        return False
    line_opp = base_val + slope * (opp_idx - base_idx)
    depth = (line_opp - opp_val) if peak_sign == 1 else (opp_val - line_opp)
    return depth >= dip_min_atr * atr_i


@njit
def _trendline_touch_side_nb(high, low, close, atr, conf_pivot, conf_idx, peak_sign,
                             touch_tol_atr, break_tol_atr, dev_max_atr,
                             min_touch, max_touch, min_bars_between, dip_min_atr):
    """Eine Seite der Trendlinien-Touch-Erkennung (kausal, zustandsbehaftet).

    peak_sign=+1: fallende Widerstandslinie aus Pivot-Hochs (Short-Kandidat).
    peak_sign=-1: steigende Stützlinie aus Pivot-Tiefs (Long-Kandidat).

    Linie aus den letzten zwei bestätigten Pivots, verlängert pro Bar. Ein Touch
    zählt nur, wenn ein weiteres gleichsinniges, bestätigtes Pivot die Linie
    innerhalb touch_tol_atr*ATR trifft. Zwei zusätzliche Filter trennen echte
    Trendlinien von Mini-Swings:

    - min_bars_between: Mindest-Bar-Abstand zwischen zwei aufeinanderfolgenden
      Touch-Pivots (auch zwischen Anker 1 und 2). Zu eng beieinanderliegende
      Pivots zählen nicht.
    - dip_min_atr: Mindest-Tiefe der "Kuhle" (des Rücksetzers) zwischen zwei
      Touches in ATR-Einheiten. Gemessen am Low des bestätigten Gegen-Pivots
      relativ zur Linie (peak_sign=1: Linie - Low; peak_sign=-1: High - Linie).
      0 = Filter aus (dann wirkt nur die Zigzag-Schwelle up_th/down_th).

    Pivot 1+2 = Touch 1+2, Signal nur bei Touch min_touch..max_touch und Abpraller.
    Bruch wenn Close die Linie um break_tol_atr*ATR überschreitet -> Linie verworfen.

    Returns:
        (line, signal, touch): Linienwert pro Bar (NaN wenn keine aktive Linie),
        1.0 an Signal-Bars (sonst 0.0) und die laufende Touch-Nummer am jeweiligen
        Pivot-Bar (sonst NaN). Touch 1+2 sind die zwei Anker-Pivots der Linie,
        Touch 3+ weitere gleichsinnige Pivots an der Linie. Nur Touches 1..max_touch
        werden markiert. Signal kausal am Pivot-Bestaetigungs-Bar. Zaehlung startet pro Linie neu.
    """
    n = close.shape[0]
    line_out = np.full(n, np.nan)
    sig_out = np.zeros(n, dtype=np.float64)
    touch_out = np.full(n, np.nan)

    prev_pidx = -1
    prev_pval = np.nan
    p1_idx = -1
    p1_val = np.nan
    slope = np.nan
    line_active = False
    touch_count = 0
    last_conf = -1
    last_touch_idx = -1
    # Letztes bestätigtes Gegen-Pivot = Boden/Decke der Kuhle zwischen zwei Touches
    last_opp_idx = -1
    last_opp_val = np.nan

    for i in range(n):
        atr_i = atr[i]
        if np.isnan(atr_i) or atr_i <= 0.0:
            continue

        # Neues bestätigtes Pivot an diesem Bar?
        ci = conf_idx[i]
        if ci != last_conf and ci >= 0:
            last_conf = ci
            sign = conf_pivot[i]
            if sign == -peak_sign:
                # Gegen-Pivot merken (tiefster/hoechster Punkt des Ruecksetzers).
                last_opp_idx = ci
                last_opp_val = low[ci] if peak_sign == 1 else high[ci]
            elif sign == peak_sign:
                new_idx = ci
                new_val = high[ci] if peak_sign == 1 else low[ci]
                if not line_active:
                    if (not np.isnan(prev_pval)) and prev_pidx != new_idx:
                        s = (new_val - prev_pval) / (new_idx - prev_pidx)
                        # Widerstand: fallend (s<0); Stütze: steigend (s>0)
                        far_enough = (new_idx - prev_pidx) >= min_bars_between
                        valid_dir = (peak_sign == 1 and s < 0.0) or (peak_sign == -1 and s > 0.0)
                        if valid_dir and far_enough and _kuhle_ok(
                            prev_pval, prev_pidx, s, last_opp_idx, last_opp_val,
                            prev_pidx, new_idx, peak_sign, dip_min_atr, atr_i
                        ):
                            p1_idx = prev_pidx
                            p1_val = prev_pval
                            slope = s
                            line_active = True
                            touch_count = 2
                            last_touch_idx = new_idx
                            # Anker-Pivots als Touch 1+2 an ihren Bar-Indizes markieren
                            touch_out[p1_idx] = 1.0
                            touch_out[new_idx] = 2.0
                else:
                    # Linie aktiv: trifft dieses bestätigte gleichsinnige Pivot die Linie?
                    line_at = p1_val + slope * (new_idx - p1_idx)
                    breach = (new_val - line_at) if peak_sign == 1 else (line_at - new_val)
                    reject = close[new_idx] < line_at if peak_sign == 1 else close[new_idx] > line_at
                    far_enough = (new_idx - last_touch_idx) >= min_bars_between
                    if breach > dev_max_atr * atr_i:
                        # Pivot durchsticht die Linie zu weit -> Linie ungueltig
                        line_active = False
                    elif (abs(new_val - line_at) <= touch_tol_atr * atr_i and far_enough
                          and _kuhle_ok(p1_val, p1_idx, slope, last_opp_idx, last_opp_val,
                                        last_touch_idx, new_idx, peak_sign, dip_min_atr, atr_i)):
                        # Gueltiger Touch: gleichsinniges Pivot an der Linie, Mindestabstand
                        # und Kuhle-Tiefe seit dem letzten Touch erfuellt.
                        touch_count += 1
                        last_touch_idx = new_idx
                        if touch_count <= max_touch:
                            touch_out[new_idx] = float(touch_count)
                        # Signal kausal am Bestaetigungs-Bar i (das Pivot ist erst hier bekannt)
                        if reject and min_touch <= touch_count <= max_touch:
                            sig_out[i] = 1.0
                    # sonst: Pivot unter der Linie/zu nah/zu flache Kuhle -> Linie bleibt aktiv
                prev_pidx = new_idx
                prev_pval = new_val

        if not line_active:
            continue

        line_i = p1_val + slope * (i - p1_idx)
        line_out[i] = line_i

        # Bruch? (Close laeuft zu weit ueber/unter die Linie -> Linie verworfen).
        # Touches werden nicht mehr hier, sondern pivot-basiert oben gezaehlt.
        if peak_sign == 1:
            if close[i] > line_i + break_tol_atr * atr_i:
                line_active = False
        else:
            if close[i] < line_i - break_tol_atr * atr_i:
                line_active = False

    return line_out, sig_out, touch_out


def trendline_touch_inc(high, low, close, up_th=0.05, down_th=0.05, atr_length=14,
                        touch_tol_atr=0.5, break_tol_atr=0.5, dev_max_atr=0.75,
                        min_touch=3, max_touch=4, min_bars_between=0, dip_min_atr=0.0):
    """Trendlinien-Touch-Indikator (TAP-Methode).

    Erkennt valide Trendlinien aus bestätigten Pivots (VBT pivot_info_1d_nb) und
    meldet die 3./4. Berührung mit Abpraller als Signal — Short an einer fallenden
    Widerstandslinie, Long an einer steigenden Stützlinie. ATR (talib) liefert die
    Touch-/Bruch-/Devianz-Toleranz. Kausal, kein Look-Ahead.

    Args:
        high: High-Serie.
        low: Low-Serie.
        close: Close-Serie.
        up_th: Pivot-Zigzag-Schwelle für Hochs (0.05 = 5%).
        down_th: Pivot-Zigzag-Schwelle für Tiefs.
        atr_length: ATR-Fensterlänge für die Toleranzen.
        touch_tol_atr: Touch wenn |Preis - Linie| <= touch_tol_atr * ATR.
        break_tol_atr: Bruch wenn Close die Linie um break_tol_atr * ATR überschreitet.
        dev_max_atr: Maximaler Pivot-Durchstich der Linie in ATR-Einheiten.
        min_touch: Niedrigste zählende Berührung für ein Signal (Default 3).
        max_touch: Höchste zählende Berührung für ein Signal (Default 4).
        min_bars_between: Mindest-Bar-Abstand zwischen zwei aufeinanderfolgenden
            Touch-Pivots (0 = aus).
        dip_min_atr: Mindest-Tiefe der Kuhle (Rücksetzer) zwischen zwei Touches in
            ATR-Einheiten (0 = aus).

    Returns:
        Tuple (short_line, long_line, short_signal, long_signal, short_touch, long_touch).
        Linien preisskaliert (NaN ohne aktive Linie), Signale 1.0/0.0, Touch-Outputs tragen
        die laufende Touch-Nummer am Beruehrungs-Bar (sonst NaN) zur Chart-Visualisierung.
    """
    high = np.ascontiguousarray(np.asarray(high, dtype=np.float64))
    low = np.ascontiguousarray(np.asarray(low, dtype=np.float64))
    close = np.ascontiguousarray(np.asarray(close, dtype=np.float64))

    atr = talib.ATR(high, low, close, timeperiod=int(atr_length))
    conf_pivot, conf_idx, _last_pivot, _last_idx = pivot_info_1d_nb(
        high, low, float(up_th), float(down_th)
    )
    conf_idx = conf_idx.astype(np.int64)

    short_line, short_signal, short_touch = _trendline_touch_side_nb(
        high, low, close, atr, conf_pivot, conf_idx, 1,
        touch_tol_atr, break_tol_atr, dev_max_atr, min_touch, max_touch,
        float(min_bars_between), float(dip_min_atr)
    )
    long_line, long_signal, long_touch = _trendline_touch_side_nb(
        high, low, close, atr, conf_pivot, conf_idx, -1,
        touch_tol_atr, break_tol_atr, dev_max_atr, min_touch, max_touch,
        float(min_bars_between), float(dip_min_atr)
    )
    return short_line, long_line, short_signal, long_signal, short_touch, long_touch


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


# dwsTrendlineTouch — TAP-Methode: 3./4. Trendlinien-Berührung mit Abpraller.
# Multi-Output: short_line/long_line (preisskalierte Trendlinien, über dem Chart),
# short_signal/long_signal (1.0 an Entry-Bars). SMI-Filter + Stops liegen außerhalb.
dwsTrendlineTouch = vbt.IF(
    class_name='dwsTrendlineTouch',
    input_names=['high', 'low', 'close'],
    param_names=['up_th', 'down_th', 'atr_length', 'touch_tol_atr',
                 'break_tol_atr', 'dev_max_atr', 'min_touch', 'max_touch',
                 'min_bars_between', 'dip_min_atr'],
    output_names=['short_line', 'long_line', 'short_signal', 'long_signal',
                  'short_touch', 'long_touch'],
).with_apply_func(trendline_touch_inc, takes_1d=True,
                  # Factory-Defaults: macht die neuen Parameter in run() optional,
                  # damit bestehende Setups/Iterationen ohne diese Werte lauffähig bleiben.
                  min_bars_between=0, dip_min_atr=0.0)
