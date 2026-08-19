"""Zentrale Test-Fixtures für die VBT App Test-Suite.

Stellt zwei Fixture-Ebenen bereit:
  - db_engine (session-scope): PostgreSQL-Engine gegen die Test-DB.
    Läuft Alembic-Migrationen einmalig pro Session.
  - session (function-scope): Isolierte DB-Session per Truncate aller Tabellen
    vor jedem Test (schneller als Schema-Drop, sicher bei Hypertables).

Safety-Check: Beim Start wird sichergestellt, dass die URL auf den Host der
Test-DB (db_bt_pro_v1_test) zeigt und NICHT auf die Arbeits-DB (db_bt_pro_v1
bzw. deren Host-Port 5560). Verstoß bricht den gesamten pytest-Lauf mit einem
harten Fehler ab.

Die Suite läuft ausschließlich im Container (Ticket 88):
    docker compose -f docker-compose-local.yml run --rm --build test

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
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

# Projekt-Root für Imports und .env-Laden
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

# .env laden damit VBT_TEST_DATABASE_URL verfügbar ist
load_dotenv(_ROOT / '.env')

from user_data.utils.database.models import Base  # noqa: E402

# Hostname der Test-DB im Docker-Netz. Einziges zulässiges Ziel für
# VBT_TEST_DATABASE_URL (Ticket 88) — siehe _assert_test_db().
TEST_DB_HOST = 'db_bt_pro_v1_test'

# Hostname und Host-Port der Arbeits-DB. Rein für die Fehlermeldung, damit ein
# Fehlgriff sofort benannt werden kann.
LIVE_DB_HOST = 'db_bt_pro_v1'
LIVE_DB_HOST_PORT = 5560


# ============================================================================
# Hilfsfunktionen
# ============================================================================

def _get_test_db_url() -> str:
    """Liest VBT_TEST_DATABASE_URL aus der Umgebung."""
    url = os.getenv('VBT_TEST_DATABASE_URL', '')
    if not url:
        pytest.exit(
            'VBT_TEST_DATABASE_URL ist nicht gesetzt. '
            'Die Suite läuft im Container-Dienst "test" '
            '(docker compose -f docker-compose-local.yml run --rm --build test), '
            f'der die Variable setzt. Erwartet: postgresql+psycopg2://...@{TEST_DB_HOST}:5432/vbt',
            returncode=1,
        )
    return url


def _assert_test_db(url: str) -> None:
    """Bricht ab, wenn die URL nicht auf die Test-DB zeigt.

    Geprüft wird der Hostname, nicht der Port: Der Host-Port 5560 der Arbeits-DB
    existiert im Container-Netz gar nicht, dort heißen die beiden Datenbanken
    db_bt_pro_v1 (Arbeit) und db_bt_pro_v1_test (Test). Beide tragen denselben
    Datenbanknamen, der Host ist also das einzige unterscheidende Merkmal.

    Die Prüfung ist bewusst eine Positivliste mit genau einem zulässigen Ziel:
    Jede andere Adresse — die Arbeits-DB unter beiden Schreibweisen ebenso wie die
    Host-Form der Test-DB aus dem alten venv-Weg — bricht den Lauf ab.
    """
    host = make_url(url).host or ''
    if host == TEST_DB_HOST:
        return

    if host == LIVE_DB_HOST:
        grund = f'auf den Arbeits-DB-Host ({LIVE_DB_HOST})'
    elif f':{LIVE_DB_HOST_PORT}' in url:
        grund = f'auf die Arbeits-DB (Host-Port {LIVE_DB_HOST_PORT})'
    else:
        grund = f'auf den unbekannten Host "{host}"'

    pytest.exit(
        f'SICHERHEITS-ABBRUCH: VBT_TEST_DATABASE_URL zeigt {grund}!\n'
        f'URL: {url}\n'
        f'Tests dürfen NIEMALS gegen die Arbeits-DB laufen. Einziges zulässiges Ziel ist '
        f'der Host {TEST_DB_HOST}. Die Suite wird im Container gefahren:\n'
        f'  docker compose -f docker-compose-local.yml run --rm --build test',
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
    """PostgreSQL-Engine gegen die dedizierte Test-DB (Host db_bt_pro_v1_test).

    Einmalig pro pytest-Session:
    - Safety-Check: URL muss auf die Test-DB zeigen, nie auf die Arbeits-DB.
    - Alembic-Migrationen werden angewendet (idempotent via 'upgrade head').
    """
    url = _get_test_db_url()
    _assert_test_db(url)
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
