"""Tests für enqueue_reindex.py (Ticket 33, Teil C).

Prüft, dass main() genau einen reindex_vault_chunk_job mit trigger='scheduler'
in die recompute-Queue einreiht und einen VaultReindexRun-Eintrag anlegt.

Verwendet PostgreSQL Test-DB (Port 5562) via db_engine/session-Fixtures
aus tests/conftest.py. Queue.enqueue und Redis werden gemockt.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import sessionmaker

# Projekt-Root für alle Importe
_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))

# rq via sys.modules mocken bevor enqueue_reindex importiert wird
_mock_rq = MagicMock()
_mock_queue_cls = MagicMock()
_mock_rq.Queue = _mock_queue_cls
sys.modules.setdefault('rq', _mock_rq)

# Modul vorladen damit patch() darauf zugreifen kann
import services.api.enqueue_reindex  # noqa: E402, F401
import user_data.utils.database.db as _db_module  # noqa: E402

from user_data.utils.database.models import VaultReindexRun
from services.api.redis_conn import RECOMPUTE_QUEUE_NAME


# ============================================================================
# Tests
# ============================================================================

class TestEnqueueReindex:
    """main() reiht genau einen Job ein und legt VaultReindexRun-Eintrag an."""

    def test_enqueue_einmal_aufgerufen(self, db_engine, monkeypatch):
        """main() muss genau einen Queue.enqueue-Aufruf absetzen."""
        mock_job = MagicMock()
        mock_job.id = 'test-job-id-001'
        mock_q = MagicMock()
        mock_q.enqueue.return_value = mock_job
        monkeypatch.setattr(_db_module, '_engine', None)
        monkeypatch.setattr(_db_module, '_session_factory', None)

        with patch('services.api.enqueue_reindex.get_redis_connection', return_value=MagicMock()), \
             patch('services.api.enqueue_reindex.Queue', return_value=mock_q):
            services.api.enqueue_reindex.main()

        assert mock_q.enqueue.call_count == 1, (
            f"Erwartet genau 1 enqueue-Aufruf, war: {mock_q.enqueue.call_count}"
        )

    def test_korrekter_task_name(self, db_engine, monkeypatch):
        """Eingereiht wird 'services.api.worker_tasks.reindex_vault_chunk_job'."""
        mock_job = MagicMock()
        mock_job.id = 'test-job-id-002'
        mock_q = MagicMock()
        mock_q.enqueue.return_value = mock_job
        monkeypatch.setattr(_db_module, '_engine', None)
        monkeypatch.setattr(_db_module, '_session_factory', None)

        with patch('services.api.enqueue_reindex.get_redis_connection', return_value=MagicMock()), \
             patch('services.api.enqueue_reindex.Queue', return_value=mock_q):
            services.api.enqueue_reindex.main()

        call_args = mock_q.enqueue.call_args
        assert call_args[0][0] == 'services.api.worker_tasks.reindex_vault_chunk_job', (
            f"Falscher Task-Name: {call_args[0][0]}"
        )

    def test_trigger_ist_scheduler(self, db_engine, monkeypatch):
        """Der eingereithe Job muss trigger='scheduler' haben."""
        mock_job = MagicMock()
        mock_job.id = 'test-job-id-003'
        mock_q = MagicMock()
        mock_q.enqueue.return_value = mock_job
        monkeypatch.setattr(_db_module, '_engine', None)
        monkeypatch.setattr(_db_module, '_session_factory', None)

        with patch('services.api.enqueue_reindex.get_redis_connection', return_value=MagicMock()), \
             patch('services.api.enqueue_reindex.Queue', return_value=mock_q):
            services.api.enqueue_reindex.main()

        call_kwargs = mock_q.enqueue.call_args[1]
        assert call_kwargs.get('trigger') == 'scheduler', (
            f"trigger muss 'scheduler' sein, war: {call_kwargs.get('trigger')}"
        )

    def test_korrekte_queue_recompute(self, db_engine, monkeypatch):
        """Queue wird mit RECOMPUTE_QUEUE_NAME instanziiert."""
        mock_job = MagicMock()
        mock_job.id = 'test-job-id-004'
        mock_q_instance = MagicMock()
        mock_q_instance.enqueue.return_value = mock_job
        mock_queue_cls = MagicMock(return_value=mock_q_instance)
        monkeypatch.setattr(_db_module, '_engine', None)
        monkeypatch.setattr(_db_module, '_session_factory', None)

        with patch('services.api.enqueue_reindex.get_redis_connection', return_value=MagicMock()), \
             patch('services.api.enqueue_reindex.Queue', mock_queue_cls):
            services.api.enqueue_reindex.main()

        # Queue muss mit RECOMPUTE_QUEUE_NAME aufgerufen worden sein
        assert mock_queue_cls.call_args[0][0] == RECOMPUTE_QUEUE_NAME, (
            f"Queue-Name erwartet '{RECOMPUTE_QUEUE_NAME}', war: {mock_queue_cls.call_args[0][0]}"
        )

    def test_vault_reindex_run_eintrag_angelegt(self, db_engine, monkeypatch):
        """Nach main() muss ein VaultReindexRun-Eintrag mit trigger='scheduler' in der DB sein."""
        mock_job = MagicMock()
        mock_job.id = 'test-job-id-005'
        mock_q = MagicMock()
        mock_q.enqueue.return_value = mock_job
        monkeypatch.setattr(_db_module, '_engine', None)
        monkeypatch.setattr(_db_module, '_session_factory', None)

        with patch('services.api.enqueue_reindex.get_redis_connection', return_value=MagicMock()), \
             patch('services.api.enqueue_reindex.Queue', return_value=mock_q):
            services.api.enqueue_reindex.main()

        SessionFactory = sessionmaker(bind=db_engine)
        with SessionFactory() as sess:
            runs = sess.query(VaultReindexRun).filter(
                VaultReindexRun.trigger == 'scheduler',
                VaultReindexRun.job_id == 'test-job-id-005',
            ).all()

        assert len(runs) >= 1, "Mindestens ein VaultReindexRun mit trigger='scheduler' erwartet"
        run = runs[-1]
        assert run.status == 'queued', f"Status erwartet 'queued', war: {run.status}"
        assert run.scope == 'full', f"Scope erwartet 'full', war: {run.scope}"
