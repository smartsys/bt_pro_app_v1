"""Tests für Vault-Reindex-Lauf-Persistenz und API-Endpoints.

Prüft:
- Pre-Insert beim Enqueue: Run ist sofort mit status='queued' in der DB sichtbar.
- Job-Lifecycle (gemockter Indexer): nach Job-Ende status='success', Werte gesetzt.
- Job-Lifecycle bei Exception: status='failed', error_message gesetzt, Exception propagiert.
- GET /api/knowledge/runs: sortierte Liste, Limit funktioniert, Filter greifen.
- GET /api/knowledge/runs/{id}: 200 bei vorhandenem Run, 404 bei fehlendem.
- chunks_per_second im Detail-Response korrekt berechnet, NULL wenn duration_seconds=0.

Verwendet PostgreSQL Test-DB (Port 5562) via db_engine/session-Fixtures
aus tests/conftest.py.
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))

from user_data.utils.database.models import VaultReindexRun
import user_data.utils.database.db as _db_module


# ============================================================================
# Hilfsfunktionen
# ============================================================================

def _insert_run(
    session,
    job_id: str = 'test-job-abc',
    scope: str = 'full',
    target_path: str | None = None,
    trigger: str = 'api',
    status: str = 'queued',
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    duration_seconds: float | None = None,
    files_scanned: int | None = None,
    files_reindexed: int | None = None,
    files_deleted: int | None = None,
    chunks_written: int | None = None,
    error_message: str | None = None,
) -> VaultReindexRun:
    """Legt einen VaultReindexRun direkt in der Test-DB an."""
    run = VaultReindexRun(
        job_id=job_id,
        scope=scope,
        target_path=target_path,
        trigger=trigger,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=duration_seconds,
        files_scanned=files_scanned,
        files_reindexed=files_reindexed,
        files_deleted=files_deleted,
        chunks_written=chunks_written,
        error_message=error_message,
        created_at=datetime.now(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


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
    """TestClient mit gemocktem embed/rq-Backend und Test-DB-Session.

    - embed() wird durch Fake-Vektor ersetzt.
    - rq wird via sys.modules gemockt (nicht im Windows-venv installiert).
    - get_session()-Cache wird zurückgesetzt damit Test-DB genutzt wird.
    """
    monkeypatch.setattr(
        'services.api.routes.api_knowledge.embed',
        lambda text: [0.0] * 1024,
    )
    monkeypatch.setattr(
        'services.api.routes.api_knowledge.get_redis_connection',
        lambda: None,
    )

    # rq via sys.modules mocken
    mock_job = MagicMock()
    mock_job.id = 'mock-job-id-42'
    mock_queue_instance = MagicMock()
    mock_queue_instance.enqueue.return_value = mock_job
    mock_queue_class = MagicMock(return_value=mock_queue_instance)
    mock_rq = MagicMock()
    mock_rq.Queue = mock_queue_class
    monkeypatch.setitem(sys.modules, 'rq', mock_rq)

    # get_session()-Cache invalidieren damit Test-DB genutzt wird
    monkeypatch.setattr(_db_module, '_engine', None)
    monkeypatch.setattr(_db_module, '_session_factory', None)

    with TestClient(knowledge_app) as c:
        yield c


# ============================================================================
# Tests: Pre-Insert beim Enqueue
# ============================================================================

def test_reindex_pre_insert_queued_status(client, session):
    """POST /reindex legt sofort einen Run mit status='queued' in der DB an."""
    resp = client.post('/api/knowledge/reindex')
    assert resp.status_code == 202, resp.text

    data = resp.json()
    job_id = data['job_id']

    # In der Test-DB nachschlagen (gleiche DB, da conftest.py POSTGRES_PORT gesetzt hat)
    run = session.query(VaultReindexRun).filter(
        VaultReindexRun.job_id == job_id
    ).first()
    assert run is not None, f'Kein VaultReindexRun für job_id={job_id!r} gefunden'
    assert run.status == 'queued'
    assert run.trigger == 'api'
    assert run.scope == 'full'
    assert run.target_path is None


def test_reindex_pre_insert_single_file(client, session):
    """POST /reindex mit path: Pre-Insert hat scope='single-file' und target_path gesetzt."""
    resp = client.post(
        '/api/knowledge/reindex',
        json={'path': 'strategies/teststrategie-dws/STATUS.md'},
    )
    assert resp.status_code == 202, resp.text
    data = resp.json()
    job_id = data['job_id']

    run = session.query(VaultReindexRun).filter(
        VaultReindexRun.job_id == job_id
    ).first()
    assert run is not None
    assert run.status == 'queued'
    assert run.scope == 'single-file'
    assert run.target_path == 'strategies/teststrategie-dws/STATUS.md'
    assert run.trigger == 'api'


# ============================================================================
# Tests: Job-Lifecycle (gemockter Indexer)
# ============================================================================

def test_job_lifecycle_success(session, monkeypatch):
    """Erfolgreicher Job-Lauf setzt status='success' und füllt alle Ergebnis-Felder."""
    run = _insert_run(session, job_id='job-lifecycle-ok', status='queued')
    run_db_id = run.id

    # get_session()-Cache invalidieren damit Test-DB genutzt wird
    monkeypatch.setattr(_db_module, '_engine', None)
    monkeypatch.setattr(_db_module, '_session_factory', None)

    fake_indexer_result = {
        'files_scanned': 10,
        'files_reindexed': 3,
        'files_deleted': 1,
        'chunks_written': 42,
        'duration_seconds': 5.0,
    }

    # Indexer-Modul als sys.modules-Mock setzen (reindex ist lokaler Import in der Task-Funktion)
    mock_indexer_module = MagicMock()
    mock_indexer_module.reindex.return_value = fake_indexer_result
    monkeypatch.setitem(sys.modules, 'services.vbt.knowledge.indexer', mock_indexer_module)
    monkeypatch.setitem(sys.modules, 'services.vbt.knowledge', MagicMock())
    monkeypatch.setitem(sys.modules, 'services.vbt', MagicMock())

    # rq.get_current_job mocken (kein aktiver Job-Kontext im Test)
    mock_rq = MagicMock()
    mock_rq.get_current_job.return_value = None
    monkeypatch.setitem(sys.modules, 'rq', mock_rq)

    import services.api.worker_tasks as wt
    wt.reindex_vault_chunk_job(target_path=None, trigger='api', run_db_id=run_db_id)

    session.expire(run)
    session.refresh(run)
    assert run.status == 'success'
    assert run.files_scanned == 10
    assert run.files_reindexed == 3
    assert run.files_deleted == 1
    assert run.chunks_written == 42
    assert run.finished_at is not None
    assert run.error_message is None


def test_job_lifecycle_failed(session, monkeypatch):
    """Fehlgeschlagener Job setzt status='failed', error_message und propagiert Exception."""
    run = _insert_run(session, job_id='job-lifecycle-fail', status='queued')
    run_db_id = run.id

    monkeypatch.setattr(_db_module, '_engine', None)
    monkeypatch.setattr(_db_module, '_session_factory', None)

    import services.api.worker_tasks as wt

    mock_indexer_module = MagicMock()
    mock_indexer_module.reindex.side_effect = RuntimeError('Indexer kaputt')
    monkeypatch.setitem(sys.modules, 'services.vbt.knowledge.indexer', mock_indexer_module)
    monkeypatch.setitem(sys.modules, 'services.vbt.knowledge', MagicMock())
    monkeypatch.setitem(sys.modules, 'services.vbt', MagicMock())

    # rq-get_current_job mocken (kein aktiver Job-Kontext im Test)
    monkeypatch.setitem(sys.modules, 'rq', MagicMock(get_current_job=MagicMock(return_value=None)))

    with pytest.raises(RuntimeError, match='Indexer kaputt'):
        wt.reindex_vault_chunk_job(target_path=None, trigger='api', run_db_id=run_db_id)

    session.expire(run)
    session.refresh(run)
    assert run.status == 'failed'
    assert run.error_message == 'Indexer kaputt'
    assert run.finished_at is not None


# ============================================================================
# Tests: GET /api/knowledge/runs
# ============================================================================

def test_list_runs_returns_sorted_list(client, session):
    """GET /runs liefert sortierte Liste nach created_at DESC."""
    _insert_run(session, job_id='run-old', status='success')
    _insert_run(session, job_id='run-new', status='success')

    resp = client.get('/api/knowledge/runs')
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert 'runs' in data
    assert 'total' in data
    assert 'limit' in data
    assert data['limit'] == 50


def test_list_runs_limit(client, session):
    """limit-Parameter begrenzt die Anzahl der zurückgelieferten Einträge."""
    for i in range(5):
        _insert_run(session, job_id=f'run-limit-{i}')

    resp = client.get('/api/knowledge/runs?limit=2')
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data['runs']) <= 2
    assert data['limit'] == 2


def test_list_runs_status_filter(client, session):
    """status-Filter liefert nur Einträge mit passendem Status."""
    _insert_run(session, job_id='run-filter-success', status='success')
    _insert_run(session, job_id='run-filter-failed', status='failed')

    resp = client.get('/api/knowledge/runs?status=success')
    assert resp.status_code == 200, resp.text
    runs = resp.json()['runs']
    assert all(r['status'] == 'success' for r in runs)


def test_list_runs_scope_filter(client, session):
    """scope-Filter liefert nur Einträge mit passendem Scope."""
    _insert_run(session, job_id='run-scope-full', scope='full')
    _insert_run(session, job_id='run-scope-single', scope='single-file', target_path='foo.md')

    resp = client.get('/api/knowledge/runs?scope=single-file')
    assert resp.status_code == 200, resp.text
    runs = resp.json()['runs']
    assert all(r['scope'] == 'single-file' for r in runs)


# ============================================================================
# Tests: GET /api/knowledge/runs/{id}
# ============================================================================

def test_get_run_by_id_returns_200(client, session):
    """GET /runs/{id} liefert 200 für vorhandenen Run."""
    run = _insert_run(session, job_id='run-get-ok', status='success')

    resp = client.get(f'/api/knowledge/runs/{run.id}')
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data['id'] == run.id
    assert data['job_id'] == 'run-get-ok'
    assert data['status'] == 'success'


def test_get_run_by_id_returns_404(client, session):
    """GET /runs/{id} liefert 404 für nicht existierenden Run."""
    resp = client.get('/api/knowledge/runs/999999')
    assert resp.status_code == 404, resp.text


def test_chunks_per_second_calculated(client, session):
    """chunks_per_second wird korrekt berechnet wenn beide Werte gesetzt sind."""
    run = _insert_run(
        session,
        job_id='run-cps-ok',
        status='success',
        chunks_written=100,
        duration_seconds=20.0,
    )

    resp = client.get(f'/api/knowledge/runs/{run.id}')
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert 'chunks_per_second' in data
    assert data['chunks_per_second'] == pytest.approx(5.0)


def test_chunks_per_second_null_when_duration_zero(client, session):
    """chunks_per_second ist NULL wenn duration_seconds=0 (Division durch 0 vermeiden)."""
    run = _insert_run(
        session,
        job_id='run-cps-zero',
        status='success',
        chunks_written=50,
        duration_seconds=0.0,
    )

    resp = client.get(f'/api/knowledge/runs/{run.id}')
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data['chunks_per_second'] is None


def test_chunks_per_second_null_when_missing(client, session):
    """chunks_per_second ist NULL wenn chunks_written oder duration_seconds fehlt."""
    run = _insert_run(
        session,
        job_id='run-cps-missing',
        status='queued',
        chunks_written=None,
        duration_seconds=None,
    )

    resp = client.get(f'/api/knowledge/runs/{run.id}')
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data['chunks_per_second'] is None
