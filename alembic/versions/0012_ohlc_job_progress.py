"""ohlc_download_jobs: Intervall-Fortschrittsspalten

Fügt intervals_total/intervals_done an ohlc_download_jobs hinzu. Der Worker
schätzt intervals_total vor dem Laden aus (end - start) / timeframe und zählt
intervals_done pro abgerufenem Binance-Chunk hoch. Beide Spalten sind nullable -
bei vor dieser Migration angelegten Jobs bleiben sie NULL; das Frontend zeigt
dann nur den Status ohne Fortschrittsbalken.

Revision ID: 0012_ohlc_job_progress
Revises: 0011_run_started_at
Create Date: 2026-06-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0012_ohlc_job_progress'
down_revision: Union[str, Sequence[str], None] = '0011_run_started_at'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fügt die beiden nullable Fortschrittsspalten hinzu."""
    op.add_column('ohlc_download_jobs', sa.Column('intervals_total', sa.Integer(), nullable=True))
    op.add_column('ohlc_download_jobs', sa.Column('intervals_done', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Entfernt die Fortschrittsspalten wieder."""
    op.drop_column('ohlc_download_jobs', 'intervals_done')
    op.drop_column('ohlc_download_jobs', 'intervals_total')
