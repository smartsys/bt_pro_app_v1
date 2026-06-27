"""Tests für den TestSet-Runs API-Endpunkt und die Worker-Increment-Logik.

Ticket 05: Stellt sicher, dass POST /api/testset-runs korrekt funktioniert und
die atomare Increment-Logik im Worker den TestSetRun-Status sauber verwaltet.

Tests laufen gegen die echte PostgreSQL-Test-DB (VBT_TEST_DATABASE_URL, Port 5562).
db_engine und session kommen aus tests/conftest.py (Ticket 14).
"""

# GEÄNDERT: Ticket 14 — Lokale db_engine/session-Fixtures entfernt, zentrale
# Fixtures aus conftest.py werden automatisch injiziert.
import pytest
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from user_data.utils.database.models import (
    BacktestConfig,
    BacktestRun,
    IndicatorConfig,
    StrategyConfig,
    TestSet,
    TestSetRun,
)
# GEÄNDERT: Ticket 13 — Naming-Cleanup auf testsets / testset_id

_BACKTEST_CONFIG = {
    'strategy_family': 'test_family',
    'strategy_name': 'test_strat_05',
    'import_path': 'user_data.strategies.test.dummy',
    'symbols': ['BTCUSDT'],
    'exchange': 'binance',
    'timeframe': '4h',
    'start': '2024-01-01',
    'end': '2024-12-31',
    'ohlc_start': '2023-12-01',
    'ohlc_end': '2025-01-01',
}
_INDICATORS: dict = {}


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope='function')
def bt_config(session) -> BacktestConfig:
    """Minimale BacktestConfig."""
    c = BacktestConfig(
        name='T05-BT-Config',
        symbol='BTCUSDT',
        exchange='binance',
        timeframe='4h',
        start='2024-01-01',
        end='2024-12-31',
        ohlc_start='2023-12-01',
        ohlc_end='2025-01-01',
    )
    session.add(c)
    session.flush()
    return c


@pytest.fixture(scope='function')
def bt_config2(session) -> BacktestConfig:
    """Zweite BacktestConfig für 2-Config TestSet."""
    c = BacktestConfig(
        name='T05-BT-Config-2',
        symbol='ETHUSDT',
        exchange='binance',
        timeframe='1h',
        start='2024-01-01',
        end='2024-12-31',
        ohlc_start='2023-12-01',
        ohlc_end='2025-01-01',
    )
    session.add(c)
    session.flush()
    return c


@pytest.fixture(scope='function')
def test_set(session, bt_config, bt_config2) -> TestSet:
    """TestSet mit 2 BacktestConfigs."""
    ts = TestSet(
        name='T05-TestSet',
        # GEÄNDERT: Ticket 15 — _json-Suffix
        backtest_config_ids_json=[bt_config.id, bt_config2.id],
    )
    session.add(ts)
    session.flush()
    return ts


@pytest.fixture(scope='function')
def strategy_config(session) -> StrategyConfig:
    """Minimale StrategyConfig."""
    sc = StrategyConfig(
        name='T05-Strategy',
        strategy_family='test_family',
        strategy_name='test_strat_05',
        import_path='user_data.strategies.test.dummy',
    )
    session.add(sc)
    session.flush()
    return sc


# ============================================================================
# Hilfsfunktion: TestSetRun direkt anlegen
# ============================================================================

def _make_testset_run(session, testset_id: int, n_total: int = 2) -> TestSetRun:
    """Legt einen minimalen TestSetRun über ORM an."""
    run = TestSetRun(
        testset_id=testset_id,
        strategy_family='test_family',
        strategy_name='test_strat_05',
        n_runs_total=n_total,
        status='queued',
    )
    session.add(run)
    session.flush()
    return run


def _make_backtest_run(session, testset_run_id: int, bt_cfg: BacktestConfig) -> BacktestRun:
    """Legt einen minimalen BacktestRun (status=queued) über ORM an."""
    run = BacktestRun(
        strategy_family='test_family',
        strategy_name='test_strat_05',
        symbol=bt_cfg.symbol,
        exchange=bt_cfg.exchange,
        timeframe=bt_cfg.timeframe,
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
        # GEÄNDERT: Ticket 15 — _json-Suffix
        backtest_config_json=_BACKTEST_CONFIG,
        indicators_config_json=_INDICATORS,
        n_combinations=1,
        status='queued',
        testset_run_id=testset_run_id,
    )
    session.add(run)
    session.flush()
    return run


# ============================================================================
# Tests: API-Endpunkt-Logik (direkt ohne HTTP-Client)
# ============================================================================

@pytest.mark.integration
def test_testset_run_record_and_backtest_runs_created(db_engine):
    """POST-Logik: 1 testset_runs-Record + N backtest_runs mit testset_run_id gesetzt.

    Integrations-Test: create_backtest_run benötigt committed strategy_iterations
    (iteration_id=1 Fallback). Nur mit Migrations-Daten ausführbar.


    Simuliert die Kernlogik des Endpunkts direkt ohne HTTP-Server:
    - Legt TestSet mit 2 Configs an
    - Legt TestSetRun an (n_runs_total=2, status=queued)
    - Legt 2 BacktestRuns mit testset_run_id an
    - Prüft DB-Zustand
    """
    from user_data.utils.database.repository_testsets import create_testset_run

    # Fixtures direkt aufbauen (committed, da create_testset_run eigene Session braucht)
    with db_engine.begin() as conn:
        bc1_id = conn.execute(text(
            "INSERT INTO backtest_configs (name, symbol, exchange, timeframe, start, \"end\","
            " ohlc_start, ohlc_end) VALUES ('T05-api-bc1', 'BTCUSDT', 'binance', '4h',"
            " '2024-01-01', '2024-12-31', '2023-12-01', '2025-01-01') RETURNING id"
        )).scalar()
        bc2_id = conn.execute(text(
            "INSERT INTO backtest_configs (name, symbol, exchange, timeframe, start, \"end\","
            " ohlc_start, ohlc_end) VALUES ('T05-api-bc2', 'ETHUSDT', 'binance', '1h',"
            " '2024-01-01', '2024-12-31', '2023-12-01', '2025-01-01') RETURNING id"
        )).scalar()
        ts_id = conn.execute(text(
            # GEÄNDERT: Ticket 15 — _json-Suffix
            "INSERT INTO testsets (name, backtest_config_ids_json)"
            " VALUES ('T05-api-ts', :ids) RETURNING id"
        ), {'ids': f'[{bc1_id}, {bc2_id}]'}).scalar()

    Session = sessionmaker(bind=db_engine)
    sess = Session()
    try:
        tsr = create_testset_run(
            session=sess,
            testset_id=ts_id,
            strategy_family='test_family',
            strategy_name='test_strat_05',
            n_runs_total=2,
            status='queued',
        )
        tsr_id = tsr.id
        assert tsr.n_runs_completed == 0
        assert tsr.status == 'queued'
        assert tsr.n_runs_total == 2

        # 2 BacktestRuns anlegen
        from user_data.utils.database.repository import create_backtest_run
        from unittest.mock import patch
        with patch('user_data.utils.database.repository.get_engine', return_value=db_engine):
            run_id1 = create_backtest_run(
                backtest_config=_BACKTEST_CONFIG,
                indicators_config=_INDICATORS,
                testset_run_id=tsr_id,
            )
            run_id2 = create_backtest_run(
                backtest_config=_BACKTEST_CONFIG,
                indicators_config=_INDICATORS,
                testset_run_id=tsr_id,
            )

        # DB-Checks
        with db_engine.connect() as conn:
            tsr_row = conn.execute(
                text("SELECT status, n_runs_total, n_runs_completed FROM testset_runs WHERE id = :id"),
                {'id': tsr_id}
            ).fetchone()
            assert tsr_row.status == 'queued'
            assert tsr_row.n_runs_total == 2
            assert tsr_row.n_runs_completed == 0

            for run_id in (run_id1, run_id2):
                row = conn.execute(
                    text("SELECT testset_run_id FROM backtest_runs WHERE id = :id"),
                    {'id': run_id}
                ).fetchone()
                assert row is not None
                assert row[0] == tsr_id, f"Run {run_id}: testset_run_id erwartet {tsr_id}, bekam {row[0]}"

    finally:
        sess.close()
        with db_engine.begin() as conn:
            conn.execute(text("DELETE FROM backtest_runs WHERE testset_run_id = :id"), {'id': tsr_id})
            conn.execute(text("DELETE FROM testset_runs WHERE id = :id"), {'id': tsr_id})
            conn.execute(text("DELETE FROM testsets WHERE id = :id"), {'id': ts_id})
            conn.execute(text("DELETE FROM backtest_configs WHERE id IN (:id1, :id2)"), {'id1': bc1_id, 'id2': bc2_id})


def test_invalid_testset_id_returns_400(db_engine):
    """POST mit nicht-existierender testset_id liefert 400 mit Fehlermeldung.

    Mockt get_testset direkt, damit kein rq-Import oder DB-Verbindung nötig ist.
    """
    import json
    from unittest.mock import MagicMock, patch
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=db_engine)
    mock_session = Session()

    with patch('services.api.routes.api_testset_runs.get_session', return_value=mock_session), \
         patch('services.api.routes.api_testset_runs.get_testset', return_value=None):
        from services.api.routes.api_testset_runs import start_testset_run, TestSetRunIn
        # GEÄNDERT: Endpunkt nutzt jetzt iteration_id + indicator_config_id (wie Einzel-Lauf)
        payload = TestSetRunIn(
            testset_id=99999999,
            iteration_id=1,
            indicator_config_id=1,
        )
        result = start_testset_run(payload)

    mock_session.close()
    assert result.status_code == 400
    body = json.loads(result.body)
    assert '99999999' in body['error'] or 'nicht gefunden' in body['error'].lower()


# ============================================================================
# Tests: Atomares Increment (_increment_testset_run)
# ============================================================================

@pytest.mark.integration
def test_increment_single_completed_run(db_engine):
    """Nach 1 completed Run: n_runs_completed=1, status bleibt 'queued'."""
    from services.api.worker_tasks import _increment_testset_run
    from unittest.mock import patch

    with db_engine.begin() as conn:
        bc_id = conn.execute(text(
            "INSERT INTO backtest_configs (name, symbol, exchange, timeframe, start, \"end\","
            " ohlc_start, ohlc_end) VALUES ('T05-inc1-bc', 'BTCUSDT', 'binance', '4h',"
            " '2024-01-01', '2024-12-31', '2023-12-01', '2025-01-01') RETURNING id"
        )).scalar()
        ts_id = conn.execute(text(
            "INSERT INTO testsets (name, backtest_config_ids_json)"
            " VALUES ('T05-inc1-ts', :ids) RETURNING id"
        ), {'ids': f'[{bc_id}]'}).scalar()
        tsr_id = conn.execute(text(
            "INSERT INTO testset_runs (testset_id, strategy_family, strategy_name, n_runs_total, status)"
            " VALUES (:ts_id, 'fam', 'strat', 2, 'queued') RETURNING id"
        ), {'ts_id': ts_id}).scalar()

    try:
        from unittest.mock import patch
        with patch('user_data.utils.database.db.get_engine', return_value=db_engine):
            _increment_testset_run(tsr_id, 'completed')

        with db_engine.connect() as conn:
            row = conn.execute(
                text("SELECT n_runs_completed, status, completed_at FROM testset_runs WHERE id = :id"),
                {'id': tsr_id}
            ).fetchone()
            assert row.n_runs_completed == 1
            assert row.status == 'queued'
            assert row.completed_at is None

    finally:
        with db_engine.begin() as conn:
            conn.execute(text("DELETE FROM testset_runs WHERE id = :id"), {'id': tsr_id})
            conn.execute(text("DELETE FROM testsets WHERE id = :id"), {'id': ts_id})
            conn.execute(text("DELETE FROM backtest_configs WHERE id = :id"), {'id': bc_id})


@pytest.mark.integration
def test_increment_all_completed_sets_status(db_engine):
    """Nach N=2 completed Runs: status='completed', completed_at gesetzt."""
    from services.api.worker_tasks import _increment_testset_run

    with db_engine.begin() as conn:
        bc_id = conn.execute(text(
            "INSERT INTO backtest_configs (name, symbol, exchange, timeframe, start, \"end\","
            " ohlc_start, ohlc_end) VALUES ('T05-inc2-bc', 'BTCUSDT', 'binance', '4h',"
            " '2024-01-01', '2024-12-31', '2023-12-01', '2025-01-01') RETURNING id"
        )).scalar()
        ts_id = conn.execute(text(
            "INSERT INTO testsets (name, backtest_config_ids_json)"
            " VALUES ('T05-inc2-ts', :ids) RETURNING id"
        ), {'ids': f'[{bc_id}]'}).scalar()
        tsr_id = conn.execute(text(
            "INSERT INTO testset_runs (testset_id, strategy_family, strategy_name, n_runs_total, status)"
            " VALUES (:ts_id, 'fam', 'strat', 2, 'queued') RETURNING id"
        ), {'ts_id': ts_id}).scalar()

    try:
        from unittest.mock import patch
        with patch('user_data.utils.database.db.get_engine', return_value=db_engine):
            _increment_testset_run(tsr_id, 'completed')  # 1. Run
            _increment_testset_run(tsr_id, 'completed')  # 2. Run (letzter)

        with db_engine.connect() as conn:
            row = conn.execute(
                text("SELECT n_runs_completed, status, completed_at FROM testset_runs WHERE id = :id"),
                {'id': tsr_id}
            ).fetchone()
            assert row.n_runs_completed == 2
            assert row.status == 'completed'
            assert row.completed_at is not None

    finally:
        with db_engine.begin() as conn:
            conn.execute(text("DELETE FROM testset_runs WHERE id = :id"), {'id': tsr_id})
            conn.execute(text("DELETE FROM testsets WHERE id = :id"), {'id': ts_id})
            conn.execute(text("DELETE FROM backtest_configs WHERE id = :id"), {'id': bc_id})


@pytest.mark.integration
def test_increment_failed_run_sets_status(db_engine):
    """Ein failed Run setzt testset_runs.status='failed'."""
    from services.api.worker_tasks import _increment_testset_run

    with db_engine.begin() as conn:
        bc_id = conn.execute(text(
            "INSERT INTO backtest_configs (name, symbol, exchange, timeframe, start, \"end\","
            " ohlc_start, ohlc_end) VALUES ('T05-fail-bc', 'BTCUSDT', 'binance', '4h',"
            " '2024-01-01', '2024-12-31', '2023-12-01', '2025-01-01') RETURNING id"
        )).scalar()
        ts_id = conn.execute(text(
            "INSERT INTO testsets (name, backtest_config_ids_json)"
            " VALUES ('T05-fail-ts', :ids) RETURNING id"
        ), {'ids': f'[{bc_id}]'}).scalar()
        tsr_id = conn.execute(text(
            "INSERT INTO testset_runs (testset_id, strategy_family, strategy_name, n_runs_total, status)"
            " VALUES (:ts_id, 'fam', 'strat', 2, 'queued') RETURNING id"
        ), {'ts_id': ts_id}).scalar()

    try:
        from unittest.mock import patch
        with patch('user_data.utils.database.db.get_engine', return_value=db_engine):
            _increment_testset_run(tsr_id, 'failed')

        with db_engine.connect() as conn:
            row = conn.execute(
                text("SELECT n_runs_completed, status FROM testset_runs WHERE id = :id"),
                {'id': tsr_id}
            ).fetchone()
            assert row.n_runs_completed == 1
            assert row.status == 'failed'

    finally:
        with db_engine.begin() as conn:
            conn.execute(text("DELETE FROM testset_runs WHERE id = :id"), {'id': tsr_id})
            conn.execute(text("DELETE FROM testsets WHERE id = :id"), {'id': ts_id})
            conn.execute(text("DELETE FROM backtest_configs WHERE id = :id"), {'id': bc_id})


def test_einzelstart_increment_not_called(session, test_set):
    """Einzelstart-BacktestRun hat testset_run_id=NULL — Increment-Logik nicht betroffen."""
    run = BacktestRun(
        strategy_family='test_family',
        strategy_name='test_strat_05',
        symbol='BTCUSDT',
        exchange='binance',
        timeframe='4h',
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
        # GEÄNDERT: Ticket 15 — _json-Suffix
        backtest_config_json=_BACKTEST_CONFIG,
        indicators_config_json=_INDICATORS,
        n_combinations=1,
        status='queued',
        testset_run_id=None,
    )
    session.add(run)
    session.flush()
    assert run.testset_run_id is None
