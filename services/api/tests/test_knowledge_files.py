"""Tests für GET /api/knowledge/files Endpoint (Ticket 29).

Prüft:
- Grundlegende Listierung: 200, JSON-Format mit files/total/limit/offset.
- Substring-Filter ?q=...: filtert auf vault_path.
- Tag-Filter ?tag=...: filtert auf frontmatter_json-Tags.
- Pagination: limit/offset funktioniert.
- Leere DB: leere Liste, total=0.

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

from user_data.utils.database.models import VaultChunk
import user_data.utils.database.db as _db_module


# ============================================================================
# Hilfsfunktionen
# ============================================================================

_FAKE_EMBEDDING = [0.0] * 1024


def _insert_chunk(
    session,
    vault_path: str,
    chunk_index: int = 0,
    tags: list[str] | None = None,
    content: str = 'Testinhalt',
    mtime: datetime | None = None,
    indexed_at: datetime | None = None,
) -> VaultChunk:
    """Legt einen VaultChunk direkt in der Test-DB an.

    Args:
        session: Aktive Test-DB-Session.
        vault_path: Relativer Vault-Pfad.
        chunk_index: Chunk-Index innerhalb der Datei.
        tags: Optionale Liste von Tags für frontmatter_json.
        content: Chunk-Text.
        mtime: Quelldatei-mtime (Standard: jetzt).
        indexed_at: Indexier-Zeitpunkt (Standard: jetzt).

    Returns:
        Angelegtes VaultChunk-Objekt.
    """
    frontmatter = {'tags': tags} if tags else None
    now = datetime.now()
    chunk = VaultChunk(
        vault_path=vault_path,
        chunk_index=chunk_index,
        content=content,
        frontmatter_json=frontmatter,
        mtime=mtime or now,
        embedding=_FAKE_EMBEDDING,
        indexed_at=indexed_at or now,
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
    """Minimale FastAPI-App mit dem knowledge-Router."""
    from services.api.routes.api_knowledge import router as knowledge_router
    app = FastAPI()
    app.include_router(knowledge_router)
    return app


@pytest.fixture(scope='function')
def client(knowledge_app: FastAPI, monkeypatch) -> Generator:
    """TestClient mit gemocktem embed-Backend und Test-DB-Session.

    - embed() wird durch Fake-Vektor ersetzt.
    - get_session()-Cache wird zurückgesetzt damit Test-DB genutzt wird.
    """
    monkeypatch.setattr(
        'services.api.routes.api_knowledge.embed',
        lambda text: _FAKE_EMBEDDING,
    )
    monkeypatch.setattr(
        'services.api.routes.api_knowledge.get_redis_connection',
        lambda: None,
    )

    # get_session()-Cache invalidieren damit Test-DB genutzt wird
    monkeypatch.setattr(_db_module, '_engine', None)
    monkeypatch.setattr(_db_module, '_session_factory', None)

    with TestClient(knowledge_app) as c:
        yield c


# ============================================================================
# Tests: GET /api/knowledge/files
# ============================================================================

def test_list_files_basic(client, session):
    """GET /files liefert 200 mit korrektem JSON-Format."""
    _insert_chunk(session, vault_path='strategies/teststrategie-dws/STATUS.md', chunk_index=0)
    _insert_chunk(session, vault_path='strategies/teststrategie-dws/STATUS.md', chunk_index=1)
    _insert_chunk(session, vault_path='strategies/other/concept.md', chunk_index=0)

    resp = client.get('/api/knowledge/files')
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert 'files' in data
    assert 'total' in data
    assert 'limit' in data
    assert 'offset' in data
    assert data['limit'] == 100
    assert data['offset'] == 0

    # 2 verschiedene vault_paths → 2 Einträge
    assert data['total'] == 2
    assert len(data['files']) == 2

    # Jede Datei hat die Pflicht-Felder
    for f in data['files']:
        assert 'vault_path' in f
        assert 'chunk_count' in f
        assert 'last_indexed' in f
        assert 'source_mtime' in f
        assert 'tags' in f

    # Chunks korrekt aggregiert
    paths_and_counts = {f['vault_path']: f['chunk_count'] for f in data['files']}
    assert paths_and_counts['strategies/teststrategie-dws/STATUS.md'] == 2
    assert paths_and_counts['strategies/other/concept.md'] == 1


def test_list_files_q_filter(client, session):
    """?q=teststrategie filtert auf vault_path-Substring."""
    _insert_chunk(session, vault_path='strategies/teststrategie-dws/STATUS.md')
    _insert_chunk(session, vault_path='strategies/other/concept.md')
    _insert_chunk(session, vault_path='guides/teststrategie-intro.md')

    resp = client.get('/api/knowledge/files?q=teststrategie')
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data['total'] == 2

    paths = [f['vault_path'] for f in data['files']]
    assert 'strategies/teststrategie-dws/STATUS.md' in paths
    assert 'guides/teststrategie-intro.md' in paths
    assert 'strategies/other/concept.md' not in paths


def test_list_files_tag_filter(client, session):
    """?tag=strategy filtert auf Dateien mit diesem Tag im frontmatter_json."""
    _insert_chunk(session, vault_path='strategies/teststrategie.md', tags=['strategy', 'teststrategie'])
    _insert_chunk(session, vault_path='guides/intro.md', tags=['guide'])
    _insert_chunk(session, vault_path='strategies/other.md', tags=['strategy'])

    resp = client.get('/api/knowledge/files?tag=strategy')
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data['total'] == 2

    paths = [f['vault_path'] for f in data['files']]
    assert 'strategies/teststrategie.md' in paths
    assert 'strategies/other.md' in paths
    assert 'guides/intro.md' not in paths


def test_list_files_pagination(client, session):
    """limit und offset begrenzen und verschieben das Ergebnis korrekt."""
    for i in range(5):
        _insert_chunk(session, vault_path=f'file-{i:02d}.md')

    # Erste Seite
    resp = client.get('/api/knowledge/files?limit=2&offset=0')
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data['total'] == 5
    assert data['limit'] == 2
    assert data['offset'] == 0
    assert len(data['files']) == 2

    # Zweite Seite
    resp2 = client.get('/api/knowledge/files?limit=2&offset=2')
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()
    assert len(data2['files']) == 2
    assert data2['offset'] == 2

    # Keine Überschneidung zwischen Seiten
    paths1 = {f['vault_path'] for f in data['files']}
    paths2 = {f['vault_path'] for f in data2['files']}
    assert len(paths1 & paths2) == 0


def test_list_files_empty(client, session):
    """Keine vault_chunks → leere Liste, total=0."""
    resp = client.get('/api/knowledge/files')
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data['total'] == 0
    assert data['files'] == []
