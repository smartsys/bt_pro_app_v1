"""drop stop columns from backtest_configs

Schritt 3c des Stop-Umbaus: Entfernt die fünf Stop-Spalten aus backtest_configs.
Stops leben jetzt ausschließlich im Meta-Key indicators_json['_stops']
(Eigentümer = IndicatorConfig); die Run-Snapshots wurden in Schritt 3a
(Migration 0002) gebackfillt, die Lesepfade in Schritt 3b umgestellt.

Zusätzlich werden inkompatible Alt-Leaderboard-Entries gelöscht: Entries, deren
Indikator-Snapshot (indicator_config_snapshot_json->'config_json') keinen '_stops'-
Key trägt, stammen aus der Zeit vor dem Stop-Umbau. Unter dem neuen Lesepfad
(Schritt 3c) würden sie ohne Stops reproduzieren und damit andere Kennzahlen
liefern als bei ihrer Entstehung — sie sind nicht reproduzierbar und werden
entfernt. Die Results bleiben unberührt: winning_result_ids_json ist nur eine
Referenzliste, kein Foreign Key.

Idempotent: Ein zweiter Lauf trifft 0 Zeilen (alle Alt-Entries bereits weg).

Revision ID: 0003_drop_stop_columns
Revises: 0002_backfill_stops_meta_key
Create Date: 2026-06-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0003_drop_stop_columns'
down_revision: Union[str, Sequence[str], None] = '0002_backfill_stops_meta_key'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


STOP_COLUMNS = ('tp_stop', 'sl_stop', 'tsl_th', 'tsl_stop', 'td_stop')


def upgrade() -> None:
    """Löscht inkompatible Alt-Entries und droppt die fünf Stop-Spalten."""
    conn = op.get_bind()

    # Inkompatible Alt-Leaderboard-Entries entfernen: ohne '_stops' im Indikator-
    # Snapshot nicht reproduzierbar. Der jsonb-Operator '?' prüft Key-Existenz;
    # NULL-Snapshots und fehlende 'config_json' fallen über NOT (... ? ...)
    # ebenfalls in die Löschmenge (kein '_stops' vorhanden = nicht reproduzierbar).
    result = conn.execute(
        sa.text(
            "DELETE FROM leaderboard_entries "
            "WHERE NOT (indicator_config_snapshot_json->'config_json' ? '_stops')"
        )
    )
    print(f"[drop stops] {result.rowcount} inkompatible Leaderboard-Entries gelöscht "
          f"(kein '_stops' im Indikator-Snapshot).")

    # Stop-Spalten droppen.
    for col in STOP_COLUMNS:
        op.drop_column('backtest_configs', col)
    print(f"[drop stops] {len(STOP_COLUMNS)} Stop-Spalten aus backtest_configs entfernt.")


def downgrade() -> None:
    """Stellt die fünf Stop-Spalten als nullable wieder her (Schema reversibel).

    Die Daten sind NICHT wiederherstellbar — die alten Stop-Werte wurden beim
    Drop verworfen; die Spalten kommen leer (NULL) zurück. Die in upgrade()
    gelöschten Leaderboard-Entries werden bewusst NICHT wiederhergestellt.
    """
    op.add_column('backtest_configs', sa.Column('tp_stop', sa.Float(), nullable=True))
    op.add_column('backtest_configs', sa.Column('sl_stop', sa.Float(), nullable=True))
    op.add_column('backtest_configs', sa.Column('tsl_th', sa.Float(), nullable=True))
    op.add_column('backtest_configs', sa.Column('tsl_stop', sa.Float(), nullable=True))
    op.add_column('backtest_configs', sa.Column('td_stop', sa.Integer(), nullable=True))
