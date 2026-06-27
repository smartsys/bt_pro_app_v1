"""Pydantic-Schemas für GET /api/knowledge/stats Endpoint (Ticket 30).

Response-Struktur:
  - index: Aggregat-Werte aus vault_chunks (Anzahl, Größe, Zeitstempel)
  - runs: Aggregat-Werte aus vault_reindex_runs (Counts, Erfolge, Durchschnitte)
  - top_paths_by_chunks: TOP 10 Dateipfade nach Chunk-Anzahl
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class KnowledgeIndexStats(BaseModel):
    """Statistiken über den Vektor-Index (vault_chunks)."""

    chunk_count: int
    file_count: int
    vault_size_bytes: int
    embedding_dim: int
    embedding_size_bytes_est: Optional[int]
    avg_chunks_per_file: Optional[float]
    last_indexed_at: Optional[datetime]
    oldest_indexed_at: Optional[datetime]


class KnowledgeRunsStats(BaseModel):
    """Statistiken über Reindex-Läufe (vault_reindex_runs)."""

    total: int
    by_status: dict[str, int]
    by_trigger: dict[str, int]
    last_run_at: Optional[datetime]
    last_success_at: Optional[datetime]
    last_failure_at: Optional[datetime]
    avg_duration_seconds_last_10: Optional[float]
    avg_chunks_per_second_last_10: Optional[float]


class KnowledgeTopPathEntry(BaseModel):
    """Ein Eintrag in der Top-Pfade-Liste."""

    vault_path: str
    chunks: int


class KnowledgeStatsResponse(BaseModel):
    """Gesamt-Response für GET /api/knowledge/stats."""

    index: KnowledgeIndexStats
    runs: KnowledgeRunsStats
    top_paths_by_chunks: list[KnowledgeTopPathEntry]
