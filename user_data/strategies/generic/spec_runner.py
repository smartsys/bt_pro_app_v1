"""Generic Spec Runner.

Führt eine Strategie aus drei Dicts aus (indicators_json, backtest_config_json,
rules_json) und liefert ein strategy_results-Dict im selben Format wie die
handgeschriebenen Strategien.

Unterstützt Multi-Combo über `factory.run(..., param_product=True)` im
indicator_factory. Single-Combo ist der Sonderfall, wenn alle Parameter-Arrays
Length 1 haben — der Code-Pfad ist in beiden Fällen identisch.

Für sehr große Multiparameter-Läufe (> chunk_size Kombis) wird automatisch
chunk-weises Batching aktiviert. Jeder Block ist ein kartesisches Sub-Produkt;
nach dem Lauf werden die Metriken aller Blöcke konkateniert. Das Ergebnis-Dict
enthält dann 'metrics_table' + 'columns' statt 'portfolios'. Der recompute-Pfad
und single-combo-Pfad bleiben unverändert ('_disable_chunked': True).

Versionierung (SemVer — MANUELL erhöhen):
    Major (X.0.0): Breaking Change der Spec-Interpretation. Gleiche Spec liefert
        nach dem Upgrade andere Ergebnisse, z.B. geändertes Rules-Engine-Verhalten,
        neue Pflicht-Felder in backtest_config_json, geänderter Default-Wert mit
        messbarer Auswirkung auf Signale oder Portfolio-Werte.
    Minor (x.Y.0): Neues Primitiv oder Feature, rückwärtskompatibel. Bestehende
        Specs laufen unverändert durch; die neue Funktionalität ist opt-in, z.B.
        ein neuer Rule-Typ oder ein neuer optionaler Parameter.
    Patch (x.y.Z): Bugfix ohne Verhaltensänderung für korrekte Inputs. Falsch
        berechnete oder gar nicht ausgeführte Logik wird repariert, ohne dass
        gültige Specs andere Ergebnisse produzieren.

Hinweis: Nach einer Version-Erhöhung muss der Worker-Container neu gestartet
werden, damit die neue VERSION in neue Runs/Results geschrieben wird.
"""

from typing import Any, Callable, Optional

# GEÄNDERT: Versionskonstante für Reproduzierbarkeit von Backtests (Ticket 01)
# GEÄNDERT: Ticket 34 — Patch-Bump: Run-Start-Validierung deaktivierter/fehlender
# Indikator-Referenzen. Keine Verhaltensänderung für korrekte Specs.
# GEÄNDERT: Patch-Bump 1.0.2 — Multi-Indikator-Cross-Produkt im rules_engine.
# Disjunkte Param-Level mehrerer Indikatoren (z.B. zwei Indikator-Ketten mit verschiedenen Param-Leveln)
# werden jetzt kreuzproduktiert statt mit 'Cannot align indexes' abzubrechen.
# Vorher gar nicht ausführbare Multi-Combo-Specs laufen nun durch; Single-Combo
# unverändert.
# GEÄNDERT: Ticket 46 — Minor-Bump 1.1.0: Short-Positionen im Masken-Pfad via
# is_short=True auf Entry/Exit-Blöcken. evaluate_rules gibt jetzt SignalMasks
# (vier Masken) zurück; from_signals erhält short_entries/short_exits.
# GEÄNDERT: Ticket 47 Bugfix — Patch-Bump 1.2.1: Multi-Combo im nativen Pfad jetzt
# vektorisiert (col % n_combo Mapping in der signal_func_nb) statt fehlerhaftem
# Single-Combo-Pre-Expand. Spalten-Identität (Indikator-Param-Achse) wieder
# vollständig; Ticket-44-Multi-Combo-Chunking reaktiviert. Korrekte Specs liefern
# identische Werte UND korrekte Spalten-Labels.
# GEÄNDERT: Paket B — Major-Bump 2.0.0: Per-Indikator-Timeframe (tf) im echten Runner
# scharf geschaltet. Ein Indikator mit abweichendem (groeberem) 'tf' rechnet jetzt nativ
# auf ohlc_data.resample(tf) und wird look-ahead-sicher auf den Basis-Index realignt
# (vorher wurde 'tf' im Runner still verworfen). Breaking: Specs, die ein nicht-Basis-'tf'
# tragen, liefern nach dem Upgrade andere (jetzt korrekte) Ergebnisse. Specs ohne 'tf'
# bzw. mit tf==Basis bleiben bit-identisch.
VERSION = "2.0.0"

# Zentraler Importpfad zum generischen Spec-Runner-Einstiegspunkt. Wird von API-Routen
# als import_path in die BacktestConfig geschrieben — Single Source statt verstreuter Literale.
SPEC_RUNNER_IMPORT_PATH = "user_data.strategies.generic.spec_runner.run_spec_strategy"

import pandas as pd
import vectorbtpro as vbt

from user_data.strategies.generic.indicator_factory import (
    build_indicators,
    split_indicators_json_chunks,
    STOP_PARAM_KEYS,
    _TSL_PAIR_KEYS,
    expand_stop_values,
    is_stop_sweep,
)
from user_data.strategies.generic.rules_engine import (
    evaluate_rules_native,
)


def run_spec_strategy(
    ohlc_data: Any,
    indicators_json: dict,
    backtest_config_json: dict,
    rules_json: Optional[dict] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> dict:
    """Führt die Spec als Multi-Combo-Backtest aus.

    Args:
        ohlc_data: vbt.Data-Objekt (z.B. aus load_ohlc_data).
        indicators_json: Indikator-Spec (flat) mit 'indicator:<id>:<out>'-Chaining. Darf keinen '_rules'-Key
            mehr enthalten (ab Ticket 12 in iteration.spec_json).
        backtest_config_json: Backtest-Parameter inkl. 'portfolio'-Block.
        rules_json: Entry-/Exit-Regeln. Pflichtparameter seit Ticket 12. Der Worker
            lädt Rules aus iteration.spec_json und übergibt sie explizit.
        progress_callback: Optionaler Callback (current_chunk, total_chunks), den der
            gechunkte Pfad einmal je Chunk aufruft. Hält den Spec-Runner DB-frei -
            der Worker injiziert das DB-Update. None = kein Fortschritts-Reporting.

    Returns:
        dict mit Keys 'portfolios', 'indicators_results', 'signals',
        'analysis_results_dict' - kompatibel zu save_strategy_results().
        Bei gechunkten Läufen stattdessen 'metrics_table' + 'columns'.

    Raises:
        ValueError: Wenn rules_json fehlt.
    """
    print("\nstart run_spec_strategy ..")

    # GEÄNDERT: Ticket 12 — _rules-Fallback entfernt. Rules kommen jetzt immer explizit
    # aus iteration.spec_json (Worker-Pfad) oder direkt vom Aufrufer.
    if rules_json is None:
        raise ValueError(
            "rules_json fehlt. Ab Ticket 12 müssen Rules explizit übergeben werden. "
            "Worker-Pfad: rules aus BacktestRun.iteration.spec_json['rules'] laden."
        )

    # GEÄNDERT: Ticket 34 — Run-Start-Validierung. Referenziert eine Regel einen
    # Indikator, der in der Indikator-Config deaktiviert (enabled: false) ist oder
    # ganz fehlt, bricht der Run hier mit klarer Meldung ab — statt später still
    # in rules_engine._resolve_ref mit einer generischen Meldung zu crashen.
    _validate_rule_references(rules_json, indicators_json)

    # GEÄNDERT: Ticket 44 — Combo-Batching: große Grids werden chunk-weise verarbeitet
    # um OOM-Crashes bei 36k+ Kombis zu vermeiden. Der recompute-Pfad setzt
    # '_disable_chunked': True in backtest_config_json um Chunking zu unterbinden.
    chunk_size = int(backtest_config_json.get('chunk_size', 5000))
    disable_chunked = backtest_config_json.get('_disable_chunked', False)

    if not disable_chunked:
        chunks = split_indicators_json_chunks(indicators_json, chunk_size=chunk_size)
    else:
        chunks = [indicators_json]

    if len(chunks) > 1:
        # GEÄNDERT: Ticket 47 Bugfix — Multi-Combo-Sub-Grid-Chunking (Ticket 44)
        # wiederhergestellt. Der native Pfad verarbeitet jetzt Multi-Combo direkt
        # (col % n_combo Mapping), daher kein Single-Combo-Zwang mehr. Jeder Chunk
        # ist ein kartesisches Sub-Produkt von max. chunk_size Kombis und liefert
        # ein Multi-Combo-Portfolio mit vollständigem Spalten-MultiIndex.
        print(f" - Chunked Modus: {len(chunks)} Chunks a max. {chunk_size} Kombis")
        return _run_chunked(
            chunks=chunks,
            ohlc_data=ohlc_data,
            backtest_config_json=backtest_config_json,
            rules_json=rules_json,
            progress_callback=progress_callback,
        )

    # Indikatoren bauen (respektiert Chain-Dependencies). base_tf = Basis-Timeframe aus
    # der BacktestConfig: erkennt tf==Basis als No-Op unabhaengig von ohlc_data.wrapper.freq.
    indicators = build_indicators(
        indicators_json, ohlc_data, base_tf=backtest_config_json.get('timeframe')
    )
    print(f" - Indikatoren gebaut: {list(indicators.keys())}")

    # Portfolio-Parameter aus backtest_config_json extrahieren
    pf_cfg = backtest_config_json['portfolio']
    timeframe = backtest_config_json['timeframe']

    # GEÄNDERT: Schritt 1 — Stop-Parameter (tp/sl/tsl/td) kommen aus dem reservierten
    # Meta-Key '_stops' im indicators_json, NICHT mehr aus pf_cfg.
    # GEÄNDERT: Schritt 2 — Skalar bleibt Skalar, Liste/Range wird zur Sweep-Achse
    # (vbt.Param). build_stop_kwargs übersetzt das und koppelt das TSL-Paar.
    stops_cfg = indicators_json.get('_stops', {})
    stop_kwargs = build_stop_kwargs(stops_cfg)
    stops_swept = any(is_stop_sweep(stops_cfg.get(k)) for k in STOP_PARAM_KEYS)

    stop_exit_price = _resolve_stop_exit_price(pf_cfg.get('stop_exit_price'))
    stop_order_type = pf_cfg.get('stop_order_type')

    close_series = ohlc_data.get('Close')
    open_series = ohlc_data.get('Open')
    high_series = ohlc_data.get('High')
    low_series = ohlc_data.get('Low')

    # GEÄNDERT: Ticket 47 Phase 2 — Einheitlicher nativer Pfad. Alle Backtests laufen
    # über evaluate_rules_native (signal_func_nb). Der Masken-Pfad (else-Zweig) wurde
    # entfernt. use_native-Flag und _rule_group_uses_state_refs-Check nicht mehr nötig.
    print(" - Nativer Pfad: signal_func_nb")
    start_date = pd.Timestamp(backtest_config_json['start'], tz='UTC')
    end_date   = pd.Timestamp(backtest_config_json['end'], tz='UTC')

    pf_common_kwargs = dict(
        close=close_series,
        open=open_series,
        high=high_series,
        low=low_series,
        fees=pf_cfg['fees'],
        tp_stop=stop_kwargs['tp_stop'],
        sl_stop=stop_kwargs['sl_stop'],
        tsl_th=stop_kwargs['tsl_th'],
        tsl_stop=stop_kwargs['tsl_stop'],
        freq=timeframe,
        init_cash=pf_cfg['init_cash'],
        size=pf_cfg['size'],
        size_type=pf_cfg['size_type'],
        td_stop=stop_kwargs['td_stop'],
        delta_format=stops_cfg.get('delta_format'),
        time_delta_format=stops_cfg.get('time_delta_format'),
        stop_exit_price=stop_exit_price,
        stop_order_type=stop_order_type,
        chunked=False,
    )

    portfolios = evaluate_rules_native(
        rules_json=rules_json,
        ohlc_data=ohlc_data,
        indicators=indicators,
        pf_kwargs=pf_common_kwargs,
        date_start=start_date,
        date_end=end_date,
        stops_swept=stops_swept,
    )

    # Roh-Signale nicht verfügbar (signal_func_nb produziert per-bar)
    long_entries = None
    long_exits = None
    short_entries = None
    short_exits = None
    print(f" - Portfolio gebaut (Trades = {len(portfolios.trades.records)})")

    # indicators_results in Format der bestehenden Strategien bringen
    indicators_results = _build_indicators_results(indicators, indicators_json, timeframe)

    # GEÄNDERT: Ticket 46 — signals-Dict enthält jetzt vier Masken statt entries/exits
    return {
        'portfolios': portfolios,
        'indicators_results': indicators_results,
        'signals': {
            'long_entries': long_entries,
            'long_exits': long_exits,
            'short_entries': short_entries,
            'short_exits': short_exits,
        },
        'analysis_results_dict': None,
    }


# GEÄNDERT: Ticket 44 — Hilfsfunktion für chunk-weisen Multi-Combo-Backtest
def _run_chunked(
    chunks: list[dict],
    ohlc_data: Any,
    backtest_config_json: dict,
    rules_json: dict,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> dict:
    """Führt einen Multi-Combo-Backtest chunk-weise aus und sammelt Metrik-Tabellen.

    Jeder Chunk ist ein kartesisches Sub-Produkt. Pro Chunk werden Indikatoren
    gebaut, Signale berechnet, das Portfolio erstellt und sofort auf die exakt
    16 Felder von _extract_partial_metrics reduziert. n_block==1 (VBT liefert
    Skalare) wird durch np.atleast_1d() in _vals() korrekt behandelt.
    Der Chunk-Speicher wird zwischen den Blöcken freigegeben.

    deflated_sharpe_ratio ist quer-schnittlich: var_sharpe und N hängen von ALLEN
    Kombis ab. Im gechunkten Lauf sieht jeder Chunk nur seine eigenen Spalten,
    weshalb _extract_partial_metrics ein falsches DSR liefern würde. Lösung:
    Pro Chunk werden die DSR-Bausteine (nicht-annualisierte Sharpe, Skew, Kurtosis, T)
    gesammelt. Nach der Konkatenation wird DSR global und korrekt neu berechnet und
    in flat_metrics überschrieben. Die exakte VBT-Formel wird 1:1 kopiert.

    Args:
        chunks: Liste von sub-indicators_json-Dicts (je ein gültiger Sub-Grid).
        ohlc_data: OHLCV-Datenobjekt.
        backtest_config_json: Backtest-Konfiguration (ohne chunk_size — wird intern gesetzt).
        rules_json: Entry-/Exit-Regeln.

    Returns:
        dict mit 'metrics_table' (list[dict]), 'columns' (pd.Index / MultiIndex),
        'indicators_results', 'signals', 'analysis_results_dict'.
    """
    import gc
    import numpy as np
    from scipy import stats as scipy_stats
    from user_data.utils.database.repository import _extract_partial_metrics

    all_metrics: list[list[dict]] = []
    all_columns: list = []
    last_indicators_results = None

    # DSR-Bausteine pro Kombi — werden nach Konkatenation global verrechnet
    all_sharpes: list[np.ndarray] = []    # nicht-annualisierte Sharpe je Kombi
    all_skews: list[np.ndarray] = []      # Skewness der Returns je Kombi
    all_kurtoses: list[np.ndarray] = []   # Kurtosis der Returns je Kombi
    dsr_T: int = 0                        # Anzahl Zeitreihen-Zeilen (gleich für alle)

    # VBT-Default-Parameter für Sharpe / DSR (aus ReturnsAccessor.defaults)
    _DSR_RISK_FREE: float = 0.0
    _DSR_DDOF: int = 1
    _DSR_BIAS: bool = True

    # _disable_chunked setzt, damit rekursive Aufrufe nicht erneut chunken
    sub_config = {**backtest_config_json, '_disable_chunked': True}

    for block_idx, sub_indicators_json in enumerate(chunks):
        print(f" - Chunk {block_idx + 1}/{len(chunks)}: Indikatoren bauen ...")

        # GEÄNDERT: Chunk-Fortschritt an die DB melden (ein UPDATE pro Chunk), damit
        # das Frontend "Chunk X/Y" anzeigen kann. Fehler im Reporting darf den Lauf
        # nie kippen - daher defensiv gekapselt.
        if progress_callback is not None:
            try:
                progress_callback(block_idx + 1, len(chunks))
            except Exception as exc:
                print(f"   ! Fortschritts-Update fehlgeschlagen (ignoriert): {exc}")

        block_result = run_spec_strategy(
            ohlc_data=ohlc_data,
            indicators_json=sub_indicators_json,
            backtest_config_json=sub_config,
            rules_json=rules_json,
        )

        block_pf = block_result['portfolios']
        block_columns = block_pf.wrapper.columns
        n_block = len(block_columns)

        print(f"   -> {n_block} Kombis in Chunk {block_idx + 1}, Metriken extrahieren ...")
        # GEÄNDERT: Ticket 44 Bugfix — _vals() in _extract_partial_metrics verwendet nun
        # np.atleast_1d(), sodass n_block==1 (VBT liefert Skalare statt Arrays) korrekt
        # behandelt wird. Kein gesonderter Workaround für n_block==1 mehr nötig.
        block_metrics = _extract_partial_metrics(block_pf, block_columns)

        # GEÄNDERT: Ticket 44 DSR-Fix — DSR-Bausteine je Kombi sammeln (quer-schnittliche
        # Rekonstruktion nach Konkatenation aller Chunks).
        # Nicht-annualisierte Sharpe: ann_factor=1 (identisch zu VBT sharpe_ratio_1d_nb,
        # annualized=False → ann_factor=1, risk_free=0.0).
        # block_pf.returns ist ein DataFrame; np.asarray → T x n_block numpy-Array.
        returns_2d = np.asarray(block_pf.returns)  # T x n_block

        # Nicht-annualisierte Sharpe exakt nach VBT sharpe_ratio_1d_nb:
        # mean(returns) / nanstd(returns, ddof) mit risk_free=0.0 abgezogen.
        excess_returns = returns_2d - _DSR_RISK_FREE  # 0.0 → no-op
        col_means = np.nanmean(excess_returns, axis=0)
        col_stds = np.nanstd(excess_returns, axis=0, ddof=_DSR_DDOF)
        block_sharpe_arr = np.where(
            col_stds > 0,
            col_means / col_stds,
            np.where(col_means == 0, np.nan, np.inf),
        )

        # Skew und Kurtosis für DSR (VBT setzt NaN→0 vor scipy-Aufruf)
        returns_2d_for_moments = returns_2d.copy()
        nanmask = np.isnan(returns_2d_for_moments)
        if nanmask.any():
            returns_2d_for_moments[nanmask] = 0.0
        block_skew = np.atleast_1d(scipy_stats.skew(returns_2d_for_moments, axis=0, bias=_DSR_BIAS))
        block_kurt = np.atleast_1d(scipy_stats.kurtosis(returns_2d_for_moments, axis=0, bias=_DSR_BIAS))

        # T (Anzahl Zeitreihen-Schritte) — gleich für alle Chunks
        if dsr_T == 0:
            dsr_T = block_pf.wrapper.shape_2d[0]

        all_sharpes.append(np.atleast_1d(block_sharpe_arr))
        all_skews.append(block_skew)
        all_kurtoses.append(block_kurt)

        all_metrics.append(block_metrics)
        all_columns.append(block_columns)
        last_indicators_results = block_result.get('indicators_results')

        # Chunk-Speicher freigeben
        del block_pf, block_result, returns_2d, returns_2d_for_moments
        gc.collect()
        print(f"   -> Chunk {block_idx + 1} abgeschlossen")

    # Metriken aller Chunks zu einer flachen Liste zusammenführen
    flat_metrics = [row for block in all_metrics for row in block]

    # Spalten-Index aller Chunks konkatenieren
    combined_columns = all_columns[0]
    for col in all_columns[1:]:
        combined_columns = combined_columns.append(col)

    # GEÄNDERT: Ticket 44 DSR-Fix — deflated_sharpe_ratio global korrekt neu berechnen.
    # Exakte VBT-Formel aus ReturnsAccessor.deflated_sharpe_ratio (1:1 kopiert):
    #   var_sharpe = np.nanvar(sharpe_ratio, ddof=ddof)  # über ALLE Kombis
    #   SR0 = sharpe + sqrt(var_sharpe) * (
    #       (1 - euler_gamma) * norm.ppf(1 - 1/N)
    #       + euler_gamma * norm.ppf(1 - 1/(N*e))
    #   )
    #   out = norm.cdf(((sharpe - SR0) * sqrt(T-1)) / sqrt(1 - skew*sharpe + ((kurt-1)/4)*sharpe**2))
    all_sharpes_concat = np.concatenate(all_sharpes)
    all_skews_concat = np.concatenate(all_skews)
    all_kurtoses_concat = np.concatenate(all_kurtoses)
    N_total = len(all_sharpes_concat)
    var_sharpe_global = np.nanvar(all_sharpes_concat, ddof=_DSR_DDOF)

    SR0_global = all_sharpes_concat + np.sqrt(var_sharpe_global) * (
        (1 - np.euler_gamma) * scipy_stats.norm.ppf(1 - 1 / N_total)
        + np.euler_gamma * scipy_stats.norm.ppf(1 - 1 / (N_total * np.e))
    )
    dsr_denominator = np.sqrt(
        1
        - all_skews_concat * all_sharpes_concat
        + ((all_kurtoses_concat - 1) / 4) * all_sharpes_concat ** 2
    )
    # Schutz vor Division durch null / negativem Radikand
    dsr_denominator = np.where(dsr_denominator > 0, dsr_denominator, np.nan)
    dsr_global = scipy_stats.norm.cdf(
        ((all_sharpes_concat - SR0_global) * np.sqrt(dsr_T - 1)) / dsr_denominator
    )

    # Globale DSR-Werte zurückschreiben
    def _safe_float_local(v: float) -> Optional[float]:
        """Konvertiert float zu None bei NaN/Inf (identisch zu repository._safe_float)."""
        if v is None:
            return None
        try:
            f = float(v)
            if np.isnan(f) or np.isinf(f):
                return None
            return f
        except (TypeError, ValueError):
            return None

    for i, dsr_val in enumerate(dsr_global):
        flat_metrics[i]['deflated_sharpe_ratio'] = _safe_float_local(dsr_val)

    print(
        f" - Chunked Lauf abgeschlossen: {len(flat_metrics)} Kombis gesamt"
        f" (DSR global neu berechnet: N={N_total}, var_sharpe={var_sharpe_global:.6f})"
    )

    # GEÄNDERT: Ticket 46 — signals-Dict enthält jetzt vier Masken statt entries/exits
    return {
        'metrics_table': flat_metrics,       # list[dict] mit 16-Spalten-Records
        'columns': combined_columns,          # pd.Index / MultiIndex
        'indicators_results': last_indicators_results,
        'signals': {
            'long_entries': None,
            'long_exits': None,
            'short_entries': None,
            'short_exits': None,
        },
        'analysis_results_dict': None,
    }


def _collect_indicator_refs(obj: Any) -> set[str]:
    """Sammelt rekursiv alle in rules_json referenzierten Indikator-IDs.

    Eine Referenz hat die Form 'indicator:<id>:<output>' (oder 'indicator:<id>').
    Die Struktur von rules_json (entry/exit -> conditions -> lhs/rhs) wird
    generisch durchlaufen, damit auch verschachtelte Gruppen erfasst werden.

    Args:
        obj: Beliebiger Teilbaum von rules_json (dict, list oder Skalar).

    Returns:
        Menge der referenzierten Indikator-IDs.
    """
    refs: set[str] = set()
    if isinstance(obj, str):
        if obj.startswith('indicator:'):
            parts = obj.split(':')
            if len(parts) >= 2 and parts[1]:
                refs.add(parts[1])
    elif isinstance(obj, dict):
        for value in obj.values():
            refs |= _collect_indicator_refs(value)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            refs |= _collect_indicator_refs(value)
    return refs


def _validate_rule_references(rules_json: dict, indicators_json: dict) -> None:
    """Prüft beim Run-Start, ob alle regelreferenzierten Indikatoren verfügbar sind.

    Bricht mit klarer Fehlermeldung ab, wenn eine Entry-/Exit-Regel einen
    Indikator referenziert, der in der Indikator-Config deaktiviert
    (enabled: false) ist oder ganz fehlt.

    Args:
        rules_json: Entry-/Exit-Regeln mit Indikator-Referenzen.
        indicators_json: Indikator-Config mit optionalem 'enabled'-Flag je Eintrag.

    Raises:
        ValueError: Wenn referenzierte Indikatoren deaktiviert sind oder fehlen.
    """
    # GEÄNDERT: Ticket 48 — nur aktive Blöcke (enabled: true / fehlendes enabled) in die
    # Referenz-Prüfung einbeziehen. Deaktivierte Blöcke dürfen deaktivierte Indikatoren
    # referenzieren, ohne den Lauf zu blockieren. _collect_indicator_refs selbst bleibt unverändert.
    referenced: set[str] = set()
    for grp_key in ('entry', 'exit'):
        grp = rules_json.get(grp_key)
        if grp and isinstance(grp, dict):
            active_blocks = [b for b in (grp.get('blocks') or []) if b.get('enabled', True)]
            referenced |= _collect_indicator_refs({'blocks': active_blocks})
    disabled: list[str] = []
    missing: list[str] = []
    for ind_id in sorted(referenced):
        entry = indicators_json.get(ind_id)
        if entry is None:
            missing.append(ind_id)
        elif entry.get('enabled', True) is False:
            disabled.append(ind_id)

    if not disabled and not missing:
        return

    parts: list[str] = []
    if disabled:
        parts.append(
            "deaktivierte Indikatoren: " + ", ".join(disabled)
            + " (in der Indikator-Config aktivieren oder die Bedingung entfernen)"
        )
    if missing:
        parts.append(
            "fehlende Indikatoren: " + ", ".join(missing)
            + " (nicht in der gewählten Indikator-Config enthalten)"
        )
    raise ValueError(
        "Run abgebrochen: Die Regeln referenzieren Indikatoren, die nicht "
        "verfügbar sind — " + "; ".join(parts) + "."
    )


def _resolve_stop_exit_price(value: Optional[str]):
    """Mapt einen String wie 'Close' auf vbt.pf_enums.StopExitPrice.Close."""
    if value is None:
        return None
    return getattr(vbt.pf_enums.StopExitPrice, value)


# GEÄNDERT: Schritt 2 — '_stops' in from_signals-kwargs übersetzen (Skalar vs. Sweep).
def build_stop_kwargs(stops_cfg: dict) -> dict:
    """Übersetzt das '_stops'-Dict in from_signals-kwargs (Skalar oder vbt.Param).

    Skalar/None bleibt Skalar. Liste/Range-Dict wird zur Sweep-Achse via vbt.Param.
    Unabhängige Stops (tp_stop, sl_stop, td_stop) kreuzen sich (volles Kreuzprodukt).
    Das TSL-Paar (tsl_th, tsl_stop) wird — wenn BEIDE gesweept sind — als
    zusammengehörige Paare gekoppelt (gleiches level=0, zip, kein Kreuzprodukt);
    Längen müssen übereinstimmen. Wird nur EINER gesweept, läuft er als normale
    unabhängige Achse.

    vbt-Mechanik (verifiziert): Sobald irgendein vbt.Param ein level= trägt, brauchen
    ALLE Param-Achsen ein level=. Daher: bei gekoppeltem TSL-Paar bekommen alle
    Sweep-Stops explizite, eindeutige Level (TSL-Paar teilt level=0, jeder andere
    Stop ein eigenes Level). Ohne TSL-Kopplung bleiben alle Param ohne level (Default).

    Args:
        stops_cfg: Das '_stops'-Dict (kann fehlen/leer sein).

    Returns:
        Dict mit from_signals-kwargs (Schlüssel aus STOP_PARAM_KEYS), Werte sind
        Skalare oder vbt.Param-Objekte. Fehlende Keys -> None.

    Raises:
        ValueError: Bei TSL-Paar-Längen-Mismatch oder leerer Sweep-Achse.
    """
    if not stops_cfg:
        return {key: None for key in STOP_PARAM_KEYS}

    tsl_th_swept = is_stop_sweep(stops_cfg.get('tsl_th'))
    tsl_stop_swept = is_stop_sweep(stops_cfg.get('tsl_stop'))
    tsl_pair_coupled = tsl_th_swept and tsl_stop_swept

    # Bei Kopplung brauchen ALLE Sweep-Achsen ein explizites Level.
    use_explicit_levels = tsl_pair_coupled

    kwargs: dict = {}
    next_level = 1  # level=0 ist für das gekoppelte TSL-Paar reserviert

    for key in STOP_PARAM_KEYS:
        raw = stops_cfg.get(key)

        if not is_stop_sweep(raw):
            # Skalar/None bleibt unverändert (wie Schritt 1).
            kwargs[key] = raw
            continue

        values = expand_stop_values(raw, key)

        if tsl_pair_coupled and key in _TSL_PAIR_KEYS:
            # Gekoppeltes Paar: gleiches level=0 erzwingt zip statt Kreuzprodukt.
            # Längen-Check sicherstellen (beide Paar-Hälften gleich lang).
            th_len = len(expand_stop_values(stops_cfg.get('tsl_th'), 'tsl_th'))
            stop_len = len(expand_stop_values(stops_cfg.get('tsl_stop'), 'tsl_stop'))
            if th_len != stop_len:
                raise ValueError(
                    f"Gekoppelter TSL-Sweep: tsl_th ({th_len} Werte) und tsl_stop "
                    f"({stop_len} Werte) müssen gleich lang sein — sie werden als "
                    f"Paare (zip) gekoppelt, kein Kreuzprodukt."
                )
            kwargs[key] = vbt.Param(values, level=0)
        elif use_explicit_levels:
            # Unabhängige Achse bei aktiver Kopplung: eigenes, eindeutiges Level.
            kwargs[key] = vbt.Param(values, level=next_level)
            next_level += 1
        else:
            # Keine Kopplung: Default-vbt.Param (volles Kreuzprodukt ohne level).
            kwargs[key] = vbt.Param(values)

    return kwargs


def _build_indicators_results(indicators: dict, indicators_json: dict, timeframe: str) -> dict:
    """Baut das indicators_results-Dict im Format der bestehenden Strategien."""
    out: dict = {}
    from user_data.strategies.generic.registry import resolve_indicator_factory
    for ind_id, inst in indicators.items():
        spec = indicators_json.get(ind_id, {})
        # Inputs anhand factory.input_names aussortieren, damit nur echte Parameter übrig bleiben
        try:
            fac = resolve_indicator_factory(spec.get('indicator', ''))
            input_names = set(getattr(fac, 'input_names', ()) or ())
        except Exception:
            input_names = set()
        skip_keys = {'indicator', 'tf', 'enabled'} | input_names
        params = {k: v for k, v in spec.items() if k not in skip_keys}
        out[ind_id] = {
            'name': ind_id,
            'type': spec.get('indicator'),
            'tf': spec.get('tf', timeframe),
            'enabled': spec.get('enabled', True),
            'params': params,
            'data': inst,
        }
    return out
