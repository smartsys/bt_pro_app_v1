"""Pydantic-Schemas für Vault-Reindex-Lauf-Endpunkte.

Wird von GET /api/knowledge/runs und GET /api/knowledge/runs/{run_id} verwendet.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, computed_field


class KnowledgeRunSchema(BaseModel):
    """Einzelner Vault-Reindex-Lauf."""

    id: int
    job_id: str
    scope: str
    target_path: Optional[str]
    trigger: str
    status: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    duration_seconds: Optional[float]
    files_scanned: Optional[int]
    files_reindexed: Optional[int]
    files_deleted: Optional[int]
    chunks_written: Optional[int]
    error_message: Optional[str]
    created_at: datetime

    model_config = {'from_attributes': True}


class KnowledgeRunDetailSchema(KnowledgeRunSchema):
    """Einzel-Lauf-Response mit zusätzlichem chunks_per_second-Feld.

    chunks_per_second = chunks_written / duration_seconds,
    NULL wenn eines der beiden Felder fehlt oder duration_seconds == 0.
    """

    @computed_field  # type: ignore[prop-decorator]
    @property
    def chunks_per_second(self) -> Optional[float]:
        """Durchsatz in Chunks pro Sekunde."""
        if (
            self.chunks_written is not None
            and self.duration_seconds is not None
            and self.duration_seconds > 0
        ):
            return self.chunks_written / self.duration_seconds
        return None


class KnowledgeRunListSchema(BaseModel):
    """Listen-Response für GET /api/knowledge/runs."""

    runs: list[KnowledgeRunSchema]
    total: int
    limit: int
