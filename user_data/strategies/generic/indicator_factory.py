"""Baut Indikatoren aus einem indicators_json Spec-Dict.

Der Generic Spec Runner nutzt dieses Modul um:
  1. Indikator-Typen über die Registry aufzulösen
  2. Parameter-Ranges als Arrays aufzulösen (immer Multi-Combo-fähig)
  3. Inputs zu resolven (OHLCV-Feld oder 'indicator:<id>:<output>'-Referenz)
  4. Indikatoren in topologisch sortierter Reihenfolge zu berechnen

Für sehr große Multiparameter-Läufe (> chunk_size Kombis) stellt
`split_indicators_json_chunks` eine Chunking-Funktion bereit, die den
Parameter-Grid mehrdimensional (über alle variierenden Achsen) so aufteilt,
dass jeder Block höchstens chunk_size Kombis trägt und ein gültiges
kartesisches Sub-Produkt bleibt.

Spec-Format (flach, ohne 'inputs'-Wrapper):
  {
    "ema_fast": {
      "indicator": "vbt:talib:EMA",
      "tf": "4h", "enabled": true,
      "real": "Close",                          # Input (Name aus factory.input_names)
      "timeperiod": 10                          # Param
    },
    "ema_slow": {
      "indicator": "vbt:talib:EMA",
      "tf": "4h", "enabled": true,
      "real": "indicator:ema_fast:real",        # Chaining-Input auf einen anderen Indikator
      "timeperiod": 20                          # Param
    }
  }

Inputs vs. Params werden anhand factory.input_names / factory.param_names getrennt.
Metafelder: 'indicator', 'tf', 'enabled'. Alles andere muss in einer der beiden
Listen vorkommen.
"""

from typing import Any, Optional

import numpy as np
import pandas as pd

from user_data.strategies.generic.registry import resolve_indicator_factory
from user_data.strategies.generic.tf_resample import (
    normalize_tf,
    realign_to_index,
    resampled_ohlc,
    tf_to_timedelta,
    validate_tf,
)
from user_data.utils.functions.converter import convert_range_json_numpy_arrays


# Indikator-Keys, die weder Input noch Parameter sind (Metafelder)
_META_KEYS = {'indicator', 'tf', 'enabled'}


class _RealignedIndicator:
    """Kapselt einen am Per-Indikator-Timeframe (tf) berechneten Indikator.

    Liefert dessen Outputs look-ahead-sicher auf den Basis-Index realignt zurueck.
    Transparent fuer alle Konsumenten, die Outputs ueber `output_names` plus
    `getattr(inst, output_name)` lesen (Rules-Engine, Chaining, DB-Persistenz, Report):
    Output-Namen werden aus dem realignten Dict bedient, alles andere an die echte
    Indikator-Instanz delegiert.

    Hintergrund: Eine echte vbt-Indikator-Instanz traegt ihren tf-Index fest (kuerzere
    Laenge). Ihn nachtraeglich auf den Basis-Index zu tauschen ist nicht moeglich — die
    realignten Output-Serien (Basis-Laenge) werden daher separat gehalten.
    """

    def __init__(self, inst: Any, realigned_outputs: dict[str, Any]) -> None:
        # Direkt ins __dict__, damit __getattr__ fuer diese Felder nicht ausgeloest wird.
        self.__dict__['_inst'] = inst
        self.__dict__['_realigned'] = realigned_outputs
        self.__dict__['output_names'] = tuple(getattr(inst, 'output_names', ()) or ())

    def __getattr__(self, name: str) -> Any:
        # __getattr__ greift nur bei Attributen, die NICHT im __dict__ stehen.
        realigned = self.__dict__['_realigned']
        if name in realigned:
            return realigned[name]
        return getattr(self.__dict__['_inst'], name)


# GEÄNDERT: Schritt 1 Stops-Quelle — reservierte Top-Level-Keys in indicators_json,
# die KEINE Indikatoren sind (z.B. '_stops'). Alles mit '_'-Präfix gilt als
# Meta-Eintrag und wird von jeder Key-Iteration über indicators_json ausgeschlossen.
def _is_indicator_key(key: str) -> bool:
    """True, wenn ein Top-Level-Key in indicators_json einen Indikator beschreibt (kein Meta-Key)."""
    return not key.startswith('_')


def indicator_keys(indicators_json: dict) -> list[str]:
    """Liefert alle echten Indikator-Keys aus indicators_json (ohne Meta-Keys wie '_stops')."""
    return [k for k in indicators_json.keys() if _is_indicator_key(k)]


# Stop-Parameter, die der Spec-Runner aus indicators_json['_stops'] liest (Single Source).
STOP_PARAM_KEYS = ('tp_stop', 'sl_stop', 'tsl_th', 'tsl_stop', 'td_stop')

# GEÄNDERT: Schritt 2 — Das gekoppelte TSL-Paar. Sind BEIDE Keys als Sweep angegeben
# (Liste/Range), werden sie als zusammengehörige Paare (zip) gekoppelt — gleiches
# vbt.Param-Level, KEIN Kreuzprodukt.
_TSL_PAIR_KEYS = ('tsl_th', 'tsl_stop')


def expand_stop_values(value: Any, stop_key: str) -> list:
    """Expandiert einen einzelnen '_stops'-Wert zu einer Werteliste (Length >= 1).

    Skalar/None -> einelementige Liste. Liste/Tuple/ndarray -> Liste. Range-Dict
    (mit 'type', z.B. {'type':'arange',...}) -> via convert_range_json_numpy_arrays
    expandiert. Nutzt dieselbe Mechanik wie Indikator-Parameter (_expand_range),
    damit es keinen zweiten Parser gibt.

    Args:
        value: Roher '_stops'-Wert (Skalar, None, Liste oder Range-Dict).
        stop_key: Name des Stops (für Fehlermeldungen).

    Returns:
        Liste der konkreten Stop-Werte (Length >= 1).

    Raises:
        ValueError: Bei leerer Liste/Range oder unbekanntem Wert-Typ.
    """
    # Range-Dict und Skalar/None deckt _expand_range bereits ab. Leere Container
    # liefern eine leere Liste — die weisen wir hier explizit ab.
    values = _expand_range(value, '_stops', stop_key)
    if len(values) == 0:
        raise ValueError(
            f"Stop-Parameter {stop_key!r}: leere Werteliste/Range — bitte mindestens "
            f"einen Wert angeben oder den Key weglassen."
        )
    return values


def is_stop_sweep(value: Any) -> bool:
    """True, wenn ein '_stops'-Wert eine Sweep-Achse ist (Liste oder Range-Dict)."""
    if isinstance(value, (list, tuple, np.ndarray)):
        return True
    if isinstance(value, dict) and 'type' in value:
        return True
    return False


def count_stop_combos(stops_cfg: dict) -> int:
    """Zählt die Stop-Kombinationen aus einem '_stops'-Dict.

    Unabhängige Sweep-Stops (tp_stop, sl_stop, td_stop) multiplizieren sich. Wird
    das TSL-Paar (tsl_th + tsl_stop) gemeinsam gesweept, zählt es als EINE Achse
    der Paar-Länge (zip-Kopplung, kein Kreuzprodukt). Skalare zählen als 1.

    Args:
        stops_cfg: Das '_stops'-Dict (kann fehlen/leer sein).

    Returns:
        Anzahl der Stop-Kombinationen (>= 1).

    Raises:
        ValueError: Bei TSL-Paar-Längen-Mismatch oder leerer Sweep-Achse.
    """
    if not stops_cfg:
        return 1

    n = 1
    tsl_th_swept = is_stop_sweep(stops_cfg.get('tsl_th'))
    tsl_stop_swept = is_stop_sweep(stops_cfg.get('tsl_stop'))

    # Gekoppeltes TSL-Paar: beide gesweept -> eine Achse der (geprüften) Paar-Länge.
    if tsl_th_swept and tsl_stop_swept:
        th_vals = expand_stop_values(stops_cfg.get('tsl_th'), 'tsl_th')
        stop_vals = expand_stop_values(stops_cfg.get('tsl_stop'), 'tsl_stop')
        if len(th_vals) != len(stop_vals):
            raise ValueError(
                f"Gekoppelter TSL-Sweep: tsl_th ({len(th_vals)} Werte) und tsl_stop "
                f"({len(stop_vals)} Werte) müssen gleich lang sein — sie werden als "
                f"Paare (zip) gekoppelt, kein Kreuzprodukt."
            )
        n *= len(th_vals)

    # Übrige Stops als unabhängige Achsen (TSL-Paar bereits behandelt).
    for key in STOP_PARAM_KEYS:
        if key in _TSL_PAIR_KEYS and tsl_th_swept and tsl_stop_swept:
            continue
        val = stops_cfg.get(key)
        if is_stop_sweep(val):
            n *= len(expand_stop_values(val, key))
    return n


def stops_from_portfolio(portfolio_cfg: dict) -> dict:
    """Extrahiert die Stop-Werte aus einem portfolio-Konfig-Block für den '_stops'-Meta-Key.

    Übergangsbrücke (Schritt 1): Die BacktestConfig bleibt Wertequelle der Stops;
    diese Funktion legt sie in das von indicators_json['_stops'] erwartete Skalar-Dict.
    """
    return {key: portfolio_cfg.get(key) for key in STOP_PARAM_KEYS}


# Param-Alias-Map: Spec-Feldname -> Factory-Param-Name pro Indikator-Typ.
# Aktuell leer — dwsFastSMA nutzt seit Ticket 19 direkt 'multiplier'.
_PARAM_ALIASES: dict[str, dict[str, str]] = {}


def _normalize_alias_key(type_id: str) -> str:
    """Vereinheitlicht Typ-IDs, damit 'dwsFastSMA' und 'custom:dwsFastSMA' denselben Alias-Eintrag finden."""
    return type_id.split(':', 1)[1] if type_id.startswith('custom:') else type_id


# Standard-OHLCV-Mapping: spec-Input-Wert (lowercase) -> ohlc_data.get()-Schlüssel
_OHLCV_MAP = {
    'open':   'Open',
    'high':   'High',
    'low':    'Low',
    'close':  'Close',
    'volume': 'Volume',
}


# GEÄNDERT: NaN-sicherer Indikator-Lauf. Beim Per-Indikator-tf erzeugt das Resampling
# fuer Zeitfenster ohne zugrundeliegende Basis-Bars (Datenluecken) NaN-Bars. TA-Lib
# (und die meisten talib-basierten Indikatoren) propagieren ein einzelnes NaN in der
# Mitte der Serie bis zum Serienende — der Indikator wird ab der ersten Luecke konstant
# (im Chart: flache Linie), was via realign_closing(ffill=True) bis zum Rand durchschlaegt.
# Loesung (kanonisch laut VBT): skipna=True laesst den Indikator nur auf den Nicht-NaN-
# Werten laufen und setzt die Ergebnisse an die Originalpositionen zurueck. split_columns=True
# ist Voraussetzung, damit skipna auch bei Multi-Combo-Laeufen (mehrspaltige Inputs) greift.
def run_indicator_nan_safe(factory: Any, *args: Any, **run_kwargs: Any) -> Any:
    """Ruft ``factory.run`` mit look-ahead-sicherer NaN-Behandlung auf.

    Setzt ``skipna=True`` und ``split_columns=True``, damit ein einzelnes NaN in einer
    (z.B. durch Resampling an Datenluecken entstandenen) Input-Serie nicht via TA-Lib bis
    zum Serienende durchschlaegt. Ohne NaN-Werte sind beide Argumente ein No-Op — die
    Ergebnisse bleiben unveraendert.

    Args:
        factory: VBT IndicatorFactory-Objekt (talib-, vbt- oder custom-Indikator).
        *args: Positionale Argumente fuer ``factory.run`` (z.B. Input-Serien).
        **run_kwargs: Weitere run-Argumente (Params, ``param_product`` usw.).

    Returns:
        Die vom Indikator gelieferte Instanz.
    """
    return factory.run(*args, skipna=True, split_columns=True, **run_kwargs)


# GEÄNDERT: Ticket 53 — Getragene Ketten-Param-Level id-benennen (7x-Blowup-Fix).
# Ein Indikator, der einen anderen als Chain-Input traegt, fuehrte dessen Param-Level
# bisher unter dem Factory-Namen (z.B. 'dwsfastsma_length') statt dem Spec-ID-Namen
# ('fast_sma_length') mit. Wird derselbe Indikator zugleich direkt referenziert (dort
# von _uniquify_param_levels bereits auf den ID-Namen umbenannt), gelten die beiden
# Achsen als disjunkt und werden von _combine_broadcast gekreuzt statt gefaltet — die
# Portfolio-Spaltenzahl blaeht sich um den Faktor der geteilten Achse auf. Fix: die
# Instanz wird direkt beim Bauen umbenannt (Variante A), bevor sie als Chain-Input
# oder Direkt-Referenz konsumiert wird. VBT stapelt Input-Columns unveraendert unter
# die neuen Param-Level (build_columns/stack_indexes), der ID-Name propagiert also
# natuerlich durch jede weitere Kettenstufe.
def _rename_indicator_instance(inst: Any, ind_id: str) -> Any:
    """Benennt die Param-Level-Namen einer Indikator-Instanz auf `<ind_id>_<param>` um.

    Ersetzt NICHT `IndicatorBase.rename()`/`.rename_levels()`: beide brechen empirisch
    (per VBT-MCP `run_code` verifiziert) mit `IndexError: tuple index out of range`
    bei Indikatoren mit genau EINEM Parameter (z.B. dwsConst, dwsVWMABand) — VBTs
    `_tuple_mapper` liefert nur ab zwei Params ein MultiIndex, sonst `None`, wodurch
    `level_names` dort strukturell leer bleibt. Beide rename-Methoden indizieren aber
    blind ueber `param_names` in das leere `level_names`-Tupel. Diese Funktion baut die
    Umbenennung stattdessen direkt aus `param_names` + den echten Param-Mapper-Namen auf
    (robust unabhaengig von der Parameterzahl).

    Instanz ist immutable (VBT) — `.replace(...)` gibt eine neue Instanz zurueck, die
    gespeicherte Instanz muss also ersetzt werden (`results[ind_id] = ...`).

    Args:
        inst: Frisch gebaute VBT-Indikator-Instanz (aus `factory.run(...)`).
        ind_id: Spec-Key des Indikators (z.B. 'fast_sma').

    Returns:
        Neue Instanz mit umbenannten Param-Leveln; die uebergebene Instanz unveraendert,
        wenn der Indikator keine Parameter hat oder die Level schon passend benannt sind.
    """
    param_names = tuple(getattr(inst, 'param_names', ()) or ())
    if not param_names:
        return inst

    mappers = {name: getattr(inst, f"_{name}_mapper") for name in param_names}
    rename_map = {
        mapper.name: f"{ind_id}_{name}"
        for name, mapper in mappers.items()
        if mapper.name != f"{ind_id}_{name}"
    }
    if not rename_map:
        return inst

    new_mapper_list = [
        mappers[name].rename(rename_map[mappers[name].name])
        if mappers[name].name in rename_map else mappers[name]
        for name in param_names
    ]

    old_columns = inst.wrapper.columns
    if isinstance(old_columns, pd.MultiIndex):
        new_columns = old_columns.rename(rename_map)
    else:
        # Einzel-Param-Indikator: flacher Index, kein Dict-Rename moeglich (pandas
        # verlangt einen hashable Namen statt Dict) -> den einen Namen direkt ersetzen.
        new_columns = old_columns.rename(rename_map.get(old_columns.name, old_columns.name))

    new_wrapper = inst.wrapper.replace(columns=new_columns)
    return inst.replace(wrapper=new_wrapper, mapper_list=new_mapper_list, short_name=ind_id)


def _rename_realigned_output(df: Any, short_name: Optional[str], param_names: tuple,
                             ind_id: str) -> Any:
    """Benennt Param-Level eines realignten Per-tf-Outputs `<short_name>_<param>` -> `<ind_id>_<param>` um.

    Plain-Pandas-Variante fuer den Per-Indikator-tf-Zweig (`_RealignedIndicator`): die
    dort gehaltenen Outputs sind bereits realignte DataFrames, keine VBT-Instanz mehr —
    `.rename()`/`.rename_levels()` (IndicatorBase-API) greifen hier nicht. Nur tatsaechlich
    vorhandene Level werden umbenannt (analog `_uniquify_param_levels` in rules_engine.py).

    Args:
        df: Realignter Output (DataFrame oder Series) eines Per-tf-Indikators.
        short_name: Factory-Kurzname der inneren Instanz (z.B. 'dwsfastsma').
        param_names: Param-Namen der inneren Instanz.
        ind_id: Spec-Key des Indikators (z.B. 'fast_sma').

    Returns:
        DataFrame mit umbenannten Param-Leveln; unveraendert bei Series oder wenn kein
        Level zum Umbenennen vorhanden ist.
    """
    if not isinstance(df, pd.DataFrame) or not short_name or not param_names:
        return df
    current = set(df.columns.names)
    mapping = {f"{short_name}_{p}": f"{ind_id}_{p}"
               for p in param_names if f"{short_name}_{p}" in current}
    if not mapping:
        return df
    return df.rename_axis(columns=mapping)


def build_indicators(indicators_json: dict, ohlc_data: Any,
                     base_tf: Optional[str] = None) -> dict[str, Any]:
    """Baut alle Indikatoren aus dem Spec in Abhängigkeits-Reihenfolge.

    GEÄNDERT: Per-Indikator-Timeframe (tf) scharf geschaltet (Paket B). Traegt ein
    Indikator ein abweichendes (groeberes) `tf`, wird er nativ auf `ohlc_data.resample(tf)`
    berechnet und jeder Output per `realign_closing` look-ahead-sicher auf den Basis-Index
    zurueckgeholt (Portfolio + Rules laufen am Basis-Raster). Gleicher tf = No-Op; feinerer
    tf (Downsampling) wird abgewiesen. Chained-Inputs werden auf den Rechen-tf mitresampled.

    Args:
        indicators_json: Indikator-Spec (flat).
        ohlc_data: vbt.Data am Basis-Raster (Feature-Config gesetzt).
        base_tf: Basis-Timeframe-String (z.B. '4h'). Dient der No-Op-Erkennung
            (tf == Basis) unabhaengig von `ohlc_data.wrapper.freq` — der Spec-Runner
            reicht den Wert aus der BacktestConfig durch. None faellt auf den
            Frequenz-Vergleich via `ohlc_data.wrapper.freq` zurueck.
    """
    order = _topological_order(indicators_json)
    results: dict[str, Any] = {}

    wrapper = getattr(ohlc_data, 'wrapper', None)
    base_index = getattr(wrapper, 'index', None)
    base_freq = getattr(wrapper, 'freq', None)

    for ind_id in order:
        entry = indicators_json[ind_id]
        if entry.get('enabled', True) is False:
            continue

        type_id = entry['indicator']
        factory = resolve_indicator_factory(type_id)
        params_kwargs = _resolve_params(entry, factory, type_id, ind_id)

        target_tf = _resolve_target_tf(entry.get('tf'), base_freq, base_tf)

        if target_tf is None:
            # Basis-Timeframe: unveraendert (kein Resampling).
            inputs_kwargs = _resolve_inputs(entry, factory, ohlc_data, results, ind_id)
            inst = run_indicator_nan_safe(
                factory, **inputs_kwargs, **params_kwargs, param_product=True
            )
            # GEÄNDERT: Ticket 53 — Param-Level auf den ID-Namen umbenennen, BEVOR die
            # Instanz als Chain-Input oder Direkt-Referenz konsumiert wird (Instanz
            # ersetzen, nicht mutieren — VBT-Instanzen sind immutable).
            results[ind_id] = _rename_indicator_instance(inst, ind_id)
            continue

        # Per-Indikator-tf: auf groeberem Raster rechnen, Outputs auf Basis realignen.
        resampled = resampled_ohlc(ohlc_data, target_tf)
        tf_index = resampled.wrapper.index
        inputs_kwargs = _resolve_inputs(
            entry, factory, resampled, results, ind_id, chain_realign_index=tf_index
        )
        inst = run_indicator_nan_safe(factory, **inputs_kwargs, **params_kwargs, param_product=True)

        # GEÄNDERT: Ticket 53 — dieselbe ID-Umbenennung fuer den Per-tf-Zweig, plain-pandas
        # auf den realignten DataFrames (die innere Instanz bleibt unveraendert, siehe
        # _rename_realigned_output-Docstring).
        short_name = getattr(inst, 'short_name', None)
        param_names = tuple(getattr(inst, 'param_names', ()) or ())
        realigned: dict[str, Any] = {}
        for oname in (getattr(inst, 'output_names', ()) or ()):
            out = getattr(inst, oname, None)
            if out is None:
                continue
            out = realign_to_index(out, base_index, freq=base_freq)
            realigned[oname] = _rename_realigned_output(out, short_name, param_names, ind_id)
        results[ind_id] = _RealignedIndicator(inst, realigned)

    return results


def _resolve_target_tf(raw_tf: Any, base_freq: Any, base_tf: Optional[str] = None) -> Optional[str]:
    """Ermittelt den effektiven Rechen-tf eines Indikators (oder None = Basis-Raster).

    GEÄNDERT: tf 'same' -> None (explizit gleicher tf wie die Basis). Fehlender/leerer tf
    -> ValueError (kein implizites "gleich" mehr, s. normalize_tf). tf gleich Basis (per
    String `base_tf` ODER Frequenz `base_freq`) -> None (No-Op). tf feiner als Basis ->
    ValueError (Downsampling). tf groeber -> der getrimmte tf-String.

    Args:
        raw_tf: Roher 'tf'-Wert aus dem Spec-Eintrag.
        base_freq: Frequenz des Basis-Index (pd.Timedelta) oder None.
        base_tf: Basis-Timeframe-String fuer die No-Op-Erkennung ohne Frequenz.

    Returns:
        Effektiver tf-String oder None.

    Raises:
        ValueError: Wenn tf feiner als die Basis-Frequenz ist.
    """
    target_tf = normalize_tf(raw_tf, base_tf)
    if target_tf is None:
        return None
    if base_freq is not None and tf_to_timedelta(target_tf) == pd.Timedelta(base_freq):
        return None
    validate_tf(target_tf, base_freq)
    return target_tf


def _topological_order(indicators_json: dict) -> list[str]:
    """Sortiert Indikatoren so, dass Abhängigkeiten zuerst berechnet werden.

    Kahn's Algorithmus: Ein Indikator X hängt von Y ab, wenn einer seiner
    Spec-Werte 'indicator:Y:<output>' enthält.
    """
    # GEÄNDERT: Schritt 1 — Meta-Keys ('_'-Präfix, z.B. '_stops') sind keine Indikatoren
    ids = indicator_keys(indicators_json)
    deps: dict[str, set[str]] = {ind_id: set() for ind_id in ids}

    for ind_id in ids:
        entry = indicators_json[ind_id]
        for key, val in (entry or {}).items():
            if key in _META_KEYS:
                continue
            if isinstance(val, str) and val.startswith('indicator:'):
                dep_id = val.split(':', 2)[1]
                if dep_id not in indicators_json:
                    raise ValueError(
                        f"Indikator {ind_id!r} referenziert unbekannten "
                        f"Indikator {dep_id!r}"
                    )
                deps[ind_id].add(dep_id)

    order: list[str] = []
    ready = [i for i in ids if not deps[i]]
    remaining_deps = {k: set(v) for k, v in deps.items()}

    while ready:
        node = ready.pop(0)
        order.append(node)
        for other, other_deps in remaining_deps.items():
            if node in other_deps:
                other_deps.discard(node)
                if not other_deps and other not in order and other not in ready:
                    ready.append(other)

    if len(order) != len(ids):
        missing = set(ids) - set(order)
        raise ValueError(f"Zyklus in Indikator-Abhängigkeiten: {missing}")
    return order


def _resolve_inputs(entry: dict, factory: Any, data_source: Any,
                    prev_results: dict, ind_id: str,
                    chain_realign_index: Any = None) -> dict:
    """Resolved Input-Felder eines Spec-Eintrags zu Series/DataFrames für factory.run().

    Args:
        data_source: vbt.Data, aus dem OHLCV-Inputs gelesen werden — bei Per-Indikator-tf
            das resamplete Data-Objekt, sonst die Basis-Daten.
        chain_realign_index: Ziel-Index, auf den Chained-Inputs (Output eines anderen
            Indikators, am Basis-Raster) realignt werden, wenn dieser Indikator auf einem
            groeberen tf rechnet. None = kein Realign (Basis-Raster).
    """
    input_names = tuple(getattr(factory, 'input_names', ()) or ())

    kwargs = {}
    for input_name in input_names:
        if input_name in entry:
            ref = entry[input_name]
        else:
            # Default: Input-Name selbst als OHLCV-Feld interpretieren (z.B. 'volume' → 'Volume').
            # 'source' fällt auf 'Close' zurück.
            ref = 'close' if input_name.lower() == 'source' else input_name.lower()
        kwargs[input_name] = _resolve_reference(
            ref, data_source, prev_results, ind_id, chain_realign_index
        )
    return kwargs


def _resolve_reference(ref: Any, data_source: Any, prev_results: dict, ctx_ind_id: str,
                       chain_realign_index: Any = None) -> pd.Series:
    """Löst eine Input-Referenz auf: OHLCV-Feld, indicator:<id>:<output> oder Skalar.

    OHLCV-Felder kommen aus `data_source` (bei tf das resamplete Data-Objekt). Chained-
    Referenzen liefern den Output eines anderen Indikators am Basis-Raster; rechnet der
    aktuelle Indikator auf einem groeberen tf (`chain_realign_index` gesetzt), wird der
    Chained-Input look-ahead-sicher (last-in-bucket) auf diesen tf-Index realignt.
    """
    if not isinstance(ref, str):
        raise ValueError(
            f"Input-Referenz in Indikator {ctx_ind_id!r} muss string sein, "
            f"got {type(ref).__name__}: {ref!r}"
        )

    if ref.startswith('indicator:'):
        parts = ref.split(':')
        if len(parts) < 2:
            raise ValueError(f"Ungültige Indikator-Referenz: {ref!r}")
        dep_id = parts[1]
        if dep_id not in prev_results:
            raise ValueError(
                f"Indikator {ctx_ind_id!r} referenziert {dep_id!r}, "
                f"aber {dep_id!r} wurde noch nicht berechnet"
            )
        dep_inst = prev_results[dep_id]
        output_name = parts[2] if len(parts) >= 3 else _default_output(dep_inst)
        series = getattr(dep_inst, output_name)
        if chain_realign_index is not None:
            # Cross-TF-Chaining: Basis-Output auf den groeberen Rechen-tf bringen.
            series = realign_to_index(series, chain_realign_index)
        return series

    key = ref.lower()
    if key in _OHLCV_MAP:
        return data_source.get(_OHLCV_MAP[key])

    raise ValueError(
        f"Unbekannte Input-Referenz {ref!r} in Indikator {ctx_ind_id!r}. "
        f"Erlaubt: OHLCV-Felder {list(_OHLCV_MAP.keys())} oder 'indicator:<id>:<output>'."
    )


def _default_output(ind_instance: Any) -> str:
    """Ermittelt den Standard-Output-Namen einer IndicatorInstance.

    Liest `output_names` instanz-level (nicht ueber `type(...)`), damit auch der
    _RealignedIndicator-Wrapper (Per-Indikator-tf) korrekt aufgeloest wird.
    """
    output_names = tuple(getattr(ind_instance, 'output_names', ()) or ())
    if not output_names:
        raise ValueError(
            f"Indicator-Instanz {type(ind_instance).__name__} hat keine output_names"
        )
    return output_names[0]


def _resolve_params(entry: dict, factory: Any, type_id: str, ind_id: str) -> dict:
    """Extrahiert Parameter aus dem Spec-Eintrag und expandiert Ranges zu Arrays.

    Alle Felder außer Metafeldern und Inputs (factory.input_names) gelten als Params.
    """
    factory_input_names = set(getattr(factory, 'input_names', ()) or ())
    factory_param_names = tuple(getattr(factory, 'param_names', ()) or ())
    alias_map = _PARAM_ALIASES.get(_normalize_alias_key(type_id), {})

    kwargs: dict = {}
    for key, value in entry.items():
        if key in _META_KEYS:
            continue
        if key in factory_input_names:
            continue

        # Alias-Mapping anwenden
        target_name = alias_map.get(key, key)
        if target_name not in factory_param_names:
            raise ValueError(
                f"Indikator {ind_id!r} ({type_id}): Feld {key!r} "
                f"(gemappt zu {target_name!r}) ist weder Input {sorted(factory_input_names)} "
                f"noch Param {factory_param_names}"
            )

        kwargs[target_name] = _expand_range(value, ind_id, key)
    return kwargs


def _expand_range(value: Any, ind_id: str, key: str) -> list:
    """Konvertiert einen Parameter-Wert in eine Liste (immer Length >= 1)."""
    if isinstance(value, (int, float, bool, str)) or value is None:
        return [value]

    if isinstance(value, dict) and 'type' in value:
        arr = convert_range_json_numpy_arrays(value)
        return [_np_scalar_to_python(v) for v in arr]

    if isinstance(value, (list, tuple, np.ndarray)):
        return [_np_scalar_to_python(v) for v in value]

    raise ValueError(
        f"Indikator {ind_id!r} Parameter {key!r}: unbekannter Wert-Typ "
        f"{type(value).__name__}: {value!r}"
    )


def _np_scalar_to_python(val: Any) -> Any:
    """Konvertiert numpy scalar zu python scalar (int/float)."""
    if isinstance(val, np.integer):
        return int(val)
    if isinstance(val, np.floating):
        return float(val)
    return val


def _collect_varying_axes(indicators_json: dict) -> list[tuple[str, str, list]]:
    """Sammelt alle variierenden Indikator-Parameterachsen (aktiviert, Länge > 1).

    Eine Achse variiert, wenn ihr Wert über _expand_range mehr als einen Wert
    ergibt — deckt sowohl Range-Dicts ({start, stop, step}) als auch Listen
    ([a, b, c]) ab. Inputs (OHLC) und Meta-Keys zählen nicht.

    Args:
        indicators_json: Indikator-Spec mit Range-/Listen-Parametern.

    Returns:
        Liste von (ind_id, param_name, values) in topologischer Reihenfolge.
    """
    varying: list[tuple[str, str, list]] = []
    order = _topological_order(indicators_json)
    for ind_id in order:
        entry = indicators_json[ind_id]
        if not isinstance(entry, dict):
            continue
        if entry.get('enabled', True) is False:
            continue
        try:
            factory = resolve_indicator_factory(entry['indicator'])
        except Exception:
            continue
        factory_input_names = set(getattr(factory, 'input_names', ()) or ())
        for key, value in entry.items():
            if key in _META_KEYS or key in factory_input_names:
                continue
            vals = _expand_range(value, ind_id, key)
            if len(vals) > 1:
                varying.append((ind_id, key, vals))
    return varying


def describe_indicator_params(indicators_json: dict) -> list:
    """Listet je aktivem Indikator seine Parameter-Achsen (Skalar oder Range) als Werte-Listen.

    Wie ``_collect_varying_axes``, aber OHNE den Filter auf variierende Achsen — auch feste
    Skalar-Parameter werden aufgeführt. Inputs (OHLC/Chains) und Meta-Keys bleiben außen vor.
    Basis für die lesbare Indikator-Auflistung in der Config-Beschreibung.

    Args:
        indicators_json: Indikator-Spec (mit optionalem '_stops').

    Returns:
        Liste von (ind_id, [(param_name, values), ...]) in topologischer Reihenfolge;
        Indikatoren ohne Parameter werden ausgelassen.
    """
    result: list[tuple[str, list]] = []
    order = _topological_order(indicators_json)
    for ind_id in order:
        entry = indicators_json[ind_id]
        if not isinstance(entry, dict):
            continue
        if entry.get('enabled', True) is False:
            continue
        try:
            factory = resolve_indicator_factory(entry['indicator'])
            factory_input_names = set(getattr(factory, 'input_names', ()) or ())
        except Exception:
            factory_input_names = set()
        params = []
        for key, value in entry.items():
            if key in _META_KEYS or key in factory_input_names:
                continue
            # String-Werte sind Quellen/Chains (Fallback, falls Factory nicht auflösbar), keine Parameter.
            if isinstance(value, str):
                continue
            params.append((key, _expand_range(value, ind_id, key)))
        if params:
            result.append((ind_id, params))
    return result


def describe_combos(indicators_json: dict) -> dict:
    """Kombinationszahl + Achsen-Aufschlüsselung — einzige Wahrheit, was der Motor läuft.

    Liefert die echte Spaltenzahl pro from_signals-Aufruf (Indikator-Kombis x
    Stop-Kombis) sowie eine Liste der variierenden Achsen mit ihrer Werteanzahl.
    Listen-Achsen ([a, b, c]) zählen über _expand_range mit; das gekoppelte
    TSL-Paar (tsl_th + tsl_stop) zählt als EINE Achse.

    Args:
        indicators_json: Indikator-Spec (mit optionalem '_stops').

    Returns:
        {'total': int (>= 1), 'details': list[str]} — Details als "achse: anzahl".

    Raises:
        ValueError: Bei TSL-Paar-Längen-Mismatch (über count_stop_combos).
    """
    details: list[str] = []
    n_indicator_combos = 1
    for ind_id, key, vals in _collect_varying_axes(indicators_json):
        n_indicator_combos *= len(vals)
        details.append(f"{ind_id}.{key}: {len(vals)}")

    stops_cfg = indicators_json.get('_stops', {}) or {}
    # count_stop_combos ist autoritativ für die Zahl (kapselt die TSL-Paar-Kopplung).
    n_stop_combos = count_stop_combos(stops_cfg)

    # Stop-Achsen für die Aufschlüsselung benennen — TSL-Paar als EINE Achse.
    tsl_th_swept = is_stop_sweep(stops_cfg.get('tsl_th'))
    tsl_stop_swept = is_stop_sweep(stops_cfg.get('tsl_stop'))
    if tsl_th_swept and tsl_stop_swept:
        details.append(f"_stops.tsl_pair: {len(expand_stop_values(stops_cfg.get('tsl_th'), 'tsl_th'))}")
    for key in STOP_PARAM_KEYS:
        if key in _TSL_PAIR_KEYS and tsl_th_swept and tsl_stop_swept:
            continue
        val = stops_cfg.get(key)
        if is_stop_sweep(val):
            details.append(f"_stops.{key}: {len(expand_stop_values(val, key))}")

    return {'total': n_indicator_combos * n_stop_combos, 'details': details}


def count_total_combos(indicators_json: dict) -> int:
    """Echte Kombinationszahl (Indikator-Kombis x Stop-Kombis). Wrapper um describe_combos."""
    return describe_combos(indicators_json)['total']


# GEÄNDERT: Ticket 44 — Combo-Batching: indicators_json in kartesische Sub-Grids aufteilen
def split_indicators_json_chunks(
    indicators_json: dict,
    chunk_size: int = 5000,
) -> list[dict]:
    """Teilt indicators_json in kartesische Sub-Grids mit je hoechstens chunk_size Kombis.

    Chunking geschieht mehrdimensional: alle variierenden Achsen (Indikator-Parameter
    plus unabhaengige Stop-Sweeps und das gekoppelte TSL-Paar) werden in zusammen-
    haengende Teil-Listen zerlegt, sodass das Produkt der Teil-Laengen pro Block
    hoechstens chunk_size ergibt. Jeder Block bleibt ein gueltiges kartesisches
    Sub-Produkt; alle Bloecke zusammen decken das volle Grid genau einmal ab.

    GEÄNDERT: Mehrdimensionales Chunking. Die fruehere Fassung teilte nur entlang der
    ERSTEN Achse — reichte deren innerer Rest (Produkt aller uebrigen Achsen) schon
    ueber chunk_size, blieb der Block zu gross und riss den Worker per OOM ab. Die
    mehrdimensionale Aufteilung deckelt jeden Block hart auf chunk_size Kombis.

    Args:
        indicators_json: Indikator-Spec mit Range-/Listen-Parametern (optional '_stops').
        chunk_size: Maximale Kombi-Zahl pro Block (Default: 5000).

    Returns:
        Liste von sub-indicators_json-Dicts. Genau ein Element (das Original, ohne Kopie),
        wenn n_combos <= chunk_size oder keine variierenden Achsen vorhanden sind.

    Raises:
        ValueError: Bei TSL-Paar-Laengen-Mismatch (ueber count_stop_combos/expand_stop_values).
    """
    import copy
    import itertools

    varying = _collect_varying_axes(indicators_json)
    stops_cfg = indicators_json.get('_stops', {}) or {}
    n_stop_combos = count_stop_combos(stops_cfg)

    n_indicator_combos = 1
    for _, _, vals in varying:
        n_indicator_combos *= len(vals)
    n_combos = n_indicator_combos * n_stop_combos

    if n_combos <= chunk_size:
        return [indicators_json]

    # Einheitliche Achsenliste (Laenge, Setter). Indikator-Achsen sind 'aeusser'
    # (zuerst), Stop-Achsen 'inner' (danach) — das haelt die Stops moeglichst
    # vollstaendig (bisheriges Verhalten) und splittet zusaetzlich, wenn ein innerer
    # Rest allein schon ueber chunk_size laege.
    axes = _build_chunk_axes(varying, stops_cfg)

    # Slice-Laenge (step) je Achse greedy von innen nach aussen: die inneren Achsen
    # zuerst moeglichst voll auffuellen, die aeusseren mit dem Restbudget. Die
    # Invariante prod(step) <= chunk_size gilt konstruktionsbedingt — jeder Faktor
    # ist <= chunk_size // (Produkt der bereits gewaehlten inneren Steps).
    steps = [1] * len(axes)
    running = 1
    for i in range(len(axes) - 1, -1, -1):
        room = max(1, chunk_size // running)
        steps[i] = min(axes[i][0], room)
        running *= steps[i]

    # Pro Achse die Slice-Grenzen (start, stop) auflisten, dann das kartesische Produkt
    # aller Achsen-Slices als Chunks materialisieren.
    per_axis_slices = []
    for (length, _setter), step in zip(axes, steps):
        per_axis_slices.append(
            [(start, min(start + step, length)) for start in range(0, length, step)]
        )

    chunks: list[dict] = []
    for slice_combo in itertools.product(*per_axis_slices):
        sub = copy.deepcopy(indicators_json)
        for (_length, setter), (start, stop) in zip(axes, slice_combo):
            setter(sub, start, stop)
        chunks.append(sub)
    return chunks


def _build_chunk_axes(varying: list, stops_cfg: dict) -> list:
    """Baut die einheitliche Achsenliste fuers mehrdimensionale Chunking.

    Jede Achse ist ein Tupel (length, setter). ``setter(sub, start, stop)`` schreibt den
    Slice [start:stop] der Achsenwerte in das Chunk-Dict ``sub``. Reihenfolge: erst die
    variierenden Indikator-Achsen (topologisch), dann die Stop-Achsen. Das gekoppelte
    TSL-Paar bildet EINE Achse ueber die Paar-Position — ein Slice trifft tsl_th und
    tsl_stop synchron, die zip-Kopplung bleibt intakt (das Paar IST entlang seiner
    Position teilbar, es muss nicht als ganzer Block bleiben).

    Args:
        varying: (ind_id, param, values)-Achsen aus _collect_varying_axes.
        stops_cfg: Das '_stops'-Dict der Spec.

    Returns:
        Liste von (length, setter)-Tupeln.
    """
    axes: list = []

    # Indikator-Achsen (aeusser).
    for ind_id, param, values in varying:
        def _make_ind_setter(ind_id=ind_id, param=param, values=values):
            def _set(sub, start, stop):
                sub[ind_id][param] = values[start:stop]
            return _set
        axes.append((len(values), _make_ind_setter()))

    # Stop-Achsen (inner). Gekoppeltes TSL-Paar als EINE Achse, sonst unabhaengige Achsen.
    tsl_pair_swept = (
        is_stop_sweep(stops_cfg.get('tsl_th'))
        and is_stop_sweep(stops_cfg.get('tsl_stop'))
    )
    if tsl_pair_swept:
        th_vals = expand_stop_values(stops_cfg.get('tsl_th'), 'tsl_th')
        stop_vals = expand_stop_values(stops_cfg.get('tsl_stop'), 'tsl_stop')
        # count_stop_combos hat die Laengengleichheit des Paares bereits geprueft.
        def _set_tsl(sub, start, stop, th_vals=th_vals, stop_vals=stop_vals):
            s = sub.setdefault('_stops', {})
            s['tsl_th'] = th_vals[start:stop]
            s['tsl_stop'] = stop_vals[start:stop]
        axes.append((len(th_vals), _set_tsl))

    for key in STOP_PARAM_KEYS:
        if key in _TSL_PAIR_KEYS and tsl_pair_swept:
            continue
        if not is_stop_sweep(stops_cfg.get(key)):
            continue
        vals = expand_stop_values(stops_cfg.get(key), key)
        def _make_stop_setter(key=key, vals=vals):
            def _set(sub, start, stop):
                sub.setdefault('_stops', {})[key] = vals[start:stop]
            return _set
        axes.append((len(vals), _make_stop_setter()))

    return axes
