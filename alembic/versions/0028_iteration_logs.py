"""iteration_logs — append-only Denkprotokoll je Iteration

Legt die neue Tabelle ``iteration_logs`` an: ein chronologisches, unveränder-
liches Log aus Freitext-Einträgen je Iteration. ``iteration_id`` trägt einen
FK auf ``strategy_iterations.id`` (NOT NULL, indiziert) — analog zum Muster
der bestehenden Kind-Tabellen. ``run_id`` ist bewusst **kein** FK (lose
Referenz nach Projektkonvention): Runs sind löschbar, der Log-Eintrag bleibt
danach weiterhin vollständig lesbar.

Erste Migration in diesem Projekt, die eine komplett neue Tabelle per
Alembic anlegt (alle bisherigen Tabellen kamen aus dem Baseline-SQL-Dump
``_sql/0001_baseline.sql``) — Spaltentypen und FK-Namenskonvention
(``fk_<tabelle>_<spalte>``) an den Bestand angelehnt (siehe z.B.
``fk_strategy_iterations_concept_id`` im Baseline-Dump).

Revision ID: 0028_iteration_logs
Revises: 0027_concept_status_idee
Create Date: 2026-08-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0028_iteration_logs'
down_revision: Union[str, Sequence[str], None] = '0027_concept_status_idee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Legt iteration_logs mit FK+Index auf iteration_id an (run_id ohne FK)."""
    op.create_table(
        'iteration_logs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('iteration_id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('text', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ['iteration_id'], ['strategy_iterations.id'],
            name='fk_iteration_logs_iteration_id',
        ),
    )
    op.create_index('idx_iteration_logs_iteration', 'iteration_logs', ['iteration_id'])


def downgrade() -> None:
    """Entfernt iteration_logs wieder."""
    op.drop_index('idx_iteration_logs_iteration', table_name='iteration_logs')
    op.drop_table('iteration_logs')
