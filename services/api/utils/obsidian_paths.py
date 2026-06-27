"""Utility: Deterministisch ableitbare Obsidian-Vault-Pfade.

Alle Pfade leiten sich ausschließlich aus slug + version ab.
Keine DB-Felder nötig — kein obsidian_slug, kein obsidian_path.

Pfad-Konvention:
  Konzept-Ordner:      30_Trading/strategies/<slug>/
  Konzept-Notiz:       30_Trading/strategies/<slug>/<slug>-concept.md
  Iterations-Ordner:   30_Trading/strategies/<slug>/iterations/<version>/
  Iterations-Notiz:    .../iterations/<version>/<slug>-<version>.md
"""
import os
import re
from pathlib import Path


def vault_root() -> Path:
    """Vault-Root aus Env-Variable OBSIDIAN_VAULT_PATH, default /obsidian_vault.

    Im Container wird OBSIDIAN_VAULT_PATH gesetzt (Bind-Mount). Der Default
    /obsidian_vault entspricht dem Container-Mount-Ziel.

    Returns:
        Absoluter Pfad zum Obsidian-Vault.
    """
    return Path(os.environ.get('OBSIDIAN_VAULT_PATH', '/obsidian_vault'))


def normalize_slug(raw: str) -> str:
    """Normalisiert einen Slug auf ^[a-z0-9-]+$.

    Leerzeichen und Unterstriche werden zu Bindestrichen,
    alles lowercase. Ungültige Zeichen werden entfernt.

    Args:
        raw: Roher Slug-String (z.B. 'Test Strategie' oder 'teststrategie').

    Returns:
        Normalisierter Slug (z.B. 'test-strategie').
    """
    s = raw.strip().lower()
    s = re.sub(r'[\s_]+', '-', s)
    s = re.sub(r'[^a-z0-9-]', '', s)
    s = re.sub(r'-+', '-', s).strip('-')
    return s


def normalize_version(raw: str) -> str:
    """Normalisiert eine Versions-Bezeichnung auf ^[a-z0-9._-]+$.

    Leerzeichen werden zu Bindestrichen, lowercase.
    Punkte und Unterstriche bleiben erhalten (z.B. dyn-v0.31o_robustness-bestvariante).

    Args:
        raw: Roher Versions-String.

    Returns:
        Normalisierte Version.
    """
    s = raw.strip().lower()
    s = re.sub(r'\s+', '-', s)
    s = re.sub(r'[^a-z0-9._-]', '', s)
    return s


def concept_dir(slug: str) -> Path:
    """Ordner-Pfad für ein Strategie-Konzept.

    Args:
        slug: Normalisierter Konzept-Slug (z.B. 'teststrategie').

    Returns:
        Absoluter Pfad zum Konzept-Ordner im Vault.
    """
    return vault_root() / '30_Trading' / 'strategies' / slug


def concept_md_path(slug: str) -> Path:
    """Pfad zur Konzept-Notiz.

    Args:
        slug: Normalisierter Konzept-Slug.

    Returns:
        Absoluter Pfad zur Konzept-Markdown-Datei.
    """
    return concept_dir(slug) / f'{slug}-concept.md'


def iteration_dir(slug: str, version) -> Path:
    """Ordner-Pfad für eine Iterations-Version.

    Args:
        slug: Normalisierter Konzept-Slug.
        version: Fortlaufende Iterations-Nummer (Integer, z.B. 3).

    Returns:
        Absoluter Pfad zum Iterations-Ordner.
    """
    # GEÄNDERT: version ist Integer — für den Pfad-Join in String wandeln
    return concept_dir(slug) / 'iterations' / str(version)


def iteration_md_path(slug: str, version) -> Path:
    """Pfad zur Iterations-Notiz.

    Dateiname: {slug}-{version}.md (z.B. teststrategie-3.md).

    Args:
        slug: Normalisierter Konzept-Slug.
        version: Fortlaufende Iterations-Nummer (Integer).

    Returns:
        Absoluter Pfad zur Iterations-Markdown-Datei.
    """
    return iteration_dir(slug, version) / f'{slug}-{version}.md'
