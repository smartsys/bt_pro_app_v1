"""Tests für die Lese-Routen des Befunds (Teilaufgabe 3).

Geprüft wird, was die drei neuen Endpunkte leisten:
  - GET /api/testset-run-findings/{id}: ein Befund samt Kontext, Soll und (falls
    geschlossen) den fünf Ist-Gruppen; 404 bei unbekannter ID
  - GET /api/testset-run-findings/by-iteration/{iteration_id}: Historie einer
    Iteration, chronologisch, ohne Sortier-/Filteroption
  - PATCH /api/testset-run-findings/{id}/interpretation: Deutung nachtragen, ohne
    die Zahlen zu berühren
  - Kein Verdict-Feld im Ausgabe-Schema (Anforderung 7)
  - Die DSR steht in der Antwort nie ohne N und SR0

Endpunkt-Funktionen werden direkt aufgerufen (Projekt-Konvention, siehe
test_testset_runs_api.py) — kein TestClient/HTTP-Layer nötig. `get_session` wird auf
eine Sessionmaker-Factory gegen die Test-DB umgebogen, damit jeder Routen-Aufruf eine
eigene, unabhängige Session bekommt (wie der `wired`-Fixture in
test_testset_run_finding_phase2.py).
"""

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from services.api.utils.best_criteria_labels import BEST_CRITERIA_LABELS
from user_data.utils.database.models import TestSetRun
from user_data.utils.database.repository_findings import (
    close_testset_run_finding,
    create_testset_run_finding,
)


@pytest.fixture(autouse=True)
def wired(monkeypatch, db_engine):
    """Verdrahtet den Routen-Modul-Einstieg auf die Test-DB statt auf die Arbeits-DB."""
    session_factory = sessionmaker(bind=db_engine)
    monkeypatch.setattr(
        'services.api.routes.api_testset_run_findings.get_session', session_factory,
    )


@pytest.fixture
def open_finding(session):
    """Ein offener Befund (Phase 1) ohne TestSetRun-Bindung — genügt für die Routen-Tests."""
    return create_testset_run_finding(
        session=session,
        testset_run_id=None,
        iteration_id=777,
        concept_id=9,
        testset_id=11,
        indicator_config_id=22,
        spec_runner_version='4.0.0',
        goal_snapshot={'sharpe_min': 1.0},
        best_criteria=list(BEST_CRITERIA_LABELS.keys()),
        planned_n_runs=2,
        planned_combos_per_run=10,
    )


@pytest.fixture
def closed_finding(session):
    """Ein geschlossener Befund mit einem Robustheits-Block (N + SR0 + DSR zusammen)."""
    testset_run = TestSetRun(
        testset_id=11, strategy_family='teststrategie', strategy_name='1',
        n_runs_total=1, indicators_config_json={}, status='completed',
    )
    session.add(testset_run)
    session.commit()
    finding = create_testset_run_finding(
        session=session, testset_run_id=testset_run.id, iteration_id=778, concept_id=9,
        testset_id=11, indicator_config_id=22, spec_runner_version='4.0.0',
        goal_snapshot=None, best_criteria=list(BEST_CRITERIA_LABELS.keys()),
        planned_n_runs=1, planned_combos_per_run=9,
    )
    ist_groups = {
        'scope': {'n_runs': 1, 'n_eff': None, 'n_eff_reason': 'nicht ausgewiesen'},
        'candidates': {'per_run': []},
        'robustness': {
            'dsr': [{
                'run_id': 1, 'n': 9, 'sr0': 1.13, 'best_sharpe_ratio': 1.5,
                'best': {'result_id': 5, 'deflated_sharpe_ratio': 0.62}, 'best_reason': None,
            }],
        },
        'benchmarks': {'concept_benchmark_line': None},
        'warnings': {'items': [], 'not_evaluated': []},
    }
    close_testset_run_finding(session, finding, **ist_groups)
    return finding


# ============================================================================
# GET /api/testset-run-findings/{id}
# ============================================================================

def test_get_finding_returns_context_and_soll(open_finding):
    from services.api.routes.api_testset_run_findings import get_finding

    resp = get_finding(open_finding.id)
    assert resp['error'] is None
    data = resp['data']
    assert data['iteration_id'] == 777
    assert data['testset_id'] == 11
    assert data['goal_snapshot_json'] == {'sharpe_min': 1.0}
    assert data['closed_at'] is None
    # Deutung ist ein eigenes, getrenntes Objekt.
    assert data['interpretation'] == {'text': None, 'interpreted_at': None}


def test_get_finding_survives_deleted_testset_run(session, closed_finding):
    """Der TestSetRun darf gelöscht sein — der Befund bleibt lesbar (Grund für die eigene Tabelle)."""
    from services.api.routes.api_testset_run_findings import get_finding

    session.query(TestSetRun).filter(TestSetRun.id == closed_finding.testset_run_id).delete()
    session.commit()

    resp = get_finding(closed_finding.id)
    assert resp['data']['testset_run_id'] == closed_finding.testset_run_id
    assert resp['data']['iteration_id'] == 778


def test_get_finding_unknown_id_raises_404():
    from services.api.routes.api_testset_run_findings import get_finding

    with pytest.raises(HTTPException) as exc:
        get_finding(9_999_999)
    assert exc.value.status_code == 404


def test_dsr_never_appears_without_n_and_sr0(closed_finding):
    """DSR, N und SR0 stehen in der API-Antwort in genau einem Objekt zusammen."""
    from services.api.routes.api_testset_run_findings import get_finding

    data = get_finding(closed_finding.id)['data']
    block = data['robustness_json']['dsr'][0]
    assert block['n'] == 9
    assert block['sr0'] == 1.13
    assert block['best']['deflated_sharpe_ratio'] == 0.62


def test_no_verdict_field_in_schema():
    """Weder Score noch Ampel noch Sortier-Rang im Ausgabe-Schema (Anforderung 7)."""
    from services.api.routes.api_testset_run_findings import TestSetRunFindingOut

    fields = set(TestSetRunFindingOut.model_fields)
    for forbidden in ('passed', 'verdict', 'score', 'rank', 'bestanden'):
        assert forbidden not in fields


# ============================================================================
# GET /api/testset-run-findings/by-testset-run/{testset_run_id}
# ============================================================================

def test_by_testset_run_returns_newest_finding_and_total(session):
    """Bei mehreren Befunden desselben Testset-Laufs (Rerun) gewinnt der jüngste,
    die Gesamtzahl macht die Historie sichtbar."""
    from services.api.routes.api_testset_run_findings import get_finding_for_testset_run_route

    testset_run = TestSetRun(
        testset_id=11, strategy_family='teststrategie', strategy_name='1',
        n_runs_total=1, indicators_config_json={}, status='completed',
    )
    session.add(testset_run)
    session.commit()

    older = create_testset_run_finding(
        session=session, testset_run_id=testset_run.id, iteration_id=333, concept_id=9,
        testset_id=11, indicator_config_id=22, spec_runner_version='4.0.0',
        goal_snapshot=None, best_criteria=list(BEST_CRITERIA_LABELS.keys()),
        planned_n_runs=1, planned_combos_per_run=5,
    )
    newer = create_testset_run_finding(
        session=session, testset_run_id=testset_run.id, iteration_id=333, concept_id=9,
        testset_id=11, indicator_config_id=22, spec_runner_version='4.0.0',
        goal_snapshot=None, best_criteria=list(BEST_CRITERIA_LABELS.keys()),
        planned_n_runs=1, planned_combos_per_run=5,
    )
    assert newer.id != older.id

    resp = get_finding_for_testset_run_route(testset_run.id)
    data = resp['data']
    assert data['finding']['id'] == newer.id
    assert data['total_for_testset_run'] == 2


def test_by_testset_run_unknown_id_raises_404():
    from services.api.routes.api_testset_run_findings import get_finding_for_testset_run_route

    with pytest.raises(HTTPException) as exc:
        get_finding_for_testset_run_route(9_999_999)
    assert exc.value.status_code == 404


# ============================================================================
# GET /api/testset-run-findings/by-iteration/{iteration_id}
# ============================================================================

def test_history_is_chronological_and_unfiltered(session):
    from services.api.routes.api_testset_run_findings import list_findings_for_iteration

    first = create_testset_run_finding(
        session=session, testset_run_id=None, iteration_id=555, concept_id=9,
        testset_id=11, indicator_config_id=22, spec_runner_version='4.0.0',
        goal_snapshot=None, best_criteria=list(BEST_CRITERIA_LABELS.keys()),
        planned_n_runs=1, planned_combos_per_run=5,
    )
    second = create_testset_run_finding(
        session=session, testset_run_id=None, iteration_id=555, concept_id=9,
        testset_id=11, indicator_config_id=22, spec_runner_version='4.0.0',
        goal_snapshot=None, best_criteria=list(BEST_CRITERIA_LABELS.keys()),
        planned_n_runs=1, planned_combos_per_run=5,
    )

    resp = list_findings_for_iteration(555)
    ids = [item['id'] for item in resp['data']['items']]
    assert ids == [first.id, second.id]
    assert resp['data']['total'] == 2


def test_history_empty_for_unknown_iteration():
    from services.api.routes.api_testset_run_findings import list_findings_for_iteration

    resp = list_findings_for_iteration(9_999_999)
    assert resp['data']['items'] == []
    assert resp['data']['total'] == 0


# ============================================================================
# PATCH /api/testset-run-findings/{id}/interpretation
# ============================================================================

def test_set_interpretation_leaves_numbers_untouched(closed_finding):
    from services.api.routes.api_testset_run_findings import (
        InterpretationIn,
        set_finding_interpretation_route,
    )

    scope_before = closed_finding.scope_json

    resp = set_finding_interpretation_route(
        closed_finding.id, InterpretationIn(text='Deutung, keine Messung.'),
    )
    data = resp['data']
    assert data['interpretation']['text'] == 'Deutung, keine Messung.'
    assert data['interpretation']['interpreted_at'] is not None
    assert data['scope_json'] == scope_before


def test_set_interpretation_unknown_id_raises_404():
    from services.api.routes.api_testset_run_findings import (
        InterpretationIn,
        set_finding_interpretation_route,
    )

    with pytest.raises(HTTPException) as exc:
        set_finding_interpretation_route(9_999_999, InterpretationIn(text='x'))
    assert exc.value.status_code == 404
