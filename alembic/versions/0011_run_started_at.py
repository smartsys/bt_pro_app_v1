"""backtest_runs: started_at (Verarbeitungsstart)

Fügt started_at an backtest_runs hinzu. Die Spalte wird beim Wechsel des Runs
auf Status 'running' gesetzt (Moment, in dem der Worker den Job aufgreift). Damit
lässt sich die echte Rechendauer (completed_at - started_at) ohne die
Queue-Wartezeit anzeigen. Nullable - bei vor dieser Migration angelegten Runs
bleibt der Wert NULL; das Frontend fällt dann auf created_at zurück.

Revision ID: 0011_run_started_at
Revises: 0010_result_filter_sort_indexes
Create Date: 2026-06-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0011_run_started_at'
down_revision: Union[str, Sequence[str], None] = '0010_result_filter_sort_indexes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fügt die nullable Spalte started_at hinzu."""
    op.add_column('backtest_runs', sa.Column('started_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Entfernt die Spalte started_at wieder."""
    op.drop_column('backtest_runs', 'started_at')
