"""walk_forward_chains — Walk-Forward als Fold-Kette

Legt die neue Tabelle ``walk_forward_chains`` an: je Kette ein Datensatz mit
vorregistriertem Plan (Fold-Zahl, Fensterlängen, konkrete Fold-Fenster,
Auswahlkriterium), den angehängten Fold-Blöcken und der Gesamtbewertung. Nach
``completed``/``failed`` ist der Datensatz unveränderlich.

Bewusst **ohne jeden Fremdschlüssel**: ``anchor_run_id``, ``iteration_id`` und
``concept_id`` sind lose Referenzen — analog ``significance_tests`` und
``testset_run_findings``. Die Ketten-Läufe und -Results werden regelmäßig
aufgeräumt; die Kette muss das überleben, deshalb trägt sie ihren Kontext in
``config_snapshot_json`` und alle tragenden Werte als Kopie in ``plan_json``,
``folds_json`` und ``aggregate_json``.

Ebenso bewusst **kein Verdict-Feld**: kein ``passed``, kein Score, keine Ampel.
Die Kette misst, sie urteilt nicht (dieselbe Regel wie bei DSR, Befund und
Signifikanztest).

Keine Baseline-Tabelle — der Daten-Load ``0021_seed_baseline_data_v3`` muss
nicht ans Kettenende umziehen (Regel aus CLAUDE.md, Abschnitt „Grundausstattung":
betroffen sind nur ``backtest_configs``, ``testsets`` und die Demo-Strategie-Zeilen).

Revision ID: 0031_walk_forward_chains
Revises: 0030_significance_tests
Create Date: 2026-08-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0031_walk_forward_chains'
down_revision: Union[str, Sequence[str], None] = '0030_significance_tests'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Legt walk_forward_chains mit drei Lookup-Indizes an (keine FKs, kein Unique)."""
    op.create_table(
        'walk_forward_chains',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        # Kontext (lose Referenzen, kein FK)
        sa.Column('anchor_run_id', sa.Integer(), nullable=False),
        sa.Column('iteration_id', sa.Integer(), nullable=True),
        sa.Column('concept_id', sa.Integer(), nullable=True),
        sa.Column('config_snapshot_json', postgresql.JSONB(none_as_null=True), nullable=True),
        # Plan (Vorregistrierung)
        sa.Column('plan_json', postgresql.JSONB(none_as_null=True), nullable=False),
        # Folds (append-only)
        sa.Column('folds_json', postgresql.JSONB(none_as_null=True), nullable=True),
        # Abschluss
        sa.Column('aggregate_json', postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column('method_note', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='running'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(), nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
        ),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )
    op.create_index(
        'idx_walk_forward_chains_iteration', 'walk_forward_chains', ['iteration_id'],
    )
    op.create_index(
        'idx_walk_forward_chains_anchor', 'walk_forward_chains', ['anchor_run_id'],
    )
    op.create_index(
        'idx_walk_forward_chains_created', 'walk_forward_chains', ['created_at'],
    )


def downgrade() -> None:
    """Entfernt walk_forward_chains wieder."""
    op.drop_index('idx_walk_forward_chains_created', table_name='walk_forward_chains')
    op.drop_index('idx_walk_forward_chains_anchor', table_name='walk_forward_chains')
    op.drop_index('idx_walk_forward_chains_iteration', table_name='walk_forward_chains')
    op.drop_table('walk_forward_chains')
