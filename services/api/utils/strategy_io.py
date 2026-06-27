"""Export und Import von Strategie-Objekten als eigenständige JSON-Dateien.

Drei unabhängige Objekttypen, je ein Export/Import-Paar — kein Bündeln:

- Konzept (``strategy_concepts``)      -> ``<base>/<slug>/concept.json``
- Iteration (``strategy_iterations``)  -> ``<base>/<slug>/<version>/iteration.json``
- Indikator-Konfig (``indicator_configs``)
      -> ``<base>/<slug>/<version>/indicator-configs/<name>.json`` (bei Iterations-Link)
      -> ``<base>/<slug>/indicator-configs/<name>.json``           (nur Konzept-Link)
      -> ``<base>/_unlinked/indicator-configs/<name>.json``        (ohne Link)

``<base>`` ist ``documentation/backup/strategies`` im Projekt-Root. Der Export
schreibt die Datei dorthin; der Import liest eine vom Nutzer hochgeladene Datei
(Herkunft beliebig) und legt das Objekt neu an. IDs werden niemals übernommen.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from user_data.utils.database.models import IndicatorConfig
from user_data.utils.database.repository_strategies import (
    create_concept,
    create_iteration,
    get_concept,
    get_concept_by_slug,
    get_iteration,
    next_iteration_version,
    update_concept,
)

# Format-Version des Datei-Schemas — erlaubt robusten Import bei späteren Änderungen.
FORMAT_VERSION = 1


def backup_base() -> Path:
    """Basis-Ordner für die Export-Dateien.

    Override über die Umgebungsvariable ``STRATEGY_BACKUP_DIR`` (für Tests).
    Sonst ``<PROJECT_ROOT>/documentation/backup/strategies`` — PROJECT_ROOT aus
    der Env (im Container ``/app``) oder aus dem Datei-Pfad abgeleitet.

    Returns:
        Absoluter Pfad zum Strategie-Backup-Ordner.
    """
    override = os.environ.get('STRATEGY_BACKUP_DIR')
    if override:
        return Path(override)
    root = os.environ.get('PROJECT_ROOT')
    base = Path(root) if root else Path(__file__).resolve().parents[3]
    return base / 'documentation' / 'backup' / 'strategies'


def _safe_filename(name: str) -> str:
    """Normalisiert einen Namen auf einen dateisystem-sicheren Dateinamen-Stamm.

    Leerzeichen/Slashes werden zu Bindestrichen, problematische Zeichen entfernt.
    Leerer Rest fällt auf ``unnamed`` zurück.

    Args:
        name: Roher Objekt-Name.

    Returns:
        Sicherer Dateiname-Stamm (ohne ``.json``).
    """
    s = (name or '').strip().lower()
    s = re.sub(r'[\s/\\]+', '-', s)
    s = re.sub(r'[^a-z0-9._-]', '', s)
    s = re.sub(r'-+', '-', s).strip('-.')
    return s or 'unnamed'


def _write_json(path: Path, payload: Dict[str, Any]) -> Path:
    """Schreibt ein Dict als hübsch formatiertes JSON (UTF-8, Umlaute erhalten).

    Args:
        path: Zielpfad (Eltern-Ordner werden angelegt).
        payload: Zu serialisierendes Dict.

    Returns:
        Der geschriebene Pfad.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding='utf-8',
    )
    return path


def _envelope(kind: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Baut den gemeinsamen Datei-Umschlag (format_version, kind, exported_at)."""
    return {
        'format_version': FORMAT_VERSION,
        'kind': kind,
        'exported_at': datetime.now().isoformat(),
        **body,
    }


# ============================================================================
# Konzept
# ============================================================================

def export_concept(session: Session, concept_id: int) -> Path:
    """Exportiert ein Konzept als ``<slug>/concept.json``.

    Args:
        session: SQLAlchemy-Session.
        concept_id: Primärschlüssel des Konzepts.

    Returns:
        Pfad der geschriebenen Datei.

    Raises:
        ValueError: Konzept nicht gefunden.
    """
    concept = get_concept(session, concept_id)
    if concept is None:
        raise ValueError(f"Konzept {concept_id} nicht gefunden.")
    payload = _envelope('strategy_concept', {
        'concept': {
            'slug': concept.slug,
            'name': concept.name,
            'category': concept.category,
            'description': concept.description,
            'status': concept.status,
        },
    })
    return _write_json(backup_base() / concept.slug / 'concept.json', payload)


def import_concept(session: Session, payload: Dict[str, Any]) -> Tuple[Any, str]:
    """Legt ein Konzept aus einem Export-Payload an oder aktualisiert es per slug.

    Args:
        session: SQLAlchemy-Session.
        payload: Geparstes JSON (mit ``concept``-Block).

    Returns:
        Tupel (Konzept, Aktion) — Aktion ist 'created' oder 'updated'.

    Raises:
        ValueError: Payload ohne gültigen Konzept-Block.
    """
    data = payload.get('concept') if isinstance(payload, dict) else None
    if not isinstance(data, dict) or not data.get('slug'):
        raise ValueError("Ungültige Konzept-Datei: 'concept.slug' fehlt.")
    fields = {
        'slug': data['slug'],
        'name': data.get('name') or data['slug'],
        'category': data.get('category'),
        'description': data.get('description'),
        'status': data.get('status') or 'active',
    }
    existing = get_concept_by_slug(session, fields['slug'])
    if existing is not None:
        update_concept(session, existing.id, **fields)
        return get_concept(session, existing.id), 'updated'
    return create_concept(session, **fields), 'created'


# ============================================================================
# Iteration
# ============================================================================

def export_iteration(session: Session, iteration_id: int) -> Path:
    """Exportiert eine Iteration als ``<slug>/<version>/iteration.json``.

    ``version`` dient nur der Ablage; beim Import wird eine frische Nummer
    vergeben. ``concept_slug`` ist Kontext (Anzeige) — das Import-Ziel bestimmt
    der Nutzer über das Konzept, in das er importiert.

    Args:
        session: SQLAlchemy-Session.
        iteration_id: Primärschlüssel der Iteration.

    Returns:
        Pfad der geschriebenen Datei.

    Raises:
        ValueError: Iteration oder zugehöriges Konzept nicht gefunden.
    """
    iteration = get_iteration(session, iteration_id)
    if iteration is None:
        raise ValueError(f"Iteration {iteration_id} nicht gefunden.")
    concept = get_concept(session, iteration.concept_id)
    if concept is None:
        raise ValueError(f"Konzept {iteration.concept_id} zur Iteration nicht gefunden.")
    payload = _envelope('strategy_iteration', {
        'concept_slug': concept.slug,
        'source_version': iteration.version,
        'iteration': {
            'version_name': iteration.version_name,
            'spec_json': iteration.spec_json,
            'spec_hash': iteration.spec_hash,
            'type': iteration.type,
            'import_path': iteration.import_path,
            'description': iteration.description,
            'status': iteration.status,
        },
    })
    target = backup_base() / concept.slug / str(iteration.version) / 'iteration.json'
    return _write_json(target, payload)


def import_iteration(session: Session, concept_id: int, payload: Dict[str, Any]) -> Any:
    """Legt eine Iteration als neue Version in ein bestehendes Konzept an.

    ``version`` wird frisch aus dem Konzept-Zähler vergeben,
    ``parent_iteration_id`` auf NULL gesetzt (der Vorgänger ist nicht Teil des
    Einzel-Exports). Keine ID-Übernahme.

    Args:
        session: SQLAlchemy-Session.
        concept_id: Ziel-Konzept, in das importiert wird.
        payload: Geparstes JSON (mit ``iteration``-Block).

    Returns:
        Die neu angelegte Iteration.

    Raises:
        ValueError: Ziel-Konzept fehlt oder Payload ungültig.
    """
    if get_concept(session, concept_id) is None:
        raise ValueError(f"Ziel-Konzept {concept_id} nicht gefunden.")
    data = payload.get('iteration') if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise ValueError("Ungültige Iterations-Datei: 'iteration'-Block fehlt.")
    return create_iteration(
        session,
        concept_id=concept_id,
        version=next_iteration_version(session, concept_id),
        version_name=data.get('version_name'),
        spec_json=data.get('spec_json'),
        spec_hash=data.get('spec_hash'),
        type=data.get('type') or 'generic',
        import_path=data.get('import_path'),
        parent_iteration_id=None,
        status=data.get('status') or 'active',
        description=data.get('description'),
    )


# ============================================================================
# Indikator-Konfiguration
# ============================================================================

def _indicator_config_target(session: Session, config: IndicatorConfig) -> Path:
    """Bestimmt den Ablage-Pfad einer IndicatorConfig nach ihrer Verknüpfung."""
    base = backup_base()
    fname = f"{_safe_filename(config.name)}.json"
    if config.strategy_iteration_id:
        iteration = get_iteration(session, config.strategy_iteration_id)
        if iteration is not None:
            concept = get_concept(session, iteration.concept_id)
            if concept is not None:
                return base / concept.slug / str(iteration.version) / 'indicator-configs' / fname
    if config.strategy_concept_id:
        concept = get_concept(session, config.strategy_concept_id)
        if concept is not None:
            return base / concept.slug / 'indicator-configs' / fname
    return base / '_unlinked' / 'indicator-configs' / fname


def export_indicator_config(session: Session, config_id: int) -> Path:
    """Exportiert eine IndicatorConfig als eigenständige JSON-Datei.

    Die JSON enthält keine lokalen Verknüpfungs-IDs (die sind auf einer anderen
    Installation bedeutungslos) — nur Name, Beschreibung, config_json, is_default.

    Args:
        session: SQLAlchemy-Session.
        config_id: Primärschlüssel der IndicatorConfig.

    Returns:
        Pfad der geschriebenen Datei.

    Raises:
        ValueError: Config nicht gefunden.
    """
    config = session.query(IndicatorConfig).filter(IndicatorConfig.id == config_id).first()
    if config is None:
        raise ValueError(f"IndicatorConfig {config_id} nicht gefunden.")
    payload = _envelope('indicator_config', {
        'indicator_config': {
            'name': config.name,
            'description': config.description,
            'config_json': config.config_json,
            'is_default': config.is_default,
        },
    })
    return _write_json(_indicator_config_target(session, config), payload)


def import_indicator_config(
    session: Session,
    payload: Dict[str, Any],
    strategy_concept_id: Optional[int] = None,
    strategy_iteration_id: Optional[int] = None,
) -> IndicatorConfig:
    """Legt eine IndicatorConfig aus einem Export-Payload neu an.

    Immer ein neuer Datensatz (Namen dürfen sich wiederholen). Die Verknüpfung
    wird optional auf das Ziel gesetzt, in das importiert wird.

    Args:
        session: SQLAlchemy-Session.
        payload: Geparstes JSON (mit ``indicator_config``-Block).
        strategy_concept_id: Optionale Konzept-Verknüpfung.
        strategy_iteration_id: Optionale Iterations-Verknüpfung.

    Returns:
        Die neu angelegte IndicatorConfig.

    Raises:
        ValueError: Payload ungültig.
    """
    data = payload.get('indicator_config') if isinstance(payload, dict) else None
    if not isinstance(data, dict) or not data.get('name') or data.get('config_json') is None:
        raise ValueError("Ungültige Config-Datei: 'indicator_config.name'/'config_json' fehlt.")
    config = IndicatorConfig(
        name=data['name'],
        description=data.get('description'),
        config_json=data['config_json'],
        is_default=int(data.get('is_default') or 0),
        strategy_concept_id=strategy_concept_id,
        strategy_iteration_id=strategy_iteration_id,
    )
    session.add(config)
    session.commit()
    session.refresh(config)
    return config
