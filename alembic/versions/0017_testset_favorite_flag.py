"""testsets.is_favorite Favoriten-Stern

Fügt der Tabelle testsets eine Integer-Spalte is_favorite (0/1) hinzu —
gelber Stern wie bei backtest_configs. Favoriten stehen in der TestSet-Liste
und im Test-Set-Dropdown der Start-Maske oben.

Revision ID: 0017_testset_favorite
Revises: 0016_result_run_sort_asc
Create Date: 2026-07-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0017_testset_favorite'
down_revision: Union[str, Sequence[str], None] = '0016_result_run_sort_asc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fügt die Favoriten-Spalte mit Default 0 hinzu."""
    op.add_column(
        'testsets',
        sa.Column(
            'is_favorite',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ),
    )


def downgrade() -> None:
    """Entfernt die Spalte wieder."""
    op.drop_column('testsets', 'is_favorite')
