"""Tests für files_changed JSONB-Spalte in vault_reindex_runs (Ticket 34).

Prüft:
- Reindex mit zwei Dateien: files_changed enthält beide Pfade unter 'reindexed'.
- Gelöschte Datei: nächster Lauf hat den Pfad unter 'deleted'.
- Stub-Datei (Sentinel-Row): landet wie normale Datei unter 'reindexed'.
- Mount-Guard-Abbruch (RuntimeError): files_changed bleibt NULL in der DB.
- API-Response enthält files_changed-Feld.

Verwendet PostgreSQL Test-DB (Port 5562) via db_engine/session-Fixtures
aus tests/conftest.py.
"""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))

from user_data.utils.database.models import VaultReindexRun
import user_data.utils.database.db as _db_module


# ============================================================================
# Hilfsfunktion: Run anlegen
# ============================================================================

def _insert_run(
    session,
    job_id: str = 'fc-test-job',
    scope: str = 'full',
    status: str = 'queued',
) -> VaultReindexRun:
    """Legt einen VaultReindexRun direkt in der Test-DB an."""
    run = VaultReindexRun(
        job_id=job_id,
        scope=scope,
        target_path=None,
        trigger='api',
        status=status,
        created_at=datetime.now(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


# ============================================================================
# Fixture: FastAPI-Client mit gemocktem embed + rq
# ============================================================================

@pytest.fixture(scope='module')
def knowledge_app() -> FastAPI:
    """Minimale FastAPI-App mit dem knowledge-Router."""
    from services.api.routes.api_knowledge import router as knowledge_router
    app = FastAPI()
    app.include_router(knowledge_router)
    return app


@pytest.fixture(scope='function')
def client(knowledge_app, monkeypatch):
    """TestClient mit gemocktem embed/rq und Test-DB."""
    monkeypatch.setattr(
        'services.api.routes.api_knowledge.embed',
        lambda text: [0.0] * 1024,
    )
    monkeypatch.setattr(
        'services.api.routes.api_knowledge.get_redis_connection',
        lambda: None,
    )

    mock_job = MagicMock()
    mock_job.id = 'mock-fc-job-id'
    mock_queue_instance = MagicMock()
    mock_queue_instance.enqueue.return_value = mock_job
    mock_rq = MagicMock()
    mock_rq.Queue = MagicMock(return_value=mock_queue_instance)
    monkeypatch.setitem(sys.modules, 'rq', mock_rq)

    monkeypatch.setattr(_db_module, '_engine', None)
    monkeypatch.setattr(_db_module, '_session_factory', None)

    with TestClient(knowledge_app) as c:
        yield c


# ============================================================================
# Hilfsfunktion: reindex_vault_chunk_job mit gemocktem Indexer ausführen
# ============================================================================

def _run_job_with_mock_result(session, monkeypatch, run_db_id: int, indexer_result: dict) -> None:
    """Führt reindex_vault_chunk_job mit gemocktem Indexer-Ergebnis aus."""
    monkeypatch.setattr(_db_module, '_engine', None)
    monkeypatch.setattr(_db_module, '_session_factory', None)

    mock_indexer_module = MagicMock()
    mock_indexer_module.reindex.return_value = indexer_result
    monkeypatch.setitem(sys.modules, 'services.vbt.knowledge.indexer', mock_indexer_module)
    monkeypatch.setitem(sys.modules, 'services.vbt.knowledge', MagicMock())
    monkeypatch.setitem(sys.modules, 'services.vbt', MagicMock())
    monkeypatch.setitem(sys.modules, 'rq', MagicMock(get_current_job=MagicMock(return_value=None)))

    import services.api.worker_tasks as wt
    wt.reindex_vault_chunk_job(target_path=None, trigger='api', run_db_id=run_db_id)


# ============================================================================
# Test 1: Zwei Dateien reindiziert — beide Pfade unter 'reindexed'
# ============================================================================

def test_files_changed_reindexed_paths(session, monkeypatch):
    """Nach erfolgreichem Lauf mit zwei reindexierten Dateien sind beide Pfade in files_changed['reindexed']."""
    run = _insert_run(session, job_id='fc-two-files')
    run_db_id = run.id

    fake_result = {
        'files_scanned': 2,
        'files_reindexed': 2,
        'files_deleted': 0,
        'chunks_written': 5,
        'files_unchanged': 0,
        'duration_seconds': 1.0,
        'reindexed_paths': ['strategies/teststrategie/STATUS.md', 'strategies/teststrategie/concept.md'],
        'deleted_paths': [],
    }
    _run_job_with_mock_result(session, monkeypatch, run_db_id, fake_result)

    session.expire(run)
    session.refresh(run)
    assert run.status == 'success'
    assert run.files_changed is not None
    assert 'reindexed' in run.files_changed
    assert 'deleted' in run.files_changed
    assert 'strategies/teststrategie/STATUS.md' in run.files_changed['reindexed']
    assert 'strategies/teststrategie/concept.md' in run.files_changed['reindexed']
    assert run.files_changed['deleted'] == []


# ============================================================================
# Test 2: Gelöschte Datei — Pfad unter 'deleted'
# ============================================================================

def test_files_changed_deleted_paths(session, monkeypatch):
    """Nach Lauf mit gelöschter Datei ist der Pfad in files_changed['deleted']."""
    run = _insert_run(session, job_id='fc-deleted-file')
    run_db_id = run.id

    fake_result = {
        'files_scanned': 1,
        'files_reindexed': 0,
        'files_deleted': 1,
        'chunks_written': 0,
        'files_unchanged': 0,
        'duration_seconds': 0.5,
        'reindexed_paths': [],
        'deleted_paths': ['strategies/old-strategy/notes.md'],
    }
    _run_job_with_mock_result(session, monkeypatch, run_db_id, fake_result)

    session.expire(run)
    session.refresh(run)
    assert run.status == 'success'
    assert run.files_changed is not None
    assert 'strategies/old-strategy/notes.md' in run.files_changed['deleted']
    assert run.files_changed['reindexed'] == []


# ============================================================================
# Test 3: Stub-Datei (Sentinel-Row) — landet unter 'reindexed'
# ============================================================================

def test_files_changed_sentinel_row_counts_as_reindexed(session, monkeypatch):
    """Sentinel-Row-Pfad zählt wie normale Datei als reindexiert."""
    run = _insert_run(session, job_id='fc-sentinel-file')
    run_db_id = run.id

    # Sentinel: files_reindexed=1, chunks_written=0 (kein Embedding), aber Pfad in reindexed_paths
    fake_result = {
        'files_scanned': 1,
        'files_reindexed': 1,
        'files_deleted': 0,
        'chunks_written': 0,
        'files_unchanged': 0,
        'duration_seconds': 0.1,
        'reindexed_paths': ['strategies/stub-file.md'],
        'deleted_paths': [],
    }
    _run_job_with_mock_result(session, monkeypatch, run_db_id, fake_result)

    session.expire(run)
    session.refresh(run)
    assert run.status == 'success'
    assert run.files_changed is not None
    assert 'strategies/stub-file.md' in run.files_changed['reindexed']


# ============================================================================
# Test 4: Mount-Guard-Abbruch — files_changed bleibt NULL
# ============================================================================

def test_files_changed_null_on_exception(session, monkeypatch):
    """Bei RuntimeError (z.B. Mount-Guard) bleibt files_changed NULL in der DB."""
    run = _insert_run(session, job_id='fc-mount-guard-fail')
    run_db_id = run.id

    monkeypatch.setattr(_db_module, '_engine', None)
    monkeypatch.setattr(_db_module, '_session_factory', None)

    mock_indexer_module = MagicMock()
    mock_indexer_module.reindex.side_effect = RuntimeError('vault_root nicht erreichbar: /vault/trading')
    monkeypatch.setitem(sys.modules, 'services.vbt.knowledge.indexer', mock_indexer_module)
    monkeypatch.setitem(sys.modules, 'services.vbt.knowledge', MagicMock())
    monkeypatch.setitem(sys.modules, 'services.vbt', MagicMock())
    monkeypatch.setitem(sys.modules, 'rq', MagicMock(get_current_job=MagicMock(return_value=None)))

    import services.api.worker_tasks as wt
    with pytest.raises(RuntimeError):
        wt.reindex_vault_chunk_job(target_path=None, trigger='api', run_db_id=run_db_id)

    session.expire(run)
    session.refresh(run)
    assert run.status == 'failed'
    # files_changed darf nicht gesetzt worden sein — kein Erfolgs-Update bei Exception
    assert run.files_changed is None


# ============================================================================
# Test 5: API-Response enthält files_changed-Feld
# ============================================================================

def test_api_response_contains_files_changed(client, session):
    """GET /api/knowledge/runs/{id} liefert files_changed im Response."""
    run = _insert_run(session, job_id='fc-api-check', status='success')
    # files_changed direkt setzen (kein Job-Lifecycle nötig)
    run.files_changed = {
        'reindexed': ['strategies/teststrategie/STATUS.md'],
        'deleted': [],
    }
    session.commit()

    resp = client.get(f'/api/knowledge/runs/{run.id}')
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert 'files_changed' in data
    assert data['files_changed'] is not None
    assert 'reindexed' in data['files_changed']
    assert 'strategies/teststrategie/STATUS.md' in data['files_changed']['reindexed']


def test_api_response_files_changed_null_when_not_set(client, session):
    """GET /api/knowledge/runs/{id}: files_changed ist null wenn nicht gesetzt (queued/failed)."""
    run = _insert_run(session, job_id='fc-api-null', status='queued')

    resp = client.get(f'/api/knowledge/runs/{run.id}')
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert 'files_changed' in data
    assert data['files_changed'] is None
