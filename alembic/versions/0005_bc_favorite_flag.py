"""rename backtest_configs.is_default to is_favorite

Ersetzt das exklusive Default-Flag (genau eine Config = Default, im
Backtest-Start-Formular automatisch vorausgewählt) durch einen
nicht-exklusiven Favoriten-Stern, analog zu Konzepten/Iterationen/Results.

Ein reines RENAME bewahrt den Bestand: eine bisher als Default markierte
Config wird damit zum Favoriten. Die früher nötige Exklusivität (nur eine
Config = 1) wird in der API aufgegeben; mehrere Favoriten sind erlaubt.
Der zugehörige Index idx_bc_default wird zu idx_bc_favorite umbenannt.

Revision ID: 0005_bc_favorite_flag
Revises: 0004_move_stop_formats_to_stops
Create Date: 2026-06-18
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0005_bc_favorite_flag'
down_revision: Union[str, Sequence[str], None] = '0004_move_stop_formats_to_stops'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Benennt Spalte und Index um (Bestand bleibt erhalten)."""
    op.alter_column('backtest_configs', 'is_default', new_column_name='is_favorite')
    op.execute('ALTER INDEX IF EXISTS idx_bc_default RENAME TO idx_bc_favorite')


def downgrade() -> None:
    """Macht die Umbenennung rückgängig."""
    op.execute('ALTER INDEX IF EXISTS idx_bc_favorite RENAME TO idx_bc_default')
    op.alter_column('backtest_configs', 'is_favorite', new_column_name='is_default')
