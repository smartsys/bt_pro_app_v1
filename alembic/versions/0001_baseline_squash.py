"""baseline squash

Squash aller bisherigen Migrationen (vormals 0001-0015) auf einen Initial-Stand,
der dem aktuellen Schema entspricht - so, wie es bei einer Neuinstallation entsteht.

Quelle: frische DB via `alembic upgrade head` der alten 0001-0015-Kette aufgebaut,
danach `pg_dump -s --schema=public`. Globale Objekte (Extensions timescaledb + vector)
und die TimescaleDB-Hypertables werden manuell ergänzt, da der schema-beschränkte
Dump sie weglässt. Quelle und Ziel wurden schema-identisch gegengeprüft.

Bestehende DBs werden via `alembic stamp 0001_baseline_squash` auf diese Revision
gesetzt - dabei wird KEIN DDL ausgeführt, nur die alembic_version-Tabelle aktualisiert.

Revision ID: 0001_baseline_squash
Revises:
Create Date: 2026-06-17
"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = '0001_baseline_squash'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SQL_DIR = Path(__file__).parent / '_sql'


def upgrade() -> None:
    sql = (_SQL_DIR / '0001_baseline.sql').read_text(encoding='utf-8')
    op.execute(sql)


def downgrade() -> None:
    # Reine Notfall-Reverse: alle Tabellen droppen. Bewusst keine feinere
    # Steuerung - eine Baseline geht entweder hoch oder nicht.
    op.execute("""
        DROP TABLE IF EXISTS
            vault_reindex_runs, vault_chunks,
            leaderboard_entries, testset_runs, testsets,
            chart_playground_setups,
            backtest_result_equity, backtest_result_indicators,
            backtest_result_orders, backtest_result_params,
            backtest_result_positions, backtest_result_trades,
            backtest_results, backtest_jobs, backtest_runs,
            indicator_configs, backtest_configs,
            strategy_iterations, strategy_concepts, strategy_configs,
            ohlc_download_jobs
        CASCADE
    """)
