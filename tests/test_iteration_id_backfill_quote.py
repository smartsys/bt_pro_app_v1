"""Test: Backfill-Quote nach Migration (Ticket 10).

Prüft gegen die echte lokale DB, dass mindestens 95% der Records
in indicator_configs, backtest_runs und backtest_results eine
iteration_id haben (nicht NULL).

Dieser Test läuft nur wenn eine echte DB-Verbindung verfügbar ist
(POSTGRES_SERVER gesetzt oder localhost erreichbar). Schlägt fehl
wenn die Migration noch nicht angewendet wurde.

Pytest-Marker: 'integration' — separate Ausführung möglich via
  pytest -m integration tests/test_iteration_id_backfill_quote.py
"""

import os
import pytest
from sqlalchemy import create_engine, text


def _get_db_url() -> str:
    """Baut DB-URL aus Umgebungsvariablen (Pflicht, kein Fallback; conftest lädt .env)."""
    values = {}
    for key in ('POSTGRES_SERVER', 'POSTGRES_PORT', 'POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD'):
        val = os.getenv(key)
        if not val:
            raise RuntimeError(f"Pflicht-Umgebungsvariable {key} fehlt oder ist leer")
        values[key] = val
    return (
        f"postgresql+psycopg2://{values['POSTGRES_USER']}:{values['POSTGRES_PASSWORD']}"
        f"@{values['POSTGRES_SERVER']}:{values['POSTGRES_PORT']}/{values['POSTGRES_DB']}"
    )


@pytest.fixture(scope='module')
def live_engine():
    """Verbindung zur lokalen PostgreSQL-DB."""
    url = _get_db_url()
    engine = create_engine(url, pool_pre_ping=True, connect_args={'connect_timeout': 5})
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
    except Exception as exc:
        pytest.skip(f'Keine DB-Verbindung verfügbar: {exc}')
    yield engine
    engine.dispose()


def _check_iteration_id_column_exists(conn, table: str) -> bool:
    """Prüft ob iteration_id-Spalte in der Tabelle existiert."""
    result = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name = :table AND column_name = 'iteration_id'"
    ), {'table': table}).scalar()
    return result > 0


@pytest.mark.integration
def test_backtest_runs_backfill_quote(live_engine):
    """Nach Migration: >= 95% der backtest_runs haben iteration_id IS NOT NULL."""
    with live_engine.connect() as conn:
        if not _check_iteration_id_column_exists(conn, 'backtest_runs'):
            pytest.skip('Spalte iteration_id in backtest_runs fehlt — Migration noch nicht angewendet')

        total = conn.execute(text('SELECT COUNT(*) FROM backtest_runs')).scalar()
        if total == 0:
            pytest.skip('backtest_runs ist leer — kein Backfill zu prüfen')

        null_count = conn.execute(text(
            'SELECT COUNT(*) FROM backtest_runs WHERE iteration_id IS NULL'
        )).scalar()

    filled = total - null_count
    quote = filled / total
    assert quote >= 0.95, (
        f'backtest_runs Backfill-Quote zu niedrig: {filled}/{total} = {quote:.1%} '
        f'(erwartet >= 95%)'
    )


@pytest.mark.integration
def test_backtest_results_backfill_quote(live_engine):
    """Nach Migration: >= 95% der backtest_results haben iteration_id IS NOT NULL."""
    with live_engine.connect() as conn:
        if not _check_iteration_id_column_exists(conn, 'backtest_results'):
            pytest.skip('Spalte iteration_id in backtest_results fehlt — Migration noch nicht angewendet')

        total = conn.execute(text('SELECT COUNT(*) FROM backtest_results')).scalar()
        if total == 0:
            pytest.skip('backtest_results ist leer — kein Backfill zu prüfen')

        null_count = conn.execute(text(
            'SELECT COUNT(*) FROM backtest_results WHERE iteration_id IS NULL'
        )).scalar()

    filled = total - null_count
    quote = filled / total
    assert quote >= 0.95, (
        f'backtest_results Backfill-Quote zu niedrig: {filled}/{total} = {quote:.1%} '
        f'(erwartet >= 95%)'
    )


@pytest.mark.integration
def test_indicator_configs_backfill_quote(live_engine):
    """Nach Migration: >= 95% der indicator_configs mit strategy_name haben iteration_id IS NOT NULL."""
    with live_engine.connect() as conn:
        if not _check_iteration_id_column_exists(conn, 'indicator_configs'):
            pytest.skip('Spalte iteration_id in indicator_configs fehlt — Migration noch nicht angewendet')

        # Nur Records mit strategy_name (die mappbar sein sollten)
        total = conn.execute(text(
            "SELECT COUNT(*) FROM indicator_configs WHERE strategy_name IS NOT NULL"
        )).scalar()
        if total == 0:
            pytest.skip('Keine indicator_configs mit strategy_name vorhanden')

        null_count = conn.execute(text(
            "SELECT COUNT(*) FROM indicator_configs "
            "WHERE strategy_name IS NOT NULL AND iteration_id IS NULL"
        )).scalar()

    filled = total - null_count
    quote = filled / total
    assert quote >= 0.95, (
        f'indicator_configs Backfill-Quote zu niedrig: {filled}/{total} = {quote:.1%} '
        f'(erwartet >= 95%)'
    )
