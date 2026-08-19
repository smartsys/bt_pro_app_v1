"""strategy_concepts.probe_count — Zähler der Lite-Sondierungen

Der Befund weist mit ``N`` nur die Rastergröße der gespeicherten Läufe aus. Die
Lite-Sondierungen (``POST /api/chart-playground/run-backtest-lite``) schreiben
nichts in die Datenbank und tauchen deshalb nirgends auf — je sauberer nach der
Skill-Regel „klein sweepen" gearbeitet wird, desto mehr Suche wandert aus dem
Raster in diese unsichtbare Schleife. ``probe_count`` zählt sie am Konzept mit.

Reiner Ausweis: Der Wert wird nirgends bewertet, in keine Schwelle und in keine
DSR-Rechnung eingerechnet.

NOT NULL mit Server-Default 0 statt nullable — abweichend vom Arbeitstitel im
Ticket, aus zwei Gründen:

1. Semantik: Ein Konzept ohne Sondierungen hat null Sondierungen, nicht
   „unbekannt". NULL wäre eine Aussage, die niemand geprüft hat.
2. Der atomare Hochzähler (``probe_count = probe_count + 1``) ergäbe auf einer
   NULL-Zeile wieder NULL — der Zähler würde still verschwinden. Ein
   COALESCE-Fallback wäre genau der Kompensationspfad, den das Projekt
   ausschließt. Das Schwester-Feld ``iteration_counter`` derselben Tabelle ist
   aus demselben Grund NOT NULL mit Server-Default 0.

Baseline-Prüfung: ``strategy_concepts`` ist Baseline-Tabelle (Demo-Strategie im
Daten-Load ``0021_seed_baseline_data_v3``). Die INSERTs dort tragen eine
explizite Spaltenliste ohne ``probe_count``; die neue Spalte fließt über ihren
Server-Default mit 0 ein. Ein Umziehen des Daten-Loads ans Kettenende ist nicht
nötig, weil diese Migration sich ohnehin hinter 0021 hängt (aktuelles
Kettenende). Belegt am Neuinstallations-Test gegen eine frische, leere DB.

Revision ID: 0034_concept_probe_count
Revises: 0033_run_completed_chunks
Create Date: 2026-08-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0034_concept_probe_count'
down_revision: Union[str, Sequence[str], None] = '0033_run_completed_chunks'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fügt probe_count (NOT NULL, Default 0) an strategy_concepts hinzu."""
    op.add_column(
        'strategy_concepts',
        sa.Column('probe_count', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    """Entfernt probe_count wieder."""
    op.drop_column('strategy_concepts', 'probe_count')
