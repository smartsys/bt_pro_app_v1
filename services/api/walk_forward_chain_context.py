"""Gemeinsame Bausteine der Walk-Forward-Ketten-Routen.

Hier liegt, was sowohl die Artefakt-Routen
(:mod:`services.api.routes.api_walk_forward_chains`) als auch die Lauf-Routen
(:mod:`services.api.routes.api_walk_forward_chain_runs`) brauchen: den Anker-Lauf
laden, die offene Kette laden, einen geplanten Fold nachschlagen, den Kontext
einfrieren und einen Lauf einreihen.

Die Funktionen melden Fehler als ``HTTPException`` — sie sind Randstücke der API,
kein Domänenmodell.
"""

import copy
from typing import Any, Dict

from fastapi import HTTPException
from rq import Queue

from services.api.redis_conn import (
    BACKTEST_JOB_TIMEOUT,
    BACKTEST_QUEUE_NAME,
    get_redis_connection,
)
from services.api.utils.walk_forward_plan import plan_fold
from user_data.utils.database.models import (
    WALK_FORWARD_CHAIN_TERMINAL_STATUS,
    BacktestRun,
)
from user_data.utils.database.repository_walk_forward_chains import (
    get_walk_forward_chain,
)


def load_anchor_run(session, anchor_run_id: int) -> BacktestRun:
    """Lädt den Anker-Lauf und prüft ihn auf Ketten-Tauglichkeit.

    Args:
        session: Aktive SQLAlchemy-Session.
        anchor_run_id: ID des Anker-Laufs.

    Returns:
        Der Anker-Lauf.

    Raises:
        HTTPException: Wenn der Lauf fehlt oder ihm die Iteration fehlt (ohne die
            findet der Worker keine Regeln).
    """
    run = session.query(BacktestRun).filter(BacktestRun.id == anchor_run_id).first()
    if run is None:
        raise HTTPException(status_code=404, detail=f'Run {anchor_run_id} nicht gefunden.')
    if run.iteration_id is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f'Run {anchor_run_id} hat keine iteration_id — die Ketten-Läufe hätten '
                f'keine Regeln. Ein Anker-Lauf muss an einer Iteration hängen.'
            ),
        )
    return run


def load_running_chain(session, chain_id: int):
    """Lädt eine Kette und stellt sicher, dass sie noch offen ist.

    Args:
        session: Aktive SQLAlchemy-Session.
        chain_id: ID der Kette.

    Returns:
        Die Kette.

    Raises:
        HTTPException: Wenn die Kette fehlt oder bereits abgeschlossen ist.
    """
    chain = get_walk_forward_chain(session, chain_id)
    if chain is None:
        raise HTTPException(
            status_code=404, detail=f'Walk-Forward-Kette {chain_id} nicht gefunden.',
        )
    if chain.status in WALK_FORWARD_CHAIN_TERMINAL_STATUS:
        raise HTTPException(
            status_code=400,
            detail=(
                f'Walk-Forward-Kette {chain_id} ist mit Status "{chain.status}" '
                f'abgeschlossen und unveränderlich.'
            ),
        )
    return chain


def planned_fold_or_400(plan: Dict[str, Any], fold_index: int) -> Dict[str, Any]:
    """Holt den geplanten Fold-Block oder meldet einen sauberen 400er.

    Args:
        plan: Das ``plan_json`` der Kette.
        fold_index: 1-basierter Fold-Index.

    Returns:
        Der geplante Fold-Block.

    Raises:
        HTTPException: Wenn der Index nicht im Plan steht.
    """
    try:
        return plan_fold(plan, fold_index)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def config_snapshot(run: BacktestRun) -> Dict[str, Any]:
    """Friert den Kontext des Anker-Laufs für die Kette ein.

    Args:
        run: Der Anker-Lauf.

    Returns:
        Symbol, Exchange, Timeframe, Portfolio-Kern und Anker-Fenster als Kopie.
    """
    config = dict(run.backtest_config_json or {})
    return {
        'anchor_run_id': run.id,
        'symbol': run.symbol,
        'symbols': config.get('symbols'),
        'exchange': run.exchange,
        'timeframe': run.timeframe,
        'strategy_family': run.strategy_family,
        'strategy_name': run.strategy_name,
        'portfolio': copy.deepcopy(config.get('portfolio')),
        'anchor_window': {
            'start': config.get('start'),
            'end': config.get('end'),
            'ohlc_start': config.get('ohlc_start'),
            'ohlc_end': config.get('ohlc_end'),
        },
        'n_combinations': run.n_combinations,
        'spec_runner_version': run.spec_runner_version,
        'ann_factor': run.ann_factor,
    }


def enqueue_backtest_run(run_id: int) -> None:
    """Reiht einen Backtest-Lauf in die Queue ein.

    Args:
        run_id: ID des angelegten Laufs.
    """
    queue = Queue(BACKTEST_QUEUE_NAME, connection=get_redis_connection())
    queue.enqueue(
        'services.api.worker_tasks.run_backtest_job',
        run_id=run_id,
        job_timeout=BACKTEST_JOB_TIMEOUT,
    )
