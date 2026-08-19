"""Utility: Deterministisch ableitbare Obsidian-Vault-Pfade.

Alle Pfade leiten sich ausschließlich aus slug + version ab.
Keine DB-Felder nötig — kein obsidian_slug, kein obsidian_path.

Pfad-Konvention (Vault-Umbau vom 2026-08-18):
  Konzept-Ordner:      30_Trading/strategies/<slug>/
  Konzept-Notiz:       30_Trading/strategies/<slug>/<slug>-concept.md
  Welten-Ordner:       30_Trading/strategies/<slug>/vbt/
  Status-Notiz:        30_Trading/strategies/<slug>/vbt/status.md
  Iterations-Ordner:   30_Trading/strategies/<slug>/vbt/iterations/<version>/
  Iterations-Notiz:    .../iterations/<version>/<slug>-<version>.md

Ein Konzept liegt in EINEM Ordner; die Werkzeugwelten (vbt, tradingview) sind
Unterordner darin. Die Konzept-Notiz gehoert beiden Welten und liegt deshalb
eine Ebene ueber dem Welten-Ordner — alles, was es nur auf der vbt-Seite gibt
(Status, Iterationen, Lessons, Ideen), liegt darunter.
"""
import os
import re
from pathlib import Path

# GEÄNDERT: Vault-Umbau 2026-08-18 — die Werkzeugwelt ist nicht mehr die oberste
# Trennung. Ein Konzept liegt unter 30_Trading/strategies/<slug>/, die Welten
# (vbt, tradingview) sind Unterordner darin.
# Single Source für Backend UND Frontend (Deeplinks holen die Werte per
# strategies_base_rel() bzw. world_dir_rel()).
STRATEGIES_BASE_REL = '30_Trading/strategies'

# Werkzeugwelt dieses Projekts. Alles, was es nur auf der vbt-Seite gibt (Status,
# Iterationen, Lessons, Ideen), liegt in diesem Unterordner des Konzept-Ordners.
WORLD_DIR_REL = 'vbt'


def strategies_base_rel() -> str:
    """Vault-relativer Basis-Pfad aller Strategie-Konzepte.

    Wird ans Frontend durchgereicht, damit die Obsidian-Deeplinks den Pfad
    nicht selbst zusammenbauen müssen.

    Returns:
        Vault-relativer Pfad mit Forward-Slashes (z.B. '30_Trading/strategies').
    """
    return STRATEGIES_BASE_REL


def world_dir_rel() -> str:
    """Name des Welten-Unterordners innerhalb eines Konzept-Ordners.

    Wird ans Frontend durchgereicht, damit die Obsidian-Deeplinks auf Iterationen
    den Pfad nicht selbst zusammenbauen müssen.

    Returns:
        Ordnername der vbt-Welt (z.B. 'vbt').
    """
    return WORLD_DIR_REL


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
    return vault_root() / STRATEGIES_BASE_REL / slug


def concept_md_path(slug: str) -> Path:
    """Pfad zur Konzept-Notiz.

    Args:
        slug: Normalisierter Konzept-Slug.

    Returns:
        Absoluter Pfad zur Konzept-Markdown-Datei.
    """
    return concept_dir(slug) / f'{slug}-concept.md'


def world_dir(slug: str) -> Path:
    """Ordner-Pfad der vbt-Welt innerhalb eines Konzept-Ordners.

    Hier liegt alles, was es nur auf der vbt-Seite gibt: status.md, iterations/,
    lessons/, ideas/. Die Konzept-Notiz gehört beiden Welten und liegt eine Ebene
    darüber (siehe `concept_md_path`).

    Args:
        slug: Normalisierter Konzept-Slug.

    Returns:
        Absoluter Pfad zum Welten-Ordner im Vault.
    """
    return concept_dir(slug) / WORLD_DIR_REL


def status_md_path(slug: str) -> Path:
    """Pfad zur Status-Notiz (operativer Anker der vbt-Seite).

    Args:
        slug: Normalisierter Konzept-Slug.

    Returns:
        Absoluter Pfad zur status.md im Welten-Ordner.
    """
    return world_dir(slug) / 'status.md'


def iteration_dir(slug: str, version) -> Path:
    """Ordner-Pfad für eine Iterations-Version.

    Args:
        slug: Normalisierter Konzept-Slug.
        version: Fortlaufende Iterations-Nummer (Integer, z.B. 3).

    Returns:
        Absoluter Pfad zum Iterations-Ordner.
    """
    # GEÄNDERT: version ist Integer — für den Pfad-Join in String wandeln
    # GEÄNDERT: Vault-Umbau 2026-08-18 — Iterationen liegen im Welten-Ordner
    return world_dir(slug) / 'iterations' / str(version)


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
