"""Stabiler RQ-Worker-Entrypoint.

Ersetzt den nackten Aufruf 'python -m rq.cli worker --url redis://...'.
Die CLI-Variante baut eine Redis-Verbindung ohne TCP-Keepalive; idle
Verbindungen reißen unter Docker/WSL2 nach einigen Minuten still ab,
woraufhin der blockierende Dequeue in einen Redis-Timeout läuft, der
Worker mit 'Redis connection timeout, quitting...' (Exit 0) endet und der
Container in einer Restart-Schleife respawnt — was laufende Backtests killt.

Dieser Entrypoint nutzt get_redis_connection() (mit Keepalive + Health-Check)
und startet denselben Worker auf denselben Qüüs in derselben Priorität.
"""
import sys

from rq import Queue, Worker

from services.api.redis_conn import (
    get_redis_connection,
    BACKTEST_QUEUE_NAME,
    RECOMPUTE_QUEUE_NAME,
    OHLC_DOWNLOAD_QUEUE_NAME,
)

# Default-Qüüs (Reihenfolge = Priorität, backtest zuerst), wenn keine Argumente
# übergeben werden. Per CLI-Argumenten überschreibbar, damit jede Umgebung ihr
# eigenes Queue-Set behält (z.B. Staging-Server ohne ohlc_download).
DEFAULT_QUEUE_NAMES: list[str] = [BACKTEST_QUEUE_NAME, RECOMPUTE_QUEUE_NAME, OHLC_DOWNLOAD_QUEUE_NAME]


def main(argv: list[str] | None = None) -> None:
    """Startet einen RQ-Worker mit stabiler Redis-Verbindung.

    Args:
        argv: Optionale Queue-Namen; ohne Angabe werden DEFAULT_QUEUE_NAMES genutzt.
    """
    queue_names = list(argv) if argv else DEFAULT_QUEUE_NAMES
    connection = get_redis_connection()
    queues = [Queue(name, connection=connection) for name in queue_names]
    worker = Worker(queues, connection=connection)
    # Scheduler läuft als eigener Container — hier nicht mitstarten.
    worker.work(with_scheduler=False)


if __name__ == '__main__':
    main(sys.argv[1:])
