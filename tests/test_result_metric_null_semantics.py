"""Persistenz-Semantik der Metrik-Auswahl (Ticket 68, Anforderung 3).

`save_strategy_results` schreibt immer **alle** Kennzahl-Spalten. Felder, die eine
Auswahl nicht gerechnet hat, gehen ausdrücklich als NULL in die Datenbank — auch im
Upsert-Fall. Damit trägt ein Result nie einen Mix aus zwei Läufen mit verschiedener
Auswahl, und ein Re-Run mit schmalerer Auswahl lässt keine Altwerte stehen.

Gefahren wird über den gechunkten Pfad (`metrics_table`), weil er die fertigen
Kennzahl-Dicts direkt entgegennimmt — die Persistenz lässt sich so ohne Portfolio
prüfen.
"""

from datetime import datetime

import pandas as pd
import pytest
from sqlalchemy import text

from user_data.utils.metrics.metric_sets import (
    ALL_METRIC_FIELDS,
    METRIC_GROUPS,
    fields_for_groups,
    resolve_metric_groups,
    skipped_fields,
)

_ANN_FACTOR = 2190.0
_RUN_ID = 930001
_COLUMNS = pd.Index(['c0', 'c1'])

# Werte je Feldtyp — die Spaltentypen von BacktestResult sind Float, Integer,
# DateTime und String(50).
_INT_FIELDS = ('bar_count', 'total_orders', 'total_trades', 'open_trades',
               'long_trades', 'short_trades')
_DATETIME_FIELDS = ('start_index', 'end_index')
_TEXT_FIELDS = ('total_duration', 'max_drawdown_duration',
                'avg_winning_trade_duration', 'avg_losing_trade_duration')


def _metric_value(field: str, offset: int):
    """Liefert einen typgerechten, je Kombination verschiedenen Wert."""
    if field in _DATETIME_FIELDS:
        return datetime(2022, 1, 1 + offset, 12, 0, 0)
    if field in _TEXT_FIELDS:
        return f'{10 + offset} days'
    if field in _INT_FIELDS:
        return 100 + offset
    return 1.5 + offset


def _metrics_table(groups) -> list[dict]:
    """Baut die Kennzahl-Tabelle für zwei Kombinationen über die aktiven Gruppen."""
    fields = fields_for_groups(groups)
    return [
        {field: _metric_value(field, offset) for field in fields}
        for offset in range(len(_COLUMNS))
    ]


def _insert_run(session, run_id: int) -> None:
    """Legt einen minimalen backtest_runs-Datensatz an."""
    session.execute(text(
        "INSERT INTO backtest_runs (id, strategy_family, strategy_name, symbol, exchange, "
        "timeframe, start_date, end_date, backtest_config_json, indicators_config_json, "
        "n_combinations, status, created_at) "
        "VALUES (:id, 'test', 'v1', 'FETUSDT', 'binance', '4h', '2022-01-01', '2024-01-01', "
        "'{}', '{}', 2, 'queued', NOW())"
    ), {'id': run_id})


def _save(groups) -> None:
    """Speichert den Lauf mit der angegebenen Gruppenmenge (gechunkter Pfad)."""
    from user_data.utils.database.repository import save_strategy_results

    save_strategy_results(
        run_id=_RUN_ID,
        strategy_results={
            'metrics_table': _metrics_table(groups),
            'columns': _COLUMNS,
            'ann_factor': _ANN_FACTOR,
        },
    )


def _stored_rows(session) -> list:
    """Liest alle Kennzahl-Spalten der Results des Laufs, nach ID sortiert."""
    columns = ', '.join(ALL_METRIC_FIELDS)
    return session.execute(text(
        f'SELECT {columns} FROM backtest_results WHERE run_id = :run_id ORDER BY id'
    ), {'run_id': _RUN_ID}).fetchall()


@pytest.fixture()
def repo_against_test_db(session, monkeypatch):
    """Verdrahtet das Repository mit der Test-DB und legt den Lauf an."""
    import user_data.utils.database.repository as repo

    _insert_run(session, _RUN_ID)
    session.commit()
    monkeypatch.setattr(repo, 'get_engine', lambda: session.get_bind())
    yield session


def test_full_selection_fills_every_metric_column(repo_against_test_db):
    """Gegenprobe: die volle Auswahl lässt keine Kennzahl-Spalte leer."""
    session = repo_against_test_db
    _save(resolve_metric_groups('voll'))
    session.rollback()

    rows = _stored_rows(session)
    assert len(rows) == 2
    for row in rows:
        for field in ALL_METRIC_FIELDS:
            assert getattr(row, field) is not None, f'{field} ist leer'


def test_narrow_selection_writes_the_skipped_fields_as_null(repo_against_test_db):
    """Eine schmale Auswahl schreibt die abgewählten Felder als NULL, nicht als 0."""
    session = repo_against_test_db
    groups = resolve_metric_groups('kern')
    _save(groups)
    session.rollback()

    rows = _stored_rows(session)
    for row in rows:
        for field in skipped_fields(groups):
            assert getattr(row, field) is None, f'{field} sollte leer sein'
        for field in fields_for_groups(groups):
            assert getattr(row, field) is not None, f'{field} ist leer'


def test_rerun_with_narrower_selection_clears_the_old_values(repo_against_test_db):
    """Der Kern des Tickets: ein Re-Run mit schmalerer Auswahl hinterlässt keine Altwerte.

    Erst voll speichern, dann denselben Lauf mit `kern` erneut speichern (identische
    Parameter, also derselbe `params_hash` und damit der Upsert-Zweig). Danach müssen
    die `tail_risk`-Spalten leer sein — nicht die Werte des ersten Laufs.
    """
    session = repo_against_test_db
    _save(resolve_metric_groups('voll'))
    session.rollback()
    assert all(
        getattr(row, 'tail_ratio') is not None for row in _stored_rows(session)
    )
    session.rollback()

    core_groups = resolve_metric_groups('kern')
    _save(core_groups)
    session.rollback()

    rows = _stored_rows(session)
    # Kein zweiter Satz Results — der Upsert hat dieselben Zeilen getroffen.
    assert len(rows) == 2
    for row in rows:
        for field in METRIC_GROUPS['tail_risk']:
            assert getattr(row, field) is None, f'{field} trägt noch den Altwert'
        for field in fields_for_groups(core_groups):
            assert getattr(row, field) is not None, f'{field} ist leer'


def test_rerun_with_wider_selection_fills_the_missing_fields(repo_against_test_db):
    """Gegenrichtung: der volle Re-Run füllt die vorher leeren Spalten nach."""
    session = repo_against_test_db
    _save(resolve_metric_groups([]))
    session.rollback()
    assert all(getattr(row, 'alpha') is None for row in _stored_rows(session))
    session.rollback()

    _save(resolve_metric_groups('voll'))
    session.rollback()

    rows = _stored_rows(session)
    assert len(rows) == 2
    for row in rows:
        for field in ALL_METRIC_FIELDS:
            assert getattr(row, field) is not None, f'{field} ist leer'


def test_deflated_sharpe_postrun_runs_on_the_narrowest_selection(repo_against_test_db):
    """Der DSR-Nachlauf läuft auch bei der schmalsten Auswahl und füllt die Spalte.

    Die Pflichtgruppen sind genau so geschnitten, dass seine vier Eingänge
    (`sharpe_ratio`, `skew`, `kurtosis`, `bar_count`) immer vorliegen.
    """
    session = repo_against_test_db
    _save(resolve_metric_groups([]))
    session.rollback()

    values = session.execute(text(
        'SELECT deflated_sharpe_ratio FROM backtest_results '
        'WHERE run_id = :run_id ORDER BY id'
    ), {'run_id': _RUN_ID}).fetchall()
    assert len(values) == 2
    for row in values:
        assert row.deflated_sharpe_ratio is not None


def test_metric_field_without_group_is_rejected(repo_against_test_db):
    """Ein Kennzahl-Feld ohne Gruppe fällt auf, statt still unter den Tisch zu fallen."""
    from user_data.utils.database.repository import save_strategy_results

    table = _metrics_table(resolve_metric_groups('voll'))
    for row in table:
        row['erfundene_kennzahl'] = 1.0

    with pytest.raises(ValueError, match='ohne Gruppe'):
        save_strategy_results(
            run_id=_RUN_ID,
            strategy_results={
                'metrics_table': table,
                'columns': _COLUMNS,
                'ann_factor': _ANN_FACTOR,
            },
        )
