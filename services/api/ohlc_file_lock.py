"""Schreibsperre je OHLC-Datei (Ticket 97).

Die Kursdaten liegen als genau **eine** HDF5-Datei je Timeframe und Börse
(`ohlcv_{timeframe}_{exchange}.h5`). HDF5 lässt nur einen Schreiber zu: Zwei
gleichzeitig schreibende Worker enden in `errno 11` (Dateisperre) — der zweite
verliert sein Symbol, ohne dass der Aufrufer es merkt.

Diese Sperre serialisiert die Schreiber **je Datei**. Der Schlüssel trägt den
Timeframe, deshalb blockieren sich Updates verschiedener Timeframes nicht
gegenseitig; nur Schreiber auf dieselbe Datei warten aufeinander.

Die Sperre liegt in Redis (dieselbe Instanz wie die RQ-Queues), damit sie über
Container- und Prozessgrenzen hinweg gilt. Ein Hintergrund-Faden setzt die
Restlaufzeit fort, solange die Sperre gehalten wird: Ein voller Download kann
Stunden dauern, ein hart gestorbener Worker soll die Datei aber nicht dauerhaft
blockieren — ohne Fortsetzung verfällt die Sperre nach `ttl` Sekunden.
"""

import logging
import threading
from contextlib import contextmanager
from typing import Iterator, Optional

from services.api.redis_conn import get_redis_connection

logger = logging.getLogger(__name__)

# Namensraum der Sperren in Redis.
OHLC_FILE_LOCK_PREFIX: str = 'ohlc:file-lock'

# Restlaufzeit der Sperre in Sekunden. Wird gehalten und laufend fortgesetzt;
# stirbt der Worker hart, gibt Redis die Datei nach dieser Zeit wieder frei.
OHLC_FILE_LOCK_TTL: int = 900

# Maximale Wartezeit auf eine belegte Datei in Sekunden (6 Stunden). Danach gilt
# der Job als fehlgeschlagen — sichtbar mit Grund, nicht still übersprungen.
OHLC_FILE_LOCK_WAIT: int = 21600


class OhlcFileBusyError(RuntimeError):
    """Die OHLC-Datei war innerhalb der Wartezeit nicht frei."""


def ohlc_file_lock_key(exchange: str, timeframe: str) -> str:
    """Liefert den Redis-Schlüssel der Sperre für eine OHLC-Datei.

    Der Schlüssel bildet exakt die Datei ab, auf die geschrieben wird
    (`ohlcv_{timeframe}_{exchange}.h5`) — nicht mehr und nicht weniger. Damit
    ist die Serialisierung je Datei und nicht global.

    Args:
        exchange: Börse, z.B. 'binance'.
        timeframe: Timeframe, z.B. '4h'.

    Returns:
        Redis-Schlüssel der Sperre.
    """
    return f'{OHLC_FILE_LOCK_PREFIX}:{timeframe}:{exchange}'


@contextmanager
def ohlc_file_lock(
    exchange: str,
    timeframe: str,
    ttl: int = OHLC_FILE_LOCK_TTL,
    wait: int = OHLC_FILE_LOCK_WAIT,
    connection: Optional[object] = None,
) -> Iterator[object]:
    """Hält die Schreibsperre für eine OHLC-Datei, solange der Block läuft.

    Args:
        exchange: Börse, z.B. 'binance'.
        timeframe: Timeframe, z.B. '4h'.
        ttl: Restlaufzeit der Sperre in Sekunden (wird laufend fortgesetzt).
        wait: Maximale Wartezeit auf eine belegte Datei in Sekunden.
        connection: Redis-Verbindung; ohne Angabe die Standardverbindung.

    Yields:
        Das gehaltene Sperr-Objekt.

    Raises:
        OhlcFileBusyError: Wenn die Datei innerhalb von `wait` nicht frei wurde.
    """
    conn = connection if connection is not None else get_redis_connection()
    key = ohlc_file_lock_key(exchange, timeframe)
    # thread_local=False: Der Fortsetzungs-Faden muss dasselbe Sperr-Merkmal
    # sehen wie der Haupt-Faden, sonst scheitert jedes extend().
    lock = conn.lock(key, timeout=ttl, blocking=True, blocking_timeout=wait, thread_local=False)
    if not lock.acquire():
        raise OhlcFileBusyError(
            f'OHLC-Datei {timeframe}/{exchange} war nach {wait}s noch belegt'
        )
    logger.info('[OHLC-LOCK] Sperre gehalten: %s', key)

    stop_renewal = threading.Event()

    def _renew() -> None:
        """Setzt die Restlaufzeit fort, bis die Sperre freigegeben wird."""
        while not stop_renewal.wait(max(ttl / 3.0, 1.0)):
            try:
                lock.extend(ttl, replace_ttl=True)
            except Exception as exc:  # LockNotOwnedError u.a.
                logger.warning('[OHLC-LOCK] Fortsetzen von %s fehlgeschlagen: %s', key, exc)
                return

    renewal = threading.Thread(target=_renew, name='ohlc-file-lock-renew', daemon=True)
    renewal.start()
    try:
        yield lock
    finally:
        stop_renewal.set()
        renewal.join(timeout=5)
        try:
            lock.release()
            logger.info('[OHLC-LOCK] Sperre freigegeben: %s', key)
        except Exception as exc:  # bereits verfallen o.ä. — kein Grund zum Abbruch
            logger.warning('[OHLC-LOCK] Freigeben von %s fehlgeschlagen: %s', key, exc)
