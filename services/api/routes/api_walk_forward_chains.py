"""Artefakt-Routen der Walk-Forward-Fold-Kette (Ticket 82)

POST /api/backtest/walk-forward-chains            — Kette mit vollem Plan anlegen
POST /api/backtest/walk-forward-chains/{id}/folds — abgeschlossenen Fold anhängen
POST /api/backtest/walk-forward-chains/{id}/close — aggregieren und versiegeln
GET  /api/walk-forward-chains/{id}                — eine Kette
GET  /api/walk-forward-chains?iteration_id=…      — Historie, chronologisch

Die beiden Lauf-Endpunkte der Kette (``/is-run`` und ``/oos-run``) liegen in
:mod:`services.api.routes.api_walk_forward_chain_runs`.

Die Orchestrierung ist client-getrieben (Toolbox-Verb, run-wait-Muster) — hier
liegen nur die Bausteine. Der Plan wird beim Anlegen festgeschrieben und **vor**
dem ersten Lauf gegen die vorhandene OHLC-Abdeckung geprüft: ragt ein Fold-Fenster
über die Daten hinaus, entsteht weder Datensatz noch Teillauf.

**Kein Verdict, keine Güte-Sortierung.** Die Historie liefert ausnahmslos die
chronologische Reihenfolge. Es gibt ebenso **keine** Update- und keine
Delete-Route: eine abgeschlossene Kette ist unveränderlich, ein erneuter Lauf
erzeugt eine neue Kette.
"""

import logging
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.api.utils.walk_forward_aggregation import build_chain_aggregate
from services.api.utils.walk_forward_plan import (
    METHOD_NOTE,
    build_fold_plan,
    validate_plan_coverage,
)
from services.api.utils.walk_forward_selection import (
    result_metrics,
    validate_selection_metric,
)
from services.api.walk_forward_chain_context import (
    config_snapshot,
    load_anchor_run,
    load_running_chain,
    planned_fold_or_400,
)
from user_data.utils.database.db import get_session
from user_data.utils.database.models import (
    BacktestResult,
    BacktestRun,
    StrategyIteration,
)
from user_data.utils.database.repository_walk_forward_chains import (
    WalkForwardPlanMismatchError,
    append_walk_forward_fold,
    complete_walk_forward_chain,
    create_walk_forward_chain,
    fail_walk_forward_chain,
    get_walk_forward_chain,
    list_walk_forward_chains,
    walk_forward_chain_to_dict,
)
from user_data.utils.metrics.metric_sets import validate_metrics_selection
from user_data.utils.ohlc.coverage import ohlc_coverage

logger = logging.getLogger(__name__)

router = APIRouter(tags=['walk-forward-chains'])

CHAIN_BASE = '/api/backtest/walk-forward-chains'


# ============================================================================
# Eingabe-Schemata
# ============================================================================

class ChainStartIn(BaseModel):
    """Eingabe zum Anlegen einer Kette — zugleich die Vorregistrierung."""
    anchor_run_id: int = Field(description='Lauf, dessen Raster und Fenster den Anker bilden.')
    folds: int = Field(description='Anzahl der Folds (>= 1).')
    oos_months: int = Field(description='Länge des Testfensters in Monaten.')
    is_months: Optional[int] = Field(
        default=None,
        description='Länge des Optimierfensters in Monaten. Default: Länge des Anker-Fensters.',
    )
    selection_metric: str = Field(description='Kennzahl-Feld, nach dem der Sieger gewählt wird.')
    selection_direction: str = Field(default='max', description="'max' oder 'min'.")
    trade_floor: int = Field(default=0, description='Mindestzahl Trades eines Kandidaten.')
    metrics: Optional[Union[str, List[str]]] = Field(
        default=None,
        description="Metrik-Stufe der IS-Läufe ('kern'/'voll'/'auto' oder Gruppenliste).",
    )


class FoldAppendIn(BaseModel):
    """Eingabe zum Anhängen eines abgeschlossenen Fold-Blocks."""
    fold_index: int = Field(description='1-basierter Fold-Index aus dem Plan.')
    is_window: Dict[str, Any] = Field(description='Gerechnetes IS-Fenster (start/end).')
    is_run_id: Optional[int] = Field(default=None, description='IS-Lauf des Folds.')
    oos_window: Optional[Dict[str, Any]] = Field(
        default=None, description='Gerechnetes OOS-Fenster (start/end).',
    )
    winner: Optional[Dict[str, Any]] = Field(
        default=None, description='Sieger-Block aus dem oos-run-Aufruf.',
    )
    oos_run_id: Optional[int] = Field(default=None, description='Testfenster-Lauf.')
    oos_result_id: Optional[int] = Field(default=None, description='Testfenster-Result.')
    no_winner_reason: Optional[str] = Field(
        default=None, description='Grund, wenn der Fold ohne Sieger blieb.',
    )


class ChainCloseIn(BaseModel):
    """Eingabe zum Abschluss einer Kette."""
    error_message: Optional[str] = Field(
        default=None,
        description='Gesetzt = Abbruch: die Kette schließt mit Status "failed".',
    )


# ============================================================================
# Kette anlegen
# ============================================================================

@router.post(CHAIN_BASE)
def start_walk_forward_chain(payload: ChainStartIn):
    """Legt eine Kette mit vollständigem Plan an und gibt die ``chain_id`` zurück.

    Reihenfolge ist wesentlich: Kriterium und Metrik-Stufe werden syntaktisch
    geprüft, der Plan gerechnet und gegen die vorhandene OHLC-Abdeckung validiert
    — **erst danach** entsteht der Datensatz. Ein Plan, der über die Daten
    hinausragt, hinterlässt damit keine halbe Kette.
    """
    try:
        metric = validate_selection_metric(payload.selection_metric)
        metrics_level = validate_metrics_selection(payload.metrics)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session = get_session()
    try:
        anchor = load_anchor_run(session, payload.anchor_run_id)
        anchor_config = dict(anchor.backtest_config_json or {})

        try:
            plan = build_fold_plan(
                anchor_config=anchor_config,
                n_folds=payload.folds,
                oos_months=payload.oos_months,
                is_months=payload.is_months,
                selection_metric=metric,
                selection_direction=payload.selection_direction,
                trade_floor=payload.trade_floor,
                metrics_level=metrics_level,
            )
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        symbols = anchor_config.get('symbols') or [anchor.symbol]
        try:
            coverage = ohlc_coverage(anchor.exchange, anchor.timeframe, list(symbols))
            validate_plan_coverage(plan, coverage)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        iteration = (
            session.query(StrategyIteration)
            .filter(StrategyIteration.id == anchor.iteration_id)
            .first()
        )
        chain = create_walk_forward_chain(
            session=session,
            anchor_run_id=anchor.id,
            plan=plan,
            iteration_id=anchor.iteration_id,
            concept_id=iteration.concept_id if iteration else None,
            config_snapshot=config_snapshot(anchor),
            method_note=METHOD_NOTE,
        )
        return {
            'data': {
                'chain_id': chain.id,
                'chain': walk_forward_chain_to_dict(chain),
            },
            'error': None,
        }
    finally:
        session.close()


# ============================================================================
# Fold anhängen und Kette schließen
# ============================================================================

@router.post(CHAIN_BASE + '/{chain_id}/folds')
def append_chain_fold(chain_id: int, payload: FoldAppendIn):
    """Hängt einen abgeschlossenen Fold-Block an — geprüft gegen den Plan.

    Der Aufrufer liefert die IDs, der Server kopiert die Werte: die OOS-Kennzahlen
    werden hier aus dem Result gelesen und vollständig in den Fold-Block
    übernommen, dazu der Annualisierungsfaktor des Laufs. Damit bleibt der Fold
    lesbar, wenn Lauf und Result später aufgeräumt sind.
    """
    if payload.winner is None and (payload.oos_run_id or payload.oos_result_id):
        raise HTTPException(
            status_code=400,
            detail='Ohne Sieger darf kein OOS-Lauf und kein OOS-Result am Fold hängen.',
        )

    session = get_session()
    try:
        chain = load_running_chain(session, chain_id)
        # Früher, sprechender 400er, wenn der Index gar nicht im Plan steht — die
        # eigentliche Plan-Prüfung (Index-Reihenfolge, Fenstergrenzen) macht das
        # Repository beim Anhängen.
        planned_fold_or_400(chain.plan_json or {}, payload.fold_index)

        oos_metrics: Optional[Dict[str, Any]] = None
        ann_factor: Optional[float] = None
        if payload.oos_result_id:
            result = (
                session.query(BacktestResult)
                .filter(BacktestResult.id == payload.oos_result_id)
                .first()
            )
            if result is None:
                raise HTTPException(
                    status_code=404,
                    detail=f'OOS-Result {payload.oos_result_id} nicht gefunden.',
                )
            oos_metrics = result_metrics(result)
            oos_run = (
                session.query(BacktestRun)
                .filter(BacktestRun.id == result.run_id)
                .first()
            )
            ann_factor = oos_run.ann_factor if oos_run else None

        fold = {
            'fold_index': payload.fold_index,
            'is_window': payload.is_window,
            'is_run_id': payload.is_run_id,
            'winner': payload.winner,
            'no_winner_reason': payload.no_winner_reason,
            'oos_window': payload.oos_window,
            'oos_run_id': payload.oos_run_id,
            'oos_result_id': payload.oos_result_id,
            'oos_metrics': oos_metrics,
            'ann_factor': ann_factor,
        }

        try:
            chain = append_walk_forward_fold(session, chain_id, fold)
        except WalkForwardPlanMismatchError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return {
            'data': {
                'chain_id': chain.id,
                'fold_index': payload.fold_index,
                'folds_total': len(chain.folds_json or []),
                'chain': walk_forward_chain_to_dict(chain),
            },
            'error': None,
        }
    finally:
        session.close()


@router.post(CHAIN_BASE + '/{chain_id}/close')
def close_walk_forward_chain(chain_id: int, payload: Optional[ChainCloseIn] = None):
    """Rechnet die Aggregation serverseitig und versiegelt die Kette.

    Mit ``error_message`` schließt die Kette als ``failed`` — bereits gelaufene
    Folds und ihr Teil-Aggregat bleiben erhalten, der Abbruchgrund steht im
    Datensatz. Ohne ``error_message`` schließt sie als ``completed``.
    """
    error_message = payload.error_message if payload else None
    session = get_session()
    try:
        chain = load_running_chain(session, chain_id)
        aggregate = build_chain_aggregate(
            session=session,
            plan=chain.plan_json or {},
            folds=list(chain.folds_json or []),
        )
        if error_message:
            chain = fail_walk_forward_chain(
                session, chain_id, error_message, aggregate=aggregate,
            )
        else:
            chain = complete_walk_forward_chain(session, chain_id, aggregate)
        return {'data': walk_forward_chain_to_dict(chain), 'error': None}
    finally:
        session.close()


# ============================================================================
# Lesen
# ============================================================================

@router.get('/api/walk-forward-chains/{chain_id}')
def get_walk_forward_chain_route(chain_id: int):
    """Eine einzelne Kette — bleibt lesbar, auch wenn Läufe und Results längst
    aufgeräumt wurden (lose Referenzen, siehe Modell-Docstring)."""
    session = get_session()
    try:
        chain = get_walk_forward_chain(session, chain_id)
        if chain is None:
            raise HTTPException(
                status_code=404, detail=f'Walk-Forward-Kette {chain_id} nicht gefunden.',
            )
        return {'data': walk_forward_chain_to_dict(chain), 'error': None}
    finally:
        session.close()


@router.get('/api/walk-forward-chains')
def list_walk_forward_chains_route(
    iteration_id: Optional[int] = Query(
        default=None, description='Optionale Einschränkung auf eine Iteration.',
    ),
):
    """Ketten-Historie — chronologisch, ohne Sortier- oder Filteroption.

    Bewusst keine Sortierung nach Ergebnis: sonst würde die Historie zur
    Bestenliste, und die Kette ist ein Bericht, kein Filter.
    """
    session = get_session()
    try:
        chains = list_walk_forward_chains(session, iteration_id)
        items = [walk_forward_chain_to_dict(chain) for chain in chains]
        return {'data': {'items': items, 'total': len(items)}, 'error': None}
    finally:
        session.close()
