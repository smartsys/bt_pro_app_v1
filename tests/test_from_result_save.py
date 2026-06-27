"""Ticket 43 — Aus Result speichern (vereinheitlicht auf Snapshot).

Verifiziert:
- create_backtest_config_from_result: legt BacktestConfig aus Snapshot an
- create_backtest_config_from_result: 422 bei fehlendem Snapshot
- create_backtest_config_from_result: 404 bei unbekanntem Result
- create_indicator_config_from_result: legt IndicatorConfig aus Snapshot an
- create_indicator_config_from_result: 422 bei fehlendem Snapshot
- create_indicator_config_from_result: funktioniert ohne Run/Iteration (kein Zugriff mehr)
- create_setup_from_result: legt ChartPlaygroundSetup aus Snapshot an
- create_setup_from_result: 422 bei fehlendem Snapshot
"""

import sys
import types

import pytest

# rq ist nur im Worker-Container installiert — für reine Tests stubben wir den Import
if 'rq' not in sys.modules:
    rq_stub = types.ModuleType('rq')
    rq_stub.Queue = object
    sys.modules['rq'] = rq_stub

from services.api.routes import api_config as api_config_module  # noqa: E402
from services.api.routes import api_chart_playground as api_playground_module  # noqa: E402
from user_data.utils.database.models import (  # noqa: E402
    BacktestResult,
    BacktestConfig,
    IndicatorConfig,
)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _make_valid_snapshot() -> dict:
    """Erzeugt einen vollständigen, gültigen Config-Snapshot für Tests."""
    return {
        'backtest_config': {
            'symbol': 'BTCUSDT',
            'exchange': 'binance',
            'timeframe': '4h',
            'start': '2023-01-01',
            'end': '2024-01-01',
            'ohlc_start': '2023-01-01',
            'ohlc_end': '2024-01-01',
            'size': 100,
            'size_type': 'value',
            'init_cash': 100,
            'fees': 0.001,
            'tp_stop': None,
            'sl_stop': None,
            'tsl_th': None,
            'tsl_stop': None,
            'td_stop': None,
            'delta_format': 'percent',
            'time_delta_format': 'rows',
        },
        'indicators': {
            'teststrategie': {
                'indicator': 'custom:dwsVWMA',
                'tf': None,
                'enabled': True,
                'window': 20,
            }
        },
        'rules': {
            'entry': [{'type': 'signal', 'source': 'teststrategie', 'field': 'entry'}],
            'exit': [{'type': 'signal', 'source': 'teststrategie', 'field': 'exit'}],
        },
    }


def _make_result(snapshot: dict | None = None) -> BacktestResult:
    """Erzeugt ein minimales BacktestResult mit optionalem Snapshot."""
    return BacktestResult(
        run_id=1,
        params_hash='abc123',
        actual_params_json={},
        full_config_snapshot_json=snapshot,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def session_bc(test_session, monkeypatch):
    """Session mit Monkeypatch auf api_config.get_session."""
    monkeypatch.setattr(api_config_module, 'get_session', lambda: test_session)
    return test_session


@pytest.fixture
def session_pg(test_session, monkeypatch):
    """Session mit Monkeypatch auf api_playground.get_session."""
    monkeypatch.setattr(api_playground_module, 'get_session', lambda: test_session)
    return test_session


# ---------------------------------------------------------------------------
# Tests: create_backtest_config_from_result
# ---------------------------------------------------------------------------

def test_backtest_config_from_result_legt_config_an(test_engine, monkeypatch):
    """Gültiger Snapshot → BacktestConfig wird korrekt angelegt."""
    from sqlalchemy.orm import sessionmaker as sm

    # Session vorab aufbauen, result einfügen, Session schließen
    Session = sm(bind=test_engine)
    s = Session()
    result = _make_result(snapshot=_make_valid_snapshot())
    s.add(result)
    s.commit()
    result_id = result.id
    s.close()

    # Neue Session für den Endpunkt-Aufruf (Endpunkt schließt sie selbst)
    s2 = Session()
    monkeypatch.setattr(api_config_module, 'get_session', lambda: s2)

    resp = api_config_module.create_backtest_config_from_result(result_id)

    assert resp['error'] is None
    data = resp['data']
    assert data['symbol'] == 'BTCUSDT'
    assert data['timeframe'] == '4h'
    # GEÄNDERT: Schritt 3d — delta_format ist kein BacktestConfig-Feld mehr
    # (lebt jetzt in der IndicatorConfig '_stops'), daher kein Assert hier.
    assert data['ohlc_start'] == '2023-01-01'
    assert f'Result {result_id}' in data['name']

    # Datenbankprüfung: Config wirklich gespeichert
    s3 = Session()
    saved = s3.query(BacktestConfig).filter(BacktestConfig.id == data['id']).first()
    assert saved is not None
    assert saved.symbol == 'BTCUSDT'
    s3.close()


def test_backtest_config_from_result_422_bei_fehlendem_snapshot(session_bc):
    """Fehlendem Snapshot → 422 mit klarer Meldung."""
    result = _make_result(snapshot=None)
    session_bc.add(result)
    session_bc.commit()

    from fastapi.responses import JSONResponse
    resp = api_config_module.create_backtest_config_from_result(result.id)

    # Funktion gibt JSONResponse oder Dict zurück
    if isinstance(resp, JSONResponse):
        import json
        body = json.loads(resp.body)
        assert resp.status_code == 422
        assert body['error'] is not None
        assert 'Snapshot' in body['error'] or 'snapshot' in body['error'].lower()
    else:
        # Sollte nie hier ankommen — oben schlägt es schon mit JSONResponse fehl
        assert False, f'Erwartete JSONResponse, bekam: {resp}'


def test_backtest_config_from_result_404_bei_unbekanntem_result(session_bc):
    """Unbekannte Result-ID → 404."""
    from fastapi.responses import JSONResponse
    resp = api_config_module.create_backtest_config_from_result(9999)

    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 404
    import json
    body = json.loads(resp.body)
    assert body['error'] is not None
    assert '9999' in body['error']


# ---------------------------------------------------------------------------
# Tests: create_indicator_config_from_result
# ---------------------------------------------------------------------------

def test_indicator_config_from_result_legt_config_an(test_engine, monkeypatch):
    """Gültiger Snapshot → IndicatorConfig wird angelegt, kein Run/Iteration-Zugriff."""
    from sqlalchemy.orm import sessionmaker as sm

    Session = sm(bind=test_engine)
    s = Session()
    result = _make_result(snapshot=_make_valid_snapshot())
    s.add(result)
    s.commit()
    result_id = result.id
    s.close()

    s2 = Session()
    monkeypatch.setattr(api_config_module, 'get_session', lambda: s2)

    # body=None direkt übergeben — bei direktem Aufruf außerhalb FastAPI kein Body()-Marker
    resp = api_config_module.create_indicator_config_from_result(result_id, body=None)

    assert resp['error'] is None
    data = resp['data']
    # GEÄNDERT: Schritt 3b/3d — from-result übernimmt die Stops UND die Stop-Formate
    # aus dem Snapshot-backtest_config als '_stops'-Meta-Key in die eingefrorene Config.
    assert data['config_json'] == {
        'teststrategie': {'indicator': 'custom:dwsVWMA', 'tf': None, 'enabled': True, 'window': 20},
        '_stops': {
            'tp_stop': None, 'sl_stop': None, 'tsl_th': None, 'tsl_stop': None, 'td_stop': None,
            'delta_format': 'percent', 'time_delta_format': 'rows',
        },
    }
    # Kein Concept/Iteration-Bezug aus Snapshot
    assert data['strategy_concept_id'] is None
    assert data['strategy_iteration_id'] is None
    assert data['id'] is not None


def test_indicator_config_from_result_422_bei_fehlendem_snapshot(session_bc):
    """Fehlendem Snapshot → 422."""
    result = _make_result(snapshot=None)
    session_bc.add(result)
    session_bc.commit()

    from fastapi.responses import JSONResponse
    resp = api_config_module.create_indicator_config_from_result(result.id, body=None)

    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 422


def test_indicator_config_from_result_funktioniert_ohne_run_iteration(test_engine, monkeypatch):
    """Result ohne Run/Iteration (run_id verweist auf nichts) → trotzdem erfolgreich.

    Der neue Code greift NIE auf Run oder Iteration zu — nur auf den Snapshot.
    """
    from sqlalchemy.orm import sessionmaker as sm

    Session = sm(bind=test_engine)
    s = Session()
    # Result mit run_id=9999 (existiert nicht in der DB) — kein Problem mehr
    result = BacktestResult(
        run_id=9999,
        params_hash='xyz999',
        actual_params_json={},
        full_config_snapshot_json=_make_valid_snapshot(),
    )
    s.add(result)
    s.commit()
    result_id = result.id
    s.close()

    s2 = Session()
    monkeypatch.setattr(api_config_module, 'get_session', lambda: s2)
    resp = api_config_module.create_indicator_config_from_result(result_id, body=None)

    # Kein Fehler — Run wird nicht mehr abgefragt
    assert resp['error'] is None
    assert resp['data']['config_json'] is not None


# ---------------------------------------------------------------------------
# Tests: create_setup_from_result (api_chart_playground)
# ---------------------------------------------------------------------------

def test_setup_from_result_legt_setup_an(test_engine, monkeypatch):
    """Gültiger Snapshot → ChartPlaygroundSetup wird angelegt."""
    from sqlalchemy.orm import sessionmaker as sm
    from user_data.utils.database.models import ChartPlaygroundSetup

    Session = sm(bind=test_engine)
    s = Session()
    result = _make_result(snapshot=_make_valid_snapshot())
    s.add(result)
    s.commit()
    result_id = result.id
    s.close()

    s2 = Session()
    monkeypatch.setattr(api_playground_module, 'get_session', lambda: s2)

    resp = api_playground_module.create_setup_from_result(result_id)

    assert resp['error'] is None
    data = resp['data']
    assert data['setup_id'] is not None
    assert 'BTCUSDT' in data['name']
    assert f'/chart-playground?setupid={data["setup_id"]}' == data['url']

    # Datenbankprüfung mit neuer Session
    s3 = Session()
    saved = s3.query(ChartPlaygroundSetup).filter(ChartPlaygroundSetup.id == data['setup_id']).first()
    assert saved is not None
    assert saved.backtest_config_json['symbols'] == ['BTCUSDT']
    assert saved.strategy_config_json['concept_slug'] is None
    s3.close()


def test_setup_from_result_422_bei_fehlendem_snapshot(test_engine, monkeypatch):
    """Fehlendem Snapshot → 422 (HTTPException)."""
    from fastapi import HTTPException
    from sqlalchemy.orm import sessionmaker as sm

    Session = sm(bind=test_engine)
    s = Session()
    result = _make_result(snapshot=None)
    s.add(result)
    s.commit()
    result_id = result.id
    s.close()

    s2 = Session()
    monkeypatch.setattr(api_playground_module, 'get_session', lambda: s2)

    with pytest.raises(HTTPException) as exc_info:
        api_playground_module.create_setup_from_result(result_id)

    assert exc_info.value.status_code == 422
    assert 'Snapshot' in exc_info.value.detail or 'snapshot' in exc_info.value.detail.lower()
