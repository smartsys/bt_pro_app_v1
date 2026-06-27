"""Enqueue-Reindex — Standalone-Script für den Scheduler-Container.

Wird alle 5 Minuten von cron im scheduler-Container aufgerufen.
Reiht einen reindex_vault_chunk_job in die recompute-Queue ein und
legt einen VaultReindexRun-Eintrag mit trigger='scheduler' an.

Kein Daemon, kein Thread — nur einmal ausführen und beenden.

Aufruf: python services/api/enqueue_reindex.py
"""

import logging
import os
import sys
from datetime import datetime

# PYTHONPATH auf /app setzen (WORKDIR im Container)
sys.path.insert(0, os.environ.get('PROJECT_ROOT', '/app'))

from rq import Queue

from services.api.redis_conn import get_redis_connection, RECOMPUTE_QUEUE_NAME
from user_data.utils.database.db import get_session
from user_data.utils.database.models import VaultReindexRun

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    """Reiht einen Vault-Reindex-Job ein und legt den Run-Eintrag in der DB an."""
    try:
        q = Queue(RECOMPUTE_QUEUE_NAME, connection=get_redis_connection())
        job = q.enqueue(
            'services.api.worker_tasks.reindex_vault_chunk_job',
            target_path=None,
            trigger='scheduler',
            job_timeout=600,
        )
        logger.info("[ENQUEUE-REINDEX] reindex_vault_chunk_job eingereiht (job_id=%s)", job.id)

        session = get_session()
        try:
            run_entry = VaultReindexRun(
                job_id=job.id,
                scope='full',
                target_path=None,
                trigger='scheduler',
                status='queued',
                created_at=datetime.now(),
            )
            session.add(run_entry)
            session.commit()
        finally:
            session.close()

        logger.info("[ENQUEUE-REINDEX] VaultReindexRun-Eintrag angelegt (job_id=%s)", job.id)

    except Exception as exc:
        logger.error("[ENQUEUE-REINDEX] Fehler beim Einreihen: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
