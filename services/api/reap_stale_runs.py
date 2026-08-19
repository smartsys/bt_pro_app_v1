"""Run-Reaper — Standalone-Script für den Scheduler-Container (Ticket 69).

Wird periodisch von cron im scheduler-Container aufgerufen und gleicht
backtest_runs mit status='running' gegen den echten RQ-Zustand ab. Ein
sterbender Worker-Prozess kann seinen eigenen Status nicht mehr schreiben —
die Erkennung kommt deshalb von außen, über RQ selbst:

- Wird ein Work-Horse hart beendet (OOM-Killer, kill -9), erkennt der
  überlebende RQ-Worker-Prozess das selbst (monitor_work_horse()) und schiebt
  den Job mit einem festen exc_string in die FailedJobRegistry.
- Ist der RQ-Job zu einer run_id nirgends mehr auffindbar (weder wartend noch
  gestartet noch failed), gilt der Run ebenfalls als tot — das deckt auch
  Altbestand ab, dessen Job-Eintrag in Redis längst abgelaufen ist.

Anders als reap_stale_jobs.py (für backtest_jobs / Recompute) wird hier
NICHT neu eingereiht — der Resume-Weg ("Analyse starten") bleibt laut Ticket
69 bewusst manuell. Bereits geschriebene backtest_results bleiben unberührt;
nur backtest_runs.status/error_message/completed_at werden aktualisiert.

Kein Daemon, kein Thread — nur einmal ausführen und beenden.

Aufruf: python services/api/reap_stale_runs.py
"""

import logging
import os
import sys
from datetime import datetime

# PYTHONPATH auf /app setzen (WORKDIR im Container)
sys.path.insert(0, os.environ.get('PROJECT_ROOT', '/app'))

from rq import Queue
from rq.job import Job as RqJob
from rq.registry import FailedJobRegistry, StartedJobRegistry

from services.api.reap_run_logic import build_abort_reason
from services.api.redis_conn import get_redis_connection, BACKTEST_QUEUE_NAME
from user_data.utils.database.db import get_session
from user_data.utils.database.models import BacktestRun

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _run_id_states(queue: Queue) -> tuple[set[int], dict[int, str | None]]:
    """Ermittelt den Redis-Zustand aller Backtest-Jobs anhand ihres run_id-Kwargs.

    Args:
        queue: Die Backtest-Queue.

    Returns:
        Tupel (alive_run_ids, dead_run_exc_info):
        - alive_run_ids: run_ids mit wartendem oder laufendem Job (queue.job_ids
          bzw. StartedJobRegistry) — nicht anfassen.
        - dead_run_exc_info: run_id -> exc_info für run_ids, deren Job in der
          FailedJobRegistry steht (Work-Horse hart beendet oder regulärer
          Fehler außerhalb des eigenen try/except von run_backtest_job).
    """
    connection = queue.connection

    live_job_ids = list(queue.job_ids) + list(StartedJobRegistry(queue=queue).get_job_ids())
    failed_job_ids = list(FailedJobRegistry(queue=queue).get_job_ids())

    alive_run_ids: set[int] = set()
    for job in RqJob.fetch_many(live_job_ids, connection=connection):
        if job is None:
            continue
        run_id = job.kwargs.get('run_id')
        if run_id is not None:
            alive_run_ids.add(int(run_id))

    dead_run_exc_info: dict[int, str | None] = {}
    for job in RqJob.fetch_many(failed_job_ids, connection=connection):
        if job is None:
            continue
        run_id = job.kwargs.get('run_id')
        if run_id is not None:
            dead_run_exc_info[int(run_id)] = job.exc_info

    return alive_run_ids, dead_run_exc_info


def _claim_failed(session, run_id: int, error_message: str) -> int:
    """Setzt einen Run auf 'failed', aber nur solange er noch 'running' ist.

    Verhindert, dass ein Run überschrieben wird, den ein Worker im selben
    Moment noch regulär abgeschlossen hat (eigener try/except in
    run_backtest_job setzt 'completed' oder 'failed').

    Returns:
        Anzahl betroffener Zeilen (0 oder 1).
    """
    rows = session.query(BacktestRun).filter(
        BacktestRun.id == run_id,
        BacktestRun.status == 'running',
    ).update({
        'status': 'failed',
        'completed_at': datetime.now(),
        'error_message': error_message[:2000],
    }, synchronize_session=False)
    session.commit()
    return rows


def main() -> None:
    """Setzt 'running'-BacktestRuns ohne lebenden RQ-Job auf 'failed'."""
    redis_conn = get_redis_connection()
    queue = Queue(BACKTEST_QUEUE_NAME, connection=redis_conn)
    session = get_session()

    reaped = 0
    try:
        alive_run_ids, dead_run_exc_info = _run_id_states(queue)

        running_runs = session.query(BacktestRun).filter(
            BacktestRun.status == 'running'
        ).all()

        for run in running_runs:
            if run.id in alive_run_ids:
                continue

            reason = build_abort_reason(dead_run_exc_info.get(run.id))
            if _claim_failed(session, run.id, reason):
                reaped += 1
                logger.info("[RUN-REAPER] Run %d abgebrochen: %s", run.id, reason)

        logger.info("[RUN-REAPER] Fertig: %d Run(s) auf 'failed' gesetzt", reaped)
    except Exception as exc:
        session.rollback()
        logger.error("[RUN-REAPER] Fehler beim Abgleich: %s", exc, exc_info=True)
        sys.exit(1)
    finally:
        session.close()


if __name__ == '__main__':
    main()
