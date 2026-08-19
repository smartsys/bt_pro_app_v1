"""Tests für den Einzel-Run-Endpunkt GET /api/backtest/runs/{run_id}.

Prüft: der Einzel-Endpunkt liefert exakt dieselbe Feldform wie ein Element der
Runs-Liste (beide nutzen _serialize_runs), eine unbekannte ID liefert 404 im
im Modul etablierten Fehlerformat (JSONResponse mit 'error'-Key, nicht
HTTPException/'detail' — siehe die anderen 404-Stellen in api_backtest.py).
"""

import json
import sys
import types
from datetime import datetime

# rq-Familie stubben (nur im Worker-Container installiert), damit api_backtest importierbar ist
for _m in ('rq', 'rq.job', 'rq.registry', 'rq.command'):
    if _m not in sys.modules:
        sys.modules[_m] = types.ModuleType(_m)
sys.modules['rq'].Queue = object
sys.modules['rq.job'].Job = object
sys.modules['rq.registry'].StartedJobRegistry = object
sys.modules['rq.command'].send_stop_job_command = lambda *a, **k: None

from sqlalchemy.orm import sessionmaker  # noqa: E402

from services.api.routes import api_backtest as api_backtest_module  # noqa: E402
from user_data.utils.database.models import BacktestRun  # noqa: E402


_BACKTEST_CONFIG = {
    'strategy_family': 'test_family',
    'strategy_name': 'test_strategy',
    'symbols': ['BTCUSDT'],
    'exchange': 'binance',
    'timeframe': '4h',
    'start': '2024-01-01',
    'end': '2024-12-31',
}


def _make_run(session) -> int:
    """Minimalen BacktestRun in die Test-DB schreiben, gibt die id zurück."""
    run = BacktestRun(
        strategy_family='test_family',
        strategy_name='test_strategy',
        symbol='BTCUSDT',
        exchange='binance',
        timeframe='4h',
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
        backtest_config_json=_BACKTEST_CONFIG,
        indicators_config_json={},
        n_combinations=1,
        status='completed',
    )
    session.add(run)
    session.commit()
    return run.id


def test_get_run_matches_list_item_field_form(test_engine, monkeypatch):
    """GET /runs/{id} liefert exakt dieselben Felder+Werte wie das passende Element aus GET /runs."""
    Session = sessionmaker(bind=test_engine)
    s = Session()
    rid = _make_run(s)
    s.close()
    monkeypatch.setattr(api_backtest_module, 'get_session', lambda: Session())

    single = api_backtest_module.get_run(rid)
    assert single['error'] is None
    single_item = single['data']

    # get_runs() direkt aufgerufen: Query(...)-Defaults der Route explizit als
    # Werte übergeben (ohne FastAPI-DI würden sonst die Query-Marker-Objekte
    # selbst als Parameterwerte landen statt der aufgelösten Defaults).
    listing = api_backtest_module.get_runs(
        limit=10000, offset=0, iteration_id=None, strategy=None, version=None, testset_run_id=None,
    )
    list_item = next(item for item in listing.data.items if item['id'] == rid)

    assert single_item == list_item


def test_get_run_unknown_id_returns_404_with_error_key(test_engine, monkeypatch):
    """Unbekannte Run-ID liefert Status 404 mit {'error': '...'} im Body (kein 'detail')."""
    Session = sessionmaker(bind=test_engine)
    monkeypatch.setattr(api_backtest_module, 'get_session', lambda: Session())

    resp = api_backtest_module.get_run(999999999)
    assert resp.status_code == 404
    body = json.loads(resp.body)
    assert body['error'] == 'Run #999999999 nicht gefunden'
