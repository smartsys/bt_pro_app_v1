"""Tests für die Iterations-Log-API (Ticket 67) — append-only Denkprotokoll.

Tests laufen gegen eine isolierte, file-basierte SQLite-DB (TestClient-Fixture
analog zu tests/test_obsidian_paths_and_vault_create.py) — kein Live-Container
nötig. File-basiert statt In-Memory, damit der TestClient (separater Thread)
dieselben Daten sieht.
"""
import sys
import uuid
from datetime import datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from user_data.utils.database.models import BacktestRun, Base


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def _test_engine(tmp_path):
    """Isolierte, file-basierte SQLite-Engine mit dem vollen Schema."""
    db_file = tmp_path / f'test_iteration_logs_{uuid.uuid4().hex[:8]}.db'
    engine = create_engine(f'sqlite:///{db_file}', connect_args={'check_same_thread': False}, echo=False)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def strategy_client(_test_engine, monkeypatch):
    """FastAPI TestClient mit nur dem strategy-Router gegen die isolierte DB."""
    session_factory = sessionmaker(bind=_test_engine, autoflush=True)

    def mock_get_session():
        return session_factory()

    # Modul-Level-Import in api_strategy patchen (nicht db_module — die Kopie dort ist lokal)
    import services.api.routes.api_strategy as api_strategy_module
    monkeypatch.setattr(api_strategy_module, 'get_session', mock_get_session)

    from services.api.routes.api_strategy import router as strategy_router
    test_app = FastAPI()
    test_app.include_router(strategy_router)

    with TestClient(test_app) as client:
        yield client


@pytest.fixture
def db_session(_test_engine):
    """Direkter DB-Zugriff für Test-Setup, das die API nicht abdeckt (z.B. BacktestRun anlegen)."""
    session_factory = sessionmaker(bind=_test_engine, autoflush=True)
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def sample_concept(strategy_client):
    """Test-Konzept via API anlegen."""
    response = strategy_client.post('/api/strategy/concepts', json={
        'slug': 'test-log-concept', 'name': 'Test Log Concept', 'status': 'active',
    })
    assert response.status_code == 200, response.text
    return response.json()['data']


@pytest.fixture
def sample_iteration(strategy_client, sample_concept):
    """Test-Iteration via API anlegen."""
    response = strategy_client.post('/api/strategy/iterations', json={
        'concept_id': sample_concept['id'], 'type': 'generic', 'status': 'active',
    })
    assert response.status_code == 200, response.text
    return response.json()['data']


# ============================================================================
# Roundtrip + Chronologie
# ============================================================================

def test_create_log_entry_roundtrip_via_get(strategy_client, sample_iteration):
    """POST legt einen Eintrag an, GET liefert ihn zurück."""
    iid = sample_iteration['id']
    create_resp = strategy_client.post(
        f'/api/strategy/iterations/{iid}/logs',
        json={'text': 'Erster Versuch: RSI-Schwelle auf 30 gesetzt.'},
    )
    assert create_resp.status_code == 200, create_resp.text
    created = create_resp.json()['data']
    assert created['iteration_id'] == iid
    assert created['text'] == 'Erster Versuch: RSI-Schwelle auf 30 gesetzt.'
    assert created['run_id'] is None

    list_resp = strategy_client.get(f'/api/strategy/iterations/{iid}/logs')
    assert list_resp.status_code == 200
    data = list_resp.json()['data']
    assert data['total'] == 1
    assert data['items'][0]['id'] == created['id']


def test_multiple_entries_returned_chronologically_ascending(strategy_client, sample_iteration):
    """Mehrere Einträge kommen älteste zuerst."""
    iid = sample_iteration['id']
    for txt in ('Erster Eintrag', 'Zweiter Eintrag', 'Dritter Eintrag'):
        resp = strategy_client.post(f'/api/strategy/iterations/{iid}/logs', json={'text': txt})
        assert resp.status_code == 200

    items = strategy_client.get(f'/api/strategy/iterations/{iid}/logs').json()['data']['items']
    assert [i['text'] for i in items] == ['Erster Eintrag', 'Zweiter Eintrag', 'Dritter Eintrag']
    assert [i['id'] for i in items] == sorted(i['id'] for i in items)


def test_create_log_entry_with_run_id_roundtrips(strategy_client, sample_iteration):
    """run_id wird als lose Referenz mitgeschrieben und zurückgegeben."""
    iid = sample_iteration['id']
    resp = strategy_client.post(
        f'/api/strategy/iterations/{iid}/logs',
        json={'text': 'Mit Run-Bezug', 'run_id': 9999},
    )
    assert resp.status_code == 200
    assert resp.json()['data']['run_id'] == 9999


# ============================================================================
# Validierung
# ============================================================================

def test_empty_text_rejected_with_422(strategy_client, sample_iteration):
    """Leerer Text wird abgelehnt."""
    iid = sample_iteration['id']
    resp = strategy_client.post(f'/api/strategy/iterations/{iid}/logs', json={'text': ''})
    assert resp.status_code == 422


def test_whitespace_only_text_rejected_with_422(strategy_client, sample_iteration):
    """Nur-Whitespace-Text wird nach Trim als leer abgelehnt."""
    iid = sample_iteration['id']
    resp = strategy_client.post(f'/api/strategy/iterations/{iid}/logs', json={'text': '   \n\t  '})
    assert resp.status_code == 422


def test_create_log_entry_for_unknown_iteration_returns_404(strategy_client):
    """POST auf eine nicht existierende Iteration liefert 404."""
    resp = strategy_client.post('/api/strategy/iterations/999999/logs', json={'text': 'Egal'})
    assert resp.status_code == 404


def test_list_log_entries_for_unknown_iteration_returns_404(strategy_client):
    """GET auf eine nicht existierende Iteration liefert 404."""
    resp = strategy_client.get('/api/strategy/iterations/999999/logs')
    assert resp.status_code == 404


# ============================================================================
# Append-only — kein Update/Delete
# ============================================================================

def test_no_update_endpoint_for_log_entries(strategy_client, sample_iteration):
    """Es existiert keine PUT-Route für Log-Einträge (Sammel- oder Einzel-Pfad)."""
    iid = sample_iteration['id']
    created = strategy_client.post(
        f'/api/strategy/iterations/{iid}/logs', json={'text': 'Original'}
    ).json()['data']

    collection_resp = strategy_client.put(f'/api/strategy/iterations/{iid}/logs', json={'text': 'Geändert'})
    assert collection_resp.status_code in (404, 405)

    single_resp = strategy_client.put(
        f'/api/strategy/iterations/{iid}/logs/{created["id"]}', json={'text': 'Geändert'}
    )
    assert single_resp.status_code in (404, 405)


def test_no_delete_endpoint_for_log_entries(strategy_client, sample_iteration):
    """Es existiert keine DELETE-Route für Log-Einträge (Sammel- oder Einzel-Pfad)."""
    iid = sample_iteration['id']
    created = strategy_client.post(
        f'/api/strategy/iterations/{iid}/logs', json={'text': 'Original'}
    ).json()['data']

    collection_resp = strategy_client.delete(f'/api/strategy/iterations/{iid}/logs')
    assert collection_resp.status_code in (404, 405)

    single_resp = strategy_client.delete(f'/api/strategy/iterations/{iid}/logs/{created["id"]}')
    assert single_resp.status_code in (404, 405)


# ============================================================================
# Löschverhalten
# ============================================================================

def test_deleting_iteration_removes_its_log_entries(strategy_client, sample_iteration):
    """Iteration löschen räumt die zugehörigen Log-Einträge mit."""
    iid = sample_iteration['id']
    strategy_client.post(f'/api/strategy/iterations/{iid}/logs', json={'text': 'Wird mitgelöscht'})

    delete_resp = strategy_client.delete(f'/api/strategy/iterations/{iid}')
    assert delete_resp.status_code == 200, delete_resp.text

    list_resp = strategy_client.get(f'/api/strategy/iterations/{iid}/logs')
    assert list_resp.status_code == 404


def test_run_id_pointing_to_deleted_run_still_returns_full_entry(strategy_client, db_session, sample_iteration):
    """Ein Log-Eintrag bleibt vollständig lesbar, wenn der referenzierte Run inzwischen gelöscht wurde."""
    run = BacktestRun(
        strategy_family='test', strategy_name='test', symbol='BTCUSDT', exchange='binance',
        timeframe='4h', start_date=datetime(2024, 1, 1), end_date=datetime(2024, 6, 1),
        backtest_config_json={}, indicators_config_json={},
    )
    db_session.add(run)
    db_session.commit()
    run_id = run.id

    iid = sample_iteration['id']
    create_resp = strategy_client.post(
        f'/api/strategy/iterations/{iid}/logs',
        json={'text': 'Bezug auf einen Run', 'run_id': run_id},
    )
    assert create_resp.status_code == 200

    db_session.delete(run)
    db_session.commit()

    list_resp = strategy_client.get(f'/api/strategy/iterations/{iid}/logs')
    assert list_resp.status_code == 200
    items = list_resp.json()['data']['items']
    assert len(items) == 1
    assert items[0]['run_id'] == run_id
    assert items[0]['text'] == 'Bezug auf einen Run'
