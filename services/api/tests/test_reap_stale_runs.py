"""Tests für reap_stale_runs.py.

Prüft, dass main() 'running'-BacktestRuns ohne lebenden RQ-Job auf 'failed'
setzt, mit lesbarer Begründung in error_message, während Runs mit lebendem
RQ-Job unberührt bleiben. Die RQ-Zustandserkennung selbst (_run_id_states)
wird gemockt — deren Übersetzung in eine Begründung ist bereits in
tests/test_reap_run_logic.py abgedeckt.

Verwendet PostgreSQL Test-DB (Port 5562) via db_engine/session-Fixtures aus
tests/conftest.py.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

# Projekt-Root für alle Importe
_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))

# rq via sys.modules mocken bevor reap_stale_runs importiert wird
# (rq ist nur im Docker/WSL-venv verfügbar, nicht im Windows-venv).
# GEÄNDERT: bewusst überschreiben statt setdefault, siehe
# test_recovery_oneshot.py: andere Testdateien legen beim Import einen
# minimalen rq-Stub in sys.modules ab; wird der zuerst gesetzt, übernimmt
# setdefault ihn und die Registry-Klassen fehlen — je nach Collect-Reihenfolge
# grün oder rot.
_mock_rq = MagicMock()
_mock_rq.Queue = MagicMock()
sys.modules['rq'] = _mock_rq
sys.modules['rq.job'] = MagicMock()
sys.modules['rq.registry'] = MagicMock()

import services.api.reap_stale_runs as reap_stale_runs  # noqa: E402
import user_data.utils.database.db as _db_module  # noqa: E402


# ============================================================================
# Hilfsfunktionen
# ============================================================================

def _insert_backtest_run(engine, status: str) -> int:
    """Legt einen BacktestRun mit dem angegebenen Status direkt per SQL an.

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


def _run_status_and_error(engine, run_id: int) -> tuple:
    SessionFactory = sessionmaker(bind=engine)
    with SessionFactory() as sess:
        row = sess.execute(
            text("SELECT status, error_message FROM backtest_runs WHERE id = :id"),
            {"id": run_id},
        ).fetchone()
    return row.status, row.error_message


def _run_reap(db_engine, monkeypatch, alive_run_ids: set, dead_run_exc_info: dict) -> None:
    """Führt main() aus, mit gemockter RQ-Zustandserkennung und echter Test-DB."""
    monkeypatch.setattr(_db_module, '_engine', None)
    monkeypatch.setattr(_db_module, '_session_factory', None)

    with patch('services.api.reap_stale_runs.get_redis_connection', return_value=MagicMock()), \
         patch('services.api.reap_stale_runs.Queue', return_value=MagicMock()), \
         patch(
             'services.api.reap_stale_runs._run_id_states',
             return_value=(alive_run_ids, dead_run_exc_info),
         ):
        reap_stale_runs.main()


# ============================================================================
# Tests
# ============================================================================

class TestReapStaleRuns:
    """main() setzt tote 'running'-Runs auf 'failed', lässt lebende unberührt."""

    def test_keine_running_runs(self, db_engine, session, monkeypatch):
        """Leere DB — main() läuft ohne Fehler durch."""
        _run_reap(db_engine, monkeypatch, alive_run_ids=set(), dead_run_exc_info={})

    def test_lebender_run_bleibt_unberuehrt(self, db_engine, session, monkeypatch):
        """Run mit lebendem RQ-Job (in alive_run_ids) bleibt auf 'running'."""
        run_id = _insert_backtest_run(db_engine, 'running')

        _run_reap(db_engine, monkeypatch, alive_run_ids={run_id}, dead_run_exc_info={})

        status, error_message = _run_status_and_error(db_engine, run_id)
        assert status == 'running'
        assert error_message is None

    def test_work_horse_kill_wird_auf_failed_gesetzt(self, db_engine, session, monkeypatch):
        """Run, dessen Job mit Work-Horse-Kill (Signal 9) in FailedJobRegistry steht,
        wird auf 'failed' gesetzt mit lesbarer Speicher-Begründung."""
        run_id = _insert_backtest_run(db_engine, 'running')
        exc_info = 'Work-horse terminated unexpectedly; waitpid returned -9 (signal 9); '

        _run_reap(
            db_engine, monkeypatch,
            alive_run_ids=set(),
            dead_run_exc_info={run_id: exc_info},
        )

        status, error_message = _run_status_and_error(db_engine, run_id)
        assert status == 'failed'
        assert 'Signal 9' in error_message
        assert 'Speichermangel' in error_message or 'OOM' in error_message

    def test_verschwundener_job_wird_auf_failed_gesetzt_mit_unbekannter_ursache(
        self, db_engine, session, monkeypatch,
    ):
        """Run ohne jeglichen RQ-Job (weder lebendig noch failed) wird ebenfalls auf
        'failed' gesetzt — deckt auch Altbestand ab, dessen Job-Eintrag längst
        aus Redis verschwunden ist."""
        run_id = _insert_backtest_run(db_engine, 'running')

        _run_reap(db_engine, monkeypatch, alive_run_ids=set(), dead_run_exc_info={})

        status, error_message = _run_status_and_error(db_engine, run_id)
        assert status == 'failed'
        assert 'nicht mehr auffindbar' in error_message

    def test_gegenprobe_nur_toter_run_wird_angefasst(self, db_engine, session, monkeypatch):
        """Zwei gleichzeitig 'running' Runs: nur der tote wird angefasst, der
        lebende bleibt exakt unverändert (Gegenprobe)."""
        healthy_run_id = _insert_backtest_run(db_engine, 'running')
        dead_run_id = _insert_backtest_run(db_engine, 'running')
        exc_info = 'Work-horse terminated unexpectedly; waitpid returned -9 (signal 9); '

        _run_reap(
            db_engine, monkeypatch,
            alive_run_ids={healthy_run_id},
            dead_run_exc_info={dead_run_id: exc_info},
        )

        healthy_status, healthy_error = _run_status_and_error(db_engine, healthy_run_id)
        dead_status, dead_error = _run_status_and_error(db_engine, dead_run_id)

        assert healthy_status == 'running'
        assert healthy_error is None
        assert dead_status == 'failed'
        assert dead_error is not None

    def test_bereits_completed_run_wird_nicht_angefasst(self, db_engine, session, monkeypatch):
        """Ein Run, der nicht 'running' ist, wird von der Erkennung ignoriert
        (query filtert bereits auf status='running')."""
        run_id = _insert_backtest_run(db_engine, 'completed')

        _run_reap(db_engine, monkeypatch, alive_run_ids=set(), dead_run_exc_info={})

        status, error_message = _run_status_and_error(db_engine, run_id)
        assert status == 'completed'
        assert error_message is None
