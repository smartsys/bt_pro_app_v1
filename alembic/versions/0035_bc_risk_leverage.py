"""backtest_configs.risk_pct/leverage/leverage_mode ergänzen

Drei neue Portfolio-Parameter für die risikobasierte Positionsgröße
(Ticket 104, Teilaufgabe 1):

- `risk_pct`: Float, nullable — der Kontoanteil je Trade (z.B. `0.03` = 3 %).
  Nur wirksam bei `size_type = 'risk_percent'`. `NULL` = nicht gesetzt, analog
  zu `stop_exit_price`/`stop_order_type` (kein erzwungener Wert).
- `leverage`: Float, NOT NULL, Default `1.0` — geht ab dieser Teilaufgabe
  IMMER an `from_signals`, unabhängig von `size_type`. `1.0` ist VBTs eigener
  Default (`vectorbtpro/_settings.py`, `portfolio.leverage`), also kein
  stiller Verhaltenswechsel für Bestandsconfigs.
- `leverage_mode`: String, NOT NULL, Default `'lazy'` — ebenfalls immer
  durchgereicht. `'lazy'` ist VBTs eigener Default
  (`vectorbtpro/_settings.py`, `portfolio.leverage_mode`).

Baseline-Prüfung: `backtest_configs` ist Baseline-Tabelle (Grundausstattung im
Daten-Load `0021_seed_baseline_data_v3`). Alle drei Spalten sind NOT NULL mit
Server-Default bzw. nullable ohne Server-Default — die INSERTs in `0021`
tragen eine explizite Spaltenliste ohne diese drei Spalten, sie fließen also
über ihren jeweiligen Server-Default (`1`/`'lazy'`) bzw. `NULL` ein. Ein
Umziehen des Daten-Loads ans Kettenende ist nicht nötig, weil diese Migration
sich ohnehin hinter `0021` (und hinter `0034`, dem aktuellen Kettenende) hängt
— analog zur Begründung in `0034_concept_probe_count`. Gegen eine frische,
leere DB verifiziert (`alembic upgrade head`).

Revision ID: 0035_bc_risk_leverage
Revises: 0034_concept_probe_count
Create Date: 2026-08-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0035_bc_risk_leverage'
down_revision: Union[str, Sequence[str], None] = '0034_concept_probe_count'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fügt risk_pct/leverage/leverage_mode an backtest_configs hinzu."""
    op.add_column(
        'backtest_configs',
        sa.Column('risk_pct', sa.Float(), nullable=True),
    )
    op.add_column(
        'backtest_configs',
        sa.Column('leverage', sa.Float(), nullable=False, server_default='1'),
    )
    op.add_column(
        'backtest_configs',
        sa.Column('leverage_mode', sa.String(length=20), nullable=False, server_default='lazy'),
    )


def downgrade() -> None:
    """Entfernt die drei Spalten wieder (Rollback-Pfad)."""
    op.drop_column('backtest_configs', 'leverage_mode')
    op.drop_column('backtest_configs', 'leverage')
    op.drop_column('backtest_configs', 'risk_pct')
