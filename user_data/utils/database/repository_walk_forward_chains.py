"""Repository-Funktionen der Walk-Forward-Fold-Kette.

Der Datensatz entsteht beim Start mit dem vollständigen Plan (Vorregistrierung),
wächst danach ausschließlich um angehängte Fold-Blöcke und wird genau einmal
abgeschlossen — mit Aggregat (``completed``) oder mit Fehlermeldung (``failed``).
Danach ist er unveränderlich; durchgesetzt wird das von den ORM-Wächtern an
:class:`~user_data.utils.database.models.WalkForwardChain`, nicht von einer
Konvention in diesem Docstring.

Es gibt bewusst **keine** Update- und keine Delete-Funktion: eine neue Kette
erzeugt einen neuen Datensatz. Und **keine** Güte-Sortierung — die Historie ist
ausnahmslos chronologisch, damit aus dem Bericht keine Bestenliste wird.
"""

import copy
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from user_data.utils.database.models import (
    WALK_FORWARD_CHAIN_TERMINAL_STATUS,
    WalkForwardChain,
)

logger = logging.getLogger(__name__)


class WalkForwardPlanMismatchError(Exception):
    """Ein Fold-Block weicht vom vorregistrierten Plan ab.

    Eigener Fehlertyp, damit die API ihn als sauberen 400er meldet — abgewiesen
    wird, nicht stillschweigend zurechtgebogen.
    """


def _planned_fold(plan: Dict[str, Any], fold_index: int) -> Dict[str, Any]:
    """Sucht den geplanten Fold-Block zu einem Index.

    Args:
        plan: Das ``plan_json`` der Kette.
        fold_index: 1-basierter Fold-Index.

    Returns:
        Der geplante Fold-Block.

    Raises:
        WalkForwardPlanMismatchError: Wenn der Index nicht im Plan steht.
    """
    for fold in (plan or {}).get('folds') or []:
        if fold.get('fold_index') == fold_index:
            return fold
    raise WalkForwardPlanMismatchError(
        f'Fold {fold_index} steht nicht im Plan (geplant sind '
        f'{(plan or {}).get("n_folds")} Folds).'
    )


def _assert_window_matches(
    label: str, fold_index: int, planned: Dict[str, Any], submitted: Dict[str, Any],
) -> None:
    """Prüft ein übergebenes Fenster gegen das geplante.

    Args:
        label: Bezeichnung des Fensters für die Fehlermeldung ('IS' oder 'OOS').
        fold_index: 1-basierter Fold-Index.
        planned: Geplantes Fenster aus dem Plan.
        submitted: Übergebenes Fenster aus dem Fold-Block.

    Raises:
        WalkForwardPlanMismatchError: Bei abweichenden Grenzen.
    """
    for bound in ('start', 'end'):
        if (submitted or {}).get(bound) != (planned or {}).get(bound):
            raise WalkForwardPlanMismatchError(
                f'Fold {fold_index}: {label}-Fenster weicht vom Plan ab — geplant '
                f'{planned.get("start")}..{planned.get("end")}, übergeben '
                f'{(submitted or {}).get("start")}..{(submitted or {}).get("end")}.'
            )


def create_walk_forward_chain(
    session: Session,
    anchor_run_id: int,
    plan: Dict[str, Any],
    iteration_id: Optional[int] = None,
    concept_id: Optional[int] = None,
    config_snapshot: Optional[Dict[str, Any]] = None,
    method_note: Optional[str] = None,
) -> WalkForwardChain:
    """Legt eine Kette mit vollständigem Plan an (Status 'running').

    Plan und Kontext werden tief kopiert: eine spätere Änderung am Anker-Lauf darf
    eine bereits angelegte Kette nicht mehr berühren.

    Args:
        session: Aktive SQLAlchemy-Session.
        anchor_run_id: Lose Referenz auf backtest_runs.id des Anker-Laufs.
        plan: Vollständiger Fold-Plan (Vorregistrierung).
        iteration_id: Lose Referenz auf strategy_iterations.id.
        concept_id: Lose Referenz auf strategy_concepts.id.
        config_snapshot: Symbol, Exchange, Timeframe, Portfolio-Kern, Anker-Fenster.
        method_note: Fester Methodenhinweis zur Verkettung.

    Returns:
        Die neu angelegte Kette.

    Raises:
        ValueError: Wenn der Plan keine Fold-Fenster enthält.
    """
    if not (plan or {}).get('folds'):
        raise ValueError('Der Plan enthält keine Fold-Fenster.')

    chain = WalkForwardChain(
        anchor_run_id=anchor_run_id,
        iteration_id=iteration_id,
        concept_id=concept_id,
        config_snapshot_json=copy.deepcopy(config_snapshot) if config_snapshot else None,
        plan_json=copy.deepcopy(plan),
        folds_json=[],
        method_note=method_note,
        status='running',
    )
    session.add(chain)
    session.commit()
    session.refresh(chain)
    logger.info(
        '[WF-KETTE] Kette %d angelegt (Anker-Run %d, %d Folds, Kriterium %s %s, '
        'Trade-Floor %s).',
        chain.id, anchor_run_id, plan.get('n_folds'), plan.get('selection_direction'),
        plan.get('selection_metric'), plan.get('trade_floor'),
    )
    return chain


def get_walk_forward_chain(session: Session, chain_id: int) -> Optional[WalkForwardChain]:
    """Gibt eine einzelne Kette zurück oder None.

    Args:
        session: Aktive SQLAlchemy-Session.
        chain_id: Primärschlüssel der Kette.

    Returns:
        Die Kette oder None.
    """
    return (
        session.query(WalkForwardChain)
        .filter(WalkForwardChain.id == chain_id)
        .first()
    )


def list_walk_forward_chains(
    session: Session, iteration_id: Optional[int] = None,
) -> List[WalkForwardChain]:
    """Historie der Ketten — chronologisch, ohne Güte-Sortierung.

    Args:
        session: Aktive SQLAlchemy-Session.
        iteration_id: Optionale Einschränkung auf eine Iteration.

    Returns:
        Liste der Ketten, älteste zuerst.
    """
    query = session.query(WalkForwardChain)
    if iteration_id is not None:
        query = query.filter(WalkForwardChain.iteration_id == iteration_id)
    return query.order_by(
        WalkForwardChain.created_at.asc(), WalkForwardChain.id.asc(),
    ).all()


def append_walk_forward_fold(
    session: Session, chain_id: int, fold: Dict[str, Any],
) -> WalkForwardChain:
    """Hängt einen abgeschlossenen Fold-Block an eine laufende Kette an.

    Geprüft wird gegen den vorregistrierten Plan: der Index muss der nächste sein,
    die Fenster müssen exakt den geplanten entsprechen. Ein Fold ohne Sieger ist
    zulässig und wird als solcher gespeichert — nicht verschluckt.

    Args:
        session: Aktive SQLAlchemy-Session.
        chain_id: Primärschlüssel der Kette.
        fold: Fold-Block mit fold_index, is_window, optional oos_window, winner,
            Run-/Result-IDs und OOS-Kennzahlen.

    Returns:
        Die aktualisierte Kette.

    Raises:
        ValueError: Wenn die Kette nicht existiert oder bereits abgeschlossen ist.
        WalkForwardPlanMismatchError: Bei Abweichung vom Plan.
    """
    chain = get_walk_forward_chain(session, chain_id)
    if chain is None:
        raise ValueError(f'Walk-Forward-Kette {chain_id} nicht gefunden.')
    if chain.status in WALK_FORWARD_CHAIN_TERMINAL_STATUS:
        raise ValueError(
            f'Walk-Forward-Kette {chain_id} ist mit Status "{chain.status}" '
            f'abgeschlossen — es können keine Folds mehr angehängt werden.'
        )

    existing = list(chain.folds_json or [])
    fold_index = fold.get('fold_index')
    expected_index = len(existing) + 1
    if fold_index != expected_index:
        raise WalkForwardPlanMismatchError(
            f'Fold-Index {fold_index} passt nicht: erwartet wird Fold '
            f'{expected_index} ({len(existing)} bereits angehängt).'
        )

    planned = _planned_fold(chain.plan_json or {}, fold_index)
    _assert_window_matches('IS', fold_index, planned.get('is_window') or {}, fold.get('is_window') or {})
    if fold.get('oos_result_id') or fold.get('oos_run_id') or fold.get('oos_window'):
        _assert_window_matches(
            'OOS', fold_index, planned.get('oos_window') or {}, fold.get('oos_window') or {},
        )

    chain.folds_json = existing + [copy.deepcopy(fold)]
    session.commit()
    session.refresh(chain)
    logger.info(
        '[WF-KETTE] Kette %d: Fold %d angehängt (Sieger %s, OOS-Result %s).',
        chain.id, fold_index,
        'ja' if fold.get('winner') else 'nein', fold.get('oos_result_id'),
    )
    return chain


def complete_walk_forward_chain(
    session: Session, chain_id: int, aggregate: Dict[str, Any],
) -> WalkForwardChain:
    """Schließt eine Kette mit Aggregat ab (Status 'completed').

    Aggregat und Endstatus werden in **einem** Flush geschrieben: für diesen
    Schreibvorgang war die Kette noch offen, der Wächter greift also noch nicht.
    Jeder weitere Versuch trifft den Endzustand und läuft auf.

    Args:
        session: Aktive SQLAlchemy-Session.
        chain_id: Primärschlüssel der Kette.
        aggregate: Die serverseitig gerechnete Gesamtbewertung.

    Returns:
        Die abgeschlossene Kette.

    Raises:
        ValueError: Wenn die Kette nicht existiert.
        WalkForwardChainImmutableError: Wenn die Kette bereits abgeschlossen war.
    """
    chain = get_walk_forward_chain(session, chain_id)
    if chain is None:
        raise ValueError(f'Walk-Forward-Kette {chain_id} nicht gefunden.')
    chain.aggregate_json = aggregate
    chain.error_message = None
    chain.status = 'completed'
    chain.completed_at = datetime.now()
    session.commit()
    session.refresh(chain)
    logger.info(
        '[WF-KETTE] Kette %d abgeschlossen (%d Folds, %d mit Sieger).',
        chain.id, len(chain.folds_json or []),
        (aggregate or {}).get('folds_with_winner', 0),
    )
    return chain


def fail_walk_forward_chain(
    session: Session,
    chain_id: int,
    error_message: str,
    aggregate: Optional[Dict[str, Any]] = None,
) -> WalkForwardChain:
    """Schließt eine Kette mit sichtbarer Fehlermeldung ab (Status 'failed').

    Der Fehler wird als Endzustand festgeschrieben, nicht geschluckt: eine
    abgebrochene Kette ist ein Ergebnis, das lesbar bleiben muss. Bereits
    angehängte Folds bleiben erhalten.

    Args:
        session: Aktive SQLAlchemy-Session.
        chain_id: Primärschlüssel der Kette.
        error_message: Klartext des Abbruchgrunds.
        aggregate: Optionales Teil-Aggregat über die bereits gelaufenen Folds.

    Returns:
        Die abgebrochene Kette.

    Raises:
        ValueError: Wenn die Kette nicht existiert.
        WalkForwardChainImmutableError: Wenn die Kette bereits abgeschlossen war.
    """
    chain = get_walk_forward_chain(session, chain_id)
    if chain is None:
        raise ValueError(f'Walk-Forward-Kette {chain_id} nicht gefunden.')
    if aggregate is not None:
        chain.aggregate_json = aggregate
    chain.error_message = str(error_message)[:4000]
    chain.status = 'failed'
    chain.completed_at = datetime.now()
    session.commit()
    session.refresh(chain)
    logger.error(
        '[WF-KETTE] Kette %d abgebrochen: %s', chain.id, chain.error_message,
    )
    return chain


def walk_forward_chain_to_dict(chain: WalkForwardChain) -> Dict[str, Any]:
    """Serialisiert eine Kette für die API-Antwort.

    Enthält bewusst **kein** Verdict-Feld: kein ``passed``, kein Score, keine
    Ampel. Das Aggregat steht immer zusammen mit den Fold-Blöcken, aus denen es
    entstanden ist.

    Args:
        chain: Die ORM-Instanz.

    Returns:
        JSON-serialisierbares Dict.
    """
    created_at: Optional[datetime] = chain.created_at
    completed_at: Optional[datetime] = chain.completed_at
    return {
        'id': chain.id,
        'anchor_run_id': chain.anchor_run_id,
        'iteration_id': chain.iteration_id,
        'concept_id': chain.concept_id,
        'config_snapshot_json': chain.config_snapshot_json,
        'plan_json': chain.plan_json,
        'folds_json': chain.folds_json or [],
        'aggregate_json': chain.aggregate_json,
        'method_note': chain.method_note,
        'status': chain.status,
        'error_message': chain.error_message,
        'created_at': created_at.isoformat() if created_at else None,
        'completed_at': completed_at.isoformat() if completed_at else None,
    }
