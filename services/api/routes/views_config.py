"""
HTML-Seiten für Konfiguration

GET /config/backtest              — Backtest-Configs Übersicht
GET /config/backtest/new          — Neue Backtest-Config anlegen
GET /config/backtest/{id}         — Backtest-Config bearbeiten
GET /config/indicator             — Indicator-Configs Übersicht
GET /config/indicator/new         — Neue Indicator-Config anlegen
GET /config/indicator/{id}        — Indicator-Config bearbeiten
GET /config/strategy              — Strategie-Konzepte Übersicht (Ticket 11)
GET /config/strategy/concepts/{id} — Iterations-Liste für ein Konzept (Ticket 11)
GET /backtest/start               — Backtest starten (Config + Indicator auswahelen)
"""

import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import json

from services.api.utils.obsidian_paths import concept_md_path, iteration_md_path
from user_data.utils.database.db import get_session
from user_data.utils.database.models import BacktestConfig, IndicatorConfig, StrategyConfig, StrategyConcept, StrategyIteration, ChartPlaygroundSetup


# GEÄNDERT: Stops-Defaults + kanonische innere Reihenfolge (analog Frontend defaultStops/STOPS_FIELDS)
_STOPS_KEY_ORDER = ['tp_stop', 'sl_stop', 'tsl_th', 'tsl_stop', 'td_stop', 'delta_format', 'time_delta_format']


def _default_stops() -> dict:
    """Default-Stops — identisch zur Frontend-Funktion defaultStops()."""
    return {
        'tp_stop': 0.30, 'sl_stop': 0.15, 'tsl_th': None, 'tsl_stop': None,
        'td_stop': 8, 'delta_format': 'percent', 'time_delta_format': 'rows',
    }


def _ensure_stops(config: dict) -> dict:
    """Ergänzt fehlende _stops (Defaults), damit die JSON-Ansicht die Stops direkt zeigt —
    konsistent mit dem visuellen Editor (kein Auftauchen erst beim Umschalten).
    _stops_pos wird bewusst NICHT ergänzt: die Stops-Position ist reine Anzeige und gehört
    nicht in eine Indikator-Config (sie lebt nur im Playground-Setup)."""
    cfg = dict(config) if isinstance(config, dict) else {}
    if not isinstance(cfg.get('_stops'), dict):
        cfg['_stops'] = _default_stops()
    return cfg


def _sort_indicator_config(config: dict) -> dict:
    """Sortiert Indicator-Config: Indikatoren (Meta-Felder zuerst, dann Parameter), danach der
    _stops-Sonderblock und der _stops_pos-Meta-Key. _-präfixierte Keys sind keine Indikatoren."""
    meta_keys = ['indicator', 'tf', 'enabled']
    param_key_order = ['start', 'stop', 'step', 'type', 'dtype']
    sorted_config = {}
    for ind_key in config:
        # GEÄNDERT: _stops / _stops_pos separat behandeln, nicht als Indikator
        if str(ind_key).startswith('_'):
            continue
        ind = config[ind_key]
        sorted_ind = {}
        # Meta-Felder zuerst (nur wenn vorhanden)
        for k in meta_keys:
            if k in ind:
                sorted_ind[k] = ind[k]
        # Dann Parameter und sonstige Felder
        for k in ind:
            if k in meta_keys:
                continue
            val = ind[k]
            if isinstance(val, dict) and 'start' in val:
                sorted_param = {}
                for pk in param_key_order:
                    if pk in val:
                        sorted_param[pk] = val[pk]
                # Unbekannte Felder anhängen
                for pk in val:
                    if pk not in sorted_param:
                        sorted_param[pk] = val[pk]
                sorted_ind[k] = sorted_param
            else:
                sorted_ind[k] = val
        sorted_config[ind_key] = sorted_ind
    # GEÄNDERT: _stops als Sonderblock ans Ende — kanonische innere Reihenfolge,
    # Range-Dicts der Stop-Werte wie Indikator-Params nach start/stop/step/type/dtype sortieren
    stops = config.get('_stops')
    if isinstance(stops, dict):
        sorted_stops = {}
        for sk in _STOPS_KEY_ORDER:
            if sk not in stops:
                continue
            sval = stops[sk]
            if isinstance(sval, dict) and 'start' in sval:
                sorted_range = {}
                for pk in param_key_order:
                    if pk in sval:
                        sorted_range[pk] = sval[pk]
                for pk in sval:
                    if pk not in sorted_range:
                        sorted_range[pk] = sval[pk]
                sorted_stops[sk] = sorted_range
            else:
                sorted_stops[sk] = sval
        # Etwaige unbekannte Zusatz-Keys aus _stops nicht verlieren
        for ek in stops:
            if ek not in sorted_stops:
                sorted_stops[ek] = stops[ek]
        sorted_config['_stops'] = sorted_stops
    # GEÄNDERT: _stops_pos wird NICHT mehr ausgegeben — gehört nicht in eine Indikator-Config.
    # Der _-Skip oben verhindert weiterhin, dass ein evtl. (legacy) vorhandener Wert crasht.
    return sorted_config

router = APIRouter(prefix='/config', tags=['config-views'])


@router.get('/backtest', response_class=HTMLResponse)
def backtest_configs_page(request: Request) -> HTMLResponse:
    """Backtest-Configs Übersicht — DataTable lädt per AJAX."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='config/backtest_configs.html',
        context={'active_nav': 'config_backtest'},
    )


@router.get('/data', response_class=HTMLResponse)
def data_files_page(request: Request) -> HTMLResponse:
    """OHLC-Daten verwalten: Dateien ansehen, Symbole herunterladen/updaten/löschen."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='config/data_files.html',
        context={'active_nav': 'config_data'},
    )


@router.get('/backtest/new', response_class=HTMLResponse)
def backtest_config_new_page(request: Request) -> HTMLResponse:
    """Neue Backtest-Config anlegen."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='config/backtest_config_edit.html',
        context={'active_nav': 'config_backtest', 'config': None},
    )


@router.get('/backtest/{config_id}', response_class=HTMLResponse)
def backtest_config_edit_page(request: Request, config_id: int) -> HTMLResponse:
    """Bestehende Backtest-Config bearbeiten."""
    session = get_session()
    try:
        config = session.query(BacktestConfig).filter(BacktestConfig.id == config_id).first()
        if not config:
            return HTMLResponse('<h1>Config nicht gefunden</h1>', status_code=404)
        config_data = {
            'id': config.id,
            'name': config.name,
            'description': config.description,
            'symbol': config.symbol,
            'exchange': config.exchange,
            'timeframe': config.timeframe,
            'start': config.start,
            'end': config.end,
            'ohlc_start': config.ohlc_start,
            'ohlc_end': config.ohlc_end,
            'size': config.size,
            'size_type': config.size_type,
            'init_cash': config.init_cash,
            'fees': config.fees,
            # GEÄNDERT: Schritt 3d — Stop-Formate aus BacktestConfig entfernt
            # (leben jetzt in indicators_json['_stops']).
            # GEÄNDERT: is_favorite wird nur über den Tabellen-Stern getoggelt,
            # nicht im Edit-Formular — daher hier nicht mehr im Kontext.
        }
    finally:
        session.close()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='config/backtest_config_edit.html',
        context={'active_nav': 'config_backtest', 'config': config_data},
    )


# ============================================================================
# Indicator-Configs
# ============================================================================

@router.get('/indicator', response_class=HTMLResponse)
def indicator_configs_page(request: Request) -> HTMLResponse:
    """Indicator-Configs Übersicht — DataTable lädt per AJAX."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='config/indicator_configs.html',
        context={'active_nav': 'config_indicator'},
    )


@router.get('/indicator/new', response_class=HTMLResponse)
def indicator_config_new_page(request: Request) -> HTMLResponse:
    """Neue Indicator-Config anlegen."""
    templates = request.app.state.templates
    # GEÄNDERT: leere Config mit Default-Stops vorbelegen, damit die Stops direkt im JSON stehen
    config_json_str = json.dumps(
        _sort_indicator_config(_ensure_stops({})), indent=2, ensure_ascii=False
    )
    return templates.TemplateResponse(
        request=request,
        name='config/indicator_config_edit.html',
        context={'active_nav': 'config_indicator', 'config': None, 'config_json_str': config_json_str},
    )


@router.get('/indicator/{config_id}', response_class=HTMLResponse)
def indicator_config_edit_page(request: Request, config_id: int) -> HTMLResponse:
    """Bestehende Indicator-Config bearbeiten."""
    session = get_session()
    try:
        config = session.query(IndicatorConfig).filter(IndicatorConfig.id == config_id).first()
        if not config:
            return HTMLResponse('<h1>Config nicht gefunden</h1>', status_code=404)
        config_data = {
            'id': config.id,
            'name': config.name,
            'description': config.description,
            'config_json': config.config_json,
            'is_default': config.is_default,
            # GEÄNDERT: Ticket 22 — Concept/Iteration-Verknüpfung an Template übergeben
            'strategy_concept_id': config.strategy_concept_id,
            'strategy_iteration_id': config.strategy_iteration_id,
        }
        # GEÄNDERT: Default-Stops injizieren, damit das JSON die Stops direkt zeigt
        config_json_str = json.dumps(
            _sort_indicator_config(_ensure_stops(config.config_json)), indent=2, ensure_ascii=False
        )
    finally:
        session.close()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='config/indicator_config_edit.html',
        context={'active_nav': 'config_indicator', 'config': config_data, 'config_json_str': config_json_str},
    )


# ============================================================================
# Chart-Playground-Setups (DataTable-Verwaltung)
# ============================================================================

@router.get('/playground', response_class=HTMLResponse)
def playground_setups_page(request: Request) -> HTMLResponse:
    """Playground-Setups Übersicht — DataTable lädt per AJAX."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='config/playground_setups.html',
        context={'active_nav': 'config_playground'},
    )


@router.get('/playground/new', response_class=HTMLResponse)
def playground_setup_new_page(request: Request) -> HTMLResponse:
    """Neues Playground-Setup anlegen."""
    templates = request.app.state.templates
    empty_json = '{}'
    return templates.TemplateResponse(
        request=request,
        name='config/playground_setup_edit.html',
        context={
            'active_nav': 'config_playground',
            'setup': None,
            'backtest_config_json_str': empty_json,
            'indicators_config_json_str': empty_json,
            'strategy_config_json_str': empty_json,
            'ui_state_json_str': empty_json,
        },
    )


@router.get('/playground/{setup_id}', response_class=HTMLResponse)
def playground_setup_edit_page(request: Request, setup_id: int) -> HTMLResponse:
    """Bestehendes Playground-Setup bearbeiten."""
    session = get_session()
    try:
        setup = session.query(ChartPlaygroundSetup).filter(ChartPlaygroundSetup.id == setup_id).first()
        if not setup:
            return HTMLResponse('<h1>Setup nicht gefunden</h1>', status_code=404)
        setup_data = {
            'id': setup.id,
            'name': setup.name,
            'description': setup.description,
            'created_at': setup.created_at.isoformat() if setup.created_at else None,
            'updated_at': setup.updated_at.isoformat() if setup.updated_at else None,
        }
        bt_str = json.dumps(setup.backtest_config_json or {}, indent=2, ensure_ascii=False)
        ind_str = json.dumps(setup.indicators_config_json or {}, indent=2, ensure_ascii=False)
        strat_str = json.dumps(setup.strategy_config_json or {}, indent=2, ensure_ascii=False)
        ui_str = json.dumps(setup.ui_state_json or {}, indent=2, ensure_ascii=False)
    finally:
        session.close()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='config/playground_setup_edit.html',
        context={
            'active_nav': 'config_playground',
            'setup': setup_data,
            'backtest_config_json_str': bt_str,
            'indicators_config_json_str': ind_str,
            'strategy_config_json_str': strat_str,
            'ui_state_json_str': ui_str,
        },
    )


# ============================================================================
# Strategie-Konzepte (GEÄNDERT: Ticket 11 — zweistufige Ansicht Concepts -> Iterations)
# ============================================================================

@router.get('/strategy-concepts', response_class=HTMLResponse)
def strategy_concepts_page(request: Request) -> HTMLResponse:
    """Strategie-Konzepte Übersicht — DataTable lädt per AJAX von /api/strategy/concepts."""
    templates = request.app.state.templates
    # GEÄNDERT: Vault-Name aus Env-Variable für konfigurierbare Obsidian-Links
    obsidian_vault_name = os.environ.get('OBSIDIAN_VAULT_NAME', 'vault')
    return templates.TemplateResponse(
        request=request,
        name='config/strategy_concepts.html',
        context={
            'active_nav': 'strategy_concepts',
            'obsidian_vault_name': obsidian_vault_name,
        },
    )


@router.get('/strategy-concepts/{concept_id}/iterations/new', response_class=HTMLResponse)
def strategy_iteration_new_page(request: Request, concept_id: int) -> HTMLResponse:
    """Neue Iteration anlegen."""
    session = get_session()
    try:
        concept = session.query(StrategyConcept).filter(StrategyConcept.id == concept_id).first()
        if not concept:
            return HTMLResponse('<h1>Konzept nicht gefunden</h1>', status_code=404)
        concept_data = {'id': concept.id, 'slug': concept.slug, 'name': concept.name}
    finally:
        session.close()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='config/strategy_iteration_edit.html',
        context={
            'active_nav': 'strategy_concepts',
            'concept': concept_data,
            'iteration': None,
            'spec_json_str': '',
        },
    )


@router.get('/strategy-concepts/{concept_id}/iterations/{iteration_id}/edit', response_class=HTMLResponse)
def strategy_iteration_edit_page(request: Request, concept_id: int, iteration_id: int) -> HTMLResponse:
    """Iteration bearbeiten."""
    session = get_session()
    try:
        concept = session.query(StrategyConcept).filter(StrategyConcept.id == concept_id).first()
        iteration = session.query(StrategyIteration).filter(StrategyIteration.id == iteration_id).first()
        if not concept or not iteration:
            return HTMLResponse('<h1>Nicht gefunden</h1>', status_code=404)
        concept_data = {'id': concept.id, 'slug': concept.slug, 'name': concept.name}
        # GEÄNDERT: Ticket 16 — obsidian_path entfernt; vault_exists live aus Filesystem
        iteration_data = {
            'id': iteration.id,
            'concept_id': iteration.concept_id,
            'version': iteration.version,
            # GEÄNDERT: version_name für Edit-Form-Vorbelegung
            'version_name': iteration.version_name,
            'status': iteration.status,
            'type': iteration.type,
            'import_path': iteration.import_path,
            'parent_iteration_id': iteration.parent_iteration_id,
            'vault_exists': iteration_md_path(concept.slug, iteration.version).exists(),
            'created_by': iteration.created_by,
            'description': iteration.description,
            'spec_json': iteration.spec_json,
            'is_favorite': bool(iteration.is_favorite),
            # GEÄNDERT: Doku-Favoriten-Flag für Iteration-Edit-Template
            'is_doc_favorite': bool(iteration.is_doc_favorite),
        }
        spec_json_str = json.dumps(iteration.spec_json, indent=2, ensure_ascii=False) if iteration.spec_json else ''
    finally:
        session.close()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='config/strategy_iteration_edit.html',
        context={
            'active_nav': 'strategy_concepts',
            'concept': concept_data,
            'iteration': iteration_data,
            'spec_json_str': spec_json_str,
        },
    )

