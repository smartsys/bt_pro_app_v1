"""backtest_results.open_trades — am Fensterende offene Positionen

Ticket 58: Kennzahlen laufen ausschließlich über das Handelsfenster start..end
der BacktestConfig. Eine Position, die über `end` hinausläuft, wird zur
Fenstergrenze marktbewertet und geht damit in total_return_pct und end_value
ein, nicht aber in win_rate_pct und profit_factor (die rechnen über
geschlossene Trades). Die neue Spalte macht diesen Fall je Result sichtbar:
total_trades - open_trades ist die Grundgesamtheit von Trefferquote und
Profitfaktor.

Bewusst nullable ohne Server-Default: NULL kennzeichnet Results, die vor
Ticket 58 entstanden sind (spec_runner_version < 3.0.0) und deren Kennzahlen
noch über das volle Datenfenster inklusive Vorlauf gerechnet wurden. Der
Altbestand wird nicht nachgerechnet.

Revision ID: 0018_result_open_trades
Revises: 0017_testset_favorite
Create Date: 2026-08-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0018_result_open_trades'
down_revision: Union[str, Sequence[str], None] = '0017_testset_favorite'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fügt die Spalte open_trades hinzu (nullable, kein Backfill)."""
    op.add_column(
        'backtest_results',
        sa.Column('open_trades', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Entfernt die Spalte wieder."""
    op.drop_column('backtest_results', 'open_trades')
