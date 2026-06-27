"""
Markdown-Chunker für den Obsidian-Vault.

Liest eine Markdown-Datei, parst optionalen YAML-Frontmatter und zerlegt
den Body in semantische Chunks entlang H2/H3-Überschriften. Chunks die
~1000 Tokens überschreiten (ca. 4000 Zeichen) werden per Hard-Split geteilt.

Öffentliche API:
    chunk_markdown(path) -> list[Chunk]
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

# Grobe Token-Schätzung: 1 Token ≈ 4 Zeichen
_CHARS_PER_TOKEN = 4
_MAX_TOKENS = 1000
_MAX_CHARS = _MAX_TOKENS * _CHARS_PER_TOKEN  # 4000 Zeichen


@dataclass
class Chunk:
    """Ein einzelner Text-Chunk aus einer Vault-Datei.

    Attributes:
        chunk_index: 0-basierter Index innerhalb der Quelldatei.
        heading_path: Hierarchischer Pfad der Überschriften, z.B. "Titel > Abschnitt > Unterabschnitt".
                      NULL für Dateien ohne Headings oder reinen Frontmatter.
        content: Reiner Chunk-Text inkl. Code-Blöcken.
        frontmatter: Geparstes YAML-Frontmatter der Quelldatei (leer wenn nicht vorhanden).
    """
    chunk_index: int
    heading_path: Optional[str]
    content: str
    frontmatter: dict = field(default_factory=dict)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Trennt YAML-Frontmatter vom Body.

    Erkennt Frontmatter als YAML-Block zwischen zwei '---'-Zeilen am Datei-Anfang.

    Args:
        text: Vollständiger Dateiinhalt.

    Returns:
        Tupel aus (frontmatter_dict, body_text).
    """
    if not text.startswith("---"):
        return {}, text

    # Zweites '---' finden (nicht das erste)
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?", text, re.DOTALL)
    if not match:
        return {}, text

    fm_raw = match.group(1)
    body = text[match.end():]
    try:
        fm = yaml.safe_load(fm_raw) or {}
        if not isinstance(fm, dict):
            fm = {}
    except yaml.YAMLError:
        fm = {}
    return fm, body


def _build_heading_path(h1: Optional[str], h2: Optional[str], h3: Optional[str]) -> Optional[str]:
    """Baut den hierarchischen Heading-Pfad aus H1/H2/H3.

    Args:
        h1: H1-Überschrift (Datei-Top-Level).
        h2: Aktuelle H2-Überschrift.
        h3: Aktuelle H3-Überschrift.

    Returns:
        Pfad-String mit ' > ' als Trennzeichen, oder None wenn alle leer.
    """
    parts = [p for p in (h1, h2, h3) if p]
    return " > ".join(parts) if parts else None


def _split_on_headings(body: str) -> list[tuple[Optional[str], Optional[str], Optional[str], str]]:
    """Zerlegt den Markdown-Body in Abschnitte per H1/H2/H3.

    Code-Blöcke (zwischen ```-Markierungen) werden dabei nicht gesplittet —
    Headings innerhalb eines Code-Blocks werden ignoriert.

    Returns:
        Liste von (h1, h2, h3, content)-Tupeln. Jeder Eintrag repräsentiert
        einen Heading-Block. Der erste Block kann h1=h2=h3=None sein (Text vor
        der ersten Überschrift).
    """
    sections: list[tuple[Optional[str], Optional[str], Optional[str], str]] = []
    current_h1: Optional[str] = None
    current_h2: Optional[str] = None
    current_h3: Optional[str] = None
    current_lines: list[str] = []
    in_code_block = False

    for line in body.splitlines(keepends=True):
        # Code-Block-Zustand tracken
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            current_lines.append(line)
            continue

        if in_code_block:
            current_lines.append(line)
            continue

        # H1 erkennen
        h1_match = re.match(r"^#\s+(.+)$", line.rstrip())
        if h1_match:
            # Bisherigen Block speichern
            content = "".join(current_lines).strip()
            if content or sections:
                sections.append((current_h1, current_h2, current_h3, content))
            current_h1 = h1_match.group(1).strip()
            current_h2 = None
            current_h3 = None
            current_lines = []
            continue

        # H2 erkennen
        h2_match = re.match(r"^##\s+(.+)$", line.rstrip())
        if h2_match:
            content = "".join(current_lines).strip()
            if content or sections:
                sections.append((current_h1, current_h2, current_h3, content))
            current_h2 = h2_match.group(1).strip()
            current_h3 = None
            current_lines = []
            continue

        # H3 erkennen
        h3_match = re.match(r"^###\s+(.+)$", line.rstrip())
        if h3_match:
            content = "".join(current_lines).strip()
            if content or sections:
                sections.append((current_h1, current_h2, current_h3, content))
            current_h3 = h3_match.group(1).strip()
            current_lines = []
            continue

        current_lines.append(line)

    # Letzten Block nicht vergessen
    content = "".join(current_lines).strip()
    sections.append((current_h1, current_h2, current_h3, content))

    # Leere Eröffnungseinträge ohne Inhalt herausfiltern
    return [(h1, h2, h3, c) for h1, h2, h3, c in sections if c or (h1 or h2 or h3)]


def _hard_split(content: str, heading_path: Optional[str], frontmatter: dict, start_index: int) -> list[Chunk]:
    """Teilt einen zu großen Chunk per Hard-Split auf ~1000 Tokens (4000 Zeichen).

    Teilt an Zeilengrenzen um den Grenzwert herum. chunk_index wird weitergezählt.
    Gleicher heading_path in allen Teil-Chunks.

    Args:
        content: Zu teilender Text.
        heading_path: Gemeinsamer Heading-Pfad für alle Teil-Chunks.
        frontmatter: Frontmatter-Dict.
        start_index: Erster chunk_index für den ersten Teil-Chunk.

    Returns:
        Liste von Chunks.
    """
    chunks: list[Chunk] = []
    idx = start_index
    remaining = content

    while remaining:
        if len(remaining) <= _MAX_CHARS:
            chunks.append(Chunk(
                chunk_index=idx,
                heading_path=heading_path,
                content=remaining,
                frontmatter=frontmatter,
            ))
            break

        # An Zeilengrenze schneiden, möglichst nah an MAX_CHARS
        cut = remaining.rfind("\n", 0, _MAX_CHARS)
        if cut <= 0:
            # Keine Zeilengrenze gefunden — hard cut an MAX_CHARS
            cut = _MAX_CHARS

        part = remaining[:cut].strip()
        remaining = remaining[cut:].strip()
        if part:
            chunks.append(Chunk(
                chunk_index=idx,
                heading_path=heading_path,
                content=part,
                frontmatter=frontmatter,
            ))
            idx += 1

    return chunks


def chunk_markdown(path: Path) -> list[Chunk]:
    """Zerlegt eine Markdown-Datei in semantische Chunks.

    Ablauf:
    1. Frontmatter parsen (YAML zwischen --- Markern).
    2. Body entlang H1/H2/H3-Überschriften aufteilen.
    3. Zu große Chunks per Hard-Split teilen (~1000 Tokens).
    4. Dateien ohne Überschriften -> ein einzelner Chunk mit heading_path=None.

    Args:
        path: Absoluter oder relativer Pfad zur Markdown-Datei.

    Returns:
        Geordnete Liste von Chunk-Objekten (0-basierter chunk_index).

    Raises:
        FileNotFoundError: Wenn die Datei nicht existiert.
        UnicodeDecodeError: Wenn die Datei nicht UTF-8-kodiert ist.
    """
    text = path.read_text(encoding="utf-8")
    frontmatter, body = _parse_frontmatter(text)

    sections = _split_on_headings(body)

    # Wenn keine Headings und kein Inhalt -> leere Liste
    if not sections:
        return []

    # Prüfe ob echte Headings vorhanden sind
    has_headings = any(h1 or h2 or h3 for h1, h2, h3, _ in sections)

    if not has_headings:
        # Kein Heading -> ein einzelner Chunk mit heading_path=None
        combined = body.strip()
        if not combined:
            return []
        if len(combined) > _MAX_CHARS:
            return _hard_split(combined, None, frontmatter, 0)
        return [Chunk(chunk_index=0, heading_path=None, content=combined, frontmatter=frontmatter)]

    result: list[Chunk] = []
    chunk_index = 0

    for h1, h2, h3, content in sections:
        if not content:
            continue
        heading_path = _build_heading_path(h1, h2, h3)

        if len(content) > _MAX_CHARS:
            sub_chunks = _hard_split(content, heading_path, frontmatter, chunk_index)
            result.extend(sub_chunks)
            chunk_index += len(sub_chunks)
        else:
            result.append(Chunk(
                chunk_index=chunk_index,
                heading_path=heading_path,
                content=content,
                frontmatter=frontmatter,
            ))
            chunk_index += 1

    return result
