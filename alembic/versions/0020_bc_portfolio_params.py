"""backtest_configs.slippage/stop_exit_price/stop_order_type ergänzen

Ticket 59: Drei Portfolio-Parameter, die bisher entweder gar nicht existierten
(`slippage`, Ticket 55) oder nur transient im Playground-Formular lebten
(`stop_exit_price`/`stop_order_type`, Ticket 52), werden reguläre Spalten der
BacktestConfig — persistiert, in jedem Rechenpfad wirksam.

- `slippage`: Float, NOT NULL, Default `0.0` — entspricht dem bisherigen
  impliziten VBT-Default (kein Slippage-Parameter wurde bisher je an
  `from_signals` übergeben). Bestandsconfigs bekommen `0.0` und rechnen exakt
  wie bisher, kein stiller Verhaltenswechsel.
- `stop_exit_price` / `stop_order_type`: String, nullable. `NULL` bedeutet
  „VBT-Default" (keine erzwungene Voreinstellung) — dieselbe Konvention, die
  das Playground-JS bereits nutzt.

`backtest_configs` ist eine Baseline-Tabelle (CLAUDE.md, Abschnitt
„Grundausstattung"). Der Daten-Load `0009_seed_baseline_data_at_end` muss daher
hinter diese Migration gezogen werden, analog zum Präzedenzfall `0006 -> 0009`:
`0009` wird zur bewussten No-op (siehe dortiger Docstring), `0021` übernimmt den
Load ans neue Kettenende mit frisch gezogenem `_sql`-Dump.

Revision ID: 0020_bc_portfolio_params
Revises: 0019_drop_testset_runs_fk
Create Date: 2026-08-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0020_bc_portfolio_params'
down_revision: Union[str, Sequence[str], None] = '0019_drop_testset_runs_fk'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fügt die drei neuen Portfolio-Spalten hinzu."""
    op.add_column(
        'backtest_configs',
        sa.Column('slippage', sa.Float(), nullable=False, server_default='0'),
    )
    op.add_column(
        'backtest_configs',
        sa.Column('stop_exit_price', sa.String(length=20), nullable=True),
    )
    op.add_column(
        'backtest_configs',
        sa.Column('stop_order_type', sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    """Entfernt die drei Spalten wieder (Rollback-Pfad)."""
    op.drop_column('backtest_configs', 'stop_order_type')
    op.drop_column('backtest_configs', 'stop_exit_price')
    op.drop_column('backtest_configs', 'slippage')
