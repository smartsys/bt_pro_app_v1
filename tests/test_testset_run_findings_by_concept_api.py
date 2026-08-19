"""Tests für GET /api/testset-run-findings/by-concept/{concept_id} (Ticket 85).

Deckt die Anforderungen aus Ticket 85, Anforderung 6 ab:
  - chronologische Reihenfolge (created_at ASC, id ASC)
  - leere Liste bei einem Konzept ohne Befunde (kein Fehler)
  - Befunde eines gelöschten TestSetRun erscheinen weiterhin (lose Referenz)

Endpunkt-Funktion wird direkt aufgerufen (Projekt-Konvention, siehe
test_testset_run_findings_api.py) — kein TestClient/HTTP-Layer nötig.
"""

import pytest
from sqlalchemy.orm import sessionmaker

from services.api.utils.best_criteria_labels import BEST_CRITERIA_LABELS
from user_data.utils.database.models import TestSetRun
from user_data.utils.database.repository_findings import create_testset_run_finding


@pytest.fixture(autouse=True)
def wired(monkeypatch, db_engine):
    """Verdrahtet den Routen-Modul-Einstieg auf die Test-DB statt auf die Arbeits-DB."""
    session_factory = sessionmaker(bind=db_engine)
    monkeypatch.setattr(
        'services.api.routes.api_testset_run_findings.get_session', session_factory,
    )


def test_by_concept_returns_findings_chronologically(session):
    from services.api.routes.api_testset_run_findings import list_findings_for_concept

    first = create_testset_run_finding(
        session=session, testset_run_id=None, iteration_id=101, concept_id=42,
        testset_id=11, indicator_config_id=22, spec_runner_version='4.0.0',
        goal_snapshot=None, best_criteria=list(BEST_CRITERIA_LABELS.keys()),
        planned_n_runs=1, planned_combos_per_run=5,
    )
    second = create_testset_run_finding(
        session=session, testset_run_id=None, iteration_id=102, concept_id=42,
        testset_id=11, indicator_config_id=22, spec_runner_version='4.0.0',
        goal_snapshot=None, best_criteria=list(BEST_CRITERIA_LABELS.keys()),
        planned_n_runs=1, planned_combos_per_run=5,
    )

    resp = list_findings_for_concept(42)
    assert resp['error'] is None
    ids = [item['id'] for item in resp['data']['items']]
    assert ids == [first.id, second.id]
    assert resp['data']['total'] == 2


def test_by_concept_empty_list_for_concept_without_findings():
    from services.api.routes.api_testset_run_findings import list_findings_for_concept

    resp = list_findings_for_concept(9_999_999)
    assert resp['error'] is None
    assert resp['data']['items'] == []
    assert resp['data']['total'] == 0


def test_by_concept_ignores_other_concepts(session):
    """Nur Befunde des angefragten Konzepts, keine fremden."""
    from services.api.routes.api_testset_run_findings import list_findings_for_concept

    create_testset_run_finding(
        session=session, testset_run_id=None, iteration_id=201, concept_id=7,
        testset_id=11, indicator_config_id=22, spec_runner_version='4.0.0',
        goal_snapshot=None, best_criteria=list(BEST_CRITERIA_LABELS.keys()),
        planned_n_runs=1, planned_combos_per_run=5,
    )
    own = create_testset_run_finding(
        session=session, testset_run_id=None, iteration_id=202, concept_id=8,
        testset_id=11, indicator_config_id=22, spec_runner_version='4.0.0',
        goal_snapshot=None, best_criteria=list(BEST_CRITERIA_LABELS.keys()),
        planned_n_runs=1, planned_combos_per_run=5,
    )

    resp = list_findings_for_concept(8)
    ids = [item['id'] for item in resp['data']['items']]
    assert ids == [own.id]


def test_by_concept_survives_deleted_testset_run(session):
    """Der TestSetRun darf gelöscht sein — der Befund bleibt lesbar (lose Referenz)."""
    from services.api.routes.api_testset_run_findings import list_findings_for_concept

    testset_run = TestSetRun(
        testset_id=11, strategy_family='teststrategie', strategy_name='1',
        n_runs_total=1, indicators_config_json={}, status='completed',
    )
    session.add(testset_run)
    session.commit()

    finding = create_testset_run_finding(
        session=session, testset_run_id=testset_run.id, iteration_id=303, concept_id=55,
        testset_id=11, indicator_config_id=22, spec_runner_version='4.0.0',
        goal_snapshot=None, best_criteria=list(BEST_CRITERIA_LABELS.keys()),
        planned_n_runs=1, planned_combos_per_run=5,
    )

    session.query(TestSetRun).filter(TestSetRun.id == testset_run.id).delete()
    session.commit()

    resp = list_findings_for_concept(55)
    ids = [item['id'] for item in resp['data']['items']]
    assert ids == [finding.id]
    assert resp['data']['items'][0]['testset_run_id'] == testset_run.id
