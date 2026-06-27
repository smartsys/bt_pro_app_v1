"""
Repository-Funktionen

Speichert Strategie-Ergebnisse in MySQL.
- backtest_runs: immer neuer INSERT
- backtest_results: Upsert per params_hash (MD5 aus run_id + actual_params)
- 1 Kombination: alle Metriken aus pf.stats()
- Mehr als 1: nur Total Return, Benchmark Return, Profit Factor
"""

import hashlib
import json
import logging
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Optional

from sqlalchemy.dialects.postgresql import insert

from user_data.utils.database.db import get_engine
from user_data.utils.database.models import (
    BacktestRun, BacktestResult, BacktestTrade, BacktestOrder,
    BacktestPosition, BacktestIndicator, BacktestEquity, BacktestParam
)

logger = logging.getLogger(__name__)


def _safe_float(value) -> Optional[float]:
    """Konvertiert einen Wert sicher zu float, None bei NaN/Inf."""
    if value is None:
        return None
    try:
        f = float(value)
        if np.isnan(f) or np.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _safe_int(value) -> Optional[int]:
    """Konvertiert einen Wert sicher zu int, None bei NaN."""
    if value is None:
        return None
    try:
        f = float(value)
        if np.isnan(f) or np.isinf(f):
            return None
        return int(f)
    except (TypeError, ValueError):
        return None


def _safe_duration(value) -> Optional[str]:
    """Konvertiert Timedelta zu String, None bei NaT."""
    if value is None or (isinstance(value, pd.Timedelta) and pd.isna(value)):
        return None
    return str(value)


def _safe_datetime(value) -> Optional[datetime]:
    """Konvertiert Pandas Timestamp zu Python datetime."""
    if value is None or pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().replace(tzinfo=None)
    return None


def _safe_json_value(val):
    """Konvertiert numpy-Typen zu JSON-kompatiblen Python-Typen."""
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val)
    if isinstance(val, np.ndarray):
        return val.tolist()
    return val


def _make_params_hash(run_id: int, actual_params: dict) -> str:
    """Erzeugt MD5-Hash aus run_id + actual_params für Duplikat-Erkennung."""
    raw = f"{run_id}|{json.dumps(actual_params, sort_keys=True)}"
    return hashlib.md5(raw.encode()).hexdigest()


def _negate(value: Optional[float]) -> Optional[float]:
    """Negiert einen Float-Wert, None bleibt None."""
    return -abs(value) if value is not None else None


def _extract_chart_metrics(pf) -> dict:
    """Extrahiert Chart-Metriken aus pf.stats() für eine einzelne Kombination.

    Stufe 2 (chart): Alle stats()-Felder, aber keine langsamen Properties.
    Die langsamen Properties (tail_ratio, VaR, alpha, beta etc.) werden
    erst in Stufe 3 (full) via _extract_full_metrics berechnet.
    """
    stats = pf.stats()

    return {
        'start_index': _safe_datetime(stats.get('Start Index')),
        'end_index': _safe_datetime(stats.get('End Index')),
        'total_duration': _safe_duration(stats.get('Total Duration')),
        'start_value': _safe_float(stats.get('Start Value')),
        'min_value': _safe_float(stats.get('Min Value')),
        'max_value': _safe_float(stats.get('Max Value')),
        'end_value': _safe_float(stats.get('End Value')),
        'total_return_pct': _safe_float(stats.get('Total Return [%]')),
        'benchmark_return_pct': _safe_float(stats.get('Benchmark Return [%]')),
        'position_coverage_pct': _safe_float(stats.get('Position Coverage [%]')),
        'max_gross_exposure_pct': _safe_float(stats.get('Max Gross Exposure [%]')),
        # GEÄNDERT: stats() liefert DD positiv, muss negativ gespeichert werden
        'max_drawdown_pct': _negate(_safe_float(stats.get('Max Drawdown [%]'))),
        'max_drawdown_duration': _safe_duration(stats.get('Max Drawdown Duration')),
        'total_orders': _safe_int(stats.get('Total Orders')),
        'total_fees_paid': _safe_float(stats.get('Total Fees Paid')),
        'total_trades': _safe_int(stats.get('Total Trades')),
        'win_rate_pct': _safe_float(stats.get('Win Rate [%]')),
        'best_trade_pct': _safe_float(stats.get('Best Trade [%]')),
        'worst_trade_pct': _safe_float(stats.get('Worst Trade [%]')),
        'avg_winning_trade_pct': _safe_float(stats.get('Avg Winning Trade [%]')),
        'avg_losing_trade_pct': _safe_float(stats.get('Avg Losing Trade [%]')),
        'avg_winning_trade_duration': _safe_duration(stats.get('Avg Winning Trade Duration')),
        'avg_losing_trade_duration': _safe_duration(stats.get('Avg Losing Trade Duration')),
        'profit_factor': _safe_float(stats.get('Profit Factor')),
        'expectancy': _safe_float(stats.get('Expectancy')),
        'sharpe_ratio': _safe_float(stats.get('Sharpe Ratio')),
        'calmar_ratio': _safe_float(stats.get('Calmar Ratio')),
        'omega_ratio': _safe_float(stats.get('Omega Ratio')),
        'sortino_ratio': _safe_float(stats.get('Sortino Ratio')),
        'metrics_level': 'chart',
    }


def _extract_full_metrics(pf) -> dict:
    """Extrahiert die langsamen Metriken direkt vom pf-Objekt.

    Stufe 3 (full): Wird als Hintergrund-Job ausgeführt.
    Berechnet nur die Felder die nicht in stats() enthalten sind.
    """
    return {
        'annualized_return': _safe_float(pf.annualized_return * 100),
        'annualized_volatility': _safe_float(pf.annualized_volatility * 100),
        'downside_risk': _safe_float(pf.downside_risk * 100),
        'tail_ratio': _safe_float(pf.tail_ratio),
        'value_at_risk': _safe_float(pf.value_at_risk),
        'cond_value_at_risk': _safe_float(pf.cond_value_at_risk),
        'alpha': _safe_float(pf.alpha),
        'beta': _safe_float(pf.beta),
        'information_ratio': _safe_float(pf.information_ratio),
        'sqn': _safe_float(pf.trades.sqn),
        'edge_ratio': _safe_float(pf.trades.edge_ratio),
        'deflated_sharpe_ratio': _safe_float(pf.deflated_sharpe_ratio),
        'metrics_level': 'full',
    }


def _extract_partial_metrics(portfolios, columns) -> list[dict]:
    """Extrahiert Metriken vektorisiert für alle Kombinationen auf einmal.

    Verwendet Pandas DataFrame statt Python-Schleife für Performance
    bei >100K Kombinationen.
    """
    import time as _time

    t0 = _time.time()
    total_return = portfolios.total_return * 100
    print(f"  [DB] total_return: {_time.time() - t0:.1f}s")

    t0 = _time.time()
    total_market_return = portfolios.total_market_return * 100
    print(f"  [DB] total_market_return: {_time.time() - t0:.1f}s")

    t0 = _time.time()
    profit_factor = portfolios.trades.profit_factor
    print(f"  [DB] profit_factor: {_time.time() - t0:.1f}s")

    t0 = _time.time()
    final_value = portfolios.final_value
    print(f"  [DB] final_value: {_time.time() - t0:.1f}s")

    t0 = _time.time()
    trade_count = portfolios.trades.count()
    print(f"  [DB] trade_count: {_time.time() - t0:.1f}s")

    t0 = _time.time()
    win_rate = portfolios.trades.win_rate * 100
    print(f"  [DB] win_rate: {_time.time() - t0:.1f}s")

    t0 = _time.time()
    max_dd = portfolios.max_drawdown * 100
    print(f"  [DB] max_drawdown: {_time.time() - t0:.1f}s")

    # GEÄNDERT: Trades-basierte Metriken (Trades-Objekt ist bereits gecacht)
    t0 = _time.time()
    expectancy = portfolios.trades.expectancy
    print(f"  [DB] expectancy: {_time.time() - t0:.1f}s")

    # HINWEIS: sqn und edge_ratio nach full verschoben (Trade-Qualität)

    # GEÄNDERT: Risiko-Kennzahlen (Gruppe A)
    t0 = _time.time()
    sharpe = portfolios.sharpe_ratio
    print(f"  [DB] sharpe_ratio: {_time.time() - t0:.1f}s")

    t0 = _time.time()
    sortino = portfolios.sortino_ratio
    print(f"  [DB] sortino_ratio: {_time.time() - t0:.1f}s")

    t0 = _time.time()
    calmar = portfolios.calmar_ratio
    print(f"  [DB] calmar_ratio: {_time.time() - t0:.1f}s")

    t0 = _time.time()
    omega = portfolios.omega_ratio
    print(f"  [DB] omega_ratio: {_time.time() - t0:.1f}s")

    # GEÄNDERT: Annualisierte Metriken (Gruppe B)
    t0 = _time.time()
    ann_return = portfolios.annualized_return * 100
    print(f"  [DB] annualized_return: {_time.time() - t0:.1f}s")

    t0 = _time.time()
    ann_vol = portfolios.annualized_volatility * 100
    print(f"  [DB] annualized_volatility: {_time.time() - t0:.1f}s")

    # GEÄNDERT: Erweiterte Risiko-Metriken (Gruppe B)
    t0 = _time.time()
    down_risk = portfolios.downside_risk * 100
    print(f"  [DB] downside_risk: {_time.time() - t0:.1f}s")

    # HINWEIS: Folgende Metriken nur in _extract_full_metrics (Stufe 3, Hintergrund-Job):
    # sqn, edge_ratio (Trade-Qualität), tail_ratio (61s), value_at_risk (47s),
    # cond_value_at_risk (43s), alpha (7s), beta (7s), information_ratio (7s)

    # GEÄNDERT: Overfitting-Kontrolle (Gruppe B)
    t0 = _time.time()
    deflated_sharpe = portfolios.deflated_sharpe_ratio
    print(f"  [DB] deflated_sharpe_ratio: {_time.time() - t0:.1f}s")

    # GEÄNDERT: Ticket 44 Bugfix — atleast_1d(...) wandelt VBT-Skalare (n_block==1) in
    # 1-Element-Arrays, bevor .values geholt wird. Für n_block>1 ist atleast_1d ein No-Op.
    def _vals(x):
        import numpy as np
        x = np.atleast_1d(x)
        return x.values if hasattr(x, 'values') else x

    t0 = _time.time()
    df = pd.DataFrame({
        'total_return_pct': _vals(total_return),
        'benchmark_return_pct': _vals(total_market_return),
        'profit_factor': _vals(profit_factor),
        'end_value': _vals(final_value),
        'total_trades': _vals(trade_count),
        'win_rate_pct': _vals(win_rate),
        'max_drawdown_pct': _vals(max_dd),
        # Gruppe A
        'sharpe_ratio': _vals(sharpe),
        'sortino_ratio': _vals(sortino),
        'calmar_ratio': _vals(calmar),
        'omega_ratio': _vals(omega),
        'expectancy': _vals(expectancy),
        # Gruppe B
        'annualized_return': _vals(ann_return),
        'annualized_volatility': _vals(ann_vol),
        'downside_risk': _vals(down_risk),
        'deflated_sharpe_ratio': _vals(deflated_sharpe),
    })

    # GEÄNDERT: NaN/Inf echt zu None konvertieren. Das frühere df.where(np.isfinite(df), None)
    # war ein No-Op für Float-Spalten — pandas wandelt None dort sofort zurück in NaN, sodass
    # NaN ungefiltert in die DB lief und u.a. die Sortierung verfälschte (NaN gilt in PostgreSQL
    # als größter Wert). Konvertierung daher erst auf Record-Ebene nach to_dict.
    df['total_trades'] = df['total_trades'].apply(lambda x: int(x) if pd.notna(x) and np.isfinite(x) else None)
    print(f"  [DB] DataFrame: {_time.time() - t0:.1f}s, {len(df)} Zeilen")
    records = df.to_dict('records')
    for r in records:
        for key, value in r.items():
            if isinstance(value, float) and not np.isfinite(value):
                r[key] = None
        r['metrics_level'] = 'partial'
    return records


def _count_combinations(indicators_config: dict) -> int:
    """Vorab-Schätzung der Parameterkombinationen für einen neuen Run.

    Delegiert an die einzige Zähl-Wahrheit count_total_combos (Indikator-Kombis x
    Stop-Kombis, Listen und gekoppeltes TSL-Paar inklusive) — exakt die Zahl, die
    nach dem Lauf als len(columns) persistiert wird. Lokaler Import, damit das
    DB-Repository ohne vectorbtpro importierbar bleibt (count_total_combos wird nur
    im Run-Kontext aufgerufen, wo vbt verfügbar ist).

    Args:
        indicators_config: Indikator-Konfiguration mit Ranges/Listen (+ optional '_stops')

    Returns:
        Anzahl Kombinationen (mindestens 1)
    """
    from user_data.strategies.generic.indicator_factory import count_total_combos
    return count_total_combos(indicators_config)


def create_backtest_run(
    backtest_config: dict,
    indicators_config: dict,
    parent_run_id: Optional[int] = None,
    parent_result_id: Optional[int] = None,
    selection_metric: Optional[str] = None,
    spec_runner_version: Optional[str] = None,
    testset_run_id: Optional[int] = None,
    iteration_id: Optional[int] = None,
    backtest_config_id: Optional[int] = None,
    indicator_config_id: Optional[int] = None,
) -> int:
    """Erstellt einen neuen BacktestRun mit status='queued'.

    Wird VOR der Strategie-Ausführung aufgerufen, damit der Run
    sofort in der UI sichtbar ist. Der Worker setzt den Status auf 'running'
    wenn der Job tatsächlich startet.

    Args:
        backtest_config: Backtest-Konfiguration (enthält strategy_family, strategy_name,
                         symbols, exchange, timeframe, start, end)
        indicators_config: Indikator-Konfiguration
        parent_run_id: Optionale Parent-Run-ID für Walk-Forward Verkettung
        parent_result_id: Optionale Result-ID die die Config geliefert hat
        selection_metric: Metrik nach der das Parent-Result ausgewählt wurde
        spec_runner_version: Versionsnummer des spec_runner-Moduls (Ticket 01)
        testset_run_id: Optionale TestSet-Run-ID (Ticket 04) — NULL bei Einzelstarts
        iteration_id: Optionale Iteration-ID (Ticket 10) — wird via Lookup ermittelt wenn None
        backtest_config_id: Optionale Herkunfts-Referenz auf die gespeicherte BacktestConfig
        indicator_config_id: Optionale Herkunfts-Referenz auf die gespeicherte IndicatorConfig

    Returns:
        int: Die neue Run-ID
    """
    n_combinations = _count_combinations(indicators_config)

    # iteration_id wird vom Aufrufer explizit mitgegeben (Playground, Start-Run, Testset).
    # Kein Auto-Lookup, kein Fallback — wer einen Run startet, wählt die Iteration.

    engine = get_engine()
    with engine.begin() as conn:
        run_stmt = insert(BacktestRun).values(
            strategy_family=backtest_config['strategy_family'],
            strategy_name=backtest_config['strategy_name'],
            symbol=backtest_config['symbols'][0],
            exchange=backtest_config['exchange'],
            timeframe=backtest_config['timeframe'],
            start_date=datetime.strptime(backtest_config['start'], '%Y-%m-%d'),
            end_date=datetime.strptime(backtest_config['end'], '%Y-%m-%d'),
            # GEÄNDERT: Ticket 15 — _json-Suffix
            backtest_config_json=backtest_config,
            indicators_config_json=indicators_config,
            n_combinations=n_combinations,
            status='queued',
            parent_run_id=parent_run_id,
            parent_result_id=parent_result_id,
            selection_metric=selection_metric,
            # GEÄNDERT: Spec-Runner-Version mitschreiben (Ticket 01)
            spec_runner_version=spec_runner_version,
            # GEÄNDERT: TestSet-Run-Zuordnung (Ticket 04)
            testset_run_id=testset_run_id,
            # GEÄNDERT: Ticket 10 — Iterations-FK
            iteration_id=iteration_id,
            # GEÄNDERT: Herkunfts-Referenzen auf gespeicherte Configs (lose, kein FK)
            backtest_config_id=backtest_config_id,
            indicator_config_id=indicator_config_id,
        ).returning(BacktestRun.id)
        result = conn.execute(run_stmt)
        run_id = result.scalar()

    print(f"[DB] BacktestRun {run_id} angelegt (status=queued, {n_combinations} Kombinationen, parent_run={parent_run_id}, iteration_id={iteration_id})")
    return run_id


def update_backtest_run_status(
    run_id: int,
    status: str,
    error_message: Optional[str] = None,
    n_combinations: Optional[int] = None,
) -> None:
    """Aktualisiert den Status eines BacktestRun.

    Args:
        run_id: ID des Runs
        status: Neuer Status ('completed' oder 'failed')
        error_message: Fehlermeldung bei status='failed'
        n_combinations: Anzahl der Kombinationen (optional aktualisieren)
    """
    engine = get_engine()
    values: dict = {'status': status}
    # GEÄNDERT: Verarbeitungsstart festhalten — Moment, in dem der Worker den Run
    # aufgreift. Grundlage für die echte Rechendauer (ohne Queue-Wartezeit).
    if status == 'running':
        values['started_at'] = datetime.now()
    if status in ('completed', 'failed'):
        values['completed_at'] = datetime.now()
    if error_message:
        values['error_message'] = error_message[:2000]
    if n_combinations is not None:
        values['n_combinations'] = n_combinations

    with engine.begin() as conn:
        conn.execute(
            BacktestRun.__table__.update()
            .where(BacktestRun.id == run_id)
            .values(**values)
        )


def update_backtest_run_progress(
    run_id: int,
    current_chunk: int,
    total_chunks: int,
) -> None:
    """Schreibt den Chunk-Fortschritt eines laufenden Runs (ein UPDATE pro Chunk).

    Bewusst schlank gehalten und vom Status entkoppelt: wird vom Spec-Runner per
    Callback einmal je Chunk aufgerufen, damit das Frontend "Chunk X/Y" anzeigen kann.

    Args:
        run_id: ID des Runs
        current_chunk: 1-basierter Index des aktuell bearbeiteten Chunks
        total_chunks: Gesamtzahl der Chunks
    """
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            BacktestRun.__table__.update()
            .where(BacktestRun.id == run_id)
            .values(current_chunk=current_chunk, total_chunks=total_chunks)
        )


def _build_full_config_snapshot(
    backtest_config: dict,
    indicators_config: dict,
    actual_params: dict,
    rules: dict,
) -> dict:
    """Baut den vollständigen Config-Snapshot für ein einzelnes Result.

    Enthält alle drei Teile, die für eine bit-genaue Reproduktion nötig sind:
    - backtest_config: Symbol, Exchange, Zeitraum, Sizing, alle Stops, Formate
    - indicators: aufgelöste Indikator-Config als Dict (Key=Name, feste Werte)
    - rules: {entry, exit} aus der Strategie-Spec

    Args:
        backtest_config: Backtest-Konfiguration aus dem Run (backtest_config_json)
        indicators_config: Indikator-Config mit Ranges (indicators_config_json)
        actual_params: Konkrete Parameterwerte dieses Results
        rules: Regeln {entry, exit} aus der Strategie-Spec

    Returns:
        dict mit Schlüsseln 'backtest_config', 'indicators', 'rules'
    """
    # Portfolio-Felder können verschachtelt unter 'portfolio' liegen (Playground)
    # oder flach auf oberster Ebene (Worker/BacktestConfig aus DB).
    # Beide Strukturen werden unterstützt — flache Felder haben Vorrang.
    _portfolio = backtest_config.get('portfolio') or {}

    def _bc(key: str):
        """Liest Feld erst von oberster Ebene, dann aus 'portfolio'-Block."""
        val = backtest_config.get(key)
        if val is None:
            val = _portfolio.get(key)
        return val

    # GEÄNDERT: Schritt 3d — Die Stops und ihre Formate (delta_format/
    # time_delta_format) gehören jetzt zu '_stops' (Eigentümer IndicatorConfig),
    # nicht mehr zur BacktestConfig. Muss VOR _stop() gebunden sein, da _stop()
    # daraus liest.
    _stops_cfg = indicators_config.get('_stops') or {}

    # GEÄNDERT: Schritt 4c-pre — skalare Stops aus _stops statt backtest_config.
    # Wird ein Stop als Sweep-Achse gefahren, erscheint sein konkreter Wert als
    # MultiIndex-Level in actual_params (Level-Name = vbt.Param-Name, z.B. 'sl_stop').
    # Dieser per-Result-Wert hat Vorrang. Andernfalls gilt der SKALARE Wert aus
    # '_stops'. Kein Rückgriff mehr auf backtest_config (toter Pfad nach dem
    # Stop-Umbau, Eigentümerschaft liegt bei der IndicatorConfig).
    def _stop(key: str):
        """Per-Result-Stop: actual_params (Sweep) vor Skalar aus _stops."""
        if key in actual_params:
            return _safe_json_value(actual_params[key])
        sval = _stops_cfg.get(key)
        # Range-Dicts erscheinen bei Sweep in actual_params; ein hier verbliebenes
        # dict ist kein skalarer Stop-Wert und gilt als nicht gesetzt.
        if isinstance(sval, dict):
            return None
        return _safe_json_value(sval)

    # Backtest-Config-Felder die für Reproduktion zwingend benötigt werden
    _symbols = backtest_config.get('symbols')
    bc_snapshot = {
        'symbol': _symbols[0] if isinstance(_symbols, list) and _symbols else backtest_config.get('symbol'),
        'exchange': _bc('exchange'),
        'timeframe': _bc('timeframe'),
        'start': _bc('start'),
        'end': _bc('end'),
        'ohlc_start': _bc('ohlc_start'),
        'ohlc_end': _bc('ohlc_end'),
        'size': _bc('size'),
        'size_type': _bc('size_type'),
        'init_cash': _bc('init_cash'),
        'fees': _bc('fees'),
        'td_stop': _stop('td_stop'),
        'tp_stop': _stop('tp_stop'),
        'sl_stop': _stop('sl_stop'),
        'tsl_stop': _stop('tsl_stop'),
        'tsl_th': _stop('tsl_th'),
        'delta_format': _stops_cfg.get('delta_format'),
        'time_delta_format': _stops_cfg.get('time_delta_format'),
    }

    # Aufgelöste Indikator-Config (feste Werte statt Ranges)
    resolved_indicators = _build_resolved_config(indicators_config, actual_params)

    return {
        'backtest_config': bc_snapshot,
        'indicators': resolved_indicators,
        'rules': rules,
    }


def _build_resolved_config(indicators_config: dict, actual_params: dict) -> dict:
    """Erstellt eine aufgelöste Indicator-Config mit festen Werten statt Ranges.

    Nimmt die Struktur der indicators_config (tf, indicator, enabled, etc.)
    und ersetzt Range-Parameter durch die konkreten Werte aus actual_params.

    Args:
        indicators_config: Indicator-Config des Runs (mit Ranges)
        actual_params: Flache Parameter des Results (z.B. fastsma_length: 16)

    Returns:
        dict: Gleiche Struktur wie indicators_config aber mit festen Werten
    """
    import copy
    # GEÄNDERT: Schritt 1 — Meta-Keys ('_'-Präfix, z.B. '_stops') gehören nicht in den
    # aufgelösten Indikator-Block. Die Stops liegen im backtest_config-Block des Snapshots.
    resolved = copy.deepcopy({k: v for k, v in indicators_config.items() if not k.startswith('_')})

    for config_key, config_val in resolved.items():
        if not isinstance(config_val, dict):
            continue
        # GEÄNDERT: Level-Präfix der param_product-Columns = vbt-Klassenname,
        # also der Namespace-Teil NACH 'custom:'/'vbt:', kleingeschrieben. Die
        # actual_params-Keys heißen z.B. 'fastsma_length' bzw. 'supertrend_period'
        # — NICHT 'custom:fastsma_length'. Früher wurde der volle Typ-String
        # ('custom:fastSMA') als Präfix genutzt, wodurch nie ein Param matchte und
        # der Recompute den vollen Sweep statt der Einzel-Kombination rechnete.
        indicator_type = config_val.get('indicator', config_key)
        short_name = indicator_type.split(':', 1)[1] if ':' in indicator_type else indicator_type
        prefix = short_name.lower() + '_'

        for param_key, param_val in config_val.items():
            if not isinstance(param_val, dict) or 'start' not in param_val:
                continue
            # Exakter Match: prefix + param_key
            exact_key = prefix + param_key.lower()
            matched_value = actual_params.get(exact_key)

            # Kein exakter Match: Prefix-basiert suchen (Abkürzungen)
            if matched_value is None:
                for ap_key, ap_val in actual_params.items():
                    if not ap_key.lower().startswith(prefix):
                        continue
                    ap_suffix = ap_key.lower()[len(prefix):]
                    if ap_suffix.startswith(param_key.lower()) or param_key.lower().startswith(ap_suffix):
                        matched_value = ap_val
                        break

            if matched_value is not None:
                # GEÄNDERT: Ticket 18 — Skalar statt Pseudo-Range schreiben, dtype-Erhaltung
                dtype = param_val.get('dtype', 'float64')
                if 'int' in dtype:
                    resolved[config_key][param_key] = int(matched_value)
                else:
                    resolved[config_key][param_key] = float(matched_value)

    return resolved


def save_strategy_results(
    run_id: int,
    strategy_results: dict,
    spec_runner_version: Optional[str] = None,
    rules: Optional[dict] = None,
    backtest_config: Optional[dict] = None,
) -> int:
    """
    Speichert Backtest-Ergebnisse für einen existierenden Run in die Datenbank.

    Der Run muss vorher mit create_backtest_run() angelegt worden sein.

    Args:
        run_id: ID des bereits angelegten BacktestRun
        strategy_results: Return-Dict der Strategie-Funktion (enthält 'portfolios')
        spec_runner_version: Versionsnummer des spec_runner-Moduls (Ticket 01)
        rules: Regeln {entry, exit} aus der Strategie-Spec (Ticket 41 — für Snapshot)
        backtest_config: Backtest-Konfiguration (Ticket 41 — für Snapshot).
            Wird für den full_config_snapshot_json benötigt. Falls None, wird aus dem Run geladen.

    Returns:
        int: Anzahl der Parameter-Kombinationen
    """
    # GEÄNDERT: Ticket 44 — Chunked-Pfad: metrics_table + columns statt portfolios.
    # Der spec_runner liefert dieses Format, wenn der Grid in Chunks aufgeteilt wurde.
    # Die Metriken sind bereits fertig extrahiert — kein _extract_partial_metrics nötig.
    if 'metrics_table' in strategy_results:
        all_metrics = strategy_results['metrics_table']   # list[dict]
        columns = strategy_results['columns']              # pd.Index / MultiIndex
        n_combinations = len(columns)
        if n_combinations == 0:
            raise ValueError(
                "Keine Parameter-Kombinationen im Chunked-Ergebnis (leere columns) — "
                "vermutlich fehlende oder leere OHLCV-Daten für den gewählten Zeitraum. "
                "Run kann nicht gespeichert werden."
            )
        metric_keys = list(all_metrics[0].keys()) if all_metrics else []
        portfolios = None  # nicht verfügbar im Chunked-Pfad
    else:
        portfolios = strategy_results['portfolios']
        columns = portfolios.wrapper.columns
        n_combinations = len(columns)

        # GEÄNDERT: Audit-Fund — 0 Kombinationen = Fehlzustand sichtbar abweisen.
        # Ein leeres Portfolio (keine Spalten) entsteht, wenn keine OHLCV-Daten geladen
        # wurden (fehlendes Symbol oder leerer Zeitbereich). Ohne diesen Guard liefe der
        # Code in einen kryptischen IndexError (all_metrics[0] auf leerer Liste), und der
        # Backtest-Run würde je nach Aufrufer still als 'completed' gewertet. Stattdessen
        # eine klare Fehlermeldung — der aufrufende Job markiert den Run dann als 'failed'.
        if n_combinations == 0:
            raise ValueError(
                "Keine Parameter-Kombinationen im Portfolio (leere Spalten) — vermutlich "
                "fehlende oder leere OHLCV-Daten für den gewählten Zeitraum. "
                "Run kann nicht gespeichert werden."
            )

        # Metriken werden weiter unten extrahiert (nach engine.begin())
        all_metrics = None
        metric_keys = None

    engine = get_engine()
    import time as _time
    _t_start = _time.time()
    print(f"[DB] {n_combinations} Kombinationen in strategy_results")

    with engine.begin() as conn:

        # Metriken extrahieren (nur im Original-Pfad — im Chunked-Pfad bereits fertig)
        if portfolios is not None:
            if n_combinations == 1:
                print("[DB] Metriken extrahieren ...")
                pf = portfolios[columns[0]]
                # GEÄNDERT: Chart-Metriken (schnell), Full kommt per Hintergrund-Job
                all_metrics = [_extract_chart_metrics(pf)]
                metric_keys = list(all_metrics[0].keys())

                # Trades, Orders und Positions extrahieren (nur bei 1 Kombination)
                trades_records = pf.trades.records_readable
                orders_records = pf.orders.records_readable
                positions_records = pf.positions.records_readable

            else:
                _t0 = _time.time()
                print("[DB] Partial Metriken extrahieren ...")
                all_metrics = _extract_partial_metrics(portfolios, columns)
                metric_keys = list(all_metrics[0].keys())
                print(f"[DB] Metriken extrahiert ({_time.time() - _t0:.1f}s)")
        else:
            # Chunked-Pfad: Metriken bereits gesetzt, keine Trades/Orders/Positions
            print(f"[DB] Chunked-Pfad: {len(all_metrics)} Metriken bereits extrahiert")

        # Batch aufbauen
        _t0 = _time.time()
        print("[DB] Batch aufbauen ...")
        # Parameter aus MultiIndex extrahieren (vektorisiert)
        col_names = list(columns.names) if hasattr(columns, 'names') else []
        if col_names and hasattr(columns[0], '__iter__') and not isinstance(columns[0], str):
            all_params = [
                {name: _safe_json_value(val) for name, val in zip(col_names, col)}
                for col in columns
            ]
        else:
            all_params = [{'param': str(col)} for col in columns]

        # Indicators-Config und iteration_id des Runs laden für resolved_config
        run_row = conn.execute(
            BacktestRun.__table__.select().where(BacktestRun.id == run_id)
        ).fetchone()
        # GEÄNDERT: Ticket 15 — _json-Suffix
        run_indicators_config = run_row.indicators_config_json if run_row else {}
        # Ticket 10 — iteration_id aus Run konsistent in Results übernehmen
        run_iteration_id = run_row.iteration_id if run_row else None
        # GEÄNDERT: Ticket 41 — backtest_config für Snapshot: Parameter hat Vorrang, sonst aus Run
        _snapshot_backtest_config = backtest_config if backtest_config is not None else (
            run_row.backtest_config_json if run_row else {}
        )

        batch = []
        for idx in range(len(columns)):
            actual_params = all_params[idx]
            resolved = _build_resolved_config(run_indicators_config, actual_params)
            record = {
                'run_id': run_id,
                'params_hash': _make_params_hash(run_id, actual_params),
                # GEÄNDERT: Ticket 15 — _json-Suffix
                'actual_params_json': actual_params,
                'resolved_config_json': resolved,
                **all_metrics[idx],
            }
            # GEÄNDERT: Spec-Runner-Version mitschreiben (Ticket 01)
            if spec_runner_version is not None:
                record['spec_runner_version'] = spec_runner_version
            # GEÄNDERT: Ticket 10 — iteration_id konsistent zum Run setzen
            record['iteration_id'] = run_iteration_id
            # GEÄNDERT: Ticket 41 — vollständigen Config-Snapshot schreiben (nur wenn rules vorhanden)
            if rules is not None:
                record['full_config_snapshot_json'] = _build_full_config_snapshot(
                    backtest_config=_snapshot_backtest_config,
                    indicators_config=run_indicators_config,
                    actual_params=actual_params,
                    rules=rules,
                )
            batch.append(record)

        print(f"[DB] Batch aufgebaut ({_time.time() - _t0:.1f}s)")

        # Bulk-Upsert in Batches à 5000
        _t0 = _time.time()
        batch_size = 5000
        for i in range(0, len(batch), batch_size):
            chunk = batch[i:i + batch_size]
            result_stmt = insert(BacktestResult).values(chunk)
            update_cols = {col: result_stmt.excluded[col] for col in metric_keys}
            # GEÄNDERT: Ticket 15 — _json-Suffix
            update_cols['resolved_config_json'] = result_stmt.excluded['resolved_config_json']
            # GEÄNDERT: spec_runner_version beim Upsert mitschreiben (Ticket 01)
            if spec_runner_version is not None:
                update_cols['spec_runner_version'] = result_stmt.excluded['spec_runner_version']
            # GEÄNDERT: Ticket 10 — iteration_id beim Upsert mitschreiben
            update_cols['iteration_id'] = result_stmt.excluded['iteration_id']
            # GEÄNDERT: Ticket 41 — vollständigen Config-Snapshot beim Upsert mitschreiben
            if rules is not None:
                update_cols['full_config_snapshot_json'] = result_stmt.excluded['full_config_snapshot_json']
            result_stmt = result_stmt.on_conflict_do_update(
                index_elements=['run_id', 'params_hash'],
                set_=update_cols,
            )
            conn.execute(result_stmt)
            print(f"  [DB] {min(i + batch_size, len(batch))}/{len(batch)} geschrieben")
        print(f"[DB] Results geschrieben ({_time.time() - _t0:.1f}s)")

        # Parameter in backtest_params speichern
        _t0 = _time.time()
        print("[DB] Parameter speichern ...")
        # Result-IDs für diesen Run holen (nach Upsert)
        result_rows = conn.execute(
            BacktestResult.__table__.select()
            .where(BacktestResult.run_id == run_id)
            .order_by(BacktestResult.id)
        ).fetchall()
        result_id_map = {r.params_hash: r.id for r in result_rows}

        # Bestehende Parameter löschen (verhindert Duplikate bei Re-Runs)
        existing_result_ids = list(result_id_map.values())
        if existing_result_ids:
            conn.execute(
                BacktestParam.__table__.delete().where(
                    BacktestParam.result_id.in_(existing_result_ids)
                )
            )

        params_batch = []
        for idx in range(len(columns)):
            actual_params = all_params[idx]
            params_hash = batch[idx]['params_hash']
            rid = result_id_map.get(params_hash)
            if rid is None:
                continue
            for param_name, param_value in actual_params.items():
                if param_name == 'symbol':
                    continue
                params_batch.append({
                    'result_id': rid,
                    'param_name': param_name,
                    'param_value': _safe_float(param_value),
                })

        if params_batch:
            for i in range(0, len(params_batch), batch_size):
                conn.execute(insert(BacktestParam), params_batch[i:i + batch_size])
            print(f"  [DB] {len(params_batch)} Parameter gespeichert ({_time.time() - _t0:.1f}s)")

        # Bei 1 Kombination: Trades und Orders speichern (nicht im Chunked-Pfad)
        if n_combinations == 1 and portfolios is not None:
            # Result-ID holen
            result_row = conn.execute(
                BacktestResult.__table__.select().where(BacktestResult.run_id == run_id)
            ).fetchone()
            result_id = result_row.id

            # Trades speichern
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
                print(f"  [DB] {len(trades_batch)} Trades gespeichert")

            # Orders speichern
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
                print(f"  [DB] {len(orders_batch)} Orders gespeichert")

            # Positions speichern
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
                print(f"  [DB] {len(positions_batch)} Positions gespeichert")

            # Equity-Kurve speichern
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
                    chunk = equity_batch[i:i + batch_size]
                    conn.execute(insert(BacktestEquity), chunk)
                print(f"  [DB] {len(equity_batch)} Equity-Werte gespeichert")

            # Indikatoren speichern
            indicators_results = strategy_results.get('indicators_results', {})
            indicators_batch = []
            for ind_name, ind_data in indicators_results.items():
                data_obj = ind_data.get('data')
                if data_obj is None:
                    continue

                # Output-Namen ermitteln (z.B. ['result'] oder ['trend', 'direction', 'long', 'short']).
                # GEÄNDERT: M7 — kein stilles Raten von ['result'] mehr. Ein Datenobjekt ohne
                # output_names ist ein unbekanntes Format; in einer Trading-Software werden solche
                # Unbekannten nicht stillschweigend halb gespeichert. Stattdessen harter Abbruch:
                # die Transaktion rollt zurück, der aufrufende Job markiert den Run als 'failed'
                # mit dieser Meldung (sichtbar in der Runs-Liste).
                output_names = getattr(data_obj, 'output_names', None)
                if not output_names:
                    raise ValueError(
                        f"Indikator '{ind_name}': Datenobjekt vom Typ '{type(data_obj).__name__}' "
                        f"hat keine 'output_names' — die Output-Kanäle sind nicht bestimmbar. "
                        f"Run wird abgebrochen, um keine unvollständigen Indikator-Daten zu speichern."
                    )

                for output_name in output_names:
                    series = getattr(data_obj, output_name, None)
                    if series is None:
                        continue
                    # Bei MultiIndex-Columns die erste Spalte nehmen (n_combinations == 1)
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
                    chunk = indicators_batch[i:i + batch_size]
                    conn.execute(insert(BacktestIndicator), chunk)
                print(f"  [DB] {len(indicators_batch)} Indikator-Werte gespeichert")

        # Run abschließen — n_combinations aktualisieren und Status setzen
        conn.execute(
            BacktestRun.__table__.update()
            .where(BacktestRun.id == run_id)
            .values(
                status='completed',
                completed_at=datetime.now(),
                n_combinations=n_combinations,
            )
        )

    print(f"[DB] BacktestRun {run_id} gespeichert, {n_combinations} Kombinationen (Gesamt: {_time.time() - _t_start:.1f}s)")

    return n_combinations
