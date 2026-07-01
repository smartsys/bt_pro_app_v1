"""backtest_jobs: retry_count (automatische Neustarts durch den Reaper)

Fügt retry_count an backtest_jobs hinzu. Der Reaper (services/api/reap_stale_jobs.py)
erkennt verwaiste Jobs (running ohne lebenden Worker, queued ohne RQ-Eintrag) und
reiht sie neu ein statt sie sofort auf failed zu setzen. retry_count zählt diese
automatischen Neustarts. Nach insgesamt 3 Startversuchen (Original + 2 Neustarts)
ohne Erfolg wird der Job endgültig auf failed gesetzt. NOT NULL mit Default 0,
damit bestehende Zeilen sauber gefüllt sind.

Revision ID: 0013_backtest_job_retry_count
Revises: 0012_ohlc_job_progress
Create Date: 2026-07-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0013_backtest_job_retry_count'
down_revision: Union[str, Sequence[str], None] = '0012_ohlc_job_progress'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fügt die Spalte retry_count (NOT NULL, Default 0) hinzu."""
    op.add_column(
        'backtest_jobs',
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    """Entfernt die Spalte retry_count wieder."""
    op.drop_column('backtest_jobs', 'retry_count')
