"""Tests für repository_strategies.py und api_strategy.py — Ticket 09.

Repository-Tests: CRUD für StrategyConcept + StrategyIteration.
version ist eine fortlaufende Integer-Nummer pro Konzept (High-Water-Mark
strategy_concepts.iteration_counter), die beim Anlegen automatisch vergeben wird.

API-Tests: FastAPI TestClient gegen echte PostgreSQL-DB.

Verwendet PostgreSQL (JSONB-kompatibel), Test-DB via VBT_TEST_DATABASE_URL (Port 5562).
db_engine und session kommen aus tests/conftest.py (Ticket 14).
"""

# GEÄNDERT: Ticket 14 — Lokale db_engine/session-Fixtures entfernt, zentrale
# Fixtures aus conftest.py werden automatisch injiziert.
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Projekt-Root für Imports
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from user_data.utils.database.models import StrategyConcept, StrategyIteration

from user_data.utils.database.repository_strategies import (
    create_concept,
    create_iteration,
    get_concept,
    get_concept_by_slug,
    get_iteration,
    list_concepts,
    list_iterations,
    next_iteration_version,
    update_concept,
    update_iteration,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope='function')
def test_concept(session) -> StrategyConcept:
    """Test-Konzept für Isolations-Tests."""
    concept = create_concept(
        session,
        slug='test-unit-abc',
        name='Test Unit ABC',
        status='active',
        created_by='pytest',
    )
    return concept


@pytest.fixture(scope='function')
def test_iteration(session, test_concept) -> StrategyIteration:
    """Test-Iteration für Isolations-Tests.

    version ist eine fortlaufende Integer-Nummer aus dem Konzept-Zähler.
    """
    version = next_iteration_version(session, test_concept.id)
    iteration = create_iteration(
        session,
        concept_id=test_concept.id,
        version=version,
        status='draft',
        created_by='pytest',
    )
    return iteration


# ============================================================================
# Repository-Tests: Concepts
# ============================================================================

def test_create_concept(session):
    """Anlegen und Wiederfinden eines Konzepts per Slug."""
    concept = create_concept(
        session,
        slug='test-slug-repo-1',
        name='Test Repo Konzept 1',
        category='Trend',
        status='active',
        created_by='pytest',
    )
    assert concept.id is not None
    assert concept.slug == 'test-slug-repo-1'
    assert concept.name == 'Test Repo Konzept 1'
    assert concept.category == 'Trend'
    assert concept.created_by == 'pytest'

    # Wiederfinden per Slug
    found = get_concept_by_slug(session, 'test-slug-repo-1')
    assert found is not None
    assert found.id == concept.id


def test_get_concept_by_id(session, test_concept):
    """Konzept per ID laden."""
    found = get_concept(session, test_concept.id)
    assert found is not None
    assert found.slug == 'test-unit-abc'


def test_list_concepts_includes_created(session, test_concept):
    """list_concepts gibt das angelegte Konzept zurück."""
    concepts = list_concepts(session)
    ids = [c.id for c in concepts]
    assert test_concept.id in ids


def test_update_concept(session, test_concept):
    """Konzept-Name aktualisieren."""
    updated = update_concept(session, test_concept.id, name='Geänderter Name')
    assert updated is not None
    assert updated.name == 'Geänderter Name'


def test_update_concept_not_found(session):
    """update_concept gibt None für nicht existierende ID zurück."""
    result = update_concept(session, 999999, name='Nicht vorhanden')
    assert result is None


# ============================================================================
# Repository-Tests: Iterations
# ============================================================================

def test_create_iteration(session, test_concept):
    """Iteration anlegen und per ID finden.

    version wird als fortlaufende Integer-Nummer aus dem Konzept-Zähler vergeben.
    """
    version = next_iteration_version(session, test_concept.id)
    iteration = create_iteration(
        session,
        concept_id=test_concept.id,
        version=version,
        status='draft',
        created_by='pytest',
    )
    assert iteration.id is not None
    assert isinstance(iteration.version, int)
    assert iteration.version == version
    assert iteration.concept_id == test_concept.id

    found = get_iteration(session, iteration.id)
    assert found is not None
    assert found.version == version


def test_list_iterations_by_concept(session, test_concept):
    """list_iterations filtert korrekt nach concept_id."""
    v1 = next_iteration_version(session, test_concept.id)
    v2 = next_iteration_version(session, test_concept.id)
    create_iteration(session, concept_id=test_concept.id, version=v1, status='active')
    create_iteration(session, concept_id=test_concept.id, version=v2, status='archived')

    results = list_iterations(session, concept_id=test_concept.id)
    versions = [r.version for r in results]
    assert v1 in versions
    assert v2 in versions


def test_update_iteration(session, test_iteration):
    """Iterations-Status aktualisieren."""
    updated = update_iteration(session, test_iteration.id, status='active')
    assert updated is not None
    assert updated.status == 'active'


def test_update_iteration_not_found(session):
    """update_iteration gibt None für nicht existierende ID zurück."""
    result = update_iteration(session, 999999, status='active')
    assert result is None


# ============================================================================
# API-Tests via FastAPI TestClient
# ============================================================================

@pytest.fixture(scope='module')
def api_client():
    """FastAPI TestClient mit nur dem strategy-Router (kein rq/redis nötig)."""
    # DB-Verbindung kommt aus den Umgebungsvariablen (conftest lädt .env), kein Fallback
    # Minimale Test-App — nur strategy-Router, keine rq/redis-Abhängigkeiten
    from fastapi import FastAPI
    from services.api.routes.api_strategy import router as strategy_router
    test_app = FastAPI()
    test_app.include_router(strategy_router)
    with TestClient(test_app) as client:
        yield client


@pytest.mark.integration
def test_api_list_concepts_returns_200(api_client):
    """GET /api/strategy/concepts -> 200 mit items-Liste.

    Integrations-Test: FastAPI-Client gegen echte DB (Port 5560).
    """
    response = api_client.get('/api/strategy/concepts')
    assert response.status_code == 200
    data = response.json()
    assert data['error'] is None
    assert 'items' in data['data']
    assert isinstance(data['data']['items'], list)


@pytest.mark.integration
def test_api_list_concepts_contains_known_concept(api_client):
    """Bestandsdaten: teststrategie-Konzept in der Liste.

    Integrations-Test: erwartet das persistierte teststrategie-Konzept in der Arbeits-DB.
    """
    response = api_client.get('/api/strategy/concepts')
    assert response.status_code == 200
    items = response.json()['data']['items']
    slugs = [item['slug'] for item in items]
    assert 'teststrategie' in slugs, f"teststrategie nicht gefunden. Gefundene Slugs: {slugs}"


@pytest.mark.integration
def test_api_list_iterations_returns_200(api_client):
    """GET /api/strategy/iterations -> 200 mit items-Liste.

    Integrations-Test: FastAPI-Client gegen echte DB (Port 5560).
    """
    response = api_client.get('/api/strategy/iterations')
    assert response.status_code == 200
    data = response.json()
    assert data['error'] is None
    assert 'items' in data['data']


@pytest.mark.integration
def test_api_list_iterations_versions_are_int(api_client):
    """Bestandsdaten: alle Iterations-Versionen sind fortlaufende Integer-Nummern.

    Integrations-Test gegen die Arbeits-DB. version ist seit dem Schema-Umbau
    eine Integer-Nummer pro Konzept (kein String-Slug mehr).
    """
    response = api_client.get('/api/strategy/iterations')
    assert response.status_code == 200
    items = response.json()['data']['items']
    versions = [item['version'] for item in items]
    assert all(isinstance(v, int) for v in versions), \
        f"Nicht alle Versionen sind Integer: {versions}"


@pytest.mark.integration
def test_api_create_and_get_concept(api_client):
    """POST /api/strategy/concepts -> Concept anlegen + GET Detail."""
    payload = {
        "slug": "test-api-roundtrip-xyz",
        "name": "API Roundtrip Test",
        "category": "Test",
        "status": "draft",
    }
    create_resp = api_client.post('/api/strategy/concepts', json=payload)
    assert create_resp.status_code == 200
    created = create_resp.json()['data']
    assert created['slug'] == 'test-api-roundtrip-xyz'
    assert created['name'] == 'API Roundtrip Test'
    concept_id = created['id']

    # Detail abrufen
    get_resp = api_client.get(f'/api/strategy/concepts/{concept_id}')
    assert get_resp.status_code == 200
    assert get_resp.json()['data']['id'] == concept_id

    # Aufräumen
    from user_data.utils.database.db import get_session as _get_sess
    sess = _get_sess()
    try:
        c = sess.query(StrategyConcept).filter(StrategyConcept.id == concept_id).first()
        if c:
            # Erst Iterationen löschen (FK-Constraint)
            sess.query(StrategyIteration).filter(StrategyIteration.concept_id == concept_id).delete()
            sess.delete(c)
            sess.commit()
    finally:
        sess.close()


@pytest.mark.integration
def test_api_update_concept(api_client):
    """PUT /api/strategy/concepts/{id} -> Name aktualisieren."""
    payload = {"slug": "test-api-update-abc", "name": "Vor Update", "status": "draft"}
    create_resp = api_client.post('/api/strategy/concepts', json=payload)
    assert create_resp.status_code == 200
    concept_id = create_resp.json()['data']['id']

    update_resp = api_client.put(f'/api/strategy/concepts/{concept_id}', json={"name": "Nach Update"})
    assert update_resp.status_code == 200
    assert update_resp.json()['data']['name'] == 'Nach Update'

    # Aufräumen
    from user_data.utils.database.db import get_session as _get_sess
    sess = _get_sess()
    try:
        c = sess.query(StrategyConcept).filter(StrategyConcept.id == concept_id).first()
        if c:
            sess.delete(c)
            sess.commit()
    finally:
        sess.close()


@pytest.mark.integration
def test_api_create_iteration_roundtrip(api_client):
    """POST /api/strategy/iterations + GET Detail Roundtrip."""
    # Erst Konzept anlegen
    concept_resp = api_client.post('/api/strategy/concepts', json={
        "slug": "test-iter-rt-xyz",
        "name": "Test Iter RT",
        "status": "draft",
    })
    assert concept_resp.status_code == 200
    concept_id = concept_resp.json()['data']['id']

    # Iteration anlegen — version wird server-seitig automatisch vergeben
    iter_payload = {
        "concept_id": concept_id,
        "version_name": "v0.1 RT",
        "status": "draft",
        "spec_json": {"test": True},
    }
    iter_resp = api_client.post('/api/strategy/iterations', json=iter_payload)
    assert iter_resp.status_code == 200
    iter_data = iter_resp.json()['data']
    # Neues Konzept -> erste Iteration bekommt Nummer 1
    assert iter_data['version'] == 1
    assert iter_data['concept_id'] == concept_id
    iteration_id = iter_data['id']

    # Detail abrufen
    get_resp = api_client.get(f'/api/strategy/iterations/{iteration_id}')
    assert get_resp.status_code == 200
    assert get_resp.json()['data']['id'] == iteration_id

    # Aufräumen
    from user_data.utils.database.db import get_session as _get_sess
    sess = _get_sess()
    try:
        it = sess.query(StrategyIteration).filter(StrategyIteration.id == iteration_id).first()
        if it:
            sess.delete(it)
        c = sess.query(StrategyConcept).filter(StrategyConcept.id == concept_id).first()
        if c:
            sess.delete(c)
        sess.commit()
    finally:
        sess.close()


@pytest.mark.integration
def test_api_update_iteration(api_client):
    """PUT /api/strategy/iterations/{id} -> Status aktualisieren."""
    concept_resp = api_client.post('/api/strategy/concepts', json={
        "slug": "test-iter-upd-xyz",
        "name": "Test Iter Update",
        "status": "draft",
    })
    concept_id = concept_resp.json()['data']['id']

    iter_resp = api_client.post('/api/strategy/iterations', json={
        "concept_id": concept_id,
        "version_name": "v0.1 upd",
        "status": "draft",
    })
    iteration_id = iter_resp.json()['data']['id']

    update_resp = api_client.put(f'/api/strategy/iterations/{iteration_id}', json={"status": "active"})
    assert update_resp.status_code == 200
    assert update_resp.json()['data']['status'] == 'active'

    # Aufräumen
    from user_data.utils.database.db import get_session as _get_sess
    sess = _get_sess()
    try:
        it = sess.query(StrategyIteration).filter(StrategyIteration.id == iteration_id).first()
        if it:
            sess.delete(it)
        c = sess.query(StrategyConcept).filter(StrategyConcept.id == concept_id).first()
        if c:
            sess.delete(c)
        sess.commit()
    finally:
        sess.close()


@pytest.mark.integration
def test_api_copy_iteration(api_client):
    """POST /api/strategy/iterations/{id}/copy -> dupliziert Iteration mit (Kopie)-Suffix.

    Prüft: identisches spec_json, neue ID/Version, Kollisions-Nummerierung
    bei mehrfachem Kopieren sowie 404 für unbekannte Iterationen.
    """
    concept_resp = api_client.post('/api/strategy/concepts', json={
        "slug": "test-api-copy-iter-xyz", "name": "Copy Iter Test", "status": "draft",
    })
    assert concept_resp.status_code == 200
    concept_id = concept_resp.json()['data']['id']

    spec = {"indicators": {"sma": {"indicator": "vbt:MA", "window": 10}}, "rules": {}}
    iter_resp = api_client.post('/api/strategy/iterations', json={
        "concept_id": concept_id,
        "version_name": "v1 copytest",
        "spec_json": spec,
        "status": "active",
    })
    assert iter_resp.status_code == 200
    orig_id = iter_resp.json()['data']['id']

    created_ids = [orig_id]
    try:
        # Erste Kopie
        copy_resp = api_client.post(f'/api/strategy/iterations/{orig_id}/copy')
        assert copy_resp.status_code == 200
        copy1 = copy_resp.json()['data']
        created_ids.append(copy1['id'])
        assert copy1['id'] != orig_id
        assert copy1['concept_id'] == concept_id
        assert '(Kopie)' in (copy1['version_name'] or '')
        assert copy1['spec_json'] == spec

        # Zweite Kopie -> Kollisions-Nummerierung, eindeutige version
        copy_resp2 = api_client.post(f'/api/strategy/iterations/{orig_id}/copy')
        assert copy_resp2.status_code == 200
        copy2 = copy_resp2.json()['data']
        created_ids.append(copy2['id'])
        assert copy2['version'] != copy1['version']
        assert '(Kopie 2)' in (copy2['version_name'] or '')

        # 404 für unbekannte Iteration
        assert api_client.post('/api/strategy/iterations/999999/copy').status_code == 404
    finally:
        from user_data.utils.database.db import get_session as _get_sess
        sess = _get_sess()
        try:
            for iid in created_ids:
                it = sess.query(StrategyIteration).filter(StrategyIteration.id == iid).first()
                if it:
                    sess.delete(it)
            c = sess.query(StrategyConcept).filter(StrategyConcept.id == concept_id).first()
            if c:
                sess.delete(c)
            sess.commit()
        finally:
            sess.close()


@pytest.mark.integration
def test_api_get_concept_not_found(api_client):
    """GET /api/strategy/concepts/999999 -> 404."""
    response = api_client.get('/api/strategy/concepts/999999')
    assert response.status_code == 404


@pytest.mark.integration
def test_api_get_iteration_not_found(api_client):
    """GET /api/strategy/iterations/999999 -> 404."""
    response = api_client.get('/api/strategy/iterations/999999')
    assert response.status_code == 404
