"""
API-Endpunkte für den Befund eines Testset-Laufs

GET   /api/testset-run-findings/{finding_id}                  — ein Befund
GET   /api/testset-run-findings/by-iteration/{iteration_id}    — Befund-Historie einer Iteration
GET   /api/testset-run-findings/by-concept/{concept_id}        — Befund-Historie eines Konzepts
                                                                   (Konzept-Detailseite)
GET   /api/testset-run-findings/by-testset-run/{testset_run_id} — jüngster Befund eines
                                                                   Testset-Laufs + Gesamtzahl
PATCH /api/testset-run-findings/{finding_id}/interpretation    — Deutung nachtragen

Der Befund entsteht zweiphasig (Kontext+Soll beim Start, Ist-Werte beim Abschluss,
siehe `user_data.utils.database.repository_findings`) und ist danach unveränderlich.
Diese Routen sind reine Lese-Endpunkte plus ein Endpunkt, der ausschließlich den
Freitext der Deutung ergänzt — sie berühren keine der gesperrten Spalten.

**Kein Verdict, keine Sortier-/Filter-Einladung** (Anforderung 7): Die Historie
liefert ausnahmslos die chronologische Reihenfolge, es gibt keinen `sort_by`, keinen
„nur bestandene"-Filter und keinen Gesamtscore in der Antwort.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from user_data.utils.database.db import get_session
from user_data.utils.database.repository_findings import (
    count_testset_run_findings_for_testset_run,
    get_finding_for_testset_run,
    get_testset_run_finding,
    list_testset_run_findings_for_concept,
    list_testset_run_findings_for_iteration,
    set_finding_interpretation,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/testset-run-findings', tags=['testset-run-findings'])


# --- Pydantic Schema ---

class InterpretationOut(BaseModel):
    """Deutung — ausdrücklich als Interpretation gekennzeichnet, getrennt von den Zahlen."""
    text: Optional[str] = None
    interpreted_at: Optional[datetime] = None


class TestSetRunFindingOut(BaseModel):
    """Ausgabe-Schema für einen Befund.

    Bewusst **kein** Verdict-Feld: kein `passed`, kein Gesamtscore, keine Ampel, kein
    Sortier-Rang (Anforderung 7). Die fünf Ist-Gruppen bleiben als JSON-Blöcke
    erhalten, wie sie `finding_aggregation.build_ist_groups` gebaut hat — die DSR steht
    darin immer zusammen mit `N` und `SR0` in einem Objekt, nie allein.
    """
    id: int
    testset_run_id: Optional[int] = None
    iteration_id: int
    concept_id: Optional[int] = None
    testset_id: int
    indicator_config_id: Optional[int] = None
    spec_runner_version: Optional[str] = None
    created_at: datetime
    goal_snapshot_json: Optional[Dict[str, Any]] = None
    goal_missing_reason: Optional[str] = None
    best_criteria_json: List[str]
    planned_n_runs: int
    planned_combos_per_run: Optional[int] = None
    planned_combos_total: Optional[int] = None
    planned_grid_reason: Optional[str] = None
    scope_json: Optional[Dict[str, Any]] = None
    candidates_json: Optional[Dict[str, Any]] = None
    robustness_json: Optional[Dict[str, Any]] = None
    benchmarks_json: Optional[Dict[str, Any]] = None
    warnings_json: Optional[Dict[str, Any]] = None
    holdout_touched: Optional[bool] = None
    closed_at: Optional[datetime] = None
    interpretation: InterpretationOut


class InterpretationIn(BaseModel):
    """Eingabe-Schema zum Nachtragen der Deutung."""
    text: str


def _finding_to_out(finding) -> TestSetRunFindingOut:
    """Baut das Ausgabe-Schema aus einer `TestSetRunFinding`-ORM-Instanz.

    Die Deutung wird als eigenes, benanntes Objekt verschachtelt statt als flache
    Felder — das hält die Trennung „Zahlen vs. Interpretation" auch in der
    JSON-Struktur der Antwort sichtbar.

    Args:
        finding: Die ORM-Instanz aus dem Repository.

    Returns:
        Das serialisierbare Ausgabe-Schema.
    """
    return TestSetRunFindingOut(
        id=finding.id,
        testset_run_id=finding.testset_run_id,
        iteration_id=finding.iteration_id,
        concept_id=finding.concept_id,
        testset_id=finding.testset_id,
        indicator_config_id=finding.indicator_config_id,
        spec_runner_version=finding.spec_runner_version,
        created_at=finding.created_at,
        goal_snapshot_json=finding.goal_snapshot_json,
        goal_missing_reason=finding.goal_missing_reason,
        best_criteria_json=finding.best_criteria_json,
        planned_n_runs=finding.planned_n_runs,
        planned_combos_per_run=finding.planned_combos_per_run,
        planned_combos_total=finding.planned_combos_total,
        planned_grid_reason=finding.planned_grid_reason,
        scope_json=finding.scope_json,
        candidates_json=finding.candidates_json,
        robustness_json=finding.robustness_json,
        benchmarks_json=finding.benchmarks_json,
        warnings_json=finding.warnings_json,
        holdout_touched=finding.holdout_touched,
        closed_at=finding.closed_at,
        interpretation=InterpretationOut(
            text=finding.interpretation_text,
            interpreted_at=finding.interpretation_at,
        ),
    )


# --- Endpunkte ---

@router.get('/{finding_id}')
def get_finding(finding_id: int):
    """Ein einzelner Befund per ID — der Kontext bleibt lesbar, auch wenn der zugehörige
    TestSetRun längst aufgeräumt wurde (lose Referenz, siehe Modell-Docstring)."""
    session = get_session()
    try:
        finding = get_testset_run_finding(session, finding_id)
        if finding is None:
            raise HTTPException(status_code=404, detail=f'Befund {finding_id} nicht gefunden.')
        return {'data': _finding_to_out(finding).model_dump(mode='json'), 'error': None}
    finally:
        session.close()


@router.get('/by-iteration/{iteration_id}')
def list_findings_for_iteration(iteration_id: int):
    """Befund-Historie einer Iteration — chronologisch, ohne Sortier- oder Filteroption."""
    session = get_session()
    try:
        findings = list_testset_run_findings_for_iteration(session, iteration_id)
        items = [_finding_to_out(f).model_dump(mode='json') for f in findings]
        return {'data': {'items': items, 'total': len(items)}, 'error': None}
    finally:
        session.close()


@router.get('/by-concept/{concept_id}')
def list_findings_for_concept(concept_id: int):
    """Befund-Historie eines Konzepts — chronologisch, ohne Sortier-
    oder Filteroption. Befunde überleben einen gelöschten TestSetRun (lose
    Referenz) und erscheinen weiterhin; ein Konzept ohne Befunde liefert eine
    leere Liste statt eines Fehlers."""
    session = get_session()
    try:
        findings = list_testset_run_findings_for_concept(session, concept_id)
        items = [_finding_to_out(f).model_dump(mode='json') for f in findings]
        return {'data': {'items': items, 'total': len(items)}, 'error': None}
    finally:
        session.close()


@router.get('/by-testset-run/{testset_run_id}')
def get_finding_for_testset_run_route(testset_run_id: int):
    """Jüngster Befund eines Testset-Laufs plus Gesamtzahl.

    `testset-run-start` gibt die Testset-Lauf-Nummer zurück, nicht die Befund-ID —
    dieser Endpunkt löst das serverseitig auf, statt den Umweg über
    `by-iteration` + Ablesen der Befund-Nummer zu erzwingen. Bei einem Rerun
    existieren mehrere Befunde je Testset-Lauf; `total_for_testset_run` macht
    diese Historie sichtbar, auch wenn nur der jüngste geliefert wird.
    """
    session = get_session()
    try:
        finding = get_finding_for_testset_run(session, testset_run_id)
        if finding is None:
            raise HTTPException(
                status_code=404,
                detail=f'Kein Befund für Testset-Lauf {testset_run_id} gefunden.',
            )
        total = count_testset_run_findings_for_testset_run(session, testset_run_id)
        return {
            'data': {
                'finding': _finding_to_out(finding).model_dump(mode='json'),
                'total_for_testset_run': total,
            },
            'error': None,
        }
    finally:
        session.close()


@router.patch('/{finding_id}/interpretation')
def set_finding_interpretation_route(finding_id: int, payload: InterpretationIn):
    """Trägt die Deutung nachträglich ein — reiner Freitext, die Zahlen bleiben unberührt."""
    session = get_session()
    try:
        finding = get_testset_run_finding(session, finding_id)
        if finding is None:
            raise HTTPException(status_code=404, detail=f'Befund {finding_id} nicht gefunden.')
        finding = set_finding_interpretation(session, finding, payload.text)
        return {'data': _finding_to_out(finding).model_dump(mode='json'), 'error': None}
    finally:
        session.close()
