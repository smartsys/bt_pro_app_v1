"""
Datenbank-Verbindung

SQLAlchemy Engine und Session-Factory für PostgreSQL/TimescaleDB-Zugriff.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session


def _require_env(name: str) -> str:
    """Liest eine Pflicht-Umgebungsvariable; bricht hart ab, wenn sie fehlt oder leer ist."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Pflicht-Umgebungsvariable {name} fehlt oder ist leer "
            "(muss in .env bzw. der Container-Umgebung gesetzt sein)"
        )
    return value


def get_engine():
    """Erstellt SQLAlchemy Engine aus Umgebungsvariablen (alle Pflicht, kein Fallback)."""
    server = _require_env('POSTGRES_SERVER')
    port = _require_env('POSTGRES_PORT')
    database = _require_env('POSTGRES_DB')
    user = _require_env('POSTGRES_USER')
    password = _require_env('POSTGRES_PASSWORD')

    url = f"postgresql+psycopg2://{user}:{password}@{server}:{port}/{database}"
    return create_engine(url, pool_pre_ping=True)


# Gecachte Engine und Session-Factory
_engine = None
_session_factory = None


def get_session() -> Session:
    """Erstellt eine neue DB-Session mit gecachter Engine."""
    global _engine, _session_factory
    if _engine is None:
        _engine = get_engine()
        _session_factory = sessionmaker(bind=_engine)
    return _session_factory()
