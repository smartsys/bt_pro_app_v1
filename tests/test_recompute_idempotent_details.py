"""Test für die Idempotenz der Recompute-Detail-Speicherung.

Sichert den Faktor-3-Bugfix ab: `recompute_single_result` muss vorhandene
Detail-Zeilen eines Results löschen, bevor es neue einfügt. Ohne diesen
DELETE-Schritt hängt jeder erneute Recompute (mehrere Trigger-Pfade:
chart-data, trades/orders/positions, full-metrics, Worker-Job) eine weitere
volle Kopie an — die Einzel-Detailzeilen vervielfachen sich, während das
Aggregat (z.B. total_trades) korrekt bleibt.

Getestet wird der extrahierte Helper `_clear_result_details`, der den
Lösch-Vertrag kapselt. Lauf nur mit dem Projekt-venv (hat PostgreSQL-Test-DB):
    ./.venv/Scripts/python.exe -m pytest tests/test_recompute_idempotent_details.py
"""

import datetime

from services.api.recompute import _clear_result_details, _RECOMPUTE_DETAIL_TABLES
from user_data.utils.database.models import (
    BacktestTrade, BacktestOrder, BacktestPosition, BacktestEquity, BacktestIndicator,
)

# Result-IDs für den Test: das Ziel-Result und ein Nachbar, der unangetastet bleiben muss.
_TARGET_RESULT_ID = 999001
_OTHER_RESULT_ID = 999002

_TS = datetime.datetime(2024, 1, 1, 0, 0, 0)


def _seed_detail_rows(session, result_id: int) -> None:
    """Legt je eine Zeile in allen fünf Detail-Tabellen für ein Result an."""
    session.add(BacktestEquity(result_id=result_id, timestamp=_TS, value=1000.0))
    session.add(BacktestTrade(
        result_id=result_id, exit_trade_id=0, direction='Long', status='Closed',
        size=1.0, entry_index=_TS, avg_entry_price=10.0,
    ))
    session.add(BacktestOrder(
        result_id=result_id, order_id=0, fill_index=_TS, size=1.0, price=10.0, side='Buy',
    ))
    session.add(BacktestPosition(
        result_id=result_id, position_id=0, direction='Long', status='Closed',
        size=1.0, entry_index=_TS, avg_entry_price=10.0,
    ))
    session.add(BacktestIndicator(
        result_id=result_id, indicator_name='x', indicator_output='out',
        timestamp=_TS, value=1.0,
    ))
    session.commit()


def _count_detail_rows(session, result_id: int) -> dict:
    """Zählt die Detail-Zeilen pro Tabelle für ein Result."""
    return {
        'trades': session.query(BacktestTrade).filter(BacktestTrade.result_id == result_id).count(),
        'orders': session.query(BacktestOrder).filter(BacktestOrder.result_id == result_id).count(),
        'positions': session.query(BacktestPosition).filter(BacktestPosition.result_id == result_id).count(),
        'equity': session.query(BacktestEquity).filter(BacktestEquity.result_id == result_id).count(),
        'indicators': session.query(BacktestIndicator).filter(BacktestIndicator.result_id == result_id).count(),
    }


def test_clear_result_details_removes_only_target(db_engine, session) -> None:
    """_clear_result_details löscht alle Detail-Zeilen des Ziel-Results, fremde bleiben."""
    _seed_detail_rows(session, _TARGET_RESULT_ID)
    _seed_detail_rows(session, _OTHER_RESULT_ID)

    # Vorbedingung: beide Results haben je 1 Zeile pro Tabelle
    assert all(v == 1 for v in _count_detail_rows(session, _TARGET_RESULT_ID).values())
    assert all(v == 1 for v in _count_detail_rows(session, _OTHER_RESULT_ID).values())

    with db_engine.begin() as conn:
        _clear_result_details(conn, _TARGET_RESULT_ID)

    session.expire_all()
    # Ziel-Result: alle Detail-Zeilen weg
    assert all(v == 0 for v in _count_detail_rows(session, _TARGET_RESULT_ID).values())
    # Nachbar-Result: unangetastet
    assert all(v == 1 for v in _count_detail_rows(session, _OTHER_RESULT_ID).values())


def test_clear_then_reinsert_is_idempotent(db_engine, session) -> None:
    """Löschen + erneutes Einfügen ergibt keine Vervielfachung (Faktor-3-Bug)."""
    # Erstes "Recompute": Zeilen anlegen
    _seed_detail_rows(session, _TARGET_RESULT_ID)
    assert _count_detail_rows(session, _TARGET_RESULT_ID)['trades'] == 1

    # Zweites "Recompute": erst löschen, dann neu einfügen — kein Anhängen
    with db_engine.begin() as conn:
        _clear_result_details(conn, _TARGET_RESULT_ID)
    _seed_detail_rows(session, _TARGET_RESULT_ID)

    session.expire_all()
    counts = _count_detail_rows(session, _TARGET_RESULT_ID)
    assert all(v == 1 for v in counts.values()), f"Detail-Zeilen vervielfacht: {counts}"


def test_detail_tables_constant_is_complete() -> None:
    """Die Lösch-Konstante deckt genau die fünf Recompute-Detail-Tabellen ab."""
    assert set(_RECOMPUTE_DETAIL_TABLES) == {
        'backtest_result_indicators',
        'backtest_result_equity',
        'backtest_result_trades',
        'backtest_result_orders',
        'backtest_result_positions',
    }
