"""Recovery-Oneshot

One-Shot-Script für den worker-init-Container. Räumt zwei Fälle auf und beendet
sich danach mit exit 0:

1. Runs mit status='running', deren Worker gestorben ist — zurück auf 'queued'
   und neu einreihen.
2. Runs mit status='queued', zu denen kein RQ-Job mehr existiert — nur neu
   einreihen. Diese Waisen entstehen, wenn Jobs scheitern, bevor sie den Status
   in der DB umschreiben konnten (z.B. Datenbank beim Hochfahren noch nicht
   bereit): RQ schiebt sie ins FailedJobRegistry, in der DB bleiben sie auf
   'queued' stehen und niemand arbeitet sie je ab.

Keine Scheduler, kein RQ-Worker-Spawn — nur Recovery.

Aufruf (Docker): python services/api/recovery_oneshot.py
"""

import logging
import os
import sys

# PYTHONPATH auf /app setzen (WORKDIR im Container)
sys.path.insert(0, os.environ.get('PROJECT_ROOT', '/app'))

from rq import Queue
from rq.job import Job
from rq.registry import StartedJobRegistry

from services.api.redis_conn import get_redis_connection, BACKTEST_QUEUE_NAME, BACKTEST_JOB_TIMEOUT
from user_data.utils.database.db import get_session
from user_data.utils.database.models import BacktestRun

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _enqueue_run(queue: Queue, run_id: int) -> None:
    """Reiht einen Backtest-Run als RQ-Job ein."""
    queue.enqueue(
        'services.api.worker_tasks.run_backtest_job',
        run_id=run_id,
        job_timeout=BACKTEST_JOB_TIMEOUT,
    )


def _live_run_ids(queue: Queue) -> set[int]:
    """Sammelt die run_ids aller RQ-Jobs, die noch wartend oder in Arbeit sind.

    Berücksichtigt sowohl die wartenden Jobs der Queue als auch die bereits von
    einem Worker gestarteten (StartedJobRegistry) — ein zeitgleich anlaufender
    Worker darf nicht dazu führen, dass ein Run doppelt eingereiht wird.

    Args:
        queue: Die Backtest-Queue.

    Returns:
        Menge der run_ids, für die noch ein lebender RQ-Job existiert.
    """
    job_ids = list(queue.job_ids) + list(StartedJobRegistry(queue=queue).get_job_ids())
    jobs = Job.fetch_many(job_ids, connection=queue.connection)

    run_ids: set[int] = set()
    for job in jobs:
        if job is None:
            continue
        run_id = job.kwargs.get('run_id')
        if run_id is not None:
            run_ids.add(int(run_id))
    return run_ids


def recover_stale_runs() -> None:
    """Reiht hängende 'running'- und verwaiste 'queued'-Runs neu ein."""
    session = get_session()
    queue = Queue(BACKTEST_QUEUE_NAME, connection=get_redis_connection())
    try:
        # Fall 1: Worker gestorben, Run steht auf 'running'
        stale_runs = session.query(BacktestRun).filter(
            BacktestRun.status == 'running'
        ).all()

        if stale_runs:
            logger.info(
                "[RECOVERY] %d hängende Runs gefunden: %s",
                len(stale_runs),
                [r.id for r in stale_runs],
            )
            for run in stale_runs:
                run.status = 'queued'
                run.completed_at = None
                run.error_message = None
            session.commit()

            for run in stale_runs:
                _enqueue_run(queue, run.id)
                logger.info("[RECOVERY] Run #%d neu eingereiht", run.id)
        else:
            logger.info("[RECOVERY] Keine hängenden Runs gefunden")

        # Fall 2: Run steht auf 'queued', der zugehörige RQ-Job existiert nicht mehr.
        # Die eben in Fall 1 eingereihten Runs sind ebenfalls 'queued' und werden
        # explizit ausgeschlossen, statt sich auf ihre Sichtbarkeit in Redis zu verlassen.
        recovered_ids = {run.id for run in stale_runs}
        live_run_ids = _live_run_ids(queue) | recovered_ids
        orphaned_runs = [
            run for run in session.query(BacktestRun).filter(
                BacktestRun.status == 'queued'
            ).all()
            if run.id not in live_run_ids
        ]

        if not orphaned_runs:
            logger.info("[RECOVERY] Keine verwaisten queued-Runs gefunden")
            return

        logger.info(
            "[RECOVERY] %d verwaiste queued-Runs gefunden: %s",
            len(orphaned_runs),
            [r.id for r in orphaned_runs],
        )
        for run in orphaned_runs:
            _enqueue_run(queue, run.id)
            logger.info("[RECOVERY] Verwaisten Run #%d neu eingereiht", run.id)

    finally:
        session.close()


if __name__ == '__main__':
    recover_stale_runs()
