"""backtest_results: Sortier-Indizes inklusive Tiebreaker, beide Richtungen

Die Results-Liste sortiert nicht nur nach der geklickten Spalte, sondern hängt
zwei Tiebreaker an (api_backtest.get_results_datatable):

    ORDER BY <metrik> <dir> NULLS LAST, max_drawdown_pct DESC NULLS LAST, id DESC

Die Tiebreaker sind gewollt (ohne sie springen wertgleiche Zeilen beim
Auto-Reload und die Bestwert-Auswahl kürt mal das eine, mal das andere Result).
Die Indizes aus 0010 decken aber nur die erste Spalte ab und nur DESC:

- Der id-Tiebreaker zwingt PostgreSQL, innerhalb gleicher Metrik-Werte
  nachzusortieren. Über eine Million Results stammen aus Kombinationen ohne
  einen einzigen Trade und tragen deshalb überall den Wert 0 bzw. NULL. Bei
  ``max_drawdown_pct DESC`` (Default der Liste) steht diese Millionen-Gruppe
  ganz oben - alle echten Drawdowns sind negativ. Für 25 angezeigte Zeilen muss
  die komplette Gruppe geladen und sortiert werden (gemessen ~4 s, bei
  win_rate_pct DESC ~9,5 s).
- 0010 ging davon aus, die Liste sortiere "immer absteigend". Inzwischen kann
  jede Spalte auch aufsteigend sortiert werden. Ein DESC-NULLS-LAST-Index
  bedient ASC NULLS LAST nicht (beim Rückwärtslesen kippt die NULL-Position
  mit), also sortiert PostgreSQL dort die ganze Tabelle durch (~7 s je Spalte).

Diese Migration ersetzt die acht Single-Column-Indizes aus 0010 durch je einen
Index pro Richtung, der die vollständige Sortierkette abbildet. Die
``(run_id, metrik)``-Composites aus 0010 bleiben unangetastet.

Bei max_drawdown_pct ist die Sortierspalte zugleich der erste Tiebreaker - der
Index führt sie deshalb nur einmal.

Alle CREATE/DROP laufen CONCURRENTLY (kein Schreib-Lock) in einem
autocommit_block, damit laufende Runs während der Migration weiter inserten
können. IF NOT EXISTS / IF EXISTS macht die Migration idempotent.

Revision ID: 0015_result_sort_tiebreaker_indexes
Revises: 0014_result_best_criteria
Create Date: 2026-07-12
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0015_result_sort_indexes'
down_revision: Union[str, Sequence[str], None] = '0014_result_best_criteria'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Metrik-Spalte -> (Basis-Indexname, abgeloester Single-Column-Index aus 0010)
#
# Der Basisname darf NICHT so heissen, dass Basis+'_desc' auf den Namen des
# abgeloesten Index faellt (0010 nannte zwei davon bereits '..._desc'): das
# CREATE ... IF NOT EXISTS wuerde den Altbestand als "schon da" ansehen und das
# nachfolgende DROP ihn ersatzlos entfernen. Daher 'idx_res_return' / 'idx_res_pf'.
_METRIC_INDEXES = [
    ('sharpe_ratio', 'idx_res_sharpe', 'idx_res_sharpe'),
    ('sortino_ratio', 'idx_res_sortino', 'idx_res_sortino'),
    ('max_drawdown_pct', 'idx_res_max_dd', 'idx_res_max_dd'),
    ('total_trades', 'idx_res_trades', 'idx_res_trades'),
    ('win_rate_pct', 'idx_res_win_rate', 'idx_res_win_rate'),
    ('profit_factor', 'idx_res_pf', 'idx_res_profit_factor_desc'),
    ('total_return_pct', 'idx_res_return', 'idx_res_total_return_desc'),
    ('end_value', 'idx_res_end_value', 'idx_res_end_value'),
]

# Tiebreaker-Kette der Liste (siehe get_results_datatable).
_TIEBREAKER = 'max_drawdown_pct DESC NULLS LAST, id DESC'


def _index_columns(col: str, direction: str) -> str:
    """Spaltenliste des Sortier-Index für eine Metrik und eine Richtung.

    Bei max_drawdown_pct faellt der erste Tiebreaker mit der Sortierspalte
    zusammen; die Spalte wird dann nicht doppelt in den Index gelegt.
    """
    if col == 'max_drawdown_pct':
        return f'{col} {direction} NULLS LAST, id DESC'
    return f'{col} {direction} NULLS LAST, {_TIEBREAKER}'


def upgrade() -> None:
    """Legt je Metrik-Spalte einen DESC- und einen ASC-Sortier-Index an und
    entfernt die abgeloesten Single-Column-Indizes aus 0010."""
    with op.get_context().autocommit_block():
        for col, base, obsolete in _METRIC_INDEXES:
            for direction, suffix in (('DESC', 'desc'), ('ASC', 'asc')):
                op.execute(
                    f'CREATE INDEX CONCURRENTLY IF NOT EXISTS {base}_{suffix} '
                    f'ON backtest_results ({_index_columns(col, direction)})'
                )
            op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS {obsolete}')


def downgrade() -> None:
    """Stellt die Single-Column-Indizes aus 0010 wieder her und entfernt die
    Sortier-Indizes dieser Migration."""
    with op.get_context().autocommit_block():
        for col, base, obsolete in _METRIC_INDEXES:
            op.execute(
                f'CREATE INDEX CONCURRENTLY IF NOT EXISTS {obsolete} '
                f'ON backtest_results ({col} DESC NULLS LAST)'
            )
            for suffix in ('desc', 'asc'):
                op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS {base}_{suffix}')
