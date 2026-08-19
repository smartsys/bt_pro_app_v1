"""
Pydantic Response-Models

API-Response-Format gemäß design-guide.md:
{"data": {"items": [...], "total": N, "limit": N, "offset": N}, "error": null}

GEÄNDERT: Ticket 28 — schemas/ ist jetzt ein Paket. Inhalte aus schemas.py hier
re-exportiert damit bestehende Imports (from services.api.schemas import ...) weiter
funktionieren. schemas.py bleibt als Referenz erhalten wird aber nicht mehr importiert
(Paket hat Vorrang vor gleichnamigem Modul).
"""

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict


class PaginatedData(BaseModel):
    """Paginierte Daten mit items, total, limit, offset."""
    items: list[Any]
    total: int
    limit: int
    offset: int


class ApiResponse(BaseModel):
    """Standard API-Response Wrapper."""
    data: Optional[PaginatedData] = None
    error: Optional[str] = None


class BacktestRunOut(BaseModel):
    """Backtest-Run für die API-Ausgabe."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_family: str
    strategy_name: str
    symbol: str
    exchange: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    n_combinations: int
    status: str
    # GEÄNDERT: Ticket 34 — Fehlermeldung fehlgeschlagener Runs an die UI durchreichen
    error_message: Optional[str] = None
    # GEÄNDERT: Chunk-Fortschritt für laufende Runs (NULL bei ungechunkt/Alt-Runs)
    current_chunk: Optional[int] = None
    total_chunks: Optional[int] = None
    # GEÄNDERT: Ticket 71 — Fortsetzungspunkt: Zahl der fertig gespeicherten Chunks.
    # > 0 heißt, ein abgebrochener Lauf trägt Teilergebnisse und ist fortsetzbar.
    completed_chunks: int = 0
    # GEÄNDERT: Ticket 60 — Selbstauskunft des Laufs ('usable' | 'no_signals' |
    # 'insufficient_history') mit lesbarem Grund, plus Ergebnis der Vorlauf-Prüfung.
    usability: Optional[str] = None
    usability_note: Optional[str] = None
    warmup_bars: Optional[int] = None
    warmup_required_bars: Optional[int] = None
    warmup_note: Optional[str] = None
    remarks: Optional[str] = None
    testset_run_id: Optional[int] = None
    # GEÄNDERT: Iteration-Verknüpfung (FK) ausgeben — Anker für "Runs zu Strategie+Version"
    iteration_id: Optional[int] = None
    # GEÄNDERT: Ticket 15 — _json-Suffix
    backtest_config_json: Optional[dict] = None
    indicators_config_json: Optional[dict] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class BacktestResultOut(BaseModel):
    """Backtest-Result für die API-Ausgabe."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    # GEÄNDERT: Ticket 15 — _json-Suffix
    actual_params_json: dict

    # Return-Metriken
    total_return_pct: Optional[float] = None
    benchmark_return_pct: Optional[float] = None

    # Risiko-Metriken
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    calmar_ratio: Optional[float] = None
    omega_ratio: Optional[float] = None

    # Drawdown
    max_drawdown_pct: Optional[float] = None

    # Trade-Metriken
    total_trades: Optional[int] = None
    # GEÄNDERT: Ticket 58 — am Fensterende offene Positionen. Die Trefferquote rechnet
    # über total_trades - open_trades; der Nenner gehört überall dorthin, wo sie steht.
    open_trades: Optional[int] = None
    # GEÄNDERT: Ticket 60 — Long/Short-Aufteilung (long_trades + short_trades = total_trades)
    # sowie der tatsächlich gerechnete Zeitraum und die Balkenzahl. NULL bei Alt-Results.
    long_trades: Optional[int] = None
    short_trades: Optional[int] = None
    start_index: Optional[datetime] = None
    end_index: Optional[datetime] = None
    total_duration: Optional[str] = None
    bar_count: Optional[int] = None
    win_rate_pct: Optional[float] = None
    profit_factor: Optional[float] = None
    expectancy: Optional[float] = None

    # Portfolio-Werte
    start_value: Optional[float] = None
    end_value: Optional[float] = None

    # Exposure
    position_coverage_pct: Optional[float] = None
