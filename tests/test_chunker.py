"""
Unit-Tests für services/vbt/knowledge/chunker.py (Ticket 25).

Prüft:
  - Heading-Split: H2/H3-Trennung, heading_path-Hierarchie
  - Frontmatter-Parse: YAML zwischen --- Markern
  - Hard-Split bei ~1000 Tokens (4000 Zeichen)
  - Notiz ohne Headings -> ein einzelner Chunk mit heading_path=None
"""

import sys
import textwrap
from pathlib import Path

import pytest

# Sicherstellen dass Projekt-Root im Suchpfad ist
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.vbt.knowledge.chunker import chunk_markdown, Chunk, _parse_frontmatter, _build_heading_path


# ============================================================================
# Hilfsfunktionen
# ============================================================================

def _write_tmp(tmp_path: Path, content: str, filename: str = "test.md") -> Path:
    """Schreibt content als UTF-8-Datei und gibt den Pfad zurück."""
    p = tmp_path / filename
    p.write_text(content, encoding="utf-8")
    return p


# ============================================================================
# _parse_frontmatter Tests
# ============================================================================

class TestParseFrontmatter:
    def test_ohne_frontmatter(self):
        """Kein Frontmatter -> leeres Dict, Text unverändert."""
        fm, body = _parse_frontmatter("# Titel\n\nText")
        assert fm == {}
        assert "# Titel" in body

    def test_mit_frontmatter(self):
        """Gültiger YAML-Frontmatter wird geparst."""
        text = "---\ntype: strategy-status\nstrategy: teststrategie\n---\n# Titel\n\nText"
        fm, body = _parse_frontmatter(text)
        assert fm["type"] == "strategy-status"
        assert fm["strategy"] == "teststrategie"
        assert "# Titel" in body

    def test_frontmatter_nicht_am_anfang(self):
        """Frontmatter-Block der nicht am Anfang steht wird ignoriert."""
        text = "Text\n---\ntype: test\n---\n"
        fm, body = _parse_frontmatter(text)
        assert fm == {}

    def test_frontmatter_ungueltig(self):
        """Ungültiges YAML führt zu leerem Dict statt Exception."""
        text = "---\n{unvalid: [yaml\n---\n# Titel"
        fm, body = _parse_frontmatter(text)
        assert isinstance(fm, dict)


# ============================================================================
# _build_heading_path Tests
# ============================================================================

class TestBuildHeadingPath:
    def test_nur_h1(self):
        assert _build_heading_path("Titel", None, None) == "Titel"

    def test_h1_h2(self):
        assert _build_heading_path("Titel", "Abschnitt", None) == "Titel > Abschnitt"

    def test_h1_h2_h3(self):
        result = _build_heading_path("Titel", "Abschnitt", "Unterabschnitt")
        assert result == "Titel > Abschnitt > Unterabschnitt"

    def test_alle_none(self):
        assert _build_heading_path(None, None, None) is None

    def test_nur_h2(self):
        """H2 ohne H1 ist möglich (Datei beginnt ohne H1)."""
        assert _build_heading_path(None, "Abschnitt", None) == "Abschnitt"


# ============================================================================
# chunk_markdown Tests
# ============================================================================

class TestChunkMarkdown:
    def test_notiz_ohne_headings(self, tmp_path):
        """Datei ohne Headings -> ein Chunk mit heading_path=None."""
        content = "Das ist ein einfacher Text ohne Überschriften.\n\nNoch mehr Text."
        p = _write_tmp(tmp_path, content)
        chunks = chunk_markdown(p)
        assert len(chunks) == 1
        assert chunks[0].heading_path is None
        assert chunks[0].chunk_index == 0
        assert "einfacher Text" in chunks[0].content

    def test_h2_split(self, tmp_path):
        """H2-Überschriften teilen den Body in separate Chunks."""
        content = textwrap.dedent("""\
            # Haupttitel

            Einleitung.

            ## Erster Abschnitt

            Inhalt des ersten Abschnitts.

            ## Zweiter Abschnitt

            Inhalt des zweiten Abschnitts.
        """)
        p = _write_tmp(tmp_path, content)
        chunks = chunk_markdown(p)
        # Mindestens 2 Chunks (die zwei H2-Abschnitte)
        headings = [c.heading_path for c in chunks if c.heading_path]
        assert any("Erster Abschnitt" in h for h in headings)
        assert any("Zweiter Abschnitt" in h for h in headings)

    def test_h3_split_mit_hierarchie(self, tmp_path):
        """H3 unter H2 baut korrekte Hierarchie im heading_path."""
        content = textwrap.dedent("""\
            # Haupttitel

            ## Iterationen

            Überblick.

            ### v0.41

            Details zur Iteration v0.41.
        """)
        p = _write_tmp(tmp_path, content)
        chunks = chunk_markdown(p)
        h3_chunks = [c for c in chunks if c.heading_path and "v0.41" in c.heading_path]
        assert h3_chunks, f"Kein H3-Chunk mit 'v0.41' gefunden. Chunks: {[c.heading_path for c in chunks]}"
        assert "Iterationen" in h3_chunks[0].heading_path
        assert "Haupttitel" in h3_chunks[0].heading_path

    def test_frontmatter_in_jedem_chunk(self, tmp_path):
        """Frontmatter landet in jedem Chunk als Dict."""
        content = textwrap.dedent("""\
            ---
            type: strategy-status
            strategy: teststrategie
            ---
            # Strategie

            ## Abschnitt A

            Text A.

            ## Abschnitt B

            Text B.
        """)
        p = _write_tmp(tmp_path, content)
        chunks = chunk_markdown(p)
        assert len(chunks) >= 2
        for chunk in chunks:
            assert chunk.frontmatter.get("type") == "strategy-status"
            assert chunk.frontmatter.get("strategy") == "teststrategie"

    def test_hard_split_bei_grossem_chunk(self, tmp_path):
        """Chunk > 4000 Zeichen wird per Hard-Split geteilt (gleicher heading_path)."""
        # Erstelle Block mit ~5000 Zeichen unter einem H2
        big_text = "x" * 5000
        content = f"## Großer Abschnitt\n\n{big_text}\n"
        p = _write_tmp(tmp_path, content)
        chunks = chunk_markdown(p)
        # Muss mehr als einen Chunk erzeugen
        assert len(chunks) > 1, f"Nur {len(chunks)} Chunk(s) für 5000-Zeichen-Block"
        # Alle Teil-Chunks haben denselben heading_path
        hp = chunks[0].heading_path
        for c in chunks:
            assert c.heading_path == hp
        # chunk_index zählt durch
        for i, c in enumerate(chunks):
            assert c.chunk_index == i

    def test_code_block_nicht_gesplittet(self, tmp_path):
        """H3 innerhalb eines Code-Blocks wird nicht als Heading interpretiert."""
        content = textwrap.dedent("""\
            ## Beispiel

            ```python
            ### Das ist kein Heading
            def foo():
                pass
            ```

            ## Nächster Abschnitt

            Text.
        """)
        p = _write_tmp(tmp_path, content)
        chunks = chunk_markdown(p)
        # Exakt 2 H2-Chunks (Code-Block-Heading ignoriert)
        h2_chunks = [c for c in chunks if c.heading_path]
        heading_paths = [c.heading_path for c in h2_chunks]
        assert not any("Das ist kein Heading" in (hp or "") for hp in heading_paths), \
            f"Heading innerhalb Code-Block wurde gesplittet: {heading_paths}"

    def test_chunk_index_fortlaufend(self, tmp_path):
        """chunk_index ist 0-basiert und lückenlos fortlaufend."""
        content = textwrap.dedent("""\
            # Titel

            ## A
            Text A.
            ## B
            Text B.
            ## C
            Text C.
        """)
        p = _write_tmp(tmp_path, content)
        chunks = chunk_markdown(p)
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(indices))), f"Unerwartete Indices: {indices}"

    def test_leere_datei(self, tmp_path):
        """Leere Datei -> leere Chunk-Liste."""
        p = _write_tmp(tmp_path, "")
        chunks = chunk_markdown(p)
        assert chunks == []

    def test_nur_frontmatter_kein_body(self, tmp_path):
        """Datei nur mit Frontmatter und leerem Body -> leere Chunk-Liste."""
        content = "---\ntype: test\n---\n"
        p = _write_tmp(tmp_path, content)
        chunks = chunk_markdown(p)
        assert chunks == []
