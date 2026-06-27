"""
API-Endpoints für Strategie-Konzepte und Iterationen

GET    /api/strategy/concepts              — Alle Konzepte auflisten
POST   /api/strategy/concepts              — Neues Konzept anlegen
GET    /api/strategy/concepts/{id}         — Einzelnes Konzept abrufen
PUT    /api/strategy/concepts/{id}         — Konzept aktualisieren
DELETE /api/strategy/concepts/{id}         — Konzept löschen (optional force + delete_vault)
POST   /api/strategy/concepts/{id}/vault-create  — Konzept-Notiz im Vault anlegen

GET    /api/strategy/iterations            — Alle Iterationen auflisten (optional: concept_id)
POST   /api/strategy/iterations            — Neue Iteration anlegen
GET    /api/strategy/iterations/{id}       — Einzelne Iteration abrufen
POST   /api/strategy/iterations/{id}/copy  — Iteration kopieren
PUT    /api/strategy/iterations/{id}       — Iteration aktualisieren
POST   /api/strategy/iterations/{id}/vault-create  — Iterations-Notiz im Vault anlegen
"""

import json
import shutil
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict

from services.api.utils.obsidian_paths import (
    concept_dir,
    concept_md_path,
    iteration_md_path,
    iteration_dir,
    normalize_slug,
)
from services.api.utils.strategy_io import (
    export_concept,
    export_iteration,
    import_concept,
    import_iteration,
)
from user_data.utils.database.db import get_session
from user_data.utils.database.repository_strategies import (
    create_concept,
    create_iteration,
    delete_concept,
    delete_iteration,
    force_delete_concept,
    force_delete_iteration,
    get_concept,
    get_concept_blockers,
    get_iteration,
    get_iteration_blockers,
    list_concepts,
    list_iterations,
    next_iteration_version,
    update_concept,
    update_iteration,
)

router = APIRouter(prefix='/api/strategy', tags=['strategy'])


# ============================================================================
# Pydantic Schemas
# ============================================================================

class StrategyConceptSchema(BaseModel):
    """Ausgabe-Schema für ein Strategie-Konzept."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    category: Optional[str] = None
    description: Optional[str] = None
    # GEÄNDERT: Ticket 16 — obsidian_slug entfernt; vault_exists wird live aus Filesystem berechnet
    vault_exists: bool = False
    status: str
    # GEÄNDERT: High-Water-Mark der Iterations-Nummern (für "Speichern unter..."-Vorschau)
    iteration_counter: int = 0
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None


class StrategyConceptCreateSchema(BaseModel):
    """Eingabe-Schema für neues Strategie-Konzept."""
    slug: str
    name: str
    category: Optional[str] = None
    description: Optional[str] = None
    # GEÄNDERT: Ticket 16 — obsidian_slug entfernt
    status: str = 'active'
    created_by: Optional[str] = None


class StrategyConceptUpdateSchema(BaseModel):
    """Eingabe-Schema für Konzept-Update — alle Felder optional."""
    slug: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    # GEÄNDERT: Ticket 16 — obsidian_slug entfernt
    status: Optional[str] = None
    created_by: Optional[str] = None


class StrategyIterationSchema(BaseModel):
    """Ausgabe-Schema für eine Strategie-Iteration."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    concept_id: int
    # GEÄNDERT: version ist eine fortlaufende Integer-Nummer pro Konzept
    version: int
    # GEÄNDERT: Freier Anzeige-Name (optional); version ist die fortlaufende Nummer
    version_name: Optional[str] = None
    spec_json: Optional[Dict[str, Any]] = None
    type: str = 'generic'
    import_path: Optional[str] = None
    parent_iteration_id: Optional[int] = None
    status: str
    # GEÄNDERT: Ticket 16 — obsidian_path entfernt; vault_exists wird live aus Filesystem berechnet
    vault_exists: bool = False
    description: Optional[str] = None
    is_favorite: bool = False
    # GEÄNDERT: Doku-Favoriten-Flag (roter Stern)
    is_doc_favorite: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None


class StrategyIterationCreateSchema(BaseModel):
    """Eingabe-Schema für neue Strategie-Iteration."""
    concept_id: int
    # GEÄNDERT: version ist eine fortlaufende Nummer (Server-vergeben aus dem Konzept-Zähler);
    # weder version noch version_name kommen vom Client. version_name optional als freier Anzeige-Name.
    version_name: Optional[str] = None
    spec_json: Optional[Dict[str, Any]] = None
    type: str = 'generic'
    import_path: Optional[str] = None
    parent_iteration_id: Optional[int] = None
    status: str = 'active'
    # GEÄNDERT: Ticket 16 — obsidian_path entfernt
    description: Optional[str] = None
    created_by: Optional[str] = None


class StrategyIterationUpdateSchema(BaseModel):
    """Eingabe-Schema für Iterations-Update — alle Felder optional.

    version ist nach dem Anlegen fix und wird hier nicht akzeptiert.
    """
    # GEÄNDERT: version entfernt — bleibt nach Create fix; version_name ist editierbar
    version_name: Optional[str] = None
    spec_json: Optional[Dict[str, Any]] = None
    type: Optional[str] = None
    import_path: Optional[str] = None
    parent_iteration_id: Optional[int] = None
    status: Optional[str] = None
    # GEÄNDERT: Ticket 16 — obsidian_path entfernt
    description: Optional[str] = None
    created_by: Optional[str] = None


def _validate_iteration_type_xor(type_: Optional[str], import_path: Optional[str]) -> Optional[str]:
    """Prüfft XOR-Bedingung: type='hardcoded' => import_path Pflicht; type='generic' => import_path NULL.

    Args:
        type_: 'hardcoded' oder 'generic' (None bei Update ohne Änderung erlaubt).
        import_path: Code-Pfad der Strategie-Funktion oder None.

    Returns:
        Fehlermeldung als String oder None wenn valide.
    """
    if type_ is None:
        return None
    if type_ not in ('hardcoded', 'generic'):
        return f"type muss 'hardcoded' oder 'generic' sein, war '{type_}'."
    if type_ == 'hardcoded' and not import_path:
        return "Bei type='hardcoded' muss import_path gesetzt sein."
    if type_ == 'generic' and import_path:
        return "Bei type='generic' darf import_path nicht gesetzt sein."
    return None


def _concept_to_dict(concept) -> Dict[str, Any]:
    """Konvertiert ein StrategyConcept in ein Dict inkl. vault_exists.

    vault_exists wird live aus dem Filesystem berechnet — kein DB-Feld.

    Args:
        concept: StrategyConcept-Instanz.

    Returns:
        Dict mit allen Konzept-Feldern + vault_exists.
    """
    data = StrategyConceptSchema.model_validate(concept).model_dump(mode='json')
    data['vault_exists'] = concept_md_path(concept.slug).exists()
    return data


def _iteration_to_dict(iteration, concept_slug: str) -> Dict[str, Any]:
    """Konvertiert eine StrategyIteration in ein Dict inkl. vault_exists.

    vault_exists wird live aus dem Filesystem berechnet — kein DB-Feld.

    Args:
        iteration: StrategyIteration-Instanz.
        concept_slug: Slug des zugehörigen Konzepts für Pfad-Ableitung.

    Returns:
        Dict mit allen Iterations-Feldern + vault_exists.
    """
    data = StrategyIterationSchema.model_validate(iteration).model_dump(mode='json')
    data['vault_exists'] = iteration_md_path(concept_slug, iteration.version).exists()
    return data


# ============================================================================
# Konzept-Endpoints
# ============================================================================

@router.get('/concepts')
def list_concepts_endpoint():
    """Alle Strategie-Konzepte auflisten.

    Returns:
        JSON mit Liste aller Konzepte und Gesamtanzahl. vault_exists pro Konzept.
    """
    session = get_session()
    try:
        concepts = list_concepts(session)
        items = [_concept_to_dict(c) for c in concepts]
        return {"data": {"items": items, "total": len(items)}, "error": None}
    finally:
        session.close()


@router.post('/concepts')
def create_concept_endpoint(body: StrategyConceptCreateSchema):
    """Neues Strategie-Konzept anlegen.

    Slug wird automatisch auf ^[a-z0-9-]+$ normalisiert.

    Args:
        body: Pflicht- und optionale Felder des Konzepts.

    Returns:
        JSON mit dem neu angelegten Konzept.
    """
    session = get_session()
    try:
        kwargs = body.model_dump(exclude_none=True)
        # GEÄNDERT: Ticket 16 — Slug auto-normalisieren
        if 'slug' in kwargs:
            kwargs['slug'] = normalize_slug(kwargs['slug'])
        concept = create_concept(session, **kwargs)
        result = _concept_to_dict(concept)
        return {"data": result, "error": None}
    finally:
        session.close()


@router.get('/concepts/{concept_id}')
def get_concept_endpoint(concept_id: int):
    """Einzelnes Konzept per ID abrufen.

    Args:
        concept_id: Primärschlüssel des Konzepts.

    Returns:
        JSON mit dem Konzept (inkl. vault_exists) oder 404 wenn nicht gefunden.
    """
    session = get_session()
    try:
        concept = get_concept(session, concept_id)
        if concept is None:
            raise HTTPException(status_code=404, detail=f"Konzept {concept_id} nicht gefunden.")
        result = _concept_to_dict(concept)
        return {"data": result, "error": None}
    finally:
        session.close()


@router.put('/concepts/{concept_id}')
def update_concept_endpoint(concept_id: int, body: StrategyConceptUpdateSchema):
    """Bestehendes Konzept aktualisieren.

    Slug wird automatisch auf ^[a-z0-9-]+$ normalisiert.

    Args:
        concept_id: Primärschlüssel des Konzepts.
        body: Zu aktualisierende Felder (alle optional).

    Returns:
        JSON mit dem aktualisierten Konzept (inkl. vault_exists) oder 404 wenn nicht gefunden.
    """
    session = get_session()
    try:
        kwargs = body.model_dump(exclude_none=True)
        if 'slug' in kwargs:
            kwargs['slug'] = normalize_slug(kwargs['slug'])

        # GEÄNDERT: Vault-Ordner umbenennen wenn sich der Slug ändert
        old_concept = get_concept(session, concept_id)
        if old_concept is None:
            raise HTTPException(status_code=404, detail=f"Konzept {concept_id} nicht gefunden.")
        old_slug = old_concept.slug
        new_slug = kwargs.get('slug', old_slug)

        concept = update_concept(session, concept_id, **kwargs)
        if concept is None:
            raise HTTPException(status_code=404, detail=f"Konzept {concept_id} nicht gefunden.")

        if new_slug != old_slug:
            old_dir = concept_dir(old_slug)
            new_dir = concept_dir(new_slug)
            if old_dir.exists() and not new_dir.exists():
                old_dir.rename(new_dir)
                # Konzept-Notiz umbenennen (war {old_slug}-concept.md)
                old_md = new_dir / f'{old_slug}-concept.md'
                new_md = new_dir / f'{new_slug}-concept.md'
                if old_md.exists():
                    old_md.rename(new_md)

        result = _concept_to_dict(concept)
        return {"data": result, "error": None}
    finally:
        session.close()


@router.post('/concepts/{concept_id}/vault-create')
def create_concept_vault(concept_id: int):
    """Konzept-Ordner und Konzept-Notiz mit Frontmatter im Vault anlegen.

    Idempotent: Existiert die Notiz bereits, wird sie nicht überschrieben.

    Args:
        concept_id: Primärschlüssel des Konzepts.

    Returns:
        JSON mit created (bool), exists (bool) und path.
    """
    session = get_session()
    try:
        concept = get_concept(session, concept_id)
        if concept is None:
            raise HTTPException(status_code=404, detail=f"Konzept {concept_id} nicht gefunden.")

        md_path = concept_md_path(concept.slug)

        if md_path.exists():
            return {"data": {"created": False, "exists": True, "path": str(md_path)}, "error": None}

        # Ordner anlegen
        md_path.parent.mkdir(parents=True, exist_ok=True)

        # Minimal-Frontmatter schreiben
        frontmatter = (
            "---\n"
            "type: strategy-concept\n"
            f"concept_id: {concept.id}\n"
            f"slug: {concept.slug}\n"
            f"name: {concept.name}\n"
            f"created_at: {date.today().isoformat()}\n"
            "---\n"
            "\n"
            f"# {concept.name}\n"
            "\n"
        )
        md_path.write_text(frontmatter, encoding='utf-8')

        return {"data": {"created": True, "exists": True, "path": str(md_path)}, "error": None}
    finally:
        session.close()


@router.delete('/concepts/{concept_id}')
def delete_concept_endpoint(
    concept_id: int,
    delete_vault: bool = Query(default=False),
    force: bool = Query(default=False),
):
    """Konzept löschen — optional inkl. Obsidian-Ordner und abhängigen Datensätzen.

    Args:
        concept_id: Primärschlüssel des Konzepts.
        delete_vault: Wenn True, wird der Konzept-Ordner im Obsidian-Vault
            (inkl. aller Dateien darin) ebenfalls entfernt.
        force: Wenn True, werden alle referenzierenden Datensätze (Iterationen,
            BacktestRuns, BacktestResults) vor dem Löschen entfernt.

    Returns:
        JSON mit deleted, id, vault_deleted (bool) und ggf. vault_path.
        Bei Blockierung ohne force=True: 409 mit Zählern der Blocker.
    """
    session = get_session()
    try:
        concept = get_concept(session, concept_id)
        if concept is None:
            raise HTTPException(status_code=404, detail=f"Konzept {concept_id} nicht gefunden.")
        slug = concept.slug
        vault_dir_path = concept_dir(slug) if slug else None

        blockers = get_concept_blockers(session, concept_id)
        has_blockers = any(v > 0 for v in blockers.values())

        if has_blockers and not force:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": (
                        "Konzept kann nicht gelöscht werden — es existieren noch "
                        "referenzierende Datensätze. Verwende force=true um sie mitzulöschen."
                    ),
                    "blockers": blockers,
                },
            )

        if force and has_blockers:
            deleted = force_delete_concept(session, concept_id)
        else:
            deleted = delete_concept(session, concept_id)

        if not deleted:
            raise HTTPException(status_code=404, detail=f"Konzept {concept_id} nicht gefunden.")

        vault_deleted = False
        if delete_vault and vault_dir_path is not None and vault_dir_path.exists():
            shutil.rmtree(vault_dir_path)
            vault_deleted = True

        return {
            "data": {
                "deleted": True,
                "id": concept_id,
                "force": force,
                "vault_deleted": vault_deleted,
                "vault_path": str(vault_dir_path) if vault_dir_path else None,
            },
            "error": None,
        }
    finally:
        session.close()


# ============================================================================
# Iterations-Endpoints
# ============================================================================

@router.get('/iterations')
def list_iterations_endpoint(concept_id: Optional[int] = Query(default=None)):
    """Alle Iterationen auflisten, optional gefiltert nach Konzept.

    Args:
        concept_id: Optionaler Filter auf concept_id.

    Returns:
        JSON mit Liste der Iterationen (inkl. vault_exists) und Gesamtanzahl.
    """
    session = get_session()
    try:
        iterations = list_iterations(session, concept_id=concept_id)
        # Konzepte einmalig laden für Slug-Lookup
        concepts = {c.id: c for c in list_concepts(session)}
        items = []
        for it in iterations:
            concept = concepts.get(it.concept_id)
            slug = concept.slug if concept else ''
            items.append(_iteration_to_dict(it, slug))
        return {"data": {"items": items, "total": len(items)}, "error": None}
    finally:
        session.close()


@router.post('/iterations')
def create_iteration_endpoint(body: StrategyIterationCreateSchema):
    """Neue Strategie-Iteration anlegen.

    Die Version wird automatisch als fortlaufende Nummer pro Konzept vergeben
    (High-Water-Mark, keine Wiederverwendung nach Löschen).

    Args:
        body: Pflicht- und optionale Felder der Iteration.

    Returns:
        JSON mit der neu angelegten Iteration.
    """
    err = _validate_iteration_type_xor(body.type, body.import_path)
    if err:
        raise HTTPException(status_code=400, detail=err)
    session = get_session()
    try:
        kwargs = body.model_dump(exclude_none=True)
        # GEÄNDERT: version ist eine fortlaufende Nummer pro Konzept, server-vergeben aus dem Zähler
        kwargs['version'] = next_iteration_version(session, body.concept_id)
        iteration = create_iteration(session, **kwargs)
        concept = get_concept(session, iteration.concept_id)
        slug = concept.slug if concept else ''
        result = _iteration_to_dict(iteration, slug)
        return {"data": result, "error": None}
    finally:
        session.close()


@router.post('/iterations/{iteration_id}/copy')
def copy_iteration_endpoint(iteration_id: int):
    """Bestehende Iteration kopieren.

    Erzeugt eine neue Iteration im selben Konzept mit identischem spec_json,
    spec_hash, type, import_path und parent_iteration_id (flache Duplizierung).
    Der version_name bekommt den Zusatz "(Kopie)"; bei Namenskollision wird
    durchnummeriert, damit der UniqueConstraint (concept_id, version) nicht
    verletzt wird. Das Original bleibt unverändert.

    Args:
        iteration_id: Primärschlüssel der zu kopierenden Iteration.

    Returns:
        JSON mit der neu angelegten Iteration oder 404 wenn nicht gefunden.
    """
    session = get_session()
    try:
        original = get_iteration(session, iteration_id)
        if original is None:
            raise HTTPException(status_code=404, detail=f"Iteration {iteration_id} nicht gefunden.")
        base_name = (original.version_name or str(original.version) or f"iter-{iteration_id}").strip()
        # GEÄNDERT: version ist eine fortlaufende Nummer pro Konzept — aus dem Zähler vergeben.
        # version_name dient nur der Anzeige und darf "(Kopie)" enthalten.
        version = next_iteration_version(session, original.concept_id)
        version_name = f"{base_name} (Kopie)"
        iteration = create_iteration(
            session,
            concept_id=original.concept_id,
            version=version,
            version_name=version_name,
            spec_json=original.spec_json,
            spec_hash=original.spec_hash,
            type=original.type,
            import_path=original.import_path,
            parent_iteration_id=original.parent_iteration_id,
            status='active',
            description=original.description,
        )
        concept = get_concept(session, iteration.concept_id)
        slug = concept.slug if concept else ''
        result = _iteration_to_dict(iteration, slug)
        return {"data": result, "error": None}
    finally:
        session.close()


@router.get('/iterations/{iteration_id}')
def get_iteration_endpoint(iteration_id: int):
    """Einzelne Iteration per ID abrufen.

    Args:
        iteration_id: Primärschlüssel der Iteration.

    Returns:
        JSON mit der Iteration (inkl. vault_exists) oder 404 wenn nicht gefunden.
    """
    session = get_session()
    try:
        iteration = get_iteration(session, iteration_id)
        if iteration is None:
            raise HTTPException(status_code=404, detail=f"Iteration {iteration_id} nicht gefunden.")
        concept = get_concept(session, iteration.concept_id)
        slug = concept.slug if concept else ''
        result = _iteration_to_dict(iteration, slug)
        return {"data": result, "error": None}
    finally:
        session.close()


@router.put('/iterations/{iteration_id}')
def update_iteration_endpoint(iteration_id: int, body: StrategyIterationUpdateSchema):
    """Bestehende Iteration aktualisieren.

    Version wird automatisch normalisiert.

    Args:
        iteration_id: Primärschlüssel der Iteration.
        body: Zu aktualisierende Felder (alle optional).

    Returns:
        JSON mit der aktualisierten Iteration (inkl. vault_exists) oder 404 wenn nicht gefunden.
    """
    session = get_session()
    try:
        # GEÄNDERT: XOR-Validierung gegen Effektiv-Werte (Body-Felder über DB-Bestand)
        existing = get_iteration(session, iteration_id)
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Iteration {iteration_id} nicht gefunden.")
        effective_type = body.type if body.type is not None else existing.type
        effective_path = body.import_path if 'import_path' in body.model_fields_set else existing.import_path
        err = _validate_iteration_type_xor(effective_type, effective_path)
        if err:
            raise HTTPException(status_code=400, detail=err)
        # Bei generic explizit import_path auf None setzen (auch wenn nicht im Body)
        update_kwargs = body.model_dump(exclude_unset=True)
        # GEÄNDERT: version ist nach Create fix; nur version_name editierbar
        if effective_type == 'generic' and 'import_path' not in update_kwargs:
            update_kwargs['import_path'] = None

        iteration = update_iteration(session, iteration_id, **update_kwargs)

        concept = get_concept(session, iteration.concept_id)
        slug = concept.slug if concept else ''
        result = _iteration_to_dict(iteration, slug)
        return {"data": result, "error": None}
    finally:
        session.close()


@router.post('/iterations/{iteration_id}/vault-create')
def create_iteration_vault(iteration_id: int):
    """Iterations-Ordner und Iterations-Notiz mit Frontmatter im Vault anlegen.

    Idempotent: Existiert die Notiz bereits, wird sie nicht überschrieben.

    Args:
        iteration_id: Primärschlüssel der Iteration.

    Returns:
        JSON mit created (bool), exists (bool) und path.
    """
    session = get_session()
    try:
        iteration = get_iteration(session, iteration_id)
        if iteration is None:
            raise HTTPException(status_code=404, detail=f"Iteration {iteration_id} nicht gefunden.")
        concept = get_concept(session, iteration.concept_id)
        if concept is None:
            raise HTTPException(status_code=404, detail=f"Konzept {iteration.concept_id} nicht gefunden.")

        md_path = iteration_md_path(concept.slug, iteration.version)

        if md_path.exists():
            return {"data": {"created": False, "exists": True, "path": str(md_path)}, "error": None}

        # Ordner anlegen
        md_path.parent.mkdir(parents=True, exist_ok=True)

        # GEÄNDERT: Volles ("reiches") Frontmatter-Schema — geteilt von App-Route,
        # _templates/iteration.md und den Dataview-Tabellen in den Concept-Notizen.
        # DB-Link-Felder werden befüllt; editoriale Felder als Platzhalter (später ausfüllen).
        parent = iteration.parent_iteration_id if iteration.parent_iteration_id is not None else "null"
        frontmatter = (
            "---\n"
            "type: strategy-iteration\n"
            f"iteration_id: {iteration.id}\n"
            f"concept_id: {concept.id}\n"
            f"concept_slug: {concept.slug}\n"
            f"version: {iteration.version}\n"
            f"iteration: \"v{iteration.version}\"\n"
            f"parent_iteration_id: {parent}\n"
            "status: idea\n"
            "workflow_state: drafted\n"
            "archetype: null\n"
            "hypothesis: \"\"\n"
            "verdict: \"\"\n"
            "metrics:\n"
            "  total_return_pct: null\n"
            "  sharpe: null\n"
            "  max_drawdown: null\n"
            "  profit_factor: null\n"
            "  win_rate: null\n"
            "  trades: null\n"
            "  period: null\n"
            "result_ids: []\n"
            f"created_at: {date.today().isoformat()}\n"
            "---\n"
            "\n"
            f"# v{iteration.version}\n"
            "\n"
        )
        md_path.write_text(frontmatter, encoding='utf-8')

        return {"data": {"created": True, "exists": True, "path": str(md_path)}, "error": None}
    finally:
        session.close()


@router.post('/iterations/{iteration_id}/favorite')
def toggle_iteration_favorite(iteration_id: int):
    """Favoriten-Flag der Iteration toggeln (Stern an/aus).

    Args:
        iteration_id: Primärschlüssel der Iteration.

    Returns:
        JSON mit id und neuem is_favorite-Status.
    """
    session = get_session()
    try:
        iteration = get_iteration(session, iteration_id)
        if iteration is None:
            raise HTTPException(status_code=404, detail=f"Iteration {iteration_id} nicht gefunden.")
        iteration.is_favorite = not bool(iteration.is_favorite)
        session.commit()
        return {"data": {"id": iteration_id, "is_favorite": bool(iteration.is_favorite)}, "error": None}
    finally:
        session.close()


# GEÄNDERT: Doku-Favoriten-Toggle für Iterationen (roter Stern, unabhängig vom gelben)
# HINWEIS: Falls künftig ein Iterations-Bulk-Delete ("Alle löschen") entsteht, muss er
# sowohl is_favorite == False ALS AUCH is_doc_favorite == False filtern (beide Stern-
# Markierungen schützen vor Löschung).
@router.post('/iterations/{iteration_id}/doc_favorite')
def toggle_iteration_doc_favorite(iteration_id: int):
    """Doku-Favoriten-Flag der Iteration toggeln (roter Stern an/aus)."""
    session = get_session()
    try:
        iteration = get_iteration(session, iteration_id)
        if iteration is None:
            raise HTTPException(status_code=404, detail=f"Iteration {iteration_id} nicht gefunden.")
        iteration.is_doc_favorite = not bool(iteration.is_doc_favorite)
        session.commit()
        return {"data": {"id": iteration_id, "is_doc_favorite": bool(iteration.is_doc_favorite)}, "error": None}
    finally:
        session.close()


@router.delete('/iterations/{iteration_id}')
def delete_iteration_endpoint(
    iteration_id: int,
    delete_vault: bool = Query(default=False),
    force: bool = Query(default=False),
):
    """Iteration löschen — optional inkl. Obsidian-Ordner und abhängigen Datensätzen.

    Args:
        iteration_id: Primärschlüssel der Iteration.
        delete_vault: Wenn True, wird der Iterations-Ordner im Obsidian-Vault
            (inkl. aller Dateien darin) ebenfalls entfernt.
        force: Wenn True, werden alle referenzierenden Datensätze (BacktestRuns,
            BacktestResults, Child-Iterationen) vor dem Löschen entfernt.

    Returns:
        JSON mit deleted, id, vault_deleted (bool) und ggf. vault_path.
        Bei Blockierung ohne force=True: 409 mit Zählern der Blocker.
    """
    session = get_session()
    try:
        iteration = get_iteration(session, iteration_id)
        if iteration is None:
            raise HTTPException(status_code=404, detail=f"Iteration {iteration_id} nicht gefunden.")
        concept = get_concept(session, iteration.concept_id)
        slug = concept.slug if concept else ''
        version = iteration.version
        vault_dir_path = iteration_dir(slug, version) if slug else None

        # Blocker prüfen bevor Löschversuch
        blockers = get_iteration_blockers(session, iteration_id)
        has_blockers = any(v > 0 for v in blockers.values())

        if has_blockers and not force:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": (
                        "Iteration kann nicht gelöscht werden — es existieren noch "
                        "referenzierende Datensätze. Verwende force=true um sie mitzulöschen."
                    ),
                    "blockers": blockers,
                },
            )

        if force and has_blockers:
            deleted = force_delete_iteration(session, iteration_id)
        else:
            deleted = delete_iteration(session, iteration_id)

        if not deleted:
            raise HTTPException(status_code=404, detail=f"Iteration {iteration_id} nicht gefunden.")

        vault_deleted = False
        if delete_vault and vault_dir_path is not None and vault_dir_path.exists():
            shutil.rmtree(vault_dir_path)
            vault_deleted = True

        return {
            "data": {
                "deleted": True,
                "id": iteration_id,
                "force": force,
                "vault_deleted": vault_deleted,
                "vault_path": str(vault_dir_path) if vault_dir_path else None,
            },
            "error": None,
        }
    finally:
        session.close()


# ============================================================================
# Export / Import — Konzept und Iteration als eigenständige JSON-Dateien
# ============================================================================

async def _read_uploaded_json(file: UploadFile) -> Dict[str, Any]:
    """Liest eine hochgeladene Datei und parst sie als JSON-Objekt.

    Args:
        file: Hochgeladene Datei (FastAPI UploadFile).

    Returns:
        Das geparste JSON als Dict.

    Raises:
        HTTPException: Datei nicht lesbar oder kein JSON-Objekt.
    """
    raw = await file.read()
    try:
        payload = json.loads(raw.decode('utf-8'))
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Datei ist kein gültiges JSON: {exc}")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON-Wurzel muss ein Objekt sein.")
    return payload


@router.post('/concepts/{concept_id}/export')
def export_concept_endpoint(concept_id: int):
    """Exportiert ein Konzept als JSON-Datei in den Backup-Ordner."""
    session = get_session()
    try:
        path = export_concept(session, concept_id)
        return {"data": {"path": str(path)}, "error": None}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    finally:
        session.close()


@router.post('/concepts/import')
async def import_concept_endpoint(file: UploadFile = File(...)):
    """Importiert ein Konzept aus einer hochgeladenen JSON-Datei."""
    payload = await _read_uploaded_json(file)
    session = get_session()
    try:
        concept, action = import_concept(session, payload)
        return {"data": {**_concept_to_dict(concept), "action": action}, "error": None}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        session.close()


@router.post('/iterations/{iteration_id}/export')
def export_iteration_endpoint(iteration_id: int):
    """Exportiert eine Iteration als JSON-Datei in den Backup-Ordner."""
    session = get_session()
    try:
        path = export_iteration(session, iteration_id)
        return {"data": {"path": str(path)}, "error": None}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    finally:
        session.close()


@router.post('/concepts/{concept_id}/import-iteration')
async def import_iteration_endpoint(concept_id: int, file: UploadFile = File(...)):
    """Importiert eine Iteration als neue Version in das angegebene Konzept."""
    payload = await _read_uploaded_json(file)
    session = get_session()
    try:
        iteration = import_iteration(session, concept_id, payload)
        concept = get_concept(session, concept_id)
        slug = concept.slug if concept else ''
        return {"data": _iteration_to_dict(iteration, slug), "error": None}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        session.close()
