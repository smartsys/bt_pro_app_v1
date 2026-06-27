"""seed grundausstattung (verschoben nach 0009)

Früher lud diese Migration die Grundausstattung (alle ``backtest_configs`` +
``testsets``). Der Load wurde nach ``0009_seed_baseline_data_at_end``
verschoben und diese Migration ist jetzt eine bewusste No-op.

Grund: Die Grundausstattung muss am ECHTEN Ende der Schema-Kette laufen, damit
das regenerierte SQL alle Spalten der Baseline-Tabellen tragen kann. Seit
``0007``/``0008`` ist 0006 nicht mehr das Kettenende - insbesondere fügt 0008
``testsets.leaderboard_enabled`` hinzu. Ein Load an dieser Stelle würde
brechen, sobald ``export_baseline.py`` (pg_dump --column-inserts) die Spalte
mit ausgibt. Daher liegt der Load nun in 0009, nach allen Schema-Migrationen.

Sicher für bestehende DBs: Alembic führt bereits angewandte Revisionen nie
erneut aus. DBs, die über das alte (ladende) 0006 hochgezogen sind, behalten
ihre Daten; 0009 überspringt sie per Leerheits-Check. Frische Installationen
und DBs <= 0005 laufen hier durch und laden erst in 0009.

Revision ID: 0006_seed_baseline_data
Revises: 0005_bc_favorite_flag
Create Date: 2026-06-18
"""
from typing import Sequence, Union

revision: str = '0006_seed_baseline_data'
down_revision: Union[str, Sequence[str], None] = '0005_bc_favorite_flag'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op: Der Grundausstattungs-Load liegt jetzt in 0009 (Kettenende)."""
    pass


def downgrade() -> None:
    # Bewusst no-op (war schon immer no-op: Seed-Zeilen sind nachträglich nicht
    # von echten Nutzerdaten unterscheidbar).
    pass
