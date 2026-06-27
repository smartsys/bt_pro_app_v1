"""
Konverter-Funktionen zwischen BacktestConfig-Tabellenzeile und JSON-Format.

Ticket 15 — Block 6: Konverter-Paar für BacktestConfig-Vorlage <-> JSON.
Das JSON-Format entspricht exakt dem, was in backtest_runs.backtest_config_json liegt.
"""

from typing import Any, Optional


def backtest_config_row_to_json(row: Any) -> dict:
    """Serialisiert eine BacktestConfig-ORM-Zeile in das backtest_config_json-Format.

    Output-Format identisch zu dem, was in backtest_runs.backtest_config_json gespeichert wird.
    Fehlende Stop-Felder werden als None beibehalten.

    Args:
        row: Eine BacktestConfig-ORM-Instanz (user_data.utils.database.models.BacktestConfig).

    Returns:
        Dict im backtest_config_json-Format.
    """
    return {
        'exchange': row.exchange,
        'timeframe': row.timeframe,
        'symbols': [row.symbol],
        'start': row.start,
        'end': row.end,
        'ohlc_start': row.ohlc_start,
        'ohlc_end': row.ohlc_end,
        'portfolio': {
            'size': row.size,
            'size_type': row.size_type,
            'init_cash': row.init_cash,
            'fees': row.fees,
            # GEÄNDERT: Schritt 3d — Stop-Formate aus BacktestConfig entfernt;
            # sie leben jetzt in indicators_json['_stops'] (IndicatorConfig).
        },
    }


def json_to_backtest_config_row_kwargs(data: dict) -> dict:
    """Konvertiert ein backtest_config_json-Dict in BacktestConfig-Kwargs.

    Kehrt backtest_config_row_to_json um. Kann direkt als **kwargs an den
    BacktestConfig-Konstruktor übergeben werden.

    Unbekannte Felder außerhalb des Portfolio-Blocks werden ignoriert.
    Fehlende Portfolio-Felder erhalten None.

    Args:
        data: Dict im backtest_config_json-Format.

    Returns:
        Dict mit Spalten-Kwargs für BacktestConfig (ohne id, name, description,
        is_default, created_at, updated_at — die werden vom Aufrufer gesetzt).
    """
    portfolio: dict = data.get('portfolio') or {}
    symbols: list = data.get('symbols') or []
    symbol = symbols[0] if symbols else ''

    return {
        'exchange': data.get('exchange', 'binance'),
        'timeframe': data.get('timeframe', '4h'),
        'symbol': symbol,
        'start': data.get('start', ''),
        'end': data.get('end', ''),
        'ohlc_start': data.get('ohlc_start', ''),
        'ohlc_end': data.get('ohlc_end', ''),
        'size': portfolio.get('size', 100),
        'size_type': portfolio.get('size_type', 'value'),
        'init_cash': portfolio.get('init_cash', 100),
        'fees': portfolio.get('fees', 0.001),
        # GEÄNDERT: Schritt 3d — Stop-Formate aus BacktestConfig entfernt;
        # sie leben jetzt in indicators_json['_stops'] (IndicatorConfig).
    }
