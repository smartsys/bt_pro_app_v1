"""testset_run_findings — Befund je Testset-Lauf

Legt die neue Tabelle ``testset_run_findings`` an: je Testset-Lauf ein
unveränderlicher Datensatz, der beim Start Kontext und Soll aufnimmt und beim
Abschluss einmalig um die Ist-Werte ergänzt wird.

Bewusst **ohne jeden Fremdschlüssel**: Alle Kontext-Referenzen
(``testset_run_id``, ``iteration_id``, ``concept_id``, ``testset_id``,
``indicator_config_id``) sind lose Referenzen — analog zu
``leaderboard_entries.testset_id``/``testset_run_id``. Der Befund muss das
Aufräumen der operativen Tabellen überleben; ein FK würde entweder das Löschen
blockieren oder den Befund mitreißen.

Ebenso bewusst **ohne Unique-Constraint** auf ``testset_run_id``: ein erneuter
Lauf erzeugt einen neuen Befund, überschrieben wird nie.

Keine Baseline-Tabelle — der Daten-Load ``0021_seed_baseline_data_v3`` muss
nicht ans Kettenende umziehen.

Revision ID: 0029_testset_run_findings
Revises: 0028_iteration_logs
Create Date: 2026-08-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0029_testset_run_findings'
down_revision: Union[str, Sequence[str], None] = '0028_iteration_logs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Legt testset_run_findings mit zwei Lookup-Indizes an (keine FKs, kein Unique)."""
    op.create_table(
        'testset_run_findings',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        # Kontext (Phase 1)
        sa.Column('testset_run_id', sa.Integer(), nullable=True),
        sa.Column('iteration_id', sa.Integer(), nullable=False),
        sa.Column('concept_id', sa.Integer(), nullable=True),
        sa.Column('testset_id', sa.Integer(), nullable=False),
        sa.Column('indicator_config_id', sa.Integer(), nullable=True),
        sa.Column('spec_runner_version', sa.String(length=20), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(), nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
        ),
        # Soll (Phase 1)
        sa.Column('goal_snapshot_json', postgresql.JSONB(), nullable=True),
        sa.Column('goal_missing_reason', sa.Text(), nullable=True),
        sa.Column('best_criteria_json', postgresql.JSONB(), nullable=False),
        sa.Column('planned_n_runs', sa.Integer(), nullable=False),
        sa.Column('planned_combos_per_run', sa.Integer(), nullable=True),
        sa.Column('planned_combos_total', sa.Integer(), nullable=True),
        sa.Column('planned_grid_reason', sa.Text(), nullable=True),
        # Ist (Phase 2)
        sa.Column('scope_json', postgresql.JSONB(), nullable=True),
        sa.Column('candidates_json', postgresql.JSONB(), nullable=True),
        sa.Column('robustness_json', postgresql.JSONB(), nullable=True),
        sa.Column('benchmarks_json', postgresql.JSONB(), nullable=True),
        sa.Column('warnings_json', postgresql.JSONB(), nullable=True),
        sa.Column('holdout_touched', sa.Boolean(), nullable=True),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        # Deutung (nachträglich, getrennt von den Zahlen)
        sa.Column('interpretation_text', sa.Text(), nullable=True),
        sa.Column('interpretation_at', sa.DateTime(), nullable=True),
    )
    op.create_index(
        'idx_testset_run_findings_iteration', 'testset_run_findings', ['iteration_id'],
    )
    op.create_index(
        'idx_testset_run_findings_testset_run', 'testset_run_findings', ['testset_run_id'],
    )


def downgrade() -> None:
    """Entfernt testset_run_findings wieder."""
    op.drop_index('idx_testset_run_findings_testset_run', table_name='testset_run_findings')
    op.drop_index('idx_testset_run_findings_iteration', table_name='testset_run_findings')
    op.drop_table('testset_run_findings')
