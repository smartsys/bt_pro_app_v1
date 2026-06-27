"""testsets.leaderboard_enabled Opt-in-Schalter

Fügt der Tabelle testsets eine Boolean-Spalte leaderboard_enabled hinzu.
Nur bei True wird nach einem TestSet-Lauf ein LeaderboardEntry erstellt.
Default False (Opt-in) — bestehende Testsets erzeugen ohne bewusstes
Aktivieren keine Leaderboard-Einträge mehr.

Revision ID: 0008_testset_leaderboard_flag
Revises: 0007_run_chunk_progress
Create Date: 2026-06-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0008_testset_leaderboard_flag'
down_revision: Union[str, Sequence[str], None] = '0007_run_chunk_progress'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fügt die Opt-in-Spalte mit Default False hinzu."""
    op.add_column(
        'testsets',
        sa.Column(
            'leaderboard_enabled',
            sa.Boolean(),
            nullable=False,
            server_default='false',
        ),
    )


def downgrade() -> None:
    """Entfernt die Spalte wieder."""
    op.drop_column('testsets', 'leaderboard_enabled')
