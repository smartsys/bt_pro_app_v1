"""Pydantic-Schemas für den Vault-Datei-Endpunkt.

Wird von GET /api/knowledge/files verwendet.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class KnowledgeFileSchema(BaseModel):
    """Aggregierte Datei-Zeile aus vault_chunks.

    Eine Zeile pro vault_path mit aggregierten Metadaten.
    """

    vault_path: str
    chunk_count: int
    last_indexed: Optional[datetime]
    source_mtime: Optional[datetime]
    tags: list[str]


class KnowledgeFilesResponse(BaseModel):
    """Listen-Response für GET /api/knowledge/files."""

    files: list[KnowledgeFileSchema]
    total: int
    limit: int
    offset: int
