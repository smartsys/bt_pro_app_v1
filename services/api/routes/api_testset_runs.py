"""
API-Endpunkte für TestSet-Runs

POST /api/testset-runs  — Neuen TestSet-Lauf starten (N Backtest-Runs enqueuen)
"""

import logging
from typing import Optional, Union

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from user_data.utils.database.db import get_session
from user_data.utils.database.models import (
    BacktestConfig,
    IndicatorConfig,
    StrategyConcept,
    StrategyIteration,
)
from user_data.utils.database.repository import create_backtest_run
from user_data.utils.database.repository_testsets import (
    create_testset_run,
    get_testset,
)
# GEÄNDERT: Metrik-Auswahl beim Run-Start
from user_data.utils.metrics.metric_sets import validate_metrics_selection
# GEÄNDERT: — Befund Phase 1 (Kontext + Soll) beim Start anlegen; einzige
# Implementierung, auch vom Leaderboard-Rerun genutzt
from services.api.utils.finding_aggregation import open_finding_for_testset_run
# GEÄNDERT: Genau-eines-Regel für die Raster-Quelle (Config-ID oder inline)
from services.api.utils.indicator_source import require_exactly_one_indicator_source

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/testset-runs', tags=['testset-runs'])


# --- Pydantic Schema ---

class TestSetRunIn(BaseModel):
    """Eingabe-Schema für TestSet-Lauf.

    GEÄNDERT: TestSet-Lauf nutzt jetzt iteration_id + indicator_config_id wie
    Einzel-Lauf — semantisch identisch, nur N statt 1 Runs.
    """
    testset_id: int
    iteration_id: int
    # GEÄNDERT: das Raster kommt wahlweise aus einer gespeicherten
    # IndicatorConfig (indicator_config_id) oder inline (indicators, Inhalt von
    # config_json inklusive '_stops'). Genau eines von beiden ist Pflicht; die Prüfung
    # macht die Route, damit der Grund im Klartext in der Antwort steht.
    indicator_config_id: Optional[int] = None
    indicators: Optional[dict] = None
    # GEÄNDERT: optionale Metrik-Auswahl, gilt für alle N erzeugten Runs.
    # "kern" | "voll" | "auto" (Default) | Liste zusätzlich gewünschter Gruppen-Keys.
    metrics: Optional[Union[str, list[str]]] = None


# --- Endpunkt ---

@router.post('')
def start_testset_run(payload: TestSetRunIn) -> JSONResponse:
    """Legt einen TestSet-Lauf an und enqueued N Backtest-Runs.

    Löst strategy_family/strategy_name/import_path aus der Iteration auf
    (analog Einzel-Lauf), nimmt das Indikator-Raster aus der gespeicherten
    IndicatorConfig oder inline entgegen und enqueued einen RQ-Job pro
    BacktestConfig im TestSet.

    Body: { testset_id, iteration_id, indicator_config_id | indicators, metrics? }
    Response: { data: { testset_run_id, run_ids }, error: null }
    """
    # GEÄNDERT: Metrik-Auswahl syntaktisch prüfen, BEVOR irgendein Datensatz
    # (TestSetRun oder BacktestRun) angelegt wird. Die 'auto'-Auflösung selbst (braucht
    # n_combinations je BacktestConfig) passiert erst in create_backtest_run.
    try:
        metrics_selection = validate_metrics_selection(payload.metrics)
    except ValueError as exc:
        return JSONResponse({'error': str(exc)}, status_code=400)

    # GEÄNDERT: Raster-Quelle prüfen, ebenfalls vor jedem Datensatz.
    try:
        require_exactly_one_indicator_source(payload.indicator_config_id, payload.indicators)
    except ValueError as exc:
        return JSONResponse({'error': str(exc)}, status_code=400)

    session = get_session()
    try:
        # TestSet existiert?
        testset = get_testset(session, payload.testset_id)
        if testset is None:
            return JSONResponse(
                {'error': f'TestSet #{payload.testset_id} nicht gefunden'},
                status_code=400,
            )

        backtest_config_ids: list[int] = list(testset.backtest_config_ids_json)
        if not backtest_config_ids:
            return JSONResponse(
                {'error': f'TestSet #{payload.testset_id} enthält keine BacktestConfigs'},
                status_code=400,
            )

        # Iteration + Concept auflösen (analog /api/backtest/start)
        iteration = (
            session.query(StrategyIteration)
            .filter(StrategyIteration.id == payload.iteration_id)
            .first()
        )
        if iteration is None:
            return JSONResponse(
                {'error': f'Iteration #{payload.iteration_id} nicht gefunden'},
                status_code=400,
            )
        concept = (
            session.query(StrategyConcept)
            .filter(StrategyConcept.id == iteration.concept_id)
            .first()
        )
        if concept is None:
            return JSONResponse(
                {'error': f'Concept für Iteration #{payload.iteration_id} nicht gefunden'},
                status_code=400,
            )
        strat_family = concept.slug
        strat_name = iteration.version
        # Hardcoded-Iterationen bringen eigenen Code-Pfad mit, sonst Spec-Runner
        if iteration.type == 'hardcoded':
            strat_import_path = iteration.import_path
        else:
            from user_data.strategies.generic.spec_runner import SPEC_RUNNER_IMPORT_PATH
            strat_import_path = SPEC_RUNNER_IMPORT_PATH

        # Indikator-Raster auflösen — gespeicherte IndicatorConfig oder inline
        # GEÄNDERT: bei inline entfällt der Lookup vollständig; das Dict
        # geht unverändert weiter und es entsteht keine IndicatorConfig-Zeile.
        if payload.indicator_config_id is not None:
            ind_config = (
                session.query(IndicatorConfig)
                .filter(IndicatorConfig.id == payload.indicator_config_id)
                .first()
            )
            if ind_config is None:
                return JSONResponse(
                    {'error': f'Indicator-Config #{payload.indicator_config_id} nicht gefunden'},
                    status_code=400,
                )
            indicators_json: dict = dict(ind_config.config_json or {})
        else:
            indicators_json = dict(payload.indicators or {})

        # Alle BacktestConfigs laden
        bt_configs = (
            session.query(BacktestConfig)
            .filter(BacktestConfig.id.in_(backtest_config_ids))
            .all()
        )
        bt_map = {bt.id: bt for bt in bt_configs}
        missing = [cid for cid in backtest_config_ids if cid not in bt_map]
        if missing:
            return JSONResponse(
                {'error': f'BacktestConfig-IDs nicht gefunden: {missing}'},
                status_code=400,
            )

        iteration_id_int: int = iteration.id
        # GEÄNDERT: Soll-Schnappschuss aus dem Konzept ziehen, solange die
        # Session offen ist. Das Kopieren selbst passiert im Repository (deepcopy), damit
        # eine spätere Änderung von goal_json bestehende Befunde nicht mehr berührt.
        concept_id_int: int = concept.id
        goal_snapshot: Optional[dict] = concept.goal_json

    finally:
        session.close()

    n_total = len(backtest_config_ids)

    # TestSetRun anlegen
    session = get_session()
    try:
        testset_run = create_testset_run(
            session=session,
            testset_id=payload.testset_id,
            strategy_family=strat_family,
            strategy_name=strat_name,
            n_runs_total=n_total,
            # GEÄNDERT: indicators_config_json direkt (kein indicator_config_id mehr)
            indicators_config_json=indicators_json,
            status='queued',
        )
        testset_run_id: int = testset_run.id
    finally:
        session.close()

    # N BacktestRuns anlegen und enqueuen
    # rq lazy importieren — nicht verfügbar im Test-Kontext
    from rq import Queue
    from services.api.redis_conn import get_redis_connection, BACKTEST_QUEUE_NAME, BACKTEST_JOB_TIMEOUT
    # GEÄNDERT: Spec-Runner-Version für Reproduzierbarkeit
    from user_data.strategies.generic.spec_runner import VERSION as _spec_runner_version

    # GEÄNDERT: — Befund Phase 1: Kontext + Soll stehen fest, bevor
    # gerechnet wird. Das Soll stammt ausschließlich aus concept.goal_json
    # (Schnappschuss), es gibt bewusst keine manuelle Soll-Eingabe im Payload — genau
    # die wäre der Drift-Kanal. Anlage über die einzige Phase-1-Implementierung
    # (auch vom Leaderboard-Rerun genutzt).
    session = get_session()
    try:
        open_finding_for_testset_run(
            session=session,
            testset_run_id=testset_run_id,
            iteration_id=iteration_id_int,
            concept_id=concept_id_int,
            testset_id=payload.testset_id,
            indicator_config_id=payload.indicator_config_id,
            indicators_json=indicators_json,
            spec_runner_version=_spec_runner_version,
            goal_snapshot=goal_snapshot,
            planned_n_runs=n_total,
        )
    finally:
        session.close()

    q = Queue(BACKTEST_QUEUE_NAME, connection=get_redis_connection())
    run_ids: list[int] = []

    for config_id in backtest_config_ids:
        bt = bt_map[config_id]
        backtest_config_json = {
            'strategy_family': strat_family,
            'strategy_name': strat_name,
            'import_path': strat_import_path,
            # GEÄNDERT: backtest_config_id für deterministisches Aggregat-Mapping
            'backtest_config_id': config_id,
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
                # GEÄNDERT: slippage und die zwei Stop-Ausführungsfelder
                # aus der BacktestConfig durchreichen (analog echter Einzel-Run).
                'slippage': bt.slippage,
                'stop_exit_price': bt.stop_exit_price,
                'stop_order_type': bt.stop_order_type,
                # GEÄNDERT: Ticket 104 — risikobasierte Positionsgröße + Hebel
                # aus der BacktestConfig durchreichen (analog echter Einzel-Run).
                'risk_pct': bt.risk_pct,
                'leverage': bt.leverage,
                'leverage_mode': bt.leverage_mode,
                # GEÄNDERT: Schritt 3c/3d — Stop-Spalten UND Stop-Formate aus der
                # BacktestConfig entfernt. Stops samt Formaten kommen ausschließlich
                # aus indicators_json['_stops'] (IndicatorConfig).
            },
        }
        # GEÄNDERT: Metrik-Auswahl gilt für alle N Runs des TestSet-Laufs.
        if metrics_selection is not None:
            backtest_config_json['metrics'] = metrics_selection

        # GEÄNDERT: Schritt 3b — '_stops' stammt jetzt aus der IndicatorConfig
        # (indicators_json). Kein Clobbern mehr aus dem portfolio-Block. Die eigene
        # Kopie bleibt, damit pro Run-Eintrag ein unabhängiges dict entsteht.
        run_indicators_json = dict(indicators_json)

        # GEÄNDERT: testset_run_id setzen
        # iteration_id explizit weiterreichen — kein Lookup-Umweg nötig
        run_id = create_backtest_run(
            backtest_config=backtest_config_json,
            indicators_config=run_indicators_json,
            spec_runner_version=_spec_runner_version,
            testset_run_id=testset_run_id,
            iteration_id=iteration_id_int,
            # GEÄNDERT: Herkunfts-Referenzen auf die gewählten Configs mitschreiben
            backtest_config_id=config_id,
            indicator_config_id=payload.indicator_config_id,
        )
        run_ids.append(run_id)
        q.enqueue('services.api.worker_tasks.run_backtest_job', run_id=run_id, job_timeout=BACKTEST_JOB_TIMEOUT)

    logger.info(
        '[TESTSET-RUN] TestSetRun #%d gestartet: %d Runs enqueued (TestSet #%d)',
        testset_run_id, n_total, payload.testset_id,
    )

    return JSONResponse(
        {'data': {'testset_run_id': testset_run_id, 'run_ids': run_ids}, 'error': None},
        status_code=200,
    )
