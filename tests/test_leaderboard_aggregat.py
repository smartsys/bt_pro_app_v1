"""Tests für build_leaderboard_entry_for_testset_run (Ticket 06).

Prüft:
- Happy Path: N=3 Runs mit je 2 Results -> korrekter Eintrag mit Aggregaten
- Edge "leerer Run": 1 von 3 Runs ohne Results -> null an Position, hint gesetzt
- Idempotenz: Zweiter Aufruf gibt None zurück, kein zweiter DB-Eintrag

Tests laufen gegen die echte PostgreSQL-Test-DB (VBT_TEST_DATABASE_URL, Port 5562).
db_engine und session kommen aus tests/conftest.py (Ticket 14).
"""

# GEÄNDERT: Ticket 14 — Lokale db_engine/session-Fixtures entfernt, zentrale
# Fixtures aus conftest.py werden automatisch injiziert.
import pytest
from decimal import Decimal

from user_data.utils.database.models import (
    BacktestConfig,
    BacktestResult,
    BacktestRun,
    IndicatorConfig,
    LeaderboardEntry,
    TestSet,
    TestSetRun,
)
from user_data.utils.database.repository_testsets import _build_leaderboard_entry_in_session


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope='function')
def three_backtest_configs(session):
    """Drei BacktestConfigs als Basis für ein TestSet mit 3 Positionen."""
    configs = []
    for i in range(3):
        c = BacktestConfig(
            name=f'Aggregat-Test-Config-{i}',
            symbol='BTCUSDT',
            exchange='binance',
            timeframe='4h',
            start='2024-01-01',
            end='2024-12-31',
            ohlc_start='2023-12-01',
            ohlc_end='2025-01-01',
        )
        session.add(c)
    session.commit()
    for c in session.query(BacktestConfig).filter(
        BacktestConfig.name.like('Aggregat-Test-Config-%')
    ).order_by(BacktestConfig.id).all():
        configs.append(c)
    # Nur die drei zuletzt angelegten nehmen
    return configs[-3:]


@pytest.fixture(scope='function')
def test_set(session, three_backtest_configs):
    """TestSet mit 3 BacktestConfig-IDs."""
    config_ids = [c.id for c in three_backtest_configs]
    ts = TestSet(
        name=f'Aggregat-Test-TestSet-{config_ids[0]}',
        # GEÄNDERT: Ticket 15 — _json-Suffix
        backtest_config_ids_json=config_ids,
        # Opt-in-Schalter aktiv — dieser Test prüft den Leaderboard-Build-Pfad
        leaderboard_enabled=True,
        created_by='test-aggregat',
    )
    session.add(ts)
    session.commit()
    session.refresh(ts)
    return ts


@pytest.fixture(scope='function')
def indicator_config(session):
    """Minimale IndicatorConfig für Snapshot-Tests."""
    ic = IndicatorConfig(
        name='Aggregat-Test-IndicatorConfig',
        config_json={'teststrategie_period': 20, 'signal_threshold': 0.5},
    )
    session.add(ic)
    session.commit()
    session.refresh(ic)
    return ic


@pytest.fixture(scope='function')
def testset_run(session, test_set, indicator_config):
    """TestSetRun mit n_runs_total=3 und IndicatorConfig."""
    run = TestSetRun(
        testset_id=test_set.id,
        strategy_family='teststrategie',
        strategy_name='teststrategie_v1',
        n_runs_total=3,
        n_runs_completed=3,
        status='completed',
        # GEÄNDERT: Ticket 15 — indicator_config_id → indicators_config_json
        indicators_config_json=indicator_config.config_json,
        created_by='test-aggregat',
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _make_backtest_run(
    session,
    testset_run_id: int,
    config_id: int,
    spec_runner_version: str = '1.0.0',
) -> BacktestRun:
    """Hilfsfunktion: BacktestRun für eine bestimmte BacktestConfig anlegen."""
    run = BacktestRun(
        strategy_family='teststrategie',
        strategy_name='teststrategie_v1',
        symbol='BTCUSDT',
        exchange='binance',
        timeframe='4h',
        start_date='2024-01-01',
        end_date='2024-12-31',
        # GEÄNDERT: Ticket 15 — _json-Suffix
        backtest_config_json={
            'strategy_family': 'teststrategie',
            'strategy_name': 'teststrategie_v1',
            'backtest_config_id': config_id,
            'symbols': ['BTCUSDT'],
            'start': '2024-01-01',
            'end': '2024-12-31',
        },
        indicators_config_json={},
        n_combinations=2,
        status='completed',
        testset_run_id=testset_run_id,
        spec_runner_version=spec_runner_version,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _make_backtest_result(
    session,
    run_id: int,
    total_return_pct: float,
    max_drawdown_pct: float,
    sharpe_ratio: float,
) -> BacktestResult:
    """Hilfsfunktion: BacktestResult anlegen."""
    result = BacktestResult(
        run_id=run_id,
        params_hash=f'hash_{run_id}_{total_return_pct}',
        # GEÄNDERT: Ticket 15 — _json-Suffix
        actual_params_json={'teststrategie_period': 20},
        total_return_pct=total_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        sharpe_ratio=sharpe_ratio,
    )
    session.add(result)
    session.commit()
    session.refresh(result)
    return result


# ============================================================================
# Test: Happy Path — 3 Runs mit je 2 Results
# ============================================================================

def test_happy_path_drei_runs(session, testset_run, three_backtest_configs):
    """N=3 Runs mit je 2 Results -> 1 LeaderboardEntry mit korrekten Aggregaten.

    Erwartung:
    - winning_result_ids enthält 3 Einträge (je den result_id des besten Returns)
    - configs_total = 3
    - Aggregate korrekt aus den 3 Siegern berechnet
    - hint ist None (keine leeren Runs)
    """
    config_ids = [c.id for c in three_backtest_configs]

    # 3 BacktestRuns anlegen (je einer pro Config)
    br0 = _make_backtest_run(session, testset_run.id, config_ids[0])
    br1 = _make_backtest_run(session, testset_run.id, config_ids[1])
    br2 = _make_backtest_run(session, testset_run.id, config_ids[2])

    # Je 2 Results pro Run — der höhere total_return_pct ist der Sieger
    # Run 0: Sieger 15.0
    r0_loser = _make_backtest_result(session, br0.id, total_return_pct=5.0, max_drawdown_pct=-10.0, sharpe_ratio=0.5)
    r0_winner = _make_backtest_result(session, br0.id, total_return_pct=15.0, max_drawdown_pct=-8.0, sharpe_ratio=1.2)

    # Run 1: Sieger 25.0
    r1_loser = _make_backtest_result(session, br1.id, total_return_pct=10.0, max_drawdown_pct=-12.0, sharpe_ratio=0.8)
    r1_winner = _make_backtest_result(session, br1.id, total_return_pct=25.0, max_drawdown_pct=-6.0, sharpe_ratio=1.8)

    # Run 2: Sieger 35.0
    r2_loser = _make_backtest_result(session, br2.id, total_return_pct=20.0, max_drawdown_pct=-15.0, sharpe_ratio=1.0)
    r2_winner = _make_backtest_result(session, br2.id, total_return_pct=35.0, max_drawdown_pct=-5.0, sharpe_ratio=2.1)

    # Aggregat-Funktion aufrufen
    entry = _build_leaderboard_entry_in_session(session, testset_run.id)

    assert entry is not None
    assert entry.testset_run_id == testset_run.id
    assert entry.configs_total == 3
    assert entry.hint is None

    # winning_result_ids in Reihenfolge der config_ids
    # GEÄNDERT: Ticket 15 — _json-Suffix
    assert len(entry.winning_result_ids_json) == 3
    assert entry.winning_result_ids_json[0] == r0_winner.id
    assert entry.winning_result_ids_json[1] == r1_winner.id
    assert entry.winning_result_ids_json[2] == r2_winner.id

    # Aggregate prüfen
    # total_return_avg = (15.0 + 25.0 + 35.0) / 3 = 25.0
    assert abs(float(entry.total_return_avg) - 25.0) < 0.01
    # total_return_sum = 15.0 + 25.0 + 35.0 = 75.0
    assert abs(float(entry.total_return_sum) - 75.0) < 0.01
    # max_drawdown_avg = (-8.0 + -6.0 + -5.0) / 3 = -6.333...
    assert abs(float(entry.max_drawdown_avg) - (-8.0 + -6.0 + -5.0) / 3) < 0.01
    # sharpe_avg = (1.2 + 1.8 + 2.1) / 3 = 1.7
    assert abs(float(entry.sharpe_avg) - (1.2 + 1.8 + 2.1) / 3) < 0.01

    # GEÄNDERT: Ticket 15 — _json-Suffix für Snapshot-Felder
    assert entry.testset_snapshot_json is not None
    assert entry.strategy_snapshot_json is not None
    assert entry.indicator_config_snapshot_json is not None
    assert entry.strategy_snapshot_json['strategy_family'] == 'teststrategie'
    assert entry.strategy_snapshot_json['spec_runner_version'] == '1.0.0'


# ============================================================================
# Test: Edge "leerer Run" — 1 von 3 Runs ohne Results
# ============================================================================

def test_leerer_run_null_an_position(session, testset_run, three_backtest_configs):
    """1 von 3 Runs ohne Results -> null an Position, hint gesetzt, configs_total=3."""
    config_ids = [c.id for c in three_backtest_configs]

    # Run 0 und Run 2 haben Results, Run 1 bleibt leer
    br0 = _make_backtest_run(session, testset_run.id, config_ids[0])
    br1 = _make_backtest_run(session, testset_run.id, config_ids[1])  # leer
    br2 = _make_backtest_run(session, testset_run.id, config_ids[2])

    r0_winner = _make_backtest_result(session, br0.id, total_return_pct=10.0, max_drawdown_pct=-10.0, sharpe_ratio=1.0)
    # br1: keine Results
    r2_winner = _make_backtest_result(session, br2.id, total_return_pct=20.0, max_drawdown_pct=-8.0, sharpe_ratio=1.5)

    entry = _build_leaderboard_entry_in_session(session, testset_run.id)

    assert entry is not None
    assert entry.configs_total == 3

    # GEÄNDERT: Ticket 15 — _json-Suffix
    assert len(entry.winning_result_ids_json) == 3
    assert entry.winning_result_ids_json[0] == r0_winner.id
    assert entry.winning_result_ids_json[1] is None
    assert entry.winning_result_ids_json[2] == r2_winner.id

    # hint gesetzt
    assert entry.hint is not None
    assert '1 von 3' in entry.hint

    # Aggregate nur aus den 2 nicht-leeren Siegern
    assert abs(float(entry.total_return_avg) - 15.0) < 0.01  # (10.0 + 20.0) / 2
    assert abs(float(entry.total_return_sum) - 30.0) < 0.01


# ============================================================================
# Test: Idempotenz — zweiter Aufruf gibt None zurück
# ============================================================================

def test_idempotenz_kein_zweiter_eintrag(session, testset_run, three_backtest_configs):
    """Zweiter Aufruf für gleichen TestSetRun gibt None zurück (No-Op).

    Kein zweiter DB-Eintrag wird angelegt.
    """
    config_ids = [c.id for c in three_backtest_configs]

    br0 = _make_backtest_run(session, testset_run.id, config_ids[0])
    _make_backtest_result(session, br0.id, total_return_pct=10.0, max_drawdown_pct=-10.0, sharpe_ratio=1.0)

    br1 = _make_backtest_run(session, testset_run.id, config_ids[1])
    _make_backtest_result(session, br1.id, total_return_pct=20.0, max_drawdown_pct=-8.0, sharpe_ratio=1.5)

    br2 = _make_backtest_run(session, testset_run.id, config_ids[2])
    _make_backtest_result(session, br2.id, total_return_pct=30.0, max_drawdown_pct=-6.0, sharpe_ratio=2.0)

    # Erster Aufruf
    entry_first = _build_leaderboard_entry_in_session(session, testset_run.id)
    assert entry_first is not None

    # Zweiter Aufruf -> No-Op
    entry_second = _build_leaderboard_entry_in_session(session, testset_run.id)
    assert entry_second is None

    # Nur ein Eintrag in der DB
    count = session.query(LeaderboardEntry).filter(
        LeaderboardEntry.testset_run_id == testset_run.id
    ).count()
    assert count == 1


# ============================================================================
# Test: Opt-in-Schalter aus -> kein Leaderboard-Eintrag
# ============================================================================

def test_leaderboard_disabled_kein_eintrag(session, testset_run, test_set, three_backtest_configs):
    """TestSet mit leaderboard_enabled=False -> Build gibt None, kein DB-Eintrag.

    Trotz vollständiger Runs/Results wird der Eintrag bewusst übersprungen.
    """
    config_ids = [c.id for c in three_backtest_configs]

    br0 = _make_backtest_run(session, testset_run.id, config_ids[0])
    _make_backtest_result(session, br0.id, total_return_pct=10.0, max_drawdown_pct=-10.0, sharpe_ratio=1.0)

    # Schalter ausschalten
    test_set.leaderboard_enabled = False
    session.commit()

    entry = _build_leaderboard_entry_in_session(session, testset_run.id)
    assert entry is None

    count = session.query(LeaderboardEntry).filter(
        LeaderboardEntry.testset_run_id == testset_run.id
    ).count()
    assert count == 0
