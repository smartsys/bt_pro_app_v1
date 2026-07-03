"""
SQLAlchemy Models

Tabellen: backtest_runs, backtest_results, backtest_trades, backtest_orders,
          backtest_positions, backtest_indicators, vault_chunks
Duplikat-Erkennung bei Results über MD5-Hash (params_hash).
"""

from datetime import datetime
from sqlalchemy import Column, Index, Integer, String, Float, DateTime, Text, Enum, JSON, Numeric, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB as _PgJSONB
from sqlalchemy.types import TypeDecorator, UserDefinedType
from sqlalchemy.orm import DeclarativeBase, relationship

try:
    from pgvector.sqlalchemy import Vector as _PgVector
    _PGVECTOR_AVAILABLE = True
except ImportError:
    _PGVECTOR_AVAILABLE = False


class _VectorCompat(TypeDecorator):
    """vector(1024) für PostgreSQL (via pgvector), JSON-Array-Fallback für SQLite.

    Ermöglicht Nutzung des pgvector-Typs in Produktion (PostgreSQL) und
    kompatiblen Fallback in Testumgebungen (SQLite In-Memory).
    """
    impl = JSON
    cache_ok = True

    def __init__(self, dim: int = 1024):
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql' and _PGVECTOR_AVAILABLE:
            return dialect.type_descriptor(_PgVector(self.dim))
        return dialect.type_descriptor(JSON())


class _JsonbCompat(TypeDecorator):
    """JSONB für PostgreSQL, JSON für andere Dialekte (z.B. SQLite in Tests).

    Ermöglicht JSONB-Semantik in Produktion (PostgreSQL) und kompatiblen
    Fallback in Testumgebungen (SQLite In-Memory).
    """
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(_PgJSONB())
        return dialect.type_descriptor(JSON())


class Base(DeclarativeBase):
    pass


class BacktestConfig(Base):
    """Wiederverwendbare Backtest-Konfiguration (Portfolio-Parameter, Zeitraum, etc.)."""
    __tablename__ = 'backtest_configs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    # Markt-Konfiguration
    symbol = Column(String(20), nullable=False, default='BTCUSDT')
    exchange = Column(String(50), nullable=False, default='binance')
    timeframe = Column(String(10), nullable=False, default='4h')

    # Zeitraum
    start = Column(String(20), nullable=False)
    end = Column(String(20), nullable=False)
    ohlc_start = Column(String(20), nullable=False)
    ohlc_end = Column(String(20), nullable=False)

    # Portfolio-Parameter
    size = Column(Float, nullable=False, default=100)
    size_type = Column(String(20), nullable=False, default='value')
    init_cash = Column(Float, nullable=False, default=100)
    fees = Column(Float, nullable=False, default=0.001)

    # GEÄNDERT: Schritt 3d — Format-Spalten (delta_format/time_delta_format) entfernt.
    # Die Stop-Formate leben jetzt im Meta-Key indicators_json['_stops']
    # (Eigentümer = IndicatorConfig), analog zu den 5 Stop-Werten (Schritt 3c).

    # Verwaltung
    # GEÄNDERT: is_default (exklusives Default-Flag) ersetzt durch is_favorite
    # (nicht-exklusiver Favoriten-Stern, analog zu Konzepten/Iterationen/Results).
    is_favorite = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=True)


class IndicatorConfig(Base):
    """Wiederverwendbare Indikator-Konfiguration als JSON."""
    __tablename__ = 'indicator_configs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    config_json = Column(JSON, nullable=False)
    is_default = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=True)
    # GEÄNDERT: Ticket 22 — lose Verknüpfung (kein FK) zu Strategy-Concept und -Iteration.
    # Löschen/Umbenennen der Ziele bricht nichts; Lookup auf Name/Version geschieht in der API.
    strategy_concept_id = Column(Integer, nullable=True)
    strategy_iteration_id = Column(Integer, nullable=True)


class StrategyConfig(Base):
    """Wiederverwendbare Strategie-Konfiguration (hartcodiert oder generisch).

    GEÄNDERT: Ticket 15 — type-Feld + strategy_config_json für generische Strategien;
    import_path jetzt nullable (nur bei type='hardcoded' gefüllt).
    XOR-Validierung in der API: entweder import_path (hardcoded) oder strategy_config_json (generic).
    """
    __tablename__ = 'strategy_configs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    strategy_family = Column(String(100), nullable=False)
    strategy_name = Column(String(100), nullable=False)
    # GEÄNDERT: Ticket 15 — 'hardcoded' oder 'generic'
    type = Column(String(20), nullable=False, default='hardcoded')
    # GEÄNDERT: Ticket 15 — nullable (nur bei hardcoded gefüllt)
    import_path = Column(String(500), nullable=True)
    # GEÄNDERT: Ticket 15 — Spec für generische Strategien (nur bei generic gefüllt)
    strategy_config_json = Column(JSON, nullable=True)
    is_default = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=True)


# ============================================================================
# Strategie-Konzepte und Iterationen (Ticket 09)
# ============================================================================

class StrategyConcept(Base):
    """Top-Level-Konzept einer Strategie (z.B. 'Teststrategie', 'Pullback #2').

    Trennt die Konzept-Ebene (Idee) von der Iterations-Ebene (ausführbare Spec).
    Obsidian-Pfade werden deterministisch aus slug abgeleitet (kein obsidian_slug-Feld).
    """
    __tablename__ = 'strategy_concepts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(100), nullable=False, unique=True)
    name = Column(String(200), nullable=False)
    category = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    # GEÄNDERT: Ticket 16 — obsidian_slug entfernt (Pfad wird aus slug abgeleitet)
    status = Column(String(20), nullable=False, default='active')
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    created_by = Column(String(120), nullable=True)
    # GEÄNDERT: High-Water-Mark der vergebenen Iterations-Nummern (nur steigend, kein Reuse nach Löschen)
    iteration_counter = Column(Integer, nullable=False, default=0, server_default='0')


class StrategyIteration(Base):
    """Versionierte Ausprägung eines Strategie-Konzepts (z.B. 'v2.0', 'dyn-v0.41').

    Iterationen sind immutable — strukturelle Änderungen erzeugen eine neue Iteration
    mit parent_iteration_id auf die Vorgänger-Iteration. spec_json enthält die
    ausführbare Spec (indicators, rules). NULL nur für Legacy-Einträge.
    Hinweis: spec_json enthält NICHT backtest_config — die liegt im BacktestRun.
    """
    __tablename__ = 'strategy_iterations'

    __table_args__ = (
        Index('idx_iterations_concept', 'concept_id'),
        Index('idx_iterations_parent', 'parent_iteration_id'),
        # GEÄNDERT: Ticket 12 — Index für Hash-Lookup (concept_id + spec_hash)
        Index('idx_iterations_spec_hash', 'concept_id', 'spec_hash'),
        UniqueConstraint('concept_id', 'version', name='uq_strategy_iterations_concept_version'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    concept_id = Column(Integer, ForeignKey('strategy_concepts.id'), nullable=False)
    # GEÄNDERT: Fortlaufende Integer-Nummer pro Konzept (ab 1), aus iteration_counter des Konzepts vergeben
    version = Column(Integer, nullable=False)
    # GEÄNDERT: Freier Anzeige-Name (optional); version ist die fortlaufende Nummer
    version_name = Column(String(100), nullable=True)
    spec_json = Column(_JsonbCompat, nullable=True)
    # GEÄNDERT: Ticket 12 — SHA-256-Kurzhash (16 Zeichen) über kanonisches spec_json für schnellen Lookup
    spec_hash = Column(String(16), nullable=True)
    # GEÄNDERT: Iteration kennzeichnet, ob sie auf hartcodierte oder generische Strategie verweist
    type = Column(String(20), nullable=False, default='generic')
    # GEÄNDERT: Code-Pfad der hartcodierten Strategie (nur bei type='hardcoded' gesetzt)
    import_path = Column(String(500), nullable=True)
    parent_iteration_id = Column(Integer, ForeignKey('strategy_iterations.id'), nullable=True)
    status = Column(String(20), nullable=False, default='active')
    # GEÄNDERT: Ticket 16 — obsidian_path entfernt (Pfad wird aus slug + version abgeleitet)
    # GEÄNDERT: Kurzbeschreibung der Iteration (was hat sich geändert?) — unabhängig von Obsidian
    description = Column(Text, nullable=True)
    # GEÄNDERT: Favoriten-Flag für Iterationen (Stern-Markierung im UI)
    is_favorite = Column(Boolean, nullable=False, default=False, server_default='false')
    # GEÄNDERT: Doku-Favoriten-Flag (roter Stern — unabhängig vom gelben Favorit)
    is_doc_favorite = Column(Boolean, nullable=False, default=False, server_default='false')
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    # GEÄNDERT: updated_at für Iterations-Edits (Sortierung "zuletzt aktualisiert")
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.now)
    created_by = Column(String(120), nullable=True)


class BacktestRun(Base):
    """Ein Backtest-Lauf mit Konfiguration und Metadaten."""
    __tablename__ = 'backtest_runs'

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Strategie-Info
    strategy_family = Column(String(100), nullable=False)
    strategy_name = Column(String(100), nullable=False)

    # Daten-Konfiguration
    symbol = Column(String(20), nullable=False)
    exchange = Column(String(50), nullable=False)
    timeframe = Column(String(10), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)

    # GEÄNDERT: Ticket 15 — _json-Suffix
    backtest_config_json = Column(JSON, nullable=False)
    indicators_config_json = Column(JSON, nullable=False)

    # Ergebnis-Zusammenfassung
    n_combinations = Column(Integer, nullable=False, default=0)
    status = Column(Enum('queued', 'running', 'completed', 'failed'), nullable=False, default='queued')
    error_message = Column(Text, nullable=True)

    # GEÄNDERT: Chunk-Fortschritt für laufende Runs (nur im gechunkten Modus gesetzt).
    # Der Spec-Runner meldet pro Chunk current_chunk/total_chunks an die DB, damit das
    # Frontend "Chunk 7/13" anzeigen kann. NULL bei ungechunkten oder Alt-Runs.
    current_chunk = Column(Integer, nullable=True)
    total_chunks = Column(Integer, nullable=True)

    # Bemerkung
    remarks = Column(Text, nullable=True)

    # Walk-Forward Verkettung
    parent_run_id = Column(Integer, nullable=True)
    parent_result_id = Column(Integer, nullable=True)
    selection_metric = Column(String(50), nullable=True)

    # GEÄNDERT: Spec-Runner-Version für Reproduzierbarkeit (Ticket 01)
    spec_runner_version = Column(String(20), nullable=True)

    # GEÄNDERT: TestSet-Run-Zuordnung (Ticket 04) — nullable, nur bei TestSet-Läufen gesetzt
    testset_run_id = Column(Integer, ForeignKey('testset_runs.id'), nullable=True)

    # GEÄNDERT: Ticket 10 — FK auf strategy_iterations
    iteration_id = Column(Integer, ForeignKey('strategy_iterations.id'), nullable=True)
    iteration = relationship('StrategyIteration', foreign_keys=[iteration_id])

    # GEÄNDERT: Herkunfts-Referenzen (lose, kein FK) — welche gespeicherte BacktestConfig/
    # IndicatorConfig diesen Run erzeugt hat. Ermöglicht im Playground-Result-Export die
    # Wiederherstellung der Dropdown-Auswahl. NULL bei ad-hoc-Runs ohne gespeicherte Config.
    backtest_config_id = Column(Integer, nullable=True)
    indicator_config_id = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    # GEÄNDERT: Start der tatsächlichen Verarbeitung (wird beim Wechsel auf 'running'
    # gesetzt). Dauer = completed_at - started_at = reine Rechenzeit ohne Queue-Wartezeit.
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index('ix_backtest_runs_testset_run_id', 'testset_run_id'),
        Index('idx_backtest_runs_iteration', 'iteration_id'),
    )


class BacktestResult(Base):
    """Ein Ergebnis pro Parameter-Kombination mit Metriken aus pf.stats()."""
    __tablename__ = 'backtest_results'

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=False)

    # MD5-Hash für Duplikat-Erkennung (run_id + actual_params)
    params_hash = Column(String(32), nullable=False)

    # GEÄNDERT: Ticket 15 — _json-Suffix
    actual_params_json = Column(JSON, nullable=False)

    # GEÄNDERT: Ticket 15 — _json-Suffix
    resolved_config_json = Column(JSON, nullable=True)

    # Zeitraum
    start_index = Column(DateTime, nullable=True)
    end_index = Column(DateTime, nullable=True)
    total_duration = Column(String(50), nullable=True)

    # Portfolio-Werte
    start_value = Column(Float, nullable=True)
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    end_value = Column(Float, nullable=True)

    # Return-Metriken
    total_return_pct = Column(Float, nullable=True)
    benchmark_return_pct = Column(Float, nullable=True)

    # Exposure
    position_coverage_pct = Column(Float, nullable=True)
    max_gross_exposure_pct = Column(Float, nullable=True)

    # Drawdown
    max_drawdown_pct = Column(Float, nullable=True)
    max_drawdown_duration = Column(String(50), nullable=True)

    # Orders/Trades
    total_orders = Column(Integer, nullable=True)
    total_fees_paid = Column(Float, nullable=True)
    total_trades = Column(Integer, nullable=True)

    # Trade-Metriken
    win_rate_pct = Column(Float, nullable=True)
    best_trade_pct = Column(Float, nullable=True)
    worst_trade_pct = Column(Float, nullable=True)
    avg_winning_trade_pct = Column(Float, nullable=True)
    avg_losing_trade_pct = Column(Float, nullable=True)
    avg_winning_trade_duration = Column(String(50), nullable=True)
    avg_losing_trade_duration = Column(String(50), nullable=True)
    profit_factor = Column(Float, nullable=True)
    expectancy = Column(Float, nullable=True)

    # Risiko-Metriken
    sharpe_ratio = Column(Float, nullable=True)
    calmar_ratio = Column(Float, nullable=True)
    omega_ratio = Column(Float, nullable=True)
    sortino_ratio = Column(Float, nullable=True)

    # GEÄNDERT: Annualisierte Metriken
    annualized_return = Column(Float, nullable=True)
    annualized_volatility = Column(Float, nullable=True)

    # GEÄNDERT: Erweiterte Risiko-Metriken
    downside_risk = Column(Float, nullable=True)
    tail_ratio = Column(Float, nullable=True)
    value_at_risk = Column(Float, nullable=True)
    cond_value_at_risk = Column(Float, nullable=True)

    # GEÄNDERT: Benchmark-relative Metriken
    alpha = Column(Float, nullable=True)
    beta = Column(Float, nullable=True)
    information_ratio = Column(Float, nullable=True)

    # GEÄNDERT: Trade-Qualität
    sqn = Column(Float, nullable=True)
    edge_ratio = Column(Float, nullable=True)

    # GEÄNDERT: Overfitting-Kontrolle
    deflated_sharpe_ratio = Column(Float, nullable=True)

    # GEÄNDERT: Berechnungsstufe (partial, chart, full)
    metrics_level = Column(String(10), nullable=False, default='partial')

    # GEÄNDERT: Spec-Runner-Version für Reproduzierbarkeit (Ticket 01)
    spec_runner_version = Column(String(20), nullable=True)

    # Favorit-Markierung
    is_favorite = Column(Integer, nullable=False, default=0)
    # GEÄNDERT: Doku-Favoriten-Markierung (roter Stern — unabhängig vom gelben Favorit)
    is_doc_favorite = Column(Integer, nullable=False, default=0)

    # GEÄNDERT: Bestwert-Kriterien, die dieses Result beim run-bestwerte-Lauf gewonnen hat.
    # Liste stabiler Keys (z.B. ["max_return", "sharpe_band"]), NICHT die Klartext-Labels.
    # Wird im Moment des roten Sterns festgehalten (Bänder sind run-relativ und nach dem
    # Löschen der übrigen Run-Results nicht mehr herleitbar). NULL = kein Bestwert / Alt-Result.
    # none_as_null=True: Python None wird als echtes SQL-NULL gespeichert (nicht als JSON-null),
    # damit "kein Kriterium" beim Sortieren korrekt ans Ende (nullslast) faellt.
    best_criteria_json = Column(JSON(none_as_null=True), nullable=True)

    # GEÄNDERT: Ticket 10 — FK auf strategy_iterations
    iteration_id = Column(Integer, ForeignKey('strategy_iterations.id'), nullable=True)
    iteration = relationship('StrategyIteration', foreign_keys=[iteration_id])

    # GEÄNDERT: Ticket 41 — vollständiger Config-Snapshot (backtest_config, indicators, rules)
    # Nullable für Bestandsschutz — Alt-Results bleiben als NULL erhalten
    full_config_snapshot_json = Column(JSON, nullable=True)


class BacktestJob(Base):
    """Hintergrund-Job für Recompute eines einzelnen Results."""
    __tablename__ = 'backtest_jobs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=False)
    result_id = Column(Integer, nullable=False)
    status = Column(Enum('queued', 'running', 'completed', 'failed'), nullable=False, default='queued')
    error_message = Column(Text, nullable=True)
    rq_job_id = Column(String(64), nullable=True)
    # Anzahl automatischer Neustarts durch den Reaper (services/api/reap_stale_jobs.py).
    # Nach insgesamt 3 Startversuchen (Original + 2 Neustarts) ohne Erfolg -> failed.
    retry_count = Column(Integer, nullable=False, server_default='0', default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class OhlcDownloadJob(Base):
    """Hintergrund-Job für OHLC-Download/Update via vbt.BinanceData."""
    __tablename__ = 'ohlc_download_jobs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_type = Column(String(20), nullable=False, default='download')  # 'download' | 'update'
    exchange = Column(String(20), nullable=False, default='binance')
    timeframe = Column(String(10), nullable=False)
    symbols = Column(JSON, nullable=False)
    start_date = Column(String(50), nullable=True)
    end_date = Column(String(50), nullable=True)
    status = Column(String(20), nullable=False, default='queued')
    message = Column(Text, nullable=True)
    # GEÄNDERT: Live-Fortschritt in Intervallen (Bars). intervals_total wird vor dem
    # Laden aus (end - start) / timeframe geschätzt, intervals_done zählt der Worker
    # pro abgerufenem Chunk hoch. Beide nullable - vor dieser Erweiterung angelegte
    # Jobs bleiben NULL; das Frontend zeigt dann nur den Status.
    intervals_total = Column(Integer, nullable=True)
    intervals_done = Column(Integer, nullable=True)
    rq_job_id = Column(String(64), nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class BacktestParam(Base):
    """Parameter-Werte pro Result für Analyse-Queries."""
    # GEÄNDERT: Ticket 13 — Tabelle backtest_params -> backtest_result_params
    __tablename__ = 'backtest_result_params'

    id = Column(Integer, primary_key=True, autoincrement=True)
    result_id = Column(Integer, nullable=False)
    param_name = Column(String(100), nullable=False)
    param_value = Column(Float, nullable=True)


class BacktestEquity(Base):
    """Equity-Kurve pro Zeitpunkt (nur bei n_combinations == 1)."""
    # GEÄNDERT: Ticket 13 — Tabelle backtest_equity -> backtest_result_equity
    __tablename__ = 'backtest_result_equity'

    id = Column(Integer, primary_key=True, autoincrement=True)
    result_id = Column(Integer, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    value = Column(Float, nullable=True)


class BacktestTrade(Base):
    """Ein einzelner Trade (nur bei n_combinations == 1)."""
    # GEÄNDERT: Ticket 13 — Tabelle backtest_trades -> backtest_result_trades
    __tablename__ = 'backtest_result_trades'

    id = Column(Integer, primary_key=True, autoincrement=True)
    result_id = Column(Integer, nullable=False)
    exit_trade_id = Column(Integer, nullable=False)
    position_id = Column(Integer, nullable=True)
    direction = Column(Enum('Long', 'Short'), nullable=False, default='Long')
    status = Column(Enum('Open', 'Closed'), nullable=False, default='Closed')
    size = Column(Float, nullable=False)
    entry_order_id = Column(Integer, nullable=True)
    entry_index = Column(DateTime, nullable=False)
    avg_entry_price = Column(Float, nullable=False)
    entry_fees = Column(Float, nullable=True)
    exit_order_id = Column(Integer, nullable=True)
    exit_index = Column(DateTime, nullable=True)
    avg_exit_price = Column(Float, nullable=True)
    exit_fees = Column(Float, nullable=True)
    pnl = Column(Float, nullable=True)
    return_pct = Column(Float, nullable=True)


class BacktestOrder(Base):
    """Eine einzelne Order (nur bei n_combinations == 1)."""
    # GEÄNDERT: Ticket 13 — Tabelle backtest_orders -> backtest_result_orders
    __tablename__ = 'backtest_result_orders'

    id = Column(Integer, primary_key=True, autoincrement=True)
    result_id = Column(Integer, nullable=False)
    order_id = Column(Integer, nullable=False)
    signal_index = Column(DateTime, nullable=True)
    creation_index = Column(DateTime, nullable=True)
    fill_index = Column(DateTime, nullable=True)
    size = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    fees = Column(Float, nullable=True)
    side = Column(Enum('Buy', 'Sell'), nullable=False)
    type = Column(String(50), nullable=True)
    stop_type = Column(String(50), nullable=True)


class BacktestPosition(Base):
    """Eine einzelne Position (nur bei n_combinations == 1)."""
    # GEÄNDERT: Ticket 13 — Tabelle backtest_positions -> backtest_result_positions
    __tablename__ = 'backtest_result_positions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    result_id = Column(Integer, nullable=False)
    position_id = Column(Integer, nullable=False)
    direction = Column(Enum('Long', 'Short'), nullable=False, default='Long')
    status = Column(Enum('Open', 'Closed'), nullable=False, default='Closed')
    size = Column(Float, nullable=False)
    entry_order_id = Column(Integer, nullable=True)
    entry_index = Column(DateTime, nullable=False)
    avg_entry_price = Column(Float, nullable=False)
    entry_fees = Column(Float, nullable=True)
    exit_order_id = Column(Integer, nullable=True)
    exit_index = Column(DateTime, nullable=True)
    avg_exit_price = Column(Float, nullable=True)
    exit_fees = Column(Float, nullable=True)
    pnl = Column(Float, nullable=True)
    return_pct = Column(Float, nullable=True)


class BacktestIndicator(Base):
    """Indikator-Werte pro Zeitpunkt (nur bei n_combinations == 1). Generisch für alle Indikator-Typen."""
    # GEÄNDERT: Ticket 13 — Tabelle backtest_indicators -> backtest_result_indicators
    __tablename__ = 'backtest_result_indicators'

    id = Column(Integer, primary_key=True, autoincrement=True)
    result_id = Column(Integer, nullable=False)
    indicator_name = Column(String(100), nullable=False, comment='z.B. sma, ema, supertrend')
    indicator_output = Column(String(100), nullable=False, comment='z.B. result, direction, trend')
    timestamp = Column(DateTime, nullable=False)
    value = Column(Float, nullable=True)


class ChartPlaygroundSetup(Base):
    """Gespeichertes Chart-Playground-Setup — vier separate JSON-Spalten.

    GEÄNDERT: Ticket 15 — altes config_json aufgeteilt in:
    - backtest_config_json: Markt/Zeitraum/Portfolio-Block
    - indicators_config_json: Indikator-Dict (gleiche Struktur wie BacktestRun)
    - strategy_config_json: Rules-Block {entry, exit}
    - ui_state_json: Playground-spezifisch (show_candles, Farben etc.)
    """
    __tablename__ = 'chart_playground_setups'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    # GEÄNDERT: Ticket 15 — vier neue Spalten statt config_json
    backtest_config_json = Column(JSON, nullable=False)
    indicators_config_json = Column(JSON, nullable=False)
    strategy_config_json = Column(JSON, nullable=False)
    ui_state_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=True)


# ============================================================================
# Test-Sets (Ticket 02)
# ============================================================================

class TestSet(Base):
    """Benannte Liste von BacktestConfig-IDs als Vergleichs-Anker für TestSet-Runs."""
    __tablename__ = 'testsets'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    # GEÄNDERT: Ticket 15 — _json-Suffix; JSONB für bessere Index-/Query-Performance
    backtest_config_ids_json = Column(_JsonbCompat, nullable=False)
    # GEÄNDERT: Opt-in-Schalter — nur bei True wird nach einem TestSet-Lauf ein
    # LeaderboardEntry erstellt. Default False (bewusstes Aktivieren nötig).
    leaderboard_enabled = Column(Boolean, nullable=False, default=False, server_default='false')
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    created_by = Column(String(120), nullable=True)


# ============================================================================
# TestSet-Runs und Leaderboard (Ticket 03)
# ============================================================================

class TestSetRun(Base):
    """Operativer Sammel-Datensatz für einen TestSet-Lauf (N parallele Backtest-Runs).

    Bündelt mehrere BacktestRuns unter einem TestSet und verfolgt den Gesamtstatus.
    Kann nach Cleanup gelöscht werden — langlebige Daten liegen im LeaderboardEntry.
    """
    __tablename__ = 'testset_runs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    # GEÄNDERT: kein FK mehr — TestSetRuns sind lose an das TestSet gekoppelt
    # (wie LeaderboardEntry.testset_id). Löschen eines TestSets blockiert nicht
    # und lässt die operativen Läufe unangetastet.
    testset_id = Column(Integer, nullable=False)
    strategy_family = Column(String(100), nullable=False)
    strategy_name = Column(String(100), nullable=False)
    # GEÄNDERT: Ticket 15 — kein FK mehr, JSON inline
    indicators_config_json = Column(_JsonbCompat, nullable=False, default=dict)

    # Status via CHECK-Constraint (kein SQLAlchemy-Enum-Typ — explizite Entscheidung Ticket 03)
    status = Column(String(20), nullable=False, default='queued')

    n_runs_total = Column(Integer, nullable=False)
    n_runs_completed = Column(Integer, nullable=False, default=0)

    # Zielbild 6.5: Herkunft des Triggers (z.B. "user:tom" | "agent:claude-...")
    triggered_by = Column(String(120), nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.now)
    completed_at = Column(DateTime, nullable=True)
    created_by = Column(String(120), nullable=True)


class LeaderboardEntry(Base):
    """Langlebiger Leaderboard-Eintrag mit Snapshots für Reproduzierbarkeit.

    Bleibt erhalten, auch wenn die operativen TestSetRun- und BacktestRun-Daten
    nach einem Cleanup gelöscht werden. Die drei Snapshots (testset_snapshot,
    indicator_config_snapshot, strategy_snapshot) sind Source of Truth.
    """
    __tablename__ = 'leaderboard_entries'

    __table_args__ = (
        UniqueConstraint('testset_run_id', name='uq_leaderboard_testset_run'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    testset_id = Column(Integer, nullable=False)

    # Nullable: operative Tabelle darf gelöscht werden
    testset_run_id = Column(Integer, nullable=True, unique=True)

    strategy_family = Column(String(100), nullable=False)
    strategy_name = Column(String(100), nullable=False)
    indicator_config_id = Column(Integer, nullable=True)
    spec_runner_version = Column(String(20), nullable=True)

    # Aggregate (nullable — werden in Ticket 06 befüllt)
    total_return_avg = Column(Numeric(12, 4), nullable=True)
    total_return_sum = Column(Numeric(12, 4), nullable=True)
    max_drawdown_avg = Column(Numeric(12, 4), nullable=True)
    sharpe_avg = Column(Numeric(12, 4), nullable=True)
    configs_total = Column(Integer, nullable=False)
    configs_passed = Column(Integer, nullable=True)  # NULL solange kein Goal-Filter
    filter_breached = Column(Boolean, nullable=True)

    # GEÄNDERT: Ticket 15 — _json-Suffix; Snapshots (Source of Truth für Reproduzierbarkeit nach Cleanup)
    testset_snapshot_json = Column(_JsonbCompat, nullable=False)
    indicator_config_snapshot_json = Column(_JsonbCompat, nullable=True)
    strategy_snapshot_json = Column(_JsonbCompat, nullable=False)
    winning_result_ids_json = Column(_JsonbCompat, nullable=False)

    # Info-Felder
    hint = Column(Text, nullable=True)
    executive_summary = Column(Text, nullable=True)
    mini_report = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.now)


# ============================================================================
# Vault-Vektorisierung (Ticket 24)
# ============================================================================

class VaultChunk(Base):
    """Ein vektorisierter Chunk aus dem Obsidian-Trading-Vault.

    Speichert Text-Chunks mit ihren Embeddings (bge-m3, 1024-dim) für
    semantisches Wissens-Retrieval. Scope: konfigurierbarer Vault, Prefix 30_Trading/.
    Inkrementeller Reindex über mtime-Vergleich pro vault_path.
    """
    __tablename__ = 'vault_chunks'

    __table_args__ = (
        # GEÄNDERT: Ticket 24 — Unique-Constraint verhindert doppelte Chunks bei Reindex
        UniqueConstraint('vault_path', 'chunk_index', name='uq_vault_chunks_path_index'),
        # GEÄNDERT: Ticket 24 — B-Tree-Index für inkrementellen Reindex (alte Chunks löschen)
        Index('ix_vault_chunks_vault_path', 'vault_path'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Relativer Pfad ab 30_Trading/, z.B. strategies/teststrategie/iterations/1/teststrategie-1.md
    vault_path = Column(String(1024), nullable=False)
    # 0-basierter Chunk-Index innerhalb derselben Datei

    chunk_index = Column(Integer, nullable=False)
    # Überschriften-Pfad, z.B. "Iterations > v0.41 > Lessons" (NULL bei Frontmatter-only)
    heading_path = Column(String(1024), nullable=True)
    # Reiner Chunk-Text inkl. Code-Blöcken (leer für Sentinel-Rows)
    # GEÄNDERT: Ticket 33 — nullable=True erlaubt leere Sentinel-Rows für Stub-Dateien
    content = Column(Text, nullable=True)
    # Kompletter Frontmatter-Block der Quelldatei (redundant pro Chunk, vereinfacht Filter-Queries)
    frontmatter_json = Column(_JsonbCompat, nullable=True)
    # mtime der Quelldatei zum Indexier-Zeitpunkt (für inkrementellen Reindex)
    mtime = Column(DateTime, nullable=False)
    # GEÄNDERT: Ticket 32 — SHA1-Hash des Datei-Inhalts (für Content-Hash-Skip)
    file_sha1 = Column(String(40), nullable=False, default="")
    # bge-m3-Embedding (1024-dim); NULL für Sentinel-Rows (Stub-Dateien ohne chunkbaren Content)
    # GEÄNDERT: Ticket 33 — nullable=True erlaubt Sentinel-Rows ohne Embedding
    embedding = Column(_VectorCompat(1024), nullable=True)
    indexed_at = Column(DateTime, nullable=False, default=datetime.now)


# ============================================================================
# Vault-Reindex-Job-Historie (Ticket 28)
# ============================================================================

class VaultReindexRun(Base):
    """Protokoll-Eintrag für jeden Vault-Reindex-Lauf.

    Jeder Lauf — periodisch (scheduler-Container) oder manuell (POST /api/knowledge/reindex) —
    wird hier festgehalten. Status-Lifecycle: queued -> running -> success | failed.
    """
    __tablename__ = 'vault_reindex_runs'

    __table_args__ = (
        # Index für Listen-Queries sortiert nach Erstellzeit
        Index('ix_vault_reindex_runs_started_at', 'started_at'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Von rq/arq generierte Job-ID
    job_id = Column(String(255), nullable=False, unique=True)
    # 'full' oder 'single-file'
    scope = Column(String(50), nullable=False)
    # Bei 'single-file': relativer Vault-Pfad; sonst NULL
    target_path = Column(String(1024), nullable=True)
    # Woher der Job kam: 'api', 'scheduler', 'cli'
    trigger = Column(String(50), nullable=False)
    # queued -> running -> success | failed
    status = Column(String(50), nullable=False, default='queued')
    # Gesetzt beim Beginn der Job-Ausführung
    started_at = Column(DateTime, nullable=True)
    # Gesetzt am Ende (success oder failed)
    finished_at = Column(DateTime, nullable=True)
    # Laufzeit in Sekunden (finished_at - started_at)
    duration_seconds = Column(Float, nullable=True)
    # Ergebnis-Felder aus dem Indexer
    files_scanned = Column(Integer, nullable=True)
    files_reindexed = Column(Integer, nullable=True)
    files_deleted = Column(Integer, nullable=True)
    chunks_written = Column(Integer, nullable=True)
    # Bei 'failed': die Exception-Message
    error_message = Column(Text, nullable=True)
    # GEÄNDERT: Ticket 34 — reindexierte und gelöschte Vault-Pfade pro Lauf
    # Format: {"reindexed": [...], "deleted": [...]}; NULL wenn Lauf abgebrochen
    files_changed = Column(_JsonbCompat, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
