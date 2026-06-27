"""
Embedding-Client für ein lokales bge-m3-Backend.

Sendet Text via HTTP-POST an das Embedding-Backend und gibt einen
1024-dimensionalen Float-Vektor zurück. Modell: bge-m3-f16.

Konfiguration:
    EMBEDDING_BACKEND_URL  — Backend-URL (Pflicht, kein Default)
    EMBED_BACKEND          — Backend-Identifier (Konstante für späteren Fallback)
"""

import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Backend-Identifier — Vorbereitung für späteren Fallback (kein zweites Backend implementiert)
EMBED_BACKEND: str = "llama-vulkan"

_EMBEDDING_DIM = 1024
_TIMEOUT_SECONDS = 30


def _get_backend_url() -> str:
    """Liest die Pflicht-Variable EMBEDDING_BACKEND_URL; bricht hart ab, wenn sie fehlt oder leer ist."""
    url = os.environ.get("EMBEDDING_BACKEND_URL")
    if not url:
        raise RuntimeError(
            "Pflicht-Umgebungsvariable EMBEDDING_BACKEND_URL fehlt oder ist leer"
        )
    return url


def embed(text: str) -> list[float]:
    """Erzeugt einen Embedding-Vektor für den gegebenen Text.

    Sendet einen HTTP-POST an das konfigurierte Embedding-Backend und gibt
    den 1024-dimensionalen Vektor zurück.

    Args:
        text: Zu embeddender Text (nicht leer).

    Returns:
        list[float] mit genau 1024 Elementen.

    Raises:
        requests.HTTPError: Bei einem HTTP-Fehler-Status vom Backend.
        ValueError: Wenn die Antwort nicht die erwartete Dimension hat.
        requests.RequestException: Bei Verbindungsfehlern oder Timeout.
    """
    url = f"{_get_backend_url()}/embedding"
    response = requests.post(
        url,
        json={"content": text},
        timeout=_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    data = response.json()
    # llama.cpp-Format (Embedding-Backend): [{"index": 0, "embedding": [[...]]}]
    # Das innere embedding ist eine Liste-in-Liste (batch-Format).
    # Normalisierung auf flat list[float]:
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            raw = first.get("embedding", [])
            # Batch-Format: [[v1, v2, ...]] → [v1, v2, ...]
            if raw and isinstance(raw[0], list):
                vector = raw[0]
            else:
                vector = raw
        elif isinstance(first, (int, float)):
            # Direkte Float-Liste
            vector = data
        else:
            vector = []
    elif isinstance(data, dict):
        raw = data.get("embedding") or data.get("data") or []
        if raw and isinstance(raw[0], list):
            vector = raw[0]
        else:
            vector = raw
    else:
        vector = []

    if len(vector) != _EMBEDDING_DIM:
        raise ValueError(
            f"Unerwartete Embedding-Dimension: erwartet {_EMBEDDING_DIM}, "
            f"erhalten {len(vector)}. Backend-URL: {url}"
        )

    return [float(v) for v in vector]
