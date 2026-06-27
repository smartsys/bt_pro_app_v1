"""Tests für GET /api/knowledge/stats Endpoint (Ticket 30).

Prüft:
- Grundlegendes Schema: 200, alle Felder vorhanden (index, runs, top_paths_by_chunks).
- Leerer Index: chunk_count=0, file_count=0, kein Crash.
- Keine erfolgreichen Runs: last_success_at=null, Durchschnitte NULL.
- Erfolgsquote-Basis: by_status korrekt befüllt.
- Trigger-Verteilung: by_trigger korrekt befüllt.
- Top-Pfade: sortiert nach Chunk-Anzahl DESC, max 10 Einträge.
- avg_chunks_per_file korrekt berechnet.

Verwendet PostgreSQL Test-DB (Port 5562) via db_engine/session-Fixtures
aus tests/conftest.py.
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))

from user_data.utils.database.models import VaultChunk, VaultReindexRun
import user_data.utils.database.db as _db_module


# ============================================================================
# Hilfsfunktionen
# ============================================================================

_FAKE_EMBEDDING = [0.0] * 1024


def _insert_chunk(
    session,
    vault_path: str,
    chunk_index: int = 0,
    content: str = 'Testinhalt',
    indexed_at: datetime | None = None,
) -> VaultChunk:
    """Legt einen VaultChunk direkt in der Test-DB an."""
    now = datetime.now()
    chunk = VaultChunk(
        vault_path=vault_path,
        chunk_index=chunk_index,
        content=content,
        frontmatter_json=None,
        mtime=now,
        embedding=_FAKE_EMBEDDING,
        indexed_at=indexed_at or now,
    )
    session.add(chunk)
    session.commit()
    session.refresh(chunk)
    return chunk


def _insert_run(
    session,
    job_id: str = 'test-job-stats',
    trigger: str = 'api',
    status: str = 'success',
    duration_seconds: float | None = None,
    chunks_written: int | None = None,
    finished_at: datetime | None = None,
) -> VaultReindexRun:
    """Legt einen VaultReindexRun direkt in der Test-DB an.

    Setzt finished_at automatisch auf 'jetzt' wenn status 'success' oder 'failed'
    ist und kein expliziter Wert übergeben wurde.
    """
    now = datetime.now()
    # finished_at bei abgeschlossenen Runs (success + failed) automatisch befüllen
    if finished_at is None and status in ('success', 'failed'):
        finished_at = now
    run = VaultReindexRun(
        job_id=job_id,
        scope='full',
        target_path=None,
        trigger=trigger,
        status=status,
        started_at=now,
        finished_at=finished_at,
        duration_seconds=duration_seconds,
        chunks_written=chunks_written,
        created_at=now,
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
    """TestClient mit gemocktem embed-Backend und Test-DB-Session."""
    monkeypatch.setattr(
        'services.api.routes.api_knowledge.embed',
        lambda text: _FAKE_EMBEDDING,
    )
    monkeypatch.setattr(
        'services.api.routes.api_knowledge.get_redis_connection',
        lambda: None,
    )
    monkeypatch.setattr(_db_module, '_engine', None)
    monkeypatch.setattr(_db_module, '_session_factory', None)

    with TestClient(knowledge_app) as c:
        yield c


# ============================================================================
# Tests: Schema-Vollständigkeit
# ============================================================================

def test_stats_schema_fields_complete(client, session):
    """GET /stats liefert 200 mit vollständigem Schema."""
    _insert_chunk(session, vault_path='test/file.md', chunk_index=0)
    _insert_run(session, job_id='run-schema-1', status='success')

    resp = client.get('/api/knowledge/stats')
    assert resp.status_code == 200, resp.text

    data = resp.json()

    # Top-Ebene
    assert 'index' in data
    assert 'runs' in data
    assert 'top_paths_by_chunks' in data

    # Index-Felder
    idx = data['index']
    for field in ['chunk_count', 'file_count', 'vault_size_bytes', 'embedding_dim',
                  'embedding_size_bytes_est', 'avg_chunks_per_file',
                  'last_indexed_at', 'oldest_indexed_at']:
        assert field in idx, f'Index-Feld fehlt: {field}'

    # Runs-Felder
    runs = data['runs']
    for field in ['total', 'by_status', 'by_trigger', 'last_run_at',
                  'last_success_at', 'last_failure_at',
                  'avg_duration_seconds_last_10', 'avg_chunks_per_second_last_10']:
        assert field in runs, f'Runs-Feld fehlt: {field}'

    # by_status muss alle vier Statuswerte enthalten
    for s in ['queued', 'running', 'success', 'failed']:
        assert s in runs['by_status'], f'by_status fehlt: {s}'

    # by_trigger muss alle drei Trigger enthalten
    for t in ['api', 'scheduler', 'cli']:
        assert t in runs['by_trigger'], f'by_trigger fehlt: {t}'


# ============================================================================
# Tests: Leerer Index
# ============================================================================

def test_stats_empty_index_no_crash(client, session):
    """Leere DB: alle Index-Felder konsistent 0/NULL, kein Crash."""
    resp = client.get('/api/knowledge/stats')
    assert resp.status_code == 200, resp.text

    data = resp.json()
    idx = data['index']
    assert idx['chunk_count'] == 0
    assert idx['file_count'] == 0
    assert idx['vault_size_bytes'] == 0
    assert idx['avg_chunks_per_file'] is None
    assert idx['last_indexed_at'] is None
    assert idx['oldest_indexed_at'] is None
    assert idx['embedding_size_bytes_est'] is None

    runs = data['runs']
    assert runs['total'] == 0
    assert runs['last_run_at'] is None
    assert runs['last_success_at'] is None
    assert runs['last_failure_at'] is None
    assert runs['avg_duration_seconds_last_10'] is None
    assert runs['avg_chunks_per_second_last_10'] is None
    assert runs['by_status']['queued'] == 0
    assert runs['by_status']['running'] == 0
    assert runs['by_status']['success'] == 0
    assert runs['by_status']['failed'] == 0

    assert data['top_paths_by_chunks'] == []


# ============================================================================
# Tests: Keine erfolgreichen Runs
# ============================================================================

def test_stats_no_successful_runs(client, session):
    """Nur fehlgeschlagene Runs: last_success_at=null, Durchschnitte NULL."""
    _insert_run(session, job_id='run-fail-1', status='failed')
    _insert_run(session, job_id='run-fail-2', status='failed')

    resp = client.get('/api/knowledge/stats')
    assert resp.status_code == 200, resp.text

    data = resp.json()
    runs = data['runs']

    assert runs['last_success_at'] is None
    assert runs['avg_duration_seconds_last_10'] is None
    assert runs['avg_chunks_per_second_last_10'] is None
    assert runs['by_status']['failed'] == 2
    assert runs['by_status']['success'] == 0
    assert runs['last_failure_at'] is not None


# ============================================================================
# Tests: Erfolgsquoten-Basis (by_status korrekte Counts)
# ============================================================================

def test_stats_by_status_correct(client, session):
    """by_status zählt korrekt über alle Runs."""
    _insert_run(session, job_id='bs-success-1', status='success')
    _insert_run(session, job_id='bs-success-2', status='success')
    _insert_run(session, job_id='bs-failed-1', status='failed')
    _insert_run(session, job_id='bs-queued-1', status='queued')

    resp = client.get('/api/knowledge/stats')
    assert resp.status_code == 200, resp.text

    by_status = resp.json()['runs']['by_status']
    assert by_status['success'] == 2
    assert by_status['failed'] == 1
    assert by_status['queued'] == 1
    assert by_status['running'] == 0


# ============================================================================
# Tests: Trigger-Verteilung
# ============================================================================

def test_stats_by_trigger_correct(client, session):
    """by_trigger zählt korrekt nach Trigger-Typ."""
    _insert_run(session, job_id='bt-api-1', trigger='api', status='success')
    _insert_run(session, job_id='bt-api-2', trigger='api', status='success')
    _insert_run(session, job_id='bt-sched-1', trigger='scheduler', status='success')

    resp = client.get('/api/knowledge/stats')
    assert resp.status_code == 200, resp.text

    by_trigger = resp.json()['runs']['by_trigger']
    assert by_trigger['api'] == 2
    assert by_trigger['scheduler'] == 1
    assert by_trigger['cli'] == 0


# ============================================================================
# Tests: Index-Aggregat
# ============================================================================

def test_stats_index_counts(client, session):
    """chunk_count, file_count und avg_chunks_per_file korrekt."""
    _insert_chunk(session, vault_path='file-a.md', chunk_index=0)
    _insert_chunk(session, vault_path='file-a.md', chunk_index=1)
    _insert_chunk(session, vault_path='file-b.md', chunk_index=0)

    resp = client.get('/api/knowledge/stats')
    assert resp.status_code == 200, resp.text

    idx = resp.json()['index']
    assert idx['chunk_count'] == 3
    assert idx['file_count'] == 2
    # 3 Chunks / 2 Dateien = 1.5
    assert idx['avg_chunks_per_file'] == pytest.approx(1.5)
    assert idx['embedding_dim'] == 1024
    assert idx['embedding_size_bytes_est'] == 3 * 1024 * 4


# ============================================================================
# Tests: Top-Pfade
# ============================================================================

def test_stats_top_paths_sorted_desc(client, session):
    """top_paths_by_chunks ist nach Chunk-Anzahl absteigend sortiert."""
    # Datei A: 3 Chunks, Datei B: 1 Chunk, Datei C: 2 Chunks
    for i in range(3):
        _insert_chunk(session, vault_path='top-a.md', chunk_index=i)
    _insert_chunk(session, vault_path='top-b.md', chunk_index=0)
    for i in range(2):
        _insert_chunk(session, vault_path='top-c.md', chunk_index=i)

    resp = client.get('/api/knowledge/stats')
    assert resp.status_code == 200, resp.text

    top = resp.json()['top_paths_by_chunks']
    assert len(top) == 3
    assert top[0]['vault_path'] == 'top-a.md'
    assert top[0]['chunks'] == 3
    assert top[1]['vault_path'] == 'top-c.md'
    assert top[1]['chunks'] == 2
    assert top[2]['vault_path'] == 'top-b.md'
    assert top[2]['chunks'] == 1


def test_stats_top_paths_max_10(client, session):
    """top_paths_by_chunks liefert maximal 10 Einträge."""
    for i in range(15):
        _insert_chunk(session, vault_path=f'many-file-{i:02d}.md', chunk_index=0)

    resp = client.get('/api/knowledge/stats')
    assert resp.status_code == 200, resp.text

    top = resp.json()['top_paths_by_chunks']
    assert len(top) <= 10


# ============================================================================
# Tests: Durchschnittswerte erfolgreicher Runs
# ============================================================================

def test_stats_avg_duration_last_10(client, session):
    """avg_duration_seconds_last_10 wird korrekt über erfolgreiche Runs berechnet."""
    _insert_run(session, job_id='avg-dur-1', status='success', duration_seconds=10.0)
    _insert_run(session, job_id='avg-dur-2', status='success', duration_seconds=20.0)
    _insert_run(session, job_id='avg-dur-fail', status='failed', duration_seconds=5.0)

    resp = client.get('/api/knowledge/stats')
    assert resp.status_code == 200, resp.text

    avg = resp.json()['runs']['avg_duration_seconds_last_10']
    # Nur die erfolgreichen: (10 + 20) / 2 = 15.0
    assert avg == pytest.approx(15.0, abs=0.1)
