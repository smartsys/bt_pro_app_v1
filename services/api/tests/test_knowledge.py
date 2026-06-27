"""Tests für GET /api/knowledge/search und POST /api/knowledge/reindex.

Verwendet PostgreSQL Test-DB (Port 5562) via db_engine/session-Fixtures
aus tests/conftest.py.

Das Embedding-Backend (services.vbt.knowledge.embedding.embed) wird per
monkeypatch durch einen deterministischen Fake-Vektor ersetzt, sodass
kein externer Dienst benötigt wird.
"""

import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Projekt-Root für alle Importe
_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))

from user_data.utils.database.models import VaultChunk
from user_data.utils.database.db import get_session


# ============================================================================
# Hilfsfunktionen
# ============================================================================

_EMBED_DIM = 1024


def _unit_vector(index: int) -> list[float]:
    """Deterministischer Fake-Vektor: nur an Position index eine 1.0, Rest 0.0.

    Erzeugt orthogonale Vektoren für reproduzierbare Cosine-Similarity-Tests.
    Dimension muss <= 1024 sein.
    """
    v = [0.0] * _EMBED_DIM
    v[index % _EMBED_DIM] = 1.0
    return v


def _insert_chunk(
    session,
    vault_path: str,
    chunk_index: int,
    content: str,
    frontmatter: dict | None = None,
    embed_index: int = 0,
) -> VaultChunk:
    """Hilfsfunktion: Chunk direkt in die Test-DB einfügen."""
    chunk = VaultChunk(
        vault_path=vault_path,
        chunk_index=chunk_index,
        heading_path=None,
        content=content,
        frontmatter_json=frontmatter,
        mtime=datetime(2024, 1, 1),
        embedding=_unit_vector(embed_index),
    )
    session.add(chunk)
    session.commit()
    session.refresh(chunk)
    return chunk


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope='module')
def knowledge_app() -> FastAPI:
    """Minimale FastAPI-App mit nur dem knowledge-Router."""
    from services.api.routes.api_knowledge import router as knowledge_router
    app = FastAPI()
    app.include_router(knowledge_router)
    return app


@pytest.fixture(scope='function')
def client(knowledge_app: FastAPI, monkeypatch) -> Generator:
    """TestClient mit gemocktem embed()-Backend.

    embed() gibt immer _unit_vector(0) zurück, damit die Suche
    reproduzierbar ist. rq wird via sys.modules gemockt, da es im
    Windows-venv nicht installiert ist.

    get_session() Cache wird zurückgesetzt, damit die Route die Test-DB nutzt.
    """
    monkeypatch.setattr(
        'services.api.routes.api_knowledge.embed',
        lambda text: _unit_vector(0),
    )
    monkeypatch.setattr(
        'services.api.routes.api_knowledge.get_redis_connection',
        lambda: None,
    )

    # rq via sys.modules mocken (lazy import in trigger_reindex)
    # GEÄNDERT: Ticket 28 — uuid-basierte job_id verhindert UniqueViolation bei mehreren Test-Läufen
    mock_job = MagicMock()
    mock_job.id = f'test-job-{uuid.uuid4().hex[:8]}'
    mock_queue_instance = MagicMock()
    mock_queue_instance.enqueue.return_value = mock_job
    mock_queue_class = MagicMock(return_value=mock_queue_instance)
    mock_rq = MagicMock()
    mock_rq.Queue = mock_queue_class
    monkeypatch.setitem(sys.modules, 'rq', mock_rq)

    # get_session()-Cache invalidieren, damit Route die Test-DB-Engine nutzt.
    # conftest.py hat POSTGRES_PORT bereits auf den Test-DB-Port gesetzt.
    import user_data.utils.database.db as _db_module
    monkeypatch.setattr(_db_module, '_engine', None)
    monkeypatch.setattr(_db_module, '_session_factory', None)

    with TestClient(knowledge_app) as c:
        yield c


# ============================================================================
# Tests: GET /api/knowledge/search
# ============================================================================

def test_search_returns_expected_structure(client, session):
    """Suche liefert results-Array mit korrekten Feldern."""
    _insert_chunk(session, 'strategies/teststrategie/STATUS.md', 0, 'Teststrategie Status Inhalt', embed_index=0)

    resp = client.get('/api/knowledge/search?q=Teststrategie&k=5')
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert 'results' in data
    assert 'query' in data
    assert 'total' in data
    assert data['query'] == 'Teststrategie'
    assert isinstance(data['results'], list)
    assert data['total'] == len(data['results'])


def test_search_result_fields(client, session):
    """Jedes Ergebnis hat alle erwarteten Felder."""
    _insert_chunk(
        session,
        'strategies/teststrategie/v0.41.md',
        0,
        'Inhalt des Chunks',
        frontmatter={'tags': ['strategy', 'teststrategie'], 'iteration_id': 41},
        embed_index=0,
    )

    resp = client.get('/api/knowledge/search?q=test&k=1')
    assert resp.status_code == 200, resp.text
    results = resp.json()['results']
    assert len(results) >= 1

    r = results[0]
    assert 'vault_path' in r
    assert 'chunk_index' in r
    assert 'heading_path' in r
    assert 'content' in r
    assert 'frontmatter' in r
    assert 'similarity' in r
    assert isinstance(r['similarity'], float)
    assert 0.0 <= r['similarity'] <= 1.0


def test_search_similarity_sorted_desc(client, session):
    """Ergebnisse sind nach Similarity absteigend sortiert."""
    # Chunk 0: identischer Vektor zu Query (index=0) -> Similarity ~ 1.0
    _insert_chunk(session, 'a/b.md', 0, 'Chunk A', embed_index=0)
    # Chunk 1: orthogonaler Vektor -> Similarity ~ 0.0
    _insert_chunk(session, 'c/d.md', 0, 'Chunk C', embed_index=1)

    resp = client.get('/api/knowledge/search?q=test&k=10')
    assert resp.status_code == 200, resp.text
    results = resp.json()['results']
    assert len(results) >= 2

    similarities = [r['similarity'] for r in results]
    assert similarities == sorted(similarities, reverse=True), (
        f'Ergebnisse nicht Similarity-DESC sortiert: {similarities}'
    )


def test_search_tag_filter(client, session):
    """Tag-Filter liefert nur Chunks mit dem angegebenen Tag."""
    _insert_chunk(
        session,
        'strategies/teststrategie/STATUS.md',
        0,
        'Chunk mit Tag X',
        frontmatter={'tags': ['strategy', 'tagX']},
        embed_index=0,
    )
    _insert_chunk(
        session,
        'strategies/other/README.md',
        0,
        'Chunk ohne Tag X',
        frontmatter={'tags': ['other']},
        embed_index=0,
    )

    resp = client.get('/api/knowledge/search?q=test&tag=tagX')
    assert resp.status_code == 200, resp.text
    results = resp.json()['results']

    assert len(results) == 1, f'Erwartet 1 Treffer, erhalten {len(results)}: {results}'
    tags = results[0]['frontmatter'].get('tags', [])
    assert 'tagX' in tags


def test_search_path_prefix_filter(client, session):
    """path_prefix-Filter liefert nur Chunks mit passendem vault_path."""
    _insert_chunk(session, 'strategies/teststrategie/STATUS.md', 0, 'Teststrategie Chunk', embed_index=0)
    _insert_chunk(session, 'lessons/general.md', 0, 'Allgemeine Lektion', embed_index=0)

    resp = client.get('/api/knowledge/search?q=test&path_prefix=strategies/teststrategie')
    assert resp.status_code == 200, resp.text
    results = resp.json()['results']

    assert len(results) == 1, f'Erwartet 1 Treffer, erhalten {len(results)}'
    assert results[0]['vault_path'].startswith('strategies/teststrategie')


def test_search_k_limit(client, session):
    """k-Parameter begrenzt die Trefferzahl."""
    for i in range(5):
        _insert_chunk(session, f'file_{i}.md', 0, f'Inhalt {i}', embed_index=0)

    resp = client.get('/api/knowledge/search?q=test&k=2')
    assert resp.status_code == 200, resp.text
    results = resp.json()['results']
    assert len(results) <= 2


def test_search_empty_result(client, session):
    """Suche mit path_prefix-Filter der nichts trifft: leeres results-Array."""
    _insert_chunk(session, 'strategies/teststrategie/STATUS.md', 0, 'Inhalt', embed_index=0)

    resp = client.get('/api/knowledge/search?q=test&path_prefix=nonexistent/path')
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data['results'] == []
    assert data['total'] == 0


# ============================================================================
# Tests: POST /api/knowledge/reindex
# ============================================================================

def test_reindex_without_body_returns_202_full(client):
    """POST ohne Body: Status 202, scope=full, target_path=None."""
    resp = client.post('/api/knowledge/reindex')
    assert resp.status_code == 202, resp.text

    data = resp.json()
    assert data['scope'] == 'full'
    assert data['target_path'] is None
    assert 'job_id' in data
    assert data['job_id']  # nicht leer


def test_reindex_with_path_returns_single_file(client):
    """POST mit path: scope=single-file, target_path gesetzt."""
    resp = client.post(
        '/api/knowledge/reindex',
        json={'path': 'strategies/teststrategie-dws/STATUS.md'},
    )
    assert resp.status_code == 202, resp.text

    data = resp.json()
    assert data['scope'] == 'single-file'
    assert data['target_path'] == 'strategies/teststrategie-dws/STATUS.md'
    # GEÄNDERT: Ticket 28 — job_id ist jetzt uuid-basiert, nur Präsenz prüfen
    assert data['job_id']  # nicht leer


def test_reindex_with_empty_body_returns_full(client):
    """POST mit leerem JSON-Body {}: scope=full."""
    resp = client.post('/api/knowledge/reindex', json={})
    assert resp.status_code == 202, resp.text
    assert resp.json()['scope'] == 'full'
