"""Tests für DELETE /api/knowledge/reset (Ticket 33, Teil B).

Prüft, dass der Reset-Endpoint vault_chunks und vault_reindex_runs leert
und korrekte Counts in der Response zurückgibt.

Verwendet PostgreSQL Test-DB (Port 5562) via db_engine/session-Fixtures
aus tests/conftest.py.
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))

from user_data.utils.database.models import VaultReindexRun
import user_data.utils.database.db as _db_module


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope='module')
def knowledge_app() -> FastAPI:
    """Minimale FastAPI-App mit dem knowledge-Router."""
    from services.api.routes.api_knowledge import router as knowledge_router
    app = FastAPI()
    app.include_router(knowledge_router)
    return app


@pytest.fixture(scope='function')
def client(knowledge_app: FastAPI, monkeypatch) -> Generator:
    """TestClient mit gemocktem embed/rq-Backend und Test-DB-Session."""
    monkeypatch.setattr(
        'services.api.routes.api_knowledge.embed',
        lambda t: [0.0] * 1024,
    )
    monkeypatch.setattr(
        'services.api.routes.api_knowledge.get_redis_connection',
        lambda: None,
    )

    mock_job = MagicMock()
    mock_job.id = 'mock-job-reset-test'
    mock_queue_instance = MagicMock()
    mock_queue_instance.enqueue.return_value = mock_job
    mock_queue_class = MagicMock(return_value=mock_queue_instance)
    mock_rq = MagicMock()
    mock_rq.Queue = mock_queue_class
    monkeypatch.setitem(sys.modules, 'rq', mock_rq)

    monkeypatch.setattr(_db_module, '_engine', None)
    monkeypatch.setattr(_db_module, '_session_factory', None)

    with TestClient(knowledge_app) as c:
        yield c


# ============================================================================
# Tests
# ============================================================================

class TestKnowledgeReset:
    """DELETE /api/knowledge/reset leert beide Tabellen korrekt."""

    def test_reset_leert_beide_tabellen(self, client, session, db_engine):
        """Reset löscht alle vault_chunks und vault_reindex_runs."""
        # Testdaten anlegen
        SessionFactory = sessionmaker(bind=db_engine)
        with SessionFactory() as s:
            # vault_reindex_run anlegen
            run = VaultReindexRun(
                job_id='reset-test-run-1',
                scope='full',
                trigger='api',
                status='success',
                created_at=datetime.now(),
            )
            s.add(run)
            s.commit()

            # vault_chunk anlegen (direkt via SQL, da embedding nullable)
            s.execute(
                text(
                    "INSERT INTO vault_chunks "
                    "(vault_path, chunk_index, content, embedding, mtime, file_sha1, indexed_at) "
                    "VALUES ('test/reset.md', 0, '', NULL, NOW(), 'abc123', NOW())"
                )
            )
            s.commit()

        resp = client.delete('/api/knowledge/reset')
        assert resp.status_code == 200, resp.text

        data = resp.json()
        assert data.get('error') is None
        assert 'data' in data
        counts = data['data']
        assert counts['vault_chunks_deleted'] >= 1, "Mindestens 1 Chunk muss gelöscht worden sein"
        assert counts['vault_reindex_runs_deleted'] >= 1, "Mindestens 1 Run muss gelöscht worden sein"

        # DB muss leer sein
        with SessionFactory() as s:
            chunk_count = s.execute(text("SELECT COUNT(*) FROM vault_chunks")).scalar()
            run_count = s.execute(text("SELECT COUNT(*) FROM vault_reindex_runs")).scalar()

        assert chunk_count == 0, f"vault_chunks muss leer sein, war: {chunk_count}"
        assert run_count == 0, f"vault_reindex_runs muss leer sein, war: {run_count}"

    def test_reset_leere_db_gibt_null_counts(self, client, db_engine):
        """Zweiter Reset-Aufruf auf leerer DB gibt vault_chunks_deleted=0 und runs_deleted=0."""
        # Sicherstellen dass DB leer ist
        SessionFactory = sessionmaker(bind=db_engine)
        with SessionFactory() as s:
            s.execute(text("DELETE FROM vault_chunks"))
            s.execute(text("DELETE FROM vault_reindex_runs"))
            s.commit()

        resp = client.delete('/api/knowledge/reset')
        assert resp.status_code == 200, resp.text

        counts = resp.json()['data']
        assert counts['vault_chunks_deleted'] == 0
        assert counts['vault_reindex_runs_deleted'] == 0

    def test_reset_response_format(self, client):
        """Response muss {'data': {...}, 'error': null} Format haben."""
        resp = client.delete('/api/knowledge/reset')
        assert resp.status_code == 200

        body = resp.json()
        assert 'data' in body
        assert 'error' in body
        assert body['error'] is None
        assert 'vault_chunks_deleted' in body['data']
        assert 'vault_reindex_runs_deleted' in body['data']
