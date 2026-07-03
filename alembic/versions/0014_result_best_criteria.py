"""backtest_results: best_criteria_json (gewonnene Bestwert-Kriterien am Favoriten)

Fügt best_criteria_json an backtest_results hinzu. Wenn ein Result über run-bestwerte
zum roten Doku-Favoriten wird, hält diese Spalte fest, WELCHE der vier Kriterien
(Max Total Return / Win-Rate-Band / Sharpe-Band / Profitfaktor >= 30 Trades) es
gewonnen hat — als Liste stabiler Keys, nicht als Klartext-Label. Nötig, weil die
Bänder run-relativ sind und nach dem Löschen der übrigen Run-Results nicht mehr
herleitbar wären, während der rote Stern das Sieger-Result dauerhaft schützt.
Nullable — Alt-Results und Nicht-Favoriten bleiben NULL.

Revision ID: 0014_result_best_criteria
Revises: 0013_backtest_job_retry_count
Create Date: 2026-07-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0014_result_best_criteria'
down_revision: Union[str, Sequence[str], None] = '0013_backtest_job_retry_count'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fügt die Spalte best_criteria_json (JSON, nullable) hinzu."""
    op.add_column(
        'backtest_results',
        sa.Column('best_criteria_json', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    """Entfernt die Spalte best_criteria_json wieder."""
    op.drop_column('backtest_results', 'best_criteria_json')
