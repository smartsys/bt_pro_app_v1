"""Stabiler RQ-Worker-Entrypoint.

Ersetzt den nackten Aufruf 'python -m rq.cli worker --url redis://...'.
Die CLI-Variante baut eine Redis-Verbindung ohne TCP-Keepalive; idle
Verbindungen reißen unter Docker/WSL2 nach einigen Minuten still ab,
woraufhin der blockierende Dequeue in einen Redis-Timeout läuft, der
Worker mit 'Redis connection timeout, quitting...' (Exit 0) endet und der
Container in einer Restart-Schleife respawnt — was laufende Backtests killt.

Dieser Entrypoint nutzt get_redis_connection() (mit Keepalive + Health-Check)
und startet denselben Worker auf denselben Qüüs in derselben Priorität.

Vor dem ersten Dequeue wird auf die Datenbank gewartet: Startet der Stack
nicht über 'compose up' (sondern über 'compose start' oder den Autostart von
Docker Desktop), wertet Compose die depends_on-Bedingungen nicht aus. Die
Worker sind dann vor Postgres bereit, ziehen Jobs, scheitern sofort an
'the database system is starting up' und RQ schiebt sie ohne Wiederholung ins
FailedJobRegistry — die komplette Queue brennt in Sekunden durch. Deshalb hier
das Gate.
"""
import logging
import sys
import time

from rq import Queue, Worker
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from services.api.redis_conn import (
    get_redis_connection,
    BACKTEST_QUEUE_NAME,
    RECOMPUTE_QUEUE_NAME,
    OHLC_DOWNLOAD_QUEUE_NAME,
)
from user_data.utils.database.db import get_session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default-Qüüs (Reihenfolge = Priorität, backtest zuerst), wenn keine Argumente
# übergeben werden. Per CLI-Argumenten überschreibbar, damit jede Umgebung ihr
# eigenes Queue-Set behält (z.B. Staging-Server ohne ohlc_download).
DEFAULT_QUEUE_NAMES: list[str] = [BACKTEST_QUEUE_NAME, RECOMPUTE_QUEUE_NAME, OHLC_DOWNLOAD_QUEUE_NAME]

# Wartegate auf die Datenbank (Sekunden)
DB_WAIT_TIMEOUT: int = 120
DB_WAIT_INTERVAL: int = 2


def wait_for_db(timeout: int = DB_WAIT_TIMEOUT, interval: int = DB_WAIT_INTERVAL) -> None:
    """Wartet, bis die Datenbank Abfragen beantwortet.

    Args:
        timeout: Maximale Wartezeit in Sekunden.
        interval: Pause zwischen zwei Versuchen in Sekunden.

    Raises:
        SystemExit: Wenn die Datenbank innerhalb von timeout nicht antwortet.
            Der Container endet mit Exit-Code 1 und wird von Docker neu gestartet —
            besser als ein Worker, der Jobs zieht und an der DB scheitern lässt.
    """
    deadline = time.monotonic() + timeout
    attempt = 0
    while True:
        attempt += 1
        session = None
        try:
            session = get_session()
            session.execute(text('SELECT 1'))
            if attempt > 1:
                logger.info("[WORKER] Datenbank erreichbar (Versuch %d)", attempt)
            return
        except OperationalError as exc:
            if time.monotonic() >= deadline:
                logger.error(
                    "[WORKER] Datenbank nach %ds nicht erreichbar — Abbruch: %s",
                    timeout, exc,
                )
                raise SystemExit(1)
            logger.info(
                "[WORKER] Datenbank noch nicht bereit (Versuch %d), erneut in %ds ...",
                attempt, interval,
            )
            time.sleep(interval)
        finally:
            if session is not None:
                session.close()


def main(argv: list[str] | None = None) -> None:
    """Startet einen RQ-Worker mit stabiler Redis-Verbindung.

    Args:
        argv: Optionale Queue-Namen; ohne Angabe werden DEFAULT_QUEUE_NAMES genutzt.
    """
    # GEÄNDERT: Erst wenn die DB antwortet, darf der Worker Jobs ziehen.
    wait_for_db()

    queue_names = list(argv) if argv else DEFAULT_QUEUE_NAMES
    connection = get_redis_connection()
    queues = [Queue(name, connection=connection) for name in queue_names]
    worker = Worker(queues, connection=connection)
    # Scheduler läuft als eigener Container — hier nicht mitstarten.
    worker.work(with_scheduler=False)


if __name__ == '__main__':
    main(sys.argv[1:])
