"""
API-Endpoints für Konfigurationen

Backtest-Configs (CRUD + Kopieren):
GET/POST       /api/config/backtest
GET/PUT/DELETE /api/config/backtest/{id}
POST           /api/config/backtest/{id}/copy

Indicator-Configs (CRUD + Kopieren):
GET/POST       /api/config/indicator
GET/PUT/DELETE /api/config/indicator/{id}
POST           /api/config/indicator/{id}/copy
POST           /api/config/indicator/{id}/generate-labels   (Name+Beschreibung nach Notation)

Strategy-Configs (CRUD):
GET/POST       /api/config/strategy
GET/PUT/DELETE /api/config/strategy/{id}

Verfügbare Symbole (aus HDF5-Dateien):
GET            /api/config/symbols?exchange=binance&timeframe=4h
"""

import glob
import os
import re
from datetime import datetime
from typing import List, Optional

import json

import pandas as pd
from fastapi import APIRouter, Body, File, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from rq import Queue
from sqlalchemy import func, text

import logging

from services.api.redis_conn import get_redis_connection, OHLC_DOWNLOAD_QUEUE_NAME
from user_data.config import Config
from user_data.utils.database.db import get_session
from user_data.utils.database.models import (
    BacktestConfig,
    IndicatorConfig,
    OhlcDownloadJob,
    StrategyConfig,
    StrategyConcept,
    StrategyIteration,
)
# GEÄNDERT: Ticket 15 — get_iteration_by_strategy_name-Import entfernt (nicht mehr benötigt)
# GEÄNDERT: Schritt 3b — '_stops'-Helper, um beim Einfrieren aus Result die Stops
# in die IndicatorConfig zu übernehmen (Snapshot führt sie nur im backtest_config).
from user_data.strategies.generic.indicator_factory import stops_from_portfolio, describe_combos
# GEÄNDERT: Single-Source-Notation für Name/Beschreibung einer Indicator-Config
from services.api.utils.indicator_labels import build_indicator_config_labels
# GEÄNDERT: Export/Import von Indicator-Configs als eigenständige JSON-Dateien
from services.api.utils.strategy_io import export_indicator_config, import_indicator_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/config', tags=['config'])


# --- Pydantic Schemas ---

class BacktestConfigIn(BaseModel):
    """Eingabe-Schema für Backtest-Config (Create/Update)."""
    name: str
    description: Optional[str] = None
    symbol: str = 'BTCUSDT'
    exchange: str = 'binance'
    timeframe: str = '4h'
    start: str
    end: str
    ohlc_start: str
    ohlc_end: str
    size: float = 100
    size_type: str = 'value'
    init_cash: float = 100
    fees: float = 0.001


class BacktestConfigOut(BaseModel):
    """Ausgabe-Schema für Backtest-Config."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    symbol: str
    exchange: str
    timeframe: str
    start: str
    end: str
    ohlc_start: str
    ohlc_end: str
    size: float
    size_type: str
    init_cash: float
    fees: float
    is_favorite: int
    created_at: datetime
    updated_at: Optional[datetime] = None


# --- Endpoints ---

@router.get('/backtest')
def list_configs():
    """Alle Backtest-Configs auflisten (Favoriten zuerst)."""
    session = get_session()
    try:
        configs = session.query(BacktestConfig).order_by(
            BacktestConfig.is_favorite.desc(),
            BacktestConfig.name
        ).all()
        items = [BacktestConfigOut.model_validate(c).model_dump(mode='json') for c in configs]
        return {'data': items, 'error': None}
    finally:
        session.close()


@router.get('/backtest/{config_id}')
def get_config(config_id: int):
    """Einzelne Backtest-Config laden."""
    session = get_session()
    try:
        config = session.query(BacktestConfig).filter(BacktestConfig.id == config_id).first()
        if not config:
            return JSONResponse({'data': None, 'error': 'Config nicht gefunden'}, status_code=404)
        return {'data': BacktestConfigOut.model_validate(config).model_dump(mode='json'), 'error': None}
    finally:
        session.close()


@router.post('/backtest')
def create_config(data: BacktestConfigIn):
    """Neue Backtest-Config anlegen."""
    session = get_session()
    try:
        # GEÄNDERT: is_favorite wird nicht beim Anlegen gesetzt (Default 0),
        # sondern ausschließlich über den Toggle-Endpoint markiert.
        config = BacktestConfig(
            name=data.name,
            description=data.description,
            symbol=data.symbol,
            exchange=data.exchange,
            timeframe=data.timeframe,
            start=data.start,
            end=data.end,
            ohlc_start=data.ohlc_start,
            ohlc_end=data.ohlc_end,
            size=data.size,
            size_type=data.size_type,
            init_cash=data.init_cash,
            fees=data.fees,
        )
        session.add(config)
        session.commit()
        session.refresh(config)
        return {'data': BacktestConfigOut.model_validate(config).model_dump(mode='json'), 'error': None}
    finally:
        session.close()


@router.put('/backtest/{config_id}')
def update_config(config_id: int, data: BacktestConfigIn):
    """Bestehende Backtest-Config aktualisieren."""
    session = get_session()
    try:
        config = session.query(BacktestConfig).filter(BacktestConfig.id == config_id).first()
        if not config:
            return JSONResponse({'data': None, 'error': 'Config nicht gefunden'}, status_code=404)

        # GEÄNDERT: is_favorite wird beim Speichern bewusst NICHT angefasst —
        # die Markierung läuft nur über den Toggle-Endpoint (Stern in der Tabelle).
        config.name = data.name
        config.description = data.description
        config.symbol = data.symbol
        config.exchange = data.exchange
        config.timeframe = data.timeframe
        config.start = data.start
        config.end = data.end
        config.ohlc_start = data.ohlc_start
        config.ohlc_end = data.ohlc_end
        config.size = data.size
        config.size_type = data.size_type
        config.init_cash = data.init_cash
        config.fees = data.fees
        config.updated_at = datetime.now()

        session.commit()
        session.refresh(config)
        return {'data': BacktestConfigOut.model_validate(config).model_dump(mode='json'), 'error': None}
    finally:
        session.close()


@router.delete('/backtest/{config_id}')
def delete_config(config_id: int):
    """Backtest-Config löschen."""
    session = get_session()
    try:
        config = session.query(BacktestConfig).filter(BacktestConfig.id == config_id).first()
        if not config:
            return JSONResponse({'data': None, 'error': 'Config nicht gefunden'}, status_code=404)
        session.delete(config)
        session.commit()
        return {'data': {'deleted': config_id}, 'error': None}
    finally:
        session.close()


@router.post('/backtest/{config_id}/copy')
def copy_config(config_id: int):
    """Bestehende Config kopieren mit neuem Namen."""
    session = get_session()
    try:
        original = session.query(BacktestConfig).filter(BacktestConfig.id == config_id).first()
        if not original:
            return JSONResponse({'data': None, 'error': 'Config nicht gefunden'}, status_code=404)

        copy = BacktestConfig(
            name=f"{original.name} (Kopie)",
            description=original.description,
            symbol=original.symbol,
            exchange=original.exchange,
            timeframe=original.timeframe,
            start=original.start,
            end=original.end,
            ohlc_start=original.ohlc_start,
            ohlc_end=original.ohlc_end,
            size=original.size,
            size_type=original.size_type,
            init_cash=original.init_cash,
            fees=original.fees,
        )
        session.add(copy)
        session.commit()
        session.refresh(copy)
        return {'data': BacktestConfigOut.model_validate(copy).model_dump(mode='json'), 'error': None}
    finally:
        session.close()


# GEÄNDERT: Ticket 43 — BacktestConfig aus vollständigem Config-Snapshot eines Results anlegen
@router.post('/backtest/from-result/{result_id}')
def create_backtest_config_from_result(result_id: int):
    """Speichert eine BacktestConfig aus dem vollständigen Config-Snapshot eines Results.

    Liest ausschließlich aus full_config_snapshot_json['backtest_config'] —
    kein Zugriff auf Run, Iteration oder Concept. Fehlender Snapshot wird
    sichtbar abgewiesen (kein stiller Fehlschlag).
    """
    from user_data.utils.database.models import BacktestResult

    session = get_session()
    try:
        result = session.query(BacktestResult).filter(BacktestResult.id == result_id).first()
        if not result:
            return JSONResponse({'data': None, 'error': f'Result {result_id} nicht gefunden'}, status_code=404)

        snapshot = result.full_config_snapshot_json
        if not snapshot or 'backtest_config' not in snapshot:
            return JSONResponse(
                {'data': None, 'error': f'Result {result_id} hat keinen vollständigen Config-Snapshot (full_config_snapshot_json fehlt oder ist unvollständig). Neuere Results tragen den Snapshot automatisch.'},
                status_code=422,
            )

        bc = snapshot['backtest_config']

        # Pflicht-Felder prüfen
        # GEÄNDERT: Schritt 3d — delta_format/time_delta_format sind keine
        # BacktestConfig-Felder mehr (leben in '_stops'), daher nicht mehr Pflicht hier.
        for required in ('ohlc_start', 'ohlc_end'):
            if not bc.get(required):
                return JSONResponse(
                    {'data': None, 'error': f'Snapshot unvollständig: Feld "{required}" fehlt. Result muss neu berechnet werden.'},
                    status_code=422,
                )

        config = BacktestConfig(
            name=f'Aus Result {result_id} — {bc.get("symbol", "")} {bc.get("timeframe", "")}',
            description=f'Gespeichert aus Backtest-Result {result_id}.',
            symbol=bc.get('symbol', 'BTCUSDT'),
            exchange=bc.get('exchange', 'binance'),
            timeframe=bc.get('timeframe', '4h'),
            start=bc.get('start', ''),
            end=bc.get('end', ''),
            ohlc_start=bc['ohlc_start'],
            ohlc_end=bc['ohlc_end'],
            size=bc.get('size', 100),
            size_type=bc.get('size_type', 'value'),
            init_cash=bc.get('init_cash', 100),
            fees=bc.get('fees', 0.001),
        )
        session.add(config)
        session.commit()
        session.refresh(config)
        return {'data': BacktestConfigOut.model_validate(config).model_dump(mode='json'), 'error': None}
    finally:
        session.close()


# GEÄNDERT: Favoriten-Toggle für Backtest-Configs (Stern an/aus, nicht-exklusiv),
# analog zum Iterations-Favoriten. Ersetzt das frühere exklusive Default-Flag.
@router.post('/backtest/{config_id}/favorite')
def toggle_backtest_config_favorite(config_id: int):
    """Favoriten-Flag der Backtest-Config toggeln (Stern an/aus)."""
    session = get_session()
    try:
        config = session.query(BacktestConfig).filter(BacktestConfig.id == config_id).first()
        if not config:
            return JSONResponse({'data': None, 'error': 'Config nicht gefunden'}, status_code=404)
        config.is_favorite = 0 if config.is_favorite else 1
        session.commit()
        return {'data': {'id': config_id, 'is_favorite': bool(config.is_favorite)}, 'error': None}
    finally:
        session.close()


# ============================================================================
# Indicator-Configs
# ============================================================================

class IndicatorConfigIn(BaseModel):
    """Eingabe-Schema für Indicator-Config (Create/Update)."""
    name: str
    description: Optional[str] = None
    # GEÄNDERT: Ticket 22 — lose Verknüpfung zu Concept/Iteration (kein FK)
    strategy_concept_id: Optional[int] = None
    strategy_iteration_id: Optional[int] = None
    config_json: dict
    is_default: int = 0


class IndicatorConfigFromResultIn(BaseModel):
    """Eingabe-Schema für das Einfrieren einer IndicatorConfig aus einem Result.

    Alle Felder optional: Ohne name wird er nach Konvention generiert
    (`<KONZEPT> <version> / <segment> / <result_id>`).
    """
    name: Optional[str] = None
    description: Optional[str] = None
    segment: Optional[str] = None


class IndicatorConfigOut(BaseModel):
    """Ausgabe-Schema für Indicator-Config."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    # GEÄNDERT: Ticket 22 — lose Verknüpfung zu Concept/Iteration (kein FK)
    strategy_concept_id: Optional[int] = None
    strategy_iteration_id: Optional[int] = None
    # GEÄNDERT: Ticket 22 — Read-Only-Lookups; NULL wenn Ziel gelöscht
    strategy_concept_name: Optional[str] = None
    strategy_iteration_version: Optional[str] = None
    # GEÄNDERT: Versionsnummer (Integer) zusätzlich zur Anzeige in der Liste
    strategy_iteration_number: Optional[int] = None
    config_json: dict
    is_default: int
    created_at: datetime
    updated_at: Optional[datetime] = None


def _enrich_indicator_config_dict(item: dict, concept_map: dict, iteration_map: dict) -> None:
    """Fügt die Read-Only-Lookup-Felder concept_name/iteration_version/iteration_number in das dict ein."""
    cid = item.get('strategy_concept_id')
    iid = item.get('strategy_iteration_id')
    item['strategy_concept_name'] = concept_map.get(cid) if cid else None
    # GEÄNDERT: iteration_map trägt jetzt {version, version_name} — Anzeige-Label und Nummer ableiten
    it_info = iteration_map.get(iid) if iid else None
    if it_info:
        item['strategy_iteration_version'] = it_info['version_name'] or it_info['version']
        item['strategy_iteration_number'] = it_info['version']
    else:
        item['strategy_iteration_version'] = None
        item['strategy_iteration_number'] = None


def _load_concept_iteration_maps(session) -> tuple[dict, dict]:
    """Lädt Lookup-Maps {concept_id: name} und {iteration_id: {version, version_name}}."""
    concept_map = {c.id: c.name for c in session.query(StrategyConcept).all()}
    # GEÄNDERT: Nummer und Name getrennt vorhalten (Anzeige bevorzugt Name mit Fallback auf Nummer)
    iteration_map = {
        it.id: {'version': it.version, 'version_name': it.version_name}
        for it in session.query(StrategyIteration).all()
    }
    return concept_map, iteration_map


@router.get('/indicator')
def list_indicator_configs(
    concept_id: Optional[int] = Query(None),
    iteration_id: Optional[int] = Query(None),
):
    """Alle Indicator-Configs auflisten.

    Wenn concept_id/iteration_id gesetzt sind, werden die Einträge in drei Buckets sortiert:
    1) exakter Concept+Iteration-Match, 2) nur Concept-Match, 3) Rest.
    Innerhalb jedes Buckets: is_default DESC, Iterations-Version DESC, name ASC.
    Ohne Query-Params: is_default DESC, Iterations-Version DESC, name ASC.
    """
    session = get_session()
    try:
        # GEÄNDERT: Maps vorab laden, damit die Iterations-Version als Sortierschlüssel
        # (hoch nach klein) verfügbar ist
        concept_map, iteration_map = _load_concept_iteration_maps(session)
        version_map = {it.id: (it.version or 0) for it in session.query(StrategyIteration).all()}
        all_configs = session.query(IndicatorConfig).all()

        def _sort_key(c):
            if concept_id is None and iteration_id is None:
                bucket = 0
            elif concept_id is not None and c.strategy_concept_id == concept_id and \
                    iteration_id is not None and c.strategy_iteration_id == iteration_id:
                bucket = 0
            elif concept_id is not None and c.strategy_concept_id == concept_id:
                bucket = 1
            else:
                bucket = 2
            # Innerhalb Bucket: is_default DESC, Iterations-Version DESC, name ASC
            version = version_map.get(c.strategy_iteration_id, 0) if c.strategy_iteration_id else 0
            return (bucket, -(c.is_default or 0), -version, (c.name or '').lower())

        configs = sorted(all_configs, key=_sort_key)
        items = [IndicatorConfigOut.model_validate(c).model_dump(mode='json') for c in configs]
        for item in items:
            _enrich_indicator_config_dict(item, concept_map, iteration_map)

        return {'data': items, 'error': None}
    finally:
        session.close()


@router.get('/indicator/{config_id}')
def get_indicator_config(config_id: int):
    """Einzelne Indicator-Config laden."""
    session = get_session()
    try:
        config = session.query(IndicatorConfig).filter(IndicatorConfig.id == config_id).first()
        if not config:
            return JSONResponse({'data': None, 'error': 'Config nicht gefunden'}, status_code=404)
        concept_map, iteration_map = _load_concept_iteration_maps(session)
        item = IndicatorConfigOut.model_validate(config).model_dump(mode='json')
        _enrich_indicator_config_dict(item, concept_map, iteration_map)
        return {'data': item, 'error': None}
    finally:
        session.close()


@router.post('/indicator')
def create_indicator_config(data: IndicatorConfigIn):
    """Neue Indicator-Config anlegen."""
    session = get_session()
    try:
        if data.is_default:
            session.query(IndicatorConfig).update({IndicatorConfig.is_default: 0})

        config = IndicatorConfig(
            name=data.name,
            description=data.description,
            # GEÄNDERT: Ticket 22 — lose Verknüpfung Concept/Iteration
            strategy_concept_id=data.strategy_concept_id,
            strategy_iteration_id=data.strategy_iteration_id,
            config_json=data.config_json,
            is_default=data.is_default,
        )
        session.add(config)
        session.commit()
        session.refresh(config)
        concept_map, iteration_map = _load_concept_iteration_maps(session)
        item = IndicatorConfigOut.model_validate(config).model_dump(mode='json')
        _enrich_indicator_config_dict(item, concept_map, iteration_map)
        return {'data': item, 'error': None}
    finally:
        session.close()


# GEÄNDERT: Ticket 43 — auf Snapshot umgestellt; kein Zugriff mehr auf Run/Iteration/Concept
@router.post('/indicator/from-result/{result_id}')
def create_indicator_config_from_result(result_id: int, body: IndicatorConfigFromResultIn = Body(default=None)):
    """Friert eine IndicatorConfig aus dem vollständigen Config-Snapshot eines Results ein.

    Liest ausschließlich aus full_config_snapshot_json['indicators'] —
    kein Zugriff mehr auf Run, Iteration oder Concept. Der Snapshot liefert
    bereits aufgelöste Werte (keine Range-Auflösung mehr nötig).
    Fehlender Snapshot wird sichtbar abgewiesen (kein stiller Fehlschlag).
    """
    from user_data.utils.database.models import BacktestResult

    payload = body or IndicatorConfigFromResultIn()
    session = get_session()
    try:
        result = session.query(BacktestResult).filter(BacktestResult.id == result_id).first()
        if not result:
            return JSONResponse({'data': None, 'error': f'Result {result_id} nicht gefunden'}, status_code=404)

        snapshot = result.full_config_snapshot_json
        if not snapshot or 'indicators' not in snapshot:
            return JSONResponse(
                {'data': None, 'error': f'Result {result_id} hat keinen vollständigen Config-Snapshot (full_config_snapshot_json fehlt oder ist unvollständig). Neuere Results tragen den Snapshot automatisch.'},
                status_code=422,
            )

        # Snapshot liefert bereits aufgelöste Flat-Spec — direkt übernehmen
        frozen = snapshot['indicators']
        if not isinstance(frozen, dict):
            return JSONResponse(
                {'data': None, 'error': f'Snapshot-Indikatoren in Result {result_id} sind kein Dict.'},
                status_code=422,
            )

        # GEÄNDERT: Schritt 3b — Stops in die eingefrorene Config übernehmen. Der
        # Snapshot führt die per-Result aufgelösten Stops top-level im
        # backtest_config (nicht unter 'portfolio', nicht unter 'indicators').
        # stops_from_portfolio liest die 5 STOP_PARAM_KEYS, daher direkt anwenden.
        # Defensive Kopie, damit der gespeicherte Snapshot nicht mutiert wird.
        frozen = dict(frozen)
        frozen['_stops'] = stops_from_portfolio(snapshot.get('backtest_config') or {})
        # GEÄNDERT: Schritt 3d — Die Stop-Formate gehören ebenfalls zu '_stops'.
        # stops_from_portfolio liefert nur die 5 STOP_PARAM_KEYS, daher die zwei
        # Formate hier aus dem Snapshot-backtest_config ergänzen (Snapshot führt
        # sie top-level, siehe _build_full_config_snapshot).
        _bc_snapshot = snapshot.get('backtest_config') or {}
        frozen['_stops']['delta_format'] = _bc_snapshot.get('delta_format')
        frozen['_stops']['time_delta_format'] = _bc_snapshot.get('time_delta_format')

        # Name nach Konvention generieren, falls nicht vorgegeben
        name = payload.name
        if not name:
            bc = snapshot.get('backtest_config') or {}
            symbol = bc.get('symbol', '')
            tf = bc.get('timeframe', '')
            segment = f' / {payload.segment}' if payload.segment else ''
            name = f'Indikatoren {symbol} {tf}{segment} / {result_id}'

        config = IndicatorConfig(
            name=name,
            description=payload.description or f'Eingefroren aus Result {result_id}.',
            strategy_concept_id=None,
            strategy_iteration_id=None,
            config_json=frozen,
            is_default=0,
        )
        session.add(config)
        session.commit()
        session.refresh(config)
        concept_map, iteration_map = _load_concept_iteration_maps(session)
        item = IndicatorConfigOut.model_validate(config).model_dump(mode='json')
        _enrich_indicator_config_dict(item, concept_map, iteration_map)
        return {'data': item, 'error': None}
    finally:
        session.close()


@router.put('/indicator/{config_id}')
def update_indicator_config(config_id: int, data: IndicatorConfigIn):
    """Bestehende Indicator-Config aktualisieren."""
    session = get_session()
    try:
        config = session.query(IndicatorConfig).filter(IndicatorConfig.id == config_id).first()
        if not config:
            return JSONResponse({'data': None, 'error': 'Config nicht gefunden'}, status_code=404)

        if data.is_default:
            session.query(IndicatorConfig).filter(
                IndicatorConfig.id != config_id
            ).update({IndicatorConfig.is_default: 0})

        config.name = data.name
        config.description = data.description
        # GEÄNDERT: Ticket 22 — lose Verknüpfung Concept/Iteration
        config.strategy_concept_id = data.strategy_concept_id
        config.strategy_iteration_id = data.strategy_iteration_id
        config.config_json = data.config_json
        config.is_default = data.is_default
        config.updated_at = datetime.now()

        session.commit()
        session.refresh(config)
        concept_map, iteration_map = _load_concept_iteration_maps(session)
        item = IndicatorConfigOut.model_validate(config).model_dump(mode='json')
        _enrich_indicator_config_dict(item, concept_map, iteration_map)
        return {'data': item, 'error': None}
    finally:
        session.close()


@router.post('/indicator/{config_id}/generate-labels')
def generate_indicator_config_labels(config_id: int):
    """Erzeugt Name und Beschreibung einer bestehenden Indicator-Config nach Notation.

    Single Source: nutzt services.api.utils.indicator_labels (dieselbe Notation wie
    die Frontend-Buttons). Berechnet aus config_json + verknüpftem Konzept/Iteration,
    schreibt die Werte in den Datensatz zurück und gibt die aktualisierte Config zurück.
    """
    session = get_session()
    try:
        config = session.query(IndicatorConfig).filter(IndicatorConfig.id == config_id).first()
        if not config:
            return JSONResponse({'data': None, 'error': 'Config nicht gefunden'}, status_code=404)

        # Konzept-Name (verbatim) und Iterations-Nummer (version) über die lose Verknüpfung auflösen
        concept_name = None
        if config.strategy_concept_id:
            concept = session.query(StrategyConcept).filter(
                StrategyConcept.id == config.strategy_concept_id
            ).first()
            concept_name = concept.name if concept else None

        iteration_number = None
        if config.strategy_iteration_id:
            iteration = session.query(StrategyIteration).filter(
                StrategyIteration.id == config.strategy_iteration_id
            ).first()
            iteration_number = iteration.version if iteration else None

        labels = build_indicator_config_labels(config.config_json or {}, concept_name, iteration_number)
        config.name = labels['name']
        config.description = labels['description']
        config.updated_at = datetime.now()
        session.commit()
        session.refresh(config)

        concept_map, iteration_map = _load_concept_iteration_maps(session)
        item = IndicatorConfigOut.model_validate(config).model_dump(mode='json')
        _enrich_indicator_config_dict(item, concept_map, iteration_map)
        return {'data': item, 'error': None}
    finally:
        session.close()


@router.post('/indicator/count-combos')
def count_indicator_config_combos(config_json: dict = Body(..., embed=True)):
    """Berechnet die Anzahl aller Kombinationen eines config_json (zustandslos).

    Single Source: nutzt count_total_combos aus indicator_factory — exakt die Zahl,
    die der Motor laeuft (Indikator-Kombis x Stop-Kombis, Listen und gekoppeltes
    TSL-Paar inklusive). Die Frontend-Buttons rufen diesen Endpunkt statt eigener
    JS-Mathematik, damit es nur eine Zaehl-Implementierung gibt.
    """
    try:
        result = describe_combos(config_json or {})
        return {'data': result, 'error': None}
    except ValueError as exc:
        # z.B. TSL-Paar-Laengen-Mismatch — als klare Fehlermeldung zurueckgeben
        return JSONResponse({'data': None, 'error': str(exc)}, status_code=400)


@router.delete('/indicator/{config_id}')
def delete_indicator_config(config_id: int):
    """Indicator-Config löschen."""
    session = get_session()
    try:
        config = session.query(IndicatorConfig).filter(IndicatorConfig.id == config_id).first()
        if not config:
            return JSONResponse({'data': None, 'error': 'Config nicht gefunden'}, status_code=404)
        session.delete(config)
        session.commit()
        return {'data': {'deleted': config_id}, 'error': None}
    finally:
        session.close()


@router.post('/indicator/bulk-delete')
def bulk_delete_indicator_configs(request_body: dict):
    """Mehrere Indicator-Configs auf einmal löschen."""
    ids = request_body.get('ids', [])
    if not ids:
        return {'data': {'deleted': 0}, 'error': None}
    session = get_session()
    try:
        deleted = session.query(IndicatorConfig).filter(IndicatorConfig.id.in_(ids)).delete()
        session.commit()
        return {'data': {'deleted': deleted}, 'error': None}
    finally:
        session.close()


@router.post('/indicator/{config_id}/copy')
def copy_indicator_config(config_id: int):
    """Bestehende Indicator-Config kopieren."""
    session = get_session()
    try:
        original = session.query(IndicatorConfig).filter(IndicatorConfig.id == config_id).first()
        if not original:
            return JSONResponse({'data': None, 'error': 'Config nicht gefunden'}, status_code=404)

        copy = IndicatorConfig(
            name=f"{original.name} (Kopie)",
            description=original.description,
            config_json=original.config_json,
            is_default=0,
            # GEÄNDERT: Ticket 22 — Concept/Iteration-Verknüpfung mitkopieren
            strategy_concept_id=original.strategy_concept_id,
            strategy_iteration_id=original.strategy_iteration_id,
        )
        session.add(copy)
        session.commit()
        session.refresh(copy)
        concept_map, iteration_map = _load_concept_iteration_maps(session)
        item = IndicatorConfigOut.model_validate(copy).model_dump(mode='json')
        _enrich_indicator_config_dict(item, concept_map, iteration_map)
        return {'data': item, 'error': None}
    finally:
        session.close()


@router.post('/indicator/{config_id}/export')
def export_indicator_config_endpoint(config_id: int):
    """Exportiert eine Indicator-Config als JSON-Datei in den Backup-Ordner."""
    session = get_session()
    try:
        path = export_indicator_config(session, config_id)
        return {'data': {'path': str(path)}, 'error': None}
    except ValueError as exc:
        return JSONResponse({'data': None, 'error': str(exc)}, status_code=404)
    finally:
        session.close()


@router.post('/indicator/import')
async def import_indicator_config_endpoint(
    file: UploadFile = File(...),
    strategy_concept_id: Optional[int] = Query(None),
    strategy_iteration_id: Optional[int] = Query(None),
):
    """Importiert eine Indicator-Config aus einer hochgeladenen JSON-Datei.

    Optional kann die neue Config über Query-Parameter mit einem Konzept oder
    einer Iteration verknüpft werden.
    """
    raw = await file.read()
    try:
        payload = json.loads(raw.decode('utf-8'))
    except (ValueError, UnicodeDecodeError) as exc:
        return JSONResponse({'data': None, 'error': f"Datei ist kein gültiges JSON: {exc}"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({'data': None, 'error': 'JSON-Wurzel muss ein Objekt sein.'}, status_code=400)
    session = get_session()
    try:
        config = import_indicator_config(
            session, payload,
            strategy_concept_id=strategy_concept_id,
            strategy_iteration_id=strategy_iteration_id,
        )
        concept_map, iteration_map = _load_concept_iteration_maps(session)
        item = IndicatorConfigOut.model_validate(config).model_dump(mode='json')
        _enrich_indicator_config_dict(item, concept_map, iteration_map)
        return {'data': item, 'error': None}
    except ValueError as exc:
        return JSONResponse({'data': None, 'error': str(exc)}, status_code=400)
    finally:
        session.close()


# ============================================================================
# Strategy-Configs
# ============================================================================

class StrategyConfigIn(BaseModel):
    """Eingabe-Schema für Strategy-Config (Create/Update).

    XOR-Validierung: entweder import_path (bei type='hardcoded') oder
    strategy_config_json (bei type='generic') — nicht beides, nicht keines.
    """
    name: str
    description: Optional[str] = None
    strategy_family: str
    strategy_name: str
    # GEÄNDERT: Ticket 15 — Typ-Feld
    type: str = 'hardcoded'
    # GEÄNDERT: Ticket 15 — nullable (nur bei hardcoded gefüllt)
    import_path: Optional[str] = None
    # GEÄNDERT: Ticket 15 — Spec für generic
    strategy_config_json: Optional[dict] = None
    is_default: int = 0


class StrategyConfigOut(BaseModel):
    """Ausgabe-Schema für Strategy-Config."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    strategy_family: str
    strategy_name: str
    # GEÄNDERT: Ticket 15 — Typ-Feld + strategy_config_json
    type: str
    import_path: Optional[str] = None
    strategy_config_json: Optional[dict] = None
    is_default: int
    created_at: datetime
    updated_at: Optional[datetime] = None


def _validate_strategy_config_xor(type_: str, import_path: Optional[str], strategy_config_json: Optional[dict]) -> Optional[str]:
    """XOR-Validierung für StrategyConfig: hardcoded <-> generic.

    Returns:
        Fehlermeldung oder None wenn valide.
    """
    if type_ == 'hardcoded':
        if not import_path:
            return "Bei type='hardcoded' muss import_path gesetzt sein."
        if strategy_config_json is not None:
            return "Bei type='hardcoded' darf strategy_config_json nicht gesetzt sein."
    elif type_ == 'generic':
        if strategy_config_json is None:
            return "Bei type='generic' muss strategy_config_json gesetzt sein."
        if import_path:
            return "Bei type='generic' darf import_path nicht gesetzt sein."
    else:
        return f"Ungültiger type-Wert: '{type_}'. Erlaubt: 'hardcoded', 'generic'."
    return None


@router.get('/strategy')
def list_strategy_configs():
    """Alle Strategy-Configs auflisten."""
    session = get_session()
    try:
        configs = session.query(StrategyConfig).order_by(
            StrategyConfig.is_default.desc(),
            StrategyConfig.name
        ).all()
        items = [StrategyConfigOut.model_validate(c).model_dump(mode='json') for c in configs]
        return {'data': items, 'error': None}
    finally:
        session.close()


@router.get('/strategy/{config_id}')
def get_strategy_config(config_id: int):
    """Einzelne Strategy-Config laden."""
    session = get_session()
    try:
        config = session.query(StrategyConfig).filter(StrategyConfig.id == config_id).first()
        if not config:
            return JSONResponse({'data': None, 'error': 'Strategy nicht gefunden'}, status_code=404)
        return {'data': StrategyConfigOut.model_validate(config).model_dump(mode='json'), 'error': None}
    finally:
        session.close()


@router.post('/strategy')
def create_strategy_config(data: StrategyConfigIn):
    """Neue Strategy-Config anlegen."""
    # GEÄNDERT: Ticket 15 — XOR-Validierung
    err = _validate_strategy_config_xor(data.type, data.import_path, data.strategy_config_json)
    if err:
        return JSONResponse({'data': None, 'error': err}, status_code=400)

    session = get_session()
    try:
        if data.is_default:
            session.query(StrategyConfig).update({StrategyConfig.is_default: 0})

        config = StrategyConfig(
            name=data.name,
            description=data.description,
            strategy_family=data.strategy_family,
            strategy_name=data.strategy_name,
            type=data.type,
            import_path=data.import_path,
            strategy_config_json=data.strategy_config_json,
            is_default=data.is_default,
        )
        session.add(config)
        session.commit()
        session.refresh(config)
        return {'data': StrategyConfigOut.model_validate(config).model_dump(mode='json'), 'error': None}
    finally:
        session.close()


@router.put('/strategy/{config_id}')
def update_strategy_config(config_id: int, data: StrategyConfigIn):
    """Bestehende Strategy-Config aktualisieren."""
    # GEÄNDERT: Ticket 15 — XOR-Validierung
    err = _validate_strategy_config_xor(data.type, data.import_path, data.strategy_config_json)
    if err:
        return JSONResponse({'data': None, 'error': err}, status_code=400)

    session = get_session()
    try:
        config = session.query(StrategyConfig).filter(StrategyConfig.id == config_id).first()
        if not config:
            return JSONResponse({'data': None, 'error': 'Strategy nicht gefunden'}, status_code=404)

        if data.is_default:
            session.query(StrategyConfig).filter(
                StrategyConfig.id != config_id
            ).update({StrategyConfig.is_default: 0})

        config.name = data.name
        config.description = data.description
        config.strategy_family = data.strategy_family
        config.strategy_name = data.strategy_name
        # GEÄNDERT: Ticket 15 — type + nullable import_path + strategy_config_json
        config.type = data.type
        config.import_path = data.import_path
        config.strategy_config_json = data.strategy_config_json
        config.is_default = data.is_default
        config.updated_at = datetime.now()

        session.commit()
        session.refresh(config)
        return {'data': StrategyConfigOut.model_validate(config).model_dump(mode='json'), 'error': None}
    finally:
        session.close()


@router.delete('/strategy/{config_id}')
def delete_strategy_config(config_id: int):
    """Strategy-Config löschen."""
    session = get_session()
    try:
        config = session.query(StrategyConfig).filter(StrategyConfig.id == config_id).first()
        if not config:
            return JSONResponse({'data': None, 'error': 'Strategy nicht gefunden'}, status_code=404)
        session.delete(config)
        session.commit()
        return {'data': {'deleted': config_id}, 'error': None}
    finally:
        session.close()


# ============================================================================
# Verfügbare Symbole (aus HDF5-Dateien)
# ============================================================================

@router.get('/symbols')
def list_available_symbols(
    exchange: str = Query(..., description='z.B. binance'),
    timeframe: str = Query(..., description='z.B. 4h'),
):
    """Liest verfügbare Symbole aus der passenden HDF5-Datei.

    Die Datei wird erwartet unter: {DATA_PATH}/ohlcv_{timeframe}_{exchange}.h5
    Symbole sind die Top-Level-Keys im HDFStore.
    """
    filename = f'ohlcv_{timeframe}_{exchange}.h5'
    path = os.path.join(Config.DATA_PATH, filename)
    if not os.path.exists(path):
        return {
            'data': {'symbols': [], 'file': filename, 'exists': False},
            'error': f'Keine Daten-Datei gefunden: {filename}',
        }
    try:
        with pd.HDFStore(path, mode='r') as store:
            # Keys sehen aus wie '/BTCUSDT' -> führenden Slash entfernen
            symbols = sorted(k.lstrip('/') for k in store.keys())
    except Exception as exc:
        return JSONResponse(
            {'data': None, 'error': f'HDF5 lesen fehlgeschlagen: {exc}'},
            status_code=500,
        )
    return {
        'data': {'symbols': symbols, 'file': filename, 'exists': True},
        'error': None,
    }


# ============================================================================
# Daten-Verwaltung: Liste, Download, Update, Delete
# ============================================================================

_HDF_FILE_RE = re.compile(r'^ohlcv_([^_]+)_([^.]+)\.h5$')

# Timeframe -> Intervall in Sekunden (fuer die Datenqualitaets-Berechnung).
_TF_SECONDS = {
    '1m': 60, '5m': 300, '15m': 900, '30m': 1800,
    '1h': 3600, '2h': 7200, '4h': 14400, '6h': 21600,
    '12h': 43200, '1d': 86400, '1w': 604800,
}


def _quality_pct(first_ts, last_ts, nrows: int, tf_seconds: int) -> Optional[float]:
    """Datenqualitaet in Prozent: vorhandene Kerzen / im Zeitraum erwartete Kerzen.

    Erwartete Kerzen = Intervalle zwischen erster und letzter Kerze + 1. Luecken
    (z.B. fehlende Exchange-Daten) druecken den Wert unter 100. Gibt None zurueck,
    wenn die Kennzahl nicht bestimmbar ist (unbekannter Timeframe, ungueltige Zeiten).
    """
    if not tf_seconds:
        return None
    span_sec = (last_ts - first_ts).total_seconds()
    if span_sec < 0:
        return None
    expected = round(span_sec / tf_seconds) + 1
    if expected <= 0:
        return None
    return round(min(100.0, nrows / expected * 100.0), 1)


def _read_file_metadata(path: str, tf_seconds: Optional[int]) -> dict:
    """Liest pro Symbol nrows + erste/letzte Index-Zeile (schnell, ohne OHLC zu laden).

    Berechnet zusaetzlich die Datenqualitaet (Anteil vorhandener an erwarteten Kerzen),
    sofern der Timeframe (tf_seconds) bekannt ist.
    """
    symbols_info: List[dict] = []
    with pd.HDFStore(path, mode='r') as store:
        for key in sorted(store.keys()):
            symbol = key.lstrip('/')
            storer = store.get_storer(key)
            nrows = int(getattr(storer, 'nrows', 0) or 0)
            quality = None
            if nrows > 0:
                first_row = store.select(key, start=0, stop=1)
                last_row = store.select(key, start=nrows - 1, stop=nrows)
                start_ts = first_row.index[0].isoformat() if len(first_row) else None
                end_ts = last_row.index[0].isoformat() if len(last_row) else None
                if len(first_row) and len(last_row):
                    quality = _quality_pct(first_row.index[0], last_row.index[0], nrows, tf_seconds)
            else:
                start_ts = None
                end_ts = None
            symbols_info.append({
                'symbol': symbol,
                'bars': nrows,
                'start': start_ts,
                'end': end_ts,
                'quality': quality,
            })
    return {'symbols': symbols_info}


@router.get('/data/files')
def list_data_files():
    """Listet alle HDF5-Dateien unter DATA_PATH mit Symbol-Metadaten (nrows, start, end)."""
    pattern = os.path.join(Config.DATA_PATH, 'ohlcv_*.h5')
    files_info: List[dict] = []
    for path in sorted(glob.glob(pattern)):
        fname = os.path.basename(path)
        m = _HDF_FILE_RE.match(fname)
        if not m:
            continue
        timeframe, exchange = m.group(1), m.group(2)
        try:
            size_bytes = os.path.getsize(path)
            mtime = datetime.fromtimestamp(os.path.getmtime(path)).isoformat()
            meta = _read_file_metadata(path, _TF_SECONDS.get(timeframe))
            files_info.append({
                'file': fname,
                'exchange': exchange,
                'timeframe': timeframe,
                'size_mb': round(size_bytes / 1024 / 1024, 2),
                'modified_at': mtime,
                'symbols': meta['symbols'],
            })
        except Exception as exc:
            files_info.append({
                'file': fname,
                'exchange': exchange,
                'timeframe': timeframe,
                'error': str(exc),
                'symbols': [],
            })
    return {'data': {'files': files_info}, 'error': None}


class OhlcDownloadIn(BaseModel):
    """Payload für einen Download-Job."""
    exchange: str = 'binance'
    timeframe: str
    symbols: List[str]
    start_date: str  # z.B. '2020-01-01'
    end_date: Optional[str] = None  # default 'now UTC' im Worker


class OhlcUpdateIn(BaseModel):
    """Payload für einen Update-Job (bestehende Datei fortschreiben)."""
    exchange: str = 'binance'
    timeframe: str


class OhlcUpdateSymbolIn(BaseModel):
    """Payload für einen Update-Job eines einzelnen Symbols."""
    exchange: str = 'binance'
    timeframe: str
    symbol: str


class OhlcDeleteIn(BaseModel):
    """Payload für das Löschen eines Symbols aus einer HDF5-Datei."""
    exchange: str = 'binance'
    timeframe: str
    symbol: str


def _enqueue_ohlc_job(job: OhlcDownloadJob) -> str:
    """Reiht einen OHLC-Job in die Redis-Queue ein und gibt die rq_job_id zurück.

    Wichtig: `job_id` ist ein reserviertes RQ-Keyword-Argument, deshalb die
    Funktions-Kwargs explizit über `kwargs=...` übergeben.
    """
    q = Queue(OHLC_DOWNLOAD_QUEUE_NAME, connection=get_redis_connection())
    rq_job = q.enqueue(
        'services.api.worker_tasks.run_ohlc_download_job',
        kwargs={'job_id': job.id},
        job_timeout=3600,
    )
    return rq_job.id


def _create_ohlc_jobs(
    session,
    job_type: str,
    exchange: str,
    timeframe: str,
    symbols: List[str],
    start_date: Optional[str],
    end_date: Optional[str],
) -> list:
    """Legt je Symbol einen eigenen OHLC-Job an und reiht ihn ein.

    Jeder Job trägt genau ein Symbol, damit Status und Fortschritt pro Symbol
    abfragbar sind und die Binance-API durch die Worker-Pause (OHLC_FETCH_DELAY)
    geschont wird.

    Returns:
        Liste von {id, symbol, rq_job_id} der angelegten Jobs.
    """
    created = []
    for sym in symbols:
        job = OhlcDownloadJob(
            job_type=job_type,
            exchange=exchange,
            timeframe=timeframe,
            symbols=[sym],
            start_date=start_date,
            end_date=end_date,
            status='queued',
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        rq_job_id = _enqueue_ohlc_job(job)
        job.rq_job_id = rq_job_id
        session.commit()
        created.append({'id': job.id, 'symbol': sym, 'rq_job_id': rq_job_id})
    return created


@router.post('/data/download')
def create_download_job(payload: OhlcDownloadIn):
    """Legt je Symbol einen eigenen OHLC-Download-Job an und reiht ihn ein."""
    if payload.exchange != 'binance':
        return JSONResponse(
            {'data': None, 'error': 'Aktuell wird nur binance unterstützt'},
            status_code=400,
        )
    # GEÄNDERT: Symbol-Liste in Einzel-Jobs zerlegen (Duplikate raus).
    symbols = list(dict.fromkeys(s.strip().upper() for s in payload.symbols if s.strip()))
    if not symbols:
        return JSONResponse(
            {'data': None, 'error': 'Mindestens ein Symbol erforderlich'},
            status_code=400,
        )
    session = get_session()
    try:
        created = _create_ohlc_jobs(
            session, 'download', payload.exchange, payload.timeframe,
            symbols, payload.start_date, payload.end_date,
        )
        return {
            'data': {'jobs': created, 'count': len(created), 'id': created[0]['id']},
            'error': None,
        }
    finally:
        session.close()


@router.post('/data/update')
def create_update_job(payload: OhlcUpdateIn):
    """Legt je Symbol der bestehenden Datei einen eigenen Update-Job an."""
    filename = f'ohlcv_{payload.timeframe}_{payload.exchange}.h5'
    path = os.path.join(Config.DATA_PATH, filename)
    if not os.path.exists(path):
        return JSONResponse(
            {'data': None, 'error': f'Datei nicht gefunden: {filename}'},
            status_code=404,
        )
    session = get_session()
    try:
        # GEÄNDERT: alle Symbole der Datei in Einzel-Update-Jobs zerlegen.
        with pd.HDFStore(path, mode='r') as store:
            symbols = sorted(k.lstrip('/') for k in store.keys())
        if not symbols:
            return JSONResponse(
                {'data': None, 'error': f'Keine Symbole in {filename}'},
                status_code=404,
            )
        created = _create_ohlc_jobs(
            session, 'update', payload.exchange, payload.timeframe,
            symbols, None, 'now UTC',
        )
        return {
            'data': {'jobs': created, 'count': len(created), 'id': created[0]['id']},
            'error': None,
        }
    finally:
        session.close()


@router.post('/data/install-baseline-jobs')
def create_baseline_ohlc_jobs():
    """Legt die OHLC-Download-Jobs an, die die ausgelieferte Grundausstattung braucht.

    Leitet die nötigen Kursdaten aus den in Test-Sets referenzierten Backtest-Configs
    ab (gruppiert nach exchange/symbol/timeframe mit umspannendem Zeitraum), damit die
    mitgelieferten Test-Sets und die Demo-Strategie sofort lauffähig sind. Bereits
    vorhandene Symbole werden übersprungen (idempotent, kein Doppel-Download).
    """
    session = get_session()
    try:
        rows = session.execute(text(
            """
            SELECT exchange, symbol, timeframe,
                   MIN(ohlc_start)::text AS start_date,
                   MAX(ohlc_end)::text   AS end_date
            FROM backtest_configs
            WHERE id IN (
                SELECT jsonb_array_elements_text(backtest_config_ids_json::jsonb)::int
                FROM testsets
            )
            GROUP BY exchange, symbol, timeframe
            ORDER BY symbol, timeframe
            """
        )).mappings().all()

        created = []
        skipped = []
        for r in rows:
            # Schon vorhanden? Datei pro timeframe+exchange, Symbole als HDF5-Keys.
            filename = f"ohlcv_{r['timeframe']}_{r['exchange']}.h5"
            path = os.path.join(Config.DATA_PATH, filename)
            already = False
            if os.path.exists(path):
                try:
                    with pd.HDFStore(path, mode='r') as store:
                        already = any(k.lstrip('/') == r['symbol'] for k in store.keys())
                except (OSError, KeyError):
                    already = False
            if already:
                skipped.append(r['symbol'])
                continue
            created.extend(_create_ohlc_jobs(
                session, 'download', r['exchange'], r['timeframe'],
                [r['symbol']], r['start_date'], r['end_date'],
            ))

        return {
            'data': {'jobs': created, 'count': len(created), 'skipped': skipped},
            'error': None,
        }
    finally:
        session.close()


@router.post('/data/update-symbol')
def create_update_symbol_job(payload: OhlcUpdateSymbolIn):
    """Legt einen Update-Job für genau ein Symbol an (für die Backtest-Config-Seite).

    Der Worker zieht den Bereich ab einem Tag vor dem letzten vorhandenen Bar bis
    jetzt (UTC) nach.
    """
    filename = f'ohlcv_{payload.timeframe}_{payload.exchange}.h5'
    path = os.path.join(Config.DATA_PATH, filename)
    if not os.path.exists(path):
        return JSONResponse(
            {'data': None, 'error': f'Datei nicht gefunden: {filename}'},
            status_code=404,
        )
    sym = payload.symbol.strip().upper()
    with pd.HDFStore(path, mode='r') as store:
        keys = set(k.lstrip('/') for k in store.keys())
    if sym not in keys:
        return JSONResponse(
            {'data': None, 'error': f'Symbol {sym} nicht in {filename}'},
            status_code=404,
        )
    session = get_session()
    try:
        created = _create_ohlc_jobs(
            session, 'update', payload.exchange, payload.timeframe,
            [sym], None, 'now UTC',
        )
        return {'data': created[0], 'error': None}
    finally:
        session.close()


@router.post('/data/delete-symbol')
def delete_symbol(payload: OhlcDeleteIn):
    """Entfernt ein einzelnes Symbol aus der HDF5-Datei (direkt, kein Worker)."""
    filename = f'ohlcv_{payload.timeframe}_{payload.exchange}.h5'
    path = os.path.join(Config.DATA_PATH, filename)
    if not os.path.exists(path):
        return JSONResponse(
            {'data': None, 'error': f'Datei nicht gefunden: {filename}'},
            status_code=404,
        )
    key = '/' + payload.symbol.strip().upper()
    try:
        with pd.HDFStore(path, mode='a') as store:
            if key not in store.keys():
                return JSONResponse(
                    {'data': None, 'error': f'Symbol {payload.symbol} nicht in Datei'},
                    status_code=404,
                )
            store.remove(key)
        return {'data': {'deleted': payload.symbol, 'file': filename}, 'error': None}
    except Exception as exc:
        return JSONResponse(
            {'data': None, 'error': f'Löschen fehlgeschlagen: {exc}'},
            status_code=500,
        )


@router.get('/data/jobs')
def list_download_jobs(limit: int = Query(20, ge=1, le=200)):
    """Letzte OHLC-Jobs für Status-Anzeige."""
    session = get_session()
    try:
        jobs = (
            session.query(OhlcDownloadJob)
            .order_by(OhlcDownloadJob.created_at.desc())
            .limit(limit)
            .all()
        )
        items = [
            {
                'id': j.id,
                'job_type': j.job_type,
                'exchange': j.exchange,
                'timeframe': j.timeframe,
                'symbols': j.symbols,
                'start_date': j.start_date,
                'end_date': j.end_date,
                'status': j.status,
                'message': j.message,
                'intervals_total': j.intervals_total,
                'intervals_done': j.intervals_done,
                'created_at': j.created_at.isoformat() if j.created_at else None,
                'started_at': j.started_at.isoformat() if j.started_at else None,
                'completed_at': j.completed_at.isoformat() if j.completed_at else None,
            }
            for j in jobs
        ]
        return {'data': {'items': items}, 'error': None}
    finally:
        session.close()


# Demo-Grundausstattung: Der Testlauf der Install-Maske fuehrt die mitgelieferten
# Demo-Testsets mit der Demo-Iteration und deren 10-Kombi-Indicator-Config aus.
BASELINE_TESTSET_IDS = (1, 2)
BASELINE_ITERATION_ID = 1
BASELINE_INDICATOR_CONFIG_ID = 2


def _baseline_required_candles(session) -> list:
    """Liefert die fuer die Demo-Testsets noetigen (exchange, symbol, timeframe)-Tupel."""
    ids_csv = ','.join(str(i) for i in BASELINE_TESTSET_IDS)
    return session.execute(text(
        f"""
        SELECT DISTINCT exchange, symbol, timeframe
        FROM backtest_configs
        WHERE id IN (
            SELECT jsonb_array_elements_text(backtest_config_ids_json::jsonb)::int
            FROM testsets WHERE id IN ({ids_csv})
        )
        ORDER BY symbol
        """
    )).mappings().all()


@router.get('/data/baseline-testrun/readiness')
def baseline_testrun_readiness():
    """Prueft, ob alle Candles fuer den Demo-Testlauf (Testset 1+2) vorliegen."""
    session = get_session()
    try:
        rows = _baseline_required_candles(session)
        missing = []
        for r in rows:
            filename = f"ohlcv_{r['timeframe']}_{r['exchange']}.h5"
            path = os.path.join(Config.DATA_PATH, filename)
            present = False
            if os.path.exists(path):
                try:
                    with pd.HDFStore(path, mode='r') as store:
                        present = any(k.lstrip('/') == r['symbol'] for k in store.keys())
                except (OSError, KeyError):
                    present = False
            if not present:
                missing.append(r['symbol'])
        return {
            'data': {
                'ready': len(missing) == 0,
                'missing': sorted(set(missing)),
                'required': len(rows),
            },
            'error': None,
        }
    finally:
        session.close()


@router.post('/data/baseline-testrun')
def start_baseline_testrun():
    """Startet den Demo-Testlauf: je Demo-Testset ein TestSet-Lauf mit der Demo-Iteration.

    Bricht ab, wenn noch Candles fehlen (Readiness-Pruefung), damit kein Lauf in
    unvollstaendige Daten laeuft.
    """
    session = get_session()
    try:
        missing = []
        for r in _baseline_required_candles(session):
            filename = f"ohlcv_{r['timeframe']}_{r['exchange']}.h5"
            path = os.path.join(Config.DATA_PATH, filename)
            present = False
            if os.path.exists(path):
                try:
                    with pd.HDFStore(path, mode='r') as store:
                        present = any(k.lstrip('/') == r['symbol'] for k in store.keys())
                except (OSError, KeyError):
                    present = False
            if not present:
                missing.append(r['symbol'])
    finally:
        session.close()
    if missing:
        return JSONResponse(
            {'data': None, 'error': f'Candles fehlen noch: {", ".join(sorted(set(missing)))}'},
            status_code=409,
        )

    # Bestehende TestSet-Run-Logik wiederverwenden (kein Duplikat der Start-Mechanik).
    from services.api.routes.api_testset_runs import TestSetRunIn, start_testset_run
    started = []
    for ts_id in BASELINE_TESTSET_IDS:
        resp = start_testset_run(TestSetRunIn(
            testset_id=ts_id,
            iteration_id=BASELINE_ITERATION_ID,
            indicator_config_id=BASELINE_INDICATOR_CONFIG_ID,
        ))
        body = json.loads(bytes(resp.body).decode('utf-8'))
        if body.get('error'):
            return JSONResponse({'data': None, 'error': body['error']}, status_code=400)
        started.append({'testset_id': ts_id, 'testset_run_id': body['data']['testset_run_id']})

    return {'data': {'runs': started, 'count': len(started)}, 'error': None}


@router.get('/data/jobs/summary')
def download_jobs_summary():
    """Aggregierter OHLC-Job-Fortschritt fuer die Install-Maske (Zaehlung je Status)."""
    session = get_session()
    try:
        rows = (
            session.query(OhlcDownloadJob.status, func.count())
            .group_by(OhlcDownloadJob.status)
            .all()
        )
        counts = {status: count for status, count in rows}
        queued = counts.get('queued', 0)
        running = counts.get('running', 0)
        completed = counts.get('completed', 0)
        failed = counts.get('failed', 0)
        return {
            'data': {
                'queued': queued,
                'running': running,
                'completed': completed,
                'failed': failed,
                'total': queued + running + completed + failed,
            },
            'error': None,
        }
    finally:
        session.close()


@router.delete('/data/jobs/{job_id}')
def delete_download_job(job_id: int):
    """Löscht einen OHLC-Job aus der Liste.

    Je nach Status wird der zugehörige RQ-Job zusätzlich gestoppt:
    - 'queued': wartender Job wird aus der Queue storniert (cancel).
    - 'running': laufender Job wird hart abgebrochen (SIGTERM an den Worker via
      send_stop_job_command). Der Worker arbeitet nicht kooperativ-abbrechbar,
      daher ist nur der harte Stopp möglich; bereits geschriebene Daten bleiben erhalten.
    - 'completed'/'failed': nur die DB-Zeile wird entfernt.
    """
    session = get_session()
    try:
        job = session.query(OhlcDownloadJob).filter(OhlcDownloadJob.id == job_id).first()
        if not job:
            return JSONResponse({'data': None, 'error': 'Job nicht gefunden'}, status_code=404)
        if job.status in ('queued', 'running') and job.rq_job_id:
            # rq.command/rq.job sind Worker-/Container-Deps — lokal importieren, damit
            # api_config auch ohne vollständige rq-Installation (z.B. in Tests) ladbar bleibt.
            from rq.command import send_stop_job_command
            from rq.job import Job as RqJob
            redis_conn = get_redis_connection()
            try:
                if job.status == 'running':
                    send_stop_job_command(redis_conn, job.rq_job_id)
                else:
                    RqJob.fetch(job.rq_job_id, connection=redis_conn).cancel()
            except Exception as exc:
                # RQ-Job evtl. bereits abgeschlossen/entfernt — DB-Zeile trotzdem löschen.
                logger.warning('RQ-Abbruch für OHLC-Job %s fehlgeschlagen: %s', job_id, exc)
        session.delete(job)
        session.commit()
        return {'data': {'deleted': job_id}, 'error': None}
    finally:
        session.close()
