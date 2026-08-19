"""backtest_results.long_trades/short_trades/bar_count — Selbstauskunft je Result

Ein Result kann ohne JSON-Auspacken sagen, wie
viele Long- und wie viele Short-Trades es enthielt (Summe = total_trades,
gemessen im vbt-Kernel: `trades.direction_long`/`.direction_short.count()`)
und wie viele Balken das tatsächlich gerechnete Handelsfenster umfasste
(`pf.wrapper.shape[0]`). Der gerechnete Zeitraum selbst nutzt die seit Ticket
58 vorhandenen Spalten `start_index`/`end_index`/`total_duration` — die werden
mit diesem Ticket zusätzlich vom Multi-Kombinations-Pfad
(`_extract_partial_metrics`) befüllt, brauchen aber keine neue Spalte.

Bewusst nullable ohne Server-Default: NULL kennzeichnet Results, die vor
der Umstellung entstanden sind. Der Altbestand wird nicht nachgerechnet.

Revision ID: 0022_result_long_short_bars
Revises: 0021_seed_baseline_data_v3
Create Date: 2026-08-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0022_result_long_short_bars'
down_revision: Union[str, Sequence[str], None] = '0021_seed_baseline_data_v3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fügt long_trades/short_trades/bar_count hinzu (nullable, kein Backfill)."""
    op.add_column(
        'backtest_results',
        sa.Column('long_trades', sa.Integer(), nullable=True),
    )
    op.add_column(
        'backtest_results',
        sa.Column('short_trades', sa.Integer(), nullable=True),
    )
    op.add_column(
        'backtest_results',
        sa.Column('bar_count', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Entfernt die Spalten wieder."""
    op.drop_column('backtest_results', 'bar_count')
    op.drop_column('backtest_results', 'short_trades')
    op.drop_column('backtest_results', 'long_trades')
