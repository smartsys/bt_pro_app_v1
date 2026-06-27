"""Tests für recovery_oneshot.py (Ticket 33, Teil C).

Prüft, dass recover_stale_runs() hängende BacktestRuns korrekt auf 'queued'
zurücksetzt und neu in die RQ-Queue einreiht.

Verwendet PostgreSQL Test-DB (Port 5562) via db_engine/session-Fixtures
aus tests/conftest.py. Queue.enqueue wird gemockt.
"""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

# Projekt-Root für alle Importe
_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))

# rq via sys.modules mocken bevor recovery_oneshot importiert wird
# (rq ist nur im Docker/WSL-venv verfügbar, nicht im Windows-venv)
_mock_rq = MagicMock()
_mock_queue_cls = MagicMock()
_mock_rq.Queue = _mock_queue_cls
sys.modules.setdefault('rq', _mock_rq)

import services.api.recovery_oneshot  # noqa: E402, F401
import user_data.utils.database.db as _db_module  # noqa: E402


# ============================================================================
# Hilfsfunktionen
# ============================================================================

def _insert_backtest_run(engine, status: str) -> int:
    """Legt einen BacktestRun mit dem angegebenen Status direkt per SQL ein.

    Returns:
        ID des angelegten Runs.
    """
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "INSERT INTO backtest_runs "
                "(strategy_family, strategy_name, symbol, exchange, timeframe, "
                "start_date, end_date, backtest_config_json, indicators_config_json, "
                "n_combinations, status) "
                "VALUES ('test', 'test', 'BTC', 'binance', '1h', "
                "NOW(), NOW(), '{}', '{}', 0, :status) "
                "RETURNING id"
            ),
            {"status": status},
        ).fetchone()
    return row.id


# ============================================================================
# Tests
# ============================================================================

class TestRecoverStaleRuns:
    """recover_stale_runs() setzt running-Runs zurück und reiht sie ein."""

    def test_keine_haengenden_runs(self, db_engine, monkeypatch):
        """Leere DB — recover_stale_runs() läuft ohne Fehler durch."""
        mock_q = MagicMock()
        monkeypatch.setattr(_db_module, '_engine', None)
        monkeypatch.setattr(_db_module, '_session_factory', None)

        with patch('services.api.recovery_oneshot.get_redis_connection', return_value=MagicMock()), \
             patch('services.api.recovery_oneshot.Queue', return_value=mock_q):
            services.api.recovery_oneshot.recover_stale_runs()

        # Kein enqueue-Call erwartet
        mock_q.enqueue.assert_not_called()

    def test_zwei_running_runs_werden_zurueckgesetzt(self, db_engine, monkeypatch):
        """Zwei BacktestRuns mit status='running' → beide auf 'queued', beide eingereiht."""
        run1_id = _insert_backtest_run(db_engine, 'running')
        run2_id = _insert_backtest_run(db_engine, 'running')

        mock_q = MagicMock()
        monkeypatch.setattr(_db_module, '_engine', None)
        monkeypatch.setattr(_db_module, '_session_factory', None)

        with patch('services.api.recovery_oneshot.get_redis_connection', return_value=MagicMock()), \
             patch('services.api.recovery_oneshot.Queue', return_value=mock_q):
            services.api.recovery_oneshot.recover_stale_runs()

        # Queue.enqueue muss zweimal aufgerufen worden sein
        assert mock_q.enqueue.call_count == 2, (
            f"Erwartet 2 enqueue-Aufrufe, war: {mock_q.enqueue.call_count}"
        )

        # Status in DB muss 'queued' sein
        SessionFactory = sessionmaker(bind=db_engine)
        with SessionFactory() as sess:
            r1_status = sess.execute(
                text("SELECT status FROM backtest_runs WHERE id = :id"), {"id": run1_id}
            ).scalar()
            r2_status = sess.execute(
                text("SELECT status FROM backtest_runs WHERE id = :id"), {"id": run2_id}
            ).scalar()

        assert r1_status == 'queued', f"Run1 Status erwartet 'queued', war: {r1_status}"
        assert r2_status == 'queued', f"Run2 Status erwartet 'queued', war: {r2_status}"

    def test_queued_runs_werden_nicht_angefasst(self, db_engine, monkeypatch):
        """BacktestRuns mit status='queued' bleiben unberührt."""
        _insert_backtest_run(db_engine, 'queued')

        mock_q = MagicMock()
        monkeypatch.setattr(_db_module, '_engine', None)
        monkeypatch.setattr(_db_module, '_session_factory', None)

        with patch('services.api.recovery_oneshot.get_redis_connection', return_value=MagicMock()), \
             patch('services.api.recovery_oneshot.Queue', return_value=mock_q):
            services.api.recovery_oneshot.recover_stale_runs()

        # Kein erneutes Einreihen (Run ist bereits queued)
        mock_q.enqueue.assert_not_called()

    def test_enqueue_verwendet_korrekten_task_namen(self, db_engine, monkeypatch):
        """Enqueued Job muss 'services.api.worker_tasks.run_backtest_job' verwenden."""
        _insert_backtest_run(db_engine, 'running')

        mock_q = MagicMock()
        monkeypatch.setattr(_db_module, '_engine', None)
        monkeypatch.setattr(_db_module, '_session_factory', None)

        with patch('services.api.recovery_oneshot.get_redis_connection', return_value=MagicMock()), \
             patch('services.api.recovery_oneshot.Queue', return_value=mock_q):
            services.api.recovery_oneshot.recover_stale_runs()

        assert mock_q.enqueue.call_count >= 1
        call_args = mock_q.enqueue.call_args
        assert call_args[0][0] == 'services.api.worker_tasks.run_backtest_job', (
            f"Falscher Task-Name: {call_args[0][0]}"
        )
