"""backtest_results: aufsteigende Sortier-Indizes für den run_id-gefilterten Fall

Ergänzt 0015 um den Alltagsweg "vom Run in dessen Results": dort filtert die
Liste auf run_id und sortiert mit derselben Tiebreaker-Kette

    ORDER BY <metrik> <dir> NULLS LAST, max_drawdown_pct DESC NULLS LAST, id DESC

Die ``(run_id, metrik DESC NULLS LAST)``-Composites aus 0010 bedienen davon nur
die absteigende Richtung (gemessen 12-47 ms, in Ordnung). Aufsteigend fehlt das
Gegenstück - ein DESC-NULLS-LAST-Index bedient kein ASC NULLS LAST, weil beim
Rückwärtslesen die NULL-Position mitkippt. PostgreSQL sortiert deshalb die
kompletten Results des Runs durch (gemessen 1,0-4,3 s bei 371k Results je Run).

Diese Migration legt je Metrik-Spalte das aufsteigende Gegenstück an. Die
DESC-Composites aus 0010 bleiben unangetastet.

Bei max_drawdown_pct ist die Sortierspalte zugleich der erste Tiebreaker - der
Index führt sie deshalb nur einmal.

Alle CREATE/DROP laufen CONCURRENTLY (kein Schreib-Lock) in einem
autocommit_block, damit laufende Runs während der Migration weiter inserten
können. IF NOT EXISTS / IF EXISTS macht die Migration idempotent.

Revision ID: 0016_result_run_sort_asc
Revises: 0015_result_sort_indexes
Create Date: 2026-07-12
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0016_result_run_sort_asc'
down_revision: Union[str, Sequence[str], None] = '0015_result_sort_indexes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Metrik-Spalte -> Name des neuen ASC-Index. Die Namen tragen bewusst das
# Suffix '_asc' und kollidieren damit nicht mit den DESC-Composites aus 0010
# (idx_res_run_sharpe, ...) - sonst wuerde CREATE ... IF NOT EXISTS den
# Altbestand als "schon da" ansehen.
_METRIC_INDEXES = [
    ('sharpe_ratio', 'idx_res_run_sharpe_asc'),
    ('sortino_ratio', 'idx_res_run_sortino_asc'),
    ('max_drawdown_pct', 'idx_res_run_max_dd_asc'),
    ('total_trades', 'idx_res_run_trades_asc'),
    ('win_rate_pct', 'idx_res_run_win_rate_asc'),
    ('profit_factor', 'idx_res_run_pf_asc'),
    ('total_return_pct', 'idx_res_run_return_asc'),
    ('end_value', 'idx_res_run_end_value_asc'),
]

# Tiebreaker-Kette der Liste (siehe get_results_datatable).
_TIEBREAKER = 'max_drawdown_pct DESC NULLS LAST, id DESC'


def _index_columns(col: str) -> str:
    """Spaltenliste des aufsteigenden Sortier-Index einer Metrik (mit run_id).

    Bei max_drawdown_pct faellt der erste Tiebreaker mit der Sortierspalte
    zusammen; die Spalte wird dann nicht doppelt in den Index gelegt.
    """
    if col == 'max_drawdown_pct':
        return f'run_id, {col} ASC NULLS LAST, id DESC'
    return f'run_id, {col} ASC NULLS LAST, {_TIEBREAKER}'


def upgrade() -> None:
    """Legt je Metrik-Spalte den aufsteigenden (run_id, metrik, ...)-Index an."""
    with op.get_context().autocommit_block():
        for col, name in _METRIC_INDEXES:
            op.execute(
                f'CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} '
                f'ON backtest_results ({_index_columns(col)})'
            )


def downgrade() -> None:
    """Entfernt die aufsteigenden (run_id, metrik, ...)-Indizes."""
    with op.get_context().autocommit_block():
        for _col, name in _METRIC_INDEXES:
            op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS {name}')
