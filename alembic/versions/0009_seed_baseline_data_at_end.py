"""seed grundausstattung am ende der schema-kette

Lädt die neutrale Grundausstattung, die jede Neuinstallation von Anfang an
mitbringen soll: alle ``backtest_configs`` (Symbol-/Zeitraum-/Portfolio-
Vorlagen) und alle ``testsets`` (Symbol-Körbe inkl. ``leaderboard_enabled``).
Keine privaten Strategien, Runs oder Leaderboard-Einträge.

Löst die frühere Daten-Migration 0006 ab (jetzt No-op): Der Load muss am
ECHTEN Ende der Schema-Kette laufen, damit das via ``seed/export_baseline.py``
regenerierte SQL alle Spalten der Baseline-Tabellen tragen kann - z.B. die in
0008 ergänzte Spalte ``testsets.leaderboard_enabled``. Läge der Load (wie
0006) vor 0008, würde er brechen, sobald pg_dump diese Spalte mit ausgibt.

Idempotenz: Es wird nur in eine leere DB eingefügt. Bestehende DBs (die die
Daten über das alte 0006 oder anderweitig bereits haben) überspringen den
Insert sichtbar - so entsteht kein PK-Konflikt.

Revision ID: 0009_seed_baseline_data_at_end
Revises: 0008_testset_leaderboard_flag
Create Date: 2026-06-19
"""
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0009_seed_baseline_data_at_end'
down_revision: Union[str, Sequence[str], None] = '0008_testset_leaderboard_flag'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SQL_DIR = Path(__file__).parent / '_sql'


def upgrade() -> None:
    """Lädt die Grundausstattung - nur in eine leere DB."""
    conn = op.get_bind()
    bc_count = conn.execute(sa.text('SELECT count(*) FROM backtest_configs')).scalar() or 0
    ts_count = conn.execute(sa.text('SELECT count(*) FROM testsets')).scalar() or 0
    if bc_count or ts_count:
        # Sichtbar überspringen statt still scheitern (kein PK-Konflikt auf
        # bestehenden DBs, die die Daten schon haben).
        print(
            f'0009_seed_baseline_data_at_end: Grundausstattung übersprungen - Tabellen '
            f'nicht leer (backtest_configs={bc_count}, testsets={ts_count}).'
        )
        return
    data_sql = (_SQL_DIR / '0009_baseline_data.sql').read_text(encoding='utf-8')
    op.execute(data_sql)


def downgrade() -> None:
    # Bewusst no-op: Aus dem Seed eingefügte Zeilen sind nachträglich nicht von
    # echten Nutzerdaten unterscheidbar - ein DELETE würde fremde Daten treffen.
    pass
