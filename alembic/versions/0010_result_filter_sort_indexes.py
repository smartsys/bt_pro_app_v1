"""backtest_results: Filter-/Sortier-Indizes für die Results-Tabelle

Die Results-Tabelle im Frontend (server-side DataTables) sortiert immer
absteigend (DESC NULLS LAST, beste Werte zuerst) und filtert nach run_id sowie
Min/Max auf den Metrik-Spalten. Ohne passende Indizes muss PostgreSQL bei jeder
Sortierung die kompletten (breiten, ~1,7 KB) Result-Zeilen aus dem Heap lesen
und top-N sortieren -> bei 65k Zeilen pro Run rund 2,5 s, bei Filter+Sort-Kombis
(z.B. win_rate>=90 + Sort Sharpe) über eine Minute.

Diese Migration legt pro Metrik-Spalte zwei Indizes an:

- Single-Column (`col DESC NULLS LAST`) für die Varianten OHNE run_id-Filter
  (volle Tabelle nach einer Metrik sortiert).
- Composite (`run_id, col DESC NULLS LAST`) für run_id-gefilterte Sortierung,
  für run_id + Min/Max-Filter (selektive Filterspalte wird im Index aufgelöst,
  der kleine Rest in-memory sortiert) und für Symbol/Timeframe-Filter, die
  über mehrere Runs gehen (Merge der Per-run_id-Index-Scans).

Wichtig: Die bestehenden Plain-ASC-Indizes idx_res_profit_factor und
idx_res_total_return (aus 0001_baseline) werden von der App NICHT genutzt -
ein Plain-ASC-Index bedient kein DESC-NULLS-LAST-Top-N. Sie werden durch die
DESC-NULLS-LAST-Varianten ersetzt und entfernt.

Alle CREATE/DROP laufen CONCURRENTLY (kein Schreib-Lock) in einem
autocommit_block, damit laufende Runs während der Migration weiter inserten
können. IF NOT EXISTS / IF EXISTS macht die Migration idempotent.

Revision ID: 0010_result_filter_sort_indexes
Revises: 0009_seed_baseline_data_at_end
Create Date: 2026-06-19
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0010_result_filter_sort_indexes'
down_revision: Union[str, Sequence[str], None] = '0009_seed_baseline_data_at_end'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Metrik-Spalte -> (Single-Column-Indexname, Composite-Indexname)
_METRIC_INDEXES = [
    ('sharpe_ratio', 'idx_res_sharpe', 'idx_res_run_sharpe'),
    ('sortino_ratio', 'idx_res_sortino', 'idx_res_run_sortino'),
    ('max_drawdown_pct', 'idx_res_max_dd', 'idx_res_run_max_dd'),
    ('total_trades', 'idx_res_trades', 'idx_res_run_trades'),
    ('win_rate_pct', 'idx_res_win_rate', 'idx_res_run_win_rate'),
    ('profit_factor', 'idx_res_profit_factor_desc', 'idx_res_run_pf'),
    ('total_return_pct', 'idx_res_total_return_desc', 'idx_res_run_return'),
    ('end_value', 'idx_res_end_value', 'idx_res_run_end_value'),
]

# Plain-ASC-Indizes aus 0001_baseline, die von den DESC-NULLS-LAST-Varianten
# abgelöst werden.
_OBSOLETE_PLAIN_INDEXES = ['idx_res_profit_factor', 'idx_res_total_return']


def upgrade() -> None:
    """Legt Single-Column- und Composite-Indizes CONCURRENTLY an, entfernt die
    nicht mehr genutzten Plain-ASC-Indizes."""
    with op.get_context().autocommit_block():
        for col, single, composite in _METRIC_INDEXES:
            op.execute(
                f'CREATE INDEX CONCURRENTLY IF NOT EXISTS {single} '
                f'ON backtest_results ({col} DESC NULLS LAST)'
            )
            op.execute(
                f'CREATE INDEX CONCURRENTLY IF NOT EXISTS {composite} '
                f'ON backtest_results (run_id, {col} DESC NULLS LAST)'
            )
        for old in _OBSOLETE_PLAIN_INDEXES:
            op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS {old}')


def downgrade() -> None:
    """Entfernt die neuen Indizes und stellt die Plain-ASC-Indizes wieder her."""
    with op.get_context().autocommit_block():
        op.execute(
            'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_res_profit_factor '
            'ON backtest_results (profit_factor)'
        )
        op.execute(
            'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_res_total_return '
            'ON backtest_results (total_return_pct)'
        )
        for col, single, composite in _METRIC_INDEXES:
            op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS {composite}')
            op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS {single}')
