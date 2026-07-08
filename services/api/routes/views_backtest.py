"""
HTML-Seiten für Backtest-Anzeige

GET /backtest/start               — Backtest starten
GET /backtest/runs                — Runs-Übersicht
GET /backtest/runs/{id}           — Run-Detail mit Results
GET /backtest/runs/{id}/analyse   — Analyse-Seite für einen Run
GET /backtest/results             — Alle Results mit Filtern
"""

from typing import Optional
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse

from user_data.utils.database.db import get_session
from user_data.utils.database.models import BacktestRun, BacktestResult

router = APIRouter(prefix='/backtest', tags=['views'])


# GEÄNDERT: Ticket 53 — Dual-Präfix (Klasse UND Spec-Key), analog zur bereits
# robusten Logik in repository.py:_build_resolved_config (Zeile ~563-565). Seit
# Ticket 53 benennt indicator_factory.build_indicators die Param-Level jeder
# Indikator-Instanz auf den Spec-ID-Namen um (z.B. 'fast_sma_length' statt
# 'dwsfastsma_length'). Ein rein klassenbasiertes Präfix (Klassenname aus
# cfg['indicator']) matcht bei Custom-Indikatoren (Spec-Key != Klasse) dann nicht
# mehr — das Panel zeigt still keine Werte (kein Crash). Beide Präfixe parallel
# zu prüfen heilt zugleich einen Bestandsdefekt: direkt referenzierte Custom-
# Indikatoren wurden schon vor Ticket 53 von _uniquify_param_levels (rules_engine)
# auf den Spec-Key umbenannt, das Klassen-Präfix matchte also auch dort nie.
def _resolve_ind_params(ind_config: dict, actual_params: dict) -> dict:
    """Ordnet persistierte Parameter (actual_params) den Indikatoren im Chart-Panel zu.

    actual_params trägt flache Keys im Schema `<präfix>_<param>`. Das Präfix ist je
    nach Alter des Results entweder der Klassenname (z.B. `dwsfastsma_`, alte/getragene
    Results vor Ticket 53) oder der Spec-Key (z.B. `fast_sma_`/`vwma_`, seit Ticket 53
    bzw. schon vorher bei direkt referenzierten Custom-Indikatoren). Beide Präfixe
    werden geprüft, damit das Panel für jeden Indikator unabhängig vom Alter des
    Results Werte anzeigt.

    Args:
        ind_config: Indikator-Config-Block des Runs (Spec-Key -> Spec-Eintrag).
        actual_params: Flache, persistierte Parameter eines Results.

    Returns:
        dict: Spec-Key -> {param_name: value} für jeden Indikator mit Treffern.
    """
    ind_params: dict = {}
    for ind_name, cfg in ind_config.items():
        cls = str(cfg.get('indicator', '')).split(':')[-1].lower()
        prefixes = [p for p in {cls, str(ind_name).lower()} if p]
        params: dict = {}
        for prefix in prefixes:
            full_prefix = prefix + '_'
            for k, v in actual_params.items():
                if k.startswith(full_prefix):
                    params[k[len(full_prefix):]] = v
        if params:
            ind_params[ind_name] = params
    return ind_params


@router.get('/start', response_class=HTMLResponse)
def backtest_start_page(request: Request) -> HTMLResponse:
    """Backtest starten — Backtest-Config + Indicator-Config auswählen."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='backtest/start.html',
        context={'active_nav': 'start'},
    )


@router.get('/runs', response_class=HTMLResponse)
def runs_page(request: Request) -> HTMLResponse:
    """Runs-Übersicht — leeres Template, DataTables lädt per AJAX."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='backtest/runs.html',
        context={'active_nav': 'runs'},
    )


@router.get('/runs/{run_id}', response_class=HTMLResponse)
def run_detail_page(request: Request, run_id: int) -> HTMLResponse:
    """Run-Detail — zeigt alle Results eines Runs."""
    session = get_session()
    try:
        run = session.query(BacktestRun).filter(BacktestRun.id == run_id).first()
        if not run:
            return HTMLResponse('<h1>Run nicht gefunden</h1>', status_code=404)
        # Daten für Page-Header extrahieren (bevor Session geschlossen wird)
        run_data = {
            'id': run.id,
            'strategy_family': run.strategy_family,
            'strategy_name': run.strategy_name,
            'symbol': run.symbol,
            'exchange': run.exchange,
            'timeframe': run.timeframe,
            'start_date': run.start_date,
            'end_date': run.end_date,
            'n_combinations': run.n_combinations,
            'status': run.status,
        }
    finally:
        session.close()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='backtest/run_detail.html',
        context={'active_nav': 'runs', 'run': run_data},
    )


@router.get('/runs/{run_id}/analyse', response_class=HTMLResponse)
def run_analyse_page(request: Request, run_id: int) -> HTMLResponse:
    """Analyse-Seite für einen Run — Parameter-Sensitivität und Rankings."""
    session = get_session()
    try:
        run = session.query(BacktestRun).filter(BacktestRun.id == run_id).first()
        if not run:
            return HTMLResponse('<h1>Run nicht gefunden</h1>', status_code=404)

        result_count = session.query(BacktestResult).filter(
            BacktestResult.run_id == run_id
        ).count()

        run_data = {
            'id': run.id,
            'strategy_family': run.strategy_family,
            'strategy_name': run.strategy_name,
            'symbol': run.symbol,
            'exchange': run.exchange,
            'timeframe': run.timeframe,
            'start_date': run.start_date,
            'end_date': run.end_date,
            'n_combinations': run.n_combinations,
            'result_count': result_count,
            # GEÄNDERT: Ticket 15 Code-Sweep — _json-Suffix
            'indicators_config': run.indicators_config_json,
        }
    finally:
        session.close()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='backtest/analyse.html',
        context={'active_nav': 'runs', 'run': run_data},
    )


@router.get('/results', response_class=HTMLResponse)
def results_page(
    request: Request,
    symbol: Optional[str] = Query(None),
    timeframe: Optional[str] = Query(None),
    run_id: Optional[int] = Query(None),
) -> HTMLResponse:
    """Alle Results mit Filtern — Template lädt Filter-Werte und Daten per AJAX."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='backtest/results.html',
        context={
            'active_nav': 'results',
            'filter_symbol': symbol,
            'filter_timeframe': timeframe,
            'filter_run_id': run_id,
        },
    )


@router.get('/results/{result_id}/chart', response_class=HTMLResponse)
def result_chart_page(request: Request, result_id: int) -> HTMLResponse:
    """Chart-Seite für ein einzelnes Result mit LightweightCharts."""
    session = get_session()
    try:
        result = session.query(BacktestResult).filter(BacktestResult.id == result_id).first()
        if not result:
            return HTMLResponse('<h1>Result nicht gefunden</h1>', status_code=404)
        run = session.query(BacktestRun).filter(BacktestRun.id == result.run_id).first()

        result_data = {
            'id': result.id,
            'run_id': result.run_id,
            # GEÄNDERT: Ticket 15 Code-Sweep — _json-Suffix
            'actual_params': result.actual_params_json if isinstance(result.actual_params_json, dict) else {},
            'total_return_pct': result.total_return_pct,
            'profit_factor': result.profit_factor,
            'sharpe_ratio': result.sharpe_ratio,
            'max_drawdown_pct': result.max_drawdown_pct,
            'total_trades': result.total_trades,
            'win_rate_pct': result.win_rate_pct,
            'is_favorite': bool(result.is_favorite),
        }
        # GEÄNDERT: K2 — keine Supertrend-Spezialwerte mehr; alle Indikatoren werden
        # generisch über ind_config/ind_params an das Template gereicht.
        # GEÄNDERT: Ticket 15 Code-Sweep — _json-Suffix
        ind_config = run.indicators_config_json or {}

        run_data = {
            'strategy_family': run.strategy_family,
            'strategy_name': run.strategy_name,
            'symbol': run.symbol,
            'exchange': run.exchange,
            'timeframe': run.timeframe,
            'start_date': run.start_date,
            'end_date': run.end_date,
        }

        # GEÄNDERT: Ticket 53 — aufgelöste Parameter je Indikator generisch zuordnen,
        # damit die generischen Chart-Panels die vollständige Konfiguration anzeigen
        # können. Dual-Präfix (Klasse UND Spec-Key), siehe _resolve_ind_params.
        actual_params = result_data['actual_params']
        ind_params = _resolve_ind_params(ind_config, actual_params)
    finally:
        session.close()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='backtest/result_chart.html',
        context={
            'active_nav': 'results',
            'result': result_data,
            'run': run_data,
            # GEÄNDERT: vollständige Indikator-Config für generisches Rendering aller Indikatoren
            'ind_config': ind_config,
            # GEÄNDERT: aufgelöste Parameter je Indikator für die vollständige Panel-Anzeige
            'ind_params': ind_params,
        },
    )
