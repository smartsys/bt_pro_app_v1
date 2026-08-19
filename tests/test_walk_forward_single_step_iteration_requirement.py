"""Tests der iteration_id-Durchreichung im Walk-Forward-Einzelschritt (Ticket 83).

POST /api/backtest/walk-forward kopiert einen Anker-Lauf ins nächste Zeitfenster.
`worker_tasks.run_backtest_job` wirft seit Ticket 21 hart, wenn der neue Run keine
`iteration_id` trägt — die Rules kommen ausschließlich aus `iteration.spec_json`.
Geprüft wird:

- Anker-Lauf MIT Iteration: der neue Run trägt dieselbe iteration_id.
- Anker-Lauf OHNE Iteration: der Aufruf wird VOR dem Anlegen eines Runs abgewiesen
  (JSONResponse, 400, 'error'-Key, kein 'detail') — die Bestandszählung von
  backtest_runs bleibt unverändert.

Endpunkt-Funktion wird direkt aufgerufen (Projekt-Konvention, siehe
test_walk_forward_chain_api.py). Läuft gegen die PostgreSQL-Test-DB
(VBT_TEST_DATABASE_URL, Port 5562).
"""

import json
import sys
import types
from datetime import datetime
from uuid import uuid4

# rq-Familie stubben (nur im Worker-Container installiert), damit api_backtest importierbar ist
for _m in ('rq', 'rq.job', 'rq.registry', 'rq.command'):
    if _m not in sys.modules:
        sys.modules[_m] = types.ModuleType(_m)
sys.modules['rq'].Queue = object
sys.modules['rq.job'].Job = object
sys.modules['rq.registry'].StartedJobRegistry = object
sys.modules['rq.command'].send_stop_job_command = lambda *a, **k: None

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from services.api.routes import api_backtest as api_backtest_module  # noqa: E402
from user_data.utils.database import repository as repo_module  # noqa: E402
from user_data.utils.database.models import (  # noqa: E402
    BacktestResult,
    BacktestRun,
    StrategyConcept,
    StrategyIteration,
)

_ANCHOR_CONFIG = {
    'strategy_family': 'testkonzept',
    'strategy_name': 'v1',
    'symbols': ['BTCUSDT'],
    'exchange': 'binance',
    'timeframe': '4h',
    'start': '2020-01-01',
    'end': '2020-06-01',
}


class _RecordingQueue:
    """Queue-Ersatz, der das Enqueue mitschreibt statt Redis zu brauchen."""

    calls: list = []

    def __init__(self, name, connection=None):
        self.name = name

    def enqueue(self, path, **kwargs):
        """Merkt sich Job-Pfad und Argumente statt tatsächlich zu enqueuen."""
        _RecordingQueue.calls.append({'name': self.name, 'path': path, **kwargs})
        return None


@pytest.fixture
def wired(monkeypatch, session):
    """Verdrahtet die Route, das Repository und die Queue auf die Test-DB."""
    engine = session.get_bind()
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(api_backtest_module, 'get_session', session_factory)
    monkeypatch.setattr(api_backtest_module, 'get_redis_connection', lambda: None)
    monkeypatch.setattr(api_backtest_module, 'Queue', _RecordingQueue)
    monkeypatch.setattr(repo_module, 'get_engine', lambda: engine)
    _RecordingQueue.calls = []
    return session


def _make_anchor_with_result(session, iteration_id=None) -> tuple:
    """Legt einen Anker-Run (+ Result mit resolved_config_json) an.

    Returns:
        (anchor_run_id, result_id)
    """
    run = BacktestRun(
        strategy_family='testkonzept', strategy_name='v1',
        symbol='BTCUSDT', exchange='binance', timeframe='4h',
        start_date=datetime(2020, 1, 1), end_date=datetime(2020, 6, 1),
        backtest_config_json=dict(_ANCHOR_CONFIG),
        indicators_config_json={'_stops': {'tp_stop': [0.02]}},
        n_combinations=1, status='completed',
        iteration_id=iteration_id,
    )
    session.add(run)
    session.flush()
    result = BacktestResult(
        run_id=run.id, params_hash=uuid4().hex,
        actual_params_json={'tp_stop': 0.02},
        resolved_config_json={'_stops': {'tp_stop': 0.02}},
        total_return_pct=5.0,
    )
    session.add(result)
    session.commit()
    return run.id, result.id


def _count_runs(session) -> int:
    return int(session.execute(text('SELECT count(*) FROM backtest_runs')).scalar())


def test_anchor_with_iteration_creates_run_carrying_same_iteration_id(wired):
    """Anker mit Iteration: der neue Run entsteht und trägt dieselbe iteration_id."""
    session = wired
    concept = StrategyConcept(slug='testkonzept', name='Testkonzept')
    session.add(concept)
    session.flush()
    iteration = StrategyIteration(
        concept_id=concept.id, version=1, version_name='v1', type='generic',
        spec_json={'indicators': {}, 'rules': {'entry': None, 'exit': None}},
    )
    session.add(iteration)
    session.flush()
    _anchor_run_id, result_id = _make_anchor_with_result(session, iteration_id=iteration.id)

    response = api_backtest_module.start_walk_forward({
        'result_id': result_id, 'months': 3, 'metric': 'total_return_pct',
    })

    assert response['error'] is None
    new_run_id = response['data']['run_id']
    row = session.execute(
        text('SELECT iteration_id FROM backtest_runs WHERE id = :id'), {'id': new_run_id}
    ).fetchone()
    assert row.iteration_id == iteration.id


def test_anchor_without_iteration_is_rejected_before_any_run_row_is_created(wired):
    """Anker ohne Iteration: Abweisung VOR dem Anlegen — Run-Bestand bleibt unverändert."""
    session = wired
    _anchor_run_id, result_id = _make_anchor_with_result(session, iteration_id=None)
    n_before = _count_runs(session)

    response = api_backtest_module.start_walk_forward({
        'result_id': result_id, 'months': 3, 'metric': 'total_return_pct',
    })

    assert response.status_code == 400
    body = json.loads(response.body)
    assert 'iteration_id' in body['error']
    n_after = _count_runs(session)
    assert n_after == n_before
