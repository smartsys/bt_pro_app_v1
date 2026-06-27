"""
Recompute — Einzelnen Backtest nachberechnen

Wird aufgerufen wenn ein Chart für ein Result aus einem Multi-Kombination-Run
geöffnet wird und keine Equity-Daten vorhanden sind.
Führt die Strategie mit den exakten Parametern nochmal aus und speichert
alle Detail-Daten (Equity, Trades, Orders, Positions, Indikatoren, volle Metriken).
"""

import os
import inspect
import logging

from user_data.utils.database.db import get_session, get_engine
from user_data.utils.database.models import (
    BacktestRun, BacktestResult, BacktestTrade, BacktestOrder,
    BacktestPosition, BacktestEquity, BacktestIndicator
)
# GEÄNDERT: Spec-Runner-Version für Reproduzierbarkeit (Ticket 01)
from user_data.strategies.generic.spec_runner import VERSION as _spec_runner_version
from user_data.utils.database.repository import (
    _extract_chart_metrics, _extract_full_metrics, _safe_float, _safe_datetime, _safe_int,
    _build_resolved_config,
)
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

logger = logging.getLogger(__name__)

# GEÄNDERT: Detail-Tabellen, die der Recompute schreibt. Werden vor dem Insert
# idempotent geleert, damit ein erneuter Recompute (z.B. über mehrere Trigger-Pfade)
# die Detail-Zeilen nicht vervielfacht (Faktor-3-Bug).
_RECOMPUTE_DETAIL_TABLES = (
    'backtest_result_indicators',
    'backtest_result_equity',
    'backtest_result_trades',
    'backtest_result_orders',
    'backtest_result_positions',
)


def _clear_result_details(conn, result_id: int) -> None:
    """Löscht alle Detail-Zeilen eines Results vor dem Neu-Einfügen (Idempotenz).

    Ohne dieses DELETE hängt jeder erneute Recompute (mehrere Trigger-Pfade:
    chart-data, trades/orders/positions, full-metrics, Worker-Job) eine weitere
    volle Kopie an — die Einzel-Detailzeilen vervielfachen sich (Faktor 3x bei
    drei Triggern), während das Aggregat korrekt bleibt.

    Args:
        conn: Aktive SQLAlchemy-Connection (innerhalb einer Transaktion).
        result_id: ID des BacktestResult, dessen Detail-Zeilen geleert werden.
    """
    for table in _RECOMPUTE_DETAIL_TABLES:
        conn.execute(
            text(f"DELETE FROM {table} WHERE result_id = :rid"),
            {"rid": result_id},
        )


def load_strategy_function(import_path: str):
    """Lädt eine Strategie-Funktion dynamisch anhand des Import-Pfads.

    Args:
        import_path: voll qualifizierter Pfad 'paket.modul.funktion' zur Strategie-Funktion

    Returns:
        Die Strategie-Funktion
    """
    module_path, func_name = import_path.rsplit('.', 1)
    module = __import__(module_path, fromlist=[func_name])
    return getattr(module, func_name)



def recompute_single_result(result_id: int, sync: bool = False) -> bool:
    """Berechnet ein einzelnes Result neu und speichert alle Detail-Daten.

    Args:
        result_id: ID des BacktestResult
        sync: Wenn True, werden Positions synchron statt im Background-Thread gespeichert
              (für Worker-Kontext, wo der Thread den Job überleben könnte)

    Returns:
        True wenn erfolgreich, False bei Fehler
    """
    session = get_session()
    try:
        result = session.query(BacktestResult).filter(BacktestResult.id == result_id).first()
        if not result:
            logger.error(f"[RECOMPUTE] Result {result_id} nicht gefunden")
            return False

        run = session.query(BacktestRun).filter(BacktestRun.id == result.run_id).first()
        if not run:
            logger.error(f"[RECOMPUTE] Run {result.run_id} nicht gefunden")
            return False

        # GEÄNDERT: Ticket 15 — _json-Suffix
        actual_params = result.actual_params_json
        strategy_name = run.strategy_name
        backtest_config = dict(run.backtest_config_json)
        indicators_config = dict(run.indicators_config_json)
        symbol = run.symbol
        exchange = run.exchange
        timeframe = run.timeframe
        # GEÄNDERT: rules_json aus iteration.spec_json laden (analog worker_tasks).
        # Seit Ticket 12 ist rules_json für den Spec-Runner Pflicht — ohne diese
        # Übergabe scheiterte der Recompute/Full-Metrics eines Multi-Combo-Results
        # mit 'rules_json fehlt' (Chart blieb ohne Equity/Indikatoren).
        if run.iteration_id is not None and run.iteration is not None:
            rules_json = (run.iteration.spec_json or {}).get('rules')
        else:
            rules_json = None
    finally:
        session.close()

    # Strategie-Funktion laden — import_path aus backtest_config oder Fallback
    import_path = backtest_config.get('import_path')
    if not import_path:
        logger.error(f"[RECOMPUTE] Kein import_path in backtest_config für Run {result.run_id}")
        return False

    strategy_fn = load_strategy_function(import_path)

    # OHLCV-Daten laden
    import time as _time
    _t0 = _time.time()
    from user_data.utils.ohlc.loader import load_ohlc_data
    ohlc_data = load_ohlc_data({
        'symbols': [symbol],
        'exchange': exchange,
        'timeframe': timeframe,
        'ohlc_start': backtest_config.get('ohlc_start'),
        'ohlc_end': backtest_config.get('ohlc_end'),
    })
    print(f"  [RECOMPUTE] OHLCV geladen ({_time.time() - _t0:.1f}s)")

    # GEÄNDERT: Ticket 18 — _build_resolved_config statt hartcodierter Mapping-Funktion
    single_indicators = _build_resolved_config(indicators_config, actual_params)
    # GEÄNDERT: Schritt 3b — '_stops' stammt jetzt aus dem Run-Snapshot (3a-Backfill in
    # indicators_config_json), nicht mehr aus dem portfolio-Block. _build_resolved_config
    # strippt alle '_'-Meta-Keys, daher hier explizit aus indicators_config re-injizieren.
    single_indicators['_stops'] = indicators_config.get('_stops', {})

    # Strategie ausführen (chunked deaktivieren — nur 1 Kombination, kein Chunking nötig)
    _t_total = _time.time()
    _t0 = _time.time()
    print(f"[RECOMPUTE] Starte Backtest für Result {result_id} ({strategy_name}, {symbol})...")
    backtest_config = dict(backtest_config)
    backtest_config['_disable_chunked'] = True
    # GEÄNDERT: rules_json nur übergeben, wenn die Strategie-Funktion es akzeptiert
    # (Spec-Runner: Pflicht; hartgecodete Strategien haben keinen rules_json-Parameter).
    if 'rules_json' in inspect.signature(strategy_fn).parameters:
        strategy_result = strategy_fn(ohlc_data, single_indicators, backtest_config, rules_json=rules_json)
    else:
        strategy_result = strategy_fn(ohlc_data, single_indicators, backtest_config)

    print(f"  [RECOMPUTE] Strategie ausgeführt ({_time.time() - _t0:.1f}s)")

    portfolios = strategy_result['portfolios']
    columns = portfolios.wrapper.columns
    pf = portfolios[columns[0]]

    # Volle Metriken extrahieren und Result aktualisieren
    _t0 = _time.time()
    # GEÄNDERT: Nur Chart-Metriken (schnell), Full-Metriken kommen per Hintergrund-Job
    all_metrics = _extract_chart_metrics(pf)
    print(f"  [RECOMPUTE] Chart-Metriken extrahiert ({_time.time() - _t0:.1f}s)")

    # Phase 1: Metriken + Equity + Trades + Orders (sofort, blockiert Response)
    _t_phase1 = _time.time()
    engine = get_engine()
    with engine.begin() as conn:
        # GEÄNDERT: Idempotenz — vorhandene Detail-Zeilen dieses Results löschen, bevor
        # neu eingefügt wird (verhindert den Faktor-3-Bug bei mehrfachem Recompute).
        _clear_result_details(conn, result_id)

        # Metriken in BacktestResult aktualisieren
        # GEÄNDERT: Spec-Runner-Version mitschreiben (Ticket 01)
        _t0 = _time.time()
        conn.execute(
            BacktestResult.__table__.update()
            .where(BacktestResult.id == result_id)
            .values(**all_metrics, spec_runner_version=_spec_runner_version)
        )

        print(f"  [RECOMPUTE] Metriken UPDATE ({_time.time() - _t0:.1f}s)")

        # Equity speichern
        _t0 = _time.time()
        equity_series = pf.value
        equity_batch = []
        for ts, val in equity_series.items():
            safe_val = _safe_float(val)
            if safe_val is not None:
                equity_batch.append({
                    'result_id': result_id,
                    'timestamp': _safe_datetime(ts),
                    'value': safe_val,
                })
        if equity_batch:
            batch_size = 2000
            for i in range(0, len(equity_batch), batch_size):
                conn.execute(insert(BacktestEquity), equity_batch[i:i + batch_size])
            print(f"  [RECOMPUTE] {len(equity_batch)} Equity-Werte gespeichert ({_time.time() - _t0:.1f}s)")

        # Trades speichern
        _t0 = _time.time()
        trades_records = pf.trades.records_readable
        if len(trades_records) > 0:
            trades_batch = []
            for _, row in trades_records.iterrows():
                trades_batch.append({
                    'result_id': result_id,
                    'exit_trade_id': int(row['Exit Trade Id']),
                    'position_id': _safe_int(row.get('Position Id')),
                    'direction': str(row.get('Direction', 'Long')),
                    'status': str(row.get('Status', 'Closed')),
                    'size': _safe_float(row['Size']),
                    'entry_order_id': _safe_int(row.get('Entry Order Id')),
                    'entry_index': _safe_datetime(row['Entry Index']),
                    'avg_entry_price': _safe_float(row['Avg Entry Price']),
                    'entry_fees': _safe_float(row.get('Entry Fees')),
                    'exit_order_id': _safe_int(row.get('Exit Order Id')),
                    'exit_index': _safe_datetime(row.get('Exit Index')),
                    'avg_exit_price': _safe_float(row.get('Avg Exit Price')),
                    'exit_fees': _safe_float(row.get('Exit Fees')),
                    'pnl': _safe_float(row.get('PnL')),
                    'return_pct': _safe_float(row.get('Return', 0) * 100),
                })
            conn.execute(insert(BacktestTrade), trades_batch)
            print(f"  [RECOMPUTE] {len(trades_batch)} Trades gespeichert ({_time.time() - _t0:.1f}s)")

        # Orders speichern
        _t0 = _time.time()
        orders_records = pf.orders.records_readable
        if len(orders_records) > 0:
            orders_batch = []
            for _, row in orders_records.iterrows():
                stop_type = str(row.get('Stop Type', ''))
                orders_batch.append({
                    'result_id': result_id,
                    'order_id': int(row['Order Id']),
                    'signal_index': _safe_datetime(row.get('Signal Index')),
                    'creation_index': _safe_datetime(row.get('Creation Index')),
                    'fill_index': _safe_datetime(row.get('Fill Index')),
                    'size': _safe_float(row['Size']),
                    'price': _safe_float(row['Price']),
                    'fees': _safe_float(row.get('Fees')),
                    'side': str(row['Side']),
                    'type': str(row.get('Type', '')) or None,
                    'stop_type': stop_type if stop_type and stop_type != 'None' else None,
                })
            conn.execute(insert(BacktestOrder), orders_batch)
            print(f"  [RECOMPUTE] {len(orders_batch)} Orders gespeichert ({_time.time() - _t0:.1f}s)")

        # Indikatoren speichern
        _t0 = _time.time()
        indicators_results = strategy_result.get('indicators_results', {})
        indicators_batch = []
        for ind_name, ind_data in indicators_results.items():
            data_obj = ind_data.get('data')
            if data_obj is None:
                continue
            # GEÄNDERT: M7 — kein stilles Raten von ['result'] mehr (siehe save_strategy_results).
            # Unbekanntes Datenformat -> harter Abbruch statt unvollständiger Speicherung.
            output_names = getattr(data_obj, 'output_names', None)
            if not output_names:
                raise ValueError(
                    f"Indikator '{ind_name}': Datenobjekt vom Typ '{type(data_obj).__name__}' "
                    f"hat keine 'output_names' — die Output-Kanäle sind nicht bestimmbar. "
                    f"Recompute wird abgebrochen, um keine unvollständigen Indikator-Daten zu speichern."
                )
            for output_name in output_names:
                series = getattr(data_obj, output_name, None)
                if series is None:
                    continue
                if hasattr(series, 'columns'):
                    series = series.iloc[:, 0]
                for ts, val in series.items():
                    safe_val = _safe_float(val)
                    if safe_val is not None:
                        indicators_batch.append({
                            'result_id': result_id,
                            'indicator_name': ind_name,
                            'indicator_output': output_name,
                            'timestamp': _safe_datetime(ts),
                            'value': safe_val,
                        })
        if indicators_batch:
            batch_size = 2000
            for i in range(0, len(indicators_batch), batch_size):
                conn.execute(insert(BacktestIndicator), indicators_batch[i:i + batch_size])
            print(f"  [RECOMPUTE] {len(indicators_batch)} Indikator-Werte gespeichert ({_time.time() - _t0:.1f}s)")

    print(f"[RECOMPUTE] Phase 1 fertig ({_time.time() - _t_phase1:.1f}s)")

    # Phase 2: Positions speichern
    def _save_positions():
        with engine.begin() as conn:
            positions_records = pf.positions.records_readable
            if len(positions_records) > 0:
                positions_batch = []
                for _, row in positions_records.iterrows():
                    positions_batch.append({
                        'result_id': result_id,
                        'position_id': int(row['Position Id']),
                        'direction': str(row.get('Direction', 'Long')),
                        'status': str(row.get('Status', 'Closed')),
                        'size': _safe_float(row['Size']),
                        'entry_order_id': _safe_int(row.get('Entry Order Id')),
                        'entry_index': _safe_datetime(row['Entry Index']),
                        'avg_entry_price': _safe_float(row['Avg Entry Price']),
                        'entry_fees': _safe_float(row.get('Entry Fees')),
                        'exit_order_id': _safe_int(row.get('Exit Order Id')),
                        'exit_index': _safe_datetime(row.get('Exit Index')),
                        'avg_exit_price': _safe_float(row.get('Avg Exit Price')),
                        'exit_fees': _safe_float(row.get('Exit Fees')),
                        'pnl': _safe_float(row.get('PnL')),
                        'return_pct': _safe_float(row.get('Return', 0) * 100),
                    })
                conn.execute(insert(BacktestPosition), positions_batch)
                print(f"  [RECOMPUTE] {len(positions_batch)} Positions gespeichert")

    if sync:
        # Worker-Kontext: synchron ausführen
        _save_positions()
        print(f"[RECOMPUTE] Result {result_id} vollständig ({_time.time() - _t_phase1:.1f}s)")
    else:
        # Chart-Kontext: im Hintergrund ausführen
        import threading
        def _bg():
            try:
                _save_positions()
                print(f"[RECOMPUTE BG] Result {result_id} Phase 2 fertig")
            except Exception as e:
                logger.error(f"[RECOMPUTE BG] Fehler bei Result {result_id}: {e}")
        threading.Thread(target=_bg, daemon=True).start()

    return True


def compute_full_metrics(result_id: int) -> bool:
    """Berechnet die langsamen Full-Metriken für ein einzelnes Result.

    Stufe 3: Führt den Backtest nochmal aus und berechnet nur die Metriken
    die zu langsam für partial sind (tail_ratio, VaR, alpha, beta etc.).
    Wird als Hintergrund-Job ausgeführt.

    Args:
        result_id: ID des BacktestResult

    Returns:
        True wenn erfolgreich, False bei Fehler
    """
    import time as _time

    session = get_session()
    try:
        result = session.query(BacktestResult).filter(BacktestResult.id == result_id).first()
        if not result:
            logger.error(f"[FULL-METRICS] Result {result_id} nicht gefunden")
            return False

        run = session.query(BacktestRun).filter(BacktestRun.id == result.run_id).first()
        if not run:
            logger.error(f"[FULL-METRICS] Run {result.run_id} nicht gefunden")
            return False

        # GEÄNDERT: Ticket 15 — _json-Suffix
        actual_params = result.actual_params_json
        strategy_name = run.strategy_name
        backtest_config = dict(run.backtest_config_json)
        indicators_config = dict(run.indicators_config_json)
        symbol = run.symbol
        exchange = run.exchange
        timeframe = run.timeframe
        # GEÄNDERT: rules_json aus iteration.spec_json laden (analog worker_tasks).
        # Seit Ticket 12 ist rules_json für den Spec-Runner Pflicht — ohne diese
        # Übergabe scheiterte der Recompute/Full-Metrics eines Multi-Combo-Results
        # mit 'rules_json fehlt' (Chart blieb ohne Equity/Indikatoren).
        if run.iteration_id is not None and run.iteration is not None:
            rules_json = (run.iteration.spec_json or {}).get('rules')
        else:
            rules_json = None
    finally:
        session.close()

    # Strategie-Funktion laden
    import_path = backtest_config.get('import_path')
    if not import_path:
        logger.error(f"[FULL-METRICS] Kein import_path in backtest_config für Run {result.run_id}")
        return False

    strategy_fn = load_strategy_function(import_path)

    # OHLCV-Daten laden
    _t_total = _time.time()
    from user_data.utils.ohlc.loader import load_ohlc_data
    ohlc_data = load_ohlc_data({
        'symbols': [symbol],
        'exchange': exchange,
        'timeframe': timeframe,
        'ohlc_start': backtest_config.get('ohlc_start'),
        'ohlc_end': backtest_config.get('ohlc_end'),
    })
    print(f"  [FULL-METRICS] OHLCV geladen ({_time.time() - _t_total:.1f}s)")

    # Strategie ausführen
    _t0 = _time.time()
    # GEÄNDERT: Ticket 18 — _build_resolved_config statt hartcodierter Mapping-Funktion
    single_indicators = _build_resolved_config(indicators_config, actual_params)
    # GEÄNDERT: Schritt 3b — '_stops' stammt jetzt aus dem Run-Snapshot (3a-Backfill in
    # indicators_config_json), nicht mehr aus dem portfolio-Block. _build_resolved_config
    # strippt alle '_'-Meta-Keys, daher hier explizit aus indicators_config re-injizieren.
    single_indicators['_stops'] = indicators_config.get('_stops', {})
    backtest_config['_disable_chunked'] = True
    # GEÄNDERT: rules_json nur übergeben, wenn die Strategie-Funktion es akzeptiert
    # (Spec-Runner: Pflicht; hartgecodete Strategien haben keinen rules_json-Parameter).
    if 'rules_json' in inspect.signature(strategy_fn).parameters:
        strategy_result = strategy_fn(ohlc_data, single_indicators, backtest_config, rules_json=rules_json)
    else:
        strategy_result = strategy_fn(ohlc_data, single_indicators, backtest_config)
    print(f"  [FULL-METRICS] Strategie ausgeführt ({_time.time() - _t0:.1f}s)")

    # Full-Metriken berechnen
    _t0 = _time.time()
    portfolios = strategy_result['portfolios']
    columns = portfolios.wrapper.columns
    pf = portfolios[columns[0]]
    full_metrics = _extract_full_metrics(pf)
    print(f"  [FULL-METRICS] Metriken berechnet ({_time.time() - _t0:.1f}s)")

    # Result updaten
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            BacktestResult.__table__.update()
            .where(BacktestResult.id == result_id)
            .values(**full_metrics)
        )

    print(f"[FULL-METRICS] Result {result_id} vollständig ({_time.time() - _t_total:.1f}s)")
    return True
