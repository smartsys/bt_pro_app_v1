"""backtest_runs.completed_chunks — Fortsetzungspunkt eines gechunkten Laufs

Ticket 71: Ein gechunkter Multiparameterlauf schreibt seine Ergebnisse ab sofort
nach jedem Chunk in die Datenbank, statt sie bis zum Schluss im Speicher zu
halten. Damit ein hart abgebrochener Lauf fortgesetzt werden kann, muss am Lauf
stehen, wie viele der (deterministisch gebildeten) Chunks bereits vollständig
gespeichert sind.

`completed_chunks` zählt die von vorn her fertigen Chunks. Der Wert wird in
derselben Transaktion geschrieben wie die Results des Chunks — er kann also nie
mehr Chunks behaupten, als tatsächlich in der Datenbank stehen. Ein Neustart
über den Rerun-Weg (löscht alle Results) setzt ihn zurück auf 0.

NOT NULL mit Server-Default 0: Ein Altbestands-Lauf ohne Teilergebnisse fängt
bei 0 an, also von vorn — das ist für ihn der richtige Wert.

`backtest_runs` ist keine Baseline-Tabelle; der Daten-Load am Kettenende
(0021) muss deshalb nicht umziehen.

Revision ID: 0033_run_completed_chunks
Revises: 0032_findings_concept_index
Create Date: 2026-08-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0033_run_completed_chunks'
down_revision: Union[str, Sequence[str], None] = '0032_findings_concept_index'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fügt completed_chunks (NOT NULL, Default 0) hinzu."""
    op.add_column(
        'backtest_runs',
        sa.Column(
            'completed_chunks', sa.Integer(), nullable=False, server_default='0'
        ),
    )


def downgrade() -> None:
    """Entfernt completed_chunks wieder."""
    op.drop_column('backtest_runs', 'completed_chunks')
