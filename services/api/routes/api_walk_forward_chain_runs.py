"""Läufe einer Walk-Forward-Fold-Kette (Ticket 82)

POST /api/backtest/walk-forward-chains/{id}/is-run  — Anker-Raster auf dem IS-Fenster
POST /api/backtest/walk-forward-chains/{id}/oos-run — Sieger wählen, OOS-Lauf starten

Beide Läufe entstehen ausschließlich aus **JSON-Kopien** am Anker-Lauf mit
gesetztem Fenster aus dem Plan — es entstehen keine ``backtest_configs``,
``indicator_configs`` oder ``testsets``. Beide setzen ``parent_run_id`` auf den
Anker.

Das Fenster kommt aus dem vorregistrierten Plan und nicht aus dem Request: so
kann der gerechnete Lauf gar nicht erst vom Plan abweichen.
"""

import copy
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.api.utils.walk_forward import set_backtest_window
from services.api.utils.walk_forward_selection import select_fold_winner, winner_block
from services.api.walk_forward_chain_context import (
    enqueue_backtest_run,
    load_anchor_run,
    load_running_chain,
    planned_fold_or_400,
)
from user_data.strategies.generic.spec_runner import VERSION as _spec_runner_version
from user_data.utils.database.db import get_session
from user_data.utils.database.repository import create_backtest_run

logger = logging.getLogger(__name__)

router = APIRouter(tags=['walk-forward-chains'])

CHAIN_BASE = '/api/backtest/walk-forward-chains'


class FoldRunIn(BaseModel):
    """Eingabe zum Starten des IS-Laufs eines Folds."""
    fold_index: int = Field(description='1-basierter Fold-Index aus dem Plan.')


class OosRunIn(BaseModel):
    """Eingabe zur Siegerwahl und zum Start des Testfenster-Laufs."""
    fold_index: int = Field(description='1-basierter Fold-Index aus dem Plan.')
    is_run_id: int = Field(description='Abgeschlossener IS-Lauf, aus dem gewählt wird.')


@router.post(CHAIN_BASE + '/{chain_id}/is-run')
def start_chain_is_run(chain_id: int, payload: FoldRunIn):
    """Rechnet das **Anker-Raster** auf dem geplanten IS-Fenster eines Folds.

    Gegenstück zum Einzelschritt ``/walk-forward``, der nur die Einzelkombination
    verschiebt: hier wandert das ganze Raster
    (``backtest_config_json`` + ``indicators_config_json`` des Ankers als
    JSON-Kopie) auf ein **explizites** Fenster aus dem Plan. Der Indikator-Vorlauf
    bleibt erhalten.

    Fold 1 braucht diesen Aufruf nicht, wenn der Plan ohne eigene IS-Länge
    entstanden ist: dann ist sein IS-Fenster exakt das Anker-Fenster und der
    Anker-Lauf ist der IS-Lauf (kein Doppelrechnen).
    """
    session = get_session()
    try:
        chain = load_running_chain(session, chain_id)
        plan = copy.deepcopy(chain.plan_json or {})
        anchor_run_id = chain.anchor_run_id
        window = planned_fold_or_400(plan, payload.fold_index)['is_window']

        anchor = load_anchor_run(session, anchor_run_id)
        backtest_config = copy.deepcopy(dict(anchor.backtest_config_json or {}))
        indicators_config = copy.deepcopy(dict(anchor.indicators_config_json or {}))
        anchor_iteration_id = anchor.iteration_id
        anchor_backtest_config_id = anchor.backtest_config_id
        anchor_indicator_config_id = anchor.indicator_config_id
    finally:
        session.close()

    backtest_config = set_backtest_window(backtest_config, window['start'], window['end'])
    # Metrik-Stufe aus dem Plan durchsetzen; ohne Angabe gilt der Default 'auto'.
    backtest_config.pop('metrics', None)
    if plan.get('metrics_level') is not None:
        backtest_config['metrics'] = plan['metrics_level']

    run_id = create_backtest_run(
        backtest_config=backtest_config,
        indicators_config=indicators_config,
        parent_run_id=anchor_run_id,
        selection_metric=plan.get('selection_metric'),
        spec_runner_version=_spec_runner_version,
        iteration_id=anchor_iteration_id,
        backtest_config_id=anchor_backtest_config_id,
        indicator_config_id=anchor_indicator_config_id,
    )
    enqueue_backtest_run(run_id)
    logger.info(
        '[WF-KETTE] Kette %d, Fold %d: IS-Lauf %d gestartet (%s..%s).',
        chain_id, payload.fold_index, run_id, window['start'], window['end'],
    )
    return {
        'data': {
            'chain_id': chain_id,
            'fold_index': payload.fold_index,
            'run_id': run_id,
            'window': window,
        },
        'error': None,
    }


@router.post(CHAIN_BASE + '/{chain_id}/oos-run')
def start_chain_oos_run(chain_id: int, payload: OosRunIn):
    """Wählt den Sieger des IS-Laufs und startet den Lauf im Testfenster.

    Die Siegerwahl vollzieht **serverseitig** genau das vorregistrierte Kriterium
    aus dem Plan (Metrik, Richtung, Trade-Floor). Erfüllt kein Kandidat den
    Trade-Floor, ist das ein Ergebnis und kein Fehler: die Antwort trägt
    ``winner: null`` samt Grund, es wird kein Lauf gestartet — der Fold wird
    anschließend als Fold ohne Sieger angehängt.
    """
    session = get_session()
    try:
        chain = load_running_chain(session, chain_id)
        plan = copy.deepcopy(chain.plan_json or {})
        anchor_run_id = chain.anchor_run_id
        window = planned_fold_or_400(plan, payload.fold_index)['oos_window']

        winner, reason = select_fold_winner(
            session=session,
            run_id=payload.is_run_id,
            metric=plan.get('selection_metric'),
            direction=plan.get('selection_direction', 'max'),
            trade_floor=int(plan.get('trade_floor') or 0),
        )
        if winner is None:
            logger.info(
                '[WF-KETTE] Kette %d, Fold %d: kein Sieger — %s',
                chain_id, payload.fold_index, reason,
            )
            return {
                'data': {
                    'chain_id': chain_id,
                    'fold_index': payload.fold_index,
                    'is_run_id': payload.is_run_id,
                    'winner': None,
                    'no_winner_reason': reason,
                    'oos_run_id': None,
                    'oos_window': window,
                },
                'error': None,
            }

        if not winner.resolved_config_json:
            raise HTTPException(
                status_code=400,
                detail=(
                    f'Result {winner.id} hat keine resolved_config_json — die '
                    f'Kombination lässt sich nicht einfrieren.'
                ),
            )
        frozen = winner_block(winner, plan.get('selection_metric'))
        indicators_config = copy.deepcopy(dict(winner.resolved_config_json))

        anchor = load_anchor_run(session, anchor_run_id)
        backtest_config = copy.deepcopy(dict(anchor.backtest_config_json or {}))
        anchor_iteration_id = anchor.iteration_id
    finally:
        session.close()

    backtest_config = set_backtest_window(backtest_config, window['start'], window['end'])
    # Testfenster-Läufe rechnen genau eine Kombination: die Metrik-Stufe des
    # Rasters gilt hier nicht, der Default 'auto' liefert die vollen Kennzahlen.
    backtest_config.pop('metrics', None)

    run_id = create_backtest_run(
        backtest_config=backtest_config,
        indicators_config=indicators_config,
        parent_run_id=anchor_run_id,
        parent_result_id=frozen['result_id'],
        selection_metric=plan.get('selection_metric'),
        spec_runner_version=_spec_runner_version,
        iteration_id=anchor_iteration_id,
    )
    enqueue_backtest_run(run_id)
    logger.info(
        '[WF-KETTE] Kette %d, Fold %d: OOS-Lauf %d gestartet (Sieger-Result %d, %s..%s).',
        chain_id, payload.fold_index, run_id, frozen['result_id'],
        window['start'], window['end'],
    )
    return {
        'data': {
            'chain_id': chain_id,
            'fold_index': payload.fold_index,
            'is_run_id': payload.is_run_id,
            'winner': frozen,
            'no_winner_reason': None,
            'oos_run_id': run_id,
            'oos_window': window,
        },
        'error': None,
    }
