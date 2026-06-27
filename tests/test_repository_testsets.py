"""Tests für repository_testsets.py — CRUD und Validierung.

Ticket 02: Stellt sicher, dass TestSet-CRUD korrekt funktioniert und
backtest_config_ids-Validierung fehlende IDs mit klarer Meldung ablehnt.

Hinweis: JSONB (PostgreSQL-spezifisch) wird im Model verwendet. Tests laufen
daher gegen die echte PostgreSQL-Test-DB (VBT_TEST_DATABASE_URL, Port 5562).
db_engine und session kommen aus tests/conftest.py (Ticket 14).
"""

# GEÄNDERT: Ticket 14 — Lokale db_engine/session-Fixtures entfernt, zentrale
# Fixtures aus conftest.py werden automatisch injiziert.
import pytest

from user_data.utils.database.models import BacktestConfig, TestSet
# GEÄNDERT: Ticket 13 — Funktionsnamen auf testset-Varianten umgestellt
from user_data.utils.database.repository_testsets import (
    create_testset,
    delete_testset,
    get_testset,
    list_testsets,
    update_testset,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope='function')
def backtest_config(session):
    """Minimale BacktestConfig für Validierungstests."""
    config = BacktestConfig(
        name='Test-Config',
        symbol='BTCUSDT',
        exchange='binance',
        timeframe='4h',
        start='2024-01-01',
        end='2024-12-31',
        ohlc_start='2023-12-01',
        ohlc_end='2025-01-01',
    )
    session.add(config)
    session.commit()
    session.refresh(config)
    return config


@pytest.fixture(scope='function')
def second_backtest_config(session):
    """Zweite BacktestConfig für Mehrfach-ID-Tests."""
    config = BacktestConfig(
        name='Test-Config-2',
        symbol='ETHUSDT',
        exchange='binance',
        timeframe='1h',
        start='2024-01-01',
        end='2024-12-31',
        ohlc_start='2023-12-01',
        ohlc_end='2025-01-01',
    )
    session.add(config)
    session.commit()
    session.refresh(config)
    return config


# ============================================================================
# Tests: Create
# ============================================================================

def test_create_testset(session, backtest_config):
    """Anlegen eines TestSets mit gültiger Config-ID."""
    ts = create_testset(
        session=session,
        name='Mein TestSet',
        backtest_config_ids=[backtest_config.id],
        description='Beschreibung',
        created_by='test-user',
    )
    assert ts.id is not None
    assert ts.name == 'Mein TestSet'
    assert ts.description == 'Beschreibung'
    # GEÄNDERT: Ticket 15 — _json-Suffix
    assert ts.backtest_config_ids_json == [backtest_config.id]
    assert ts.created_by == 'test-user'
    assert ts.created_at is not None


def test_create_testset_multiple_configs(session, backtest_config, second_backtest_config):
    """Anlegen mit mehreren Config-IDs."""
    ids = [backtest_config.id, second_backtest_config.id]
    ts = create_testset(session=session, name='Multi-Set', backtest_config_ids=ids)
    # GEÄNDERT: Ticket 15 — _json-Suffix
    assert set(ts.backtest_config_ids_json) == set(ids)


def test_create_testset_invalid_config_id(session):
    """Anlegen mit nicht-existierender Config-ID schlägt mit ValueError fehl."""
    with pytest.raises(ValueError) as exc_info:
        create_testset(
            session=session,
            name='Ungültig',
            backtest_config_ids=[99999999],
        )
    assert '99999999' in str(exc_info.value)


def test_create_testset_partially_invalid(session, backtest_config):
    """Anlegen mit einer gültigen und einer ungültigen ID schlägt fehl."""
    with pytest.raises(ValueError) as exc_info:
        create_testset(
            session=session,
            name='Teilweise ungültig',
            backtest_config_ids=[backtest_config.id, 88888888],
        )
    assert '88888888' in str(exc_info.value)


# ============================================================================
# Tests: Read
# ============================================================================

def test_get_testset(session, backtest_config):
    """Einzelnes TestSet abrufen."""
    ts = create_testset(session=session, name='Abruf-Test', backtest_config_ids=[backtest_config.id])
    result = get_testset(session, ts.id)
    assert result is not None
    assert result.id == ts.id
    assert result.name == 'Abruf-Test'


def test_get_testset_not_found(session):
    """Nicht-existierendes TestSet gibt None zurück."""
    result = get_testset(session, 99999999)
    assert result is None


def test_list_testsets(session, backtest_config):
    """Liste aller TestSets."""
    create_testset(session=session, name='Alpha', backtest_config_ids=[backtest_config.id])
    create_testset(session=session, name='Beta', backtest_config_ids=[backtest_config.id])
    result = list_testsets(session)
    names = [ts.name for ts in result]
    assert 'Alpha' in names
    assert 'Beta' in names
    # Sortiert nach Name
    assert names == sorted(names)


def test_list_testsets_empty(session):
    """Leere Liste wenn keine TestSets vorhanden."""
    result = list_testsets(session)
    assert result == []


# ============================================================================
# Tests: Update
# ============================================================================

def test_update_testset_name(session, backtest_config):
    """Name eines TestSets aktualisieren."""
    ts = create_testset(session=session, name='Alt', backtest_config_ids=[backtest_config.id])
    updated = update_testset(session, ts.id, name='Neu')
    assert updated is not None
    assert updated.name == 'Neu'
    # Config-IDs unverändert
    # GEÄNDERT: Ticket 15 — _json-Suffix
    assert updated.backtest_config_ids_json == [backtest_config.id]


def test_update_testset_config_ids(session, backtest_config, second_backtest_config):
    """backtest_config_ids eines TestSets aktualisieren."""
    ts = create_testset(session=session, name='Update-Test', backtest_config_ids=[backtest_config.id])
    updated = update_testset(session, ts.id, backtest_config_ids=[second_backtest_config.id])
    # GEÄNDERT: Ticket 15 — _json-Suffix
    assert updated.backtest_config_ids_json == [second_backtest_config.id]


def test_update_testset_invalid_config_id(session, backtest_config):
    """Update mit ungültiger Config-ID schlägt mit ValueError fehl."""
    ts = create_testset(session=session, name='Zu-Aktualisieren', backtest_config_ids=[backtest_config.id])
    with pytest.raises(ValueError) as exc_info:
        update_testset(session, ts.id, backtest_config_ids=[99999999])
    assert '99999999' in str(exc_info.value)


def test_update_testset_not_found(session):
    """Update eines nicht-existierenden TestSets gibt None zurück."""
    result = update_testset(session, 99999999, name='Ghost')
    assert result is None


# ============================================================================
# Tests: Delete
# ============================================================================

def test_delete_testset(session, backtest_config):
    """TestSet löschen."""
    ts = create_testset(session=session, name='Zu-Löschen', backtest_config_ids=[backtest_config.id])
    deleted = delete_testset(session, ts.id)
    assert deleted is True
    assert get_testset(session, ts.id) is None


def test_delete_testset_not_found(session):
    """Löschen eines nicht-existierenden TestSets gibt False zurück."""
    result = delete_testset(session, 99999999)
    assert result is False
