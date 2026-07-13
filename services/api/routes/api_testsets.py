"""
API-Endpoints für TestSets

GET    /api/testsets                 — Alle TestSets auflisten
GET    /api/testsets/{id}            — Einzelnes TestSet abrufen
POST   /api/testsets                 — Neues TestSet anlegen
PUT    /api/testsets/{id}            — TestSet aktualisieren
POST   /api/testsets/{id}/favorite   — Favoriten-Stern umschalten
DELETE /api/testsets/{id}            — TestSet löschen
"""
# GEÄNDERT: Ticket 13 — Naming-Cleanup auf api_testsets, Prefix /api/testsets

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from user_data.utils.database.db import get_session
from user_data.utils.database.repository_testsets import (
    create_testset,
    delete_testset,
    get_testset,
    list_testsets,
    toggle_testset_favorite,
    update_testset,
)

router = APIRouter(prefix='/api/testsets', tags=['testsets'])


# --- Pydantic Schemas ---

class TestSetIn(BaseModel):
    """Eingabe-Schema für TestSet (Create)."""
    name: str
    description: Optional[str] = None
    backtest_config_ids: List[int]
    created_by: Optional[str] = None
    leaderboard_enabled: bool = False


class TestSetUpdateIn(BaseModel):
    """Eingabe-Schema für TestSet (Update) -- alle Felder optional."""
    name: Optional[str] = None
    description: Optional[str] = None
    backtest_config_ids: Optional[List[int]] = None
    created_by: Optional[str] = None
    leaderboard_enabled: Optional[bool] = None


class TestSetOut(BaseModel):
    """Ausgabe-Schema für TestSet."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    # GEÄNDERT: Ticket 15 Code-Sweep — API-Vertrag behält backtest_config_ids (kein _json),
    # validation_alias liest ORM-Attribut backtest_config_ids_json (from_attributes=True)
    backtest_config_ids: List[int] = Field(validation_alias='backtest_config_ids_json')
    leaderboard_enabled: bool
    # GEÄNDERT: Favoriten-Stern — wird nur über den Toggle-Endpunkt geändert,
    # nicht über Create/Update (Muster wie bei BacktestConfig).
    is_favorite: int
    created_at: datetime
    created_by: Optional[str] = None


# --- Endpoints ---

@router.get('')
def list_testsets_endpoint():
    """Alle TestSets auflisten."""
    session = get_session()
    try:
        items = list_testsets(session)
        return {
            'data': [TestSetOut.model_validate(ts).model_dump(mode='json') for ts in items],
            'error': None,
        }
    finally:
        session.close()


@router.get('/{testset_id}')
def get_testset_endpoint(testset_id: int):
    """Einzelnes TestSet abrufen."""
    session = get_session()
    try:
        ts = get_testset(session, testset_id)
        if ts is None:
            raise HTTPException(status_code=404, detail=f'TestSet {testset_id} nicht gefunden.')
        return {'data': TestSetOut.model_validate(ts).model_dump(mode='json'), 'error': None}
    finally:
        session.close()


@router.post('')
def create_testset_endpoint(payload: TestSetIn):
    """Neues TestSet anlegen. Validiert alle backtest_config_ids."""
    session = get_session()
    try:
        ts = create_testset(
            session=session,
            name=payload.name,
            backtest_config_ids=payload.backtest_config_ids,
            description=payload.description,
            created_by=payload.created_by,
            leaderboard_enabled=payload.leaderboard_enabled,
        )
        return {'data': TestSetOut.model_validate(ts).model_dump(mode='json'), 'error': None}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        session.close()


@router.put('/{testset_id}')
def update_testset_endpoint(testset_id: int, payload: TestSetUpdateIn):
    """TestSet aktualisieren. Validiert backtest_config_ids wenn angegeben."""
    session = get_session()
    try:
        ts = update_testset(
            session=session,
            testset_id=testset_id,
            name=payload.name,
            description=payload.description,
            backtest_config_ids=payload.backtest_config_ids,
            created_by=payload.created_by,
            leaderboard_enabled=payload.leaderboard_enabled,
        )
        if ts is None:
            raise HTTPException(status_code=404, detail=f'TestSet {testset_id} nicht gefunden.')
        return {'data': TestSetOut.model_validate(ts).model_dump(mode='json'), 'error': None}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        session.close()


@router.post('/{testset_id}/favorite')
def toggle_testset_favorite_endpoint(testset_id: int):
    """Favoriten-Stern eines TestSets umschalten."""
    session = get_session()
    try:
        ts = toggle_testset_favorite(session, testset_id)
        if ts is None:
            raise HTTPException(status_code=404, detail=f'TestSet {testset_id} nicht gefunden.')
        return {
            'data': {'id': testset_id, 'is_favorite': bool(ts.is_favorite)},
            'error': None,
        }
    finally:
        session.close()


@router.delete('/{testset_id}')
def delete_testset_endpoint(testset_id: int):
    """TestSet löschen."""
    session = get_session()
    try:
        deleted = delete_testset(session, testset_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f'TestSet {testset_id} nicht gefunden.')
        return {'data': {'deleted': True, 'id': testset_id}, 'error': None}
    finally:
        session.close()
