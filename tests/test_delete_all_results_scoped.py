"""Tests für das eingegrenzte `DELETE /results`.

`result-delete-all` löschte Results außer Favoriten bisher nur global (Hintergrund-
Job über die komplette Tabelle). Mit `run_id`/`testset_run_id` läuft stattdessen eine
synchrone, auf die Menge eingegrenzte Löschung über `_delete_results_and_orphans` —
dieselbe Löschsemantik wie `bulk_delete_results`, inklusive der auf die betroffenen
Runs eingegrenzten Orphan-Sweep-Regel (kein globaler Sweep).

Die Fixtures brauchen die echte PostgreSQL-Test-DB (session/db_engine aus
tests/conftest.py), weil `_delete_results_and_orphans` rohes SQL mit `ANY(:run_ids)`
und `RETURNING` ausführt — beides nicht SQLite-kompatibel.
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

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from services.api.routes import api_backtest as api_backtest_module  # noqa: E402
from user_data.utils.database.models import (  # noqa: E402
    BacktestResult,
    BacktestRun,
    TestSet,
    TestSetRun,
)

_BACKTEST_CONFIG = {
    'strategy_family': 'test_family',
    'strategy_name': 'test_strategy',
    'symbols': ['BTCUSDT'],
    'exchange': 'binance',
    'timeframe': '4h',
    'start': '2024-01-01',
    'end': '2024-12-31',
}


def _make_run(session, testset_run_id=None) -> int:
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
        testset_run_id=testset_run_id,
    )
    session.add(run)
    session.commit()
    return run.id


def _make_result(session, run_id: int, *, is_favorite: int = 0, is_doc_favorite: int = 0) -> int:
    """Minimales BacktestResult in die Test-DB schreiben, gibt die id zurück."""
    result = BacktestResult(
        run_id=run_id,
        params_hash=f'hash-{run_id}-{is_favorite}-{is_doc_favorite}-{datetime.now().timestamp()}',
        actual_params_json={},
        total_return_pct=1.0,
        is_favorite=is_favorite,
        is_doc_favorite=is_doc_favorite,
    )
    session.add(result)
    session.commit()
    return result.id


def _make_testset_run(session) -> int:
    """Testset + zugehörigen TestSetRun anlegen, gibt die testset_run_id zurück."""
    testset = TestSet(
        name=f'T77-TestSet-{datetime.now().timestamp()}',
        backtest_config_ids_json=[],
        leaderboard_enabled=False,
    )
    session.add(testset)
    session.commit()

    testset_run = TestSetRun(
        testset_id=testset.id,
        strategy_family='test_family',
        strategy_name='test_strategy',
        indicators_config_json={},
        status='completed',
        n_runs_total=1,
    )
    session.add(testset_run)
    session.commit()
    return testset_run.id


def test_run_id_and_testset_run_id_together_raises(session, db_engine, monkeypatch):
    Session = sessionmaker(bind=db_engine)
    monkeypatch.setattr(api_backtest_module, 'get_session', lambda: Session())

    with pytest.raises(HTTPException) as exc:
        api_backtest_module.delete_all_results(run_id=1, testset_run_id=1)
    assert exc.value.status_code == 400


def test_scoped_by_testset_run_removes_non_favorites_keeps_favorites_and_foreign(session, db_engine, monkeypatch):
    """result-delete-all --testset-run <id>: Nicht-Favoriten der Menge weg, Favoriten
    (gelb und rot) UND ein fremder Testset-Lauf mit eigenem Favoriten bleiben unberührt."""
    Session = sessionmaker(bind=db_engine)
    s = Session()

    testset_run_id = _make_testset_run(s)
    run_a = _make_run(s, testset_run_id=testset_run_id)
    run_b = _make_run(s, testset_run_id=testset_run_id)
    keep_favorite_id = _make_result(s, run_a, is_favorite=1)
    keep_doc_favorite_id = _make_result(s, run_b, is_doc_favorite=1)
    delete_id_a = _make_result(s, run_a)
    delete_id_b = _make_result(s, run_b)

    # Fremder Testset-Lauf außerhalb des Scopes — darf von der Löschung nicht berührt werden.
    foreign_testset_run_id = _make_testset_run(s)
    foreign_run_id = _make_run(s, testset_run_id=foreign_testset_run_id)
    foreign_result_id = _make_result(s, foreign_run_id)
    s.close()

    monkeypatch.setattr(api_backtest_module, 'get_session', lambda: Session())

    resp = api_backtest_module.delete_all_results(run_id=None, testset_run_id=testset_run_id)
    body = json.loads(resp.body)

    assert body['deleted_results'] == 2
    assert sorted(body['deleted_run_ids']) == []  # beide Runs behalten je einen Favoriten

    check = Session()
    remaining_ids = {r.id for r in check.query(BacktestResult.id).all()}
    assert keep_favorite_id in remaining_ids
    assert keep_doc_favorite_id in remaining_ids
    assert delete_id_a not in remaining_ids
    assert delete_id_b not in remaining_ids
    assert foreign_result_id in remaining_ids
    assert check.query(BacktestRun).filter(BacktestRun.id == foreign_run_id).first() is not None
    check.close()


def test_scoped_by_run_removes_only_that_runs_non_favorites(session, db_engine, monkeypatch):
    """result-delete-all --run <id> bleibt auf genau diesen Run eingegrenzt."""
    Session = sessionmaker(bind=db_engine)
    s = Session()

    run_a = _make_run(s)
    run_b = _make_run(s)
    delete_id = _make_result(s, run_a)
    other_run_result_id = _make_result(s, run_b)
    s.close()

    monkeypatch.setattr(api_backtest_module, 'get_session', lambda: Session())

    resp = api_backtest_module.delete_all_results(run_id=run_a, testset_run_id=None)
    body = json.loads(resp.body)

    assert body['deleted_results'] == 1
    assert body['deleted_runs'] == 1
    assert body['deleted_run_ids'] == [run_a]

    check = Session()
    assert check.query(BacktestResult).filter(BacktestResult.id == delete_id).first() is None
    assert check.query(BacktestResult).filter(BacktestResult.id == other_run_result_id).first() is not None
    assert check.query(BacktestRun).filter(BacktestRun.id == run_a).first() is None
    assert check.query(BacktestRun).filter(BacktestRun.id == run_b).first() is not None
    check.close()


def test_scoped_purge_leaves_foreign_result_less_run_untouched(session, db_engine, monkeypatch):
    """Regressionsfall im neuen scoped Pfad: ein fremder, result-loser Run
    (außerhalb des Scopes) überlebt eine eingegrenzte Löschung."""
    Session = sessionmaker(bind=db_engine)
    s = Session()

    run_foreign_id = _make_run(s)  # nie Results — z.B. failed-Lauf
    run_own_id = _make_run(s)
    own_result_id = _make_result(s, run_own_id)
    s.close()

    monkeypatch.setattr(api_backtest_module, 'get_session', lambda: Session())

    resp = api_backtest_module.delete_all_results(run_id=run_own_id, testset_run_id=None)
    body = json.loads(resp.body)

    assert body['deleted_run_ids'] == [run_own_id]
    assert run_foreign_id not in body['deleted_run_ids']

    check = Session()
    assert check.query(BacktestRun).filter(BacktestRun.id == run_foreign_id).first() is not None
    assert check.query(BacktestResult).filter(BacktestResult.id == own_result_id).first() is None
    check.close()


def test_scoped_purge_with_empty_scope_is_a_no_op(session, db_engine, monkeypatch):
    """--run auf einen Run ohne Nicht-Favoriten löscht nichts (kein Fehler, keine Nebenwirkung)."""
    Session = sessionmaker(bind=db_engine)
    s = Session()
    run_id = _make_run(s)
    favorite_id = _make_result(s, run_id, is_favorite=1)
    s.close()

    monkeypatch.setattr(api_backtest_module, 'get_session', lambda: Session())

    resp = api_backtest_module.delete_all_results(run_id=run_id, testset_run_id=None)
    body = json.loads(resp.body)

    assert body == {'status': 'ok', 'deleted_results': 0, 'deleted_runs': 0, 'deleted_run_ids': []}

    check = Session()
    assert check.query(BacktestResult).filter(BacktestResult.id == favorite_id).first() is not None
    check.close()
