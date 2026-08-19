"""
SQLAlchemy Models

Tabellen: backtest_runs, backtest_results, backtest_trades, backtest_orders,
          backtest_positions, backtest_indicators, vault_chunks
Duplikat-Erkennung bei Results über MD5-Hash (params_hash).
"""

from datetime import datetime
from sqlalchemy import Column, Index, Integer, String, Float, DateTime, Text, Enum, JSON, Numeric, Boolean, ForeignKey, UniqueConstraint, event
from sqlalchemy.dialects.postgresql import JSONB as _PgJSONB
from sqlalchemy.types import TypeDecorator, UserDefinedType
from sqlalchemy.orm import DeclarativeBase, relationship
# GEÄNDERT: Ticket 56 — Attribut-Historie für den Schreibschutz auf Phase-1-Feldern
from sqlalchemy.orm.attributes import get_history

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
        # GEÄNDERT (Nachtrag Ticket 88): Fehlt pgvector unter PostgreSQL, fiel der Typ
        # bisher still auf JSON zurück. Die Spalte ist dort aber als 'vector' angelegt —
        # jeder Schreibzugriff scheiterte danach in der Datenbank, mit einem Fehler, der
        # nicht mehr auf die fehlende Abhängigkeit zeigte. Der JSON-Weg ist allein für
        # SQLite gedacht (Unit-Tests ohne PostgreSQL).
        if dialect.name == 'postgresql':
            if not _PGVECTOR_AVAILABLE:
                raise RuntimeError(
                    'pgvector ist nicht installiert, die Spalte vault_chunks.embedding '
                    'hat in PostgreSQL aber den Typ vector(1024). Ohne das Paket gibt es '
                    'keinen tragfähigen Ersatz — bitte pgvector in die Umgebung aufnehmen, '
                    'in der dieses Modell benutzt wird.'
                )
            return dialect.type_descriptor(_PgVector(self.dim))
        return dialect.type_descriptor(JSON())


class _JsonbCompat(TypeDecorator):
    """JSONB für PostgreSQL, JSON für andere Dialekte (z.B. SQLite in Tests).

    Ermöglicht JSONB-Semantik in Produktion (PostgreSQL) und kompatiblen
    Fallback in Testumgebungen (SQLite In-Memory).

    GEÄNDERT: Ticket 56 — optionales ``none_as_null``. Standard bleibt False (Python
    ``None`` landet als JSON-``null`` in der Spalte, unverändertes Verhalten für alle
    Bestandsspalten). Mit ``none_as_null=True`` wird ``None`` als echtes SQL-NULL
    geschrieben — nötig überall dort, wo „leer" per ``IS NULL`` abfragbar sein muss.
    """
    impl = JSON
    cache_ok = True

    def __init__(self, none_as_null: bool = False):
        super().__init__()
        self.none_as_null = none_as_null

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(_PgJSONB(none_as_null=self.none_as_null))
        return dialect.type_descriptor(JSON(none_as_null=self.none_as_null))


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
    # GEÄNDERT: Ticket 59 — slippage als regulärer Portfolio-Parameter (analog fees).
    # Default 0.0 entspricht dem bisherigen impliziten VBT-Default, kein stiller
    # Verhaltenswechsel für Bestandsconfigs.
    slippage = Column(Float, nullable=False, default=0.0, server_default='0')
    # GEÄNDERT: Ticket 59 — stop_exit_price/stop_order_type persistiert statt nur
    # transient im Playground-Formular. None = VBT-Default (keine erzwungene
    # Voreinstellung), dieselbe Konvention wie im Playground-JS.
    stop_exit_price = Column(String(20), nullable=True)
    stop_order_type = Column(String(20), nullable=True)

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
    # GEÄNDERT: Ticket 66 — Entwicklungsziel des Konzepts. goal_json (strukturierte
    # Zielgrößen, frei formuliert, kein festes Schema) + goal_prompt (Original-Auftrag
    # im Wortlaut). Beide nullable, kein Gate — reine Anzeige/Speicherung/Übernahme.
    goal_json = Column(_JsonbCompat, nullable=True)
    goal_prompt = Column(Text, nullable=True)
    # GEÄNDERT: Ticket 92 — Zähler der Lite-Sondierungen dieses Konzepts (nur steigend,
    # kein Zurücksetzen). Macht den Suchumfang sichtbar, der nicht im Raster steht;
    # wird ausgewiesen, nicht bewertet (keine Schwelle, keine Verrechnung in die DSR).
    probe_count = Column(Integer, nullable=False, default=0, server_default='0')


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


class IterationLog(Base):
    """Append-only Denkprotokoll einer Iteration (Ticket 67).

    Freitext-Eintrag, der festhält, warum ein Versuch unternommen wurde und was
    aus dem Ergebnis geschlossen wird. Bewusst kein Update-/Delete-Pfad — die
    Nachvollziehbarkeit entsteht strukturell durch Unveränderlichkeit, nicht
    durch Disziplin. run_id ist eine lose Referenz ohne ForeignKey (Runs sind
    löschbar, der Log-Eintrag bleibt gültig).
    """
    __tablename__ = 'iteration_logs'

    __table_args__ = (
        Index('idx_iteration_logs_iteration', 'iteration_id'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    iteration_id = Column(Integer, ForeignKey('strategy_iterations.id'), nullable=False)
    run_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    text = Column(Text, nullable=False)


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

    # GEÄNDERT: Ticket 71 — Fortsetzungspunkt. Zählt die von vorn her vollständig
    # gerechneten UND gespeicherten Chunks; wird in derselben Transaktion wie die
    # Results des Chunks geschrieben und kann deshalb nie mehr behaupten, als in der
    # Datenbank steht. Ein fortgesetzter Lauf überspringt genau diese Chunks, ein
    # Neustart (Rerun, löscht alle Results) setzt den Wert auf 0 zurück.
    completed_chunks = Column(Integer, nullable=False, server_default='0', default=0)

    # GEÄNDERT: Ticket 60 — Selbstauskunft des Laufs. 'usable' | 'no_signals' |
    # 'insufficient_history'; NULL bei Alt-Runs und bei Runs, die nie bis zur
    # Bewertung kamen (failed). Der lesbare Grund steht in usability_note. Der Lauf
    # bleibt in jedem Fall vollständig erhalten — Kennzeichnung, kein Ausblenden.
    usability = Column(String(32), nullable=True)
    usability_note = Column(Text, nullable=True)

    # GEÄNDERT: Ticket 60 — Vorlauf-Prüfung beim Run-Start (siehe
    # user_data/strategies/generic/warmup.py). warmup_bars = tatsächlich vorhandener
    # Vorlauf zwischen ohlc_start und start in Basis-Balken, warmup_required_bars =
    # längste konfigurierte Indikator-Periode, warmup_note = lesbare Meldung.
    warmup_bars = Column(Integer, nullable=True)
    warmup_required_bars = Column(Integer, nullable=True)
    warmup_note = Column(Text, nullable=True)

    # GEÄNDERT: Ticket 54 — Annualisierungsfaktor des Laufs, genau der Wert, den VBT
    # selbst benutzt (`ReturnsAccessor.ann_factor` = Jahresfrequenz / Balkenfrequenz).
    # Der gespeicherte `backtest_results.sharpe_ratio` ist annualisiert; die Deflated
    # Sharpe Ratio braucht den Sharpe je Balken. Mit diesem Faktor ist die Rückrechnung
    # `SR_bar = SR_ann / sqrt(ann_factor)` exakt (VBT schließt mit
    # `mean / std * sqrt(ann_factor)`, am Quelltext von `sharpe_ratio_1d_nb` gelesen).
    # NULL bei Läufen von vor diesem Ticket.
    ann_factor = Column(Float, nullable=True)

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
        # GEÄNDERT: Ticket 60 — Filter "welche Läufe sind nicht verwertbar?"
        Index('idx_backtest_runs_usability', 'usability'),
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
    # GEÄNDERT: Ticket 60 — start_index/end_index/total_duration sind seit Ticket 58 das
    # tatsächlich gerechnete Handelsfenster start..end (nicht das Datenfenster ab
    # ohlc_start). Seit Ticket 64 füllt sie _extract_metrics für jeden Lauf.
    start_index = Column(DateTime, nullable=True)
    end_index = Column(DateTime, nullable=True)
    total_duration = Column(String(50), nullable=True)
    # GEÄNDERT: Ticket 60 — Zahl der Balken im gerechneten Handelsfenster
    # (pf.wrapper.shape[0]). NULL bei Alt-Results vor Ticket 60.
    bar_count = Column(Integer, nullable=True)

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
    # GEÄNDERT: Ticket 58 — Anzahl der am Ende des Handelsfensters (start..end) offenen
    # Positionen. Sie gehen marktbewertet in total_return_pct/end_value ein, aber NICHT
    # in win_rate_pct und profit_factor (die rechnen über geschlossene Trades).
    # total_trades - open_trades = Grundgesamtheit von Trefferquote und Profitfaktor.
    # NULL bei Results, die vor Ticket 58 entstanden sind (spec_runner_version < 3.0.0).
    open_trades = Column(Integer, nullable=True)
    # GEÄNDERT: Ticket 60 — Long/Short-Aufteilung je Result (trades.direction_long/
    # .direction_short.count()), wie total_trades inklusive einer am Fensterende
    # offenen Position. long_trades + short_trades = total_trades. NULL bei
    # Alt-Results vor Ticket 60.
    long_trades = Column(Integer, nullable=True)
    short_trades = Column(Integer, nullable=True)

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

    # GEÄNDERT: Ticket 64 — Verteilungsform der Renditen je Kombination. Bausteine der
    # Deflated Sharpe Ratio, ohne die sie nicht nachrechenbar ist (Ticket 54).
    # kurtosis ist die ROHE Wölbung (Normalverteilung rund 3), nicht die
    # Excess-Wölbung. NULL bei Results, die vor Ticket 64 entstanden sind.
    skew = Column(Float, nullable=True)
    kurtosis = Column(Float, nullable=True)

    # GEÄNDERT: Overfitting-Kontrolle
    deflated_sharpe_ratio = Column(Float, nullable=True)

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
    # GEÄNDERT: Favoriten-Stern (gelb) — sortiert Favoriten in Listen und im
    # Test-Set-Dropdown der Start-Maske nach oben. 0/1 wie bei BacktestConfig.
    is_favorite = Column(Integer, nullable=False, default=0, server_default='0')
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
    # GEÄNDERT: Ticket 62 — diese Zusage gilt seit der Migration
    # 0019_drop_testset_runs_fk auch in der Datenbank. Bis dahin trug
    # `0001_baseline.sql` hier fälschlich den Fremdschlüssel
    # fk_testset_runs_testset_id (Modell/DB-Drift, Ursache des HTTP-500 aus
    # Ticket 61). Diesen Constraint nicht versehentlich wieder einführen.
    # Ergänzung: Auf Anwendungsebene zieht delete_testset (siehe
    # repository_testsets.py) die Zusage inzwischen nach — es löscht ausschließlich
    # die TestSet-Zeile. Hängen noch Läufe dran, fragt die Oberfläche einmal nach
    # (HTTP 409 ohne force); bestätigt der User, bleiben Läufe, Backtest-Runs und
    # Results bestehen und ihre testset_id zeigt auf ein gelöschtes TestSet.
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
# Befund je Testset-Lauf (Ticket 56)
# ============================================================================

class FindingImmutableError(Exception):
    """Ein bereits angelegter Befund sollte in einem geschützten Feld geändert werden.

    Wird vom ORM-Wächter unter dieser Klasse ausgelöst (siehe
    ``_block_testset_run_finding_phase1_updates``). Bewusst ein eigener Fehlertyp
    und keine stille Rücknahme der Änderung — Projekt-Prinzip „Altlasten sichtbar
    machen".
    """


class TestSetRunFinding(Base):
    """Befund eines Testset-Laufs — Soll beim Start, Ist beim Abschluss (Ticket 56).

    Zweiphasiger, unveränderlicher Datensatz: Phase 1 legt Kontext und Soll beim
    Start an, Phase 2 ergänzt die Ist-Werte genau einmal beim Abschluss. Eine
    Deutung darf nachträglich dazukommen — als Freitext, getrennt von den Zahlen
    und ausdrücklich als Interpretation gekennzeichnet.

    **Kein Verdict.** Es gibt bewusst kein ``passed``, keinen Gesamtscore, keine
    Ampel und keinen Sortier-Rang. Sobald es eine solche Zahl gäbe, würde danach
    sortiert — und damit wäre das entfernte Goal-Gate unter anderem Namen zurück.

    **Warum eigene Tabelle und keine Spalte am TestSetRun:** Der ``TestSetRun`` ist
    per Entwurf wegwerfbar (siehe dessen Docstring), der Befund muss das Aufräumen
    aber überleben — seine Historie ist der eigentliche Wert.

    **Warum ohne Fremdschlüssel:** Alle Kontext-Referenzen (``testset_run_id``,
    ``iteration_id``, ``concept_id``, ``testset_id``, ``indicator_config_id``) sind
    lose Referenzen ohne FK — genau wie ``LeaderboardEntry.testset_id`` und
    ``LeaderboardEntry.testset_run_id``, die aus demselben Grund ohne FK stehen: Der
    langlebige Datensatz darf nicht daran hängen, ob die operativen Objekte noch
    existieren. Ein FK auf ``testset_runs.id`` würde entweder das Löschen blockieren
    oder den Befund mitreißen; beides widerspricht dem Akzeptanzkriterium „ein Befund
    überlebt das Aufräumen". Der Kontext wird deshalb hier selbst festgehalten und
    nicht über den ``TestSetRun`` hergeleitet.

    **Kein Unique-Constraint auf ``testset_run_id``:** Ein erneuter Lauf erzeugt einen
    neuen Befund; überschrieben wird nie.

    Fehlende Werte bleiben NULL und tragen ihren Grund im zugehörigen ``*_reason``-
    bzw. ``*_missing_reason``-Feld — nicht mit 0 gefüllt und nicht stillschweigend
    weggelassen.
    """
    __tablename__ = 'testset_run_findings'

    __table_args__ = (
        Index('idx_testset_run_findings_iteration', 'iteration_id'),
        Index('idx_testset_run_findings_testset_run', 'testset_run_id'),
        # GEÄNDERT: Ticket 85 — Index für die Konzept-Detailseite (by-concept-Route)
        Index('idx_testset_run_findings_concept', 'concept_id'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    # --- Kontext (Phase 1, echte Spalten — danach wird gesucht) ---
    # Lose Referenz: der TestSetRun darf gelöscht werden, der Befund bleibt lesbar.
    testset_run_id = Column(Integer, nullable=True)
    iteration_id = Column(Integer, nullable=False)
    # Herkunft des Soll-Schnappschusses (goal_json hängt am Konzept, nicht an der Iteration).
    concept_id = Column(Integer, nullable=True)
    testset_id = Column(Integer, nullable=False)
    indicator_config_id = Column(Integer, nullable=True)
    spec_runner_version = Column(String(20), nullable=True)
    # Zeitpunkt der Anlage = Startzeitpunkt des Laufs.
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    # --- Soll (Phase 1) ---
    # Schnappschuss von strategy_concepts.goal_json. Bleibt JSON, weil goal_json per
    # Ticket 66 bewusst kein festes Schema hat und sich nicht in Spalten zerlegen lässt.
    goal_snapshot_json = Column(_JsonbCompat(none_as_null=True), nullable=True)
    # Grund, wenn kein Soll vorliegt (z.B. "kein Ziel am Konzept hinterlegt").
    goal_missing_reason = Column(Text, nullable=True)
    # Stabile Keys der Bestwert-Kriterien (Single Source: best_criteria_labels.py).
    best_criteria_json = Column(_JsonbCompat, nullable=False, default=list)
    # Geplante Rastergröße als echte Spalten (ohne JSON-Auspacken abfragbar).
    planned_n_runs = Column(Integer, nullable=False)
    planned_combos_per_run = Column(Integer, nullable=True)
    planned_combos_total = Column(Integer, nullable=True)
    planned_grid_reason = Column(Text, nullable=True)

    # --- Ist (Phase 2, wird beim Abschluss genau einmal ergänzt) ---
    scope_json = Column(_JsonbCompat(none_as_null=True), nullable=True)
    candidates_json = Column(_JsonbCompat(none_as_null=True), nullable=True)
    robustness_json = Column(_JsonbCompat(none_as_null=True), nullable=True)
    benchmarks_json = Column(_JsonbCompat(none_as_null=True), nullable=True)
    warnings_json = Column(_JsonbCompat(none_as_null=True), nullable=True)
    # Vorgesehen, aber bis auf Weiteres nicht befüllt: es gibt noch keinen markierten
    # Holdout-Zeitraum (Ticket 56, Out of Scope). Bleibt NULL statt False.
    holdout_touched = Column(Boolean, nullable=True)
    # Abschlusszeitpunkt der zweiten Phase. Gesetzt = Befund geschlossen.
    closed_at = Column(DateTime, nullable=True)

    # --- Deutung (nachträglich, getrennt von den Zahlen) ---
    interpretation_text = Column(Text, nullable=True)
    interpretation_at = Column(DateTime, nullable=True)


# Geschützte Phase-1-Felder: Kontext und Soll sind ab der Anlage unveränderlich.
# Absichtlich nicht enthalten sind die Ist-Felder (Phase 2 ergänzt sie einmal) und
# die Deutungs-Felder (nachträglich pflegbar).
_FINDING_PHASE1_COLUMNS: tuple = (
    'testset_run_id',
    'iteration_id',
    'concept_id',
    'testset_id',
    'indicator_config_id',
    'spec_runner_version',
    'created_at',
    'goal_snapshot_json',
    'goal_missing_reason',
    'best_criteria_json',
    'planned_n_runs',
    'planned_combos_per_run',
    'planned_combos_total',
    'planned_grid_reason',
)


# Geschützte Phase-2-Felder: die Ist-Werte werden beim Abschluss genau einmal gesetzt.
# Der Schutz greift erst, wenn `closed_at` bereits stand — vorher ist der Befund offen
# und Phase 2 darf schreiben. Absichtlich nicht enthalten sind die Deutungs-Felder: die
# Deutung wird nachträglich ergänzt, ohne die Zahlen zu berühren.
_FINDING_PHASE2_COLUMNS: tuple = (
    'scope_json',
    'candidates_json',
    'robustness_json',
    'benchmarks_json',
    'warnings_json',
    'holdout_touched',
    'closed_at',
)


def _finding_changed_fields(target, fields: tuple) -> list:
    """Sammelt die Feldnamen, deren Wert sich in diesem Flush tatsächlich ändert.

    Args:
        target: Die zu aktualisierende TestSetRunFinding-Instanz.
        fields: Zu prüfende Spaltennamen.

    Returns:
        Namen der geänderten Felder in der Reihenfolge von ``fields``.
    """
    changed: list[str] = []
    for field in fields:
        history = get_history(target, field)
        if not history.has_changes():
            continue
        old_value = history.deleted[0] if history.deleted else None
        new_value = history.added[0] if history.added else None
        if old_value != new_value:
            changed.append(field)
    return changed


@event.listens_for(TestSetRunFinding, 'before_update')
def _block_testset_run_finding_phase1_updates(mapper, connection, target) -> None:
    """Weist jede Änderung an Kontext oder Soll eines bestehenden Befunds ab.

    Der Schutz sitzt am ORM-Mapper und nicht in einer Hilfsfunktion, damit er für
    jeden Schreibweg gilt, der über eine Session läuft — auch für Code, der die
    Repository-Funktionen umgeht. Nachträgliches Nachschärfen der Vorregistrierung
    ist damit eine Eigenschaft des Systems und keine Anweisung.

    Nicht abgedeckt sind rohe SQL-UPDATEs an der Session vorbei; dafür gibt es im
    Projekt bewusst keinen Schreibpfad.

    Args:
        mapper: Der auslösende SQLAlchemy-Mapper (von der Event-API vorgegeben).
        connection: Die aktive Verbindung (von der Event-API vorgegeben).
        target: Die zu aktualisierende TestSetRunFinding-Instanz.

    Raises:
        FindingImmutableError: Wenn mindestens ein geschütztes Feld geändert wurde.
    """
    changed = _finding_changed_fields(target, _FINDING_PHASE1_COLUMNS)
    if changed:
        raise FindingImmutableError(
            f'Befund {target.id}: Kontext und Soll sind nach dem Start unveränderlich. '
            f'Abgewiesene Felder: {", ".join(changed)}.'
        )


@event.listens_for(TestSetRunFinding, 'before_update')
def _block_testset_run_finding_phase2_updates(mapper, connection, target) -> None:
    """Weist jede Änderung an den Ist-Werten eines geschlossenen Befunds ab.

    Phase 2 schreibt genau einmal: solange ``closed_at`` leer ist, darf der Abschluss
    seine Zahlen setzen; sobald es steht, ist der Befund geschlossen und jeder weitere
    Ist-Schreibvorgang wird abgewiesen — kein stilles Überschreiben.

    Maßgeblich ist der Wert von ``closed_at`` **vor** diesem Flush. Der Abschluss selbst
    setzt die Ist-Felder und ``closed_at`` in einem Zug; für ihn war der Befund vorher
    offen und der Schutz greift noch nicht. Der zweite Versuch trifft ein gesetztes
    ``closed_at`` und läuft auf.

    Die Deutungs-Felder (``interpretation_text``/``interpretation_at``) sind bewusst
    nicht geschützt — sie werden nachträglich ergänzt, ohne die Zahlen zu berühren.

    Args:
        mapper: Der auslösende SQLAlchemy-Mapper (von der Event-API vorgegeben).
        connection: Die aktive Verbindung (von der Event-API vorgegeben).
        target: Die zu aktualisierende TestSetRunFinding-Instanz.

    Raises:
        FindingImmutableError: Wenn ein Ist-Feld eines geschlossenen Befunds
            geändert wurde.
    """
    closed_history = get_history(target, 'closed_at')
    if closed_history.has_changes():
        previous_closed_at = closed_history.deleted[0] if closed_history.deleted else None
    else:
        previous_closed_at = target.closed_at
    if previous_closed_at is None:
        return

    changed = _finding_changed_fields(target, _FINDING_PHASE2_COLUMNS)
    if changed:
        raise FindingImmutableError(
            f'Befund {target.id}: der Befund ist seit {previous_closed_at} geschlossen, '
            f'die Ist-Werte sind unveränderlich. Abgewiesene Felder: '
            f'{", ".join(changed)}. Ein erneuter Lauf erzeugt einen neuen Befund.'
        )


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


# ============================================================================
# Signifikanztest je Kandidat (Ticket 79)
# ============================================================================

# Zulässige Methoden. `permutation` = Monte-Carlo-Permutationstest gegen
# strukturlose Preisreihen (Nullmodell), `bootstrap` = Resampling der eigenen
# Trade-Renditen (Unsicherheitsband, kein Nullmodell).
SIGNIFICANCE_METHODS: tuple = ('permutation', 'bootstrap')

# Status-Lebenslauf. `completed`/`failed` sind Endzustände — ab dann ist der
# Datensatz unveränderlich.
SIGNIFICANCE_TERMINAL_STATUS: tuple = ('completed', 'failed')


class SignificanceTestImmutableError(Exception):
    """Ein abgeschlossener Signifikanztest sollte geändert werden.

    Eigener Fehlertyp statt stiller Rücknahme — wie ``FindingImmutableError``.
    Ein neuer Test erzeugt einen neuen Datensatz; überschrieben wird nie.
    """


class SignificanceTest(Base):
    """Ein statistischer Signifikanztest für genau einen Kandidaten (Ticket 79).

    Ein Kandidat ist ein Result: Iteration × eingefrorene Parameterkombination ×
    BacktestConfig. Zwei Methoden teilen sich diese Tabelle, weil beide dieselbe
    Frage-Form beantworten („wie belastbar ist diese Zahl?") und dieselben
    Kontext-, Status- und Ergebnis-Felder brauchen:

    * ``permutation`` — die Strategie läuft auf N synthetischen Preisreihen
      (Bar-Permutation, ``user_data/utils/analysis/synthetic_series.py``). Der
      p-Wert sagt, wie oft ein so gutes Ergebnis aus strukturlosen Daten entsteht.
    * ``bootstrap`` — Resampling der Trade-Renditen des Kandidaten liefert
      Konfidenzbänder. **Kein Nullmodell**, also auch kein p-Wert.

    **Kein Verdict.** Es gibt bewusst kein ``passed``, keine Ampel, keinen Score
    und keine Güte-Sortierung — dieselbe Regel wie bei DSR und Befund. Ein p-Wert
    wird berichtet, nicht angewandt.

    **Warum ohne Fremdschlüssel:** ``result_id``, ``run_id`` und ``iteration_id``
    sind lose Referenzen — genau wie bei ``TestSetRunFinding`` und
    ``LeaderboardEntry``. Rechenspuren (Results, Runs) werden regelmäßig
    aufgeräumt; der Test muss das überleben, sonst wäre seine Historie wertlos.
    Deshalb trägt der Datensatz seinen Kontext selbst: ``params_json`` hält die
    eingefrorene Kombination, ``config_snapshot_json`` Symbol, Timeframe,
    Zeitraum und Portfolio-Kern.

    **Unveränderlich nach Abschluss:** Sobald ``status`` auf ``completed`` oder
    ``failed`` steht, weist der ORM-Wächter jede weitere Änderung ab.
    """
    __tablename__ = 'significance_tests'

    __table_args__ = (
        Index('idx_significance_tests_result', 'result_id'),
        Index('idx_significance_tests_created', 'created_at'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    # --- Kontext (lose Referenzen, kein FK) ---
    result_id = Column(Integer, nullable=False)
    run_id = Column(Integer, nullable=True)
    iteration_id = Column(Integer, nullable=True)
    # Eingefrorene Parameterkombination des Kandidaten (aus resolved_config_json
    # plus die aufgelösten Stops) — der Test bleibt ohne das Result deutbar.
    params_json = Column(_JsonbCompat(none_as_null=True), nullable=True)
    # Symbol, Exchange, Timeframe, Handelsfenster, Portfolio-Kern.
    config_snapshot_json = Column(_JsonbCompat(none_as_null=True), nullable=True)

    # --- Methode und Aufbau ---
    method = Column(String(20), nullable=False)
    n_iterations = Column(Integer, nullable=False)
    seed = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default='queued')
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    duration_seconds = Column(Float, nullable=True)

    # --- Ergebnis ---
    # Echte Werte des Kandidaten je Metrik: {"sharpe_ratio": 2.07, ...}
    real_values_json = Column(_JsonbCompat(none_as_null=True), nullable=True)
    # VOLLSTÄNDIGE Wertelisten je Metrik: {"sharpe_ratio": [...N Zahlen...], ...}.
    # Absichtlich nicht auf Kennwerte eingekocht — nur so sind Nachanalysen
    # möglich, und N Zahlen sind billig.
    distribution_json = Column(_JsonbCompat(none_as_null=True), nullable=True)
    # Kennwerte je Metrik (mean/median/p05/p95/max) plus p-Wert bzw.
    # Konfidenzbänder, dazu der Anteil der Läufe ohne Trades.
    summary_json = Column(_JsonbCompat(none_as_null=True), nullable=True)


@event.listens_for(SignificanceTest, 'before_update')
def _block_completed_significance_test_updates(mapper, connection, target) -> None:
    """Weist jede Änderung an einem abgeschlossenen Signifikanztest ab.

    Maßgeblich ist der Status **vor** diesem Flush: der Abschluss selbst setzt
    Ergebnisse und ``status`` in einem Zug und läuft durch; jeder weitere
    Schreibversuch trifft einen Endzustand und wird abgewiesen. Der Wächter sitzt
    am ORM-Mapper, damit er für jeden Schreibweg über eine Session gilt — nicht
    nur für die Repository-Funktionen.

    Args:
        mapper: Der auslösende SQLAlchemy-Mapper (von der Event-API vorgegeben).
        connection: Die aktive Verbindung (von der Event-API vorgegeben).
        target: Die zu aktualisierende SignificanceTest-Instanz.

    Raises:
        SignificanceTestImmutableError: Wenn der Test bereits abgeschlossen war.
    """
    status_history = get_history(target, 'status')
    if status_history.has_changes():
        previous_status = status_history.deleted[0] if status_history.deleted else None
    else:
        previous_status = target.status
    if previous_status not in SIGNIFICANCE_TERMINAL_STATUS:
        return
    raise SignificanceTestImmutableError(
        f'Signifikanztest {target.id}: der Test ist mit Status "{previous_status}" '
        f'abgeschlossen und damit unveränderlich. Ein erneuter Test erzeugt einen '
        f'neuen Datensatz.'
    )


# ============================================================================
# Walk-Forward-Fold-Kette (Ticket 82)
# ============================================================================

# Status-Lebenslauf. `completed`/`failed` sind Endzustände — ab dann ist der
# Datensatz unveränderlich.
WALK_FORWARD_CHAIN_TERMINAL_STATUS: tuple = ('completed', 'failed')

# Felder, die während `running` geschrieben werden dürfen: das Anhängen von Folds
# und der Abschluss. Alles andere (Plan, Kontext, Anlagezeitpunkt) steht ab der
# Anlage fest — das ist die Vorregistrierung, strukturell statt disziplinarisch.
WALK_FORWARD_CHAIN_MUTABLE_COLUMNS: tuple = (
    'folds_json',
    'aggregate_json',
    'method_note',
    'status',
    'error_message',
    'completed_at',
)

# Geschützte Felder: Plan und Kontext der Vorregistrierung.
WALK_FORWARD_CHAIN_FROZEN_COLUMNS: tuple = (
    'anchor_run_id',
    'iteration_id',
    'concept_id',
    'config_snapshot_json',
    'plan_json',
    'created_at',
)


class WalkForwardChainImmutableError(Exception):
    """An einer Kette sollte ein geschütztes Feld geändert werden.

    Eigener Fehlertyp statt stiller Rücknahme — wie ``FindingImmutableError`` und
    ``SignificanceTestImmutableError``. Eine neue Kette erzeugt einen neuen
    Datensatz; überschrieben wird nie.
    """


class WalkForwardChain(Base):
    """Eine Walk-Forward-Fold-Kette: Plan, Fold-Ergebnisse, Gesamtbewertung (Ticket 82).

    Die Kette führt N-mal nacheinander „auf einem Zeitfenster optimieren → Sieger
    einfrieren → auf dem nächsten, ungesehenen Zeitfenster testen" aus. Der
    vollständige Plan (Fold-Zahl, Fensterlängen, konkrete Fold-Fenster,
    Auswahlkriterium) wird beim Anlegen festgeschrieben und danach stur vollzogen
    — das ist die Vorregistrierung.

    **Kein Verdict.** Es gibt bewusst kein ``passed``, keine Ampel, keinen Score
    und keine Güte-Sortierung — dieselbe Regel wie bei DSR, Befund und
    Signifikanztest. Die Kette misst, sie urteilt nicht.

    **Warum ohne Fremdschlüssel:** ``anchor_run_id``, ``iteration_id`` und
    ``concept_id`` sind lose Referenzen — genau wie bei ``TestSetRunFinding`` und
    ``SignificanceTest``. Die Ketten-Läufe und -Results sind per Entwurf
    wegwerfbar; die Kette muss ihr Aufräumen überleben. Deshalb trägt sie alle
    tragenden Werte als Kopie: ``config_snapshot_json`` den Kontext,
    ``plan_json`` den Plan, ``folds_json`` je Fold die eingefrorene
    Sieger-Kombination samt IS- und OOS-Kennzahlen, ``aggregate_json`` die
    Gesamtbewertung.

    **Unveränderlich nach Abschluss:** Sobald ``status`` auf ``completed`` oder
    ``failed`` steht, weist der ORM-Wächter jede weitere Änderung ab. Während
    ``running`` sind ausschließlich das Anhängen von Folds und der Abschluss
    erlaubt; ``folds_json`` wächst dabei streng append-only.
    """
    __tablename__ = 'walk_forward_chains'

    __table_args__ = (
        Index('idx_walk_forward_chains_iteration', 'iteration_id'),
        Index('idx_walk_forward_chains_anchor', 'anchor_run_id'),
        Index('idx_walk_forward_chains_created', 'created_at'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    # --- Kontext (lose Referenzen, kein FK) ---
    anchor_run_id = Column(Integer, nullable=False)
    iteration_id = Column(Integer, nullable=True)
    concept_id = Column(Integer, nullable=True)
    # Symbol, Exchange, Timeframe, Portfolio-Kern, Anker-Fenster.
    config_snapshot_json = Column(_JsonbCompat(none_as_null=True), nullable=True)

    # --- Plan (Vorregistrierung, beim Anlegen geschrieben) ---
    # Fold-Zahl, IS-/OOS-Fensterlänge, die konkreten Fold-Fenster als Datumsliste,
    # Auswahlkriterium (Metrik, Richtung, Trade-Floor), Metrik-Stufe der IS-Läufe.
    plan_json = Column(_JsonbCompat(none_as_null=True), nullable=False)

    # --- Folds (append-only nach Fold-Abschluss) ---
    # Liste je Fold: Index, IS-Fenster + IS-Run-ID, Sieger-Kopie mit IS-Wert des
    # Kriteriums, OOS-Fenster + OOS-Run-ID + OOS-Result-ID, OOS-Kennzahlen.
    # Ein Fold ohne Sieger steht mit ``winner: null`` und ``no_winner_reason`` drin.
    folds_json = Column(_JsonbCompat(none_as_null=True), nullable=True)

    # --- Abschluss ---
    aggregate_json = Column(_JsonbCompat(none_as_null=True), nullable=True)
    # Fester Methodenhinweis zur Verkettung statt Signal-Splice.
    method_note = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default='running')
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    completed_at = Column(DateTime, nullable=True)


def _walk_forward_chain_changed_columns(target, columns: tuple) -> list:
    """Sammelt die Feldnamen, deren Wert sich in diesem Flush tatsächlich ändert.

    Args:
        target: Die zu aktualisierende WalkForwardChain-Instanz.
        columns: Zu prüfende Spaltennamen.

    Returns:
        Namen der geänderten Felder in der Reihenfolge von ``columns``.
    """
    changed: list[str] = []
    for column in columns:
        history = get_history(target, column)
        if not history.has_changes():
            continue
        old_value = history.deleted[0] if history.deleted else None
        new_value = history.added[0] if history.added else None
        if old_value != new_value:
            changed.append(column)
    return changed


@event.listens_for(WalkForwardChain, 'before_update')
def _block_completed_walk_forward_chain_updates(mapper, connection, target) -> None:
    """Weist jede Änderung an einer abgeschlossenen Kette ab.

    Maßgeblich ist der Status **vor** diesem Flush: der Abschluss selbst setzt
    Aggregat und ``status`` in einem Zug und läuft durch; jeder weitere
    Schreibversuch trifft einen Endzustand und wird abgewiesen.

    Args:
        mapper: Der auslösende SQLAlchemy-Mapper (von der Event-API vorgegeben).
        connection: Die aktive Verbindung (von der Event-API vorgegeben).
        target: Die zu aktualisierende WalkForwardChain-Instanz.

    Raises:
        WalkForwardChainImmutableError: Wenn die Kette bereits abgeschlossen war.
    """
    status_history = get_history(target, 'status')
    if status_history.has_changes():
        previous_status = status_history.deleted[0] if status_history.deleted else None
    else:
        previous_status = target.status
    if previous_status not in WALK_FORWARD_CHAIN_TERMINAL_STATUS:
        return
    raise WalkForwardChainImmutableError(
        f'Walk-Forward-Kette {target.id}: die Kette ist mit Status "{previous_status}" '
        f'abgeschlossen und damit unveränderlich. Ein erneuter Lauf erzeugt eine neue '
        f'Kette.'
    )


@event.listens_for(WalkForwardChain, 'before_update')
def _block_walk_forward_chain_plan_updates(mapper, connection, target) -> None:
    """Weist jede Änderung an Plan oder Kontext einer laufenden Kette ab.

    Der Plan ist die Vorregistrierung: Fold-Fenster und Auswahlkriterium stehen ab
    der Anlage fest. Nachjustieren nach einem Zwischenblick scheitert damit am
    System und nicht an der Disziplin.

    Args:
        mapper: Der auslösende SQLAlchemy-Mapper (von der Event-API vorgegeben).
        connection: Die aktive Verbindung (von der Event-API vorgegeben).
        target: Die zu aktualisierende WalkForwardChain-Instanz.

    Raises:
        WalkForwardChainImmutableError: Wenn ein geschütztes Feld geändert wurde.
    """
    changed = _walk_forward_chain_changed_columns(
        target, WALK_FORWARD_CHAIN_FROZEN_COLUMNS,
    )
    if changed:
        raise WalkForwardChainImmutableError(
            f'Walk-Forward-Kette {target.id}: Plan und Kontext sind ab der Anlage '
            f'unveränderlich (Vorregistrierung). Abgewiesene Felder: '
            f'{", ".join(changed)}.'
        )


@event.listens_for(WalkForwardChain, 'before_update')
def _block_walk_forward_chain_fold_rewrites(mapper, connection, target) -> None:
    """Erzwingt, dass ``folds_json`` ausschließlich wächst (append-only).

    Ein bereits angehängter Fold darf nicht nachträglich umgeschrieben oder
    entfernt werden: die bisherige Liste muss Präfix der neuen bleiben.

    Args:
        mapper: Der auslösende SQLAlchemy-Mapper (von der Event-API vorgegeben).
        connection: Die aktive Verbindung (von der Event-API vorgegeben).
        target: Die zu aktualisierende WalkForwardChain-Instanz.

    Raises:
        WalkForwardChainImmutableError: Wenn ein bestehender Fold geändert oder
            entfernt wurde.
    """
    history = get_history(target, 'folds_json')
    if not history.has_changes():
        return
    old_folds = (history.deleted[0] if history.deleted else None) or []
    new_folds = (history.added[0] if history.added else None) or []
    if len(new_folds) >= len(old_folds) and new_folds[:len(old_folds)] == old_folds:
        return
    raise WalkForwardChainImmutableError(
        f'Walk-Forward-Kette {target.id}: bereits angehängte Folds sind '
        f'unveränderlich — Folds werden ausschließlich angehängt '
        f'({len(old_folds)} vorhanden, {len(new_folds)} übergeben).'
    )
