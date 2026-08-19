"""seed grundausstattung am ende der schema-kette (verschoben nach 0021)

Früher lud diese Migration die Grundausstattung (alle ``backtest_configs`` +
``testsets``) an der damals aktuellen Kettenspitze. Der Load wurde nach
``0021_seed_baseline_data_v3`` verschoben und diese Migration ist jetzt eine
bewusste No-op — exakt derselbe Mechanismus wie schon einmal bei
``0006_seed_baseline_data`` (siehe dortiger Docstring), nur eine Kettenstufe
weiter.

Grund: ``0020_bc_portfolio_params`` fügt
``backtest_configs.slippage/stop_exit_price/stop_order_type`` hinzu - eine
weitere Schema-Änderung an einer Baseline-Tabelle nach dieser Migration. Der
Load muss am ECHTEN Ende der Schema-Kette laufen, damit das per pg_dump
regenerierte SQL alle Spalten der Baseline-Tabellen trägt. Läge der Load (wie
hier ursprünglich) vor 0020, würde er brechen, sobald pg_dump die drei neuen
Spalten mit ausgibt.

Sicher für bestehende DBs: Alembic führt bereits angewandte Revisionen nie
erneut aus. DBs, die über dieses (damals ladende) 0009 hochgezogen sind,
behalten ihre Daten; 0021 überspringt sie per Leerheits-Check. Frische
Installationen laufen hier durch und laden erst in 0021.

Revision ID: 0009_seed_baseline_data_at_end
Revises: 0008_testset_leaderboard_flag
Create Date: 2026-06-19
"""
from typing import Sequence, Union

revision: str = '0009_seed_baseline_data_at_end'
down_revision: Union[str, Sequence[str], None] = '0008_testset_leaderboard_flag'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op: Der Grundausstattungs-Load liegt jetzt in 0021 (Kettenende)."""
    pass


def downgrade() -> None:
    # Bewusst no-op (war schon immer no-op: Seed-Zeilen sind nachträglich nicht
    # von echten Nutzerdaten unterscheidbar).
    pass
