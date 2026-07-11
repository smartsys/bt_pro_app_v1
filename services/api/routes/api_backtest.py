"""
JSON-API Endpoints für Backtest-Daten

GET /api/backtest/runs              — Alle Runs
GET /api/backtest/runs/{id}/results — Results eines Runs
GET /api/backtest/runs/{id}/results/lookup — Result-Lookup per Parameter-Werten (exakt/±Toleranz)
GET /api/backtest/results           — Alle Results (mit Filtern)
GET /api/backtest/results/lookup    — Kombinations-Verfolgung über mehrere Runs (run_ids)
GET /api/backtest/results/dt        — DataTables Server-Side Processing
GET /api/backtest/filters           — Verfügbare Filter-Werte
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional

import pandas as pd
from fastapi import APIRouter, Query, HTTPException, Request, Body
from fastapi.responses import JSONResponse
from rq import Queue
from rq.job import Job as RqJob
from rq.registry import StartedJobRegistry
from rq.command import send_stop_job_command
from sqlalchemy import func, cast, String, Float, Text, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from services.api.recompute import recompute_single_result
from services.api.redis_conn import (
    get_redis_connection,
    BACKTEST_QUEUE_NAME,
    RECOMPUTE_QUEUE_NAME,
    BACKTEST_JOB_TIMEOUT,
)
from services.api.schemas import ApiResponse, PaginatedData, BacktestRunOut, BacktestResultOut
from user_data.utils.database.db import get_session, get_engine
from user_data.utils.database.models import (
    BacktestRun, BacktestResult, BacktestTrade, BacktestOrder, BacktestPosition,
    BacktestEquity, BacktestIndicator, BacktestParam, BacktestConfig, IndicatorConfig,
    BacktestJob, StrategyConfig,
    # GEÄNDERT: Ticket 11 — Concepts/Iterations für sprechende Strategie-Spalte
    StrategyConcept, StrategyIteration,
    TestSet, TestSetRun,
)
# GEÄNDERT: ToDo 10 — Key->Kürzel+Label-Mapping der Bestwert-Kriterien (Single Source, serverseitig)
from services.api.utils.best_criteria_labels import criteria_keys_to_badges
# GEÄNDERT: _build_resolved_config für den Iterations-Tooltip (alle Indikator-Eingabewerte)
from user_data.utils.database.repository import (
    create_backtest_run, _count_combinations, _build_resolved_config,
    get_run_param_names, lookup_result_rows_by_params,
    get_scope_param_names, lookup_results_across_runs,
)
# GEÄNDERT: Spec-Runner-Version für Reproduzierbarkeit (Ticket 01)
from user_data.strategies.generic.spec_runner import VERSION as _spec_runner_version, SPEC_RUNNER_IMPORT_PATH

# GEÄNDERT: Batch-Größe für Bulk-Delete erhöht (Ticket 08) — 10x weniger Append-Aufrufe über Hypertable-Chunks
_DELETE_BATCH_SIZE = 5000

# RQ-Job-Namen (voll-qualifiziert) als eine Wahrheit — von enqueue, _stop_run_jobs
# und den delete-active-Endpunkten gemeinsam genutzt.
BACKTEST_RUN_JOB = 'services.api.worker_tasks.run_backtest_job'
DELETE_ALL_RESULTS_JOB = 'services.api.worker_tasks.delete_all_results_job'
DELETE_ALL_RUNS_JOB = 'services.api.worker_tasks.delete_all_runs_job'

# GEÄNDERT: Stops aus Result-Snapshot statt run-weitem portfolio (sweep-fähig, per Result)
def _result_stops(result) -> tuple:
    """Liest die per-Result aufgelösten Skalar-Stops (tp_stop, sl_stop) aus dem
    full_config_snapshot_json['backtest_config'] des Results.

    Einzig korrekte Anzeige-Quelle bei gesweepten Stops — kein Fallback auf die
    run-weite portfolio-Config. Fehlt der Snapshot, sind beide None.
    """
    bc = (result.full_config_snapshot_json or {}).get('backtest_config') or {}
    return bc.get('tp_stop'), bc.get('sl_stop')


# GEÄNDERT: Stop-Keys für die Tooltip-Anzeige (td/tp/sl/tsl + tsl_th)
_TOOLTIP_STOP_KEYS = ('td_stop', 'tp_stop', 'sl_stop', 'tsl_stop', 'tsl_th')


def _result_stops_dict(result) -> dict:
    """Liefert alle gesetzten Stops aus dem Result-Snapshot für die Tooltip-Anzeige.

    Quelle ist full_config_snapshot_json['backtest_config']; es werden nur
    nicht-None-Werte zurückgegeben (td/tp/sl/tsl + tsl_th). Fehlt der Snapshot,
    ist das Dict leer.
    """
    bc = (result.full_config_snapshot_json or {}).get('backtest_config') or {}
    return {k: bc[k] for k in _TOOLTIP_STOP_KEYS if bc.get(k) is not None}


router = APIRouter(prefix='/api/backtest', tags=['backtest'])


@router.post('/start')
def start_backtest(request_body: dict):
    """Startet einen Backtest als Hintergrund-Job.

    Erstellt einen BacktestRun (sofort in /runs sichtbar) und übergibt
    nur die run_id an den Worker.

    Body (neu, Ticket 11): { "backtest_config_id": int, "indicator_config_id": int, "iteration_id": int }
    Body (legacy): { "backtest_config_id": int, "strategy_config_id": int, "indicator_config_id": int }
    """
    backtest_config_id = request_body.get('backtest_config_id')
    strategy_config_id = request_body.get('strategy_config_id')
    indicator_config_id = request_body.get('indicator_config_id')
    # GEÄNDERT: Ticket 11 — iteration_id aus neuem zweistufigem Dropdown
    iteration_id = request_body.get('iteration_id')

    if not backtest_config_id or not indicator_config_id:
        return JSONResponse(
            {'error': 'backtest_config_id und indicator_config_id erforderlich'},
            status_code=400,
        )

    # GEÄNDERT: Ticket 11 — entweder iteration_id oder strategy_config_id muss gesetzt sein
    if not iteration_id and not strategy_config_id:
        return JSONResponse(
            {'error': 'iteration_id oder strategy_config_id erforderlich'},
            status_code=400,
        )

    session = get_session()
    try:
        bt = session.query(BacktestConfig).filter(BacktestConfig.id == backtest_config_id).first()
        if not bt:
            return JSONResponse({'error': f'Backtest-Config #{backtest_config_id} nicht gefunden'}, status_code=404)

        ind = session.query(IndicatorConfig).filter(IndicatorConfig.id == indicator_config_id).first()
        if not ind:
            return JSONResponse({'error': f'Indicator-Config #{indicator_config_id} nicht gefunden'}, status_code=404)

        # GEÄNDERT: Ticket 11 — strategy_family/strategy_name aus Iteration ableiten wenn iteration_id gesetzt
        if iteration_id:
            iteration = session.query(StrategyIteration).filter(StrategyIteration.id == iteration_id).first()
            if not iteration:
                return JSONResponse({'error': f'Iteration #{iteration_id} nicht gefunden'}, status_code=404)
            concept = session.query(StrategyConcept).filter(StrategyConcept.id == iteration.concept_id).first()
            if not concept:
                return JSONResponse({'error': f'Concept für Iteration #{iteration_id} nicht gefunden'}, status_code=404)
            strategy_family = concept.slug
            strategy_name = iteration.version
            # GEÄNDERT: Iteration kann hartcodiert sein und eigenen Code-Pfad mitbringen
            # GEÄNDERT: generic-Iterationen nutzen immer den Spec-Runner
            if iteration.type == 'hardcoded':
                import_path = iteration.import_path
            else:
                import_path = SPEC_RUNNER_IMPORT_PATH
        else:
            # Legacy-Pfad: aus StrategyConfig
            strat = session.query(StrategyConfig).filter(StrategyConfig.id == strategy_config_id).first()
            if not strat:
                return JSONResponse({'error': f'Strategy-Config #{strategy_config_id} nicht gefunden'}, status_code=404)
            strategy_family = strat.strategy_family
            strategy_name = strat.strategy_name
            import_path = strat.import_path
            iteration_id = None

        # Backtest-Config direkt im Strategie-Format bauen
        backtest_config_json = {
            'strategy_family': strategy_family,
            'strategy_name': strategy_name,
            'symbols': [bt.symbol],
            'start': bt.start,
            'end': bt.end,
            'ohlc_start': bt.ohlc_start,
            'ohlc_end': bt.ohlc_end,
            'exchange': bt.exchange,
            'timeframe': bt.timeframe,
            'portfolio': {
                'size': bt.size,
                'size_type': bt.size_type,
                'init_cash': bt.init_cash,
                'fees': bt.fees,
                # GEÄNDERT: Schritt 3c/3d — Stop-Spalten UND Stop-Formate aus der
                # BacktestConfig entfernt. Stops samt Formaten kommen ausschließlich
                # aus indicators_json['_stops'] (IndicatorConfig).
            },
        }
        if import_path:
            backtest_config_json['import_path'] = import_path
        # GEÄNDERT: Schritt 3b — '_stops' stammt jetzt aus der IndicatorConfig
        # (config_json). Kein Clobbern mehr aus dem portfolio-Block; fehlt '_stops'
        # in der Config, gibt es schlicht keine Stops.
        indicators_json = dict(ind.config_json)
    finally:
        session.close()

    # Run anlegen (status=queued) — Worker setzt auf running wenn Job startet
    # GEÄNDERT: Spec-Runner-Version mitschreiben (Ticket 01)
    run_id = create_backtest_run(
        backtest_config=backtest_config_json,
        indicators_config=indicators_json,
        spec_runner_version=_spec_runner_version,
        # GEÄNDERT: Ticket 11 — iteration_id direkt übergeben
        iteration_id=iteration_id,
        # GEÄNDERT: Herkunfts-Referenzen auf die gewählten Configs mitschreiben
        backtest_config_id=backtest_config_id,
        indicator_config_id=indicator_config_id,
    )

    # Job in RQ-Queue einreihen — Worker braucht nur die run_id
    q = Queue(BACKTEST_QUEUE_NAME, connection=get_redis_connection())
    q.enqueue('services.api.worker_tasks.run_backtest_job', run_id=run_id, job_timeout=BACKTEST_JOB_TIMEOUT)

    return {'data': {'run_id': run_id}, 'error': None}


@router.post('/walk-forward')
def start_walk_forward(request_body: dict):
    """Walk-Forward: Nimmt die Parameter eines Results und startet einen neuen Run im nächsten Zeitraum.

    Body: { "result_id": int, "months": int (3/6/12), "metric": str }
    """
    from dateutil.relativedelta import relativedelta
    import copy

    result_id = request_body.get('result_id')
    months = request_body.get('months', 6)
    metric = request_body.get('metric', 'total_return_pct')

    if not result_id:
        return JSONResponse({'error': 'result_id erforderlich'}, status_code=400)

    session = get_session()
    try:
        result = session.query(BacktestResult).filter(BacktestResult.id == result_id).first()
        if not result:
            return JSONResponse({'error': f'Result #{result_id} nicht gefunden'}, status_code=404)

        run = session.query(BacktestRun).filter(BacktestRun.id == result.run_id).first()
        if not run:
            return JSONResponse({'error': f'Run #{result.run_id} nicht gefunden'}, status_code=404)

        # GEÄNDERT: Ticket 15 — _json-Suffix
        if not result.resolved_config_json:
            return JSONResponse({'error': f'Result #{result_id} hat keine resolved_config_json'}, status_code=400)

        parent_run_id = run.id
        backtest_config = copy.deepcopy(dict(run.backtest_config_json))
        indicators_config = copy.deepcopy(dict(result.resolved_config_json))
    finally:
        session.close()

    # Zeitraum berechnen: neuer Start = altes Ende, neues Ende = Start + months
    old_end = datetime.strptime(backtest_config['end'], '%Y-%m-%d')
    new_start = old_end
    new_end = new_start + relativedelta(months=months)

    backtest_config['start'] = new_start.strftime('%Y-%m-%d')
    backtest_config['end'] = new_end.strftime('%Y-%m-%d')
    # OHLC-Daten: Vorlauf beibehalten (Differenz ohlc_start zu start)
    old_start = datetime.strptime(backtest_config.get('start', backtest_config['start']), '%Y-%m-%d')
    old_ohlc_start = datetime.strptime(backtest_config.get('ohlc_start', backtest_config['start']), '%Y-%m-%d')
    vorlauf = old_start - old_ohlc_start
    backtest_config['ohlc_start'] = (new_start - vorlauf).strftime('%Y-%m-%d')
    backtest_config['ohlc_end'] = new_end.strftime('%Y-%m-%d')

    # Run erstellen und Job starten
    # GEÄNDERT: Spec-Runner-Version mitschreiben (Ticket 01)
    run_id = create_backtest_run(
        backtest_config=backtest_config,
        indicators_config=indicators_config,
        parent_run_id=parent_run_id,
        parent_result_id=result_id,
        selection_metric=metric,
        spec_runner_version=_spec_runner_version,
    )

    q = Queue(BACKTEST_QUEUE_NAME, connection=get_redis_connection())
    q.enqueue('services.api.worker_tasks.run_backtest_job', run_id=run_id, job_timeout=BACKTEST_JOB_TIMEOUT)

    return {
        'data': {
            'run_id': run_id,
            'parent_run_id': parent_run_id,
            'parent_result_id': result_id,
            'start': backtest_config['start'],
            'end': backtest_config['end'],
        },
        'error': None,
    }


@router.get('/runs', response_model=ApiResponse)
def get_runs(
    limit: int = Query(10000),
    offset: int = Query(0),
    iteration_id: Optional[int] = Query(None),
    strategy: Optional[str] = Query(None),
    version: Optional[int] = Query(None),
    testset_run_id: Optional[int] = Query(None),
) -> ApiResponse:
    """Backtest-Runs als JSON, optional gefiltert.

    Filter (alle UND-verknuepft):
    - iteration_id: nur Runs dieser Iteration (FK backtest_runs.iteration_id).
    - strategy (Konzept-Slug) + optional version: serverseitig zu den
      passenden iteration_ids aufgeloest (Concept.slug [+ Iteration.version]),
      damit der Aufrufer in Strategie+Version denkt statt in Datensatz-IDs.
      Ohne version werden alle Versionen der Strategie einbezogen. Existiert
      die Strategie/Version nicht, kommt eine leere Liste zurueck.
    - testset_run_id: nur Runs dieses TestSet-Laufs.
    """
    session = get_session()
    try:
        query = session.query(BacktestRun).order_by(BacktestRun.created_at.desc())

        # GEAENDERT: (Slug, Version) -> iteration_ids aufloesen, damit der Aufrufer
        # ueber Strategie+Version filtern kann, nicht ueber interne Datensatz-IDs.
        if strategy is not None:
            iter_q = (
                session.query(StrategyIteration.id)
                .join(StrategyConcept, StrategyIteration.concept_id == StrategyConcept.id)
                .filter(StrategyConcept.slug == strategy)
            )
            if version is not None:
                iter_q = iter_q.filter(StrategyIteration.version == version)
            iter_ids = [row[0] for row in iter_q.all()]
            if not iter_ids:
                # Strategie/Version gibt es nicht -> leeres Ergebnis statt Fehler
                return ApiResponse(data=PaginatedData(items=[], total=0, limit=limit, offset=offset))
            query = query.filter(BacktestRun.iteration_id.in_(iter_ids))

        if iteration_id is not None:
            query = query.filter(BacktestRun.iteration_id == iteration_id)
        if testset_run_id is not None:
            query = query.filter(BacktestRun.testset_run_id == testset_run_id)

        total = query.count()
        runs = query.offset(offset).limit(limit).all()
        items = [BacktestRunOut.model_validate(r).model_dump(mode='json') for r in runs]

        # GEÄNDERT: Result-Anzahl pro Run nur für ABGESCHLOSSENE Runs zählen - und gezielt
        # über deren run_ids, statt per GROUP BY über die ganze Tabelle (Full-Scan, ~10 s
        # bei >700k Zeilen). Der Filter auf die stabilen run_ids nutzt die (run_id,...)-
        # Indizes (Range-Scan, ~ms je Run auf vacuumter Tabelle). Laufende/eingereihte Runs
        # werden übersprungen: deren Zeilen werden gerade geschrieben (Count langsam, weil
        # die Visibility Map noch nicht gesetzt ist) und die Zahl wäre ohnehin unvollständig
        # - das Frontend zeigt dort den Chunk-Fortschritt.
        stable_run_ids = [r.id for r in runs if r.status in ('completed', 'failed')]
        result_counts: dict[int, int] = {}
        if stable_run_ids:
            result_counts = dict(
                session.query(BacktestResult.run_id, func.count(BacktestResult.id))
                .filter(BacktestResult.run_id.in_(stable_run_ids))
                .group_by(BacktestResult.run_id)
                .all()
            )

        # Job-Status pro Run (für Worker-Anzeige)

        job_stats_rows = session.query(
            BacktestJob.run_id, BacktestJob.status, func.count(BacktestJob.id)
        ).group_by(BacktestJob.run_id, BacktestJob.status).all()
        job_stats: dict[int, dict[str, int]] = {}
        for run_id_val, status, cnt in job_stats_rows:
            job_stats.setdefault(run_id_val, {})[status] = cnt

        # TestSet-Namen + IDs über TestSetRun -> TestSet laden
        ts_run_ids = {r.testset_run_id for r in runs if r.testset_run_id}
        ts_info: dict[int, dict] = {}
        if ts_run_ids:
            ts_rows = (
                session.query(TestSetRun.id, TestSet.id, TestSet.name)
                .join(TestSet, TestSet.id == TestSetRun.testset_id)
                .filter(TestSetRun.id.in_(ts_run_ids))
                .all()
            )
            ts_info = {tsr_id: {'testset_id': ts_id, 'testset_name': ts_name} for tsr_id, ts_id, ts_name in ts_rows}

        # GEÄNDERT: Namen der verknüpften Indikator-Configs laden (lose Referenz über
        # indicator_config_id; nicht im Schema -> per run_id->config_id-Map). Gelöschte/
        # fehlende Config -> kein Name.
        run_to_ind_cfg = {r.id: r.indicator_config_id for r in runs if r.indicator_config_id}
        ind_cfg_names: dict[int, str] = {}
        if run_to_ind_cfg:
            ind_cfg_names = dict(
                session.query(IndicatorConfig.id, IndicatorConfig.name)
                .filter(IndicatorConfig.id.in_(set(run_to_ind_cfg.values())))
                .all()
            )

        for item in items:
            # GEÄNDERT: None für laufende/eingereihte Runs (Count übersprungen) - das
            # Frontend zeigt dort "–"; abgeschlossene Runs ohne Treffer bleiben 0.
            if item['status'] in ('completed', 'failed'):
                item['result_count'] = result_counts.get(item['id'], 0)
            else:
                item['result_count'] = None
            # GEÄNDERT: Name der Indikator-Config (None wenn keine/gelöscht)
            item['indicator_config_name'] = ind_cfg_names.get(run_to_ind_cfg.get(item['id']))
            # GEÄNDERT: Size-Type aus dem eingefrorenen Backtest-Config-Block (unter 'portfolio';
            # None wenn nicht gesetzt)
            item['size_type'] = (
                (item.get('backtest_config_json') or {}).get('portfolio') or {}
            ).get('size_type')
            js = job_stats.get(item['id'], {})
            item['jobs_queued'] = js.get('queued', 0)
            item['jobs_running'] = js.get('running', 0)
            item['jobs_completed'] = js.get('completed', 0)
            item['jobs_failed'] = js.get('failed', 0)
            ts = ts_info.get(item.get('testset_run_id')) if item.get('testset_run_id') else None
            item['testset_id'] = ts['testset_id'] if ts else None
            item['testset_name'] = ts['testset_name'] if ts else None

        return ApiResponse(data=PaginatedData(items=items, total=total, limit=limit, offset=offset))
    finally:
        session.close()


@router.get('/runs/{run_id}/results', response_model=ApiResponse)
def get_results(run_id: int, limit: int = Query(10000), offset: int = Query(0)) -> ApiResponse:
    """Alle Results eines Backtest-Runs als JSON."""
    session = get_session()
    try:
        query = session.query(BacktestResult).filter(
            BacktestResult.run_id == run_id
        ).order_by(BacktestResult.total_return_pct.desc())
        total = query.count()
        results = query.offset(offset).limit(limit).all()

        items = []
        for r in results:
            item = BacktestResultOut.model_validate(r).model_dump(mode='json')
            # GEÄNDERT: Stops aus Result-Snapshot statt run-weitem portfolio (per Result)
            item['tp_stop'], item['sl_stop'] = _result_stops(r)
            items.append(item)
        return ApiResponse(data=PaginatedData(items=items, total=total, limit=limit, offset=offset))
    finally:
        session.close()


# GEÄNDERT: Result-Lookup per Parameter-Werten (exakt + Nachbarschafts-Modus).
# Query-Logik liegt in repository.py (lookup_result_rows_by_params), damit sie
# ohne die Container-Abhängigkeiten dieser Route (rq/redis) testbar ist.
# Query-Keys der Lookup-Route, die KEINE Parameter-Filter sind.
_LOOKUP_RESERVED_KEYS = {'tolerance', 'tolerance_steps', 'limit'}


@router.get('/runs/{run_id}/results/lookup', response_model=ApiResponse)
def lookup_results_by_params(
    run_id: int,
    request: Request,
    tolerance: float = Query(0.0, ge=0),
    tolerance_steps: Optional[int] = Query(None, ge=1),
    limit: int = Query(100, ge=1),
) -> ApiResponse:
    """Result-Lookup per Parameter-Werten innerhalb eines Runs.

    Alle Query-Parameter außer tolerance/tolerance_steps/limit werden als
    Parameter-Filter gelesen (z.B. ?vwma_length=6&vwma_below_pct=10). Ohne
    Toleranz = exakter Lookup der einen Kombination. tolerance>0 =
    Nachbarschafts-Modus mit skalarer Fenster-Breite je Parameter.
    tolerance_steps=N = schrittweiter Nachbarschafts-Modus: je Parameter ±N
    Raster-Schritte (Schrittweite aus den distinct-Werten des Runs abgeleitet)
    — bildet eine echte ±N-Schritt-Nachbarschaft auch bei ungleichen
    Schrittweiten je Achse (Plateau-Prüfung). tolerance und tolerance_steps
    schließen sich aus. Unbekannte Parameter-Namen und nicht-numerische Werte
    geben 400 mit den vorhandenen Namen des Runs.
    """
    if tolerance_steps is not None and tolerance > 0:
        raise HTTPException(status_code=400,
                            detail="tolerance und tolerance_steps schließen sich aus — nur eins angeben")
    filters: Dict[str, float] = {}
    for key, raw in request.query_params.items():
        if key in _LOOKUP_RESERVED_KEYS:
            continue
        try:
            filters[key] = float(raw)
        except ValueError:
            raise HTTPException(status_code=400,
                                detail=f"Parameter {key!r}: Wert {raw!r} ist nicht numerisch")
    if not filters:
        raise HTTPException(status_code=400,
                            detail="Mindestens ein Parameter-Filter nötig (z.B. ?vwma_length=6)")

    engine = get_engine()
    known = get_run_param_names(engine, run_id)
    unknown = sorted(set(filters) - set(known))
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unbekannte Parameter für Run {run_id}: {', '.join(unknown)}. "
                   f"Vorhanden: {', '.join(known) or 'keine (Run leer?)'}",
        )
    items, total = lookup_result_rows_by_params(engine, run_id, filters, tolerance, limit,
                                                tolerance_steps=tolerance_steps)
    return ApiResponse(data=PaginatedData(items=items, total=total, limit=limit, offset=0))


# GEÄNDERT: Kombinations-Verfolgung — Lookup über MEHRERE Runs (combo-trace).
# Query-Keys der Across-Runs-Route, die KEINE Parameter-Filter sind.
_TRACE_RESERVED_KEYS = {'run_ids', 'tolerance', 'tolerance_steps', 'limit'}


@router.get('/results/lookup', response_model=ApiResponse)
def lookup_results_across_runs_route(
    request: Request,
    run_ids: str = Query(..., description='Komma-getrennte Run-IDs, z.B. 10,11,12'),
    tolerance: float = Query(0.0, ge=0),
    tolerance_steps: Optional[int] = Query(None, ge=1),
    limit: int = Query(200, ge=1),
) -> ApiResponse:
    """Kombinations-Verfolgung: Result-Lookup per Parameter-Werten über mehrere Runs.

    Wie /runs/{run_id}/results/lookup, aber mit expliziter Run-Menge (run_ids)
    statt einem festen Run — der Aufrufer löst den Scope (Iteration, Strategie,
    Testset-Lauf) selbst zu Run-IDs auf. Ergebnis enthält Run-Kontext
    (run_id, symbol, timeframe) und ist nach run_id sortiert. tolerance_steps=N
    leitet die Schrittweite je Run einzeln ab (Raster können differieren).
    tolerance und tolerance_steps schließen sich aus.
    """
    if tolerance_steps is not None and tolerance > 0:
        raise HTTPException(status_code=400,
                            detail="tolerance und tolerance_steps schließen sich aus — nur eins angeben")
    try:
        run_id_list = [int(part) for part in run_ids.split(',') if part.strip()]
    except ValueError:
        raise HTTPException(status_code=400,
                            detail=f"run_ids muss eine Komma-Liste von IDs sein, bekommen: {run_ids!r}")
    if not run_id_list:
        raise HTTPException(status_code=400, detail="run_ids ist leer")

    filters: Dict[str, float] = {}
    for key, raw in request.query_params.items():
        if key in _TRACE_RESERVED_KEYS:
            continue
        try:
            filters[key] = float(raw)
        except ValueError:
            raise HTTPException(status_code=400,
                                detail=f"Parameter {key!r}: Wert {raw!r} ist nicht numerisch")
    if not filters:
        raise HTTPException(status_code=400,
                            detail="Mindestens ein Parameter-Filter nötig (z.B. ?vwma_length=6)")

    engine = get_engine()
    known = get_scope_param_names(engine, run_id_list)
    unknown = sorted(set(filters) - set(known))
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unbekannte Parameter für die Run-Menge: {', '.join(unknown)}. "
                   f"Vorhanden: {', '.join(known) or 'keine (Runs leer?)'}",
        )
    items, total = lookup_results_across_runs(engine, run_id_list, filters, tolerance, limit,
                                              tolerance_steps=tolerance_steps)
    return ApiResponse(data=PaginatedData(items=items, total=total, limit=limit, offset=0))


@router.get('/results', response_model=ApiResponse)
def get_all_results(
    limit: int = Query(10000),
    offset: int = Query(0),
    strategy: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    timeframe: Optional[str] = Query(None),
    run_id: Optional[int] = Query(None),
) -> ApiResponse:
    """Alle Results mit optionalen Filtern. Joined mit backtest_runs für Kontext."""
    session = get_session()
    try:
        # GEÄNDERT: Ticket 11 — outer join auf Iterations/Concepts für sprechende Strategie-Spalte
        query = (
            session.query(BacktestResult, BacktestRun, StrategyIteration, StrategyConcept, IndicatorConfig)
            .join(BacktestRun, BacktestResult.run_id == BacktestRun.id)
            .outerjoin(StrategyIteration, BacktestRun.iteration_id == StrategyIteration.id)
            .outerjoin(StrategyConcept, StrategyIteration.concept_id == StrategyConcept.id)
            # GEÄNDERT: Indikator-Config (lose Verknüpfung über indicator_config_id) für
            # die Namens-Anzeige in der Iterations-Spalte. Gelöschte/fehlende Config -> NULL.
            .outerjoin(IndicatorConfig, BacktestRun.indicator_config_id == IndicatorConfig.id)
        )
        if strategy:
            query = query.filter(BacktestRun.strategy_name == strategy)
        if symbol:
            query = query.filter(BacktestRun.symbol == symbol)
        if timeframe:
            query = query.filter(BacktestRun.timeframe == timeframe)
        if run_id:
            query = query.filter(BacktestResult.run_id == run_id)

        query = query.order_by(BacktestResult.total_return_pct.desc())
        rows = query.offset(offset).limit(limit).all()
        total = len(rows) if len(rows) < limit else query.count()

        items = []
        for result, run, iteration, concept, ind_config in rows:
            # GEÄNDERT: Stops aus Result-Snapshot statt run-weitem portfolio (per Result)
            tp_stop, sl_stop = _result_stops(result)
            items.append({
                'id': result.id,
                'run_id': result.run_id,
                # GEÄNDERT: Ticket 15 — _json-Suffix
                'actual_params': result.actual_params_json,
                'total_return_pct': result.total_return_pct,
                'benchmark_return_pct': result.benchmark_return_pct,
                'sharpe_ratio': result.sharpe_ratio,
                'sortino_ratio': result.sortino_ratio,
                'max_drawdown_pct': result.max_drawdown_pct,
                'total_trades': result.total_trades,
                'win_rate_pct': result.win_rate_pct,
                'profit_factor': result.profit_factor,
                'end_value': result.end_value,
                'strategy_family': run.strategy_family,
                'strategy_name': run.strategy_name,
                # GEÄNDERT: Ticket 11 — sprechende Strategie-Felder aus Concept/Iteration
                'concept_name': concept.name if concept else None,
                # GEÄNDERT: Iterations-Version (Integer) + optionaler Name, keine PK-ID
                'iteration_version': iteration.version if iteration else None,
                'iteration_name': iteration.version_name if iteration else None,
                # GEÄNDERT: Name der verknüpften Indikator-Config (None wenn keine/gelöscht)
                'indicator_config_name': ind_config.name if ind_config else None,
                # GEÄNDERT: Alle aufgelösten Stops für den Iterations-Tooltip
                'stops': _result_stops_dict(result),
                'symbol': run.symbol,
                'exchange': run.exchange,
                'timeframe': run.timeframe,
                'start_date': run.start_date.isoformat() if run.start_date else None,
                'end_date': run.end_date.isoformat() if run.end_date else None,
                'tp_stop': tp_stop,
                'sl_stop': sl_stop,
            })

        return ApiResponse(data=PaginatedData(items=items, total=total, limit=limit, offset=offset))
    finally:
        session.close()


# Spalten-Mapping für DataTables Server-Side Sortierung
_DT_COLUMNS = [
    None,  # Index 0: Bulk-Select Checkbox
    # GEÄNDERT: Favorit-Spalte sortierbar gemacht (war None -> fiel in Default-Sort)
    'is_favorite',  # Index 1: gelber Stern
    # GEÄNDERT: Doku-Favorit-Spalte (roter Stern) direkt nach gelbem Stern
    'is_doc_favorite',  # Index 2: roter Stern
    # GEÄNDERT: ToDo 10 — Bestwert-Kriterium zwischen Stern und ID; sortierbar (JSON-Text)
    'best_criteria_json',  # Index 3: best_criteria
    # GEÄNDERT: Strategie-Spalte in Konzept + Iteration aufgeteilt; Konzept sortiert nach
    # Concept-Name, Iteration nach numerischer Iterations-Version
    'id', 'run_id', '__concept__', '__iteration__', 'symbol', 'timeframe',  # Index 4-9
    None, None,  # Index 10-11: Start/Ende (Sortierung via Run)
    'tp_stop', 'sl_stop', 'sharpe_ratio', 'sortino_ratio', 'max_drawdown_pct',  # Index 12-16
    'total_trades', 'win_rate_pct', 'profit_factor', 'total_return_pct',  # Index 17-20
    'end_value', None, None  # Index 21-23
]

# GEÄNDERT: Numerische Min/Max-Feld-Filter für die Results-Tabelle.
# Key = Query-Param-Präfix (z.B. win_rate_pct_min/_max), Value = ORM-Spalte.
_NUMERIC_FILTER_COLUMNS = {
    'win_rate_pct': BacktestResult.win_rate_pct,
    'total_return_pct': BacktestResult.total_return_pct,
    'sharpe_ratio': BacktestResult.sharpe_ratio,
    'profit_factor': BacktestResult.profit_factor,
    'total_trades': BacktestResult.total_trades,
    'max_drawdown_pct': BacktestResult.max_drawdown_pct,
}


@router.get('/results/dt')
def get_results_datatable(request: Request) -> dict:
    """Server-Side Processing Endpoint für DataTables."""
    params = request.query_params
    draw = int(params.get('draw', 1))
    start = int(params.get('start', 0))
    length = int(params.get('length', 25))
    search_value = params.get('search[value]', '').strip()

    # GEÄNDERT: ToDo 10 — Default-Sortierspalte um +1 verschoben (neue Badge-Spalte an Index 3);
    # 16 = max_drawdown_pct (wie zuvor 15)
    order_col_idx = int(params.get('order[0][column]', 16))
    order_dir = params.get('order[0][dir]', 'desc')

    # GEÄNDERT: Strategie-Filter in Konzept + Iteration getrennt (jeweils per ID);
    # Sonderwert 'none' = Results ohne zugeordnete Iteration (kein Konzept)
    concept_id_raw = params.get('concept_id', '') or None
    iteration_id_str = params.get('iteration_id', '') or None
    iteration_id = int(iteration_id_str) if iteration_id_str else None
    symbol = params.get('symbol', '') or None
    timeframe = params.get('timeframe', '') or None
    # GEÄNDERT: Size-Type-Filter (aus Result-Snapshot, kein Run-Feld)
    size_type = params.get('size_type', '') or None
    run_id_str = params.get('run_id', '') or None
    run_id = int(run_id_str) if run_id_str else None

    session = get_session()
    try:
        # GEÄNDERT: Ticket 11 — outer join auf Iterations/Concepts für sprechende Strategie-Spalte
        query = (
            session.query(BacktestResult, BacktestRun, StrategyIteration, StrategyConcept, IndicatorConfig)
            .join(BacktestRun, BacktestResult.run_id == BacktestRun.id)
            .outerjoin(StrategyIteration, BacktestRun.iteration_id == StrategyIteration.id)
            .outerjoin(StrategyConcept, StrategyIteration.concept_id == StrategyConcept.id)
            # GEÄNDERT: Indikator-Config (lose Verknüpfung über indicator_config_id) für
            # die Namens-Anzeige in der Iterations-Spalte. Gelöschte/fehlende Config -> NULL.
            .outerjoin(IndicatorConfig, BacktestRun.indicator_config_id == IndicatorConfig.id)
        )

        # GEÄNDERT: Run-Level-Filter (Konzept/Iteration/Symbol/Timeframe) werden NICHT
        # mehr als Join-Prädikat auf backtest_runs gehängt, sondern vorab zu konkreten
        # run_ids aufgelöst und als literale run_id-IN-Liste auf backtest_results gefiltert.
        # Grund: Nur bei LITERALEN run_ids wählt der Planner die Composite-Indizes
        # (run_id, metrik). Über das Join-Prädikat (oder eine Subquery) verschätzt er sich
        # wegen des LIMIT und scannt den Single-Column-Metrik-Index über die ganze Tabelle
        # (gemessen >11 s statt ms). 'none' = Results ohne zugeordnete Iteration.
        # GEÄNDERT: Alle Result-Level-Filter in einer Liste sammeln und sowohl auf die
        # Daten-Query (mit Join) als auch auf einen Join-freien count() anwenden. Der
        # 5er-Join wird fürs Zählen nicht gebraucht (jedes Result hat genau einen Run).
        result_conditions = []

        run_filter_active = bool(concept_id_raw or iteration_id or symbol or timeframe)
        if run_filter_active:
            rid_query = session.query(BacktestRun.id)
            if concept_id_raw == 'none':
                rid_query = rid_query.filter(BacktestRun.iteration_id.is_(None))
            elif concept_id_raw:
                rid_query = (
                    rid_query
                    .join(StrategyIteration, BacktestRun.iteration_id == StrategyIteration.id)
                    .filter(StrategyIteration.concept_id == int(concept_id_raw))
                )
            if iteration_id:
                rid_query = rid_query.filter(BacktestRun.iteration_id == iteration_id)
            if symbol:
                rid_query = rid_query.filter(BacktestRun.symbol == symbol)
            if timeframe:
                rid_query = rid_query.filter(BacktestRun.timeframe == timeframe)
            # Literale Python-ints in die IN-Liste -> Planner nutzt die Composite-Indizes.
            matching_run_ids = [row[0] for row in rid_query.all()]
            result_conditions.append(BacktestResult.run_id.in_(matching_run_ids))
        if run_id:
            result_conditions.append(BacktestResult.run_id == run_id)

        # GEÄNDERT: Size-Type-Filter als Result-Level-Bedingung auf den Snapshot-JSON-Pfad
        # (size_type lebt in full_config_snapshot_json['backtest_config'], nicht am Run).
        if size_type:
            result_conditions.append(
                func.json_extract_path_text(
                    BacktestResult.full_config_snapshot_json, 'backtest_config', 'size_type'
                ) == size_type
            )

        # GEÄNDERT: Numerische Min/Max-Feld-Filter anwenden (z.B. win_rate_pct_min=90)
        for field, column in _NUMERIC_FILTER_COLUMNS.items():
            min_raw = params.get(f'{field}_min', '').strip()
            max_raw = params.get(f'{field}_max', '').strip()
            if min_raw:
                try:
                    result_conditions.append(column >= float(min_raw))
                except ValueError:
                    pass
            if max_raw:
                try:
                    result_conditions.append(column <= float(max_raw))
                except ValueError:
                    pass

        query = query.filter(*result_conditions)

        # GEÄNDERT: records_total ohne Join zählen. Bei komplett ungefilterter Tabelle
        # die sofortige Planner-Schätzung (pg_class.reltuples) nehmen, statt 393k+ Zeilen
        # zu zählen (~2,5 s, wächst linear) - der "Showing X of Y"-Wert darf approximativ
        # sein. Sobald ein Filter greift, ist der exakte count() dank Index schnell.
        if not result_conditions:
            estimate = session.execute(
                text("SELECT reltuples::bigint FROM pg_class WHERE relname = 'backtest_results'")
            ).scalar()
            records_total = int(estimate or 0)
        else:
            records_total = (
                session.query(func.count(BacktestResult.id))
                .filter(*result_conditions)
                .scalar()
            )

        # GEÄNDERT: Zweiten count() nur bei gesetztem Suchtext - dann inkl. Join, weil die
        # Suche auf backtest_runs-Spalten (strategy_name/symbol/timeframe) zugreift. Ohne
        # Suche ist die gefilterte Menge identisch mit der Gesamtmenge.
        if search_value:
            search_pattern = f"%{search_value}%"
            search_condition = (
                (BacktestRun.strategy_name.like(search_pattern)) |
                (BacktestRun.symbol.like(search_pattern)) |
                (BacktestRun.timeframe.like(search_pattern)) |
                (cast(BacktestResult.id, String).like(search_pattern)) |
                (cast(BacktestResult.run_id, String).like(search_pattern))
            )
            query = query.filter(search_condition)
            records_filtered = (
                session.query(func.count(BacktestResult.id))
                .join(BacktestRun, BacktestResult.run_id == BacktestRun.id)
                .filter(*result_conditions)
                .filter(search_condition)
                .scalar()
            )
        else:
            records_filtered = records_total

        # Sortierung
        col_name = _DT_COLUMNS[order_col_idx] if order_col_idx < len(_DT_COLUMNS) else None
        if col_name == '__concept__':
            # GEÄNDERT: Konzept-Spalte nach Concept-Name sortieren. NULLS ans Ende.
            sort_col = StrategyConcept.name
            ordered = sort_col.desc() if order_dir == 'desc' else sort_col.asc()
            query = query.order_by(ordered.nullslast())
        elif col_name == '__iteration__':
            # GEÄNDERT: Iterations-Spalte nach numerischer Iterations-Version sortieren
            # (version ist Integer -> korrekte 2,3,32,42-Reihenfolge). NULLS ans Ende.
            sort_col = StrategyIteration.version
            ordered = sort_col.desc() if order_dir == 'desc' else sort_col.asc()
            query = query.order_by(ordered.nullslast())
        elif col_name == 'is_favorite':
            # GEÄNDERT: Favoriten gruppiert ans Ende/an den Anfang, innerhalb deterministisch
            # nach ID (sonst springen die Zeilen beim 5s-Auto-Reload).
            fav = BacktestResult.is_favorite
            primary = fav.desc() if order_dir == 'desc' else fav.asc()
            query = query.order_by(primary, BacktestResult.id.desc())
        elif col_name == 'is_doc_favorite':
            # GEÄNDERT: Doku-Favoriten analog zum gelben Stern sortieren
            doc_fav = BacktestResult.is_doc_favorite
            primary = doc_fav.desc() if order_dir == 'desc' else doc_fav.asc()
            query = query.order_by(primary, BacktestResult.id.desc())
        elif col_name:
            if col_name in ('strategy_name', 'symbol', 'timeframe'):
                sort_col = getattr(BacktestRun, col_name)
            elif col_name in ('tp_stop', 'sl_stop'):
                # GEÄNDERT: TP/SL sortierbar gemacht — die per-Result aufgelösten Stops liegen im
                # Snapshot-JSON (full_config_snapshot_json['backtest_config']); per
                # json_extract_path_text als Text ziehen und als Float sortieren. Alt-Results ohne
                # Snapshot -> NULL -> ans Ende (nullslast unten).
                sort_col = cast(
                    func.json_extract_path_text(
                        BacktestResult.full_config_snapshot_json, 'backtest_config', col_name
                    ),
                    Float,
                )
            elif col_name == 'best_criteria_json':
                # GEÄNDERT: Bestwert-Spalte sortierbar — die JSON-Liste der Kriterium-Keys als Text
                # sortieren (Results mit Kriterien gruppiert, ohne Kriterium ans Ende). NULLIF fängt
                # Bestandszeilen ab, die frueher als JSON-null (Text "null") statt SQL-NULL gespeichert
                # wurden, damit auch sie via nullslast ans Ende fallen.
                sort_col = func.nullif(cast(BacktestResult.best_criteria_json, Text), 'null')
            else:
                sort_col = getattr(BacktestResult, col_name, None)
            if sort_col is not None:
                # GEÄNDERT: NULLS (im Frontend als "-" angezeigt) immer ans Ende, egal ob
                # auf- oder absteigend. Sonst tauchen "-"-Werte bei DESC oben auf (PostgreSQL
                # legt NULLS bei DESC standardmäßig nach vorne).
                ordered = sort_col.desc() if order_dir == 'desc' else sort_col.asc()
                # GEÄNDERT: Deterministischer Tiebreaker bei Wertgleichstand der Sortierspalte.
                # Wertgleiche Parameter-Kombinationen (z.B. Raster-Dubletten) liefern sonst eine
                # willkürliche, nicht reproduzierbare Reihenfolge — die Bestwert-Auswahl kürt dann
                # mal das eine, mal das andere Result. Erst das risikoärmere Result bevorzugen
                # (geringster Drawdown = größter, weil negativ gespeichert), dann die ID als
                # final eindeutiger Anker.
                query = query.order_by(
                    ordered.nullslast(),
                    BacktestResult.max_drawdown_pct.desc().nullslast(),
                    BacktestResult.id.desc(),
                )
        else:
            query = query.order_by(BacktestResult.total_return_pct.desc().nullslast())

        rows = query.offset(start).limit(length).all()

        data = []
        for result, run, iteration, concept, ind_config in rows:
            # GEÄNDERT: Stops aus Result-Snapshot statt run-weitem portfolio (per Result)
            tp_stop, sl_stop = _result_stops(result)
            data.append({
                'id': result.id,
                'run_id': result.run_id,
                # GEÄNDERT: Ticket 15 — _json-Suffix
                'actual_params': result.actual_params_json,
                'total_return_pct': result.total_return_pct,
                'benchmark_return_pct': result.benchmark_return_pct,
                'sharpe_ratio': result.sharpe_ratio,
                'sortino_ratio': result.sortino_ratio,
                'max_drawdown_pct': result.max_drawdown_pct,
                'downside_risk': result.downside_risk,
                'total_trades': result.total_trades,
                'win_rate_pct': result.win_rate_pct,
                'profit_factor': result.profit_factor,
                'end_value': result.end_value,
                'is_favorite': bool(result.is_favorite),
                # GEÄNDERT: Doku-Favorit-Flag in Response mitliefern
                'is_doc_favorite': bool(result.is_doc_favorite),
                # GEÄNDERT: ToDo 10 — gewonnene Bestwert-Kriterien als Badge-Objekte {short, long}
                # (Frontend rendert Kürzel + Hover-Tooltip; Mapping bleibt serverseitig)
                'best_criteria': criteria_keys_to_badges(result.best_criteria_json),
                'metrics_level': result.metrics_level,
                'strategy_family': run.strategy_family,
                'strategy_name': run.strategy_name,
                # GEÄNDERT: Ticket 11 — sprechende Strategie-Felder aus Concept/Iteration
                'concept_name': concept.name if concept else None,
                # GEÄNDERT: Iterations-Version (Integer) + optionaler Name, keine PK-ID
                'iteration_version': iteration.version if iteration else None,
                'iteration_name': iteration.version_name if iteration else None,
                # GEÄNDERT: Name der verknüpften Indikator-Config (None wenn keine/gelöscht)
                'indicator_config_name': ind_config.name if ind_config else None,
                # GEÄNDERT: Alle aufgelösten Stops für den Iterations-Tooltip
                'stops': _result_stops_dict(result),
                # GEÄNDERT: Aufgelöste Indikator-Config (alle Eingabewerte je Indikator,
                # Ranges durch die konkreten Werte dieses Results ersetzt) für den Tooltip
                'resolved_indicators': _build_resolved_config(
                    run.indicators_config_json, result.actual_params_json or {}
                ) if run.indicators_config_json else None,
                'symbol': run.symbol,
                'exchange': run.exchange,
                'timeframe': run.timeframe,
                # GEÄNDERT: Size-Type aus dem Result-Snapshot (wie tp_stop/sl_stop)
                'size_type': ((result.full_config_snapshot_json or {}).get('backtest_config') or {}).get('size_type'),
                'start_date': run.start_date.isoformat() if run.start_date else None,
                'end_date': run.end_date.isoformat() if run.end_date else None,
                'tp_stop': tp_stop,
                'sl_stop': sl_stop,
            })

        return {
            'draw': draw,
            'recordsTotal': records_total,
            'recordsFiltered': records_filtered,
            'data': data
        }
    finally:
        session.close()


@router.get('/filters')
def get_filters() -> dict:
    """Verfügbare Filter-Werte aus den vorhandenen Runs."""
    session = get_session()
    try:
        # GEÄNDERT: Konzept und Iteration getrennt — nur solche mit vorhandenen Runs.
        # Iteration mit concept_id, damit das Frontend die Iterations-Liste je Konzept filtern kann.
        concept_rows = (
            session.query(StrategyConcept.id, StrategyConcept.name)
            .join(StrategyIteration, StrategyIteration.concept_id == StrategyConcept.id)
            .join(BacktestRun, BacktestRun.iteration_id == StrategyIteration.id)
            .distinct()
            .order_by(StrategyConcept.name.asc())
            .all()
        )
        concepts = [{'id': r.id, 'name': r.name} for r in concept_rows]

        iteration_rows = (
            session.query(
                StrategyIteration.id,
                StrategyIteration.concept_id,
                StrategyIteration.version,
                StrategyIteration.version_name,
            )
            .join(BacktestRun, BacktestRun.iteration_id == StrategyIteration.id)
            .distinct()
            # GEÄNDERT: nach Iterations-Version absteigend sortieren
            .order_by(StrategyIteration.version.desc())
            .all()
        )
        iterations = [
            {
                'id': r.id,  # Filter-Value (BacktestRun.iteration_id), nicht angezeigt
                'concept_id': r.concept_id,
                # GEÄNDERT: Iterations-Version (ohne Raute) voranstellen, optional mit Namen
                'label': f"{r.version}" + (f" {r.version_name}" if r.version_name else ""),
            }
            for r in iteration_rows
        ]

        # GEÄNDERT: Gibt es Results ohne zugeordnete Iteration (kein Konzept)?
        # Wenn ja, bietet das Frontend die Filter-Option "(ohne Konzept)" an.
        has_unassigned = (
            session.query(BacktestResult.id)
            .join(BacktestRun, BacktestResult.run_id == BacktestRun.id)
            .filter(BacktestRun.iteration_id.is_(None))
            .first()
            is not None
        )

        symbols = [r[0] for r in session.query(BacktestRun.symbol).distinct().all()]
        timeframes = [r[0] for r in session.query(BacktestRun.timeframe).distinct().all()]
        # GEÄNDERT: Size-Type-Filterwerte aus den vorhandenen Backtest-Configs (kleine Tabelle,
        # autoritative Quelle der genutzten Größenarten)
        size_types = [
            r[0] for r in session.query(BacktestConfig.size_type)
            .distinct().order_by(BacktestConfig.size_type.asc()).all()
        ]
        runs = [
            {'id': r.id, 'label': f"#{r.id} {r.strategy_name} {r.symbol} {r.timeframe}"}
            for r in session.query(BacktestRun).order_by(BacktestRun.id.desc()).all()
        ]
        return {
            'concepts': concepts,
            'iterations': iterations,
            'has_unassigned': has_unassigned,
            'symbols': symbols,
            'timeframes': timeframes,
            'size_types': size_types,
            'runs': runs,
        }
    finally:
        session.close()


@router.get('/results/{result_id}/ohlcv')
def get_ohlcv(result_id: int) -> dict:
    """OHLCV-Daten aus HDF5 für ein Result."""
    session = get_session()
    try:
        result = session.query(BacktestResult).filter(BacktestResult.id == result_id).first()
        if not result:
            raise HTTPException(status_code=404, detail="Result nicht gefunden")
        run = session.query(BacktestRun).filter(BacktestRun.id == result.run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Run nicht gefunden")

        symbol = run.symbol
        exchange = run.exchange
        timeframe = run.timeframe
        start_date = run.start_date.isoformat() if run.start_date else None
        end_date = run.end_date.isoformat() if run.end_date else None
    finally:
        session.close()

    data_path = os.getenv('PROJECT_ROOT', '.') + '/data/ohlc_data/'
    h5_file = os.path.join(data_path, f"ohlcv_{timeframe}_{exchange}.h5")

    if not os.path.exists(h5_file):
        raise HTTPException(status_code=404, detail=f"HDF5-Datei nicht gefunden: {h5_file}")

    store = pd.HDFStore(h5_file, 'r')
    try:
        if f'/{symbol}' not in store.keys():
            raise HTTPException(status_code=404, detail=f"Symbol {symbol} nicht in HDF5")
        df = store[f'/{symbol}']
    finally:
        store.close()

    if start_date:
        df = df[df.index >= start_date]
    if end_date:
        df = df[df.index <= end_date]

    candles = []
    for ts, row in df.iterrows():
        candles.append({
            'time': int(ts.timestamp()),
            'open': float(row['Open']),
            'high': float(row['High']),
            'low': float(row['Low']),
            'close': float(row['Close']),
        })

    return {'symbol': symbol, 'timeframe': timeframe, 'candles': candles}


@router.get('/results/{result_id}/trades')
def get_trades(result_id: int) -> dict:
    """Trades eines Results aus der DB."""
    session = get_session()
    try:
        result = session.query(BacktestResult).filter(BacktestResult.id == result_id).first()
        if not result:
            raise HTTPException(status_code=404, detail="Result nicht gefunden")

        # GEÄNDERT: Stops aus Result-Snapshot statt run-weitem portfolio (per Result)
        tp_stop, sl_stop = _result_stops(result)

        trades = session.query(BacktestTrade).filter(
            BacktestTrade.result_id == result_id
        ).order_by(BacktestTrade.entry_index).all()

        # Stop-Type pro Order-ID nachschlagen (für Exit-Typ: TP, SL, TD)
        orders = session.query(BacktestOrder).filter(
            BacktestOrder.result_id == result_id
        ).all()
        order_stop_types = {o.order_id: o.stop_type for o in orders}

        items = []
        for t in trades:
            exit_stop_type = order_stop_types.get(t.exit_order_id, '') or ''
            trade_data = {
                'exit_trade_id': t.exit_trade_id,
                'position_id': t.position_id,
                'direction': t.direction,
                'status': t.status,
                'entry_time': int(t.entry_index.timestamp()) if t.entry_index else None,
                'entry_price': t.avg_entry_price,
                'entry_order_id': t.entry_order_id,
                'exit_time': int(t.exit_index.timestamp()) if t.exit_index else None,
                'exit_price': t.avg_exit_price,
                'exit_order_id': t.exit_order_id,
                'exit_stop_type': exit_stop_type,
                'pnl': t.pnl,
                'return_pct': t.return_pct,
                'size': t.size,
            }
            if t.avg_entry_price and tp_stop:
                trade_data['tp_price'] = t.avg_entry_price * (1 + tp_stop)
            if t.avg_entry_price and sl_stop:
                trade_data['sl_price'] = t.avg_entry_price * (1 - sl_stop)
            items.append(trade_data)

        return {
            'result_id': result_id,
            'total': len(items),
            'tp_stop': tp_stop,
            'sl_stop': sl_stop,
            'trades': items,
        }
    finally:
        session.close()


@router.get('/results/{result_id}/orders')
def get_orders(result_id: int) -> dict:
    """Orders eines Results."""
    session = get_session()
    try:
        orders = session.query(BacktestOrder).filter(
            BacktestOrder.result_id == result_id
        ).order_by(BacktestOrder.order_id).all()
        items = []
        for o in orders:
            items.append({
                'order_id': o.order_id,
                'signal_index': int(o.signal_index.timestamp()) if o.signal_index else None,
                'creation_index': int(o.creation_index.timestamp()) if o.creation_index else None,
                'fill_index': int(o.fill_index.timestamp()) if o.fill_index else None,
                'side': o.side,
                'size': o.size,
                'price': o.price,
                'fees': o.fees,
                'type': o.type,
                'stop_type': o.stop_type,
            })
        return {'result_id': result_id, 'total': len(items), 'orders': items}
    finally:
        session.close()


@router.get('/results/{result_id}/positions')
def get_positions(result_id: int) -> dict:
    """Positions eines Results."""
    session = get_session()
    try:
        positions = session.query(BacktestPosition).filter(
            BacktestPosition.result_id == result_id
        ).order_by(BacktestPosition.position_id).all()
        items = []
        for p in positions:
            items.append({
                'position_id': p.position_id,
                'direction': p.direction,
                'status': p.status,
                'entry_time': int(p.entry_index.timestamp()) if p.entry_index else None,
                'exit_time': int(p.exit_index.timestamp()) if p.exit_index else None,
                'avg_entry_price': p.avg_entry_price,
                'avg_exit_price': p.avg_exit_price,
                'size': p.size,
                'pnl': p.pnl,
                'return_pct': p.return_pct,
            })
        return {'result_id': result_id, 'total': len(items), 'positions': items}
    finally:
        session.close()


def _delete_result_details(session, result_ids: list[int]) -> None:
    """Löscht alle Detail-Daten (Equity, Trades, Orders, Positions, Indikatoren) für die gegebenen Result-IDs.

    Löscht in Batches um Lock-Timeouts bei großen Datenmengen zu vermeiden. Committet nicht
    selbst — der Aufrufer steuert die Transaktion (der 'Alle löschen'-Job committet pro Batch).
    """
    if not result_ids:
        return

    # GEÄNDERT: Tabellen-Namen auf Ticket-13-Schema aktualisiert (backtest_result_*)
    tables = ['backtest_result_indicators', 'backtest_result_equity', 'backtest_result_trades',
              'backtest_result_orders', 'backtest_result_positions', 'backtest_result_params', 'backtest_jobs']
    # GEÄNDERT: Batch-Größe auf _DELETE_BATCH_SIZE erhöht (Ticket 08)
    for i in range(0, len(result_ids), _DELETE_BATCH_SIZE):
        chunk = result_ids[i:i + _DELETE_BATCH_SIZE]
        ids_str = ','.join(str(rid) for rid in chunk)
        for table in tables:
            session.execute(text(f"DELETE FROM {table} WHERE result_id IN ({ids_str})"))
        session.flush()


@router.delete('/results/{result_id}')
def delete_result(result_id: int) -> JSONResponse:
    """Löscht ein einzelnes Result mit allen Detail-Daten."""
    session = get_session()
    run_deleted = False
    try:
        result = session.query(BacktestResult).filter(BacktestResult.id == result_id).first()
        if not result:
            raise HTTPException(status_code=404, detail="Result nicht gefunden")
        run_id = result.run_id

        _delete_result_details(session, [result_id])
        session.delete(result)
        session.flush()

        remaining = session.query(BacktestResult).filter(BacktestResult.run_id == run_id).count()
        if remaining == 0:
            run = session.query(BacktestRun).filter(BacktestRun.id == run_id).first()
            if run:
                session.delete(run)
                run_deleted = True

        session.commit()
    finally:
        session.close()

    return JSONResponse({'status': 'ok', 'deleted': result_id, 'run_deleted': run_deleted})


def _stop_run_jobs(run_ids: Optional[set] = None) -> None:
    """Bricht wartende UND laufende RQ-Backtest-Berechnungen ab.

    run_ids=None bedeutet alle Backtest-Berechnungen (für 'Alle löschen'); sonst
    nur die Jobs der angegebenen Run-IDs. Wartende Jobs werden aus der Queue
    entfernt; bereits GESTARTETE Jobs erhalten zusätzlich ein Stop-Command (SIGINT
    ans Worker-Horse) -- ohne das rechnet der Worker den gelöschten Run sinnlos zu
    Ende und blockiert die Worker-Kapazität für wartende Runs.

    GEÄNDERT: Greift ausschließlich echte Backtest-Berechnungen ab (func_name ==
    BACKTEST_RUN_JOB). Die Lösch-Jobs (delete_all_results_job/delete_all_runs_job)
    laufen in derselben Queue und dürfen NICHT mitgestoppt werden -- sonst killt
    ein 'Alle Runs löschen' einen parallel laufenden Results-Lösch-Job (und früher
    via q.empty() auch sich selbst).
    """
    redis_conn = get_redis_connection()
    q = Queue(BACKTEST_QUEUE_NAME, connection=redis_conn)

    def _job_run_id(job: RqJob):
        return job.kwargs.get('run_id') or (job.args[0] if job.args else None)

    def _is_backtest_job(job: RqJob) -> bool:
        return job.func_name == BACKTEST_RUN_JOB

    # Wartende Backtest-Berechnungen aus der Queue entfernen (Lösch-Jobs bleiben)
    for job in q.jobs:
        if not _is_backtest_job(job):
            continue
        if run_ids is None or _job_run_id(job) in run_ids:
            job.cancel()

    # Laufende Jobs stoppen (q.jobs enthält nur wartende, nicht gestartete Jobs)
    for job_id in StartedJobRegistry(queue=q).get_job_ids():
        try:
            job = RqJob.fetch(job_id, connection=redis_conn)
        except Exception:
            # Job zwischen get_job_ids und fetch beendet/entfernt -- überspringen
            continue
        if not _is_backtest_job(job):
            continue
        if run_ids is None or _job_run_id(job) in run_ids:
            try:
                send_stop_job_command(redis_conn, job_id)
            except Exception:
                # Job genau jetzt beendet -> nicht mehr stoppbar, ist ok
                pass


@router.delete('/runs/{run_id}')
def delete_run(run_id: int) -> JSONResponse:
    """Löscht einen Run mit allen Results und Detail-Daten."""
    session = get_session()
    try:
        run = session.query(BacktestRun).filter(BacktestRun.id == run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Run nicht gefunden")

        result_ids = [r.id for r in session.query(BacktestResult.id).filter(
            BacktestResult.run_id == run_id
        ).all()]

        _delete_result_details(session, result_ids)

        deleted_count = session.query(BacktestResult).filter(
            BacktestResult.run_id == run_id
        ).delete(synchronize_session='fetch')

        session.delete(run)
        session.commit()
    finally:
        session.close()

    # RQ-Job für diesen Run abbrechen (wartend UND laufend)
    _stop_run_jobs({run_id})

    return JSONResponse({'status': 'ok', 'deleted_run': run_id, 'deleted_results': deleted_count})


@router.post('/runs/{run_id}/restart')
def restart_run(run_id: int) -> JSONResponse:
    """Startet einen Run neu: löscht bestehende Results, setzt Status zurück, reiht Job ein."""
    session = get_session()
    try:
        run = session.query(BacktestRun).filter(BacktestRun.id == run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Run nicht gefunden")

        # Bestehende Results und Detail-Daten löschen
        result_ids = [r.id for r in session.query(BacktestResult.id).filter(
            BacktestResult.run_id == run_id
        ).all()]
        if result_ids:
            _delete_result_details(session, result_ids)
            session.query(BacktestResult).filter(BacktestResult.run_id == run_id).delete(synchronize_session='fetch')

        # Run zurücksetzen (queued — Worker setzt auf running)
        run.status = 'queued'
        run.error_message = None
        # GEÄNDERT: Kombinationen-Vorabschätzung analog zum Create-Pfad neu berechnen,
        # statt hart auf 0 zu setzen. Sonst zeigt die Runs-Tabelle beim Rerun 0, bis der
        # Lauf erfolgreich durch ist (und bei Fehlschlag dauerhaft). Gleiche Zähl-Wahrheit
        # wie create_backtest_run (_count_combinations -> count_total_combos).
        run.n_combinations = _count_combinations(run.indicators_config_json)
        run.completed_at = None
        run.created_at = datetime.now()
        session.commit()
    finally:
        session.close()

    # Alte Jobs für diesen Run abbrechen (wartend UND laufend), bevor neu eingereiht wird
    _stop_run_jobs({run_id})

    # Neuen Job einreihen
    q = Queue(BACKTEST_QUEUE_NAME, connection=get_redis_connection())
    q.enqueue('services.api.worker_tasks.run_backtest_job', run_id=run_id, job_timeout=BACKTEST_JOB_TIMEOUT)

    return JSONResponse({'status': 'ok', 'run_id': run_id, 'message': 'Run neugestartet'})


@router.delete('/runs')
def delete_all_runs() -> JSONResponse:
    """Stößt das Löschen aller Runs/Results (außer Favoriten) als Hintergrund-Job an.

    GEÄNDERT: Läuft jetzt asynchron über RQ — analog zu DELETE /results, damit die UI
    nicht minutenlang blockiert und eine Fortschrittsanzeige bekommt. Die Löschmenge
    ist identisch zum Results-Job (non-fav Results + verwaiste Runs); zusätzlich
    stoppt der Job laufende Backtest-Berechnungen. Fortschritt über
    GET /runs/delete-status/{job_id}.

    Runs, die mindestens ein favoritisiertes Result enthalten, bleiben mit ihren
    Favoriten erhalten; nicht-favoritisierte Results in solchen Runs werden entfernt.
    """
    q = Queue(BACKTEST_QUEUE_NAME, connection=get_redis_connection())
    rq_job = q.enqueue(DELETE_ALL_RUNS_JOB, job_timeout=3600)
    return JSONResponse({'status': 'queued', 'job_id': rq_job.id}, status_code=202)


@router.post('/runs/bulk-delete')
def bulk_delete_runs(payload: dict = Body(...)) -> JSONResponse:
    """Löscht mehrere Runs in einer Operation mit allen Results und Detail-Daten.

    Erwartet Body: {"ids": [1, 2, 3]}. Favoriten-Schutz wird hier NICHT angewendet —
    die UI bestimmt die Auswahl explizit. Reduziert Roundtrips und Lock-Druck
    gegenüber Einzel-Löschungen bei großen Listen.
    """
    raw_ids = payload.get('ids') or []
    try:
        run_ids = [int(x) for x in raw_ids]
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Ungültige IDs")
    if not run_ids:
        return JSONResponse({'status': 'ok', 'deleted_runs': 0, 'deleted_results': 0})

    session = get_session()
    try:
        existing = [r.id for r in session.query(BacktestRun.id).filter(BacktestRun.id.in_(run_ids)).all()]
        if not existing:
            return JSONResponse({'status': 'ok', 'deleted_runs': 0, 'deleted_results': 0})

        result_ids = [r.id for r in session.query(BacktestResult.id).filter(
            BacktestResult.run_id.in_(existing)
        ).all()]

        _delete_result_details(session, result_ids)

        deleted_results = session.query(BacktestResult).filter(
            BacktestResult.run_id.in_(existing)
        ).delete(synchronize_session='fetch')

        deleted_runs = session.query(BacktestRun).filter(
            BacktestRun.id.in_(existing)
        ).delete(synchronize_session='fetch')

        session.commit()
    finally:
        session.close()

    # Zugehörige RQ-Jobs abbrechen (wartend UND laufend)
    _stop_run_jobs(set(existing))

    return JSONResponse({'status': 'ok', 'deleted_runs': deleted_runs, 'deleted_results': deleted_results})


@router.post('/results/bulk-delete')
def bulk_delete_results(payload: dict = Body(...)) -> JSONResponse:
    """Löscht mehrere Results in einer Operation, inkl. Detail-Daten.

    Erwartet Body: {"ids": [1, 2, 3]}. Verwaiste Runs (ohne verbleibende Results)
    werden ebenfalls entfernt. Favoriten-Schutz wird hier NICHT angewendet —
    die UI bestimmt die Auswahl explizit.
    """
    raw_ids = payload.get('ids') or []
    try:
        result_ids = [int(x) for x in raw_ids]
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Ungültige IDs")
    if not result_ids:
        return JSONResponse({'status': 'ok', 'deleted_results': 0, 'deleted_runs': 0})

    session = get_session()
    try:
        existing = [r.id for r in session.query(BacktestResult.id).filter(
            BacktestResult.id.in_(result_ids)
        ).all()]
        if not existing:
            return JSONResponse({'status': 'ok', 'deleted_results': 0, 'deleted_runs': 0})

        _delete_result_details(session, existing)

        deleted_results = session.query(BacktestResult).filter(
            BacktestResult.id.in_(existing)
        ).delete(synchronize_session='fetch')

        orphan_result = session.execute(text(
            "DELETE FROM backtest_runs WHERE id NOT IN (SELECT DISTINCT run_id FROM backtest_results)"
        ))
        deleted_runs = orphan_result.rowcount or 0

        session.commit()
    finally:
        session.close()

    return JSONResponse({'status': 'ok', 'deleted_results': deleted_results, 'deleted_runs': deleted_runs})


@router.put('/runs/{run_id}/remarks')
def update_run_remarks(run_id: int, body: dict) -> JSONResponse:
    """Aktualisiert die Bemerkung eines Runs."""
    session = get_session()
    try:
        run = session.query(BacktestRun).filter(BacktestRun.id == run_id).first()
        if not run:
            return JSONResponse({'error': f'Run #{run_id} nicht gefunden'}, status_code=404)
        run.remarks = body.get('remarks')
        session.commit()
    finally:
        session.close()

    return JSONResponse({'status': 'ok', 'run_id': run_id})


# Lösch-Job-Typen → (kind fürs Frontend, menschenlesbares Label für den Toast).
# Eine Wahrheit für den globalen Lösch-Job-Indikator (base.html).
_DELETE_JOB_KINDS = {
    DELETE_ALL_RESULTS_JOB: ('results', 'Results'),
    DELETE_ALL_RUNS_JOB: ('runs', 'Runs'),
}


def _collect_active_delete_jobs() -> list:
    """Sammelt alle aktiven (wartenden ODER laufenden) Bulk-Delete-Jobs aus RQ/Redis.

    Speist den globalen Lösch-Job-Toast: solange hier ein Job auftaucht, zeigt jede
    Maske den Fortschritt an. Da die Job-IDs nur in Redis leben (nicht im Client),
    ist das auch der Resume-Mechanismus nach einem Seiten-Reload.

    Returns:
        Liste von Dicts {job_id, kind, label, status, progress?} — eines pro
        aktivem Results-/Runs-Lösch-Job.
    """
    redis_conn = get_redis_connection()
    q = Queue(BACKTEST_QUEUE_NAME, connection=redis_conn)

    jobs = []
    # Wartende (queued) und bereits gestartete Jobs durchsuchen
    candidate_ids = list(q.job_ids) + list(StartedJobRegistry(queue=q).get_job_ids())
    for job_id in candidate_ids:
        try:
            job = RqJob.fetch(job_id, connection=redis_conn)
        except Exception:
            # Job zwischen get_ids und fetch beendet/entfernt — überspringen
            continue
        kind_label = _DELETE_JOB_KINDS.get(job.func_name)
        if kind_label is None:
            continue
        if job.get_status() not in ('queued', 'started', 'deferred'):
            continue
        kind, label = kind_label
        entry: dict = {'job_id': job_id, 'kind': kind, 'label': label, 'status': job.get_status()}
        progress = (job.meta or {}).get('progress')
        if progress is not None:
            entry['progress'] = progress
        jobs.append(entry)

    return jobs


@router.delete('/results')
def delete_all_results() -> JSONResponse:
    """Stößt das Löschen aller Results (außer Favoriten) als Hintergrund-Job an.

    GEÄNDERT (Ticket 45): Läuft asynchron über RQ, damit die UI nicht minutenlang
    blockiert — das Löschen über die TimescaleDB-Hypertables ist teuer. Die eigentliche
    Lösch-Logik liegt in worker_tasks.delete_all_results_job; der Fortschritt wird über
    den globalen Lösch-Job-Toast (GET /delete-jobs/active) angezeigt.
    """
    q = Queue(BACKTEST_QUEUE_NAME, connection=get_redis_connection())
    rq_job = q.enqueue(DELETE_ALL_RESULTS_JOB, job_timeout=3600)
    return JSONResponse({'status': 'queued', 'job_id': rq_job.id}, status_code=202)


@router.get('/delete-jobs/active')
def delete_jobs_active() -> JSONResponse:
    """Liefert alle aktiven Lösch-Jobs (Results + Runs) für den globalen Toast.

    Jede Maske pollt diesen Endpunkt und zeigt den Fortschritt seitenübergreifend
    an, solange ein Job läuft. Dient zugleich als Resume nach Seiten-Reload.
    """
    return JSONResponse({'jobs': _collect_active_delete_jobs()})


@router.post('/delete-jobs/{job_id}/cancel')
def cancel_delete_job(job_id: str) -> JSONResponse:
    """Bricht einen laufenden oder wartenden Lösch-Job ab.

    Wartend (queued) -> aus der Queue genommen; laufend (started) -> Stop-Command
    (SIGINT ans Worker-Horse), das die Löschung mitten im Lauf beendet. Bereits
    committete Batches (Results inkl. Detailzeilen) bleiben gelöscht; nur evtl.
    verwaiste Runs werden erst beim nächsten vollen Lauf idempotent mitgeräumt.
    """
    redis_conn = get_redis_connection()
    try:
        rq_job = RqJob.fetch(job_id, connection=redis_conn)
    except Exception:
        # Job-TTL abgelaufen oder unbekannte ID — aus Frontend-Sicht bereits weg
        return JSONResponse({'status': 'unknown', 'job_id': job_id}, status_code=404)

    # Nur echte Lösch-Jobs abbrechen — keine Backtest-Berechnungen über diesen Weg
    if rq_job.func_name not in _DELETE_JOB_KINDS:
        raise HTTPException(status_code=400, detail="Kein Lösch-Job")

    status = rq_job.get_status()
    if status == 'started':
        try:
            send_stop_job_command(redis_conn, job_id)
        except Exception:
            # Job genau jetzt beendet -> nicht mehr stoppbar, ist ok
            pass
    else:
        # wartend/deferred — aus der Queue nehmen
        rq_job.cancel()

    return JSONResponse({'status': 'cancelled', 'job_id': job_id})


@router.post('/results/{result_id}/favorite')
def toggle_favorite(result_id: int) -> JSONResponse:
    """Favorit-Status eines Results umschalten (Toggle)."""
    session = get_session()
    try:
        result = session.query(BacktestResult).filter(BacktestResult.id == result_id).first()
        if not result:
            raise HTTPException(status_code=404, detail="Result nicht gefunden")
        result.is_favorite = 0 if result.is_favorite else 1
        session.commit()
        return JSONResponse({'status': 'ok', 'id': result_id, 'is_favorite': bool(result.is_favorite)})
    finally:
        session.close()


# GEÄNDERT: Doku-Favorit-Toggle (roter Stern, unabhängig vom gelben Favorit)
@router.post('/results/{result_id}/doc_favorite')
def toggle_doc_favorite(result_id: int) -> JSONResponse:
    """Doku-Favorit-Status eines Results umschalten (Toggle).

    Manueller Weg (Frontend-Stern): setzt keine Bestwert-Kriterien. Beim Ausschalten
    werden vorhandene best_criteria_json mit-geleert — Flag und Kriterien sind gekoppelt,
    kein verwaistes Label ohne Stern.
    """
    session = get_session()
    try:
        result = session.query(BacktestResult).filter(BacktestResult.id == result_id).first()
        if not result:
            raise HTTPException(status_code=404, detail="Result nicht gefunden")
        result.is_doc_favorite = 0 if result.is_doc_favorite else 1
        # Kopplung: beim Ausschalten die gewonnenen Kriterien mit-leeren
        if not result.is_doc_favorite:
            result.best_criteria_json = None
        session.commit()
        return JSONResponse({'status': 'ok', 'id': result_id, 'is_doc_favorite': bool(result.is_doc_favorite)})
    finally:
        session.close()


# GEÄNDERT: ToDo 10 — idempotentes Setzen von rotem Stern + gewonnenen Bestwert-Kriterien.
# Anders als der Toggle schaltet dieser Weg den Stern nie AUS und schreibt die Kriterium-Keys
# auch dann, wenn der Stern bereits gesetzt ist (run-bestwerte markiert idempotent). Genutzt
# von der Toolbox (run-bestwerte); der manuelle Frontend-Stern bleibt der reine Toggle oben.
@router.post('/results/{result_id}/doc_favorite/mark')
def mark_doc_favorite_criteria(result_id: int, body: dict = Body(default=None)) -> JSONResponse:
    """Setzt den roten Stern und die gewonnenen Bestwert-Kriterien (idempotent).

    Body: {"criteria": ["max_return", "sharpe_band", ...]} — Liste stabiler Keys aus
    best_criteria_labels.VALID_CRITERIA_KEYS. Unbekannte Keys -> 400. Der Stern wird
    gesetzt (nie ausgeschaltet), die Kriterien werden geschrieben/ersetzt.
    """
    from services.api.utils.best_criteria_labels import VALID_CRITERIA_KEYS

    payload = body or {}
    criteria = payload.get('criteria') or []
    if not isinstance(criteria, list):
        return JSONResponse({'status': 'error', 'error': 'criteria muss eine Liste von Keys sein'}, status_code=400)
    unknown = [k for k in criteria if k not in VALID_CRITERIA_KEYS]
    if unknown:
        return JSONResponse(
            {'status': 'error', 'error': f'Unbekannte Kriterium-Keys: {unknown}. Erlaubt: {sorted(VALID_CRITERIA_KEYS)}'},
            status_code=400,
        )
    session = get_session()
    try:
        result = session.query(BacktestResult).filter(BacktestResult.id == result_id).first()
        if not result:
            raise HTTPException(status_code=404, detail="Result nicht gefunden")
        result.is_doc_favorite = 1
        # Keys deduplizieren, kanonische Reihenfolge egal (Anzeige mappt selbst)
        result.best_criteria_json = list(dict.fromkeys(criteria)) if criteria else None
        session.commit()
        return JSONResponse({
            'status': 'ok', 'id': result_id,
            'is_doc_favorite': True,
            'best_criteria': result.best_criteria_json,
        })
    finally:
        session.close()


@router.get('/results/{result_id}/chart-data')
def get_chart_data(result_id: int) -> dict:
    """Equity-Kurve und Indikatoren eines Results aus der DB.

    Wenn keine Equity-Daten vorhanden sind (Multi-Kombination-Run),
    wird ein einzelner Backtest nachberechnet und die Daten gespeichert.
    Verwendet Raw-SQL statt ORM für Performance (>20.000 Zeilen).
    """

    # Prüfen ob Equity vorhanden — schneller COUNT statt alle Zeilen laden
    engine = get_engine()
    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM backtest_result_equity WHERE result_id = :rid"),
            {"rid": result_id}
        ).scalar()

    # Keine Equity vorhanden — Recompute ausführen
    recomputed = False
    if count == 0:
        recomputed = True

        success = recompute_single_result(result_id)
        if not success:
            return {'equity': [], 'indicators': {}, 'recomputed': True}

    # Raw-SQL für Equity und Indikatoren (vermeidet ORM-Overhead)
    with engine.connect() as conn:
        # Equity
        equity_rows = conn.execute(
            text("SELECT EXTRACT(EPOCH FROM timestamp)::int AS ts, value FROM backtest_result_equity WHERE result_id = :rid ORDER BY timestamp"),
            {"rid": result_id}
        ).fetchall()
        equity = [{'time': int(r.ts), 'value': r.value} for r in equity_rows]

        # Drawdown-Perioden aus der Equity-Kurve ableiten.
        # Eine Periode startet am Timestamp des letzten Peaks und endet entweder
        # am Recovery-Zeitpunkt (equity erreicht wieder Peak-Level) oder am
        # letzten Datenpunkt (aktiver, nicht erholter Drawdown).
        drawdown_periods: list = []
        if equity:
            peak_val = equity[0]['value']
            peak_time = equity[0]['time']
            in_dd = False
            valley_val = peak_val
            valley_time = peak_time
            dd_peak_time = peak_time
            dd_peak_val = peak_val
            for pt in equity[1:]:
                v = pt['value']
                if v is None:
                    continue
                if not in_dd:
                    if v < peak_val:
                        in_dd = True
                        dd_peak_time = peak_time
                        dd_peak_val = peak_val
                        valley_val = v
                        valley_time = pt['time']
                    else:
                        peak_val = v
                        peak_time = pt['time']
                else:
                    if v < valley_val:
                        valley_val = v
                        valley_time = pt['time']
                    if v >= dd_peak_val:
                        dd_pct = 0.0 if dd_peak_val == 0 else (valley_val - dd_peak_val) / dd_peak_val * 100.0
                        drawdown_periods.append({
                            'start': dd_peak_time,
                            'valley': valley_time,
                            'end': pt['time'],
                            'status': 'recovered',
                            'dd_pct': dd_pct,
                        })
                        in_dd = False
                        peak_val = v
                        peak_time = pt['time']
            if in_dd:
                dd_pct = 0.0 if dd_peak_val == 0 else (valley_val - dd_peak_val) / dd_peak_val * 100.0
                drawdown_periods.append({
                    'start': dd_peak_time,
                    'valley': valley_time,
                    'end': equity[-1]['time'],
                    'status': 'active',
                    'dd_pct': dd_pct,
                })

        # Indikatoren
        ind_rows = conn.execute(
            text("SELECT indicator_name, indicator_output, EXTRACT(EPOCH FROM timestamp)::int AS ts, value FROM backtest_result_indicators WHERE result_id = :rid ORDER BY timestamp"),
            {"rid": result_id}
        ).fetchall()

        # GEÄNDERT: K1 — Indikator-Typen aus der Run-Config laden, um beim Aufbereiten
        # auf den Indikator-TYP statt auf den hartverdrahteten Instanz-Namen zu dispatchen.
        cfg_row = conn.execute(
            text("SELECT r.indicators_config_json AS cfg FROM backtest_runs r "
                 "JOIN backtest_results br ON br.run_id = r.id WHERE br.id = :rid"),
            {"rid": result_id}
        ).fetchone()

    # Indikator-Config zu name -> normalisiertem Typ ('vbt:SUPERTREND' -> 'supertrend')
    ind_config = cfg_row.cfg if cfg_row else None
    if isinstance(ind_config, str):
        try:
            ind_config = json.loads(ind_config)
        except Exception:
            ind_config = {}
    if not isinstance(ind_config, dict):
        ind_config = {}
    ind_type_map = {
        name: str(c.get('indicator', '')).split(':')[-1].lower()
        for name, c in ind_config.items() if isinstance(c, dict)
    }

    # Nach indicator_name + indicator_output gruppieren
    ind_raw: dict[str, dict[str, list]] = {}
    for r in ind_rows:
        ind_raw.setdefault(r.indicator_name, {}).setdefault(r.indicator_output, []).append({
            'time': int(r.ts), 'value': r.value,
        })

    # Für das Frontend aufbereiten
    indicators: dict = {}
    for ind_name, outputs in ind_raw.items():
        # GEÄNDERT: K1 — Dispatch auf den Indikator-TYP statt auf den Instanz-Namen
        if ind_type_map.get(ind_name) == 'supertrend':
            # trend + direction zusammenführen
            trend_data = outputs.get('trend', [])
            direction_data = outputs.get('direction', [])
            dir_map = {d['time']: d['value'] for d in direction_data}
            indicators[ind_name] = [
                {'time': p['time'], 'value': p['value'], 'direction': dir_map.get(p['time'], 0.0)}
                for p in trend_data
            ]
        else:
            if 'result' in outputs:
                indicators[ind_name] = outputs['result']

    return {
        'equity': equity,
        'drawdown_periods': drawdown_periods,
        'indicators': indicators,
        'recomputed': recomputed,
    }


@router.get('/results/{result_id}/stats')
def get_stats(result_id: int) -> dict:
    """Stats eines Results aus den gespeicherten Metriken."""
    session = get_session()
    try:
        result = session.query(BacktestResult).filter(BacktestResult.id == result_id).first()
        if not result:
            raise HTTPException(status_code=404, detail="Result nicht gefunden")

        stats = {
            'Start Value': result.start_value,
            'End Value': result.end_value,
            'Total Return [%]': result.total_return_pct,
            'Benchmark Return [%]': result.benchmark_return_pct,
            'Total Orders': result.total_orders,
            'Total Trades': result.total_trades,
            'Win Rate [%]': result.win_rate_pct,
            'Best Trade [%]': result.best_trade_pct,
            'Profit Factor': result.profit_factor,
            'Worst Trade [%]': result.worst_trade_pct,
            'Max Drawdown [%]': result.max_drawdown_pct,
            'Avg Losing Trade [%]': result.avg_losing_trade_pct,
            'Avg Winning Trade [%]': result.avg_winning_trade_pct,
            'Max Drawdown Duration': result.max_drawdown_duration,
            'Max Value': result.max_value,
            'Min Value': result.min_value,
            'Expectancy': result.expectancy,
            'Omega Ratio': result.omega_ratio,
            'Calmar Ratio': result.calmar_ratio,
            'Sharpe Ratio': result.sharpe_ratio,
            'Sortino Ratio': result.sortino_ratio,
            'Total Duration': result.total_duration,
            'Total Fees Paid': result.total_fees_paid,
            'Position Coverage [%]': result.position_coverage_pct,
            'Max Gross Exposure [%]': result.max_gross_exposure_pct,
            'Avg Losing Trade Duration': result.avg_losing_trade_duration,
            'Avg Winning Trade Duration': result.avg_winning_trade_duration,
            'Start Index': result.start_index.isoformat() if result.start_index else None,
            'End Index': result.end_index.isoformat() if result.end_index else None,
            # GEÄNDERT: Neue Analyse-Metriken
            'Annualized Return [%]': result.annualized_return,
            'Annualized Volatility [%]': result.annualized_volatility,
            'Downside Risk [%]': result.downside_risk,
            'SQN': result.sqn,
            'Edge Ratio': result.edge_ratio,
            'Deflated Sharpe Ratio': result.deflated_sharpe_ratio,
            'Tail Ratio': result.tail_ratio,
            'Value at Risk': result.value_at_risk,
            'Conditional VaR': result.cond_value_at_risk,
            'Alpha': result.alpha,
            'Beta': result.beta,
            'Information Ratio': result.information_ratio,
        }
        return {'result_id': result_id, 'stats': stats, 'metrics_level': result.metrics_level}
    finally:
        session.close()


# ========================================================================
# Full-Metriken (Stufe 3)
# ========================================================================

@router.post('/results/{result_id}/full-metrics')
def start_full_metrics(result_id: int) -> dict:
    """Startet Berechnung der Full-Metriken als Hintergrund-Job.

    Stufe 3: tail_ratio, VaR, CVaR, alpha, beta, information_ratio,
    deflated_sharpe_ratio etc. — zu langsam für Massen-Backtest.
    """
    session = get_session()
    try:
        result = session.query(BacktestResult).filter(BacktestResult.id == result_id).first()
        if not result:
            raise HTTPException(status_code=404, detail="Result nicht gefunden")
        if result.metrics_level == 'full':
            return {'result_id': result_id, 'status': 'already_complete'}
    finally:
        session.close()

    # Job in Recompute-Queue einreihen
    q = Queue(RECOMPUTE_QUEUE_NAME, connection=get_redis_connection())
    rq_job = q.enqueue(
        'services.api.worker_tasks.run_full_metrics_job',
        result_id,
        job_timeout=600,
    )

    return {'result_id': result_id, 'status': 'queued', 'job_id': rq_job.id}


@router.get('/results/{result_id}/metrics-level')
def get_metrics_level(result_id: int) -> dict:
    """Gibt die aktuelle Berechnungsstufe eines Results zurück."""
    session = get_session()
    try:
        result = session.query(BacktestResult).filter(BacktestResult.id == result_id).first()
        if not result:
            raise HTTPException(status_code=404, detail="Result nicht gefunden")
        return {'result_id': result_id, 'metrics_level': result.metrics_level}
    finally:
        session.close()


# ========================================================================
# Analyse-Endpoints
# ========================================================================

# Erlaubte Metriken für Analyse-Queries
_ANALYSE_METRICS = {
    # Basis-Metriken
    'total_return_pct': 'Total Return %',
    'total_trades': 'Total Trades',
    'win_rate_pct': 'Win Rate %',
    'profit_factor': 'Profit Factor',
    'max_drawdown_pct': 'Max Drawdown %',
    'expectancy': 'Expectancy',
    # Risiko-Kennzahlen
    'sharpe_ratio': 'Sharpe Ratio',
    'sortino_ratio': 'Sortino Ratio',
    'calmar_ratio': 'Calmar Ratio',
    'omega_ratio': 'Omega Ratio',
    # GEÄNDERT: Annualisierte Metriken
    'annualized_return': 'Annualisierte Rendite %',
    'annualized_volatility': 'Annualisierte Volatilität %',
    # GEÄNDERT: Erweiterte Risiko-Metriken
    'downside_risk': 'Downside Risk %',
    'tail_ratio': 'Tail Ratio',
    'value_at_risk': 'Value at Risk',
    'cond_value_at_risk': 'Conditional VaR',
    # GEÄNDERT: Benchmark-relative Metriken
    'alpha': 'Alpha',
    'beta': 'Beta',
    'information_ratio': 'Information Ratio',
    # GEÄNDERT: Trade-Qualität
    'sqn': 'SQN (System Quality)',
    'edge_ratio': 'Edge Ratio',
    # GEÄNDERT: Overfitting-Kontrolle
    'deflated_sharpe_ratio': 'Deflated Sharpe Ratio',
}


@router.get('/runs/{run_id}/analyse/parameter-ranking')
def get_parameter_ranking(
    run_id: int,
    metric: str = Query('sharpe_ratio'),
) -> dict:
    """Parameter-Ranking: Durchschnittliche Metrik pro Parameter-Wert.

    Zeigt für jeden Parameter, welche Werte die beste Performance liefern.
    """
    if metric not in _ANALYSE_METRICS:
        raise HTTPException(status_code=400, detail=f"Unbekannte Metrik: {metric}")




    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                p.param_name,
                p.param_value,
                COUNT(*) AS cnt,
                AVG(r.""" + metric + """) AS avg_val,
                MIN(r.""" + metric + """) AS min_val,
                MAX(r.""" + metric + """) AS max_val,
                STDDEV(r.""" + metric + """) AS std_val
            FROM backtest_result_params p
            JOIN backtest_results r ON r.id = p.result_id
            WHERE r.run_id = :run_id
              AND r.""" + metric + """ IS NOT NULL
            GROUP BY p.param_name, p.param_value
            ORDER BY p.param_name, avg_val DESC
        """), {"run_id": run_id}).fetchall()

    # Nach param_name gruppieren
    rankings: dict[str, list] = {}
    for r in rows:
        rankings.setdefault(r.param_name, []).append({
            'value': r.param_value,
            'count': r.cnt,
            'avg': round(r.avg_val, 4) if r.avg_val else None,
            'min': round(r.min_val, 4) if r.min_val else None,
            'max': round(r.max_val, 4) if r.max_val else None,
            'std': round(r.std_val, 4) if r.std_val else None,
        })

    return {
        'run_id': run_id,
        'metric': metric,
        'metric_label': _ANALYSE_METRICS[metric],
        'parameters': rankings,
    }


@router.get('/runs/{run_id}/analyse/top-results')
def get_top_results(
    run_id: int,
    metric: str = Query('sharpe_ratio'),
    limit: int = Query(20),
    direction: str = Query('desc'),
) -> dict:
    """Top-N Results nach einer Metrik, inkl. Parameter."""
    if metric not in _ANALYSE_METRICS:
        raise HTTPException(status_code=400, detail=f"Unbekannte Metrik: {metric}")




    order = "DESC" if direction == "desc" else "ASC"
    engine = get_engine()
    with engine.connect() as conn:
        # GEÄNDERT: Alle Analyse-Metriken im SELECT für vollständige Top-Results
        # GEÄNDERT: Ticket 15 — _json-Suffix (Raw-SQL muss neuen Spaltennamen verwenden)
        rows = conn.execute(text(f"""
            SELECT id, actual_params_json, total_return_pct, sharpe_ratio,
                   max_drawdown_pct, win_rate_pct, profit_factor, sortino_ratio,
                   total_trades, end_value, expectancy, calmar_ratio, omega_ratio,
                   annualized_return, annualized_volatility, downside_risk,
                   tail_ratio, value_at_risk, cond_value_at_risk,
                   alpha, beta, information_ratio, sqn, edge_ratio,
                   deflated_sharpe_ratio
            FROM backtest_results
            WHERE run_id = :run_id AND {metric} IS NOT NULL
            ORDER BY {metric} {order}
            LIMIT :lim
        """), {"run_id": run_id, "lim": limit}).fetchall()

    items = []
    for r in rows:
        items.append({
            'id': r.id,
            'actual_params': r.actual_params_json,
            'total_return_pct': r.total_return_pct,
            'sharpe_ratio': r.sharpe_ratio,
            'max_drawdown_pct': r.max_drawdown_pct,
            'win_rate_pct': r.win_rate_pct,
            'profit_factor': r.profit_factor,
            'sortino_ratio': r.sortino_ratio,
            'total_trades': r.total_trades,
            'end_value': r.end_value,
            'expectancy': r.expectancy,
            'calmar_ratio': r.calmar_ratio,
            'omega_ratio': r.omega_ratio,
            'annualized_return': r.annualized_return,
            'annualized_volatility': r.annualized_volatility,
            'downside_risk': r.downside_risk,
            'tail_ratio': r.tail_ratio,
            'value_at_risk': r.value_at_risk,
            'cond_value_at_risk': r.cond_value_at_risk,
            'alpha': r.alpha,
            'beta': r.beta,
            'information_ratio': r.information_ratio,
            'sqn': r.sqn,
            'edge_ratio': r.edge_ratio,
            'deflated_sharpe_ratio': r.deflated_sharpe_ratio,
        })

    return {
        'run_id': run_id,
        'metric': metric,
        'metric_label': _ANALYSE_METRICS[metric],
        'direction': direction,
        'results': items,
    }


@router.get('/runs/{run_id}/analyse/summary')
def get_analyse_summary(run_id: int) -> dict:
    """Zusammenfassung: Verteilung der Metriken über alle Results eines Runs."""



    engine = get_engine()
    with engine.connect() as conn:
        # GEÄNDERT: Erweiterte Zusammenfassung mit allen Analyse-Metriken
        row = conn.execute(text("""
            SELECT
                COUNT(*) AS total,
                AVG(total_return_pct) AS avg_return,
                AVG(sharpe_ratio) AS avg_sharpe,
                AVG(max_drawdown_pct) AS avg_dd,
                AVG(win_rate_pct) AS avg_winrate,
                AVG(profit_factor) AS avg_pf,
                MAX(total_return_pct) AS max_return,
                MIN(total_return_pct) AS min_return,
                MAX(sharpe_ratio) AS max_sharpe,
                MIN(max_drawdown_pct) AS min_dd,
                SUM(CASE WHEN total_return_pct > 0 THEN 1 ELSE 0 END) AS profitable,
                SUM(CASE WHEN sharpe_ratio > 1 THEN 1 ELSE 0 END) AS sharpe_gt1,
                AVG(sortino_ratio) AS avg_sortino,
                AVG(calmar_ratio) AS avg_calmar,
                AVG(omega_ratio) AS avg_omega,
                AVG(expectancy) AS avg_expectancy,
                AVG(annualized_return) AS avg_ann_return,
                AVG(annualized_volatility) AS avg_ann_vol,
                AVG(downside_risk) AS avg_downside_risk,
                AVG(sqn) AS avg_sqn,
                AVG(edge_ratio) AS avg_edge_ratio,
                AVG(alpha) AS avg_alpha,
                AVG(beta) AS avg_beta,
                AVG(deflated_sharpe_ratio) AS avg_deflated_sharpe
            FROM backtest_results
            WHERE run_id = :run_id
        """), {"run_id": run_id}).fetchone()

        # Parameter-Namen für diesen Run
        param_names = conn.execute(text("""
            SELECT DISTINCT p.param_name
            FROM backtest_result_params p
            JOIN backtest_results r ON r.id = p.result_id
            WHERE r.run_id = :run_id
            ORDER BY p.param_name
        """), {"run_id": run_id}).fetchall()

    def _r(val, digits: int = 2):
        return round(val, digits) if val is not None else None

    return {
        'run_id': run_id,
        'total_results': row.total,
        'profitable_count': row.profitable,
        'sharpe_gt1_count': row.sharpe_gt1,
        'avg_return': _r(row.avg_return),
        'avg_sharpe': _r(row.avg_sharpe),
        'avg_drawdown': _r(row.avg_dd),
        'avg_winrate': _r(row.avg_winrate),
        'avg_profit_factor': _r(row.avg_pf),
        'max_return': _r(row.max_return),
        'min_return': _r(row.min_return),
        'max_sharpe': _r(row.max_sharpe),
        'min_drawdown': _r(row.min_dd),
        # GEÄNDERT: Neue Durchschnittswerte
        'avg_sortino': _r(row.avg_sortino),
        'avg_calmar': _r(row.avg_calmar),
        'avg_omega': _r(row.avg_omega),
        'avg_expectancy': _r(row.avg_expectancy),
        'avg_annualized_return': _r(row.avg_ann_return),
        'avg_annualized_volatility': _r(row.avg_ann_vol),
        'avg_downside_risk': _r(row.avg_downside_risk),
        'avg_sqn': _r(row.avg_sqn),
        'avg_edge_ratio': _r(row.avg_edge_ratio),
        'avg_alpha': _r(row.avg_alpha, 4),
        'avg_beta': _r(row.avg_beta),
        'avg_deflated_sharpe': _r(row.avg_deflated_sharpe),
        'param_names': [r.param_name for r in param_names],
    }


@router.get('/runs/{run_id}/analyse/distribution')
def get_analyse_distribution(run_id: int) -> dict:
    """Verteilung: Gleichmäßige Intervalle über den tatsächlichen Return-Bereich."""
    import math

    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT total_return_pct AS val
            FROM backtest_results
            WHERE run_id = :run_id AND total_return_pct IS NOT NULL
        """), {"run_id": run_id}).fetchall()

    if not rows:
        return {"buckets": [], "total": 0}

    values = [float(r.val) for r in rows]
    total = len(values)
    min_val = min(values)
    max_val = max(values)

    # "Schönen" Step wählen der ~30 Balken ergibt
    raw_range = max_val - min_val
    nice_steps = [5, 10, 20, 25, 50, 100, 200, 250, 500]
    step = 10
    for s in nice_steps:
        if raw_range / s <= 35:
            step = s
            break

    range_min = math.floor(min_val / step) * step
    range_max = math.ceil(max_val / step) * step
    n_bins = max(1, (range_max - range_min) // step)

    # Werte in Bins zählen
    histogram = [0] * n_bins
    for v in values:
        idx = int((v - range_min) / step)
        if idx >= n_bins:
            idx = n_bins - 1
        if idx < 0:
            idx = 0
        histogram[idx] += 1

    buckets = []
    for i in range(n_bins):
        lo = range_min + i * step
        hi = lo + step
        buckets.append({
            "from": lo,
            "to": hi,
            "label": f"{lo}% bis {hi}%",
            "count": histogram[i],
        })

    return {"buckets": buckets, "total": total}


@router.get('/runs/{run_id}/analyse/equity-overview')
def get_equity_overview(run_id: int, max_points: int = Query(500)) -> dict:
    """Alle Backtest-Endwerte (Total Return %) sortiert aufsteigend, gesampelt."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT total_return_pct AS val
            FROM backtest_results
            WHERE run_id = :run_id AND total_return_pct IS NOT NULL
            ORDER BY total_return_pct ASC
        """), {"run_id": run_id}).fetchall()

    if not rows:
        return {"values": [], "total": 0}

    values = [round(float(r.val), 2) for r in rows]
    total = len(values)

    # Sampling: pro Bucket Avg/Min/Max berechnen
    if total > max_points:
        bucket_size = total / max_points
        buckets = []
        for i in range(max_points):
            start = int(i * bucket_size)
            end = int((i + 1) * bucket_size)
            chunk = values[start:end]
            buckets.append({
                "avg": round(sum(chunk) / len(chunk), 2),
                "min": round(min(chunk), 2),
                "max": round(max(chunk), 2),
            })
        return {"buckets": buckets, "total": total}

    # Weniger als max_points: alle Werte direkt
    buckets = [{"avg": v, "min": v, "max": v} for v in values]
    return {"buckets": buckets, "total": total}


@router.get('/runs/{run_id}/analyse/heatmap')
def get_heatmap(
    run_id: int,
    metric: str = Query('sharpe_ratio'),
    param_x: str = Query(...),
    param_y: str = Query(...),
    param_z: str = Query(None),
    agg: str = Query('max'),
) -> dict:
    """Heatmap: aggregierte Metrik je Kombination zweier Parameter.

    ``agg`` bestimmt die Aggregation über die nicht gewählten Parameter:
    'max' = bester Wert pro Zelle, 'avg' = Durchschnitt. Optional ``param_z``
    als dritte Dimension (Slider).
    """
    if metric not in _ANALYSE_METRICS:
        raise HTTPException(status_code=400, detail=f"Unbekannte Metrik: {metric}")
    if agg not in ('avg', 'max'):
        raise HTTPException(status_code=400, detail=f"Unbekannte Aggregation: {agg}")
    # Whitelist-Mapping → sichere SQL-Interpolation (kein User-String in die Query)
    agg_fn = 'MAX' if agg == 'max' else 'AVG'

    engine = get_engine()
    with engine.connect() as conn:
        if param_z:
            # Mit dritter Dimension: pro Z-Wert eine eigene Heatmap
            rows = conn.execute(text("""
                SELECT px.param_value AS x_val, py.param_value AS y_val,
                       pz.param_value AS z_val,
                       """ + agg_fn + """(r.""" + metric + """) AS agg_val, COUNT(*) AS cnt
                FROM backtest_results r
                JOIN backtest_result_params px ON px.result_id = r.id AND px.param_name = :px
                JOIN backtest_result_params py ON py.result_id = r.id AND py.param_name = :py
                JOIN backtest_result_params pz ON pz.result_id = r.id AND pz.param_name = :pz
                WHERE r.run_id = :run_id AND r.""" + metric + """ IS NOT NULL
                GROUP BY px.param_value, py.param_value, pz.param_value
                ORDER BY pz.param_value, px.param_value, py.param_value
            """), {"run_id": run_id, "px": param_x, "py": param_y, "pz": param_z}).fetchall()

            x_set = sorted(set(r.x_val for r in rows))
            y_set = sorted(set(r.y_val for r in rows))
            z_set = sorted(set(r.z_val for r in rows))

            # Slices als Liste parallel zu z_set: Frontend greift per Index zu und
            # vermeidet so den Float-Key-Mismatch zwischen Python-dict und JS-Lookup
            slices_by_z: dict = {z: [] for z in z_set}
            for r in rows:
                slices_by_z[r.z_val].append({
                    'x': r.x_val,
                    'y': r.y_val,
                    'value': round(r.agg_val, 2) if r.agg_val is not None else None,
                    'count': r.cnt,
                })
            slices = [slices_by_z[z] for z in z_set]

            return {
                'run_id': run_id,
                'metric': metric,
                'param_x': param_x,
                'param_y': param_y,
                'param_z': param_z,
                'agg': agg,
                'x_values': x_set,
                'y_values': y_set,
                'z_values': z_set,
                'slices': slices,
            }
        else:
            rows = conn.execute(text("""
                SELECT px.param_value AS x_val, py.param_value AS y_val,
                       """ + agg_fn + """(r.""" + metric + """) AS agg_val, COUNT(*) AS cnt
                FROM backtest_results r
                JOIN backtest_result_params px ON px.result_id = r.id AND px.param_name = :px
                JOIN backtest_result_params py ON py.result_id = r.id AND py.param_name = :py
                WHERE r.run_id = :run_id AND r.""" + metric + """ IS NOT NULL
                GROUP BY px.param_value, py.param_value
                ORDER BY px.param_value, py.param_value
            """), {"run_id": run_id, "px": param_x, "py": param_y}).fetchall()

            x_set = sorted(set(r.x_val for r in rows))
            y_set = sorted(set(r.y_val for r in rows))

            cells = []
            for r in rows:
                cells.append({
                    'x': r.x_val,
                    'y': r.y_val,
                    'value': round(r.agg_val, 2) if r.agg_val is not None else None,
                    'count': r.cnt,
                })

            return {
                'run_id': run_id,
                'metric': metric,
                'param_x': param_x,
                'param_y': param_y,
                'agg': agg,
                'x_values': x_set,
                'y_values': y_set,
                'cells': cells,
            }


@router.get('/runs/{run_id}/analyse/volume')
def get_volume(
    run_id: int,
    metric: str = Query('sharpe_ratio'),
    param_x: str = Query(...),
    param_y: str = Query(...),
    param_z: str = Query(...),
) -> JSONResponse:
    """3D-Volumen-Plot über drei Parameter-Achsen (VBT-Visualisierung als Plotly-JSON).

    Bildet die Durchschnitts-Metrik je Kombination der drei gewählten Parameter und
    rendert sie über VBTs eigene ``volume()``-Methode. Übrige (nicht gewählte)
    Parameter werden — wie bei der Heatmap — weggemittelt. Liefert die fertige
    Plotly-Figur als JSON, das das Frontend per ``Plotly.newPlot`` zeichnet.
    """
    if metric not in _ANALYSE_METRICS:
        raise HTTPException(status_code=400, detail=f"Unbekannte Metrik: {metric}")
    if len({param_x, param_y, param_z}) < 3:
        raise HTTPException(status_code=400, detail="Drei verschiedene Parameter erforderlich")

    # GEÄNDERT: vbt/numpy lazy importieren (schwere Lib, vgl. worker_tasks.py)
    import numpy as np
    import vectorbtpro as vbt  # noqa: F401  (Accessor .vbt wird durch den Import registriert)

    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT px.param_value AS x_val, py.param_value AS y_val,
                   pz.param_value AS z_val,
                   MAX(r.""" + metric + """) AS avg_val
            FROM backtest_results r
            JOIN backtest_result_params px ON px.result_id = r.id AND px.param_name = :px
            JOIN backtest_result_params py ON py.result_id = r.id AND py.param_name = :py
            JOIN backtest_result_params pz ON pz.result_id = r.id AND pz.param_name = :pz
            WHERE r.run_id = :run_id AND r.""" + metric + """ IS NOT NULL
            GROUP BY px.param_value, py.param_value, pz.param_value
        """), {"run_id": run_id, "px": param_x, "py": param_y, "pz": param_z}).fetchall()

    if not rows:
        return JSONResponse({"figure": None, "message": "Keine Daten für diese Parameter"})

    # Series mit 3-Level-MultiIndex auf lückenlosem Kreuzprodukt bauen (fehlende = NaN)
    x_set = sorted(set(r.x_val for r in rows))
    y_set = sorted(set(r.y_val for r in rows))
    z_set = sorted(set(r.z_val for r in rows))
    val_map = {(r.x_val, r.y_val, r.z_val): r.avg_val for r in rows}
    full_index = pd.MultiIndex.from_product(
        [x_set, y_set, z_set], names=[param_x, param_y, param_z]
    )
    values = [val_map.get(tuple(ix), np.nan) for ix in full_index]
    sr = pd.Series(values, index=full_index, dtype=float)

    fig = sr.vbt.volume(
        trace_kwargs=dict(
            colorscale="icefire",
            colorbar=dict(title=_ANALYSE_METRICS[metric]),
        ),
        return_fig=True,
    )
    # Würfel-Darstellung (gleichlange Achsen) wie im VBT-Beispiel statt nach
    # Datenbereich gestreckt; aspectmode="cube" normiert alle drei Achsen.
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        scene=dict(aspectmode="cube"),
    )

    return JSONResponse(json.loads(fig.to_json()))


# ========================================================================
# Recompute-Job Steuerung
# ========================================================================

@router.post('/runs/{run_id}/analyse/start')
def start_recompute_jobs(run_id: int) -> JSONResponse:
    """Startet Hintergrund-Recompute für alle Results ohne Equity-Daten."""



    engine = get_engine()
    with engine.connect() as conn:
        # Results ohne Equity finden (queued/running Jobs ausschließen, failed Jobs erlauben → Retry)
        missing = conn.execute(text("""
            SELECT r.id FROM backtest_results r
            WHERE r.run_id = :run_id
              AND r.id NOT IN (SELECT DISTINCT result_id FROM backtest_result_equity)
              AND r.id NOT IN (SELECT result_id FROM backtest_jobs WHERE status IN ('queued', 'running', 'completed'))
        """), {"run_id": run_id}).fetchall()

    if not missing:
        return JSONResponse({'queued': 0, 'message': 'Alle Results haben bereits Equity-Daten'})

    result_ids = [r.id for r in missing]

    # Alte failed Jobs für diese Results löschen (damit Retry möglich ist)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            DELETE FROM backtest_jobs
            WHERE run_id = :run_id AND status = 'failed'
              AND result_id IN :rids
        """), {"run_id": run_id, "rids": tuple(result_ids)})

    # Jobs in DB anlegen (Batch-Insert, Duplikate ignorieren)
    with engine.begin() as conn:
        batch_size = 5000
        for i in range(0, len(result_ids), batch_size):
            chunk = [{'run_id': run_id, 'result_id': rid, 'status': 'queued'} for rid in result_ids[i:i + batch_size]]
            stmt = pg_insert(BacktestJob).values(chunk).on_conflict_do_nothing(index_elements=['result_id'])
            conn.execute(stmt)

        # Alle queued Jobs mit IDs holen
        jobs = conn.execute(text("""
            SELECT id, result_id FROM backtest_jobs
            WHERE run_id = :run_id AND status = 'queued' AND rq_job_id IS NULL
        """), {"run_id": run_id}).fetchall()

    # RQ-Jobs enqueuen
    redis_conn = get_redis_connection()
    q = Queue(RECOMPUTE_QUEUE_NAME, connection=redis_conn)

    with engine.begin() as conn:
        for job_row in jobs:
            rq_job = q.enqueue(
                'services.api.worker_tasks.run_recompute_job',
                job_row.id,
                job_row.result_id,
                job_timeout=600,
            )
            conn.execute(text(
                "UPDATE backtest_jobs SET rq_job_id = :rq_id WHERE id = :id"
            ), {"rq_id": rq_job.id, "id": job_row.id})

    return JSONResponse({'queued': len(jobs)})


@router.post('/runs/{run_id}/analyse/stop')
def stop_recompute_jobs(run_id: int) -> JSONResponse:
    """Stoppt alle queued Jobs — löscht sie und leert die RQ-Queue."""
    # RQ Recompute-Queue komplett leeren (schneller als einzeln canceln)
    redis_conn = get_redis_connection()
    q = Queue(RECOMPUTE_QUEUE_NAME, connection=redis_conn)
    q.empty()

    # Queued Jobs aus DB löschen — damit Start sie neu anlegen kann
    session = get_session()
    try:
        cancelled = session.query(BacktestJob).filter(
            BacktestJob.run_id == run_id,
            BacktestJob.status == 'queued'
        ).delete()
        session.commit()
    finally:
        session.close()

    return JSONResponse({'cancelled': cancelled})


@router.post('/runs/{run_id}/analyse/reset')
def reset_recompute_jobs(run_id: int) -> JSONResponse:
    """Löscht alle Jobs für diesen Run (stoppt zuerst queued Jobs)."""



    session = get_session()
    try:

        jobs = session.query(BacktestJob).filter(BacktestJob.run_id == run_id).all()

        redis_conn = get_redis_connection()
        for job in jobs:
            if job.rq_job_id and job.status in ('queued', 'running'):
                try:
                    rq_job = RqJob.fetch(job.rq_job_id, connection=redis_conn)
                    rq_job.cancel()
                except Exception:
                    pass

        deleted = session.query(BacktestJob).filter(BacktestJob.run_id == run_id).delete()
        session.commit()
    finally:
        session.close()

    return JSONResponse({'deleted': deleted})


@router.get('/runs/{run_id}/analyse/progress')
def get_recompute_progress(run_id: int) -> dict:
    """Fortschritt der Hintergrund-Berechnung für einen Run."""



    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT status, COUNT(*) AS cnt
            FROM backtest_jobs
            WHERE run_id = :run_id
            GROUP BY status
        """), {"run_id": run_id}).fetchall()

        # Durchschnittliche Job-Dauer für ETA-Berechnung
        avg_row = conn.execute(text("""
            SELECT AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) AS avg_sec,
                   COUNT(*) AS done_count
            FROM backtest_jobs
            WHERE run_id = :run_id AND status = 'completed'
              AND started_at IS NOT NULL AND completed_at IS NOT NULL
        """), {"run_id": run_id}).fetchone()

        # Anzahl aktiver Worker (Jobs mit status 'running' über alle Runs)
        worker_count = conn.execute(text(
            "SELECT COUNT(*) FROM backtest_jobs WHERE status = 'running'"
        )).scalar() or 1

        # Gesamtzahl Results im Run (ohne die mit Equity — die brauchen keinen Recompute)
        total_results = conn.execute(text(
            "SELECT COUNT(*) FROM backtest_results WHERE run_id = :run_id"
        ), {"run_id": run_id}).scalar() or 0

        # Davon bereits mit Equity (unabhängig ob per Job oder Chart-Klick)
        with_equity = conn.execute(text(
            "SELECT COUNT(DISTINCT result_id) FROM backtest_result_equity WHERE result_id IN (SELECT id FROM backtest_results WHERE run_id = :run_id)"
        ), {"run_id": run_id}).scalar() or 0

    counts = {r.status: r.cnt for r in rows}
    queued = counts.get('queued', 0)
    running = counts.get('running', 0)
    completed = counts.get('completed', 0)
    failed = counts.get('failed', 0)
    pending = total_results - with_equity - queued - running

    # ETA berechnen
    eta_iso = None
    remaining = queued + running + pending
    if remaining > 0 and avg_row and avg_row.avg_sec and avg_row.done_count >= 3:
        avg_sec = float(avg_row.avg_sec)
        eta_seconds = (remaining * avg_sec) / max(worker_count, 1)
        eta_time = datetime.now() + timedelta(seconds=eta_seconds)
        eta_iso = eta_time.strftime('%H:%M')

    return {
        'run_id': run_id,
        'total': total_results,
        'completed': with_equity,
        'queued': queued,
        'running': running,
        'failed': failed,
        'pending': max(pending, 0),
        'is_active': queued > 0 or running > 0,
        'eta': eta_iso,
    }
