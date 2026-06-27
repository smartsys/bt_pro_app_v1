"""Import-Smoketest für das VaultChunk-Modell (Ticket 24).

Prüft:
  - VaultChunk ist importierbar
  - Pflichtfelder sind korrekt deklariert
  - __tablename__ ist korrekt
"""

import pytest
from user_data.utils.database.models import VaultChunk


def test_vault_chunk_importierbar():
    """VaultChunk-Klasse ist ohne Fehler importierbar."""
    assert VaultChunk is not None


def test_vault_chunk_tablename():
    """Tabellenname ist 'vault_chunks'."""
    assert VaultChunk.__tablename__ == 'vault_chunks'


def test_vault_chunk_pflichtfelder():
    """Alle Pflichtfelder aus dem Ticket sind als Spalten deklariert."""
    mapper = VaultChunk.__mapper__
    spalten = {col.key for col in mapper.columns}

    erwartete_spalten = {
        'id',
        'vault_path',
        'chunk_index',
        'heading_path',
        'content',
        'frontmatter_json',
        'mtime',
        'embedding',
        'indexed_at',
    }
    fehlende = erwartete_spalten - spalten
    assert not fehlende, f"Fehlende Spalten: {fehlende}"


def test_vault_chunk_nullable_regeln():
    """heading_path und frontmatter_json sind nullable, vault_path nicht."""
    mapper = VaultChunk.__mapper__
    spalten = {col.key: col for col in mapper.columns}

    assert spalten['heading_path'].nullable is True, "heading_path muss nullable sein"
    assert spalten['frontmatter_json'].nullable is True, "frontmatter_json muss nullable sein"
    assert spalten['vault_path'].nullable is False, "vault_path darf nicht nullable sein"
    # GEÄNDERT: Ticket 33 — content und embedding sind nullable (leere Sentinel-Rows
    # für Stub-Dateien ohne chunkbaren Inhalt).
    assert spalten['content'].nullable is True, "content muss nullable sein (Sentinel-Rows)"
    assert spalten['embedding'].nullable is True, "embedding muss nullable sein (Sentinel-Rows)"
    assert spalten['mtime'].nullable is False, "mtime darf nicht nullable sein"
