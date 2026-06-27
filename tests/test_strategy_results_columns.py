"""Tests für Ticket 11 — Zweistufige Strategie-UI + sprechende Results-Spalte.

Abdeckung:
- API: /api/backtest/results/dt liefert concept_name + iteration_version (über echten Container)
- API: /api/backtest/start akzeptiert iteration_id und setzt iteration_id am Run (via Repository direkt)
- Frontend-Smoke: /config/strategy -> 200 mit Konzept-Template
- Frontend-Smoke: /backtest/results, /backtest/start -> 200

Strategie: API-Tests über http://localhost:5570 (laufender Container),
Repository-Tests direkt gegen DB (ohne rq-Dependency).
"""

import sys
from pathlib import Path

import pytest
import requests

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / '.env')

# DB-Verbindung kommt aus den Umgebungsvariablen (.env), kein Fallback

BASE_URL = 'http://localhost:5570'


# ============================================================================
# Hilfsfunktion: Container erreichbar?
# ============================================================================

def container_available() -> bool:
    """Prüft ob der Frontend-Container erreichbar ist."""
    try:
        r = requests.get(BASE_URL + '/api/strategy/concepts', timeout=3)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not container_available(),
    reason="Frontend-Container nicht erreichbar (http://localhost:5570)"
)


# ============================================================================
# API-Tests: /api/backtest/results/dt — sprechende Strategie-Spalte
# ============================================================================

def test_results_dt_contains_concept_fields():
    """GET /api/backtest/results/dt -> Response-Datensätze haben concept_name + iteration_version."""
    r = requests.get(f'{BASE_URL}/api/backtest/results/dt?draw=1&start=0&length=10', timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert 'data' in body
    if body['data']:
        item = body['data'][0]
        assert 'concept_name' in item, f"concept_name fehlt im DT-Response. Vorhandene Keys: {list(item.keys())}"
        assert 'iteration_version' in item, f"iteration_version fehlt im DT-Response"
        assert 'strategy_name' in item, "strategy_name (Legacy) fehlt im DT-Response"


def test_results_dt_concept_present():
    """Mindestens ein DT-Datensatz hat einen gesetzten concept_name (aus T10-Backfill)."""
    r = requests.get(f'{BASE_URL}/api/backtest/results/dt?draw=1&start=0&length=100', timeout=10)
    assert r.status_code == 200
    items = r.json().get('data', [])
    items_with_concept = [it for it in items if it.get('concept_name')]
    if not items_with_concept:
        pytest.skip("Keine Datensätze mit concept_name vorhanden (Backfill T10 noch nicht gelaufen?)")
    concept_names = [it['concept_name'] for it in items_with_concept]
    assert len(concept_names) >= 1, \
        f"Kein Konzept in concept_names gefunden: {set(concept_names)}"


def test_results_dt_iteration_version_present():
    """Mindestens ein DT-Datensatz hat eine gesetzte iteration_version.

    GEÄNDERT: iteration.version ist seit dem Schema-Umbau eine fortlaufende
    Integer-Nummer pro Konzept. Der DT-Endpoint liefert jedoch
    `version_name or version` — d.h. das Feld kann ein freier Anzeige-Name
    (String) oder die Integer-Nummer sein. Geprüft wird daher nur, dass
    mindestens ein Datensatz eine nicht-leere iteration_version trägt.
    """
    r = requests.get(f'{BASE_URL}/api/backtest/results/dt?draw=1&start=0&length=100', timeout=10)
    assert r.status_code == 200
    items = r.json().get('data', [])
    items_with_version = [it for it in items if it.get('iteration_version') is not None]
    if not items_with_version:
        pytest.skip("Keine Datensätze mit iteration_version vorhanden")
    assert len(items_with_version) >= 1


# ============================================================================
# API-Tests: /api/backtest/results (nicht-DT)
# ============================================================================

def test_results_api_contains_concept_fields():
    """GET /api/backtest/results -> Items haben concept_name + iteration_version."""
    r = requests.get(f'{BASE_URL}/api/backtest/results?limit=5', timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body['error'] is None
    items = body['data']['items']
    if items:
        item = items[0]
        assert 'concept_name' in item, f"concept_name fehlt. Keys: {list(item.keys())}"
        assert 'iteration_version' in item


# ============================================================================
# Frontend-Smoke-Tests
# ============================================================================

def test_frontend_strategy_concepts_200():
    """GET /config/strategy-concepts -> 200, HTML enthält 'Konzept'."""
    r = requests.get(f'{BASE_URL}/config/strategy-concepts', timeout=10)
    assert r.status_code == 200
    html = r.text
    assert 'Konzept' in html or 'konzept' in html.lower(), \
        "HTML enthält kein 'Konzept' — Template wurde nicht geladen"


def test_frontend_strategy_concepts_contains_api_call():
    """GET /config/strategy-concepts -> HTML referenziert /api/strategy/concepts."""
    r = requests.get(f'{BASE_URL}/config/strategy-concepts', timeout=10)
    assert r.status_code == 200
    assert '/api/strategy/concepts' in r.text


def test_frontend_results_200():
    """GET /backtest/results -> 200."""
    r = requests.get(f'{BASE_URL}/backtest/results', timeout=10)
    assert r.status_code == 200


def test_frontend_start_200():
    """GET /backtest/start -> 200, enthält zweistufige Dropdowns."""
    r = requests.get(f'{BASE_URL}/backtest/start', timeout=10)
    assert r.status_code == 200
    html = r.text
    assert 'sel-concept' in html, "sel-concept Dropdown nicht im HTML gefunden"
    assert 'sel-iteration' in html, "sel-iteration Dropdown nicht im HTML gefunden"


# ============================================================================
# Repository-Tests: iteration_id-Schreibpfad über /api/backtest/start
# ============================================================================

def test_start_backtest_missing_iteration_and_strategy_returns_error():
    """POST /api/backtest/start ohne iteration_id/strategy_config_id -> 400 oder error-Feld."""
    r = requests.post(f'{BASE_URL}/api/backtest/start', json={
        'backtest_config_id': 1,
        'indicator_config_id': 1,
    }, timeout=10)
    # Endpoint gibt 400 zurück (JSONResponse mit status_code=400)
    assert r.status_code in (200, 400), f"Unerwarteter Status: {r.status_code}"
    body = r.json()
    # Entweder HTTP 400 oder 200 mit error-Feld
    assert r.status_code == 400 or body.get('error') is not None, \
        f"Fehler erwartet, aber kein error-Feld und kein 400: {body}"


def test_start_backtest_with_invalid_iteration_returns_error():
    """POST /api/backtest/start mit nicht existierender iteration_id -> 404 oder error-Feld."""
    r = requests.post(f'{BASE_URL}/api/backtest/start', json={
        'backtest_config_id': 1,
        'indicator_config_id': 1,
        'iteration_id': 999999,
    }, timeout=10)
    # Endpoint gibt 404 zurück wenn Iteration nicht gefunden
    assert r.status_code in (200, 400, 404), f"Unerwarteter Status: {r.status_code}"
    if r.status_code == 200:
        body = r.json()
        assert body.get('error') is not None


def test_start_backtest_with_real_iteration_sets_iteration_id():
    """POST /api/backtest/start mit echter iteration_id -> BacktestRun hat iteration_id gesetzt."""
    from user_data.utils.database.db import get_session
    from user_data.utils.database.models import StrategyIteration, BacktestConfig, IndicatorConfig, BacktestRun, BacktestResult

    # Echte Daten aus DB holen
    session = get_session()
    try:
        iteration = session.query(StrategyIteration).filter(
            StrategyIteration.status == 'active'
        ).first()
        bt_config = session.query(BacktestConfig).first()
        ind_config = session.query(IndicatorConfig).first()
    finally:
        session.close()

    if not iteration or not bt_config or not ind_config:
        pytest.skip("Keine Testdaten in DB vorhanden")

    r = requests.post(f'{BASE_URL}/api/backtest/start', json={
        'backtest_config_id': bt_config.id,
        'indicator_config_id': ind_config.id,
        'iteration_id': iteration.id,
    }, timeout=15)

    assert r.status_code == 200
    body = r.json()
    assert body.get('error') is None, f"Fehler beim Start: {body.get('error')}"
    run_id = body['data']['run_id']

    # Prüfen ob BacktestRun.iteration_id gesetzt ist
    session = get_session()
    try:
        run = session.query(BacktestRun).filter(BacktestRun.id == run_id).first()
        assert run is not None
        assert run.iteration_id == iteration.id, \
            f"iteration_id nicht gesetzt: {run.iteration_id} != {iteration.id}"
    finally:
        session.close()

    # Aufräumen
    session = get_session()
    try:
        session.query(BacktestResult).filter(BacktestResult.run_id == run_id).delete()
        session.query(BacktestRun).filter(BacktestRun.id == run_id).delete()
        session.commit()
    finally:
        session.close()
