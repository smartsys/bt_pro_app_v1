"""strategy_concepts.status erlaubt 'idee' (Ticket 66)

Anforderung 3 des Tickets ging davon aus, dass ``status`` ein freier String
ohne Schema-Änderung ist. Das stimmt nicht: ``strategy_concepts`` trägt seit
der Baseline (``_sql/0001_baseline.sql``) den Check-Constraint
``ck_strategy_concepts_status``, der nur ``'draft'``, ``'active'``,
``'archived'`` zulässt (per ``\\d strategy_concepts`` gegen die Dev-DB
verifiziert). Ohne diese Migration würde ein Konzept mit ``status='idee'``
mit einem Constraint-Verstoß abgelehnt. Der Constraint wird ersetzt durch
eine Fassung, die zusätzlich ``'idee'`` zulässt.

Revision ID: 0027_concept_status_idee
Revises: 0026_concept_goal_fields
Create Date: 2026-08-13
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0027_concept_status_idee'
down_revision: Union[str, Sequence[str], None] = '0026_concept_goal_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Erweitert ck_strategy_concepts_status um 'idee'."""
    op.drop_constraint('ck_strategy_concepts_status', 'strategy_concepts', type_='check')
    op.create_check_constraint(
        'ck_strategy_concepts_status',
        'strategy_concepts',
        "status IN ('draft', 'active', 'archived', 'idee')",
    )


def downgrade() -> None:
    """Stellt den ursprünglichen Constraint ohne 'idee' wieder her.

    Schlägt fehl, falls zu diesem Zeitpunkt noch Konzepte mit status='idee'
    existieren — das ist beabsichtigt (kein stiller Datenverlust).
    """
    op.drop_constraint('ck_strategy_concepts_status', 'strategy_concepts', type_='check')
    op.create_check_constraint(
        'ck_strategy_concepts_status',
        'strategy_concepts',
        "status IN ('draft', 'active', 'archived')",
    )
