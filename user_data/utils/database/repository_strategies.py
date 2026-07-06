"""Repository-Funktionen für StrategyConcept und StrategyIteration.

CRUD-Operationen sowie Lookup-Helper für die zweistufige Strategie-Schicht.
Ticket 09: strategy_concepts + strategy_iterations Tabellen.
"""

from typing import Dict, List, Optional

from sqlalchemy import text, update
from sqlalchemy.orm import Session

from user_data.utils.database.models import (
    BacktestResult,
    BacktestRun,
    StrategyConcept,
    StrategyIteration,
)


# ============================================================================
# Concept CRUD
# ============================================================================

def list_concepts(session: Session) -> List[StrategyConcept]:
    """Alle Strategie-Konzepte auflisten.

    Args:
        session: SQLAlchemy-Session.

    Returns:
        Liste aller StrategyConcept-Einträge.
    """
    return session.query(StrategyConcept).order_by(StrategyConcept.id).all()


def get_concept(session: Session, concept_id: int) -> Optional[StrategyConcept]:
    """Einzelnes Konzept per ID laden.

    Args:
        session: SQLAlchemy-Session.
        concept_id: Primärschlüssel des Konzepts.

    Returns:
        StrategyConcept oder None wenn nicht gefunden.
    """
    return session.query(StrategyConcept).filter(StrategyConcept.id == concept_id).first()


def get_concept_by_slug(session: Session, slug: str) -> Optional[StrategyConcept]:
    """Konzept per Slug laden.

    Args:
        session: SQLAlchemy-Session.
        slug: Eindeutiger Slug des Konzepts (z.B. 'teststrategie').

    Returns:
        StrategyConcept oder None wenn nicht gefunden.
    """
    return session.query(StrategyConcept).filter(StrategyConcept.slug == slug).first()


def create_concept(session: Session, **kwargs) -> StrategyConcept:
    """Neues Strategie-Konzept anlegen.

    Args:
        session: SQLAlchemy-Session.
        **kwargs: Felder des Konzepts (slug, name, category, description, etc.).

    Returns:
        Das neu erstellte StrategyConcept.
    """
    concept = StrategyConcept(**kwargs)
    session.add(concept)
    session.commit()
    session.refresh(concept)
    return concept


def update_concept(session: Session, concept_id: int, **kwargs) -> Optional[StrategyConcept]:
    """Bestehendes Konzept aktualisieren.

    Args:
        session: SQLAlchemy-Session.
        concept_id: Primärschlüssel des zu aktualisierenden Konzepts.
        **kwargs: Zu aktualisierende Felder.

    Returns:
        Das aktualisierte StrategyConcept oder None wenn nicht gefunden.
    """
    concept = get_concept(session, concept_id)
    if concept is None:
        return None
    for key, value in kwargs.items():
        setattr(concept, key, value)
    session.commit()
    session.refresh(concept)
    return concept


def get_concept_blockers(session: Session, concept_id: int) -> Dict[str, int]:
    """Zählt referenzierende Datensätze, die eine Konzept-Löschung blockieren würden.

    Args:
        session: SQLAlchemy-Session.
        concept_id: Primärschlüssel des Konzepts.

    Returns:
        Dict mit Zählern: iterations, backtest_runs, backtest_results.
        Alle Werte 0 bedeutet: Löschung ohne Cascade möglich.
    """
    iteration_ids = [
        row[0] for row in
        session.query(StrategyIteration.id)
        .filter(StrategyIteration.concept_id == concept_id)
        .all()
    ]
    runs = 0
    results = 0
    if iteration_ids:
        runs = (
            session.query(BacktestRun)
            .filter(BacktestRun.iteration_id.in_(iteration_ids))
            .count()
        )
        results = (
            session.query(BacktestResult)
            .filter(BacktestResult.iteration_id.in_(iteration_ids))
            .count()
        )
    return {
        "iterations": len(iteration_ids),
        "backtest_runs": runs,
        "backtest_results": results,
    }


def delete_concept(session: Session, concept_id: int) -> bool:
    """Konzept aus der DB löschen (nur ohne abhängige Iterationen).

    Args:
        session: SQLAlchemy-Session.
        concept_id: Primärschlüssel des zu löschenden Konzepts.

    Returns:
        True wenn gelöscht, False wenn nicht gefunden.
    """
    concept = get_concept(session, concept_id)
    if concept is None:
        return False
    session.delete(concept)
    session.commit()
    return True


def force_delete_concept(session: Session, concept_id: int) -> bool:
    """Konzept inkl. aller abhängigen Datensätze löschen (Cascade).

    Löscht alle Iterationen des Konzepts sowie alle BacktestRuns und
    BacktestResults, die auf diese Iterationen verweisen. Lose verknüpfte
    IndicatorConfigs (strategy_concept_id, kein FK) bleiben bestehen und
    zeigen danach ins Leere — das ist die gewollte lose Kopplung.

    Args:
        session: SQLAlchemy-Session.
        concept_id: Primärschlüssel des zu löschenden Konzepts.

    Returns:
        True wenn gelöscht, False wenn nicht gefunden.
    """
    if get_concept(session, concept_id) is None:
        return False

    iteration_ids = [
        row[0] for row in
        session.query(StrategyIteration.id)
        .filter(StrategyIteration.concept_id == concept_id)
        .all()
    ]

    if iteration_ids:
        session.query(BacktestResult).filter(
            BacktestResult.iteration_id.in_(iteration_ids)
        ).delete(synchronize_session=False)
        session.query(BacktestRun).filter(
            BacktestRun.iteration_id.in_(iteration_ids)
        ).delete(synchronize_session=False)
        # Selbstreferenzen aufheben, damit DELETE ohne Reihenfolge-Problem funktioniert
        session.query(StrategyIteration).filter(
            StrategyIteration.parent_iteration_id.in_(iteration_ids)
        ).update({StrategyIteration.parent_iteration_id: None}, synchronize_session=False)
        session.query(StrategyIteration).filter(
            StrategyIteration.id.in_(iteration_ids)
        ).delete(synchronize_session=False)

    concept = get_concept(session, concept_id)
    session.delete(concept)
    session.commit()
    return True


# ============================================================================
# Iteration CRUD
# ============================================================================

def list_iterations(
    session: Session,
    concept_id: Optional[int] = None,
) -> List[StrategyIteration]:
    """Iterationen auflisten, optional gefiltert nach Konzept.

    Args:
        session: SQLAlchemy-Session.
        concept_id: Optionaler Filter auf concept_id.

    Returns:
        Liste der StrategyIteration-Einträge.
    """
    query = session.query(StrategyIteration)
    if concept_id is not None:
        query = query.filter(StrategyIteration.concept_id == concept_id)
    return query.order_by(StrategyIteration.concept_id, StrategyIteration.id).all()


def get_iteration(session: Session, iteration_id: int) -> Optional[StrategyIteration]:
    """Einzelne Iteration per ID laden.

    Args:
        session: SQLAlchemy-Session.
        iteration_id: Primärschlüssel der Iteration.

    Returns:
        StrategyIteration oder None wenn nicht gefunden.
    """
    return session.query(StrategyIteration).filter(StrategyIteration.id == iteration_id).first()


def next_iteration_version(session: Session, concept_id: int) -> int:
    """Nächste fortlaufende Iterations-Nummer für ein Konzept vergeben.

    Zählt den High-Water-Mark `strategy_concepts.iteration_counter` atomar hoch
    und gibt den neuen Wert zurück. Der Zähler sinkt nie — gelöschte Nummern
    werden nicht wiederverwendet. Beginnt bei 1 (Zähler-Startwert 0).

    Args:
        session: SQLAlchemy-Session.
        concept_id: ID des Strategie-Konzepts.

    Returns:
        Die neu vergebene Versionsnummer (>= 1).

    Raises:
        ValueError: Wenn das Konzept nicht existiert.
    """
    row = session.execute(
        update(StrategyConcept)
        .where(StrategyConcept.id == concept_id)
        .values(iteration_counter=StrategyConcept.iteration_counter + 1)
        .returning(StrategyConcept.iteration_counter)
    ).first()
    if row is None:
        raise ValueError(f"Konzept {concept_id} nicht gefunden.")
    session.commit()
    return int(row[0])


def _clamp_negative_shifts(spec_json: Optional[dict]) -> None:
    """Klemmt negative lhs_shift/rhs_shift in den Rules auf 0 (in-place).

    Ein negativer Shift ist nicht-kausaler Lookahead — er zöge den Wert der
    Folgekerze auf die aktuelle Kerze. Beim Speichern einer Iteration wird er
    still auf 0 gesetzt, damit der User es beim Neuladen der Iteration direkt
    sieht. Zentraler Choke-Point: alle Schreibwege (create/update/copy/import,
    inkl. der ds-strategie-session-Toolbox über die API) laufen durch
    create_iteration/update_iteration. Die Rules-Engine wirft zusätzlich zur
    Laufzeit einen ValueError als Backstop (falls ein Spec je an der API vorbei
    entsteht, z.B. im Offline-Harness).

    Args:
        spec_json: Das spec_json der Iteration (wird in-place verändert). None
            oder fehlende Rules sind No-op.
    """
    if not isinstance(spec_json, dict):
        return
    rules = spec_json.get('rules')
    if not isinstance(rules, dict):
        return
    for side in ('entry', 'exit'):
        group = rules.get(side)
        if not isinstance(group, dict):
            continue
        for block in (group.get('blocks') or []):
            if not isinstance(block, dict):
                continue
            for cond in (block.get('conditions') or []):
                if not isinstance(cond, dict):
                    continue
                for key in ('lhs_shift', 'rhs_shift'):
                    val = cond.get(key)
                    if isinstance(val, (int, float)) and not isinstance(val, bool) and val < 0:
                        cond[key] = 0


def create_iteration(session: Session, **kwargs) -> StrategyIteration:
    """Neue Strategie-Iteration anlegen.

    Args:
        session: SQLAlchemy-Session.
        **kwargs: Felder der Iteration (concept_id, version, spec_json, etc.).

    Returns:
        Die neu erstellte StrategyIteration.
    """
    # GEÄNDERT: Audit 2026-07-06 Befund 3 — negative Shifts beim Speichern klemmen
    _clamp_negative_shifts(kwargs.get('spec_json'))
    iteration = StrategyIteration(**kwargs)
    session.add(iteration)
    session.commit()
    session.refresh(iteration)
    return iteration


def update_iteration(session: Session, iteration_id: int, **kwargs) -> Optional[StrategyIteration]:
    """Bestehende Iteration aktualisieren.

    Args:
        session: SQLAlchemy-Session.
        iteration_id: Primärschlüssel der zu aktualisierenden Iteration.
        **kwargs: Zu aktualisierende Felder.

    Returns:
        Die aktualisierte StrategyIteration oder None wenn nicht gefunden.
    """
    iteration = get_iteration(session, iteration_id)
    if iteration is None:
        return None
    # GEÄNDERT: Audit 2026-07-06 Befund 3 — negative Shifts beim Speichern klemmen
    _clamp_negative_shifts(kwargs.get('spec_json'))
    for key, value in kwargs.items():
        setattr(iteration, key, value)
    session.commit()
    session.refresh(iteration)
    return iteration


def delete_iteration(session: Session, iteration_id: int) -> bool:
    """Iteration aus der DB löschen.

    Args:
        session: SQLAlchemy-Session.
        iteration_id: Primärschlüssel der zu löschenden Iteration.

    Returns:
        True wenn gelöscht, False wenn nicht gefunden.
    """
    iteration = get_iteration(session, iteration_id)
    if iteration is None:
        return False
    session.delete(iteration)
    session.commit()
    return True


def _collect_subtree_ids(session: Session, root_id: int) -> List[int]:
    """Alle Iterations-IDs im Teilbaum unterhalb root_id (inkl. root) sammeln."""
    ids: List[int] = []
    queue = [root_id]
    while queue:
        current = queue.pop()
        ids.append(current)
        children = (
            session.query(StrategyIteration.id)
            .filter(StrategyIteration.parent_iteration_id == current)
            .all()
        )
        queue.extend(row[0] for row in children)
    return ids


def get_iteration_blockers(session: Session, iteration_id: int) -> Dict[str, int]:
    """Zählt alle referenzierenden Datensätze, die eine Löschung blockieren würden.

    Args:
        session: SQLAlchemy-Session.
        iteration_id: Primärschlüssel der Iteration.

    Returns:
        Dict mit Zählern: child_iterations, backtest_runs, backtest_results.
        Alle Werte 0 bedeutet: Löschung ohne Cascade möglich.
    """
    children = (
        session.query(StrategyIteration)
        .filter(StrategyIteration.parent_iteration_id == iteration_id)
        .count()
    )
    runs = (
        session.query(BacktestRun)
        .filter(BacktestRun.iteration_id == iteration_id)
        .count()
    )
    results = (
        session.query(BacktestResult)
        .filter(BacktestResult.iteration_id == iteration_id)
        .count()
    )
    return {
        "child_iterations": children,
        "backtest_runs": runs,
        "backtest_results": results,
    }


def force_delete_iteration(session: Session, iteration_id: int) -> bool:
    """Iteration inkl. aller abhängigen Datensätze löschen (Cascade).

    Löscht rekursiv alle Child-Iterationen sowie alle BacktestRuns und
    BacktestResults, die auf die Iteration (oder ihre Kinder) verweisen.

    Args:
        session: SQLAlchemy-Session.
        iteration_id: Primärschlüssel der zu löschenden Iteration.

    Returns:
        True wenn gelöscht, False wenn nicht gefunden.
    """
    if get_iteration(session, iteration_id) is None:
        return False

    all_ids = _collect_subtree_ids(session, iteration_id)

    # BacktestResults und BacktestRuns aller betroffenen Iterationen entfernen
    session.query(BacktestResult).filter(
        BacktestResult.iteration_id.in_(all_ids)
    ).delete(synchronize_session=False)
    session.query(BacktestRun).filter(
        BacktestRun.iteration_id.in_(all_ids)
    ).delete(synchronize_session=False)

    # Selbstreferenzen aufheben, damit DELETE ohne Reihenfolge-Problem funktioniert
    session.query(StrategyIteration).filter(
        StrategyIteration.parent_iteration_id.in_(all_ids)
    ).update({StrategyIteration.parent_iteration_id: None}, synchronize_session=False)

    session.query(StrategyIteration).filter(
        StrategyIteration.id.in_(all_ids)
    ).delete(synchronize_session=False)

    session.commit()
    return True
