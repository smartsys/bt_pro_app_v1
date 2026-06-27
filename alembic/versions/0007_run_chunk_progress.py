"""backtest_runs: Chunk-Fortschrittsspalten

Fügt current_chunk/total_chunks an backtest_runs hinzu. Der Spec-Runner meldet
im gechunkten Modus pro Chunk den Fortschritt an die DB, damit das Frontend bei
laufenden Runs "Chunk X/Y" anzeigen kann. Beide Spalten sind nullable - bei
ungechunkten oder vor dieser Migration angelegten Runs bleiben sie NULL.

Revision ID: 0007_run_chunk_progress
Revises: 0006_seed_baseline_data
Create Date: 2026-06-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0007_run_chunk_progress'
down_revision: Union[str, Sequence[str], None] = '0006_seed_baseline_data'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fügt die beiden nullable Fortschrittsspalten hinzu."""
    op.add_column('backtest_runs', sa.Column('current_chunk', sa.Integer(), nullable=True))
    op.add_column('backtest_runs', sa.Column('total_chunks', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Entfernt die Fortschrittsspalten wieder."""
    op.drop_column('backtest_runs', 'total_chunks')
    op.drop_column('backtest_runs', 'current_chunk')
