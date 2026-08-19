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
enthält dann 'metrics_table' + 'columns' + 'ann_factor' statt 'portfolios'. Der
recompute-Pfad und single-combo-Pfad bleiben unverändert ('_disable_chunked': True).

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

# GEÄNDERT: Versionskonstante für Reproduzierbarkeit von Backtests
# GEÄNDERT: Patch-Bump: Run-Start-Validierung deaktivierter/fehlender
# Indikator-Referenzen. Keine Verhaltensänderung für korrekte Specs.
# GEÄNDERT: Patch-Bump 1.0.2 — Multi-Indikator-Cross-Produkt im rules_engine.
# Disjunkte Param-Level mehrerer Indikatoren (z.B. zwei Indikator-Ketten mit verschiedenen Param-Leveln)
# werden jetzt kreuzproduktiert statt mit 'Cannot align indexes' abzubrechen.
# Vorher gar nicht ausführbare Multi-Combo-Specs laufen nun durch; Single-Combo
# unverändert.
# GEÄNDERT: Minor-Bump 1.1.0: Short-Positionen im Masken-Pfad via
# is_short=True auf Entry/Exit-Blöcken. evaluate_rules gibt jetzt SignalMasks
# (vier Masken) zurück; from_signals erhält short_entries/short_exits.
# GEÄNDERT: Bugfix — Patch-Bump 1.2.1: Multi-Combo im nativen Pfad jetzt
# vektorisiert (col % n_combo Mapping in der signal_func_nb) statt fehlerhaftem
# Single-Combo-Pre-Expand. Spalten-Identität (Indikator-Param-Achse) wieder
# vollständig; Multi-Combo-Chunking reaktiviert. Korrekte Specs liefern
# identische Werte UND korrekte Spalten-Labels.
# GEÄNDERT: Paket B — Major-Bump 2.0.0: Per-Indikator-Timeframe (tf) im echten Runner
# scharf geschaltet. Ein Indikator mit abweichendem (groeberem) 'tf' rechnet jetzt nativ
# auf ohlc_data.resample(tf) und wird look-ahead-sicher auf den Basis-Index realignt
# (vorher wurde 'tf' im Runner still verworfen). Breaking: Specs, die ein nicht-Basis-'tf'
# tragen, liefern nach dem Upgrade andere (jetzt korrekte) Ergebnisse. Specs ohne 'tf'
# bzw. mit tf==Basis bleiben bit-identisch.
# GEÄNDERT: Major-Bump 3.0.0: Kennzahlen laufen ausschließlich über das
# Handelsfenster start..end der BacktestConfig; der Vorlauf (ohlc_start..ohlc_end) wärmt
# nur noch die Indikatoren auf. Breaking: Buy-and-Hold-Vergleichsmaßstab, Sharpe,
# annualisierte Größen und alle benchmark-relativen Kennzahlen ändern sich für jede Spec
# mit Vorlauf. Zusätzlich rechnen Trefferquote und Profitfaktor im Multi-Kombinations-Pfad
# jetzt über geschlossene Trades (vorher inklusive einer am Fensterende offenen Position).
#
# HERKUNFT EINES RESULTS (Anforderung 4): Die Konvention, nach der die
# Kennzahlen eines Results gerechnet wurden, steht in backtest_results.spec_runner_version:
#   < 3.0.0  — Kennzahlen über das volle Datenfenster ohlc_start..ohlc_end (inkl. Vorlauf);
#              Trefferquote/Profitfaktor im Multi-Kombinations-Pfad inkl. offener Position;
#              backtest_results.open_trades ist NULL (Spalte existierte noch nicht).
#   >= 3.0.0 — Kennzahlen ausschließlich über start..end; Trefferquote/Profitfaktor über
#              geschlossene Trades; open_trades ist gesetzt.
# Alte und neue Zahlen sind nicht vergleichbar. Der Bestand wird bewusst nicht nachgerechnet.
#
# MIT 3.0.0 WECHSELT NICHT NUR DER ZEITRAUM, SONDERN AUCH DIE GRUNDGESAMTHEIT.
# Trefferquote und Profitfaktor rechnen ab 3.0.0 über die geschlossenen Trades
# (total_trades - open_trades) statt über alle. Gemessen an 200 Kombinationen
# (BTCUSDT 4h, 2022-01-01..2024-01-01): Alle 200 trugen eine am Fensterende offene
# Position; die Trefferquote verschob sich um bis zu 4,76 Prozentpunkte (Median
# -0,42), der Profitfaktor um bis zu -0,75. Der Betrag skaliert mit 1/Trades — bei
# 15 Trades 4,8 Punkte, bei 185 Trades unter 0,6.
#
# Folge für die Bestwert-Auswahl: Das Win-Rate-Band ist eines der vier
# Standard-Kriterien (siehe run-bestwerte). Verschiebt sich die Trefferquote, kann in
# einem Lauf ein anderes Result das Band gewinnen als vor 3.0.0. Wer alte und neue
# Favoriten nebeneinanderlegt, findet den Grund hier: unterschiedliche
# Grundgesamtheit, nicht unterschiedliche Rechnung auf denselben Trades.
#
# Ist für eine Kombination KEIN Trade geschlossen (alle Positionen laufen über das
# Fensterende hinaus), sind Trefferquote und Profitfaktor nicht bestimmbar und stehen
# als NULL in der Datenbank — ausdrücklich nicht als 0, das wäre ein Totalausfall.
#
# GEÄNDERT: Minor-Bump 3.1.0: 'slippage' ist ein neuer optionaler
# Portfolio-Parameter im backtest_config_json['portfolio']-Block und geht als Anteil
# vom Orderpreis an from_signals. Fehlt der Key oder ist er None/0.0, rechnet der
# Runner bit-identisch zu 3.0.0 — es ist also opt-in, kein Verhaltenswechsel für
# bestehende Specs. Ebenfalls in 3.1.0: 'stop_exit_price' wird roh an VBT
# durchgereicht statt über einen case-sensitiven Custom-Resolver; gültige Werte in
# abweichender Schreibweise ('close') laufen jetzt durch, statt mit AttributeError
# abzubrechen. Für Werte, die vorher schon funktionierten, ändert sich nichts.
#
# GEÄNDERT: Major-Bump 4.0.0: Die Deflated Sharpe Ratio entsteht nicht mehr
# hier. Der gechunkte Pfad sammelt keine DSR-Bausteine mehr und schreibt keine DSR in die
# Metriken-Tabelle; die zweite, aus VBT abgeschriebene Formelkopie ist ersatzlos entfallen.
# Stattdessen liefert der Runner den Annualisierungsfaktor des Laufs mit ('ann_factor',
# aus VBTs ReturnsAccessor), und die Kennzahl entsteht als Nachlauf über den ganzen Lauf
# (repository._calculate_deflated_sharpe) mit korrigierter Formel.
#
# HERKUNFT EINES RESULTS, Fortsetzung:
#   < 4.0.0  — deflated_sharpe_ratio nach VBTs Formel: mit dem Fehler 'sharpe_ratio +' im
#              Zähler (strukturell auf 0,5 gedeckelt und unabhängig vom bewerteten
#              Kandidaten) und mit der Excess- statt der rohen Wölbung im Nenner. Im
#              gechunkten Lauf zusätzlich aus einer zweiten Formelkopie.
#   >= 4.0.0 — deflated_sharpe_ratio aus der eigenen, korrigierten Rechnung über das
#              gesamte Raster (N = backtest_runs.n_combinations), gechunkt wie ungechunkt
#              derselbe Weg.
# Breaking, weil dieselbe Spec nach dem Upgrade eine andere (jetzt korrekte) DSR liefert.
# Alle übrigen Kennzahlen bleiben bit-identisch zu 3.1.0.
#
# GEÄNDERT: Minor-Bump 4.1.0: Zwei neue optionale Parameter, rein für die
# Ausgabe der Ergebnisse — 'chunk_sink' (Senke, die jeden fertig gerechneten Chunk sofort
# entgegennimmt) und 'completed_chunks' (Zahl der bereits gespeicherten führenden Chunks,
# die übersprungen werden). Gerechnet wird unverändert: dieselbe Spec liefert dieselben
# Kennzahlen, ob mit oder ohne Senke, ob in einem Stück oder fortgesetzt. Ohne die beiden
# Parameter verhält sich der Runner exakt wie 4.0.0.
#
# GEÄNDERT: Minor-Bump 4.2.0: Ein Stop-Feld in '_stops' nimmt zusätzlich eine
# Indikator-Referenz ({'ref': 'indicator:<id>:<output>', 'mult': ...}). Der Stopabstand
# kommt dann aus einer Zeitreihe statt aus einem festen Wert — je Portfolio-Spalte aus
# dem dort gerechneten Indikator-Parametersatz. Opt-in: Specs ohne Referenz-Stop laufen
# unverändert und bit-identisch zu 4.1.0, die Kombinationszahl bleibt gleich (eine
# Referenz ist keine Sweep-Achse).
#
# GEÄNDERT: Minor-Bump 4.3.0: Ein Referenz-Stop auf 'sl_stop'/'tsl_stop' nimmt
# zusätzlich '"live": true'. Der Abstand wird dann bei jeder Kerze einer offenen
# Position aus der Serie neu gesetzt statt beim Einstieg eingefroren; '"ratchet": true'
# (Default) lässt das Stop-Niveau dabei nur zugunsten der Position wandern. Opt-in:
# ohne Live-Serie greift der Zweig nicht, Specs ohne '"live": true' laufen bit-identisch
# zu 4.2.0.
VERSION = "4.3.0"

# Zentraler Importpfad zum generischen Spec-Runner-Einstiegspunkt. Wird von API-Routen
# als import_path in die BacktestConfig geschrieben — Single Source statt verstreuter Literale.
SPEC_RUNNER_IMPORT_PATH = "user_data.strategies.generic.spec_runner.run_spec_strategy"

import vectorbtpro as vbt

from user_data.strategies.generic.indicator_factory import (
    build_indicators,
    split_indicators_json_chunks,
    STOP_PARAM_KEYS,
    _TSL_PAIR_KEYS,
    _collect_varying_axes,
    expand_stop_values,
    is_stop_sweep,
)
from user_data.strategies.generic.stop_refs import (
    is_stop_ref,
    parse_stop_refs,
    resolve_stop_refs,
)
from user_data.strategies.generic.rules_engine import (
    evaluate_rules_native,
)
# GEÄNDERT: Handelsfenster (start..end) als einzige Bildungsvorschrift.
from user_data.utils.metrics.trading_window import (
    build_trading_window,
    slice_to_trading_window,
)


def run_spec_strategy(
    ohlc_data: Any,
    indicators_json: dict,
    backtest_config_json: dict,
    rules_json: Optional[dict] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    chunk_sink: Optional[Callable[[int, list, Any, float], None]] = None,
    completed_chunks: int = 0,
) -> dict:
    """Führt die Spec als Multi-Combo-Backtest aus.

    Args:
        ohlc_data: vbt.Data-Objekt (z.B. aus load_ohlc_data).
        indicators_json: Indikator-Spec (flat) mit 'indicator:<id>:<out>'-Chaining. Darf keinen '_rules'-Key
            mehr enthalten (seit der Umstellung in iteration.spec_json).
        backtest_config_json: Backtest-Parameter inkl. 'portfolio'-Block.
        rules_json: Entry-/Exit-Regeln. Pflichtparameter seit der Umstellung. Der Worker
            lädt Rules aus iteration.spec_json und übergibt sie explizit.
        progress_callback: Optionaler Callback (current_chunk, total_chunks), den der
            gechunkte Pfad einmal je Chunk aufruft. Hält den Spec-Runner DB-frei -
            der Worker injiziert das DB-Update. None = kein Fortschritts-Reporting.
        chunk_sink: Optionale Senke, die jeden fertig gerechneten Chunk
            sofort entgegennimmt: (chunk_index, metrics_table, columns, ann_factor).
            Der Worker hängt daran das Speichern in die Datenbank; der Spec-Runner
            bleibt DB-frei. Mit Senke sammelt der Runner nichts mehr im Speicher und
            liefert statt 'metrics_table' die Zahl der abgegebenen Kombinationen unter
            'chunks_saved'. Ohne Senke (save-freie Direktaufrufe) bleibt es beim
            bisherigen Sammeln.
        completed_chunks: Anzahl der von vorn her bereits gespeicherten Chunks eines
            fortgesetzten Laufs. Diese Chunks werden übersprungen. Die
            Chunk-Aufteilung ist deterministisch, der übersprungene Chunk k ist also
            derselbe wie im abgebrochenen Lauf. Nur im gechunkten Pfad wirksam.

    Returns:
        dict mit Keys 'portfolios', 'indicators_results', 'signals',
        'analysis_results_dict' - kompatibel zu save_strategy_results().
        Bei gechunkten Läufen stattdessen 'metrics_table' + 'columns' bzw.
        'chunks_saved' (mit Senke).

    Raises:
        ValueError: Wenn rules_json fehlt.
    """
    print("\nstart run_spec_strategy ..")

    # GEÄNDERT: _rules-Fallback entfernt. Rules kommen jetzt immer explizit
    # aus iteration.spec_json (Worker-Pfad) oder direkt vom Aufrufer.
    if rules_json is None:
        raise ValueError(
            "rules_json fehlt. Seit der Umstellung müssen Rules explizit übergeben werden. "
            "Worker-Pfad: rules aus BacktestRun.iteration.spec_json['rules'] laden."
        )

    # GEÄNDERT: Run-Start-Validierung. Referenziert eine Regel einen
    # Indikator, der in der Indikator-Config deaktiviert (enabled: false) ist oder
    # ganz fehlt, bricht der Run hier mit klarer Meldung ab — statt später still
    # in rules_engine._resolve_ref mit einer generischen Meldung zu crashen.
    _validate_rule_references(rules_json, indicators_json)

    # GEÄNDERT: (Anforderung 3, Audit-Befund 11) — Run-Start-Validierung der
    # Rastergröße. Ein enabled, gesweepter, nirgends referenzierter Indikator würde in
    # describe_combos/count_total_combos mitgezählt, ohne dass sich die Portfolio-Spalten
    # unterscheiden — Folge: kollidierende params_hash-Werte, still überschriebene
    # Ergebnisse, Ergebniszahl unter n_combinations.
    _validate_swept_indicators_referenced(rules_json, indicators_json)

    # GEÄNDERT: Run-Start-Validierung der Referenz-Stops. Notation und
    # Verfügbarkeit des referenzierten Indikators werden geprüft, bevor die
    # Indikatoren gebaut werden — ein Tippfehler kostet dann keine Rechenzeit.
    _validate_stop_references(indicators_json)

    # GEÄNDERT: Combo-Batching: große Grids werden chunk-weise verarbeitet
    # um OOM-Crashes bei 36k+ Kombis zu vermeiden. Der recompute-Pfad setzt
    # '_disable_chunked': True in backtest_config_json um Chunking zu unterbinden.
    chunk_size = int(backtest_config_json.get('chunk_size', 5000))
    disable_chunked = backtest_config_json.get('_disable_chunked', False)

    if not disable_chunked:
        chunks = split_indicators_json_chunks(indicators_json, chunk_size=chunk_size)
    else:
        chunks = [indicators_json]

    if len(chunks) > 1:
        # GEÄNDERT: Bugfix — Multi-Combo-Sub-Grid-Chunking
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
            chunk_sink=chunk_sink,
            completed_chunks=completed_chunks,
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
    # GEÄNDERT: Referenz-Stops zur Zeitreihe auflösen. Muss nach
    # build_indicators laufen — die Serie kommt aus einer gebauten Instanz.
    stop_ref_series = resolve_stop_refs(stops_cfg, ohlc_data, indicators)
    if stop_ref_series:
        print(f" - Referenz-Stops: {sorted(stop_ref_series.keys())}")
    stops_swept = any(is_stop_sweep(stops_cfg.get(k)) for k in STOP_PARAM_KEYS)

    # GEÄNDERT: beide Stop-Enum-Felder werden roh an from_signals
    # durchgereicht. VBT löst sie selbst case-insensitiv auf (map_enum_fields); der
    # frühere Custom-Resolver _resolve_stop_exit_price war case-sensitiv und hätte
    # gültige Schreibweisen wie 'close' abgewiesen. Die klare Meldung bei einem
    # ungültigen Wert liefert die Prüfung an der Eingabegrenze
    # (user_data/utils/portfolio_enums.py).
    stop_exit_price = pf_cfg.get('stop_exit_price')
    stop_order_type = pf_cfg.get('stop_order_type')

    # GEÄNDERT: slippage als Anteil vom Orderpreis. Fehlender Key oder None
    # (Alt-Runs, Alt-Leaderboard-Snapshots) bedeutet 0.0 = VBT-Default, also
    # unverändertes Rechnen wie vor dem Ticket.
    slippage = pf_cfg.get('slippage')
    if slippage is None:
        slippage = 0.0

    close_series = ohlc_data.get('Close')
    open_series = ohlc_data.get('Open')
    high_series = ohlc_data.get('High')
    low_series = ohlc_data.get('Low')

    # GEÄNDERT: Phase 2 — Einheitlicher nativer Pfad. Alle Backtests laufen
    # über evaluate_rules_native (signal_func_nb). Der Masken-Pfad (else-Zweig) wurde
    # entfernt. use_native-Flag und _rule_group_uses_state_refs-Check nicht mehr nötig.
    print(" - Nativer Pfad: signal_func_nb")
    # GEÄNDERT: Fenstergrenzen kommen aus build_trading_window, damit
    # Entry-Maske und Kennzahlen-Zuschnitt garantiert dieselben Grenzen benutzen.
    start_date, end_date = build_trading_window(backtest_config_json)

    pf_common_kwargs = dict(
        close=close_series,
        open=open_series,
        high=high_series,
        low=low_series,
        fees=pf_cfg['fees'],
        slippage=slippage,
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
        stop_ref_series=stop_ref_series,
    )

    # Roh-Signale nicht verfügbar (signal_func_nb produziert per-bar)
    long_entries = None
    long_exits = None
    short_entries = None
    short_exits = None
    print(f" - Portfolio gebaut (Trades = {len(portfolios.trades.records)})")

    # indicators_results in Format der bestehenden Strategien bringen
    indicators_results = _build_indicators_results(indicators, indicators_json, timeframe)

    # GEÄNDERT: signals-Dict enthält jetzt vier Masken statt entries/exits
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


# GEÄNDERT: Hilfsfunktion für chunk-weisen Multi-Combo-Backtest
def _run_chunked(
    chunks: list[dict],
    ohlc_data: Any,
    backtest_config_json: dict,
    rules_json: dict,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    chunk_sink: Optional[Callable[[int, list, Any, float], None]] = None,
    completed_chunks: int = 0,
) -> dict:
    """Führt einen Multi-Combo-Backtest chunk-weise aus und gibt die Metriken ab.

    Jeder Chunk ist ein kartesisches Sub-Produkt. Pro Chunk werden Indikatoren
    gebaut, Signale berechnet, das Portfolio erstellt und sofort auf die
    Felder von _extract_metrics reduziert. n_block==1 (VBT liefert
    Skalare) wird durch np.atleast_1d() in _vals() korrekt behandelt.
    Der Chunk-Speicher wird zwischen den Blöcken freigegeben.

    GEÄNDERT: mit `chunk_sink` geht jeder fertige Chunk sofort an die
    Senke (der Worker schreibt ihn in die Datenbank) und wird hier nicht mehr
    aufgehoben. Ein hart beendeter Lauf verliert damit höchstens den Chunk, an dem er
    gerade rechnete, statt seiner gesamten Arbeit. `completed_chunks` überspringt die
    beim Fortsetzen bereits gespeicherten führenden Chunks; die Chunk-Aufteilung ist
    deterministisch, Chunk k ist also derselbe wie im abgebrochenen Lauf.

    Die deflated_sharpe_ratio wird hier NICHT gerechnet. Sie ist
    rasterweit — var_sharpe und die Rastergröße N hängen von ALLEN Kombinationen ab —
    und entsteht deshalb erst als Nachlauf über den ganzen Lauf, nachdem die Results
    geschrieben sind (repository._calculate_deflated_sharpe). Damit ist der gechunkte
    Fall automatisch richtig, ohne dass hier eine zweite Formel stünde — und aus
    demselben Grund ändert das chunkweise Speichern nichts an ihrem Wert: sie läuft
    unverändert erst nach dem letzten Chunk über den kompletten Lauf. Was dieser
    Pfad dafür beisteuern muss, ist der Annualisierungsfaktor: im gechunkten Lauf
    kommt kein Portfolio beim Speichern an, aus dem er sich holen ließe.

    Args:
        chunks: Liste von sub-indicators_json-Dicts (je ein gültiger Sub-Grid).
        ohlc_data: OHLCV-Datenobjekt.
        backtest_config_json: Backtest-Konfiguration (ohne chunk_size — wird intern gesetzt).
        rules_json: Entry-/Exit-Regeln.
        progress_callback: Optionaler Fortschritts-Callback (current_chunk, total_chunks).
        chunk_sink: Optionale Senke (chunk_index, metrics_table, columns, ann_factor).
        completed_chunks: Zahl der zu überspringenden, bereits gespeicherten Chunks.

    Returns:
        Ohne Senke: dict mit 'metrics_table' (list[dict]), 'columns' (pd.Index /
        MultiIndex), 'ann_factor' (float), 'indicators_results', 'signals',
        'analysis_results_dict'.
        Mit Senke: dict mit 'chunks_saved' (Zahl der an die Senke abgegebenen
        Kombinationen), 'ann_factor', 'indicators_results', 'signals',
        'analysis_results_dict' — die Kennzahlen selbst hat die Senke.
    """
    import gc
    from user_data.utils.database.repository import _extract_metrics

    # GEÄNDERT: Überspringen ohne Senke wäre stiller Datenverlust: die
    # übersprungenen Chunks fehlten im Rückgabewert, und der Aufrufer würde ein
    # unvollständiges Raster für ein vollständiges halten.
    if completed_chunks > 0 and chunk_sink is None:
        raise ValueError(
            f"completed_chunks={completed_chunks} ohne chunk_sink: Ein fortgesetzter "
            f"Lauf setzt voraus, dass die bereits gerechneten Chunks gespeichert sind "
            f"und die neuen ebenfalls gespeichert werden."
        )

    all_metrics: list[list[dict]] = []
    all_columns: list = []
    last_indicators_results = None
    # GEÄNDERT: Zahl der an die Senke abgegebenen Kombinationen. Bleibt bei
    # 0, wenn ein fortgesetzter Lauf gar keinen Chunk mehr rechnen musste.
    n_sunk = 0

    # GEÄNDERT: Annualisierungsfaktor aus VBT (ReturnsAccessor.ann_factor).
    # Er hängt nur an Jahres- und Balkenfrequenz und ist deshalb über alle Blöcke
    # identisch; genommen wird der des ersten Blocks. Nicht nachgebaut, nicht aus einer
    # eigenen Timeframe-Tabelle abgeleitet — es muss der Wert sein, den VBT selbst für
    # den annualisierten Sharpe benutzt.
    ann_factor: Optional[float] = None

    # _disable_chunked setzt, damit rekursive Aufrufe nicht erneut chunken
    sub_config = {**backtest_config_json, '_disable_chunked': True}

    for block_idx, sub_indicators_json in enumerate(chunks):
        # GEÄNDERT: bereits gespeicherte Chunks eines fortgesetzten Laufs
        # überspringen. Ihre Results stehen in der Datenbank; sie noch einmal zu rechnen
        # wäre genau die Arbeit, die das Ticket sparen soll.
        if block_idx < completed_chunks:
            print(
                f" - Chunk {block_idx + 1}/{len(chunks)}: übersprungen "
                f"(bereits gespeichert)"
            )
            continue

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

        # GEÄNDERT: Zuschnitt auf das Handelsfenster gleich hier, damit die
        # Kennzahlen auf dem Fenster rechnen und nicht auf den erzwungen flachen
        # Vorlauf-Balken. _extract_metrics schneidet zusätzlich selbst — der zweite
        # Schnitt ist auf einem bereits gefensterten Portfolio wirkungslos und hält die
        # Garantie in der Extraktionsfunktion.
        block_pf = slice_to_trading_window(
            block_result['portfolios'], backtest_config_json
        )
        block_columns = block_pf.wrapper.columns
        n_block = len(block_columns)

        print(f"   -> {n_block} Kombis in Chunk {block_idx + 1}, Metriken extrahieren ...")
        # GEÄNDERT: Bugfix — _vals() in _extract_metrics verwendet nun
        # np.atleast_1d(), sodass n_block==1 (VBT liefert Skalare statt Arrays) korrekt
        # behandelt wird. Kein gesonderter Workaround für n_block==1 mehr nötig.
        # GEÄNDERT: Handelsfenster durchreichen. Der Zuschnitt greift je
        # Chunk, weil jeder Chunk sein eigenes Portfolio hat.
        # GEÄNDERT: 'metrics_resolved' kommt aus create_backtest_run (einzige
        # Auflösungsstelle, kennt die Gesamt-Rastergröße). Jeder Chunk bekommt dieselbe
        # bereits aufgelöste Gruppenmenge — sonst würde 'auto' hier gegen die kleinere
        # Chunk-Größe statt der Gesamtzahl entscheiden.
        block_metrics = _extract_metrics(
            block_pf, block_columns, backtest_config_json,
            groups=backtest_config_json.get('metrics_resolved'),
        )

        # GEÄNDERT: Annualisierungsfaktor einmal am ersten Block abgreifen.
        if ann_factor is None:
            ann_factor = float(block_pf.returns_acc.ann_factor)

        # GEÄNDERT: mit Senke wandert der Chunk sofort weiter (der Worker
        # schreibt ihn in die Datenbank) und wird hier nicht mehr aufgehoben. Ein Fehler
        # der Senke darf NICHT verschluckt werden: er bedeutet, dass die Arbeit dieses
        # Chunks nicht gesichert ist — der Lauf bricht dann sichtbar ab.
        if chunk_sink is not None:
            chunk_sink(block_idx, block_metrics, block_columns, ann_factor)
            n_sunk += n_block
        else:
            all_metrics.append(block_metrics)
            all_columns.append(block_columns)
        last_indicators_results = block_result.get('indicators_results')

        # Chunk-Speicher freigeben
        del block_pf, block_result, block_metrics, block_columns
        gc.collect()
        print(f"   -> Chunk {block_idx + 1} abgeschlossen")

    # GEÄNDERT: signals-Dict enthält jetzt vier Masken statt entries/exits
    # GEÄNDERT: 'ann_factor' mitliefern: im gechunkten Pfad kommt beim
    # Speichern kein Portfolio an, aus dem er sich holen ließe. Ohne ihn kann der
    # DSR-Nachlauf den Sharpe je Balken nicht aus dem annualisierten rekonstruieren.
    common = {
        'ann_factor': ann_factor,
        'indicators_results': last_indicators_results,
        'signals': {
            'long_entries': None,
            'long_exits': None,
            'short_entries': None,
            'short_exits': None,
        },
        'analysis_results_dict': None,
    }

    if chunk_sink is not None:
        print(
            f" - Chunked Lauf abgeschlossen: {n_sunk} Kombis an die Senke abgegeben,"
            f" {completed_chunks} Chunk(s) übersprungen (ann_factor={ann_factor})"
        )
        return {'chunks_saved': n_sunk, **common}

    # Metriken aller Chunks zu einer flachen Liste zusammenführen
    flat_metrics = [row for block in all_metrics for row in block]

    # Spalten-Index aller Chunks konkatenieren
    combined_columns = all_columns[0]
    for col in all_columns[1:]:
        combined_columns = combined_columns.append(col)

    print(
        f" - Chunked Lauf abgeschlossen: {len(flat_metrics)} Kombis gesamt"
        f" (ann_factor={ann_factor})"
    )

    return {
        'metrics_table': flat_metrics,       # list[dict] mit den Feldern aus _extract_metrics
        'columns': combined_columns,          # pd.Index / MultiIndex
        **common,
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
    # GEÄNDERT: nur aktive Blöcke (enabled: true / fehlendes enabled) in die
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


def _validate_swept_indicators_referenced(rules_json: dict, indicators_json: dict) -> None:
    """Prüft beim Run-Start, ob jeder gesweepte Indikator tatsächlich benutzt wird.

    Ein aktivierter (`enabled`, Default True) Indikator mit mindestens einer
    variierenden Sweep-Achse (Range/Liste statt Skalar) muss über eine
    Erreichbarkeits-Kette aus aktiven Chain-Referenzen in einer aktiven
    Regel-Bedingung enden (direkt oder über beliebig viele Zwischen-Indikatoren).
    Eine flache "wird irgendwo als Chain-Input referenziert"-Prüfung reicht
    NICHT: Eine Kette, die selbst in keiner Regel endet, oder deren haltendes
    Zwischenglied deaktiviert ist, trägt nichts zu den Signalen bei — die
    Sweep-Achse zählt in describe_combos/count_total_combos (indicator_factory.py)
    trotzdem mit, die Portfolio-Spalten unterscheiden sich für die
    verschiedenen Sweep-Werte aber nicht. Folge: kollidierende params_hash-
    Werte, der Upsert überschreibt Ergebnisse still, und die tatsächliche
    Ergebniszahl liegt unter n_combinations, ohne dass ein Fehler sichtbar wird.

    Args:
        rules_json: Entry-/Exit-Regeln mit Indikator-Referenzen.
        indicators_json: Indikator-Spec mit optionalen Sweep-Achsen (Range-Dict
            oder Liste statt Skalar).

    Raises:
        ValueError: Wenn ein gesweepter Indikator nirgends erreichbar ist.
    """
    # Startmenge: direkte Referenzen aus den aktiven Blöcken von Entry und Exit.
    referenced: set[str] = set()
    for grp_key in ('entry', 'exit'):
        grp = rules_json.get(grp_key)
        if grp and isinstance(grp, dict):
            active_blocks = [b for b in (grp.get('blocks') or []) if b.get('enabled', True)]
            referenced |= _collect_indicator_refs({'blocks': active_blocks})

    # GEÄNDERT: Ein Referenz-Stop ist eine echte Verwendung. Ein nur dort
    # referenzierter, gesweepter Indikator (z.B. die ATR-Länge des Stopabstands)
    # unterscheidet die Portfolio-Spalten sehr wohl — er darf nicht als "ohne
    # Verwendung" abgewiesen werden.
    referenced |= _collect_indicator_refs(indicators_json.get('_stops') or {})

    # Transitive Erreichbarkeits-Schließung über Chain-Inputs (BFS mit "schon gesehen"-Set,
    # analog zur Kanten-Behandlung in indicator_factory._topological_order — zyklensicher, da
    # jede ID höchstens einmal in die Arbeitsmenge kommt). Ein bereits erreichter Indikator
    # gibt seine EIGENEN Chain-Inputs nur weiter, wenn er selbst aktiviert ist — ein
    # deaktivierter Indikator wird nie gerechnet und hält keine Referenz am Leben. Es werden
    # gezielt nur die Chain-Kanten des jeweiligen Eintrags aufgelöst (_collect_indicator_refs
    # auf DIESEN Eintrag), nicht mehr blind über das gesamte indicators_json — sonst würde
    # jede Kette wieder als "irgendwie benutzt" durchgehen, egal wo sie endet.
    to_visit = list(referenced)
    while to_visit:
        ind_id = to_visit.pop()
        entry = indicators_json.get(ind_id)
        if not isinstance(entry, dict) or entry.get('enabled', True) is False:
            continue
        for dep_id in _collect_indicator_refs(entry):
            if dep_id not in referenced:
                referenced.add(dep_id)
                to_visit.append(dep_id)

    swept_ids = sorted({ind_id for ind_id, _key, _vals in _collect_varying_axes(indicators_json)})
    unused = [ind_id for ind_id in swept_ids if ind_id not in referenced]
    if not unused:
        return

    raise ValueError(
        "Run abgebrochen: gesweepte Indikatoren ohne Verwendung — " + ", ".join(unused)
        + " (weder in einer Regel referenziert noch als Chain-Input eines anderen "
        "Indikators verwendet; die Sweep-Achse zählt sonst in der Kombinationszahl mit, "
        "ohne dass sich die Portfolio-Spalten unterscheiden, wodurch Ergebnisse mit "
        "kollidierendem params_hash still überschrieben werden)."
    )


# GEÄNDERT: Run-Start-Validierung der Referenz-Stops.
def _validate_stop_references(indicators_json: dict) -> None:
    """Prüft Notation und Verfügbarkeit der Indikator-Referenzen in '_stops'.

    Die Notation selbst (ref-Form, mult als Zahl, live/ratchet als Wahrheitswerte)
    prüft ``parse_stop_refs``. Zusätzlich muss der referenzierte Indikator in der
    Indikator-Config vorhanden und aktiviert sein — sonst stünde der Stop später
    ohne Wert da.

    Args:
        indicators_json: Indikator-Spec mit optionalem '_stops'-Block.

    Raises:
        ValueError: Bei ungültiger Notation oder fehlendem/deaktiviertem Indikator.
            Die Meldung nennt Stop-Feld und Referenz.
    """
    specs = parse_stop_refs(indicators_json.get('_stops') or {})
    problems: list[str] = []
    for stop_key, spec in specs.items():
        ind_id = spec.ref.split(':')[1]
        entry = indicators_json.get(ind_id)
        if entry is None:
            problems.append(
                f"{stop_key}: {spec.ref!r} — Indikator {ind_id!r} ist nicht in der "
                f"gewählten Indikator-Config enthalten"
            )
        elif entry.get('enabled', True) is False:
            problems.append(
                f"{stop_key}: {spec.ref!r} — Indikator {ind_id!r} ist deaktiviert "
                f"(enabled: false)"
            )
    if problems:
        raise ValueError(
            "Run abgebrochen: Referenz-Stops zeigen auf nicht verfügbare Indikatoren — "
            + "; ".join(problems) + "."
        )


# GEÄNDERT: Schritt 2 — '_stops' in from_signals-kwargs übersetzen (Skalar vs. Sweep).
def build_stop_kwargs(stops_cfg: dict) -> dict:
    """Übersetzt das '_stops'-Dict in from_signals-kwargs (Skalar oder vbt.Param).

    Skalar/None bleibt Skalar. Liste/Range-Dict wird zur Sweep-Achse via vbt.Param.
    Ein Indikator-Referenz-Dict ({'ref': ...}) liefert hier None: seine Zeitreihe
    steht erst nach build_indicators fest und wird in evaluate_rules_native als
    Array je Portfolio-Spalte eingesetzt (stop_refs.resolve_stop_refs).
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

        if is_stop_ref(raw):
            # GEÄNDERT: Indikator-Referenz. Der Wert ist hier noch nicht
            # bekannt — die Zeitreihe wird erst nach build_indicators aufgelöst und in
            # evaluate_rules_native als Array je Portfolio-Spalte eingesetzt. Das
            # Referenz-Dict selbst darf nie an from_signals gehen.
            kwargs[key] = None
            continue

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
    """Baut das indicators_results-Dict im Format der bestehenden Strategien.

    Args:
        indicators: Berechnete Indikator-Instanzen.
        indicators_json: Indikator-Spec (Flat-Dict).
        timeframe: TOTER PARAMETER (2026-07-12) — wird im Rumpf nie gelesen. Fossil aus der
            Zeit, als ein fehlender `tf` auf den Basis-Timeframe defaultete; seit dem
            tf-Pflichtfeld steht `tf` verbatim aus dem Spec. Der Aufrufer (Zeile 223) reicht
            ihn weiterhin durch; nicht entfernt, um den Aufrufer nicht anzufassen.
    """
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
            # GEÄNDERT: tf verbatim aus dem Spec ('same' oder tf-String) — kein Default
            # auf den Basis-Timeframe mehr; ein fehlender tf wäre schon in build_indicators
            # als Fehler aufgefallen.
            'tf': spec.get('tf'),
            'enabled': spec.get('enabled', True),
            'params': params,
            'data': inst,
        }
    return out
