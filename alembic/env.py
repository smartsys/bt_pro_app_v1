"""Alembic Migrations — Umgebungskonfiguration.

Liest DB-URL aus Umgebungsvariablen (.env), falls vorhanden.
Bindet die SQLAlchemy-Models für autogenerate-Support ein.
"""

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Alembic Config-Objekt
config = context.config

# Logging aus alembic.ini einrichten
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# DB-URL aus .env-Datei lesen (hat Vorrang über alembic.ini-Fallback).
# Wird zuerst aus .env im Projekt-Root geladen, dann aus Umgebungsvariablen überschrieben.
def _load_dotenv(path: str) -> dict:
    """Liest Key=Value-Paare aus einer .env-Datei."""
    result = {}
    if not os.path.exists(path):
        return result
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, val = line.partition('=')
            result[key.strip()] = val.strip()
    return result

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_env_vars = _load_dotenv(os.path.join(_project_root, '.env'))


def _require_env(name: str) -> str:
    """Liest eine Pflicht-Variable aus Umgebung oder .env; bricht hart ab, wenn sie fehlt oder leer ist."""
    value = os.getenv(name) or _env_vars.get(name)
    if not value:
        raise RuntimeError(
            f"Pflicht-Umgebungsvariable {name} fehlt oder ist leer "
            "(muss in .env bzw. der Umgebung gesetzt sein)"
        )
    return value


# GEÄNDERT: Ticket 14 — VBT_TEST_DATABASE_URL hat Vorrang (Migrationen gegen Test-DB)
_test_url = os.getenv('VBT_TEST_DATABASE_URL', _env_vars.get('VBT_TEST_DATABASE_URL', ''))
if _test_url:
    _db_url = _test_url
else:
    _server = _require_env('POSTGRES_SERVER')
    _port = _require_env('POSTGRES_PORT')
    _db = _require_env('POSTGRES_DB')
    _user = _require_env('POSTGRES_USER')
    _password = _require_env('POSTGRES_PASSWORD')
    _db_url = f"postgresql+psycopg2://{_user}:{_password}@{_server}:{_port}/{_db}"
config.set_main_option('sqlalchemy.url', _db_url)

# Models für autogenerate-Support einbinden
from user_data.utils.database.models import Base  # noqa: E402
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Migrationen im Offline-Modus ausführen (ohne aktive DB-Verbindung)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Migrationen im Online-Modus ausführen (mit aktiver DB-Verbindung)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
