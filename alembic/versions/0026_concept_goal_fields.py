"""strategy_concepts.goal_json + goal_prompt

Fügt zwei nullable Spalten an ``strategy_concepts`` hinzu, damit ein Konzept
sein Entwicklungsziel maschinenlesbar bei sich trägt:

- ``goal_json`` (JSONB) — strukturierte Zielgrößen, frei formuliert, kein
  festes Schema. Einzige Prüfung liegt in der API-Schicht (muss ein
  JSON-Objekt sein, wenn gesetzt).
- ``goal_prompt`` (Text) — der Original-Auftrag im Wortlaut.

Beide Felder halten das Ziel, sie bewerten nichts (kein Gate, kein Verdict).

Baseline-Prüfung (Anforderung 1 des Tickets): ``strategy_concepts`` trägt
INSERTs sowohl in ``_sql/0009_baseline_data.sql`` (historisch, inzwischen
No-op — siehe ``0009_seed_baseline_data_at_end``) als auch im tatsächlich
aktiven Daten-Load ``_sql/0021_baseline_data_v3.sql`` (Migration
``0021_seed_baseline_data_v3``, aktuelles Kettenende der Baseline-Loads).
Beide INSERTs tragen eine explizite Spaltenliste ohne ``goal_json``/
``goal_prompt`` — die neuen, nullable Spalten fließen dort einfach als NULL
ein. Die Kettenregel aus der CLAUDE.md (Daten-Load muss hinter
Schema-Migrationen liegen, die Baseline-Tabellen ändern) greift hier nicht:
diese Migration hängt sich ohnehin ans aktuelle Kettenende (hinter 0021 UND
hinter 0025), ein Verschieben ist nicht nötig.

Revision ID: 0026_concept_goal_fields
Revises: 0025_run_ann_factor
Create Date: 2026-08-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0026_concept_goal_fields'
down_revision: Union[str, Sequence[str], None] = '0025_run_ann_factor'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fügt goal_json (JSONB) und goal_prompt (Text) hinzu, beide nullable."""
    op.add_column('strategy_concepts', sa.Column('goal_json', postgresql.JSONB(), nullable=True))
    op.add_column('strategy_concepts', sa.Column('goal_prompt', sa.Text(), nullable=True))


def downgrade() -> None:
    """Entfernt beide Spalten wieder."""
    op.drop_column('strategy_concepts', 'goal_prompt')
    op.drop_column('strategy_concepts', 'goal_json')
