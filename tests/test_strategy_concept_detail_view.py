"""Tests für die Konzept-Detailseite GET /config/strategy-concepts/{concept_id} (Ticket 85).

Deckt Anforderung 6 (View-Tests) ab: 200 mit Ziel, 200 ohne Ziel (inkl. "keine
Befunde"), 404 bei unbekanntem Konzept. Läuft über einen eigenen TestClient mit
nur dem `views_config`-Router (Muster: `tests/test_iteration_logs.py`), `get_session`
wird sowohl in `views_config` als auch in `api_testset_run_findings` auf die
Test-DB umgebogen (die Detailseite ruft die by-concept-Route intern auf).
"""

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from services.api.utils.autolink import autolink_html
from services.api.utils.best_criteria_labels import BEST_CRITERIA_LABELS
from user_data.utils.database.models import StrategyConcept
from user_data.utils.database.repository_findings import create_testset_run_finding

_FRONTEND_DIR = Path(__file__).resolve().parent.parent / 'services' / 'frontend'


@pytest.fixture
def view_client(monkeypatch, db_engine):
    """TestClient mit nur dem Config-View-Router, gegen die Test-DB verdrahtet."""
    session_factory = sessionmaker(bind=db_engine)

    import services.api.routes.views_config as views_config_module
    import services.api.routes.api_testset_run_findings as findings_module
    monkeypatch.setattr(views_config_module, 'get_session', session_factory)
    monkeypatch.setattr(findings_module, 'get_session', session_factory)

    templates = Jinja2Templates(directory=str(_FRONTEND_DIR / 'templates'))
    templates.env.filters['autolink'] = autolink_html

    test_app = FastAPI()
    test_app.state.templates = templates
    from services.api.routes.views_config import router as views_config_router
    test_app.include_router(views_config_router)

    with TestClient(test_app) as client:
        yield client


def test_detail_page_200_with_goal_and_findings(session, view_client):
    concept = StrategyConcept(
        slug='ziel-konzept', name='Ziel-Konzept', status='active',
        goal_prompt='Finde eine Strategie mit Sharpe >= 1,5.',
        goal_json={'sharpe_min': 1.5},
    )
    session.add(concept)
    session.commit()

    create_testset_run_finding(
        session=session, testset_run_id=None, iteration_id=901, concept_id=concept.id,
        testset_id=11, indicator_config_id=22, spec_runner_version='4.0.0',
        goal_snapshot={'sharpe_min': 1.5}, best_criteria=list(BEST_CRITERIA_LABELS.keys()),
        planned_n_runs=1, planned_combos_per_run=5,
    )
    create_testset_run_finding(
        session=session, testset_run_id=None, iteration_id=902, concept_id=concept.id,
        testset_id=11, indicator_config_id=22, spec_runner_version='4.0.0',
        goal_snapshot={'sharpe_min': 1.5}, best_criteria=list(BEST_CRITERIA_LABELS.keys()),
        planned_n_runs=1, planned_combos_per_run=5,
    )

    resp = view_client.get(f'/config/strategy-concepts/{concept.id}')
    assert resp.status_code == 200
    assert 'Finde eine Strategie mit Sharpe' in resp.text
    assert 'sharpe_min' in resp.text
    assert 'Befund-Historie (2)' in resp.text


def test_detail_page_200_without_goal_shows_honest_hint_and_no_findings(session, view_client):
    concept = StrategyConcept(slug='ohne-ziel', name='Ohne Ziel', status='draft')
    session.add(concept)
    session.commit()

    resp = view_client.get(f'/config/strategy-concepts/{concept.id}')
    assert resp.status_code == 200
    assert 'Kein Ziel hinterlegt' in resp.text
    assert 'Keine Befunde' in resp.text or 'Befund-Historie (0)' in resp.text


def test_detail_page_404_for_unknown_concept(view_client):
    resp = view_client.get('/config/strategy-concepts/9999999')
    assert resp.status_code == 404


def test_detail_page_no_verdict_element(session, view_client):
    """Kein Bestanden/Fehlgeschlagen-Element auf der Seite (Anforderung 2)."""
    concept = StrategyConcept(slug='verdikt-frei', name='Verdikt-Frei', status='active')
    session.add(concept)
    session.commit()

    resp = view_client.get(f'/config/strategy-concepts/{concept.id}')
    assert resp.status_code == 200
    # HTML-Kommentare (z.B. "kein Verdict"-Erklärungen im Quelltext) sind für den
    # Nutzer unsichtbar und zählen nicht als Verdict-Element auf der Seite.
    visible_html = re.sub(r'<!--.*?-->', '', resp.text, flags=re.S)
    for forbidden in ('bestanden', 'Bestanden', 'verdict', 'Verdict', 'passed'):
        assert forbidden not in visible_html
