"""testset_run_findings — Index auf concept_id (Ticket 85)

Die neue Route ``GET /api/testset-run-findings/by-concept/{concept_id}`` filtert
nach ``concept_id`` — bisher gab es dafür keinen Index (nur auf ``iteration_id``
und ``testset_run_id``, siehe Migration 0029). Keine Baseline-Tabelle, der
Daten-Load ``0021_seed_baseline_data_v3`` muss nicht ans Kettenende umziehen.

Revision ID: 0032_findings_concept_index
Revises: 0031_walk_forward_chains
Create Date: 2026-08-15
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0032_findings_concept_index'
down_revision: Union[str, Sequence[str], None] = '0031_walk_forward_chains'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Legt den Lookup-Index auf concept_id an."""
    op.create_index(
        'idx_testset_run_findings_concept', 'testset_run_findings', ['concept_id'],
    )


def downgrade() -> None:
    """Entfernt den Index wieder."""
    op.drop_index('idx_testset_run_findings_concept', table_name='testset_run_findings')
