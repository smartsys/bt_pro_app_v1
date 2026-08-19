"""Raster-Quelle für Testset-Lauf und Preflight: gespeicherte Config oder inline.

Geprüft wird an drei Stellen dieselbe Regel:
  - Startroute ``POST /api/testset-runs``: beide Varianten rechnen, inline erzeugt keine
    IndicatorConfig-Zeile und der Befund trägt ``indicator_config_id = NULL``.
  - Preflight ``POST /api/chart-playground/preflight``: beide Varianten liefern denselben
    Bericht (gleiche Kombinationszahl, gleiche Signalzahlen).
  - Genau-eines-Regel: beide Angaben oder keine enden mit HTTP 400 bzw. — in der Toolbox —
    mit Exit-Code ungleich 0 und Klartext-Grund.

Die schweren Bausteine des Preflights (OHLC laden, Indikatoren bauen, Rechnen) sind
gemockt; die Kombinationszählung läuft echt über ``count_total_combos``, damit belegt ist,
dass tatsächlich das übergebene Raster gezählt wird.
"""

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from user_data.utils.database.models import (
    BacktestConfig,
    IndicatorConfig,
    StrategyConcept,
    StrategyIteration,
    TestSet,
)

_TOOLBOX_PATH = (
    Path(__file__).resolve().parent.parent
    / '.claude' / 'skills' / 'ds-strategie-session' / 'scripts' / 'toolbox.py'
)

# Raster mit zwei Achsen: 13 x 9 = 117 Kombinationen (siehe _FACTORY_MOCK).
_RASTER = {
    'sma': {
        'indicator': 'custom:SMA',
        'tf': '4h',
        'source': 'close',
        'length': {'type': 'arange', 'start': 2, 'stop': 14.01, 'step': 1, 'dtype': 'int64'},
        'multiplier': {'type': 'arange', 'start': 1, 'stop': 9.01, 'step': 1, 'dtype': 'int64'},
    }
}
_RASTER_COMBOS = 13 * 9

# Factory-Attrappe für die Kombinationszählung: 'source' ist ein Input (zählt nie),
# 'length'/'multiplier' sind Parameter-Achsen.
_FACTORY_MOCK = MagicMock()
_FACTORY_MOCK.input_names = ('source',)
_FACTORY_MOCK.param_names = ('length', 'multiplier')
_FACTORY_PATCH_TARGET = 'user_data.strategies.generic.indicator_factory.resolve_indicator_factory'

_SPEC_JSON = {
    'indicators': _RASTER,
    'rules': {
        'entry': {'blocks': [{'conditions': [{'left': 'sma.real', 'op': '>', 'right': 'close'}]}]},
        'exit': None,
    },
}


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope='function')
def stammdaten(session) -> dict:
    """Konzept, Iteration, BacktestConfig, TestSet und eine IndicatorConfig — committet.

    Committet, weil die Routen ihre Sessions selbst schliessen: uncommittete
    Fixture-Zeilen wären nach dem ersten ``close()`` verschwunden.
    """
    concept = StrategyConcept(slug='raster-quelle', name='Raster-Quelle', goal_json={'sharpe_min': 1.0})
    session.add(concept)
    session.flush()

    iteration = StrategyIteration(
        concept_id=concept.id,
        version=1,
        type='generic',
        spec_json=_SPEC_JSON,
    )
    session.add(iteration)

    bt = BacktestConfig(
        name='Raster-Quelle-BC',
        symbol='BTCUSDT',
        exchange='binance',
        timeframe='4h',
        start='2024-01-01',
        end='2024-12-31',
        ohlc_start='2023-12-01',
        ohlc_end='2025-01-01',
    )
    session.add(bt)
    session.flush()

    testset = TestSet(name='Raster-Quelle-TS', backtest_config_ids_json=[bt.id])
    session.add(testset)

    ind_cfg = IndicatorConfig(name='Raster-Quelle-IC', config_json=_RASTER)
    session.add(ind_cfg)
    session.commit()

    return {
        'concept_id': concept.id,
        'iteration_id': iteration.id,
        'backtest_config_id': bt.id,
        'testset_id': testset.id,
        'indicator_config_id': ind_cfg.id,
    }


@pytest.fixture(scope='module')
def toolbox():
    """Lädt toolbox.py als Modul (Ordnername enthält Bindestriche -> kein Package-Import)."""
    spec = importlib.util.spec_from_file_location('toolbox', _TOOLBOX_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules['toolbox'] = module
    spec.loader.exec_module(module)
    return module


# ============================================================================
# Startroute POST /api/testset-runs
# ============================================================================

def _start_testset_run(db_engine, payload):
    """Ruft die Startroute mit echter Test-DB, aber ohne Queue und ohne Run-Anlage."""
    from services.api.routes.api_testset_runs import start_testset_run

    SessionFactory = sessionmaker(bind=db_engine)
    created_runs: list = []

    def _fake_create_backtest_run(**kwargs):
        created_runs.append(kwargs)
        return 1000 + len(created_runs)

    with patch('services.api.routes.api_testset_runs.get_session', side_effect=SessionFactory), \
         patch('services.api.routes.api_testset_runs.create_backtest_run',
               side_effect=_fake_create_backtest_run), \
         patch('rq.Queue', MagicMock()), \
         patch('services.api.redis_conn.get_redis_connection', MagicMock()), \
         patch(_FACTORY_PATCH_TARGET, return_value=_FACTORY_MOCK):
        response = start_testset_run(payload)

    return response, created_runs


def test_testset_run_start_inline_raster_creates_no_indicator_config(db_engine, session, stammdaten):
    """Inline-Raster startet den Lauf, ohne eine IndicatorConfig anzulegen."""
    from services.api.routes.api_testset_runs import TestSetRunIn

    before = session.query(IndicatorConfig).count()

    payload = TestSetRunIn(
        testset_id=stammdaten['testset_id'],
        iteration_id=stammdaten['iteration_id'],
        indicators=_RASTER,
    )
    response, created_runs = _start_testset_run(db_engine, payload)

    assert response.status_code == 200
    data = json.loads(response.body)['data']
    assert len(data['run_ids']) == 1

    # Kein neues Namensschild in der Datenbank.
    assert session.query(IndicatorConfig).count() == before

    with db_engine.connect() as conn:
        run_row = conn.execute(
            text('SELECT indicators_config_json FROM testset_runs WHERE id = :id'),
            {'id': data['testset_run_id']},
        ).fetchone()
        assert run_row[0] == _RASTER

        finding = conn.execute(
            text('SELECT indicator_config_id, iteration_id, concept_id, goal_snapshot_json, '
                 'planned_combos_per_run FROM testset_run_findings WHERE testset_run_id = :id'),
            {'id': data['testset_run_id']},
        ).fetchone()
    assert finding.indicator_config_id is None
    assert finding.iteration_id == stammdaten['iteration_id']
    assert finding.concept_id == stammdaten['concept_id']
    assert finding.goal_snapshot_json == {'sharpe_min': 1.0}
    assert finding.planned_combos_per_run == _RASTER_COMBOS

    # Auch die erzeugten Runs tragen keine Config-Referenz.
    assert created_runs[0]['indicator_config_id'] is None
    assert created_runs[0]['indicators_config'] == _RASTER


def test_testset_run_start_stored_config_keeps_config_id(db_engine, session, stammdaten):
    """Der bisherige Weg über indicator_config_id bleibt unverändert."""
    from services.api.routes.api_testset_runs import TestSetRunIn

    payload = TestSetRunIn(
        testset_id=stammdaten['testset_id'],
        iteration_id=stammdaten['iteration_id'],
        indicator_config_id=stammdaten['indicator_config_id'],
    )
    response, created_runs = _start_testset_run(db_engine, payload)

    assert response.status_code == 200
    data = json.loads(response.body)['data']

    with db_engine.connect() as conn:
        finding = conn.execute(
            text('SELECT indicator_config_id FROM testset_run_findings WHERE testset_run_id = :id'),
            {'id': data['testset_run_id']},
        ).fetchone()
    assert finding.indicator_config_id == stammdaten['indicator_config_id']
    assert created_runs[0]['indicator_config_id'] == stammdaten['indicator_config_id']
    assert created_runs[0]['indicators_config'] == _RASTER


def test_testset_run_start_rejects_both_raster_sources():
    """Config-ID und Inline-Raster zusammen: 400 mit Klartext-Grund, kein Vorrang."""
    from services.api.routes.api_testset_runs import TestSetRunIn, start_testset_run

    payload = TestSetRunIn(
        testset_id=1, iteration_id=1, indicator_config_id=1, indicators=_RASTER,
    )
    response = start_testset_run(payload)

    assert response.status_code == 400
    assert 'schließen sich aus' in json.loads(response.body)['error']


def test_testset_run_start_rejects_missing_raster_source():
    """Weder Config-ID noch Inline-Raster: 400 mit Klartext-Grund."""
    from services.api.routes.api_testset_runs import TestSetRunIn, start_testset_run

    payload = TestSetRunIn(testset_id=1, iteration_id=1)
    response = start_testset_run(payload)

    assert response.status_code == 400
    assert 'Indikator-Raster' in json.loads(response.body)['error']


# ============================================================================
# Preflight POST /api/chart-playground/preflight
# ============================================================================

_SIGNAL_SUMMARY = {'count': 42, 'first_time': '2024-02-01', 'last_time': '2024-11-30', 'note': None}


def _preflight(db_engine, req):
    """Ruft den Preflight mit echter Test-DB; Laden/Bauen/Rechnen sind gemockt."""
    from services.api.routes.api_chart_playground import preflight

    SessionFactory = sessionmaker(bind=db_engine)

    with patch('services.api.routes.api_chart_playground.get_session', side_effect=SessionFactory), \
         patch('user_data.utils.ohlc.loader.load_ohlc_data', MagicMock()), \
         patch('user_data.strategies.generic.indicator_factory.build_indicators', MagicMock()), \
         patch('user_data.strategies.generic.spec_runner.run_spec_strategy', MagicMock()), \
         patch('user_data.strategies.generic.warmup.check_warmup',
               return_value={'level': 'ok', 'note': 'Vorlauf reicht'}), \
         patch('services.api.routes.api_chart_playground._preflight_nan_ratios', return_value={}), \
         patch('services.api.routes.api_chart_playground._preflight_signal_counts',
               return_value=(_SIGNAL_SUMMARY, _SIGNAL_SUMMARY)), \
         patch(_FACTORY_PATCH_TARGET, return_value=_FACTORY_MOCK):
        return preflight(req)


def test_preflight_inline_raster_reports_like_stored_config(db_engine, stammdaten):
    """Inline und gespeicherte Config liefern denselben Bericht auf demselben Raster."""
    from services.api.routes.api_chart_playground import PreflightIn

    inline = _preflight(db_engine, PreflightIn(
        iteration_id=stammdaten['iteration_id'],
        backtest_config_id=stammdaten['backtest_config_id'],
        indicators=_RASTER,
    ))['data']
    stored = _preflight(db_engine, PreflightIn(
        iteration_id=stammdaten['iteration_id'],
        backtest_config_id=stammdaten['backtest_config_id'],
        indicator_config_id=stammdaten['indicator_config_id'],
    ))['data']

    assert inline['n_combinations'] == _RASTER_COMBOS
    assert inline['n_combinations'] == stored['n_combinations']
    assert inline['entry_signals'] == stored['entry_signals']
    assert inline['exit_signals'] == stored['exit_signals']
    assert inline['warmup'] == stored['warmup']
    # Einziger Unterschied: die Herkunft des Rasters.
    assert inline['indicator_config_id'] is None
    assert stored['indicator_config_id'] == stammdaten['indicator_config_id']


def test_preflight_rejects_both_raster_sources():
    """Config-ID und Inline-Raster zusammen: HTTP 400 mit Klartext-Grund."""
    from fastapi import HTTPException

    from services.api.routes.api_chart_playground import PreflightIn, preflight

    req = PreflightIn(
        iteration_id=1, backtest_config_id=1, indicator_config_id=1, indicators=_RASTER,
    )
    with pytest.raises(HTTPException) as exc:
        preflight(req)
    assert exc.value.status_code == 400
    assert 'schließen sich aus' in exc.value.detail


def test_preflight_rejects_missing_raster_source():
    """Weder Config-ID noch Inline-Raster: HTTP 400 mit Klartext-Grund."""
    from fastapi import HTTPException

    from services.api.routes.api_chart_playground import PreflightIn, preflight

    req = PreflightIn(iteration_id=1, backtest_config_id=1)
    with pytest.raises(HTTPException) as exc:
        preflight(req)
    assert exc.value.status_code == 400
    assert 'Indikator-Raster' in exc.value.detail


# ============================================================================
# Toolbox-Verben testset-run-start und preflight
# ============================================================================

def _raster_file(tmp_path: Path) -> str:
    path = tmp_path / 'raster.json'
    path.write_text(json.dumps(_RASTER), encoding='utf-8')
    return str(path)


def test_toolbox_testset_run_start_sends_inline_raster(toolbox, tmp_path):
    """--indicators schickt das Raster als indicators-Feld statt einer Config-ID."""
    gesendet: dict = {}

    def _fake_post(path, body, timeout=None):
        gesendet['path'] = path
        gesendet['body'] = body
        return {'data': {'testset_run_id': 7, 'run_ids': [1, 2]}}

    with patch.object(toolbox, 'post', side_effect=_fake_post):
        rc = toolbox.testset_run_start(
            ['--testset', '3', '--iteration', '4', '--indicators', _raster_file(tmp_path)]
        )

    assert rc == 0
    assert gesendet['path'] == '/api/testset-runs'
    assert gesendet['body']['indicators'] == _RASTER
    assert 'indicator_config_id' not in gesendet['body']


def test_toolbox_testset_run_start_sends_config_id(toolbox):
    """--indicator-config schickt weiterhin die ID, ohne indicators-Feld."""
    gesendet: dict = {}

    def _fake_post(path, body, timeout=None):
        gesendet['body'] = body
        return {'data': {'testset_run_id': 7, 'run_ids': [1]}}

    with patch.object(toolbox, 'post', side_effect=_fake_post):
        rc = toolbox.testset_run_start(['--testset', '3', '--iteration', '4', '--indicator-config', '9'])

    assert rc == 0
    assert gesendet['body']['indicator_config_id'] == 9
    assert 'indicators' not in gesendet['body']


def test_toolbox_preflight_sends_inline_raster(toolbox, tmp_path):
    """Preflight kennt dieselbe Alternative und meldet die Inline-Herkunft."""
    gesendet: dict = {}

    def _fake_post(path, body, timeout=None):
        gesendet['body'] = body
        return {'data': {
            'iteration_id': 4, 'indicator_config_id': None, 'backtest_config_id': 5,
            'n_combinations': _RASTER_COMBOS,
            'warmup': {'level': 'ok', 'note': 'Vorlauf reicht'},
            'entry_signals': _SIGNAL_SUMMARY, 'exit_signals': _SIGNAL_SUMMARY,
            'indicator_nan_ratio': {}, 'single_combo_duration_ms': 10,
            'estimated_full_runtime_ms': 1170, 'estimated_full_runtime_note': 'Schätzung',
        }}

    with patch.object(toolbox, 'post', side_effect=_fake_post):
        rc = toolbox.preflight_run(
            ['--iteration', '4', '--backtest-config', '5', '--indicators', _raster_file(tmp_path)]
        )

    assert rc == 0
    assert gesendet['body']['indicators'] == _RASTER
    assert 'indicator_config_id' not in gesendet['body']


@pytest.mark.parametrize('argv', [
    ['toolbox.py', 'testset-run-start', '--testset', '3', '--iteration', '4',
     '--indicator-config', '9', '--indicators', 'raster.json'],
    ['toolbox.py', 'testset-run-start', '--testset', '3', '--iteration', '4'],
    ['toolbox.py', 'preflight', '--iteration', '4', '--backtest-config', '5',
     '--indicator-config', '9', '--indicators', 'raster.json'],
    ['toolbox.py', 'preflight', '--iteration', '4', '--backtest-config', '5'],
])
def test_toolbox_exactly_one_raster_source_required(toolbox, capsys, argv):
    """Beide Angaben oder keine: Exit-Code ungleich 0 und ein Grund im Klartext."""
    with patch.object(sys, 'argv', argv), patch.object(toolbox, 'post') as gesendet:
        rc = toolbox.main()

    assert rc != 0
    gesendet.assert_not_called()
    ausgabe = capsys.readouterr().out
    assert 'Raster-Quelle' in ausgabe
