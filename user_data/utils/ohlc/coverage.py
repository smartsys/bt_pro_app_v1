"""Vorhandene OHLC-Datenspanne je Symbol ermitteln.

Liest ausschließlich die Index-Ränder aus der HDF5-Datei (erste und letzte Kerze)
— ohne die OHLC-Werte zu laden. Grundlage der Plan-Validierung der
Walk-Forward-Kette: ein Fold-Fenster außerhalb der vorhandenen Daten
muss auffallen, bevor der erste Lauf startet.
"""

import os
from typing import Dict, List, Optional, Tuple

import pandas as pd


def ohlc_file_path(exchange: str, timeframe: str) -> str:
    """Baut den Pfad der HDF5-Datei zu Exchange und Timeframe.

    Args:
        exchange: Name der Börse (z.B. 'binance').
        timeframe: Timeframe-Kürzel (z.B. '4h').

    Returns:
        Absoluter Pfad der HDF5-Datei.
    """
    from user_data.config import Config

    return os.path.join(Config.DATA_PATH, f'ohlcv_{timeframe}_{exchange}.h5')


def ohlc_coverage(
    exchange: str, timeframe: str, symbols: List[str],
) -> Dict[str, Optional[Tuple[str, str]]]:
    """Ermittelt je Symbol die vorhandene Datenspanne.

    Args:
        exchange: Name der Börse.
        timeframe: Timeframe-Kürzel.
        symbols: Zu prüfende Symbole.

    Returns:
        Je Symbol ein Tupel (erster, letzter Zeitstempel) im ISO-Format oder None,
        wenn für das Symbol keine Kerzen in der Datei stehen.

    Raises:
        FileNotFoundError: Wenn die HDF5-Datei zu Exchange und Timeframe fehlt.
    """
    path = ohlc_file_path(exchange, timeframe)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f'Keine OHLC-Datei für {exchange}/{timeframe} gefunden: {path}'
        )

    spans: Dict[str, Optional[Tuple[str, str]]] = {}
    with pd.HDFStore(path, mode='r') as store:
        available = {key.lstrip('/') for key in store.keys()}
        for symbol in symbols:
            if symbol not in available:
                spans[symbol] = None
                continue
            storer = store.get_storer(f'/{symbol}')
            nrows = int(getattr(storer, 'nrows', 0) or 0)
            if nrows <= 0:
                spans[symbol] = None
                continue
            first_row = store.select(f'/{symbol}', start=0, stop=1)
            last_row = store.select(f'/{symbol}', start=nrows - 1, stop=nrows)
            if not len(first_row) or not len(last_row):
                spans[symbol] = None
                continue
            spans[symbol] = (
                first_row.index[0].isoformat(),
                last_row.index[0].isoformat(),
            )
    return spans
