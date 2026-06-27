"""Ticket 42 — Playground flüchtig aus Result laden (kein Setup anlegen).

Verifiziert:
- get_result_config: liefert korrektes Schema (backtest_config_json, indicators_config_json,
  strategy_config_json, ui_state_json) — identisch zu GET /setups/{id}
- get_result_config: Indikatoren als Dict (Name -> Flat-Spec), nicht Liste
- get_result_config: ui_state_json.selected_configs ist leer (flüchtiger Modus)
- get_result_config: 422 bei fehlendem Snapshot
- get_result_config: 404 bei unbekanntem Result
- get_result_config: kein ChartPlaygroundSetup-Eintrag wird angelegt
- get_result_config: funktioniert ohne Run/Iteration (Daten aus Snapshot)
"""

import sys
import types

import pytest

# rq ist nur im Worker-Container installiert — für reine Tests stubben wir den Import
if 'rq' not in sys.modules:
    rq_stub = types.ModuleType('rq')
    rq_stub.Queue = object
    sys.modules['rq'] = rq_stub

from services.api.routes import api_chart_playground as api_playground_module  # noqa: E402
from user_data.utils.database.models import (  # noqa: E402
    BacktestResult,
    ChartPlaygroundSetup,
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
            },
            'rsi': {
                'indicator': 'vbt:RSI',
                'tf': None,
                'enabled': True,
                'window': 14,
            },
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
def session_pg(test_session, monkeypatch):
    """Session mit Monkeypatch auf api_playground.get_session."""
    monkeypatch.setattr(api_playground_module, 'get_session', lambda: test_session)
    return test_session


# ---------------------------------------------------------------------------
# Tests: get_result_config
# ---------------------------------------------------------------------------

def test_result_config_schema_korrekt(test_engine, monkeypatch):
    """Gültiger Snapshot → Schema identisch zu SetupOut (vier _json-Felder)."""
    from sqlalchemy.orm import sessionmaker as sm

    Session = sm(bind=test_engine)
    s = Session()
    result = _make_result(snapshot=_make_valid_snapshot())
    s.add(result)
    s.commit()
    result_id = result.id
    s.close()

    s2 = Session()
    monkeypatch.setattr(api_playground_module, 'get_session', lambda: s2)

    resp = api_playground_module.get_result_config(result_id)

    assert resp['error'] is None
    data = resp['data']
    # Alle vier Felder vorhanden
    assert 'backtest_config_json' in data
    assert 'indicators_config_json' in data
    assert 'strategy_config_json' in data
    assert 'ui_state_json' in data


def test_result_config_backtest_config_korrekt(test_engine, monkeypatch):
    """backtest_config_json enthält Exchange, Symbol, Timeframe und Portfolio-Felder."""
    from sqlalchemy.orm import sessionmaker as sm

    Session = sm(bind=test_engine)
    s = Session()
    result = _make_result(snapshot=_make_valid_snapshot())
    s.add(result)
    s.commit()
    result_id = result.id
    s.close()

    s2 = Session()
    monkeypatch.setattr(api_playground_module, 'get_session', lambda: s2)

    resp = api_playground_module.get_result_config(result_id)
    bc = resp['data']['backtest_config_json']

    assert bc['exchange'] == 'binance'
    assert bc['timeframe'] == '4h'
    assert bc['symbols'] == ['BTCUSDT']
    assert bc['start'] == '2023-01-01'
    assert bc['end'] == '2024-01-01'
    pf = bc['portfolio']
    assert pf['fees'] == 0.001
    assert pf['size'] == 100
    # GEÄNDERT: Schritt 4d — delta_format/Stops liegen jetzt in indicators_config_json['_stops'],
    # nicht mehr im portfolio-Block (der hält nur size/size_type/init_cash/fees).
    stops = resp['data']['indicators_config_json']['_stops']
    assert stops['delta_format'] == 'percent'


def test_result_config_indikatoren_als_dict(test_engine, monkeypatch):
    """indicators_config_json muss ein Dict sein (Name -> Flat-Spec), nicht Liste.

    applySetupConfig() ruft Object.entries(indCfg) auf — bei Liste kämen Index-Strings
    statt Indikator-Namen.
    """
    from sqlalchemy.orm import sessionmaker as sm

    Session = sm(bind=test_engine)
    s = Session()
    result = _make_result(snapshot=_make_valid_snapshot())
    s.add(result)
    s.commit()
    result_id = result.id
    s.close()

    s2 = Session()
    monkeypatch.setattr(api_playground_module, 'get_session', lambda: s2)

    resp = api_playground_module.get_result_config(result_id)
    ind_cfg = resp['data']['indicators_config_json']

    # Muss Dict sein
    assert isinstance(ind_cfg, dict), f'Erwartet Dict, bekam {type(ind_cfg)}'
    # Indikator-Namen als Keys
    assert 'teststrategie' in ind_cfg
    assert 'rsi' in ind_cfg
    # Flat-Spec korrekt
    assert ind_cfg['teststrategie']['indicator'] == 'custom:dwsVWMA'
    assert ind_cfg['teststrategie']['window'] == 20
    assert ind_cfg['rsi']['indicator'] == 'vbt:RSI'


def test_result_config_selected_configs_leer(test_engine, monkeypatch):
    """ui_state_json.selected_configs ist im flüchtigen Modus leer (alle None).

    Referenzen auf Configs/Iterationen existieren nach Cleanup ggf. nicht mehr.
    """
    from sqlalchemy.orm import sessionmaker as sm

    Session = sm(bind=test_engine)
    s = Session()
    result = _make_result(snapshot=_make_valid_snapshot())
    s.add(result)
    s.commit()
    result_id = result.id
    s.close()

    s2 = Session()
    monkeypatch.setattr(api_playground_module, 'get_session', lambda: s2)

    resp = api_playground_module.get_result_config(result_id)
    sc = resp['data']['ui_state_json']['selected_configs']

    assert sc['iteration_id'] is None
    assert sc['backtest_config_id'] is None
    assert sc['indicator_config_id'] is None


def test_result_config_kein_setup_eintrag(test_engine, monkeypatch):
    """Aufruf von get_result_config legt KEINEN ChartPlaygroundSetup-Eintrag an."""
    from sqlalchemy.orm import sessionmaker as sm

    Session = sm(bind=test_engine)
    s = Session()
    result = _make_result(snapshot=_make_valid_snapshot())
    s.add(result)
    s.commit()
    result_id = result.id

    count_before = s.query(ChartPlaygroundSetup).count()
    s.close()

    s2 = Session()
    monkeypatch.setattr(api_playground_module, 'get_session', lambda: s2)

    api_playground_module.get_result_config(result_id)

    s3 = Session()
    count_after = s3.query(ChartPlaygroundSetup).count()
    s3.close()

    assert count_after == count_before, (
        f'Erwartet {count_before} Setup-Einträge, nach Aufruf {count_after} — '
        'get_result_config darf KEINEN Setup-Eintrag anlegen'
    )


def test_result_config_422_bei_fehlendem_snapshot(session_pg):
    """Fehlendem Snapshot → 422 mit klarer Meldung."""
    from fastapi import HTTPException

    result = _make_result(snapshot=None)
    session_pg.add(result)
    session_pg.commit()

    with pytest.raises(HTTPException) as exc_info:
        api_playground_module.get_result_config(result.id)

    assert exc_info.value.status_code == 422
    assert 'Snapshot' in exc_info.value.detail or 'snapshot' in exc_info.value.detail.lower()


def test_result_config_404_bei_unbekanntem_result(session_pg):
    """Unbekannte Result-ID → 404."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        api_playground_module.get_result_config(99999)

    assert exc_info.value.status_code == 404
    assert '99999' in exc_info.value.detail


def test_result_config_funktioniert_ohne_run_iteration(test_engine, monkeypatch):
    """Result mit run_id auf nicht-existenten Run → trotzdem erfolgreich.

    Der Endpunkt greift ausschließlich auf den Snapshot zu — kein Run/Iteration-Zugriff.
    """
    from sqlalchemy.orm import sessionmaker as sm

    Session = sm(bind=test_engine)
    s = Session()
    result = BacktestResult(
        run_id=9999,  # existiert nicht in der DB
        params_hash='xyz999',
        actual_params_json={},
        full_config_snapshot_json=_make_valid_snapshot(),
    )
    s.add(result)
    s.commit()
    result_id = result.id
    s.close()

    s2 = Session()
    monkeypatch.setattr(api_playground_module, 'get_session', lambda: s2)

    resp = api_playground_module.get_result_config(result_id)

    assert resp['error'] is None
    assert resp['data']['indicators_config_json'] is not None
