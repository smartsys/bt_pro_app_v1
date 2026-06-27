"""Tests für BacktestRun.testset_run_id FK-Verknüpfung.

Ticket 04: Stellt sicher, dass testset_run_id korrekt persistiert wird,
Einzelstarts NULL liefern und FK-Integrität gewahrt ist.

Tests laufen gegen die echte PostgreSQL-Test-DB (VBT_TEST_DATABASE_URL, Port 5562),
da die Spalte einen FK auf testset_runs hat und SQLite keine FK-Constraints erzwingt.
db_engine und session kommen aus tests/conftest.py (Ticket 14).
"""

# GEÄNDERT: Ticket 14 — Lokale db_engine/session-Fixtures entfernt, zentrale
# Fixtures aus conftest.py werden automatisch injiziert.
import pytest
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from user_data.utils.database.models import (
    BacktestConfig,
    BacktestRun,
    TestSet,
    TestSetRun,
)

# Minimale Backtest-Config für create_backtest_run
_BACKTEST_CONFIG = {
    'strategy_family': 'test_family',
    'strategy_name': 'test_strategy',
    'symbols': ['BTCUSDT'],
    'exchange': 'binance',
    'timeframe': '4h',
    'start': '2024-01-01',
    'end': '2024-12-31',
}
_INDICATORS_CONFIG: dict = {}


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope='function')
def backtest_config_obj(session) -> BacktestConfig:
    """Minimale BacktestConfig — Voraussetzung für TestSet."""
    config = BacktestConfig(
        name='Ticket04-Config',
        symbol='BTCUSDT',
        exchange='binance',
        timeframe='4h',
        start='2024-01-01',
        end='2024-12-31',
        ohlc_start='2023-12-01',
        ohlc_end='2025-01-01',
    )
    session.add(config)
    session.flush()
    return config


@pytest.fixture(scope='function')
def testset_run(session, backtest_config_obj) -> TestSetRun:
    """Minimaler TestSetRun für FK-Tests."""
    ts = TestSet(
        name='Ticket04-TestSet',
        # GEÄNDERT: Ticket 15 — _json-Suffix
        backtest_config_ids_json=[backtest_config_obj.id],
    )
    session.add(ts)
    session.flush()

    run = TestSetRun(
        testset_id=ts.id,
        strategy_family='test_family',
        strategy_name='test_strategy',
        n_runs_total=1,
        status='queued',
    )
    session.add(run)
    session.flush()
    return run


# ============================================================================
# Hilfsfunktion: BacktestRun direkt über ORM anlegen (isoliert von Engine)
# ============================================================================

def _create_run(session, testset_run_id=None) -> BacktestRun:
    """Legt einen minimalen BacktestRun über die ORM-Session an."""
    run = BacktestRun(
        strategy_family=_BACKTEST_CONFIG['strategy_family'],
        strategy_name=_BACKTEST_CONFIG['strategy_name'],
        symbol=_BACKTEST_CONFIG['symbols'][0],
        exchange=_BACKTEST_CONFIG['exchange'],
        timeframe=_BACKTEST_CONFIG['timeframe'],
        start_date=datetime.strptime(_BACKTEST_CONFIG['start'], '%Y-%m-%d'),
        end_date=datetime.strptime(_BACKTEST_CONFIG['end'], '%Y-%m-%d'),
        # GEÄNDERT: Ticket 15 — _json-Suffix
        backtest_config_json=_BACKTEST_CONFIG,
        indicators_config_json=_INDICATORS_CONFIG,
        n_combinations=1,
        status='queued',
        testset_run_id=testset_run_id,
    )
    session.add(run)
    session.flush()
    return run


# ============================================================================
# Tests: Einzelstart (testset_run_id bleibt NULL)
# ============================================================================

def test_einzelstart_testset_run_id_is_null(session):
    """Einzelstart-BacktestRun hat testset_run_id=NULL."""
    run = _create_run(session, testset_run_id=None)
    assert run.testset_run_id is None


@pytest.mark.integration
def test_einzelstart_ueber_repository(session, db_engine):
    """create_backtest_run ohne testset_run_id erzeugt NULL in der DB.

    Integrations-Test: create_backtest_run hat Fallback auf iteration_id=1
    (strategy_iterations-FK). Benötigt committed Migrations-Daten in der DB.
    """
    from unittest.mock import patch

    # Engine auf die Test-Transaktion umleiten
    with patch('user_data.utils.database.repository.get_engine', return_value=db_engine):
        from user_data.utils.database.repository import create_backtest_run
        run_id = create_backtest_run(
            backtest_config=_BACKTEST_CONFIG,
            indicators_config=_INDICATORS_CONFIG,
        )

    # Direkt in der DB prüfen (außerhalb der Test-Transaktion — echte Zeile)
    with db_engine.connect() as conn:
        row = conn.execute(
            text('SELECT testset_run_id FROM backtest_runs WHERE id = :id'),
            {'id': run_id},
        ).fetchone()
        assert row is not None
        assert row[0] is None, f"Erwartet NULL, bekam {row[0]}"
        # Aufräumen
        conn.execute(text('DELETE FROM backtest_runs WHERE id = :id'), {'id': run_id})
        conn.commit()


# ============================================================================
# Tests: Anlage mit gültiger testset_run_id
# ============================================================================

def test_create_run_with_valid_testset_run_id(session, testset_run):
    """BacktestRun mit gültiger testset_run_id wird korrekt persistiert."""
    run = _create_run(session, testset_run_id=testset_run.id)
    assert run.testset_run_id == testset_run.id


@pytest.mark.integration
def test_create_run_via_repository_with_testset_run_id(db_engine):
    """create_backtest_run mit testset_run_id schreibt den Wert in die DB.

    Nutzt einen echten committed TestSetRun (über eigene Verbindung), da
    create_backtest_run intern eine neue Engine-Connection öffnet und
    uncommitted Daten nicht sieht.

    Integrations-Test: benötigt committed Migrations-Daten (iteration_id=1 FK).
    """
    from unittest.mock import patch

    # TestSetRun in separater committed Transaktion anlegen
    with db_engine.begin() as setup_conn:
        # Minimale BacktestConfig
        bc_id = setup_conn.execute(
            text(
                "INSERT INTO backtest_configs (name, symbol, exchange, timeframe, start, \"end\","
                " ohlc_start, ohlc_end) VALUES ('T04-Repo', 'BTCUSDT', 'binance', '4h',"
                " '2024-01-01', '2024-12-31', '2023-12-01', '2025-01-01') RETURNING id"
            )
        ).scalar()
        ts_id = setup_conn.execute(
            text(
                # GEÄNDERT: Ticket 15 — _json-Suffix
                "INSERT INTO testsets (name, backtest_config_ids_json) VALUES"
                " ('T04-Repo-TS', :ids) RETURNING id"
            ),
            {'ids': f'[{bc_id}]'},
        ).scalar()
        tsr_id = setup_conn.execute(
            text(
                "INSERT INTO testset_runs (testset_id, strategy_family, strategy_name,"
                " n_runs_total, status) VALUES (:ts_id, 'fam', 'strat', 1, 'queued') RETURNING id"
            ),
            {'ts_id': ts_id},
        ).scalar()

    try:
        with patch('user_data.utils.database.repository.get_engine', return_value=db_engine):
            from user_data.utils.database.repository import create_backtest_run
            run_id = create_backtest_run(
                backtest_config=_BACKTEST_CONFIG,
                indicators_config=_INDICATORS_CONFIG,
                testset_run_id=tsr_id,
            )

        with db_engine.connect() as conn:
            row = conn.execute(
                text('SELECT testset_run_id FROM backtest_runs WHERE id = :id'),
                {'id': run_id},
            ).fetchone()
            assert row is not None
            assert row[0] == tsr_id
    finally:
        # Aufräumen
        with db_engine.begin() as cleanup_conn:
            cleanup_conn.execute(text('DELETE FROM backtest_runs WHERE id = :id'), {'id': run_id})
            cleanup_conn.execute(text('DELETE FROM testset_runs WHERE id = :id'), {'id': tsr_id})
            cleanup_conn.execute(text('DELETE FROM testsets WHERE id = :id'), {'id': ts_id})
            cleanup_conn.execute(text('DELETE FROM backtest_configs WHERE id = :id'), {'id': bc_id})


# ============================================================================
# Tests: FK-Integrität — ungültige testset_run_id muss fehlschlagen
# ============================================================================

def test_create_run_with_invalid_testset_run_id_raises(session):
    """BacktestRun mit nicht-existierender testset_run_id löst IntegrityError aus."""
    with pytest.raises(IntegrityError):
        _create_run(session, testset_run_id=99999999)
        session.flush()
