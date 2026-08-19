"""significance_tests — Signifikanztest je Kandidat (Ticket 79)

Legt die neue Tabelle ``significance_tests`` an: je Testlauf ein Datensatz, der
nach ``completed``/``failed`` unveränderlich ist. Zwei Methoden teilen sich die
Tabelle (``permutation`` = Monte-Carlo-Permutationstest gegen strukturlose
Preisreihen, ``bootstrap`` = Resampling der eigenen Trade-Renditen).

Bewusst **ohne jeden Fremdschlüssel**: ``result_id``, ``run_id`` und
``iteration_id`` sind lose Referenzen — analog ``testset_run_findings`` und
``leaderboard_entries``. Rechenspuren werden regelmäßig aufgeräumt; der Test muss
das überleben, deshalb trägt er seinen Kontext in ``params_json`` und
``config_snapshot_json`` selbst.

Ebenso bewusst **kein Verdict-Feld**: kein ``passed``, kein Score, keine Ampel.
Der Test berichtet, er filtert nicht (dieselbe Regel wie bei DSR und Befund).

Keine Baseline-Tabelle — der Daten-Load ``0021_seed_baseline_data_v3`` muss
nicht ans Kettenende umziehen (Regel aus CLAUDE.md, Abschnitt „Grundausstattung":
betroffen sind nur ``backtest_configs``, ``testsets`` und die Demo-Strategie-Zeilen).

Revision ID: 0030_significance_tests
Revises: 0029_testset_run_findings
Create Date: 2026-08-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0030_significance_tests'
down_revision: Union[str, Sequence[str], None] = '0029_testset_run_findings'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Legt significance_tests mit zwei Lookup-Indizes an (keine FKs, kein Unique)."""
    op.create_table(
        'significance_tests',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        # Kontext (lose Referenzen, kein FK)
        sa.Column('result_id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=True),
        sa.Column('iteration_id', sa.Integer(), nullable=True),
        sa.Column('params_json', postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column('config_snapshot_json', postgresql.JSONB(none_as_null=True), nullable=True),
        # Methode und Aufbau
        sa.Column('method', sa.String(length=20), nullable=False),
        sa.Column('n_iterations', sa.Integer(), nullable=False),
        sa.Column('seed', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='queued'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(), nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
        ),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        # Ergebnis
        sa.Column('real_values_json', postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column('distribution_json', postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column('summary_json', postgresql.JSONB(none_as_null=True), nullable=True),
    )
    op.create_index('idx_significance_tests_result', 'significance_tests', ['result_id'])
    op.create_index('idx_significance_tests_created', 'significance_tests', ['created_at'])


def downgrade() -> None:
    """Entfernt significance_tests wieder."""
    op.drop_index('idx_significance_tests_created', table_name='significance_tests')
    op.drop_index('idx_significance_tests_result', table_name='significance_tests')
    op.drop_table('significance_tests')
