"""backtest_runs.ann_factor dazu, alte Deflated-Sharpe-Werte leeren

Die Deflated Sharpe Ratio wird nicht mehr je Kombination aus VBT
gezogen, sondern als Nachlauf über den ganzen Lauf mit korrigierter Formel
gerechnet (`user_data/utils/metrics/deflated_sharpe.py`).

Zwei Änderungen, die zusammengehören:

1. **`backtest_runs.ann_factor`** — der Annualisierungsfaktor des Laufs, genau
   der Wert, den VBT selbst benutzt (`ReturnsAccessor.ann_factor`). Der
   gespeicherte `backtest_results.sharpe_ratio` ist annualisiert; die DSR-Formel
   braucht den Sharpe je Balken. Mit diesem Faktor ist die Rückrechnung
   `SR_bar = SR_ann / sqrt(ann_factor)` exakt. Nullable ohne Server-Default:
   NULL kennzeichnet Läufe von vor diesem Ticket.

2. **Alte DSR-Werte werden geleert**, wo die Momente fehlen. Results ohne
   persistierte `skew`/`kurtosis` (also alles vor Migration 0024) sind nach der
   alten, defekten Formel entstanden und lassen sich ohne die Momente nicht
   nachrechnen. Ein leeres Feld ist ehrlich, ein falsch gefülltes nicht. Die
   Bedingung ist rein strukturell — sie braucht weder eine Versionsspalte noch
   eine Änderung an den Auslieferungsstellen.

`backtest_runs` und `backtest_results` sind keine Baseline-Tabellen; der
Daten-Load am Kettenende (0009) muss deshalb nicht umziehen.

Revision ID: 0025_run_ann_factor
Revises: 0024_result_skew_kurtosis
Create Date: 2026-08-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0025_run_ann_factor'
down_revision: Union[str, Sequence[str], None] = '0024_result_skew_kurtosis'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fügt ann_factor hinzu und leert DSR-Werte ohne persistierte Momente."""
    op.add_column('backtest_runs', sa.Column('ann_factor', sa.Float(), nullable=True))
    op.execute(
        "UPDATE backtest_results SET deflated_sharpe_ratio = NULL "
        "WHERE deflated_sharpe_ratio IS NOT NULL "
        "AND (skew IS NULL OR kurtosis IS NULL)"
    )


def downgrade() -> None:
    """Entfernt ann_factor wieder.

    Die geleerten DSR-Werte werden **nicht** wiederhergestellt: sie stammen aus
    der defekten Formel und sind ohne die Momente nicht rekonstruierbar. Das
    Zurückrollen der Spalte ist damit vollständig, das Zurückrollen der Daten
    bewusst nicht.
    """
    op.drop_column('backtest_runs', 'ann_factor')
