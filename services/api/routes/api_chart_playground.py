"""
JSON-API Endpoints für Chart Playground

GET    /api/chart-playground/sources           — Verfügbare Datenquellen (Exchange/TF/Symbols aus HDF5)
GET    /api/chart-playground/ohlcv             — Candles für gewähltes Symbol/TF/Zeitraum
GET    /api/chart-playground/indicators        — Katalog aller verfügbaren Indikatoren (VBT + Custom)
POST   /api/chart-playground/compute           — Mehrere Indikatoren live berechnen
GET    /api/chart-playground/setups            — Liste gespeicherter Setups
GET    /api/chart-playground/setups/{id}       — Einzelnes Setup
POST   /api/chart-playground/setups            — Neues Setup anlegen
PUT    /api/chart-playground/setups/{id}       — Setup aktualisieren
DELETE /api/chart-playground/setups/{id}       — Setup löschen
"""

import glob
import importlib
import inspect
import os
import re
from datetime import datetime
from functools import lru_cache
from typing import Any, Optional

import numpy as np
import pandas as pd
import vectorbtpro as vbt
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from user_data.strategies.generic.tf_resample import (
    normalize_tf,
    realign_to_index,
    resampled_ohlc,
    tf_to_timedelta,
    validate_tf,
)
from user_data.utils.database.db import get_session
from user_data.utils.database.models import ChartPlaygroundSetup
from user_data.utils.ohlc.loader import EXCHANGE_DATA_CLASS


router = APIRouter(prefix='/api/chart-playground', tags=['chart-playground'])


# ---------------------------------------------------------------------------
# Heuristik: Overlay vs. Subplot
# ---------------------------------------------------------------------------
OVERLAY_KEYWORDS = {
    'sma', 'ema', 'wma', 'vwma', 'bb', 'bbands', 'supertrend', 'ichimoku',
    'psar', 'sar', 'vwap', 'hull', 'kama', 'tema', 'dema', 'trima', 'ma',
    'bollinger', 'keltner', 'donchian', 'midpoint', 'midprice', 'pivotinfo',
    'fastsma', 'slowsma', 'ht_trendline', 'linearreg', 'fastslow', 'trendline',
}
SUBPLOT_KEYWORDS = {
    'rsi', 'macd', 'stoch', 'smi', 'adx', 'cci', 'atr', 'obv', 'mfi', 'williams',
    'willr', 'roc', 'cmo', 'trix', 'ao', 'mom', 'ppo', 'kst', 'vortex',
    'ult', 'aroon', 'dx', 'minus_di', 'plus_di', 'tsi', 'correl', 'std',
    'natr', 'beta', 'linearreg_slope', 'linearreg_angle',
}


def _guess_plot_type(name: str) -> str:
    """Overlay wenn der Name ein bekanntes Preis-Niveau-Indikator enthält, sonst subplot."""
    lower = name.lower()
    # Suffix nach Prefix nehmen
    if ':' in lower:
        lower = lower.split(':', 1)[1]
    lower_clean = re.sub(r'[^a-z0-9]', '', lower)
    for kw in OVERLAY_KEYWORDS:
        if kw in lower_clean:
            return 'overlay'
    for kw in SUBPLOT_KEYWORDS:
        if kw in lower_clean:
            return 'subplot'
    return 'subplot'


# ---------------------------------------------------------------------------
# 1) Sources (aus HDF5-Files)
# ---------------------------------------------------------------------------
def _ohlc_data_dir() -> str:
    return os.getenv('PROJECT_ROOT', '/app') + '/data/ohlc_data/'


@router.get('/sources')
def list_sources() -> dict:
    """Listet verfügbare Datenquellen (Exchange/TF/Symbols) aus HDF5-Files."""
    data_dir = _ohlc_data_dir()
    if not os.path.isdir(data_dir):
        return {'data': {'sources': []}, 'error': None}

    sources = []
    pattern = re.compile(r'^ohlcv_([^_]+)_([^.]+)\.h5$')
    for fname in sorted(os.listdir(data_dir)):
        m = pattern.match(fname)
        if not m:
            continue
        timeframe, exchange = m.group(1), m.group(2)
        path = os.path.join(data_dir, fname)
        try:
            store = pd.HDFStore(path, 'r')
            try:
                symbols = sorted(k.lstrip('/') for k in store.keys())
            finally:
                store.close()
        except Exception:
            symbols = []
        sources.append({
            'exchange': exchange,
            'timeframe': timeframe,
            'symbols': symbols,
        })

    return {'data': {'sources': sources}, 'error': None}


# ---------------------------------------------------------------------------
# 2) OHLCV laden
# ---------------------------------------------------------------------------
def _load_ohlcv_df(
    symbol: str, exchange: str, timeframe: str,
    start: Optional[str], end: Optional[str],
) -> pd.DataFrame:
    data_dir = _ohlc_data_dir()
    h5_file = os.path.join(data_dir, f'ohlcv_{timeframe}_{exchange}.h5')
    if not os.path.exists(h5_file):
        raise HTTPException(status_code=404, detail=f'HDF5-Datei nicht gefunden: {os.path.basename(h5_file)}')
    store = pd.HDFStore(h5_file, 'r')
    try:
        key = f'/{symbol}'
        if key not in store.keys():
            raise HTTPException(status_code=404, detail=f'Symbol {symbol} nicht in {os.path.basename(h5_file)}')
        df = store[key]
    finally:
        store.close()

    # Index ist UTC-aware — Start/End Filter entsprechend
    if start:
        df = df[df.index >= pd.Timestamp(start, tz='UTC')]
    if end:
        # Ende inklusive ganzer Tag
        df = df[df.index <= pd.Timestamp(end, tz='UTC') + pd.Timedelta(days=1)]
    return df


@router.get('/ohlcv')
def get_ohlcv(
    symbol: str = Query(...),
    exchange: str = Query(...),
    timeframe: str = Query(...),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
) -> dict:
    """OHLCV-Candles für das gewählte Symbol/TF/Zeitraum."""
    df = _load_ohlcv_df(symbol, exchange, timeframe, start, end)
    candles = []
    for ts, row in df.iterrows():
        candles.append({
            'time': int(ts.timestamp()),
            'open': float(row['Open']),
            'high': float(row['High']),
            'low': float(row['Low']),
            'close': float(row['Close']),
            'volume': float(row['Volume']),
        })
    return {
        'data': {
            'symbol': symbol,
            'exchange': exchange,
            'timeframe': timeframe,
            'candles': candles,
        },
        'error': None,
    }


# ---------------------------------------------------------------------------
# 3) Indikator-Katalog
# ---------------------------------------------------------------------------
def _extract_factory(ind_id: str):
    """Lädt die Indikator-Factory für eine ID wie 'talib:SMA' oder 'custom:dwsFastSMA'.

    Delegiert an user_data.strategies.generic.registry.resolve_indicator_factory,
    damit Playground und Spec Runner dieselbe Auflösung nutzen.
    """
    from user_data.strategies.generic.registry import resolve_indicator_factory
    try:
        return resolve_indicator_factory(ind_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


def _sanitize_default(val: Any) -> Any:
    """Konvertiert VBT-spezifische Default-Typen in JSON-serialisierbare Werte."""
    if val is None:
        return None
    if isinstance(val, (int, float, str, bool)):
        return val
    # vbt.Default hat oft ein .value Attribut
    if hasattr(val, 'value'):
        inner = val.value
        if inner is None:
            return None
        if isinstance(inner, (int, float, str, bool)):
            return inner
    return None


def _factory_param_defaults(factory) -> dict:
    """Liest Parameter-Defaults aus run() und fällt auf apply_func zurück."""
    defaults = {}
    pnames = tuple(getattr(factory, 'param_names', ()) or ())
    # Erste Quelle: run-Signatur
    try:
        sig = inspect.signature(factory.run)
        for pname in pnames:
            p = sig.parameters.get(pname)
            if p and p.default is not inspect.Parameter.empty and p.default is not None:
                val = _sanitize_default(p.default)
                if val is not None:
                    defaults[pname] = val
    except (ValueError, TypeError):
        pass
    # Fallback 1: apply_func-Signatur per Name
    apply_fn = getattr(factory, 'apply_func', None)
    if apply_fn is not None:
        try:
            sig2 = inspect.signature(apply_fn)
            for pname in pnames:
                if pname in defaults:
                    continue
                p = sig2.parameters.get(pname)
                if p and p.default is not inspect.Parameter.empty and p.default is not None:
                    val = _sanitize_default(p.default)
                    if val is not None:
                        defaults[pname] = val
        except (ValueError, TypeError):
            pass
    # Fallback 2: positionsbasiert (für Custom-Indikatoren mit abweichenden Parameter-Namen)
    if apply_fn is not None and any(p not in defaults for p in pnames):
        try:
            sig3 = inspect.signature(apply_fn)
            all_params = list(sig3.parameters.values())
            n_inputs = len(tuple(getattr(factory, 'input_names', ()) or ()))
            # apply_func-Params nach den Inputs bis zum ersten ohne Default (bzw. bis param_names alle)
            remaining = all_params[n_inputs:]
            for i, pname in enumerate(pnames):
                if pname in defaults:
                    continue
                if i >= len(remaining):
                    break
                p = remaining[i]
                if p.default is not inspect.Parameter.empty and p.default is not None:
                    val = _sanitize_default(p.default)
                    if val is not None:
                        defaults[pname] = val
        except (ValueError, TypeError):
            pass
    return defaults


def _list_custom_indicators() -> list:
    try:
        module = importlib.import_module('user_data.utils.indicators.custom')
    except Exception:
        return []
    items = []
    for attr_name in dir(module):
        if attr_name.startswith('_'):
            continue
        obj = getattr(module, attr_name)
        # IndicatorFactory-Objekte haben input_names/param_names/output_names/run
        if all(hasattr(obj, a) for a in ('input_names', 'param_names', 'output_names', 'run')):
            items.append((attr_name, obj))
    return items


@lru_cache(maxsize=1)
def _build_catalog() -> dict:
    groups: dict[str, list] = {}

    # VBT-Indikatoren
    try:
        all_inds = vbt.IF.list_indicators()
    except Exception:
        all_inds = []

    for full_id in all_inds:
        if ':' in full_id:
            grp, name = full_id.split(':', 1)
        else:
            grp, name = 'vbt', full_id
        try:
            factory = vbt.indicator(full_id)
        except Exception:
            continue
        try:
            inputs = list(getattr(factory, 'input_names', ()) or ())
            params = list(getattr(factory, 'param_names', ()) or ())
            outputs = list(getattr(factory, 'output_names', ()) or ())
        except Exception:
            continue
        defaults = _factory_param_defaults(factory)
        groups.setdefault(grp, []).append({
            'id': full_id,
            'name': name,
            'group': grp,
            'inputs': inputs,
            'params': [{'name': p, 'default': defaults.get(p)} for p in params],
            'outputs': outputs,
            'plot_type': _guess_plot_type(full_id),
        })

    # Custom-Indikatoren
    for cname, factory in _list_custom_indicators():
        full_id = f'custom:{cname}'
        inputs = list(getattr(factory, 'input_names', ()) or ())
        params = list(getattr(factory, 'param_names', ()) or ())
        outputs = list(getattr(factory, 'output_names', ()) or ())
        defaults = _factory_param_defaults(factory)
        groups.setdefault('custom', []).append({
            'id': full_id,
            'name': cname,
            'group': 'custom',
            'inputs': inputs,
            'params': [{'name': p, 'default': defaults.get(p)} for p in params],
            'outputs': outputs,
            'plot_type': _guess_plot_type(cname),
        })

    # Custom-Gruppe zuerst, dann alphabetisch
    sorted_groups = []
    if 'custom' in groups:
        sorted_groups.append({'name': 'custom', 'indicators': sorted(groups['custom'], key=lambda x: x['name'])})
    for g in sorted(k for k in groups.keys() if k != 'custom'):
        sorted_groups.append({'name': g, 'indicators': sorted(groups[g], key=lambda x: x['name'])})

    return {'groups': sorted_groups}


@router.get('/indicators')
def list_indicators() -> dict:
    """Vollständiger Indikator-Katalog (gecached)."""
    return {'data': _build_catalog(), 'error': None}


# ---------------------------------------------------------------------------
# 4) Indikatoren live berechnen
# ---------------------------------------------------------------------------
class IndicatorSpec(BaseModel):
    id: str
    name: str  # Slug-Name, eindeutiger Identifier (z.B. 'sma', 'ema_2')
    params: dict[str, Any] = {}  # Parameter (length, multiplier, ...)
    client_id: Optional[str] = None  # interner DOM-Key, nur fürs Frontend
    # Flat-Spec: Mapping Input-Name -> OHLCV-Spalte oder 'indicator:<name>:<out>'.
    # Keys entsprechen factory.input_names (z.B. 'source', 'volume', 'below_series').
    inputs: dict[str, str] = {}
    timeframe: Optional[str] = None  # Optionales Resample-TF (z.B. '4h')


class ComputeRequest(BaseModel):
    symbol: str
    exchange: str
    timeframe: str
    start: Optional[str] = None
    end: Optional[str] = None
    indicators: list[IndicatorSpec]


def _coerce_param(value: Any) -> Any:
    """Konvertiert Params zu skalaren Werten.

    Der Playground berechnet immer eine einzelne Indikator-Kombi (kein Sweep).
    Listen und Range-Dicts (aus Sweep-Runs gespeichert) werden auf den ersten
    bzw. Start-Wert reduziert, damit factory.run() keine Broadcasting-Fehler wirft.
    """
    # GEÄNDERT: Listen aus Sweep-Specs → erstes Element nehmen
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        value = value[0]
    # GEÄNDERT: Range-Dicts (type:arange oder start/stop) → Start-Wert nehmen
    if isinstance(value, dict):
        if 'start' in value:
            value = value['start']
        elif 'value' in value:
            value = value['value']
        else:
            return None
    if isinstance(value, str):
        s = value.strip()
        if s == '':
            return None
        try:
            if '.' in s or 'e' in s.lower():
                return float(s)
            return int(s)
        except ValueError:
            return s
    return value


def _series_to_points(series: pd.Series) -> list:
    """Pandas-Series in [{time, value}] — NaN wird ausgelassen."""
    points = []
    for ts, val in series.items():
        if pd.isna(val):
            continue
        points.append({'time': int(ts.timestamp()), 'value': float(val)})
    return points


@router.post('/compute')
def compute_indicators(req: ComputeRequest) -> dict:
    """Berechnet alle angeforderten Indikatoren live."""
    df = _load_ohlcv_df(req.symbol, req.exchange, req.timeframe, req.start, req.end)
    if df.empty:
        return {'data': {'results': [], 'errors': ['Keine OHLCV-Daten im Zeitraum']}, 'error': None}

    # Input-Quellen: Default-Mapping Input-Name -> OHLCV-Spalte
    col_map = {
        'Open': df['Open'], 'High': df['High'], 'Low': df['Low'],
        'Close': df['Close'], 'Volume': df['Volume'],
    }
    default_input_source = {
        'close': 'Close', 'open': 'Open', 'high': 'High', 'low': 'Low',
        'volume': 'Volume', 'source': 'Close',
    }

    # Cache: name -> {output_name: pd.Series} für Chaining
    computed_series: dict[str, dict[str, pd.Series]] = {}

    # GEÄNDERT: Topologische Sortierung nach Indikator-Referenzen (inputs: "indicator:<name>:<out>").
    # Grund: Die Reihenfolge im Frontend-Array entspricht nicht zwingend der Dependency-Reihenfolge —
    # z.B. wenn der User einen Indikator hinzufügt, der einen anderen referenziert, dieser aber erst
    # danach im Array steht. Ohne Sortierung scheitert er mit "Referenzierter Indikator noch nicht berechnet".
    available_names = {spec.name for spec in req.indicators}
    def _deps(spec: 'IndicatorSpec') -> set[str]:
        d: set[str] = set()
        for v in (spec.inputs or {}).values():
            if isinstance(v, str) and v.startswith('indicator:'):
                parts = v.split(':', 2)
                if len(parts) == 3 and parts[1] in available_names:
                    d.add(parts[1])
        return d
    remaining = list(req.indicators)
    ordered: list = []
    satisfied: set[str] = set()
    while remaining:
        progressed = False
        next_remaining = []
        for spec in remaining:
            if _deps(spec).issubset(satisfied):
                ordered.append(spec)
                satisfied.add(spec.name)
                progressed = True
            else:
                next_remaining.append(spec)
        remaining = next_remaining
        if not progressed:
            # Zyklus oder unauflösbare Dependency — Reste am Ende anhängen,
            # damit die ursprüliche Fehlermeldung greift.
            ordered.extend(remaining)
            break

    # GEÄNDERT: Paket B — Per-Indikator-tf nutzt jetzt den GETEILTEN Helper tf_resample
    # (resampled_ohlc / realign_to_index / validate_tf), exakt denselben Code wie der echte
    # Runner (build_indicators). Damit ist "Preview == gespeicherter Lauf" strukturell
    # garantiert (eine Resample-/Realign-Quelle). Das vbt.Data wird lazy aus dem df gebaut
    # (kein erneuter HDF-Load), pro Ziel-tf gecached.
    _native_data_holder: dict[str, Any] = {}
    _resampled_by_tf: dict[str, Any] = {}

    def _resampled_data(tf: str):
        if 'data' not in _native_data_holder:
            data = vbt.Data.from_data({req.symbol: df})
            data_class = EXCHANGE_DATA_CLASS.get(req.exchange)
            if data_class and hasattr(data, 'use_feature_config_of'):
                data.use_feature_config_of(data_class)
            _native_data_holder['data'] = data
        if tf not in _resampled_by_tf:
            _resampled_by_tf[tf] = resampled_ohlc(_native_data_holder['data'], tf)
        return _resampled_by_tf[tf]

    results = []
    errors = []
    for spec in ordered:
        try:
            factory = _extract_factory(spec.id)
            # Inputs zusammenstellen
            input_names = list(getattr(factory, 'input_names', ()) or ())
            # GEÄNDERT: Paket B — tf-Normalisierung + Downsampling-Guard über den geteilten
            # Helper (gleiche Regel wie der Runner). normalize_tf: leer / gleich Basis-tf -> None
            # (No-Op). validate_tf: feiner als Basis -> ValueError (vom per-Indikator-try/except
            # in die errors-Liste gefangen, statt still falsch zu rechnen).
            target_tf = normalize_tf(spec.timeframe, req.timeframe)
            if target_tf is not None:
                validate_tf(target_tf, tf_to_timedelta(req.timeframe))

            input_values = []
            for iname in input_names:
                src_key = spec.inputs.get(iname)
                if not src_key:
                    src_key = default_input_source.get(iname.lower())
                # Indikator-Referenz? Format: "indicator:<name>:<output_name>"
                if isinstance(src_key, str) and src_key.startswith('indicator:'):
                    parts = src_key.split(':', 2)
                    if len(parts) != 3:
                        raise ValueError(f'Ungültige Indikator-Referenz "{src_key}"')
                    _, ref_name, ref_out = parts
                    if ref_name not in computed_series:
                        raise ValueError(f'Referenzierter Indikator {ref_name} noch nicht berechnet')
                    outs = computed_series[ref_name]
                    if ref_out not in outs:
                        raise ValueError(f'Output "{ref_out}" nicht in Indikator {ref_name}')
                    s = outs[ref_out]
                    if target_tf:
                        # GEÄNDERT: Paket B — Cross-TF-Chaining nativ wie der Runner: den
                        # Basis-Output look-ahead-sicher (last-in-bucket via realign_closing)
                        # auf den tf-Index der resampleten OHLCV-Inputs bringen.
                        s = realign_to_index(s, _resampled_data(target_tf).wrapper.index)
                    input_values.append(s)
                    continue
                # Normale OHLCV-Spalte. GEÄNDERT: Explizit gespeicherte lowercase-Namen
                # (close/high/low/volume/open/source) auf die kapitalisierten col_map-Keys
                # mappen. Frontend serialisiert Inputs durchgängig lowercase (INPUT_DEFAULTS);
                # ohne diese Normalisierung greift default_input_source nur für leere src_keys.
                if isinstance(src_key, str) and src_key not in col_map:
                    src_key = default_input_source.get(src_key.lower(), src_key)
                if not src_key or src_key not in col_map:
                    raise ValueError(f'Kein Mapping für Input "{iname}" bei {spec.id}')
                col_series = col_map[src_key]
                if target_tf:
                    # GEÄNDERT: nativ über vbt.Data.resample(tf).get(<Spalte>) statt handgepflegter pandas-agg
                    col_series = _resampled_data(target_tf).get(src_key)
                input_values.append(col_series)

            # Parameter konvertieren
            params = {k: _coerce_param(v) for k, v in (spec.params or {}).items()}
            # NaN/None Params entfernen damit Factory-Defaults greifen
            params = {k: v for k, v in params.items() if v is not None}
            # timeframe-Param im Factory-Call entfernen - wir machen das selbst via Resample
            params.pop('timeframe', None)
            # Run
            result = factory.run(*input_values, **params)
            # Outputs einsammeln
            outputs = {}
            series_cache: dict[str, pd.Series] = {}
            for oname in (getattr(factory, 'output_names', ()) or ()):
                out_obj = getattr(result, oname, None)
                if out_obj is None:
                    continue
                # Bei mehreren Param-Kombis ist das ein DataFrame, wir nehmen die erste Spalte
                if isinstance(out_obj, pd.DataFrame):
                    if out_obj.shape[1] == 0:
                        continue
                    out_series = out_obj.iloc[:, 0]
                else:
                    out_series = out_obj
                # GEÄNDERT: Paket B — Output look-ahead-sicher auf den Basis-Index zurück
                # (geteilter Helper, identisch zum Runner). Kein stiller ffill-Fallback mehr:
                # ein Realign-Fehler wird vom per-Indikator-try/except sichtbar gemeldet.
                if target_tf:
                    out_series = realign_to_index(out_series, df.index, freq=req.timeframe)
                series_cache[oname] = out_series
                outputs[oname] = _series_to_points(out_series)
            # Für Chaining bereitstellen
            computed_series[spec.name] = series_cache
            results.append({
                'name': spec.name,
                'client_id': spec.client_id,
                'id': spec.id,
                'outputs': outputs,
            })
        except HTTPException:
            raise
        except Exception as e:
            errors.append({'name': spec.name, 'client_id': spec.client_id, 'id': spec.id, 'error': str(e)})

    return {'data': {'results': results, 'errors': errors}, 'error': None}


# ---------------------------------------------------------------------------
# 5) Setup-CRUD
# ---------------------------------------------------------------------------
class SetupIn(BaseModel):
    """Eingabe-Schema für Playground-Setup (Create/Update)."""
    name: str
    description: Optional[str] = None
    # GEÄNDERT: Ticket 15 — vier Felder statt config_json
    backtest_config_json: dict
    indicators_config_json: dict
    strategy_config_json: dict
    ui_state_json: Optional[dict] = None


class SetupOut(BaseModel):
    """Ausgabe-Schema für Playground-Setup."""
    id: int
    name: str
    description: Optional[str]
    # GEÄNDERT: Ticket 15 — vier Felder statt config_json
    backtest_config_json: dict
    indicators_config_json: dict
    strategy_config_json: dict
    ui_state_json: Optional[dict]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


@router.get('/setups')
def list_setups() -> dict:
    session = get_session()
    try:
        rows = session.query(ChartPlaygroundSetup).order_by(ChartPlaygroundSetup.name).all()
        items = [SetupOut.model_validate(r).model_dump(mode='json') for r in rows]
        return {'data': {'items': items}, 'error': None}
    finally:
        session.close()


@router.get('/setups/{setup_id}')
def get_setup(setup_id: int) -> dict:
    session = get_session()
    try:
        row = session.query(ChartPlaygroundSetup).filter(ChartPlaygroundSetup.id == setup_id).first()
        if not row:
            raise HTTPException(status_code=404, detail='Setup nicht gefunden')
        return {'data': SetupOut.model_validate(row).model_dump(mode='json'), 'error': None}
    finally:
        session.close()


@router.post('/setups')
def create_setup(data: SetupIn) -> dict:
    """Neues Playground-Setup anlegen."""
    session = get_session()
    try:
        row = ChartPlaygroundSetup(
            name=data.name,
            description=data.description,
            # GEÄNDERT: Ticket 15 — vier Felder statt config_json
            backtest_config_json=data.backtest_config_json,
            indicators_config_json=data.indicators_config_json,
            strategy_config_json=data.strategy_config_json,
            ui_state_json=data.ui_state_json,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return {'data': SetupOut.model_validate(row).model_dump(mode='json'), 'error': None}
    finally:
        session.close()


@router.put('/setups/{setup_id}')
def update_setup(setup_id: int, data: SetupIn) -> dict:
    """Playground-Setup aktualisieren."""
    session = get_session()
    try:
        row = session.query(ChartPlaygroundSetup).filter(ChartPlaygroundSetup.id == setup_id).first()
        if not row:
            raise HTTPException(status_code=404, detail='Setup nicht gefunden')
        row.name = data.name
        row.description = data.description
        # GEÄNDERT: Ticket 15 — vier Felder statt config_json
        row.backtest_config_json = data.backtest_config_json
        row.indicators_config_json = data.indicators_config_json
        row.strategy_config_json = data.strategy_config_json
        row.ui_state_json = data.ui_state_json
        row.updated_at = datetime.now()
        session.commit()
        session.refresh(row)
        return {'data': SetupOut.model_validate(row).model_dump(mode='json'), 'error': None}
    finally:
        session.close()


@router.delete('/setups/{setup_id}')
def delete_setup(setup_id: int) -> dict:
    session = get_session()
    try:
        row = session.query(ChartPlaygroundSetup).filter(ChartPlaygroundSetup.id == setup_id).first()
        if not row:
            raise HTTPException(status_code=404, detail='Setup nicht gefunden')
        session.delete(row)
        session.commit()
        return {'data': {'deleted': setup_id}, 'error': None}
    finally:
        session.close()


@router.post('/setups/bulk-delete')
def bulk_delete_setups(request_body: dict) -> dict:
    """Mehrere Playground-Setups auf einmal löschen."""
    ids = request_body.get('ids', [])
    if not ids:
        return {'data': {'deleted': 0}, 'error': None}
    session = get_session()
    try:
        deleted = session.query(ChartPlaygroundSetup).filter(ChartPlaygroundSetup.id.in_(ids)).delete(synchronize_session=False)
        session.commit()
        return {'data': {'deleted': deleted}, 'error': None}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Playground-Config aus Result-Snapshot (flüchtig, kein Setup-Eintrag)
# ---------------------------------------------------------------------------
# GEÄNDERT: Ticket 42 — neuer GET-Endpunkt für flüchtiges Laden aus Result-Snapshot
@router.get('/result-config/{result_id}')
def get_result_config(result_id: int) -> dict:
    """Liefert Playground-Config aus dem Result-Snapshot — OHNE Setup-Eintrag anzulegen.

    Gibt dasselbe Schema zurück wie GET /api/chart-playground/setups/{id}
    ({data: {backtest_config_json, indicators_config_json, strategy_config_json, ui_state_json}}),
    damit applySetupConfig() ohne Umbau wiederverwendbar ist.

    Indikatoren kommen als Dict (Name -> Flat-Spec), nicht als Liste.
    ui_state_json.selected_configs wird, soweit moeglich, aus dem zugehoerigen
    BacktestRun zurückgeführt (Konzept, Iteration, Indicator-/Backtest-Config),
    damit die oberen Dropdowns im Playground vorausgewählt sind. Lose Referenzen
    (Configs nach Cleanup geloescht, ad-hoc-Runs) bleiben None.
    """
    from user_data.utils.database.models import (
        BacktestResult,
        BacktestRun,
        StrategyIteration,
        StrategyConcept,
    )

    session = get_session()
    try:
        result = session.query(BacktestResult).filter(BacktestResult.id == result_id).first()
        if not result:
            raise HTTPException(status_code=404, detail=f'Result {result_id} nicht gefunden')

        snapshot = result.full_config_snapshot_json
        if not snapshot or 'backtest_config' not in snapshot or 'indicators' not in snapshot or 'rules' not in snapshot:
            raise HTTPException(
                status_code=422,
                detail=f'Result {result_id} hat keinen vollständigen Config-Snapshot. Neuere Results tragen den Snapshot automatisch.',
            )

        bc = snapshot['backtest_config']
        indicators_flat = snapshot['indicators']  # Dict: Name -> Flat-Spec (bereits aufgelöst)
        rules = snapshot['rules']

        if not isinstance(indicators_flat, dict):
            raise HTTPException(
                status_code=422,
                detail=f'Snapshot-Indikatoren in Result {result_id} sind kein Dict.',
            )

        # Indikatoren: Snapshot-Dict direkt als indicators_config_json übernehmen
        # (bereits Flat-Spec, kein topo_sort nötig — Snapshot enthält aufgelöste Reihenfolge)
        indicators_config_json = dict(indicators_flat)
        # GEÄNDERT: Schritt 4d — Stops gehören in indicators_config_json._stops (Wire-Format-Vertrag),
        # die Werte stammen weiterhin aus dem Backtest-Config-Snapshot (bc).
        indicators_config_json['_stops'] = {
            'tp_stop': bc.get('tp_stop'),
            'sl_stop': bc.get('sl_stop'),
            'tsl_th': bc.get('tsl_th'),
            'tsl_stop': bc.get('tsl_stop'),
            'td_stop': bc.get('td_stop'),
            'delta_format': bc.get('delta_format', 'percent'),
            'time_delta_format': bc.get('time_delta_format', 'rows'),
        }

        backtest_config_json = {
            'exchange': bc.get('exchange', 'binance'),
            'timeframe': bc.get('timeframe', '4h'),
            'symbols': [bc.get('symbol', 'BTCUSDT')],
            'start': bc.get('start'),
            'end': bc.get('end'),
            'ohlc_start': bc.get('ohlc_start'),
            'ohlc_end': bc.get('ohlc_end'),
            # GEÄNDERT: Schritt 4d — Stop-/Format-Felder raus; Portfolio behält nur size/size_type/init_cash/fees
            'portfolio': {
                'size': bc.get('size', 100),
                'size_type': bc.get('size_type', 'value'),
                'init_cash': bc.get('init_cash', 100),
                'fees': bc.get('fees', 0.001),
            },
        }

        # GEÄNDERT: Rückführung der Dropdown-Auswahl aus dem zugehoerigen BacktestRun.
        # iteration_id liegt direkt am Result (FK), Config-Herkunft am Run (lose Refs).
        run = session.query(BacktestRun).filter(BacktestRun.id == result.run_id).first()
        iteration_id = result.iteration_id or (run.iteration_id if run else None)
        backtest_config_id = run.backtest_config_id if run else None
        indicator_config_id = run.indicator_config_id if run else None

        # Konzept-Slug ueber die Iteration aufloesen (cpConceptSlug nutzt den Slug als value)
        concept_slug = None
        if iteration_id:
            iteration = session.query(StrategyIteration).filter(
                StrategyIteration.id == iteration_id
            ).first()
            if iteration:
                concept = session.query(StrategyConcept).filter(
                    StrategyConcept.id == iteration.concept_id
                ).first()
                concept_slug = concept.slug if concept else None

        strategy_config_json = {
            'entry': rules.get('entry') if isinstance(rules, dict) else None,
            'exit': rules.get('exit') if isinstance(rules, dict) else None,
            'concept_slug': concept_slug,
        }

        # ui_state_json: selected_configs aus der Rückführung (None bei fehlenden/ad-hoc-Refs)
        ui_state_json = {
            'show_candles': True,
            'indicators': {},
            'selected_configs': {
                'iteration_id': iteration_id,
                'backtest_config_id': backtest_config_id,
                'indicator_config_id': indicator_config_id,
            },
        }

        return {
            'data': {
                'backtest_config_json': backtest_config_json,
                'indicators_config_json': indicators_config_json,
                'strategy_config_json': strategy_config_json,
                'ui_state_json': ui_state_json,
            },
            'error': None,
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Setup aus einem Backtest-Result erzeugen
# ---------------------------------------------------------------------------
# GEÄNDERT: Ticket 43 — auf Snapshot umgestellt; kein Zugriff mehr auf Run/Iteration/StrategyConcept
@router.post('/setups/from-result/{result_id}')
def create_setup_from_result(result_id: int) -> dict:
    """Erzeugt aus einem Backtest-Result ein Playground-Setup.

    Liest ausschließlich aus full_config_snapshot_json — kein Zugriff mehr auf
    Run, Iteration oder StrategyConcept. Fehlender Snapshot wird sichtbar
    abgewiesen (kein stiller Fehlschlag).
    """
    from user_data.utils.database.models import BacktestResult

    session = get_session()
    try:
        result = session.query(BacktestResult).filter(BacktestResult.id == result_id).first()
        if not result:
            raise HTTPException(status_code=404, detail=f'Result {result_id} nicht gefunden')

        snapshot = result.full_config_snapshot_json
        if not snapshot or 'backtest_config' not in snapshot or 'indicators' not in snapshot or 'rules' not in snapshot:
            raise HTTPException(
                status_code=422,
                detail=f'Result {result_id} hat keinen vollständigen Config-Snapshot (full_config_snapshot_json fehlt oder ist unvollständig). Neuere Results tragen den Snapshot automatisch.',
            )

        bc = snapshot['backtest_config']
        indicators_flat = snapshot['indicators']  # Dict: Name -> Flat-Spec (bereits aufgelöst)
        rules = snapshot['rules']

        if not isinstance(indicators_flat, dict):
            raise HTTPException(
                status_code=422,
                detail=f'Snapshot-Indikatoren in Result {result_id} sind kein Dict.',
            )

        # OHLCV-Default-Mapping für Inputs
        _OHLCV_DEFAULT = {
            'open': 'Open', 'high': 'High', 'low': 'Low',
            'close': 'Close', 'volume': 'Volume', 'source': 'Close',
        }

        # Indikatoren in Playground-Format überführen
        # Snapshot liefert bereits Flat-Spec — kein topo_sort, keine Range-Auflösung mehr nötig
        indicators_out = []
        for ind_key, ind_cfg in indicators_flat.items():
            if not isinstance(ind_cfg, dict):
                continue
            raw_id = ind_cfg.get('indicator')
            if not raw_id:
                continue
            tf = ind_cfg.get('tf')
            enabled = ind_cfg.get('enabled', True)

            # Metadaten aus Factory auslesen (inputNames, outputNames, paramsMeta)
            input_names, output_names, params_meta = [], [], []
            try:
                factory = _extract_factory(raw_id)
                input_names = list(getattr(factory, 'input_names', ()) or ())
                output_names = list(getattr(factory, 'output_names', ()) or ())
                defaults = _factory_param_defaults(factory)
                for pname in (getattr(factory, 'param_names', ()) or ()):
                    params_meta.append({'name': pname, 'default': defaults.get(pname)})
            except HTTPException:
                pass

            input_name_set = set(input_names)
            non_meta = {k: v for k, v in ind_cfg.items() if k not in {'indicator', 'tf', 'enabled'}}
            inputs = {k: v for k, v in non_meta.items() if k in input_name_set}
            params = {k: v for k, v in non_meta.items() if k not in input_name_set}

            # Inputs auffüllen: falls leer, aus input_names Default-OHLCV mappen
            if not inputs and input_names:
                for iname in input_names:
                    inputs[iname] = _OHLCV_DEFAULT.get(iname.lower(), iname)

            indicators_out.append({
                'id': raw_id,
                'name': ind_key,
                'params': params,
                'color': None,
                'plot_type': _guess_plot_type(raw_id),
                'visible': bool(enabled),
                'paramsMeta': params_meta,
                'inputNames': input_names,
                'outputNames': output_names,
                'inputs': inputs,
                'timeframe': tf,
            })

        # Backtest-Config für das Setup zusammenbauen
        new_backtest_config_json = {
            'exchange': bc.get('exchange', 'binance'),
            'timeframe': bc.get('timeframe', '4h'),
            'symbols': [bc.get('symbol', 'BTCUSDT')],
            'start': bc.get('start'),
            'end': bc.get('end'),
            'ohlc_start': bc.get('ohlc_start'),
            'ohlc_end': bc.get('ohlc_end'),
            # GEÄNDERT: Schritt 4d — Stop-/Format-Felder raus; Portfolio behält nur size/size_type/init_cash/fees
            'portfolio': {
                'size': bc.get('size', 100),
                'size_type': bc.get('size_type', 'value'),
                'init_cash': bc.get('init_cash', 100),
                'fees': bc.get('fees', 0.001),
            },
        }

        # Indikatoren: Liste -> Dict für indicators_config_json
        new_indicators_config_json = {}
        for ind_item in indicators_out:
            ind_name = ind_item.get('name') or ind_item.get('id') or 'indicator'
            entry = {
                'indicator': ind_item.get('id'),
                'tf': ind_item.get('timeframe'),
                'enabled': ind_item.get('visible', True),
            }
            if ind_item.get('inputs'):
                entry.update(ind_item['inputs'])
            if ind_item.get('params') and isinstance(ind_item['params'], dict):
                entry.update(ind_item['params'])
            new_indicators_config_json[ind_name] = entry
        # GEÄNDERT: Schritt 4d — Stops als _stops in indicators_config_json (Wire-Format-Vertrag),
        # Werte aus dem Backtest-Config-Snapshot (bc).
        new_indicators_config_json['_stops'] = {
            'tp_stop': bc.get('tp_stop'),
            'sl_stop': bc.get('sl_stop'),
            'tsl_th': bc.get('tsl_th'),
            'tsl_stop': bc.get('tsl_stop'),
            'td_stop': bc.get('td_stop'),
            'delta_format': bc.get('delta_format', 'percent'),
            'time_delta_format': bc.get('time_delta_format', 'rows'),
        }

        # Strategie-Config (Rules kommen direkt aus Snapshot)
        new_strategy_config_json = {
            'entry': rules.get('entry') if isinstance(rules, dict) else None,
            'exit': rules.get('exit') if isinstance(rules, dict) else None,
            'concept_slug': None,  # Snapshot enthält keinen Concept-Bezug
        }

        new_ui_state_json = {
            'show_candles': True,
            'indicators': {
                ind_item.get('name') or ind_item.get('id'): {
                    'color': ind_item.get('color'),
                    'plot_type': ind_item.get('plot_type'),
                }
                for ind_item in indicators_out
            },
            'selected_configs': {
                'iteration_id': None,
                'backtest_config_id': None,
                'indicator_config_id': None,
            },
        }

        setup_name = f'Result #{result_id} ({bc.get("symbol", "")} {bc.get("timeframe", "")})'
        setup_row = ChartPlaygroundSetup(
            name=setup_name,
            description=f'Automatisch aus Backtest-Result #{result_id} erzeugt',
            backtest_config_json=new_backtest_config_json,
            indicators_config_json=new_indicators_config_json,
            strategy_config_json=new_strategy_config_json,
            ui_state_json=new_ui_state_json,
        )
        session.add(setup_row)
        session.commit()
        session.refresh(setup_row)

        return {
            'data': {
                'setup_id': setup_row.id,
                'name': setup_row.name,
                'url': f'/chart-playground?setupid={setup_row.id}',
            },
            'error': None,
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Run Backtest (Generic Spec Runner über Playground-State)
# ---------------------------------------------------------------------------
class RunBacktestIn(BaseModel):
    indicators: dict      # {name -> {indicator, tf, inputs, enabled, <params>}, _stops: {tp_stop, sl_stop, ...}}
    rules: dict           # {entry: {...}, exit: None|{...}}
    portfolio: dict       # {size, size_type, init_cash, fees, stop_exit_price, stop_order_type}
    data: dict            # {exchange, symbols, timeframe, start, end, ohlc_start, ohlc_end}
    name: Optional[str] = None           # optional Strategie-Name für DB
    concept_slug: Optional[str] = None  # Strategie-Konzept (nur informativ)
    # GEÄNDERT: Voller Run nutzt die im Dropdown gewählte (gespeicherte) Iteration; keine Auto-Registrierung mehr
    iteration_id: Optional[int] = None
    # GEÄNDERT: Herkunfts-Referenzen der im Playground gewählten Configs (lose, optional)
    backtest_config_id: Optional[int] = None
    indicator_config_id: Optional[int] = None


def _build_backtest_config(req: RunBacktestIn) -> dict:
    """Baut das backtest_config-Dict aus dem Request-Payload.

    Helper-Funktion für /run-backtest-lite.
    Stellt sicher, dass Portfolio-Eingabeparameter unverändert durchgereicht werden.
    """
    from user_data.strategies.generic.spec_runner import SPEC_RUNNER_IMPORT_PATH
    strategy_name = req.name or f'pg_spec_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
    return {
        **req.data,
        'portfolio': req.portfolio,
        'strategy_family': 'playground',
        'strategy_name': strategy_name,
        'import_path': SPEC_RUNNER_IMPORT_PATH,
    }


def _indicators_with_stops(req: "RunBacktestIn") -> dict:
    """Liefert die Indikator-Config inkl. '_stops'-Meta-Key (Schritt 4d).

    Der Spec-Runner liest die Stops aus indicators_json['_stops']. Das Frontend
    sendet '_stops' jetzt bereits in req.indicators (Wire-Format-Vertrag) — daher
    wird die Config nur durchgereicht. Fehlt '_stops' (direkter API-Call), werden
    KEINE Stops ergänzt (kein Fallback); der Spec-Runner liest dann keine Stops.
    """
    return dict(req.indicators)


@router.post('/run-backtest-lite')
def run_backtest_lite(req: RunBacktestIn) -> dict:
    """Lite-Backtest: nur Total Return + Trade-Anzahl, kein DB-Schreiben.

    Kein create_backtest_run, kein save_strategy_results.
    Wird genutzt für den Schnellbacktest-Button im Chart-Playground.
    """
    import time
    from user_data.strategies.generic.spec_runner import run_spec_strategy
    from user_data.utils.ohlc.loader import load_ohlc_data

    # GEÄNDERT: Ticket 23 — gemeinsame Helper-Funktion nutzen (DRY)
    backtest_config = _build_backtest_config(req)

    try:
        ohlc_data = load_ohlc_data(backtest_config)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f'OHLC-Daten laden fehlgeschlagen: {e}')

    # GEÄNDERT: Schritt 1 — Stops als '_stops'-Meta-Key in die Indikator-Config spiegeln
    indicators_with_stops = _indicators_with_stops(req)

    t_start = time.monotonic()
    try:
        strategy_results = run_spec_strategy(
            ohlc_data, indicators_with_stops, backtest_config, req.rules,
        )
    except Exception as e:
        # GEÄNDERT: Reiner Fehlertext — das Quell-Label ("Schnellbacktest: ") setzt das Frontend-Banner
        raise HTTPException(status_code=500, detail=f'{e}')
    duration_ms = int((time.monotonic() - t_start) * 1000)

    portfolios = strategy_results['portfolios']

    # GEÄNDERT: Auf erste Kombi reduzieren — analog save_strategy_results, damit pf.value
    # eine Series statt einer mehrspaltigen DataFrame ist (sonst iteriert .items() Spalten).
    try:
        columns = portfolios.wrapper.columns
        pf = portfolios[columns[0]] if len(columns) >= 1 else portfolios
    except Exception:
        pf = portfolios

    # GEÄNDERT: Equity-Kurve aus pf.value extrahieren (Format identisch zu /chart-data:
    # Liste von {time: epoch_seconds, value: float}), damit Frontend dieselbe
    # ResultOverlay.renderEquityCurve-Routine wie der volle Lauf nutzen kann.
    equity: list[dict] = []
    try:
        equity_series = pf.value
        for ts, val in equity_series.items():
            try:
                fval = float(val)
                if np.isnan(fval) or np.isinf(fval):
                    continue
            except (TypeError, ValueError):
                continue
            try:
                t_epoch = int(pd.Timestamp(ts).timestamp())
            except Exception:
                continue
            equity.append({'time': t_epoch, 'value': fval})
    except Exception:
        equity = []

    # GEÄNDERT: Trade-Daten für Marker im Chart (analog /trades), damit Schnellanalyse
    # die Entry/Exit-Marker, gepunktete Dauer-Linien und PnL-Labels rendern kann.
    trades_data: list[dict] = []
    try:
        trades_records = pf.trades.records_readable
        orders_records = pf.orders.records_readable
        order_stop_types: dict[int, str] = {}
        try:
            for _, orow in orders_records.iterrows():
                st = str(orow.get('Stop Type', '') or '')
                if st and st != 'None':
                    order_stop_types[int(orow['Order Id'])] = st
        except Exception:
            pass

        # GEÄNDERT: Schritt 4d — Stops liegen jetzt in req.indicators._stops (nicht mehr im Portfolio)
        _stops = req.indicators.get('_stops') if isinstance(req.indicators, dict) else None
        if not isinstance(_stops, dict):
            _stops = {}
        # Defensiv: Range-Objekte (dict) als None behandeln — Playground-Stops sind skalar
        tp_stop = _stops.get('tp_stop')
        if isinstance(tp_stop, dict):
            tp_stop = None
        sl_stop = _stops.get('sl_stop')
        if isinstance(sl_stop, dict):
            sl_stop = None

        for _, row in trades_records.iterrows():
            try:
                entry_ts = pd.Timestamp(row.get('Entry Index')) if row.get('Entry Index') is not None else None
                exit_ts = pd.Timestamp(row.get('Exit Index')) if row.get('Exit Index') is not None else None
                entry_price = float(row.get('Avg Entry Price')) if row.get('Avg Entry Price') is not None else None
                exit_price = float(row.get('Avg Exit Price')) if row.get('Avg Exit Price') is not None else None
                exit_order_id = row.get('Exit Order Id')
                exit_order_id_int = int(exit_order_id) if exit_order_id is not None and not pd.isna(exit_order_id) else None
                return_raw = row.get('Return', 0)
                return_pct = float(return_raw) * 100 if return_raw is not None and not pd.isna(return_raw) else None
                pnl_raw = row.get('PnL')
                pnl_val = float(pnl_raw) if pnl_raw is not None and not pd.isna(pnl_raw) else None
                size_raw = row.get('Size')
                size_val = float(size_raw) if size_raw is not None and not pd.isna(size_raw) else None

                trade_data: dict = {
                    'exit_trade_id': int(row['Exit Trade Id']) if row.get('Exit Trade Id') is not None else None,
                    'position_id': int(row.get('Position Id')) if row.get('Position Id') is not None and not pd.isna(row.get('Position Id')) else None,
                    'direction': str(row.get('Direction', 'Long')),
                    'status': str(row.get('Status', 'Closed')),
                    'entry_time': int(entry_ts.timestamp()) if entry_ts is not None and not pd.isna(entry_ts) else None,
                    'entry_price': entry_price,
                    'entry_order_id': int(row.get('Entry Order Id')) if row.get('Entry Order Id') is not None and not pd.isna(row.get('Entry Order Id')) else None,
                    'exit_time': int(exit_ts.timestamp()) if exit_ts is not None and not pd.isna(exit_ts) else None,
                    'exit_price': exit_price,
                    'exit_order_id': exit_order_id_int,
                    'exit_stop_type': order_stop_types.get(exit_order_id_int, '') if exit_order_id_int is not None else '',
                    'pnl': pnl_val,
                    'return_pct': return_pct,
                    'size': size_val,
                }
                # GEÄNDERT: Ticket 46 — TP/SL-Preise richtungsabhängig berechnen
                trade_direction = str(row.get('Direction', 'Long'))
                if entry_price and tp_stop:
                    if trade_direction == 'Short':
                        trade_data['tp_price'] = entry_price * (1 - float(tp_stop))
                    else:
                        trade_data['tp_price'] = entry_price * (1 + float(tp_stop))
                if entry_price and sl_stop:
                    if trade_direction == 'Short':
                        trade_data['sl_price'] = entry_price * (1 + float(sl_stop))
                    else:
                        trade_data['sl_price'] = entry_price * (1 - float(sl_stop))
                trades_data.append(trade_data)
            except Exception:
                continue
    except Exception:
        trades_data = []

    # GEÄNDERT: Zusätzliche Kennzahlen für den Schnellbacktest-Badge — billige
    # Portfolio-Properties (kein teures pf.stats(), passt zum Lite-Charakter).
    # total_market_return = Benchmark-Buy-and-Hold-Rendite als Fraction (z.B. 0.25 = 25 %).
    try:
        profit_factor = _pf_scalar(pf.trades.profit_factor)
    except Exception:
        profit_factor = None
    try:
        benchmark_return = _pf_scalar(pf.total_market_return)
    except Exception:
        benchmark_return = None
    try:
        max_drawdown = _pf_scalar(pf.max_drawdown)
    except Exception:
        max_drawdown = None

    return {
        'data': {
            'total_return': _pf_scalar(pf.total_return),
            'benchmark_return': benchmark_return,
            'profit_factor': profit_factor,
            'max_drawdown': max_drawdown,
            'trades': len(pf.trades.records_readable),
            'duration_ms': duration_ms,
            'equity': equity,
            'trades_data': trades_data,
        },
        'error': None,
    }


def _pf_scalar(value: Any) -> Optional[float]:
    """Extrahiert einen Skalar aus Portfolio-Kennzahlen (Series/Scalar)."""
    try:
        if hasattr(value, 'iloc'):
            value = value.iloc[0] if len(value) > 0 else None
        if hasattr(value, 'item'):
            value = value.item()
        return float(value) if value is not None else None
    except Exception:
        return None
