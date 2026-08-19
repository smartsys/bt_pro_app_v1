"""backtest_runs: usability + Vorlauf-Prüfung — der Lauf sagt, ob man ihm glauben darf

Ein Lauf ohne Signale endete bisher als 'completed'
mit null Trades und wanderte als gültiges Ergebnis in die Auswertung. Die Spalte
`usability` macht das ohne JSON-Auspacken abfragbar ('usable' / 'no_signals' /
'insufficient_history'), `usability_note` trägt den lesbaren Grund dazu. Der Lauf
selbst bleibt vollständig erhalten — es geht um Kennzeichnung, nicht um Ausblenden.

Die drei Vorlauf-Spalten halten fest, wie viel Vorlauf zwischen `ohlc_start` und
`start` tatsächlich zur Verfügung stand und wie viel die längste konfigurierte
Indikator-Periode gebraucht hätte (`warmup_note` als lesbare Meldung).

Bewusst nullable ohne Server-Default: NULL kennzeichnet Runs, die vor der Umstellung
entstanden sind (und fehlgeschlagene Runs, die nie bis zur Bewertung kamen). Der
Altbestand wird nicht nachgerechnet.

Revision ID: 0023_run_usability_warmup
Revises: 0022_result_long_short_bars
Create Date: 2026-08-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0023_run_usability_warmup'
down_revision: Union[str, Sequence[str], None] = '0022_result_long_short_bars'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fügt usability/usability_note und die drei Vorlauf-Spalten hinzu (nullable)."""
    op.add_column(
        'backtest_runs',
        sa.Column('usability', sa.String(length=32), nullable=True),
    )
    op.add_column(
        'backtest_runs',
        sa.Column('usability_note', sa.Text(), nullable=True),
    )
    op.add_column(
        'backtest_runs',
        sa.Column('warmup_bars', sa.Integer(), nullable=True),
    )
    op.add_column(
        'backtest_runs',
        sa.Column('warmup_required_bars', sa.Integer(), nullable=True),
    )
    op.add_column(
        'backtest_runs',
        sa.Column('warmup_note', sa.Text(), nullable=True),
    )
    # Index auf usability: der Preflight und das Befund-Artefakt filtern darauf
    # ("welche Läufe sind nicht verwertbar?") — ohne Index ein Seq Scan über alle Runs.
    op.create_index('idx_backtest_runs_usability', 'backtest_runs', ['usability'])


def downgrade() -> None:
    """Entfernt Index und Spalten wieder."""
    op.drop_index('idx_backtest_runs_usability', table_name='backtest_runs')
    op.drop_column('backtest_runs', 'warmup_note')
    op.drop_column('backtest_runs', 'warmup_required_bars')
    op.drop_column('backtest_runs', 'warmup_bars')
    op.drop_column('backtest_runs', 'usability_note')
    op.drop_column('backtest_runs', 'usability')
