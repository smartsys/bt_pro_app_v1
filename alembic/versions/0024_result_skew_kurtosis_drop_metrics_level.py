"""backtest_results.skew/kurtosis dazu, metrics_level weg — eine Kennzahl-Funktion

Kennzahlen entstehen ab jetzt in genau einer Funktion
(`_extract_metrics`), die für jeden Lauf denselben Satz liefert. Damit verliert
`metrics_level` ('partial'/'chart'/'full') seinen Zweck: Es gibt keine
Berechnungsstufen mehr, die man einem Result ansehen müsste.

Neu dazu kommen `skew` und `kurtosis` je Kombination — die Bausteine, ohne die
die Deflated Sharpe Ratio nicht nachrechenbar ist. Gespeichert wird
die ROHE Wölbung (Normalverteilung rund 3), nicht die Excess-Wölbung.

Bewusst nullable ohne Server-Default und ohne Backfill: NULL kennzeichnet
Results, die vor der Umstellung entstanden sind. Der Altbestand wird nicht
nachgerechnet — der Schnitt ist gewollt (markieren statt rechnen).

`backtest_results` ist keine Baseline-Tabelle; der Daten-Load am Kettenende
(0009) muss deshalb nicht umziehen.

Revision ID: 0024_result_skew_kurtosis
Revises: 0023_run_usability_warmup
Create Date: 2026-08-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0024_result_skew_kurtosis'
down_revision: Union[str, Sequence[str], None] = '0023_run_usability_warmup'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fügt skew/kurtosis hinzu und entfernt die Spalte metrics_level."""
    op.add_column('backtest_results', sa.Column('skew', sa.Float(), nullable=True))
    op.add_column('backtest_results', sa.Column('kurtosis', sa.Float(), nullable=True))
    op.drop_column('backtest_results', 'metrics_level')


def downgrade() -> None:
    """Stellt metrics_level wieder her und entfernt skew/kurtosis."""
    op.add_column(
        'backtest_results',
        sa.Column(
            'metrics_level',
            sa.String(length=10),
            nullable=False,
            server_default='partial',
        ),
    )
    op.drop_column('backtest_results', 'kurtosis')
    op.drop_column('backtest_results', 'skew')
