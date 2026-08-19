"""
HTML-Seiten für Konfiguration

GET /config/backtest              — Backtest-Configs Übersicht
GET /config/backtest/new          — Neue Backtest-Config anlegen
GET /config/backtest/{id}         — Backtest-Config bearbeiten
GET /config/indicator             — Indicator-Configs Übersicht
GET /config/indicator/new         — Neue Indicator-Config anlegen
GET /config/indicator/{id}        — Indicator-Config bearbeiten
GET /config/strategy-concepts     — Strategie-Konzepte Übersicht
GET /backtest/start               — Backtest starten (Config + Indicator auswahelen)
GET /config/strategy-concepts/{concept_id}/iterations/{iteration_id}/log — Iterations-Log,
                                     read-only
GET /config/strategy-concepts/{concept_id} — Konzept-Detailseite: Ziel neben
                                     Befund-Historie, read-only
"""

import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import json

from services.api.routes.api_testset_run_findings import list_findings_for_concept
from services.api.utils.best_criteria_labels import BEST_CRITERIA_LABELS
from services.api.utils.obsidian_paths import (
    concept_md_path,
    iteration_md_path,
    strategies_base_rel,
    world_dir_rel,
)
from user_data.utils.database.db import get_session
from user_data.utils.database.models import BacktestConfig, BacktestRun, IndicatorConfig, StrategyConfig, StrategyConcept, StrategyIteration, ChartPlaygroundSetup, TestSet
from user_data.utils.database.repository_strategies import list_iteration_logs


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
            # GEÄNDERT: drei Portfolio-Parameter analog fees an den Formular-Kontext
            'slippage': config.slippage,
            'stop_exit_price': config.stop_exit_price,
            'stop_order_type': config.stop_order_type,
            # GEÄNDERT: Ticket 104 — risikobasierte Positionsgröße + Hebel an den Formular-Kontext
            'risk_pct': config.risk_pct,
            'leverage': config.leverage,
            'leverage_mode': config.leverage_mode,
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
            # GEÄNDERT: Concept/Iteration-Verknüpfung an Template übergeben
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
# Strategie-Konzepte (GEÄNDERT: zweistufige Ansicht Concepts -> Iterations)
# ============================================================================

@router.get('/strategy-concepts', response_class=HTMLResponse)
def strategy_concepts_page(request: Request) -> HTMLResponse:
    """Strategie-Konzepte Übersicht — DataTable lädt per AJAX von /api/strategy/concepts."""
    templates = request.app.state.templates
    # GEÄNDERT: Obsidian-Links per absolutem Host-Pfad (obsidian://open?path=) statt Vault-Name.
    # Obsidian ermittelt den Vault selbst aus dem absoluten Pfad — kein separater Vault-Name noetig.
    # Es zaehlt der Windows-Host-Pfad (dort laeuft Obsidian), nicht der Container-Mount /obsidian_vault.
    # Backslashes zu Forward-Slashes normalisieren, damit der Pfad URL-tauglich ist.
    obsidian_vault_base = os.environ.get('OBSIDIAN_VAULT_HOST_PATH', '').replace('\\', '/').rstrip('/')
    return templates.TemplateResponse(
        request=request,
        name='config/strategy_concepts.html',
        context={
            'active_nav': 'strategy_concepts',
            'obsidian_vault_base': obsidian_vault_base,
            # GEÄNDERT: Vault-relative Strategie-Basis aus obsidian_paths — kein Pfad-Hardcoding im JS
            'obsidian_strategies_base': strategies_base_rel(),
            'obsidian_world_dir': world_dir_rel(),
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
        # GEÄNDERT: obsidian_path entfernt; vault_exists live aus Filesystem
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
            # GEÄNDERT: Vault-relative Strategie-Basis für die Pfad-Anzeige im Lösch-Dialog
            'obsidian_strategies_base': strategies_base_rel(),
            'obsidian_world_dir': world_dir_rel(),
        },
    )


# GEÄNDERT: read-only Ansicht des Iterations-Logs (append-only Denkprotokoll)
@router.get('/strategy-concepts/{concept_id}/iterations/{iteration_id}/log', response_class=HTMLResponse)
def strategy_iteration_log_page(request: Request, concept_id: int, iteration_id: int) -> HTMLResponse:
    """Iterations-Log lesen — chronologische, read-only Liste der Log-Einträge.

    Zeigt je Eintrag Zeitstempel, Text und — falls run_id gesetzt und der Run
    noch existiert — einen Link auf den Run. Zeigt der Run-Bezug auf einen
    inzwischen gelöschten Run, wird die ID als reiner Text ohne Link angezeigt.
    """
    session = get_session()
    try:
        concept = session.query(StrategyConcept).filter(StrategyConcept.id == concept_id).first()
        iteration = session.query(StrategyIteration).filter(StrategyIteration.id == iteration_id).first()
        if not concept or not iteration:
            return HTMLResponse('<h1>Nicht gefunden</h1>', status_code=404)

        entries = list_iteration_logs(session, iteration_id) or []
        run_ids = {e.run_id for e in entries if e.run_id is not None}
        existing_run_ids = set()
        if run_ids:
            existing_run_ids = {
                row[0] for row in
                session.query(BacktestRun.id).filter(BacktestRun.id.in_(run_ids)).all()
            }
        log_entries = [
            {
                'id': e.id,
                'created_at': e.created_at,
                'text': e.text,
                'run_id': e.run_id,
                'run_exists': e.run_id in existing_run_ids,
            }
            for e in entries
        ]
        concept_data = {'id': concept.id, 'slug': concept.slug, 'name': concept.name}
        iteration_data = {
            'id': iteration.id,
            'version': iteration.version,
            'version_name': iteration.version_name,
        }
    finally:
        session.close()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='config/strategy_iteration_log.html',
        context={
            'active_nav': 'strategy_concepts',
            'concept': concept_data,
            'iteration': iteration_data,
            'log_entries': log_entries,
        },
    )


def _build_finding_display(finding: dict, iteration, testset_name) -> dict:
    """Bereitet einen einzelnen Befund für die Konzept-Detailseite auf.

    Löst verschachtelte JSON-Blöcke einmalig auf sichere Defaults auf (leeres
    Dict/Liste statt None bei offenen Befunden), damit das Template ohne
    `.get`-Verrenkungen direkt loopen kann. Kein Verdict, keine Wertung — es
    werden ausschließlich vorhandene Felder durchgereicht.

    Args:
        finding: Serialisierter Befund (aus `list_findings_for_concept`).
        iteration: `StrategyIteration`-ORM-Instanz oder None (Iteration gelöscht).
        testset_name: Name des Testsets oder None (Testset gelöscht/unbekannt).

    Returns:
        Anzeige-bereites Dict für das Template.
    """
    scope = finding.get('scope_json') or {}
    candidates = finding.get('candidates_json') or {}
    robustness = finding.get('robustness_json') or {}
    warnings = finding.get('warnings_json') or {}
    interpretation = finding.get('interpretation') or {}
    return {
        'id': finding['id'],
        'created_at': finding['created_at'],
        'closed_at': finding['closed_at'],
        'is_closed': finding['closed_at'] is not None,
        'iteration_exists': iteration is not None,
        'iteration_id': finding['iteration_id'],
        'iteration_label': (iteration.version_name or str(iteration.version)) if iteration else None,
        'iteration_version': iteration.version if iteration else None,
        'testset_id': finding['testset_id'],
        'testset_name': testset_name,
        'planned_n_runs': finding['planned_n_runs'],
        'planned_combos_total': finding['planned_combos_total'],
        'planned_grid_reason': finding['planned_grid_reason'],
        'actual_n_runs': scope.get('n_runs'),
        'actual_combos_total': scope.get('combos_total'),
        'goal_snapshot_json': finding.get('goal_snapshot_json'),
        'goal_missing_reason': finding.get('goal_missing_reason'),
        'candidates_per_run': candidates.get('per_run', []),
        'best_criteria_labels': BEST_CRITERIA_LABELS,
        'dsr_blocks': robustness.get('dsr', []),
        'dsr_hinweis': robustness.get('dsr_hinweis'),
        'warnings_items': warnings.get('items', []),
        'warnings_not_evaluated': warnings.get('not_evaluated', []),
        'interpretation_text': interpretation.get('text'),
        'interpreted_at': interpretation.get('interpreted_at'),
    }


# GEÄNDERT: Konzept-Detailseite: Ziel im Wortlaut neben der chronologischen
# Befund-Historie. Kein Verdict, keine Güte-Sortierung (dieselbe Regel wie am Befund selbst).
@router.get('/strategy-concepts/{concept_id}', response_class=HTMLResponse)
def strategy_concept_detail_page(request: Request, concept_id: int) -> HTMLResponse:
    """Konzept-Detailseite — liest nur.

    Zeigt den Kopf des Konzepts, das Ziel (`goal_prompt` im Wortlaut + lesbar
    formatiertes `goal_json`) sowie die vollständige Befund-Historie
    (chronologisch, `GET /api/testset-run-findings/by-concept`). Bearbeitet wird
    weiterhin ausschließlich in der Übersicht.
    """
    session = get_session()
    try:
        concept = session.query(StrategyConcept).filter(StrategyConcept.id == concept_id).first()
        if not concept:
            return HTMLResponse('<h1>Konzept nicht gefunden</h1>', status_code=404)

        findings = list_findings_for_concept(concept_id)['data']['items']

        # GEÄNDERT: Iteration/Testset sind lose Referenzen — Lookup in Bulk, fehlende
        # Datensätze bleiben None (Befund bleibt trotzdem vollständig lesbar).
        iteration_ids = {f['iteration_id'] for f in findings}
        iterations = {
            row.id: row for row in
            session.query(StrategyIteration).filter(StrategyIteration.id.in_(iteration_ids)).all()
        } if iteration_ids else {}
        testset_ids = {f['testset_id'] for f in findings}
        testset_names = {
            row.id: row.name for row in
            session.query(TestSet).filter(TestSet.id.in_(testset_ids)).all()
        } if testset_ids else {}

        finding_views = [
            _build_finding_display(f, iterations.get(f['iteration_id']), testset_names.get(f['testset_id']))
            for f in findings
        ]

        concept_data = {
            'id': concept.id,
            'slug': concept.slug,
            'name': concept.name,
            'status': concept.status,
            'description': concept.description,
            'goal_prompt': concept.goal_prompt,
            'goal_json': concept.goal_json,
            'goal_json_str': (
                json.dumps(concept.goal_json, indent=2, ensure_ascii=False)
                if concept.goal_json else None
            ),
        }
    finally:
        session.close()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='config/strategy_concept_detail.html',
        context={
            'active_nav': 'strategy_concepts',
            'concept': concept_data,
            'findings': finding_views,
        },
    )

