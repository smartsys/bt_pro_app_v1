"""
JSON-API Endpoints für Vault-Wissenssuche und Reindizierung

GET  /api/knowledge/search       — Semantische Vektorsuche über vault_chunks
POST /api/knowledge/reindex      — Manuellen Reindex-Job einreihen (async, 202)
GET  /api/knowledge/runs         — Liste der Reindex-Läufe (Ticket 28)
GET  /api/knowledge/runs/{id}    — Einzel-Lauf mit chunks_per_second (Ticket 28)
GET  /api/knowledge/files        — Aggregierte Datei-Liste aus vault_chunks (Ticket 29)
GET  /api/knowledge/stats        — Aggregierte Index- und Lauf-Statistiken (Ticket 30)
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from services.api.redis_conn import get_redis_connection, RECOMPUTE_QUEUE_NAME
from services.api.schemas_knowledge_runs import (
    KnowledgeRunSchema,
    KnowledgeRunDetailSchema,
    KnowledgeRunListSchema,
)
# GEÄNDERT: Ticket 29 — Datei-Listen-Schema importiert
from services.api.schemas.knowledge_files import (
    KnowledgeFileSchema,
    KnowledgeFilesResponse,
)
# GEÄNDERT: Ticket 30 — Stats-Schema importiert
from services.api.schemas.knowledge_stats import (
    KnowledgeIndexStats,
    KnowledgeRunsStats,
    KnowledgeTopPathEntry,
    KnowledgeStatsResponse,
)
from services.vbt.knowledge.embedding import embed
from user_data.utils.database.db import get_session
from user_data.utils.database.models import VaultReindexRun

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/knowledge', tags=['knowledge'])


# ============================================================================
# Pydantic-Schemas
# ============================================================================

class KnowledgeChunkResult(BaseModel):
    """Ein einzelnes Suchergebnis aus vault_chunks."""

    vault_path: str
    chunk_index: int
    heading_path: Optional[str]
    content: str
    frontmatter: Optional[dict]
    similarity: float


class KnowledgeSearchResponse(BaseModel):
    """Antwort-Schema für GET /api/knowledge/search."""

    results: list[KnowledgeChunkResult]
    query: str
    total: int


class KnowledgeReindexRequest(BaseModel):
    """Optionaler Request-Body für POST /api/knowledge/reindex.

    Wenn path gesetzt ist, wird nur diese Datei reindiziert.
    Andernfalls wird ein vollständiger Vault-Reindex durchgeführt.
    """

    path: Optional[str] = None


class KnowledgeReindexResponse(BaseModel):
    """Antwort-Schema für POST /api/knowledge/reindex."""

    job_id: str
    scope: str  # "full" | "single-file"
    target_path: Optional[str]


# ============================================================================
# Endpoints
# ============================================================================

@router.get('/search', response_model=KnowledgeSearchResponse)
def search_knowledge(
    q: str = Query(..., description='Suchtext'),
    k: int = Query(default=10, ge=1, le=50, description='Top-K Treffer (max 50)'),
    tag: list[str] = Query(default=[], description='Filter auf Frontmatter-Tags (ODER-Verknüpfung)'),
    path_prefix: Optional[str] = Query(default=None, description='Filter auf vault_path-Präfix'),
) -> KnowledgeSearchResponse:
    """Semantische Vektorsuche über vault_chunks.

    Wandelt den Query-Text in einen Embedding-Vektor (bge-m3, 1024-dim) um
    und führt eine Cosine-Distance-Suche gegen die HNSW-indizierten Embeddings
    durch. Optionale Filter auf Tags (JSONB-Array, ODER) und Pfad-Präfix.

    Args:
        q: Suchtext.
        k: Anzahl der Treffer (1-50).
        tag: Optionale Tag-Filter (Treffer muss mindestens einen enthalten).
        path_prefix: Optionaler Präfix-Filter auf vault_path.

    Returns:
        KnowledgeSearchResponse mit sortierten Treffern (Similarity DESC).
    """
    try:
        query_vector = embed(q)
    except Exception as exc:
        logger.error('Embedding-Fehler für Query %r: %s', q, exc)
        raise HTTPException(status_code=502, detail=f'Embedding-Backend nicht erreichbar: {exc}') from exc

    # pgvector erwartet String-Darstellung '[v1,v2,...]'
    vector_str = '[' + ','.join(str(v) for v in query_vector) + ']'

    with get_session() as session:
        from sqlalchemy import text as sa_text

        # WHERE-Klauseln dynamisch aufbauen
        # GEÄNDERT: Ticket 33 — Sentinel-Rows (embedding IS NULL) immer aus Suche ausschließen
        where_parts = ["embedding IS NOT NULL"]
        params: dict = {'vector': vector_str, 'k': k}

        if tag:
            # JSONB-Array-Check: frontmatter_json->'tags' enthält mindestens einen der Tags.
            # jsonb_array_elements_text + ANY() statt ?-Operator, da psycopg2 ? als
            # Positional-Platzhalter missinterpretiert.
            tag_clauses = []
            for i, t in enumerate(tag):
                param_name = f'tag_{i}'
                tag_clauses.append(
                    f"EXISTS ("
                    f"  SELECT 1 FROM jsonb_array_elements_text(frontmatter_json->'tags') AS elem"
                    f"  WHERE elem = :{param_name}"
                    f")"
                )
                params[param_name] = t
            where_parts.append('(' + ' OR '.join(tag_clauses) + ')')

        if path_prefix:
            where_parts.append('vault_path LIKE :path_prefix')
            params['path_prefix'] = path_prefix + '%'

        where_sql = ('WHERE ' + ' AND '.join(where_parts)) if where_parts else ''

        # CAST() statt ::-Syntax, da psycopg2 den ::-Operator als
        # benannten Parameter-Präfix missinterpretieret.
        sql = sa_text(f"""
            SELECT
                vault_path,
                chunk_index,
                heading_path,
                content,
                frontmatter_json,
                1 - (embedding <=> CAST(:vector AS vector)) AS similarity
            FROM vault_chunks
            {where_sql}
            ORDER BY embedding <=> CAST(:vector AS vector)
            LIMIT :k
        """)

        rows = session.execute(sql, params).fetchall()

    results = [
        KnowledgeChunkResult(
            vault_path=row.vault_path,
            chunk_index=row.chunk_index,
            heading_path=row.heading_path,
            content=row.content,
            frontmatter=row.frontmatter_json,
            similarity=float(row.similarity),
        )
        for row in rows
    ]

    return KnowledgeSearchResponse(results=results, query=q, total=len(results))


@router.post('/reindex', response_model=KnowledgeReindexResponse, status_code=202)
def trigger_reindex(body: Optional[KnowledgeReindexRequest] = None) -> KnowledgeReindexResponse:
    """Reiht einen Vault-Reindex-Job in die recompute-Queue ein.

    Antwortet sofort mit der Job-ID (Status 202). Der eigentliche Reindex
    läuft asynchron im Worker. Legt direkt nach dem Enqueue einen
    VaultReindexRun-Eintrag mit status='queued' an (Ticket 28).

    Args:
        body: Optionaler Request-Body. Wenn path gesetzt, nur diese Datei reindizieren.

    Returns:
        KnowledgeReindexResponse mit job_id, scope und target_path.
    """
    target_path: Optional[str] = None
    if body and body.path:
        target_path = body.path

    scope = 'single-file' if target_path else 'full'

    try:
        from rq import Queue  # noqa: PLC0415 — lazy import (rq fehlt im Windows-venv)
        q = Queue(RECOMPUTE_QUEUE_NAME, connection=get_redis_connection())
        job = q.enqueue(
            'services.api.worker_tasks.reindex_vault_chunk_job',
            target_path=target_path,
            trigger='api',
            job_timeout=600,
        )
    except Exception as exc:
        logger.error('Reindex-Job konnte nicht eingereiht werden: %s', exc)
        raise HTTPException(status_code=503, detail=f'Queue nicht erreichbar: {exc}') from exc

    # GEÄNDERT: Ticket 28 — Pre-Insert: Run sofort sichtbar mit status='queued'
    with get_session() as session:
        run_entry = VaultReindexRun(
            job_id=job.id,
            scope=scope,
            target_path=target_path,
            trigger='api',
            status='queued',
            created_at=datetime.now(),
        )
        session.add(run_entry)
        session.commit()

    logger.info('Reindex-Job eingereiht: job_id=%s scope=%s target_path=%s', job.id, scope, target_path)

    return KnowledgeReindexResponse(job_id=job.id, scope=scope, target_path=target_path)


# ============================================================================
# Endpoints: Reindex-Lauf-Historie (Ticket 28)
# ============================================================================

@router.get('/runs', response_model=KnowledgeRunListSchema)
def list_reindex_runs(
    limit: int = Query(default=50, ge=1, le=200, description='Maximale Anzahl Einträge'),
    status: Optional[str] = Query(default=None, description='Filter: queued | running | success | failed'),
    scope: Optional[str] = Query(default=None, description='Filter: full | single-file'),
) -> KnowledgeRunListSchema:
    """Liefert eine sortierte Liste der Vault-Reindex-Läufe.

    Args:
        limit: Maximale Anzahl Einträge (1-200, Default 50).
        status: Optionaler Status-Filter.
        scope: Optionaler Scope-Filter ('full' oder 'single-file').

    Returns:
        KnowledgeRunListSchema mit Läufen sortiert nach created_at DESC.
    """
    with get_session() as session:
        q = session.query(VaultReindexRun)
        if status is not None:
            q = q.filter(VaultReindexRun.status == status)
        if scope is not None:
            q = q.filter(VaultReindexRun.scope == scope)
        q = q.order_by(VaultReindexRun.created_at.desc()).limit(limit)
        runs = q.all()

    return KnowledgeRunListSchema(
        runs=[KnowledgeRunSchema.model_validate(r) for r in runs],
        total=len(runs),
        limit=limit,
    )


@router.get('/runs/{run_id}', response_model=KnowledgeRunDetailSchema)
def get_reindex_run(run_id: int) -> KnowledgeRunDetailSchema:
    """Liefert einen einzelnen Vault-Reindex-Lauf mit chunks_per_second.

    Args:
        run_id: DB-ID des VaultReindexRun-Eintrags.

    Returns:
        KnowledgeRunDetailSchema inkl. berechnetes chunks_per_second-Feld.

    Raises:
        HTTPException 404: Lauf nicht gefunden.
    """
    with get_session() as session:
        run = session.query(VaultReindexRun).filter(VaultReindexRun.id == run_id).first()
        if run is None:
            raise HTTPException(status_code=404, detail=f'Reindex-Lauf {run_id} nicht gefunden')
        return KnowledgeRunDetailSchema.model_validate(run)


# ============================================================================
# Endpoint: Indizierte Dateien (Ticket 29)
# ============================================================================

@router.get('/files', response_model=KnowledgeFilesResponse)
def list_knowledge_files(
    q: Optional[str] = Query(default=None, description='Substring-Suche auf vault_path'),
    tag: list[str] = Query(default=[], description='Tag-Filter (ODER-Verknüpfung, multi-value)'),
    limit: int = Query(default=100, ge=1, le=500, description='Maximale Anzahl Einträge'),
    offset: int = Query(default=0, ge=0, description='Offset für Pagination'),
) -> KnowledgeFilesResponse:
    """Liefert eine aggregierte Liste der indizierten Vault-Dateien.

    Jede Zeile repräsentiert eine vault_path-Datei mit aggregierten Werten
    aus vault_chunks: Chunk-Anzahl, letzter Indexier-Zeitpunkt, Quell-mtime,
    Tags aus frontmatter_json.

    Args:
        q: Optionale Substring-Suche auf vault_path (ILIKE).
        tag: Optionale Tag-Filter (Datei muss mindestens einen enthalten).
        limit: Maximale Anzahl Ergebnisse (1-500, Default 100).
        offset: Offset für Paginierung.

    Returns:
        KnowledgeFilesResponse mit paginierter Datei-Liste.
    """
    from sqlalchemy import text as sa_text

    # GEÄNDERT: Ticket 33 — Sentinel-Rows (embedding IS NULL) aus Datei-Listing ausschließen
    where_parts: list[str] = ["embedding IS NOT NULL"]
    params: dict = {'limit': limit, 'offset': offset}

    if q:
        where_parts.append('vault_path ILIKE :q_filter')
        params['q_filter'] = f'%{q}%'

    if tag:
        tag_clauses = []
        for i, t in enumerate(tag):
            param_name = f'tag_{i}'
            tag_clauses.append(
                f"EXISTS ("
                f"  SELECT 1 FROM jsonb_array_elements_text(frontmatter_json->'tags') AS elem"
                f"  WHERE elem = :{param_name}"
                f")"
            )
            params[param_name] = t
        where_parts.append('(' + ' OR '.join(tag_clauses) + ')')

    where_sql = ('WHERE ' + ' AND '.join(where_parts)) if where_parts else ''

    # Haupt-Query: GROUP BY vault_path mit Aggregaten
    sql = sa_text(f"""
        SELECT
            vault_path,
            COUNT(*) AS chunk_count,
            MAX(indexed_at) AS last_indexed,
            MAX(mtime) AS source_mtime,
            (
                SELECT array_agg(DISTINCT elem ORDER BY elem)
                FROM vault_chunks vc2
                CROSS JOIN jsonb_array_elements_text(vc2.frontmatter_json->'tags') AS elem
                WHERE vc2.vault_path = vault_chunks.vault_path
                  AND vc2.frontmatter_json IS NOT NULL
                  AND vc2.frontmatter_json->'tags' IS NOT NULL
            ) AS tags
        FROM vault_chunks
        {where_sql}
        GROUP BY vault_path
        ORDER BY MAX(indexed_at) DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """)

    # Gesamt-Anzahl (ohne Pagination)
    count_sql = sa_text(f"""
        SELECT COUNT(DISTINCT vault_path) AS total
        FROM vault_chunks
        {where_sql}
    """)

    with get_session() as session:
        rows = session.execute(sql, params).fetchall()
        count_params = {k: v for k, v in params.items() if k not in ('limit', 'offset')}
        total = session.execute(count_sql, count_params).scalar() or 0

    files = [
        KnowledgeFileSchema(
            vault_path=row.vault_path,
            chunk_count=int(row.chunk_count),
            last_indexed=row.last_indexed,
            source_mtime=row.source_mtime,
            tags=list(row.tags) if row.tags else [],
        )
        for row in rows
    ]

    return KnowledgeFilesResponse(
        files=files,
        total=int(total),
        limit=limit,
        offset=offset,
    )


# ============================================================================
# Endpoint: Knowledge-DB leeren (Ticket 33, Teil B)
# ============================================================================

class KnowledgeResetResponse(BaseModel):
    """Antwort-Schema für DELETE /api/knowledge/reset."""

    data: dict
    error: None = None


@router.delete('/reset', response_model=KnowledgeResetResponse)
def reset_knowledge_db() -> KnowledgeResetResponse:
    """Leert vault_chunks und vault_reindex_runs in einer Transaktion.

    Ermöglicht einen sauberen Neuaufbau des Wissens-Index.
    Kein Cascade-Delete an andere Tabellen — Scope ist genau diese zwei.

    Returns:
        KnowledgeResetResponse mit Anzahl der gelöschten Einträge.
    """
    from sqlalchemy import text as sa_text

    with get_session() as session:
        chunks_deleted = session.execute(
            sa_text("DELETE FROM vault_chunks RETURNING id")
        ).rowcount
        runs_deleted = session.execute(
            sa_text("DELETE FROM vault_reindex_runs RETURNING id")
        ).rowcount
        session.commit()

    logger.info(
        "[KNOWLEDGE-RESET] vault_chunks=%d, vault_reindex_runs=%d gelöscht",
        chunks_deleted,
        runs_deleted,
    )

    return KnowledgeResetResponse(
        data={
            "vault_chunks_deleted": chunks_deleted,
            "vault_reindex_runs_deleted": runs_deleted,
        }
    )


# ============================================================================
# Endpoint: Index- und Lauf-Statistiken (Ticket 30)
# ============================================================================

@router.get('/stats', response_model=KnowledgeStatsResponse)
def get_knowledge_stats() -> KnowledgeStatsResponse:
    """Liefert aggregierte Statistiken über den Vektor-Index und Reindex-Läufe.

    Aggregiert vault_chunks (Index-Größe, Datei-Anzahl, Zeitstempel) und
    vault_reindex_runs (Counts nach Status/Trigger, Durchschnittswerte der
    letzten 10 erfolgreichen Läufe) in einem einzigen Response.

    Returns:
        KnowledgeStatsResponse mit index, runs und top_paths_by_chunks.
    """
    from sqlalchemy import text as sa_text

    with get_session() as session:
        # --- Index-Aggregat ---
        # GEÄNDERT: Ticket 33 — Sentinel-Rows (embedding IS NULL) aus Statistik ausschließen
        index_row = session.execute(sa_text("""
            SELECT
                COUNT(*) FILTER (WHERE embedding IS NOT NULL)       AS chunk_count,
                COUNT(DISTINCT vault_path)                          AS file_count,
                COALESCE(SUM(octet_length(content)) FILTER (WHERE embedding IS NOT NULL), 0) AS vault_size_bytes,
                MAX(indexed_at)                                     AS last_indexed_at,
                MIN(indexed_at) FILTER (WHERE embedding IS NOT NULL) AS oldest_indexed_at
            FROM vault_chunks
        """)).fetchone()

        chunk_count = int(index_row.chunk_count) if index_row else 0
        file_count = int(index_row.file_count) if index_row else 0
        vault_size_bytes = int(index_row.vault_size_bytes) if index_row else 0

        avg_chunks_per_file: Optional[float] = None
        if file_count > 0:
            avg_chunks_per_file = round(chunk_count / file_count, 2)

        embedding_size_bytes_est: Optional[int] = None
        if chunk_count > 0:
            embedding_size_bytes_est = chunk_count * 1024 * 4

        index_stats = KnowledgeIndexStats(
            chunk_count=chunk_count,
            file_count=file_count,
            vault_size_bytes=vault_size_bytes,
            embedding_dim=1024,
            embedding_size_bytes_est=embedding_size_bytes_est,
            avg_chunks_per_file=avg_chunks_per_file,
            last_indexed_at=index_row.last_indexed_at if index_row else None,
            oldest_indexed_at=index_row.oldest_indexed_at if index_row else None,
        )

        # --- Runs-Aggregat: Counts nach Status ---
        status_rows = session.execute(sa_text("""
            SELECT status, COUNT(*) AS cnt
            FROM vault_reindex_runs
            GROUP BY status
        """)).fetchall()
        status_map: dict[str, int] = {'queued': 0, 'running': 0, 'success': 0, 'failed': 0}
        for row in status_rows:
            if row.status in status_map:
                status_map[row.status] = int(row.cnt)

        # --- Runs-Aggregat: Counts nach Trigger ---
        trigger_rows = session.execute(sa_text("""
            SELECT trigger, COUNT(*) AS cnt
            FROM vault_reindex_runs
            GROUP BY trigger
        """)).fetchall()
        trigger_map: dict[str, int] = {'api': 0, 'scheduler': 0, 'cli': 0}
        for row in trigger_rows:
            if row.trigger in trigger_map:
                trigger_map[row.trigger] = int(row.cnt)

        # --- Zeitstempel-Aggregat ---
        ts_row = session.execute(sa_text("""
            SELECT
                MAX(created_at)                                        AS last_run_at,
                MAX(finished_at) FILTER (WHERE status = 'success')    AS last_success_at,
                MAX(finished_at) FILTER (WHERE status = 'failed')     AS last_failure_at
            FROM vault_reindex_runs
        """)).fetchone()

        # --- Durchschnittswerte letzte 10 Erfolge ---
        avg_row = session.execute(sa_text("""
            SELECT
                AVG(duration_seconds)   AS avg_duration_seconds,
                AVG(
                    CASE
                        WHEN duration_seconds IS NOT NULL
                             AND duration_seconds > 0
                             AND chunks_written IS NOT NULL
                        THEN chunks_written::float / duration_seconds
                        ELSE NULL
                    END
                ) AS avg_chunks_per_second
            FROM (
                SELECT duration_seconds, chunks_written
                FROM vault_reindex_runs
                WHERE status = 'success'
                ORDER BY finished_at DESC NULLS LAST
                LIMIT 10
            ) sub
        """)).fetchone()

        avg_duration: Optional[float] = None
        avg_cps: Optional[float] = None
        if avg_row and avg_row.avg_duration_seconds is not None:
            avg_duration = round(float(avg_row.avg_duration_seconds), 2)
        if avg_row and avg_row.avg_chunks_per_second is not None:
            avg_cps = round(float(avg_row.avg_chunks_per_second), 2)

        runs_total = sum(status_map.values())

        runs_stats = KnowledgeRunsStats(
            total=runs_total,
            by_status=status_map,
            by_trigger=trigger_map,
            last_run_at=ts_row.last_run_at if ts_row else None,
            last_success_at=ts_row.last_success_at if ts_row else None,
            last_failure_at=ts_row.last_failure_at if ts_row else None,
            avg_duration_seconds_last_10=avg_duration,
            avg_chunks_per_second_last_10=avg_cps,
        )

        # --- Top-10 Pfade nach Chunk-Anzahl (Sentinel-Rows ausschließen) ---
        # GEÄNDERT: Ticket 33 — embedding IS NOT NULL filtert Sentinel-Rows heraus
        top_rows = session.execute(sa_text("""
            SELECT vault_path, COUNT(*) AS chunks
            FROM vault_chunks
            WHERE embedding IS NOT NULL
            GROUP BY vault_path
            ORDER BY COUNT(*) DESC
            LIMIT 10
        """)).fetchall()

    top_paths = [
        KnowledgeTopPathEntry(vault_path=row.vault_path, chunks=int(row.chunks))
        for row in top_rows
    ]

    return KnowledgeStatsResponse(
        index=index_stats,
        runs=runs_stats,
        top_paths_by_chunks=top_paths,
    )
