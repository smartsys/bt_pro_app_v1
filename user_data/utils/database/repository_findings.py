"""Repository-Funktionen für den Befund je Testset-Lauf.

Der Befund entsteht in zwei Phasen, und beide sind hier abgebildet:

* **Phase 1** — Anlage beim Start mit Kontext und Soll. Ab der Anlage sind diese
  Felder unveränderlich.
* **Phase 2** — Abschluss nach dem Lauf: die Ist-Werte werden **einmal** ergänzt und
  der Befund wird geschlossen. Ein zweiter Ist-Schreibvorgang wird abgewiesen.

Beide Sperren sind durchgesetzt vom ORM-Wächter an
:class:`~user_data.utils.database.models.TestSetRunFinding`, nicht durch eine
Konvention in diesem Docstring.

Die Soll-Werte stammen ausschließlich aus dem Konzept
(``strategy_concepts.goal_json``) und werden als Schnappschuss kopiert. Es gibt
bewusst **keine** manuelle Soll-Eingabe beim Start: genau die wäre der
Drift-Kanal, den der Befund schließen soll.
"""

import copy
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from user_data.utils.database.models import FindingImmutableError, TestSetRunFinding

logger = logging.getLogger(__name__)

# Grund, der hinterlegt wird, wenn das Konzept kein Entwicklungsziel trägt.
# Kein Fehler und kein Gate — der Lauf startet trotzdem.
GOAL_MISSING_REASON = 'kein Ziel am Konzept hinterlegt'


def create_testset_run_finding(
    session: Session,
    testset_run_id: int,
    iteration_id: int,
    concept_id: Optional[int],
    testset_id: int,
    indicator_config_id: Optional[int],
    spec_runner_version: Optional[str],
    goal_snapshot: Optional[Dict[str, Any]],
    best_criteria: List[str],
    planned_n_runs: int,
    planned_combos_per_run: Optional[int],
    planned_grid_reason: Optional[str] = None,
) -> TestSetRunFinding:
    """Legt den Befund eines Testset-Laufs an (Phase 1: Kontext + Soll).

    Der Ziel-Schnappschuss wird tief kopiert, damit eine spätere Änderung von
    ``concept.goal_json`` bestehende Befunde nicht mehr berührt. Fehlt das Ziel,
    bleibt ``goal_snapshot_json`` NULL und ``goal_missing_reason`` trägt den Grund.

    Args:
        session: Aktive SQLAlchemy-Session.
        testset_run_id: Lose Referenz auf testset_runs.id (kein FK).
        iteration_id: Iteration, für die der Lauf gestartet wurde.
        concept_id: Konzept der Iteration — Herkunft des Ziel-Schnappschusses.
        testset_id: Testset, über das gelaufen wird.
        indicator_config_id: Verwendete Indikator-Konfiguration.
        spec_runner_version: Version des Spec-Runners zum Startzeitpunkt.
        goal_snapshot: Inhalt von ``concept.goal_json`` oder None.
        best_criteria: Stabile Keys der Bestwert-Kriterien.
        planned_n_runs: Anzahl der geplanten Backtest-Runs (BacktestConfigs im Testset).
        planned_combos_per_run: Kombinationen je Run oder None, wenn nicht zählbar.
        planned_grid_reason: Grund, wenn die Rastergröße nicht ermittelt werden konnte.

    Returns:
        Der neu angelegte Befund.
    """
    goal_copy = copy.deepcopy(goal_snapshot) if goal_snapshot else None
    combos_total = (
        planned_combos_per_run * planned_n_runs
        if planned_combos_per_run is not None
        else None
    )

    finding = TestSetRunFinding(
        testset_run_id=testset_run_id,
        iteration_id=iteration_id,
        concept_id=concept_id,
        testset_id=testset_id,
        indicator_config_id=indicator_config_id,
        spec_runner_version=spec_runner_version,
        goal_snapshot_json=goal_copy,
        goal_missing_reason=None if goal_copy else GOAL_MISSING_REASON,
        best_criteria_json=list(best_criteria),
        planned_n_runs=planned_n_runs,
        planned_combos_per_run=planned_combos_per_run,
        planned_combos_total=combos_total,
        planned_grid_reason=planned_grid_reason,
    )
    session.add(finding)
    session.commit()
    session.refresh(finding)
    logger.info(
        '[BEFUND] Befund %d angelegt (TestSetRun %d, Iteration %d, Testset %d, Soll: %s).',
        finding.id, testset_run_id, iteration_id, testset_id,
        'vorhanden' if goal_copy else GOAL_MISSING_REASON,
    )
    return finding


def get_testset_run_finding(
    session: Session, finding_id: int,
) -> Optional[TestSetRunFinding]:
    """Gibt einen einzelnen Befund zurück oder None.

    Args:
        session: Aktive SQLAlchemy-Session.
        finding_id: Primärschlüssel des Befunds.

    Returns:
        Der Befund oder None.
    """
    return (
        session.query(TestSetRunFinding)
        .filter(TestSetRunFinding.id == finding_id)
        .first()
    )


def get_finding_for_testset_run(
    session: Session, testset_run_id: int,
) -> Optional[TestSetRunFinding]:
    """Gibt den jüngsten Befund eines Testset-Laufs zurück oder None.

    Ein erneuter Lauf erzeugt einen neuen Testset-Lauf und damit einen neuen Befund;
    mehrere Befunde am selben Testset-Lauf sind deshalb nicht vorgesehen. Sollte es
    sie doch geben, gewinnt der jüngste — und ein bereits geschlossener wird dabei
    nicht übersprungen, damit ein zweiter Abschluss sichtbar auflaufen kann statt
    still einen älteren Befund zu treffen.

    Args:
        session: Aktive SQLAlchemy-Session.
        testset_run_id: Lose Referenz auf testset_runs.id.

    Returns:
        Der jüngste Befund oder None.
    """
    return (
        session.query(TestSetRunFinding)
        .filter(TestSetRunFinding.testset_run_id == testset_run_id)
        .order_by(TestSetRunFinding.id.desc())
        .first()
    )


def count_testset_run_findings_for_testset_run(
    session: Session, testset_run_id: int,
) -> int:
    """Gibt die Gesamtzahl der Befunde eines Testset-Laufs zurück.

    Bei einem Rerun existieren mehrere Befunde je Testset-Lauf; die Zahl macht
    diese Historie sichtbar, wenn nur der jüngste Befund (siehe
    `get_finding_for_testset_run`) ausgegeben wird.

    Args:
        session: Aktive SQLAlchemy-Session.
        testset_run_id: Lose Referenz auf testset_runs.id.

    Returns:
        Anzahl der Befunde dieses Testset-Laufs.
    """
    return (
        session.query(TestSetRunFinding)
        .filter(TestSetRunFinding.testset_run_id == testset_run_id)
        .count()
    )


def list_testset_run_findings_for_iteration(
    session: Session, iteration_id: int,
) -> List[TestSetRunFinding]:
    """Gibt die Befund-Historie einer Iteration chronologisch zurück.

    Bewusst keine Sortier- oder Filteroption (Anforderung 7): chronologisch nach
    Anlage ist die einzige Reihenfolge, sonst entstünde eine Einladung, „nach
    Güte" zu sortieren.

    Args:
        session: Aktive SQLAlchemy-Session.
        iteration_id: Iteration, deren Befunde gesucht werden.

    Returns:
        Alle Befunde der Iteration, älteste zuerst.
    """
    return (
        session.query(TestSetRunFinding)
        .filter(TestSetRunFinding.iteration_id == iteration_id)
        .order_by(TestSetRunFinding.id.asc())
        .all()
    )


def list_testset_run_findings_for_concept(
    session: Session, concept_id: int,
) -> List[TestSetRunFinding]:
    """Gibt die Befund-Historie eines Konzepts chronologisch zurück.

    Bewusst keine Sortier- oder Filteroption (dieselbe Regel wie bei
    `list_testset_run_findings_for_iteration`): chronologisch nach Anlage ist
    die einzige Reihenfolge. Sortiert wird nach `created_at` mit `id` als
    stabilem Tiebreaker (gleiche Sekunde möglich).

    Args:
        session: Aktive SQLAlchemy-Session.
        concept_id: Konzept, dessen Befunde gesucht werden.

    Returns:
        Alle Befunde des Konzepts, älteste zuerst.
    """
    return (
        session.query(TestSetRunFinding)
        .filter(TestSetRunFinding.concept_id == concept_id)
        .order_by(TestSetRunFinding.created_at.asc(), TestSetRunFinding.id.asc())
        .all()
    )


def set_finding_interpretation(
    session: Session, finding: TestSetRunFinding, text: str,
) -> TestSetRunFinding:
    """Ergänzt die Deutung nachträglich — getrennt von den Zahlen.

    Die Deutung ist in beiden Phasen schreibbar (siehe Docstring von
    ``TestSetRunFinding``); sie berührt keine der Phase-1/Phase-2-Spalten.

    Args:
        session: Aktive SQLAlchemy-Session.
        finding: Der Befund, an dem die Deutung ergänzt wird.
        text: Freitext der Deutung.

    Returns:
        Der Befund mit gesetzter Deutung.
    """
    finding.interpretation_text = text
    finding.interpretation_at = datetime.now()
    session.commit()
    session.refresh(finding)
    logger.info('[BEFUND] Deutung an Befund %d ergänzt.', finding.id)
    return finding


def close_testset_run_finding(
    session: Session,
    finding: TestSetRunFinding,
    scope: Dict[str, Any],
    candidates: Dict[str, Any],
    robustness: Dict[str, Any],
    benchmarks: Dict[str, Any],
    warnings: Dict[str, Any],
) -> TestSetRunFinding:
    """Schreibt die Ist-Werte und schließt den Befund (Phase 2, genau einmal).

    ``holdout_touched`` bleibt bewusst NULL: es gibt keinen markierten
    Holdout-Zeitraum (Out of Scope). ``False`` wäre eine Aussage, die
    niemand geprüft hat — der Grund steht in ``warnings['not_evaluated']``.

    Args:
        session: Aktive SQLAlchemy-Session.
        finding: Der offene Befund aus Phase 1.
        scope: Gruppe „Umfang der Suche".
        candidates: Gruppe „Kandidaten".
        robustness: Gruppe „Robustheit".
        benchmarks: Gruppe „Vergleichsanker".
        warnings: Gruppe „Warnhinweise".

    Returns:
        Der geschlossene Befund.

    Raises:
        FindingImmutableError: Wenn der Befund bereits geschlossen ist. Der Versuch
            wird abgewiesen und nicht still überschrieben; ein erneuter Lauf erzeugt
            einen neuen Befund.
    """
    if finding.closed_at is not None:
        raise FindingImmutableError(
            f'Befund {finding.id}: bereits am {finding.closed_at} geschlossen. '
            f'Die Ist-Werte werden genau einmal geschrieben — ein erneuter Lauf '
            f'erzeugt einen neuen Befund.'
        )

    finding.scope_json = scope
    finding.candidates_json = candidates
    finding.robustness_json = robustness
    finding.benchmarks_json = benchmarks
    finding.warnings_json = warnings
    finding.closed_at = datetime.now()
    session.commit()
    session.refresh(finding)
    logger.info(
        '[BEFUND] Befund %d geschlossen (TestSetRun %s, %s Läufe).',
        finding.id, finding.testset_run_id, scope.get('n_runs'),
    )
    return finding
