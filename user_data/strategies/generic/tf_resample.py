"""Per-Indikator-Timeframe (tf): native Resample-Quelle + look-ahead-sicheres Realign.

Single Source fuer den Spec-Runner (`build_indicators`) UND den Chart-Playground-Preview
(`compute_indicators`). Beide Pfade muessen identisch resampeln und realignen, damit
"Preview == gespeicherter Lauf" strukturell garantiert ist.

Mechanik (durchgaengig nativ ueber vbt):

  - `resampled_ohlc(ohlc_data, tf)`: `vbt.Data.resample(tf)`. Das Data-Objekt kennt die
    OHLCV-Aggregationsregeln (Open=first / High=max / Low=min / Close=last / Volume=sum)
    ueber seine Feature-Config selbst.
  - `realign_to_index(obj, target_index, freq)`: `obj.vbt.realign_closing(...)`. Nutzt
    rechte Bin-Grenzen fuer Quelle UND Ziel -> look-ahead-sicher (nur eine bereits
    abgeschlossene Kerze fliesst ein). Funktioniert fuer Series UND Multi-Combo-DataFrames
    (alle Param-Spalten bleiben erhalten). Gilt in BEIDE Richtungen:
      * tf -> Basis: Indikator-Output zurueck aufs feine Raster (Portfolio laeuft auf Basis).
      * Basis -> tf: Chaining-Input eines Indikators auf den groeberen Rechen-tf
        (last-in-bucket, derselbe Index wie die tf-OHLCV-Inputs).
  - `validate_tf(tf, base_freq)`: Guard. Downsampling (tf feiner als Basis) wird abgelehnt.
  - `normalize_tf(tf, base_tf)`: leerer / mit Basis identischer tf -> None (kein Resampling).
"""

from typing import Any, Optional

import pandas as pd
import vectorbtpro as vbt


def tf_to_timedelta(tf: str) -> pd.Timedelta:
    """Wandelt einen Timeframe-String ('4h', '1d', '15min', '1w') in ein pd.Timedelta."""
    return pd.Timedelta(vbt.utils.datetime_.to_timedelta(tf))


def normalize_tf(tf: Optional[str], base_tf: Optional[str]) -> Optional[str]:
    """Normalisiert den Ziel-tf: leer / None / gleich Basis-tf -> None (kein Resampling noetig).

    Args:
        tf: Roher Per-Indikator-Timeframe (z.B. '4h', '', None).
        base_tf: Basis-Timeframe der geladenen Kerzen (z.B. '4h'); darf None sein.

    Returns:
        Der getrimmte tf-String, oder None wenn kein Resampling noetig ist.
    """
    if not isinstance(tf, str):
        return None
    trimmed = tf.strip()
    if trimmed == '':
        return None
    if base_tf is not None and trimmed.lower() == (base_tf or '').strip().lower():
        return None
    return trimmed


def validate_tf(tf: str, base_freq: Any) -> None:
    """Lehnt einen Ziel-tf ab, der feiner als der Basis-Timeframe ist (Downsampling).

    Ein Indikator kann nur auf gleichem oder groeberem Timeframe rechnen — feinere Kerzen
    als die geladenen lassen sich nicht erzeugen. Gleicher tf ist ein No-Op (vom Aufrufer
    via `normalize_tf` schon vorher ausgefiltert).

    Args:
        tf: Ziel-Timeframe (z.B. '4h').
        base_freq: Frequenz des Basis-Index (pd.Timedelta, z.B. `ohlc_data.wrapper.freq`).
            None deaktiviert den Check (keine Basis-Frequenz bekannt).

    Raises:
        ValueError: Wenn tf feiner als base_freq ist.
    """
    if base_freq is None:
        return
    target = tf_to_timedelta(tf)
    base = pd.Timedelta(base_freq)
    if target < base:
        raise ValueError(
            f"Per-Indikator-Timeframe '{tf}' ({target}) ist feiner als der Basis-Timeframe "
            f"({base}). Ein Indikator kann nur auf gleichem oder größerem Timeframe rechnen "
            f"(Downsampling der OHLC-Kerzen ist nicht möglich)."
        )


def resampled_ohlc(ohlc_data: Any, tf: str) -> Any:
    """Resampelt ein vbt.Data-Objekt nativ auf den Ziel-Timeframe.

    Das Data-Objekt traegt seine Feature-Config (OHLCV-Aggregationsregeln) bereits, daher
    genuegt ein `.resample(tf)`-Aufruf.

    Args:
        ohlc_data: Konfiguriertes vbt.Data (Feature-Config gesetzt).
        tf: Ziel-Timeframe.

    Returns:
        Das resamplete vbt.Data-Objekt am Ziel-tf-Raster.
    """
    return ohlc_data.resample(tf)


def realign_to_index(obj: Any, target_index: pd.Index, freq: Any = None) -> Any:
    """Realignt eine Series/DataFrame look-ahead-sicher auf einen Ziel-Index.

    Nutzt `realign_closing` (rechte Bin-Grenzen fuer Quelle UND Ziel). Multi-Combo-
    DataFrames behalten alle Param-Spalten. Funktioniert in beide Richtungen
    (tf -> Basis und Basis -> tf).

    Args:
        obj: pandas Series oder DataFrame (mit vbt-Accessor).
        target_index: Ziel-Index, auf den realignt wird.
        freq: Optionale Ziel-Frequenz (pd.Timedelta oder Timeframe-String). None -> aus
            dem Ziel-Index abgeleitet.

    Returns:
        Series/DataFrame auf dem Ziel-Index (look-ahead-sicher).
    """
    return obj.vbt.realign_closing(target_index, freq=freq)
