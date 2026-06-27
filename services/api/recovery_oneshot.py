"""Recovery-Oneshot

One-Shot-Script für den worker-init-Container. Setzt alle BacktestRuns
mit status='running' auf 'queued' zurück und reiht sie neu in die Queue
ein. Läuft einmal beim Compose-up und beendet sich dann mit exit 0.

Keine Scheduler, kein RQ-Worker-Spawn — nur Recovery.

Aufruf (Docker): python services/api/recovery_oneshot.py
"""

import logging
import os
import sys

# PYTHONPATH auf /app setzen (WORKDIR im Container)
sys.path.insert(0, os.environ.get('PROJECT_ROOT', '/app'))

from rq import Queue

from services.api.redis_conn import get_redis_connection, BACKTEST_QUEUE_NAME
from user_data.utils.database.db import get_session
from user_data.utils.database.models import BacktestRun

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def recover_stale_runs() -> None:
    """Setzt alle 'running'-Runs auf 'queued' zurück und reiht sie neu in die Queue ein."""
    session = get_session()
    try:
        stale_runs = session.query(BacktestRun).filter(
            BacktestRun.status == 'running'
        ).all()

        if not stale_runs:
            logger.info("[RECOVERY] Keine hängenden Runs gefunden")
            return

        logger.info(
            "[RECOVERY] %d hängende Runs gefunden: %s",
            len(stale_runs),
            [r.id for r in stale_runs],
        )

        # Status zurücksetzen
        for run in stale_runs:
            run.status = 'queued'
            run.completed_at = None
            run.error_message = None
        session.commit()

        # Jobs neu einreihen
        q = Queue(BACKTEST_QUEUE_NAME, connection=get_redis_connection())
        for run in stale_runs:
            q.enqueue(
                'services.api.worker_tasks.run_backtest_job',
                run_id=run.id,
                job_timeout=3600,
            )
            logger.info("[RECOVERY] Run #%d neu eingereiht", run.id)

    finally:
        session.close()


if __name__ == '__main__':
    recover_stale_runs()
