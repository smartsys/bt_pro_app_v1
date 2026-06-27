"""Zentrale Test-Fixtures für die VBT App Test-Suite.

Stellt zwei Fixture-Ebenen bereit:
  - db_engine (session-scope): PostgreSQL-Engine gegen die Test-DB.
    Läuft Alembic-Migrationen einmalig pro Session.
  - session (function-scope): Isolierte DB-Session per Truncate aller Tabellen
    vor jedem Test (schneller als Schema-Drop, sicher bei Hypertables).

Safety-Check: Beim Start wird sichergestellt, dass die URL auf die Test-DB
(Port 5562) zeigt und NICHT auf die Arbeits-DB (Port 5560 / Host db_bt_pro_v1).
Verstoß bricht den gesamten pytest-Lauf mit einem harten Fehler ab.

Ebenfalls enthalten: SQLite-Fixtures für reine Unit-Tests (test_engine,
test_session) die kein PostgreSQL benötigen.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Generator

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

# Projekt-Root für Imports und .env-Laden
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

# .env laden damit VBT_TEST_DATABASE_URL verfügbar ist
load_dotenv(_ROOT / '.env')

# GEÄNDERT: Ticket 14 — Test-Dateien ausschließen, die vectorbtpro direkt importieren.
# vectorbtpro ist nur im Windows-venv verfügbar, nicht in der WSL-Python-Installation.
# Diese Tests können nur mit dem korrekten Interpreter ausgeführt werden.
collect_ignore = [
    'test_spec_runner_version.py',
    'test_spec_runner_reads_iteration.py',
]

from user_data.utils.database.models import Base  # noqa: E402


# ============================================================================
# Hilfsfunktionen
# ============================================================================

def _get_test_db_url() -> str:
    """Liest VBT_TEST_DATABASE_URL aus der Umgebung."""
    url = os.getenv('VBT_TEST_DATABASE_URL', '')
    if not url:
        pytest.exit(
            'VBT_TEST_DATABASE_URL ist nicht gesetzt. '
            'Bitte .env prüfen (Ticket 14). '
            'Erwartet: postgresql+psycopg2://...@localhost:5562/vbt',
            returncode=1,
        )
    return url


def _assert_not_live_db(url: str) -> None:
    """Bricht ab wenn die URL auf die Arbeits-DB zeigt.

    Schützt die Arbeits-DB (Port 5560, Host db_bt_pro_v1) vor versehentlichem
    Überschreiben durch Tests.
    """
    # Port 5560 ist der Arbeits-DB-Port
    if ':5560/' in url or ':5560' == url.rsplit('/', 1)[0][-5:]:
        pytest.exit(
            f'SICHERHEITS-ABBRUCH: VBT_TEST_DATABASE_URL zeigt auf die Arbeits-DB (Port 5560)!\n'
            f'URL: {url}\n'
            f'Tests dürfen NIEMALS gegen die Arbeits-DB laufen. '
            f'Test-DB-Port ist 5562.',
            returncode=1,
        )
    # Host db_bt_pro_v1 ist der interne Docker-Hostname der Arbeits-DB
    if '@db_bt_pro_v1:' in url or '@db_bt_pro_v1/' in url:
        pytest.exit(
            f'SICHERHEITS-ABBRUCH: VBT_TEST_DATABASE_URL zeigt auf den Arbeits-DB-Host (db_bt_pro_v1)!\n'
            f'URL: {url}\n'
            f'Tests dürfen NIEMALS gegen die Arbeits-DB laufen.',
            returncode=1,
        )


def _apply_migrations(url: str) -> None:
    """Wendet Alembic-Migrationen gegen die Test-DB an.

    Setzt VBT_TEST_DATABASE_URL als Umgebungsvariable, damit alembic/env.py
    die Test-DB-URL bevorzugt.
    """
    env = os.environ.copy()
    env['VBT_TEST_DATABASE_URL'] = url
    result = subprocess.run(
        [sys.executable, '-m', 'alembic', 'upgrade', 'head'],
        cwd=str(_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.exit(
            f'Alembic-Migration gegen Test-DB fehlgeschlagen:\n{result.stderr}',
            returncode=1,
        )


def _truncate_all_tables(engine: Engine) -> None:
    """Leert alle Tabellen in der Test-DB via TRUNCATE CASCADE.

    Schneller als Schema-Drop und sicher bei TimescaleDB-Hypertables.
    Die Reihenfolge ist irrelevant wegen CASCADE.
    """
    inspector = inspect(engine)
    tables = inspector.get_table_names(schema='public')
    # Alembic-interne Tabelle nicht leeren
    tables = [t for t in tables if t != 'alembic_version']
    if not tables:
        return
    table_list = ', '.join(f'"{t}"' for t in tables)
    with engine.begin() as conn:
        conn.execute(text(f'TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE'))


# ============================================================================
# PostgreSQL Test-DB Fixtures (für alle Tests die PostgreSQL benötigen)
# ============================================================================

@pytest.fixture(scope='session')
def db_engine() -> Generator[Engine, None, None]:
    """PostgreSQL-Engine gegen die dedizierte Test-DB (Port 5562).

    Einmalig pro pytest-Session:
    - Safety-Check: URL darf nicht auf Arbeits-DB zeigen.
    - Alembic-Migrationen werden angewendet (idempotent via 'upgrade head').
    """
    url = _get_test_db_url()
    _assert_not_live_db(url)
    _apply_migrations(url)
    engine = create_engine(url, echo=False)
    yield engine
    engine.dispose()


@pytest.fixture(scope='function')
def session(db_engine: Engine) -> Generator[Session, None, None]:
    """Isolierte DB-Session pro Test-Funktion via Truncate-Pattern.

    Vor jedem Test werden alle Tabellen geleert (TRUNCATE CASCADE),
    sodass jeder Test mit einer leeren DB startet. Savepoint-Pattern
    wird nicht verwendet, da nested Transaktionen bei TimescaleDB-
    Hypertables Probleme verursachen können.
    """
    _truncate_all_tables(db_engine)
    SessionFactory = sessionmaker(bind=db_engine)
    sess = SessionFactory()
    yield sess
    sess.close()


# ============================================================================
# SQLite In-Memory Fixtures (für reine Unit-Tests ohne PostgreSQL)
# ============================================================================

@pytest.fixture(scope='function')
def test_engine():
    """Erstellt eine In-Memory-SQLite-Engine für Unit-Tests."""
    engine = create_engine('sqlite://', echo=False)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope='function')
def test_session(test_engine):
    """Erstellt eine Test-Session gegen SQLite und räumt nach dem Test auf."""
    SessionFactory = sessionmaker(bind=test_engine)
    sess = SessionFactory()
    yield sess
    sess.close()
