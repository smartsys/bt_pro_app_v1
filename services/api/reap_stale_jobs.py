"""Reaper — Standalone-Script für den Scheduler-Container.

Wird alle 5 Minuten von cron im scheduler-Container aufgerufen und gleicht die
DB-Tabelle backtest_jobs mit dem echten RQ-Zustand ab. Ohne diesen Abgleich
driften beide auseinander: stirbt ein Worker mitten in einem Job (Neustart,
Absturz, Timeout, Redis verliert den Job), erreicht run_recompute_job seinen
Abschluss-Schritt nie und die DB-Zeile bleibt für immer auf 'running'/'queued'
stehen. Die "Worker"-Anzeige der Runs-Liste zeigt dann dauerhaft "aktiv".

Erkennung eines verwaisten Jobs (versionsunabhängig, ohne RQ-Registry-Interna):
- running: der RQ-Job existiert nicht mehr (rq:job:<id> weg) ODER started_at ist
  älter als das Job-Timeout plus Puffer (ein Job, der so lange laeuft, wurde von
  RQ langst bei job_timeout abgebrochen).
- queued: der RQ-Job existiert nicht mehr (Redis hat ihn verloren). Ein legitim
  wartender Job hat seinen rq:job:<id>-Hash noch in Redis.

Behandlung: NICHT sofort auf failed setzen, sondern neu einreihen. Erst nach
insgesamt 3 Startversuchen (Original + 2 Neustarts) ohne Erfolg wird der Job
endgueltig auf 'failed' gesetzt. Der manuelle Rerun-Weg (Run neustarten bzw.
Analyse erneut starten) bleibt unberuehrt, weil er eigene, neu angelegte Jobs
mit retry_count=0 erzeugt.

Kein Daemon, kein Thread — nur einmal ausfuehren und beenden.

Aufruf: python services/api/reap_stale_jobs.py
"""

import logging
import os
import sys
from datetime import datetime

# PYTHONPATH auf /app setzen (WORKDIR im Container)
sys.path.insert(0, os.environ.get('PROJECT_ROOT', '/app'))

from redis.exceptions import RedisError
from rq import Queue
from rq.job import Job as RqJob

from services.api.reap_logic import classify_job, JOB_TIMEOUT_SECONDS, MAX_STARTS
from services.api.redis_conn import get_redis_connection, RECOMPUTE_QUEUE_NAME
from user_data.utils.database.db import get_session
from user_data.utils.database.models import BacktestJob

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _rq_job_alive(redis_conn, rq_job_id: str | None) -> bool:
    """Prüft, ob der RQ-Job-Hash (rq:job:<id>) noch in Redis existiert.

    Bei fehlender ID gilt der Job als nicht lebendig. Bei einem Redis-Fehler
    wird True zurueckgegeben (im Zweifel nicht anfassen).
    """
    if not rq_job_id:
        return False
    try:
        return RqJob.exists(rq_job_id, connection=redis_conn)
    except RedisError as exc:
        logger.warning("[REAPER] Redis-Fehler bei exists(%s): %s", rq_job_id, exc)
        return True


def _claim(session, job_id: int, values: dict) -> int:
    """Setzt values auf den Job, aber nur solange er noch queued/running ist.

    Verhindert, dass ein Job ueberschrieben wird, den ein Worker im selben Moment
    abgeschlossen hat. Gibt die Anzahl betroffener Zeilen zurueck (0 oder 1).
    """
    rows = session.query(BacktestJob).filter(
        BacktestJob.id == job_id,
        BacktestJob.status.in_(('queued', 'running')),
    ).update(values, synchronize_session=False)
    session.commit()
    return rows


def main() -> None:
    """Gleicht verwaiste backtest_jobs mit dem RQ-Zustand ab."""
    redis_conn = get_redis_connection()
    queue = Queue(RECOMPUTE_QUEUE_NAME, connection=redis_conn)
    session = get_session()

    reenqueued = 0
    failed = 0
    try:
        now = datetime.now()

        candidates = session.query(BacktestJob).filter(
            BacktestJob.status.in_(('queued', 'running')),
        ).all()

        for job in candidates:
            alive = _rq_job_alive(redis_conn, job.rq_job_id)
            action = classify_job(job.status, alive, job.started_at, now, job.retry_count)

            if action == 'skip':
                continue

            if action == 'retry':
                # Versuchsnummer vor dem _claim festhalten: dessen commit expired
                # das ORM-Objekt, danach laedt job.retry_count den neuen Wert.
                attempt_number = job.retry_count + 2  # Original=1, erster Neustart=2, ...
                # Neustart: erst den DB-Anspruch sichern (atomar, nur wenn noch
                # queued/running), dann neu einreihen. So entsteht kein
                # verwaister RQ-Job, falls der Job zwischenzeitlich fertig wurde.
                claimed = _claim(session, job.id, {
                    'status': 'queued',
                    'retry_count': job.retry_count + 1,
                    'started_at': None,
                    'error_message': None,
                })
                if not claimed:
                    continue
                rq_job = queue.enqueue(
                    'services.api.worker_tasks.run_recompute_job',
                    job.id,
                    job.result_id,
                    job_timeout=JOB_TIMEOUT_SECONDS,
                )
                session.query(BacktestJob).filter(BacktestJob.id == job.id).update(
                    {'rq_job_id': rq_job.id}, synchronize_session=False,
                )
                session.commit()
                reenqueued += 1
                logger.info(
                    "[REAPER] Job %d (Result %d) neu eingereiht (Versuch %d/%d)",
                    job.id, job.result_id, attempt_number, MAX_STARTS,
                )
            else:
                claimed = _claim(session, job.id, {
                    'status': 'failed',
                    'completed_at': now,
                    'error_message': '3x Abbruch mit Fehler',
                })
                if claimed:
                    failed += 1
                    logger.info(
                        "[REAPER] Job %d (Result %d) nach %d Versuchen endgueltig failed",
                        job.id, job.result_id, MAX_STARTS,
                    )

        logger.info("[REAPER] Fertig: neu eingereiht=%d, endgueltig failed=%d", reenqueued, failed)
    except Exception as exc:
        session.rollback()
        logger.error("[REAPER] Fehler beim Abgleich: %s", exc, exc_info=True)
        sys.exit(1)
    finally:
        session.close()


if __name__ == '__main__':
    main()
