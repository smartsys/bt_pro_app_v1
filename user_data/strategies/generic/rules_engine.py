"""Wertet rules_json zu Entry-/Exit-Boolean-Series aus.

Conditions haben die Form:
    {
        "lhs": <ref>, "lhs_shift": <int?>,
        "op":  <operator>,
        "rhs": <ref>, "rhs_shift": <int?>
    }

<ref> kann sein:
    - OHLCV-Feld:            "close", "open", "high", "low", "volume"
    - Indikator-Output:      "indicator:<id>:<output>" (oder "indicator:<id>" für Default-Output)
    - State-Primitiv (Exit): "since_entry", "entry_price",
                             "max_price_since_entry", "min_price_since_entry"
    - Skalar:                5.0, 1, True, ...

Operatoren: >, <, >=, <=, ==, !=

Logik-Struktur (disjunktive Normalform):
    Eine Rule-Gruppe (entry/exit) besteht aus Blöcken:
        {"blocks": [{"conditions": [...]}, {"conditions": [...]}]}
    Innerhalb eines Blocks sind die Conditions UND-verknüpft, die Blöcke
    untereinander ODER. Es gibt KEIN 'logic'-Feld mehr — die Verknüpfung
    steckt fest in der Struktur (Block intern UND, zwischen Blöcken ODER).
    Damit lässt sich jede boolesche Logik abbilden.

State-Primitiven (`since_entry`, `entry_price`, `max_price_since_entry`,
`min_price_since_entry`) stehen NUR in Exit-Rules zur Verfügung und werden
ausschließlich nativ ausgewertet:

Masken-Pfad (evaluate_rules):
    Rein statische Entry-/Exit-Rules ohne State-Refs. Liefert (entries, exits)
    als Boolean-Series; das Portfolio wird vom Aufrufer per from_signals(
    entries, exits) gebaut. State-Refs werden hier hart abgewiesen.

Nativer Pfad (evaluate_rules_native):
    Wenn die Exit-Gruppe State-Primitiven enthält, wird ein Hybrid-Split
    verwendet. Statische Conditions werden vorab als Boolean-Array ausgewertet.
    Stateful Conditions werden als kodierte Tabelle an eine Numba
    signal_func_nb übergeben, die den echten Trade-State aus last_pos_info
    liest. Das Portfolio wird über from_signals(signal_func_nb=...) aufgebaut
    statt über entries/exits-Arrays. spec_runner schaltet bei State-Refs in der
    Exit-Gruppe automatisch hierher um.
"""

from typing import Any, NamedTuple, Optional

import operator as _op
import numpy as np
import pandas as pd
import vectorbtpro as vbt
from numba import njit


# GEÄNDERT: Ticket 46 — Vier-Masken-Rückgabe für Long/Short-Unterstützung im Masken-Pfad
class SignalMasks(NamedTuple):
    """Bündelt die vier Signal-Masken des Masken-Pfades.

    long_entries: Long-Entry-Signale (Blöcke ohne is_short=True)
    long_exits: Long-Exit-Signale (Blöcke ohne is_short=True)
    short_entries: Short-Entry-Signale (Blöcke mit is_short=True)
    short_exits: Short-Exit-Signale (Blöcke mit is_short=True)
    """
    long_entries: Any
    long_exits: Any
    short_entries: Any
    short_exits: Any


_OPS = {
    '>':  _op.gt,
    '<':  _op.lt,
    '>=': _op.ge,
    '<=': _op.le,
    '==': _op.eq,
    '!=': _op.ne,
}


_OHLCV_MAP = {
    'open':   'Open',
    'high':   'High',
    'low':    'Low',
    'close':  'Close',
    'volume': 'Volume',
}


_STATE_REFS = {
    'since_entry',
    'entry_price',
    'max_price_since_entry',
    'min_price_since_entry',
}


def _describe_operand(obj: Any) -> str:
    """Kompakte Strukturbeschreibung eines Broadcast-Operanden für Fehlermeldungen.

    Zeigt für DataFrames die Param-Column-Level und Spaltenzahl, für Series den
    Namen, und in beiden Fällen den Zeit-Index (Start/Ende/Länge) — damit beim
    Broadcast-Fehler erkennbar ist, ob Zeit-Index (Timeframe/Resampling) oder
    Param-Columns kollidieren.
    """
    if isinstance(obj, pd.DataFrame):
        idx = obj.index
        span = f"{idx[0]}..{idx[-1]}" if len(idx) else "leer"
        return (f"DataFrame shape={obj.shape}, column-levels={list(obj.columns.names)}, "
                f"n_columns={obj.shape[1]}, index[{len(idx)}] {span}")
    if isinstance(obj, pd.Series):
        idx = obj.index
        span = f"{idx[0]}..{idx[-1]}" if len(idx) else "leer"
        return f"Series name={obj.name!r}, index[{len(idx)}] {span}"
    return f"{type(obj).__name__}: {obj!r}"


def _combine_broadcast(objs: list) -> tuple:
    """Broadcastet Operanden und kreuzt disjunkte Indikator-Param-Level.

    `vbt.broadcast` alignt nur gemeinsame/Teilmengen-Level. Stammen zwei Operanden
    aus Indikatoren mit disjunkten Param-Leveln (z.B. zwei Indikator-Ketten mit
    verschiedenen Param-Leveln), gibt es keine gemeinsame Spalten-Achse — sie
    müssen gekreuzt (Kartesisches Produkt) statt aligned werden.

    GEÄNDERT: Ticket 49 Bugfix — die Entscheidung "alignen vs. kreuzen" hing bisher
    davon ab, ob `vbt.broadcast` eine Exception wirft. Das ist bei disjunkten
    Leveln GLEICHER Breite falsch: `vbt.broadcast` richtet zwei gleich breite
    Operanden dann positionsweise aus (Diagonale, z.B. 3x3 -> 3 statt 9) und wirft
    KEINE Exception, der Kreuz-Pfad griff also nie. Fix: ein echter Gate-Check auf
    den Spalten-Level-NAMEN statt try/except. Sind die Level-Namen-Mengen aller
    DataFrame-Operanden paarweise in einer Teilmengen-/Gleichheits-Beziehung (echt
    alignbar — z.B. gemeinsames `symbol`-Level oder ein Indikator-Level, das im
    anderen Operanden mit enthalten ist), reicht normales `vbt.broadcast`. Sonst
    (mindestens ein Paar mit disjunkten privaten Leveln) wird IMMER gekreuzt: ein
    Ziel-Spalten-Index als Kartesisches Produkt der disjunkten Param-Level wird
    gebaut (via `vbt.base.indexes.cross_indexes`) und jeder Operand per
    `columns_from=target` dorthin expandiert. Gemeinsame Carrier-Level wie `symbol`
    bleiben dabei aligned (werden NIE gekreuzt) — ihre privaten (Nicht-Carrier-)
    Werte werden je Operand über `.unique()` dedupliziert, damit Carrier-bedingte
    Wiederholungen (z.B. dieselben Param-Werte je Symbol) nicht fälschlich mitgekreuzt
    werden. Operanden ohne eigenes privates Level (nur Carrier-Level) tragen keine
    Kreuz-Achse bei und werden aus der Kreuz-Bestimmung herausgenommen.

    Args:
        objs: Liste der zu broadcastenden Series/DataFrames.

    Returns:
        Tuple der broadcasteten Operanden mit identischer Spalten-Struktur.
    """
    if sum(isinstance(o, pd.DataFrame) for o in objs) < 2:
        return vbt.broadcast(*objs)

    dfs = [o for o in objs if isinstance(o, pd.DataFrame)]
    name_sets = [set(d.columns.names) for d in dfs]

    # Gate: alignen reicht nur, wenn JEDES Paar von Level-Namen-Mengen in einer
    # Teilmengen-/Gleichheits-Beziehung steht. Sonst immer kreuzen — nicht mehr
    # vom Exception-Zufall von vbt.broadcast abhängig (Kern von Bug 1).
    pairwise_alignable = all(
        name_sets[i] <= name_sets[j] or name_sets[j] <= name_sets[i]
        for i in range(len(name_sets)) for j in range(i + 1, len(name_sets))
    )
    if pairwise_alignable:
        return vbt.broadcast(*objs)

    # Carrier = Level-Namen, die ALLE DataFrames teilen (typisch: 'symbol').
    carrier = set.intersection(*name_sets)

    def _private(idx):
        """Private (Nicht-Carrier-)Werte eines Spalten-Index, dedupliziert.

        None, wenn der Operand außer Carrier-Leveln keine eigenen Level hat —
        trägt dann keine private Achse zum Kreuzen bei.
        """
        keep = [n for n in idx.names if n not in carrier]
        if not keep:
            return None
        return idx.droplevel(list(carrier)).unique()

    # Maximale Operanden bestimmen: private Level-Menge ist nicht echte Teilmenge
    # eines anderen und kommt nur einmal vor (gleiche Level-Mengen sind redundant).
    privs = [(d, _private(d.columns)) for d in dfs]
    privs = [(d, p) for d, p in privs if p is not None]
    level_sets = [set(p.names) for _, p in privs]
    maximal_idxs: list = []
    seen_sets: list = []
    for i, (_, p) in enumerate(privs):
        ls = level_sets[i]
        if any(j != i and ls < level_sets[j] for j in range(len(privs))):
            continue
        if any(ls == s for s in seen_sets):
            continue
        seen_sets.append(ls)
        maximal_idxs.append(p)

    if len(maximal_idxs) == 1:
        priv_target = maximal_idxs[0]
    else:
        _, priv_target = vbt.base.indexes.cross_indexes(maximal_idxs, return_new_index=True)

    if carrier:
        non_carrier = [n for n in dfs[0].columns.names if n not in carrier]
        carrier_idx = dfs[0].columns.droplevel(non_carrier).unique()
        _, target = vbt.base.indexes.cross_indexes([priv_target, carrier_idx], return_new_index=True)
    else:
        target = priv_target

    return vbt.broadcast(*objs, columns_from=target, align_index=False)


def _broadcast_explained(objs: list, context: str) -> tuple:
    """Cross-fähiges Broadcasting mit aussagekräftiger Fehlermeldung.

    Nutzt `_combine_broadcast` (alignt gemeinsame Level, kreuzt disjunkte
    Param-Level). Scheitert auch das, wird statt des nackten 'Cannot align
    indexes' die Struktur aller Operanden (Shape, Param-Column-Level, Zeit-Index)
    angehängt, damit Zeit-Index- vs. Param-Column-Probleme unterscheidbar sind.

    Args:
        objs: Liste der zu broadcastenden Series/DataFrames.
        context: Beschreibung der Aufrufstelle (z.B. 'Rule-Gruppe').

    Returns:
        Tuple der gebroadcasteten Operanden.

    Raises:
        ValueError: Wenn das Broadcasting scheitert — mit Operanden-Details.
    """
    try:
        return _combine_broadcast(objs)
    except Exception as e:
        details = "\n".join(f"  [{i}] {_describe_operand(o)}" for i, o in enumerate(objs))
        raise ValueError(
            f"Broadcast fehlgeschlagen in {context}: {type(e).__name__}: {e}\n"
            f"Operanden ({len(objs)}):\n{details}\n"
            "Prüfen: Stimmen Zeit-Index (Timeframe/Resampling) UND Param-Column-Level "
            "aller Operanden überein?"
        ) from e


def evaluate_rules(
    rules_json: dict,
    ohlc_data: Any,
    indicators: dict,
) -> 'SignalMasks':
    """Wertet Entry- und Exit-Rules aus rules_json zu vier Boolean-Masken aus.

    GEÄNDERT: Ticket 46 — Gibt jetzt ein SignalMasks-NamedTuple mit vier Masken
    zurück: long_entries, long_exits, short_entries, short_exits. Blöcke mit
    is_short=True erzeugen Short-Masken, alle anderen Long-Masken.

    Reiner Masken-Pfad für Strategien OHNE State-basierte Exits. State-Primitiven
    (`since_entry`, `entry_price`, `max_price_since_entry`, `min_price_since_entry`)
    werden hier NICHT mehr unterstützt — solche Specs laufen über den nativen
    Pfad (`evaluate_rules_native`), der den echten Trade-State per signal_func_nb
    liest. spec_runner schaltet bei State-Refs automatisch dorthin um.

    Args:
        rules_json: Entry/Exit-Rules-Spezifikation
        ohlc_data: vbt.Data mit OHLCV-Serien
        indicators: Dict mit berechneten Indikator-Instanzen

    Returns:
        SignalMasks(long_entries, long_exits, short_entries, short_exits)

    Raises:
        ValueError: Wenn Short-Blöcke vorhanden sind und exit_spec State-Refs enthält
            (Short-Blöcke sind im nativen Pfad nicht unterstützt).
    """
    entry_spec = rules_json.get('entry')
    if entry_spec is None:
        raise ValueError("rules_json muss 'entry'-Rules enthalten")

    # GEÄNDERT: Ticket 46 — Blöcke nach is_short partitionieren
    entry_blocks = entry_spec.get('blocks') or []
    # Guard: Leere Blockliste wird abgewiesen (bestehende Engine-Invariante beibehalten)
    if not entry_blocks:
        raise ValueError("Rule-Gruppe hat keine 'blocks'")
    long_entry_blocks = [b for b in entry_blocks if not b.get('is_short', False)]
    short_entry_blocks = [b for b in entry_blocks if b.get('is_short', False)]

    exit_spec = rules_json.get('exit')
    long_exit_blocks = []
    short_exit_blocks = []
    if exit_spec:
        exit_blocks = exit_spec.get('blocks') or []
        long_exit_blocks = [b for b in exit_blocks if not b.get('is_short', False)]
        short_exit_blocks = [b for b in exit_blocks if b.get('is_short', False)]

    # Referenz-Index für all-False-Masken aus Close-Serie
    close_ref = ohlc_data.get('Close')

    def _make_all_false_like(reference: Any) -> Any:
        """Erzeugt eine all-False-Maske mit derselben Struktur wie reference."""
        if isinstance(reference, pd.DataFrame):
            return pd.DataFrame(False, index=reference.index, columns=reference.columns)
        return pd.Series(False, index=reference.index)

    # Auswertung der vier Masken (None wenn keine Blöcke vorhanden)
    long_entries_raw = None
    long_exits_raw = None
    short_entries_raw = None
    short_exits_raw = None

    if long_entry_blocks:
        long_entries_raw = _evaluate_rule_group(
            {'blocks': long_entry_blocks}, ohlc_data, indicators
        )
    if exit_spec and long_exit_blocks:
        long_exits_raw = _evaluate_rule_group(
            {'blocks': long_exit_blocks}, ohlc_data, indicators
        )
    if short_entry_blocks:
        short_entries_raw = _evaluate_rule_group(
            {'blocks': short_entry_blocks}, ohlc_data, indicators
        )
    if exit_spec and short_exit_blocks:
        short_exits_raw = _evaluate_rule_group(
            {'blocks': short_exit_blocks}, ohlc_data, indicators
        )

    # Referenzstruktur für all-False-Masken bestimmen:
    # Erste vorhandene Maske nehmen (is not None statt or, pandas verträgt kein bool(Series))
    reference = None
    for _candidate in (long_entries_raw, short_entries_raw, long_exits_raw, short_exits_raw):
        if _candidate is not None:
            reference = _candidate
            break
    if reference is None:
        # Fallback: all-False als Series mit Close-Index
        reference = pd.Series(False, index=close_ref.index)

    # None-Werte durch all-False mit passender Struktur ersetzen
    long_entries = long_entries_raw if long_entries_raw is not None else _make_all_false_like(reference)
    long_exits = long_exits_raw if long_exits_raw is not None else _make_all_false_like(reference)
    short_entries = short_entries_raw if short_entries_raw is not None else _make_all_false_like(reference)
    short_exits = short_exits_raw if short_exits_raw is not None else _make_all_false_like(reference)

    return SignalMasks(
        long_entries=long_entries,
        long_exits=long_exits,
        short_entries=short_entries,
        short_exits=short_exits,
    )


def _rule_group_uses_state_refs(group: dict) -> bool:
    """Prüft, ob eine Rule-Group State-Primitiven referenziert.

    Durchläuft alle Blöcke und deren Conditions. State-Refs in der Exit-Gruppe
    schalten spec_runner auf den nativen Pfad um.
    """
    for block in (group.get('blocks') or []):
        for cond in (block.get('conditions') or []):
            for side in ('lhs', 'rhs'):
                ref = cond.get(side)
                if isinstance(ref, str) and ref in _STATE_REFS:
                    return True
    return False


def _evaluate_rule_group(group: dict, ohlc_data: Any, indicators: dict):
    """Wertet eine Rule-Gruppe in disjunktiver Normalform aus.

    Die Gruppe hat die Form {'blocks': [{'conditions': [...]}, ...]}. Innerhalb
    eines Blocks werden die Conditions UND-verknüpft, die Blöcke untereinander
    ODER. Es gibt kein 'logic'-Feld mehr.
    """
    blocks = group.get('blocks')
    if not blocks:
        raise ValueError("Rule-Gruppe hat keine 'blocks'")

    # Alle Conditions aller Blöcke flach auswerten, dann GEMEINSAM broadcasten,
    # damit MultiIndex-Columns aus verschiedenen Indikatoren zur gemeinsamen
    # Struktur vereinigt werden, bevor sie per AND/OR kombiniert werden.
    block_results: list[list] = []
    flat: list = []
    for block in blocks:
        conditions = block.get('conditions') or []
        if not conditions:
            raise ValueError("Rule-Block hat keine conditions")
        res = [_evaluate_condition(cond, ohlc_data, indicators) for cond in conditions]
        block_results.append(res)
        flat.extend(res)

    pd_results = [r for r in flat if isinstance(r, (pd.Series, pd.DataFrame))]
    if len(pd_results) >= 2:
        broadcasted = _broadcast_explained(
            pd_results,
            f"Rule-Gruppe ({len(blocks)} Blöcke ODER-verknüpft)",
        )
        it = iter(broadcasted)
        flat = [next(it) if isinstance(r, (pd.Series, pd.DataFrame)) else r for r in flat]
        # Gebroadcastete Ergebnisse zurück in die Block-Struktur verteilen.
        pos = 0
        for bi, res in enumerate(block_results):
            n = len(res)
            block_results[bi] = flat[pos:pos + n]
            pos += n

    # Je Block UND-Verknüpfung der Conditions ...
    block_masks = []
    for res in block_results:
        combined = res[0]
        for r in res[1:]:
            combined = combined & r
        block_masks.append(combined)

    # ... dann ODER-Verknüpfung der Blöcke.
    result = block_masks[0]
    for m in block_masks[1:]:
        result = result | m

    # NaN -> False (keine Signals bei fehlenden Indikator-Werten)
    if hasattr(result, 'fillna'):
        result = result.fillna(False)
    return result


def _evaluate_condition(cond: dict, ohlc_data: Any, indicators: dict):
    """Wertet eine einzelne Condition aus.

    Nutzt vbt.broadcast() für die Operanden, damit MultiIndex-Columns aus
    param_product-IndicatorFactory-Runs erhalten bleiben und über mehrere
    Indikatoren hinweg zu einer gemeinsamen Column-Struktur vereinigt werden.
    """
    op_name = cond.get('op')
    if op_name not in _OPS:
        raise ValueError(f"Unbekannter Operator: {op_name!r}. Erlaubt: {list(_OPS.keys())}")

    lhs = _resolve_ref(cond['lhs'], ohlc_data, indicators)
    lhs_shift = cond.get('lhs_shift', 0)
    if lhs_shift and hasattr(lhs, 'shift'):
        lhs = lhs.shift(lhs_shift)

    rhs = _resolve_ref(cond['rhs'], ohlc_data, indicators)
    rhs_shift = cond.get('rhs_shift', 0)
    if rhs_shift and hasattr(rhs, 'shift'):
        rhs = rhs.shift(rhs_shift)

    # Broadcast Series/DataFrame-Operanden auf gemeinsame Column-Struktur.
    lhs_is_pd = isinstance(lhs, (pd.Series, pd.DataFrame))
    rhs_is_pd = isinstance(rhs, (pd.Series, pd.DataFrame))
    if lhs_is_pd and rhs_is_pd:
        lhs, rhs = _broadcast_explained([lhs, rhs], f"Condition lhs/rhs (op={op_name!r})")

    return _OPS[op_name](lhs, rhs)


def _uniquify_param_levels(obj: Any, inst: Any, ind_id: str) -> Any:
    """Benennt die Param-Level eines Indikator-Outputs instanz-eindeutig um.

    vbt leitet den Param-Level-Namen vom Indikator-Klassennamen ab
    (`<short_name>_<param>`, z.B. `dwsconst_value` oder `ema_timeperiod`). Zwei
    Instanzen derselben Klasse mit gesweeptem Parameter — etwa zweimal dwsConst als
    Schwellen-Konstante (ADX- und AssetDD-Schwelle) — erzeugen damit denselben
    Level-Namen. `cross_indexes` kann zwei gleichnamige Achsen mit unterschiedlichen
    Werten nicht kreuzen und bricht den Broadcast ab.

    Fix: `<short_name>_<param>` -> `<ind_id>_<param>`. Der Spec-Key (`ind_id`) ist pro
    Iteration eindeutig, damit werden die Achsen instanz-eindeutig und kreuzen sauber.
    Nur echte Param-Level werden umbenannt (aus `inst.param_names` abgeleitet);
    Carrier-Level wie `symbol` bleiben unberuehrt. Reine Werte/Series (kein
    Param-Level) bleiben unveraendert.
    """
    if not isinstance(obj, pd.DataFrame):
        return obj
    short_name = getattr(inst, 'short_name', None)
    param_names = getattr(inst, 'param_names', ()) or ()
    if not short_name or not param_names:
        return obj
    current = set(obj.columns.names)
    mapping = {f"{short_name}_{p}": f"{ind_id}_{p}"
               for p in param_names if f"{short_name}_{p}" in current}
    if mapping:
        obj = obj.rename_axis(columns=mapping)
    return obj


def _resolve_ref(ref: Any, ohlc_data: Any, indicators: dict):
    """Löst eine Condition-Referenz auf (OHLCV, Indikator oder Skalar)."""
    # Skalar
    if isinstance(ref, (int, float, bool)):
        return ref

    if not isinstance(ref, str):
        raise ValueError(f"Condition-Referenz muss str oder Zahl sein, got {type(ref).__name__}: {ref!r}")

    # State-Primitiv: im Masken-Pfad nicht mehr unterstützt — solche Specs
    # laufen über evaluate_rules_native (signal_func_nb liest den echten State).
    if ref in _STATE_REFS:
        raise ValueError(
            f"State-Primitiv {ref!r} wird im Masken-Pfad nicht unterstützt. "
            f"State-basierte Exits laufen ausschließlich über den nativen Pfad "
            f"(evaluate_rules_native). spec_runner schaltet dort automatisch um."
        )

    # Indikator-Output
    if ref.startswith('indicator:'):
        parts = ref.split(':')
        if len(parts) < 2:
            raise ValueError(f"Ungültige Indikator-Referenz: {ref!r}")
        ind_id = parts[1]
        if ind_id not in indicators:
            raise ValueError(f"Unbekannter Indikator {ind_id!r} in Referenz {ref!r}")

        inst = indicators[ind_id]
        if len(parts) >= 3:
            output_name = parts[2]
        else:
            # output_names instanz-level lesen (nicht ueber type(...)), damit auch der
            # _RealignedIndicator-Wrapper (Per-Indikator-tf) korrekt aufgeloest wird.
            output_names = tuple(getattr(inst, 'output_names', ()) or ())
            if not output_names:
                raise ValueError(f"Indikator {ind_id!r} hat keine output_names")
            output_name = output_names[0]
        # Param-Level instanz-eindeutig benennen (verhindert cross_indexes-Kollision
        # bei zwei Instanzen derselben Indikator-Klasse, z.B. zweimal dwsConst).
        return _uniquify_param_levels(getattr(inst, output_name), inst, ind_id)

    # OHLCV-Feld
    key = ref.lower()
    if key in _OHLCV_MAP:
        return ohlc_data.get(_OHLCV_MAP[key])

    raise ValueError(
        f"Unbekannte Condition-Referenz {ref!r}. Erlaubt: Zahl, OHLCV-Feld "
        f"({list(_OHLCV_MAP.keys())}), 'indicator:<id>:<output>' oder State-Primitiv {sorted(_STATE_REFS)}."
    )


# ============================================================================
# NATIVER PFAD (Ticket 35) — Hybrid-Split mit signal_func_nb
# ============================================================================
#
# Kodierungsschema für stateful Conditions (Numba-kompatible Integer-Arrays):
#
#   LHS/RHS-Typ-Codes (lhs_kind / rhs_kind):
#     KIND_STATE  = 0  -> State-Primitiv (lhs_state_idx / rhs_state_idx)
#     KIND_SERIES = 1  -> Series-Operand aus series_bundle[i, col_idx]
#     KIND_SCALAR = 2  -> Skalar aus scalar_vals[cond_idx]
#
#   State-Index-Codes (lhs_state_idx / rhs_state_idx):
#     STATE_SINCE_ENTRY     = 0
#     STATE_ENTRY_PRICE     = 1
#     STATE_MAX_PRICE       = 2
#     STATE_MIN_PRICE       = 3
#
#   Operator-Codes (op_codes):
#     OP_GT = 0, OP_LT = 1, OP_GE = 2, OP_LE = 3, OP_EQ = 4, OP_NE = 5
#
#   Gruppen-Logik-Code (group_logic):
#     LOGIC_AND = 0, LOGIC_OR = 1

# --- Interne Konstanten ---

_KIND_STATE  = np.int8(0)
_KIND_SERIES = np.int8(1)
_KIND_SCALAR = np.int8(2)

_STATE_SINCE_ENTRY = np.int8(0)
_STATE_ENTRY_PRICE = np.int8(1)
_STATE_MAX_PRICE   = np.int8(2)
_STATE_MIN_PRICE   = np.int8(3)

_STATE_INDEX_MAP: dict[str, int] = {
    'since_entry':           0,
    'entry_price':           1,
    'max_price_since_entry': 2,
    'min_price_since_entry': 3,
}

_OP_CODE_MAP: dict[str, int] = {
    '>':  0,
    '<':  1,
    '>=': 2,
    '<=': 3,
    '==': 4,
    '!=': 5,
}

_LOGIC_AND = np.int8(0)
_LOGIC_OR  = np.int8(1)


# --- Numba-Kern: stateful Condition-Tabelle auswerten ---

@njit(cache=True)
def _eval_one_cond_nb(
    k: int,
    op_codes: np.ndarray,
    lhs_kind: np.ndarray,
    lhs_state_idx: np.ndarray,
    lhs_series_col: np.ndarray,
    lhs_scalar: np.ndarray,
    rhs_kind: np.ndarray,
    rhs_state_idx: np.ndarray,
    rhs_series_col: np.ndarray,
    rhs_scalar: np.ndarray,
    since_entry: np.float64,
    entry_price_val: np.float64,
    max_price_val: np.float64,
    min_price_val: np.float64,
    series_vals: np.ndarray,
) -> bool:
    """Wertet die k-te kodierte Condition für den aktuellen Balken/Spalte aus.

    Auflösung von LHS/RHS gemäß Typ-Code (STATE/SERIES/SCALAR) und Anwendung
    des Operators. Wird sowohl vom flachen Interpreter (_eval_stateful_conditions_nb)
    als auch vom Block-Evaluator (_eval_exit_blocks_nb) verwendet.
    """
    # LHS auflösen
    lk = lhs_kind[k]
    if lk == _KIND_STATE:
        si = lhs_state_idx[k]
        if si == _STATE_SINCE_ENTRY:
            lv = since_entry
        elif si == _STATE_ENTRY_PRICE:
            lv = entry_price_val
        elif si == _STATE_MAX_PRICE:
            lv = max_price_val
        else:
            lv = min_price_val
    elif lk == _KIND_SERIES:
        lv = series_vals[lhs_series_col[k]]
    else:
        lv = lhs_scalar[k]

    # RHS auflösen
    rk = rhs_kind[k]
    if rk == _KIND_STATE:
        si = rhs_state_idx[k]
        if si == _STATE_SINCE_ENTRY:
            rv = since_entry
        elif si == _STATE_ENTRY_PRICE:
            rv = entry_price_val
        elif si == _STATE_MAX_PRICE:
            rv = max_price_val
        else:
            rv = min_price_val
    elif rk == _KIND_SERIES:
        rv = series_vals[rhs_series_col[k]]
    else:
        rv = rhs_scalar[k]

    # Operator anwenden
    op = op_codes[k]
    if op == 0:
        return lv > rv
    elif op == 1:
        return lv < rv
    elif op == 2:
        return lv >= rv
    elif op == 3:
        return lv <= rv
    elif op == 4:
        return lv == rv
    else:
        return lv != rv


@njit(cache=True)
def _eval_stateful_conditions_nb(
    n_conds: int,
    op_codes: np.ndarray,
    lhs_kind: np.ndarray,
    lhs_state_idx: np.ndarray,
    lhs_series_col: np.ndarray,
    lhs_scalar: np.ndarray,
    rhs_kind: np.ndarray,
    rhs_state_idx: np.ndarray,
    rhs_series_col: np.ndarray,
    rhs_scalar: np.ndarray,
    group_logic: np.int8,
    # State-Werte für den aktuellen Balken/Spalte
    since_entry: np.float64,
    entry_price_val: np.float64,
    max_price_val: np.float64,
    min_price_val: np.float64,
    # Indikator/OHLCV-Operanden für den aktuellen Balken, Dim = (n_series_cols,)
    series_vals: np.ndarray,
) -> bool:
    """Wertet eine FLACHE Condition-Liste mit einer group_logic (AND/OR) aus.

    Bleibt als Mini-Interpreter-Primitive erhalten (direkt unit-getestet). Der
    Block-Pfad nutzt _eval_exit_blocks_nb, das je Block UND und zwischen Blöcken
    ODER kombiniert.

    Returns:
        Kombiniertes Boolean-Ergebnis aller Conditions.
    """
    # Startwert für AND/OR-Kombination
    result = group_logic == _LOGIC_AND  # AND startet mit True, OR mit False

    for k in range(n_conds):
        cond_val = _eval_one_cond_nb(
            k,
            op_codes, lhs_kind, lhs_state_idx, lhs_series_col, lhs_scalar,
            rhs_kind, rhs_state_idx, rhs_series_col, rhs_scalar,
            since_entry, entry_price_val, max_price_val, min_price_val,
            series_vals,
        )
        if group_logic == _LOGIC_AND:
            result = result and cond_val
            if not result:
                return False  # Kurzschluss-Auswertung
        else:
            result = result or cond_val
            if result:
                return True  # Kurzschluss-Auswertung

    return result


@njit(cache=True)
def _eval_exit_blocks_nb(
    n_blocks: int,
    block_start: np.ndarray,        # (n_blocks+1,) int64 — Grenzen der stateful Conds je Block
    op_codes: np.ndarray,
    lhs_kind: np.ndarray,
    lhs_state_idx: np.ndarray,
    lhs_series_col: np.ndarray,
    lhs_scalar: np.ndarray,
    rhs_kind: np.ndarray,
    rhs_state_idx: np.ndarray,
    rhs_series_col: np.ndarray,
    rhs_scalar: np.ndarray,
    # Statische Block-Maske für (Balken i, Spalte static_col): (n_blocks, T, W)
    static_block: np.ndarray,
    i: int,
    static_col: int,
    # State-Werte für den aktuellen Balken/Spalte
    since_entry: np.float64,
    entry_price_val: np.float64,
    max_price_val: np.float64,
    min_price_val: np.float64,
    series_vals: np.ndarray,
) -> bool:
    """Wertet die Exit-Gruppe in DNF aus: je Block UND, zwischen Blöcken ODER.

    Pro Block werden die stateful Conditions (Index-Range block_start[b]..block_start[b+1])
    UND-verknüpft und mit der vorberechneten statischen Block-Maske UND-kombiniert.
    Die Blöcke werden anschließend ODER-verknüpft (Kurzschluss).

    Returns:
        True wenn mindestens ein Block einen Exit liefert.
    """
    for b in range(n_blocks):
        # Stateful-Teil des Blocks: UND der Conditions block_start[b]..block_start[b+1]
        block_and = True
        ks = block_start[b]
        ke = block_start[b + 1]
        for k in range(ks, ke):
            cv = _eval_one_cond_nb(
                k,
                op_codes, lhs_kind, lhs_state_idx, lhs_series_col, lhs_scalar,
                rhs_kind, rhs_state_idx, rhs_series_col, rhs_scalar,
                since_entry, entry_price_val, max_price_val, min_price_val,
                series_vals,
            )
            block_and = block_and and cv
            if not block_and:
                break

        # Statischen Block-Teil UND-kombinieren ...
        block_exit = block_and and static_block[b, i, static_col]
        # ... Blöcke ODER-verknüpfen (Kurzschluss)
        if block_exit:
            return True

    return False


@njit(cache=True)
def _state_exit_signal_func_nb(
    c,
    # GEÄNDERT: Ticket 47 Bugfix — Combo-Spalten-Mapping für Multi-Combo + Stop-Sweep.
    # Das Portfolio hat n_total = n_combo * n_stops Spalten, die Masken aber nur
    # n_combo Spalten (Stop ist die äußere Achse, Indikator-Combo die innere).
    # combo_col_map[c.col] = c.col % n_combo liefert die zugehörige Indikator-Spalte
    # der 2D-Entry/Exit/static-Block-Masken. Für reines Single-Combo identisch [0..N-1].
    combo_col_map: np.ndarray,      # (n_total,) int64
    # Long-Entry-Maske: immer 2D (T, n_combo) — Single-Combo als (T, 1) normalisiert
    entry_mask: np.ndarray,
    # Short-Entry-Maske: immer 2D (T, n_combo) — gleiche Form wie entry_mask
    short_entry_mask: np.ndarray,
    # Long-Exit-Block-Struktur (disjunktive Normalform)
    n_blocks: np.int64,
    block_start: np.ndarray,        # (n_blocks+1,) int64 — Grenzen der stateful Conds je Block
    # Statische Block-Maske für Long-Exits: (n_blocks, T, W)
    static_block: np.ndarray,
    # Stateful Condition-Kodierung für Long-Exits (flach, block-geordnet via block_start)
    op_codes: np.ndarray,
    lhs_kind: np.ndarray,
    lhs_state_idx: np.ndarray,
    lhs_series_col: np.ndarray,
    lhs_scalar: np.ndarray,
    rhs_kind: np.ndarray,
    rhs_state_idx: np.ndarray,
    rhs_series_col: np.ndarray,
    rhs_scalar: np.ndarray,
    # Series-Bundle für Long-Exits: (T, n_series_cols) oder (1,1) wenn keine Series
    series_bundle: np.ndarray,
    n_series_cols: np.int64,
    # Spalten-Mapping für Multi-Combo: series_col_map[col] -> Basis-Spalte in series_bundle
    series_col_map: np.ndarray,     # (N,) int-Array; für Single-Combo immer 0
    # Short-Exit-Block-Struktur (disjunktive Normalform)
    n_short_blocks: np.int64,
    short_block_start: np.ndarray,  # (n_short_blocks+1,) int64
    # Statische Block-Maske für Short-Exits: (n_short_blocks, T, W)
    short_static_block: np.ndarray,
    # Stateful Condition-Kodierung für Short-Exits
    short_op_codes: np.ndarray,
    short_lhs_kind: np.ndarray,
    short_lhs_state_idx: np.ndarray,
    short_lhs_series_col: np.ndarray,
    short_lhs_scalar: np.ndarray,
    short_rhs_kind: np.ndarray,
    short_rhs_state_idx: np.ndarray,
    short_rhs_series_col: np.ndarray,
    short_rhs_scalar: np.ndarray,
    # Series-Bundle für Short-Exits
    short_series_bundle: np.ndarray,
    short_n_series_cols: np.int64,
    short_series_col_map: np.ndarray,
    # OHLCV für max/min-Tracking (volle 1D-Arrays)
    close_arr: np.ndarray,          # (T,)
    high_arr: np.ndarray,           # (T,)
    low_arr: np.ndarray,            # (T,)
    # Pro-Spalte-Tracking-Arrays (werden in-place aktualisiert)
    track_entry_idx: np.ndarray,    # (N,) int64 — letzter Entry-Bar
    track_max_price: np.ndarray,    # (N,) float64
    track_min_price: np.ndarray,    # (N,) float64
) -> tuple:
    """Numba-signal_func_nb für State-basierte Exit-Conditions in DNF.

    GEÄNDERT: Ticket 47 — Short-Unterstützung. Wertet Long- und Short-Exits
    separat anhand der aktuellen Positions-Direction aus c.last_pos_info aus.

    Liest den echten Trade-State aus c.last_pos_info und wertet je nach Direction
    die Long- oder Short-Exit-Gruppe block-weise aus (_eval_exit_blocks_nb):
    je Block UND der stateful Conditions UND der vorberechneten statischen
    Block-Maske, zwischen den Blöcken ODER.

    entry_mask / short_entry_mask sind immer 2D (T, N), static_block /
    short_static_block immer 3D (n_blocks, T, W) — auch für Single-Combo,
    damit Numba einen einheitlichen Typ kompiliert.

    direction in last_pos_info: 0 = Long, 1 = Short.

    Returns:
        (is_long_entry, is_long_exit, is_short_entry, is_short_exit)
    """
    i = c.i
    col = c.col

    # GEÄNDERT: Ticket 47 Bugfix — Indikator-Combo-Spalte aus dem Portfolio-Spalten-
    # Index ableiten. Bei Multi-Combo + Stop-Sweep hat das Portfolio n_combo*n_stops
    # Spalten (Stop außen, Indikator innen), die Masken aber nur n_combo Spalten.
    # combo_col = col % n_combo (vorab in combo_col_map kodiert). State (last_pos_info)
    # und Tracking bleiben pro Portfolio-Spalte (col), Masken werden über combo_col gelesen.
    combo_col = combo_col_map[col]

    # Entry-Masken durchreichen (Entry-Pfad unverändert), immer 2D
    is_long_entry = entry_mask[i, combo_col]
    is_short_entry = short_entry_mask[i, combo_col]

    # Trade-State aus last_pos_info lesen
    pos = c.last_pos_info[col]
    position_open = (pos['status'] == 0) and (pos['entry_idx'] >= 0)

    if position_open:
        entry_idx = pos['entry_idx']
        entry_price_val = pos['entry_price']
        since_entry_val = np.float64(i - entry_idx)
        direction = pos['direction']  # 0 = Long, 1 = Short

        # max/min inkrementell führen — Reset bei neuem Trade
        if track_entry_idx[col] != entry_idx:
            track_entry_idx[col] = entry_idx
            track_max_price[col] = high_arr[i]
            track_min_price[col] = low_arr[i]
        else:
            h = high_arr[i]
            l = low_arr[i]
            if h > track_max_price[col]:
                track_max_price[col] = h
            if l < track_min_price[col]:
                track_min_price[col] = l

        max_price_val = track_max_price[col]
        min_price_val = track_min_price[col]

        if direction == 0:
            # Long-Position: gleichen Entry-Typ unterdrücken; Short-Entry durchlassen
            # (upon_opposite_entry='Reverse' in from_signals dreht bei Short-Entry um)
            is_long_entry = False

            # Long-Exit-Blöcke auswerten
            if n_series_cols > 0:
                base_col = series_col_map[col]
                series_vals = series_bundle[i, base_col:base_col + n_series_cols]
            else:
                series_vals = np.empty(0, dtype=np.float64)

            static_col = combo_col if static_block.shape[2] > 1 else 0

            is_long_exit = _eval_exit_blocks_nb(
                n_blocks,
                block_start,
                op_codes, lhs_kind, lhs_state_idx, lhs_series_col, lhs_scalar,
                rhs_kind, rhs_state_idx, rhs_series_col, rhs_scalar,
                static_block, i, static_col,
                since_entry_val, entry_price_val, max_price_val, min_price_val,
                series_vals,
            )
            is_short_exit = False
        else:
            # Short-Position: gleichen Entry-Typ unterdrücken; Long-Entry durchlassen
            # (upon_opposite_entry='Reverse' in from_signals dreht bei Long-Entry um)
            is_short_entry = False

            # Short-Exit-Blöcke auswerten
            if short_n_series_cols > 0:
                short_base_col = short_series_col_map[col]
                short_series_vals = short_series_bundle[i, short_base_col:short_base_col + short_n_series_cols]
            else:
                short_series_vals = np.empty(0, dtype=np.float64)

            short_static_col = combo_col if short_static_block.shape[2] > 1 else 0

            is_short_exit = _eval_exit_blocks_nb(
                n_short_blocks,
                short_block_start,
                short_op_codes, short_lhs_kind, short_lhs_state_idx, short_lhs_series_col, short_lhs_scalar,
                short_rhs_kind, short_rhs_state_idx, short_rhs_series_col, short_rhs_scalar,
                short_static_block, i, short_static_col,
                since_entry_val, entry_price_val, max_price_val, min_price_val,
                short_series_vals,
            )
            is_long_exit = False
    else:
        is_long_exit = False
        is_short_exit = False

    return is_long_entry, is_long_exit, is_short_entry, is_short_exit


# --- Python-seitiger Aufbau der Condition-Kodierung ---

def _is_state_ref(ref: Any) -> bool:
    """Gibt True zurück wenn ref ein State-Primitiv ist."""
    return isinstance(ref, str) and ref in _STATE_REFS


def _is_state_ref_with_shift(ref: Any, shift: int) -> bool:
    """Gibt True zurück wenn ref ein State-Primitiv MIT shift ist (out of scope)."""
    return _is_state_ref(ref) and shift != 0


def _resolve_series_operand(
    ref: Any,
    shift: int,
    ohlc_data: Any,
    indicators: dict,
) -> tuple:
    """Löst einen Series-Operanden auf und gibt (Array, columns) zurück.

    Shift wird Python-seitig vorangestellt (N4): Das zurückgegebene Array
    enthält bereits den geshifteten Operanden.

    Args:
        ref: Condition-Referenz (OHLCV oder Indikator).
        shift: Shift-Wert (wird als pandas .shift() angewendet).
        ohlc_data: vbt.Data-Objekt.
        indicators: Berechnete Indikatoren.

    Returns:
        Tuple (arr, columns): arr ist ein 1D- (Series) oder 2D-Array (DataFrame,
        Multi-Combo). columns ist der pandas-Spalten-Index bei DataFrame, sonst None.
    """
    series = _resolve_ref(ref, ohlc_data, indicators)
    if shift:
        series = series.shift(shift)
    if isinstance(series, pd.DataFrame):
        # Für Multi-Combo: alle Spalten als Block behalten (werden später gemappt)
        return np.asarray(series.values, dtype=np.float64), series.columns
    return np.asarray(series.values, dtype=np.float64).ravel(), None


def _build_stateful_condition_spec(
    conditions: list[dict],
    ohlc_data: Any,
    indicators: dict,
) -> dict:
    """Baut die Numba-Kodierung für stateful Conditions auf (Phase 1).

    Nur Conditions, die mind. eine State-Ref enthalten, werden kodiert.
    Conditions mit State-Ref + shift werden hard-abgewiesen (out of scope).

    Für Series-Operanden in stateful Conditions wird der shift Python-seitig
    in das series_bundle vorverlagert (N4).

    Args:
        conditions: Nur die stateful Conditions (gefiltert).
        ohlc_data: vbt.Data-Objekt.
        indicators: Berechnete Indikatoren.

    Returns:
        dict mit allen Numba-kompatiblen Arrays plus 'series_bundle' (numpy 2D).

    Raises:
        ValueError: Bei shift auf State-Ref oder unbekannten Refs.
    """
    n = len(conditions)

    op_codes      = np.empty(n, dtype=np.int8)
    lhs_kind      = np.empty(n, dtype=np.int8)
    lhs_state_idx = np.empty(n, dtype=np.int8)
    lhs_series_col= np.empty(n, dtype=np.int64)
    lhs_scalar    = np.empty(n, dtype=np.float64)
    rhs_kind      = np.empty(n, dtype=np.int8)
    rhs_state_idx = np.empty(n, dtype=np.int8)
    rhs_series_col= np.empty(n, dtype=np.int64)
    rhs_scalar    = np.empty(n, dtype=np.float64)

    # Series-Slots: (Array, is_dataframe)
    series_slots: list[tuple[np.ndarray, bool]] = []
    # Parallele Liste mit dem pandas-Spalten-Index je Slot (None bei 1D-Operand) —
    # für die combo_columns-Ableitung (Multi-Combo-Spalten-Identität).
    series_slot_columns: list[tuple[np.ndarray, bool, Any]] = []

    def _add_series_slot(ref: Any, shift: int) -> int:
        """Fügt einen Series-Operanden in die Slot-Liste ein (Deduplizierung weg, einfach)."""
        arr, cols = _resolve_series_operand(ref, shift, ohlc_data, indicators)
        is_df = arr.ndim == 2
        idx = len(series_slots)
        series_slots.append((arr, is_df))
        series_slot_columns.append((arr, is_df, cols))
        return idx

    def _encode_side(ref: Any, shift: int, cond_idx: int, side: str) -> None:
        """Kodiert eine Seite (LHS oder RHS) einer Condition."""
        # Guard: State-Ref mit shift ist out of scope
        if _is_state_ref(ref) and shift:
            raise ValueError(
                f"Condition {cond_idx}: shift auf State-Primitiv '{ref}' ist out of scope "
                f"(Schritt 1 unterstützt keinen shift auf State-Seite). "
                f"Bitte lhs_shift/rhs_shift von State-Refs entfernen."
            )
        if side == 'lhs':
            k_arr, s_arr, sc_arr, sl_arr = lhs_kind, lhs_state_idx, lhs_series_col, lhs_scalar
        else:
            k_arr, s_arr, sc_arr, sl_arr = rhs_kind, rhs_state_idx, rhs_series_col, rhs_scalar

        if _is_state_ref(ref):
            k_arr[cond_idx] = _KIND_STATE
            s_arr[cond_idx] = _STATE_INDEX_MAP[ref]
        elif isinstance(ref, (int, float, bool)):
            k_arr[cond_idx] = _KIND_SCALAR
            sl_arr[cond_idx] = float(ref)
        else:
            # OHLCV oder Indikator -> Series-Slot
            k_arr[cond_idx] = _KIND_SERIES
            slot_idx = _add_series_slot(ref, shift)
            sc_arr[cond_idx] = slot_idx

    for idx, cond in enumerate(conditions):
        op_name = cond.get('op')
        if op_name not in _OP_CODE_MAP:
            raise ValueError(f"Unbekannter Operator: {op_name!r}")
        op_codes[idx] = _OP_CODE_MAP[op_name]

        lhs_ref   = cond.get('lhs')
        lhs_shift = int(cond.get('lhs_shift') or 0)
        rhs_ref   = cond.get('rhs')
        rhs_shift = int(cond.get('rhs_shift') or 0)

        _encode_side(lhs_ref, lhs_shift, idx, 'lhs')
        _encode_side(rhs_ref, rhs_shift, idx, 'rhs')

    # GEÄNDERT: Ticket 47 Bugfix — Series-Bundle in COMBO-MAJOR-Layout. Pro Combo-
    # Spalte stehen alle Slots nebeneinander: [combo0_slot0, combo0_slot1, ...,
    # combo1_slot0, ...]. So selektiert die signal_func mit base_col = (col % n_combo)
    # * n_slots den Block einer Combo, und lhs/rhs_series_col indexiert den Slot
    # INNERHALB dieses Blocks (0..n_slots-1). Ein 1-spaltiger (globaler) Slot wird auf
    # alle Combos broadcastet. Single-Combo (n_combo==1) fällt darauf zurück: ein
    # Block, base_col immer 0, Slot-Index == frühere Slot-Position.
    # Slot-Spalten-Index des breitesten DataFrame-Slots (für combo_columns-Ableitung)
    spec_combo_columns = None
    if series_slots:
        T = series_slots[0][0].shape[0]
        n_slots = len(series_slots)
        # n_combo aus dem breitesten DataFrame-Slot ableiten (1, wenn keiner 2D ist)
        n_combo_local = 1
        for arr, is_df in series_slots:
            if is_df and arr.shape[1] > n_combo_local:
                n_combo_local = arr.shape[1]

        # Combo-major aufbauen: für jede Combo alle Slots als Spalten.
        bundle_cols: list[np.ndarray] = []
        for cc in range(n_combo_local):
            for arr, is_df in series_slots:
                if is_df:
                    # Pro-Combo-Spalte; 1-spaltiger DataFrame -> Spalte 0 für alle Combos
                    col_idx = cc if arr.shape[1] > 1 else 0
                    bundle_cols.append(arr[:, col_idx].reshape(T, 1))
                else:
                    # Globaler 1D-Operand -> gleiche Spalte für alle Combos
                    bundle_cols.append(arr.reshape(T, 1))
        series_bundle = np.concatenate(bundle_cols, axis=1).astype(np.float64)

        # lhs/rhs_series_col tragen bereits die Slot-Position (0..n_slots-1) — im
        # combo-major-Block ist das genau der Index innerhalb des Combo-Blocks.

        # n_series_cols ist die Block-Breite EINER Combo (= Anzahl Slots), damit die
        # signal_func mit series_bundle[i, base:base+n_series_cols] genau einen Block liest.
        n_series_cols_total = n_slots
        spec_n_combo = n_combo_local
        # Spalten-Index des breitesten DataFrame-Slots für combo_columns merken
        for arr, is_df, cols in series_slot_columns:
            if is_df and cols is not None and len(cols) == n_combo_local and n_combo_local > 1:
                spec_combo_columns = cols
                break
    else:
        series_bundle = np.zeros((1, 1), dtype=np.float64)
        n_series_cols_total = 0
        spec_n_combo = 1

    return {
        'n_conds':        n,
        'op_codes':       op_codes,
        'lhs_kind':       lhs_kind,
        'lhs_state_idx':  lhs_state_idx,
        'lhs_series_col': lhs_series_col,
        'lhs_scalar':     lhs_scalar,
        'rhs_kind':       rhs_kind,
        'rhs_state_idx':  rhs_state_idx,
        'rhs_series_col': rhs_series_col,
        'rhs_scalar':     rhs_scalar,
        'series_bundle':  series_bundle,
        'n_series_cols':  n_series_cols_total,
        'n_combo':        spec_n_combo,
        'combo_columns':  spec_combo_columns,
    }


def _build_series_col_map(
    series_bundle: np.ndarray,
    n_total: int,
    n_combo: int,
    is_multi_combo: bool,
) -> np.ndarray:
    """Baut das Spalten-Mapping der Series-Operanden je Portfolio-Spalte.

    GEÄNDERT: Ticket 47 Bugfix — unterstützt jetzt Multi-Combo + Stop-Sweep. Das
    Portfolio hat n_total = n_combo * n_stops Spalten (Stop außen, Indikator innen),
    das series_bundle aber nur n_combo Blöcke a n_series_per_col Spalten. Jede
    Portfolio-Spalte wird per `combo_col = col % n_combo` auf ihren Bundle-Offset
    `combo_col * n_series_per_col` gemappt.

    Für Single-Combo (oder Bundle mit <= 1 Series-Spalte): alle 0.

    Args:
        series_bundle: Das series_bundle-Array (T, n_combo * n_series_per_col).
        n_total: Anzahl der Portfolio-Spalten (= n_combo * n_stops).
        n_combo: Anzahl der Indikator-Combo-Spalten (Breite der Masken).
        is_multi_combo: True wenn n_combo > 1.

    Returns:
        Int64-Array der Länge n_total mit Bundle-Offset pro Portfolio-Spalte.
    """
    if not is_multi_combo or series_bundle.shape[1] <= 1:
        return np.zeros(n_total, dtype=np.int64)

    # Multi-Combo mit echten Series-Slots: Bundle hat n_combo gleich große Blöcke.
    n_series_per_col = series_bundle.shape[1] // n_combo
    result = np.zeros(n_total, dtype=np.int64)
    for col in range(n_total):
        combo_col = col % n_combo
        result[col] = combo_col * n_series_per_col
    return result


# GEÄNDERT: Ticket 47 Bugfix — Anzahl der Stop-Sweep-Kombinationen aus den
# from_signals-Stop-kwargs bestimmen. Unabhängige vbt.Param (Default-Level)
# multiplizieren sich, gleich-gelevelte Param (gekoppeltes TSL-Paar, level=0)
# werden gezippt (Länge einmal gezählt). So ergibt sich n_total = n_combo * n_stops.
def _count_stop_combos(pf_kwargs: dict) -> int:
    """Zählt die Stop-Sweep-Kombinationen aus den from_signals-kwargs.

    vbt.Param ohne explizites Level (Default = MISSING-Sentinel) bilden je eine
    unabhängige Achse und multiplizieren sich. vbt.Param mit gleichem expliziten
    Level (z.B. gekoppeltes TSL-Paar, level=0) werden gezippt und nur einmal mit
    ihrer Länge gezählt. Skalare/None tragen nichts bei (Faktor 1).

    Args:
        pf_kwargs: from_signals-kwargs (enthält tp_stop/sl_stop/tsl_th/tsl_stop/td_stop).

    Returns:
        Produkt der Stop-Achsen-Längen (>= 1).
    """
    default_mult = 1
    level_lengths: dict[int, int] = {}
    for value in pf_kwargs.values():
        if not isinstance(value, vbt.Param):
            continue
        n = len(value.value)
        if isinstance(value.level, int):
            # Gleich-gelevelte Param werden gezippt — Länge nur einmal zählen.
            level_lengths.setdefault(value.level, n)
        else:
            default_mult *= n
    total = default_mult
    for n in level_lengths.values():
        total *= n
    return total


# GEÄNDERT: Ticket 47 Bugfix — natürliche Combo-Breite der statischen Exit-Conditions
# bestimmen. Die Combo-Achse kann ausschließlich in einer statischen Exit-Condition
# liegen (z.B. close > indicator:sma:real ohne State-Ref), während Entry/close 1-spaltig
# sind. n_combo muss diese Breite kennen, sonst kollabiert das Portfolio.
def _static_conds_combo_width(
    block_static_conds: list,
    ohlc_data: Any,
    indicators: dict,
) -> tuple:
    """Ermittelt die breiteste Combo-Spaltenzahl der statischen Exit-Conditions.

    Wertet je Block dessen statische Conditions als pandas-Maske aus und liest die
    Spaltenzahl. Liefert (max_width, columns) — columns ist der Spalten-Index der
    breitesten Maske (oder None, wenn alle 1-spaltig sind).

    Args:
        block_static_conds: Liste je Block mit dessen statischen Conditions.
        ohlc_data: vbt.Data-Objekt.
        indicators: Berechnete Indikatoren.

    Returns:
        Tuple (max_width: int, columns: pd.Index | None).
    """
    max_width = 1
    columns = None
    for conds in block_static_conds:
        if not conds:
            continue
        mask = _evaluate_rule_group(
            {'blocks': [{'conditions': conds}]}, ohlc_data, indicators
        )
        if isinstance(mask, pd.DataFrame) and mask.shape[1] > max_width:
            max_width = mask.shape[1]
            columns = mask.columns
    return max_width, columns


def _build_static_block_arr(
    block_static_conds: list,
    ohlc_data: Any,
    indicators: dict,
    T: int,
    n_cols: int,
    combo_columns: Any = None,
) -> np.ndarray:
    """Baut die statische Block-Maske (n_blocks, T, W) für den nativen Pfad.

    Je Block wird das UND seiner statischen Conditions per pandas berechnet
    (voll Multi-Combo-fähig). Blöcke ohne statische Conditions werden zu
    all-True. Alle Blöcke werden auf die gemeinsame Spaltenbreite W gebracht
    (1 für Single-Combo, n_cols für Multi-Combo).

    GEÄNDERT: Ticket 49 Bug-2-Fix — eine Block-Maske, deren Achsen eine echte
    Teilmenge der `n_cols`-Achsen sind (z.B. Exit `ema_fast < ema_slow`, schmaler
    als der volle Entry-Kreuz-Combo), wurde bisher per `m[:, :width]` blind
    zugeschnitten — das sprengt bei width>1 UND m.shape[1] != width die
    `arr[b] = m`-Zuweisung, sobald die Maske breiter als 1, aber schmaler als
    width ist ('could not broadcast input array from shape (T,9) into shape
    (T,27)'). Fix: die Maske stattdessen per `vbt.broadcast(mask,
    columns_from=combo_columns, align_index=False)` auf den vollen
    Combo-Spalten-Index EXPANDIEREN (kreuzen mit den fehlenden Achsen), statt
    sie zu truncaten. `combo_columns` ist der volle Combo-Spalten-MultiIndex aus
    `evaluate_rules_native` (`_consider`).

    Args:
        block_static_conds: Liste je Block mit dessen statischen Conditions.
        ohlc_data: vbt.Data-Objekt.
        indicators: Berechnete Indikatoren.
        T: Anzahl der Balken.
        n_cols: Portfolio-Spalten (close).
        combo_columns: Voller Combo-Spalten-MultiIndex (Breite n_cols), auf den
            schmalere Teilmengen-Masken expandiert werden. None nur zulässig,
            wenn n_cols <= 1 (Single-Combo, keine Expansion nötig).

    Returns:
        Bool-Array (n_blocks, T, W).
    """
    n_blocks = len(block_static_conds)
    width = n_cols if n_cols > 1 else 1
    arr = np.ones((n_blocks, T, width), dtype=np.bool_)

    for b, conds in enumerate(block_static_conds):
        if not conds:
            continue  # keine statischen Conditions -> all True
        mask = _evaluate_rule_group(
            {'blocks': [{'conditions': conds}]}, ohlc_data, indicators
        )
        if isinstance(mask, pd.DataFrame):
            n_mask_cols = mask.shape[1]
            if n_mask_cols == 1 and width > 1:
                m = np.repeat(mask.fillna(False).astype(bool).values, width, axis=1)
            elif n_mask_cols != width:
                # Teilmengen- (oder allgemein nicht direkt passende) Maske auf den
                # vollen Combo-Spalten-Index kreuzen statt zu truncaten.
                if combo_columns is None:
                    raise ValueError(
                        "Block-Maske mit abweichender Breite "
                        f"({n_mask_cols} != {width}), aber kein combo_columns übergeben."
                    )
                expanded = vbt.broadcast(mask, columns_from=combo_columns, align_index=False)
                m = expanded.fillna(False).astype(bool).values
            else:
                m = mask.fillna(False).astype(bool).values
        else:
            m = mask.fillna(False).astype(bool).values.reshape(T, 1)
            if width > 1:
                m = np.repeat(m, width, axis=1)
        arr[b] = m

    return arr



def evaluate_rules_native(
    rules_json: dict,
    ohlc_data: Any,
    indicators: dict,
    pf_kwargs: dict,
    date_start: Optional[Any] = None,
    date_end: Optional[Any] = None,
    stops_swept: bool = False,
) -> Any:
    """Nativer Pfad: Portfolio direkt per from_signals(signal_func_nb=...) aufbauen.

    GEÄNDERT: Ticket 47 — Long+Short-Unterstützung. Entry-Blöcke werden nach
    is_short partitioniert; Short-Exit-Blöcke werden separat kodiert und an
    _state_exit_signal_func_nb übergeben. Rein statische Specs (flat_stateful leer)
    sind erlaubt — n_blocks > 0 reicht.

    Wird von spec_runner aufgerufen wenn die Exit-Gruppe State-Primitiven enthält.
    Entry-Pfad unverändert (pandas-basiert). Exit-Pfad in disjunktiver Normalform:
    je Block UND, zwischen Blöcken ODER. Pro Block werden die statischen Conditions
    vorab als pandas-Maske berechnet und die stateful Conditions nativ per Numba
    signal_func_nb ausgewertet (_eval_exit_blocks_nb).

    Unterstützt Single-Combo oder Multi-Combo OHNE Series-Operanden in stateful
    Conditions (N5: Multi-Combo mit stateful Series-Ops wird hard-abgewiesen).
    Multi-Combo mit reinen State-Refs oder Skalaren in stateful Conditions läuft.

    Args:
        rules_json: Entry-/Exit-Rules-Spezifikation.
        ohlc_data: vbt.Data-Objekt.
        indicators: Berechnete Indikatoren.
        pf_kwargs: Portfolio-Parameter für from_signals (OHNE entries/exits/signal_func_nb).
            Muss 'close' enthalten.
        date_start: Optionaler Startzeitpunkt für die Date-Mask auf die Entry-Maske.
        date_end: Optionaler Endzeitpunkt für die Date-Mask auf die Entry-Maske.
        stops_swept: True, wenn pf_kwargs gesweepte Stop-vbt.Param-Achsen enthält.
            Dann ist nur Single-Combo zulässig (siehe Raises) — VBT broadcastet die
            signal_func-Entry-Maske nicht entlang einer Stop-Param-Achse.

    Returns:
        vbt.Portfolio-Objekt.

    Raises:
        ValueError: Bei verschachtelten Gruppen, shift auf State-Refs,
            Multi-Combo mit stateful Series-Operanden, oder Stop-Sweep
            kombiniert mit Multi-Combo-Indikatoren (still-falsch-Schutz).
    """
    entry_spec = rules_json.get('entry')
    if entry_spec is None:
        raise ValueError("rules_json muss 'entry'-Rules enthalten")
    exit_spec = rules_json.get('exit')
    # Kein exit_spec: alle Exit-Blöcke sind leer; Positionen schließen nur per Stops.

    # N3: Verschachtelung explizit abweisen
    _assert_flat_group(entry_spec, 'entry')
    if exit_spec:
        _assert_flat_group(exit_spec, 'exit')

    # GEÄNDERT: Ticket 47 — Entry-Blöcke nach is_short partitionieren
    # GEÄNDERT: Ticket 48 — deaktivierte Blöcke (enabled: false) vor der Partitionierung herausfiltern.
    # Fehlt 'enabled', gilt True (abwärtskompatibel). Alle aktiven Blöcke laufen unverändert.
    raw_entry_blocks = entry_spec.get('blocks') or []
    active_entry_blocks = [b for b in raw_entry_blocks if b.get('enabled', True)]
    long_entry_blocks = [b for b in active_entry_blocks if not b.get('is_short', False)]
    short_entry_blocks = [b for b in active_entry_blocks if b.get('is_short', False)]

    # GEÄNDERT: Ticket 47 Phase 2 — Exit-Blöcke nach is_short partitionieren.
    # GEÄNDERT: Ticket 48 — deaktivierte Exit-Blöcke ebenfalls herausfiltern (vor jeder Auswertung).
    # Fehlt exit_spec komplett, sind alle Exit-Blöcke leer (Stops übernehmen den Exit).
    raw_exit_blocks = (exit_spec.get('blocks') or []) if exit_spec else []
    active_exit_blocks = [b for b in raw_exit_blocks if b.get('enabled', True)]
    long_exit_blocks = [b for b in active_exit_blocks if not b.get('is_short', False)]
    short_exit_blocks = [b for b in active_exit_blocks if b.get('is_short', False)]

    # Long-Entry-Maske berechnen (unverändert)
    if long_entry_blocks:
        entries = _evaluate_rule_group({'blocks': long_entry_blocks}, ohlc_data, indicators)
    else:
        close_ref = ohlc_data.get('Close')
        entries = pd.Series(False, index=close_ref.index)

    # Short-Entry-Maske berechnen
    if short_entry_blocks:
        short_entries_raw = _evaluate_rule_group({'blocks': short_entry_blocks}, ohlc_data, indicators)
    else:
        close_ref = ohlc_data.get('Close')
        short_entries_raw = pd.Series(False, index=close_ref.index)

    close_series = pf_kwargs['close']

    # --- Long-Exit-Blöcke aufbereiten ---
    def _parse_exit_blocks(
        blocks: list[dict],
    ) -> tuple[int, np.ndarray, list[list[dict]], list[dict]]:
        """Parst Exit-Blöcke: trennt stateful/statisch, gibt (n_blocks, block_start, static_conds, flat_stateful)."""
        flat_sf: list[dict] = []
        static_conds: list[list[dict]] = []
        start_list: list[int] = [0]
        for blk in blocks:
            conds = blk.get('conditions') or []
            if not conds:
                raise ValueError("Exit-Block hat keine conditions")
            st = [c for c in conds if _cond_has_state_ref(c)]
            sf = [c for c in conds if not _cond_has_state_ref(c)]
            flat_sf.extend(st)
            static_conds.append(sf)
            start_list.append(len(flat_sf))
        return len(blocks), np.asarray(start_list, dtype=np.int64), static_conds, flat_sf

    n_long_exit_blocks, long_block_start, long_static_conds, long_flat_stateful = (
        _parse_exit_blocks(long_exit_blocks) if long_exit_blocks else (0, np.array([0], dtype=np.int64), [], [])
    )
    n_short_exit_blocks, short_block_start, short_static_conds, short_flat_stateful = (
        _parse_exit_blocks(short_exit_blocks) if short_exit_blocks else (0, np.array([0], dtype=np.int64), [], [])
    )

    # GEÄNDERT: Ticket 47 Bugfix — N5-Guard (kein Series-Op in stateful Conditions bei
    # Multi-Combo) und der Stop-Sweep-x-Multi-Combo-ValueError sind entfernt. Beide
    # Fälle laufen jetzt vektorisiert: die signal_func liest über combo_col_map
    # (col % n_combo) die richtige Indikator-Spalte; close wird auf die n_combo
    # Indikator-Spalten gebracht (close_mc), sodass die Stop-vbt.Param-Achse das
    # Kreuzprodukt Stop x Indikator erzeugt (Stop außen, Indikator innen).

    # Stateful Condition-Kodierung aufbauen (je Long/Short getrennt)
    long_spec = _build_stateful_condition_spec(long_flat_stateful, ohlc_data, indicators)
    short_spec = _build_stateful_condition_spec(short_flat_stateful, ohlc_data, indicators)

    # GEÄNDERT: Ticket 47 Bugfix — n_combo (Anzahl Indikator-Param-Spalten) aus der
    # breitesten Quelle ableiten: Entry-/Short-Entry-Masken, close ODER den stateful
    # Series-Bundles (Combo-Achse kann ausschließlich in einem Exit-Series-Operanden
    # liegen). combo_columns hält den Spalten-MultiIndex dieser Indikator-Achse für
    # close_mc, damit das Portfolio den vollen Spalten-Index trägt.
    # combo_columns wird mit >= aktualisiert (nicht nur >), damit auch ein Single-Combo-
    # Chunk (Breite 1) seinen Indikator-Param-Spalten-Label behält (z.B. timeperiod=15),
    # statt auf den Default-Label 0 zu kollabieren. n_combo bleibt das Maximum der Breiten.
    combo_columns = None
    n_combo = 1

    def _consider(width: int, columns: Any) -> None:
        nonlocal n_combo, combo_columns
        if width > n_combo:
            n_combo = width
        if columns is not None and width >= n_combo:
            combo_columns = columns

    if isinstance(close_series, pd.DataFrame):
        _consider(close_series.shape[1], close_series.columns)
    for _mask in (entries, short_entries_raw):
        if isinstance(_mask, pd.DataFrame):
            _consider(_mask.shape[1], _mask.columns)
    for _spec in (long_spec, short_spec):
        _consider(_spec['n_combo'], _spec['combo_columns'])
    # Statische Exit-Conditions können die einzige Combo-Achse tragen (kein State-Ref).
    for _static_conds in (long_static_conds, short_static_conds):
        _w, _cols = _static_conds_combo_width(_static_conds, ohlc_data, indicators)
        _consider(_w, _cols)
    is_multi_combo = n_combo > 1

    # Statische Block-Masken vorab berechnen: je Block AND seiner statischen
    # Conditions (pandas, voll Multi-Combo-fähig); leere Blöcke -> all True.
    T = len(ohlc_data.get('Close'))

    # GEÄNDERT: Ticket 47 Bugfix — statische Block-Masken auf n_combo Spalten (Indikator-
    # Achse), nicht auf close-Spalten. Wenn keine Exit-Blöcke: Platzhalter (1 leerer Block).
    if n_long_exit_blocks == 0:
        long_static_block_arr = np.ones((1, T, n_combo), dtype=bool)
        long_block_start = np.array([0, 0], dtype=np.int64)
        n_long_exit_blocks_nb = np.int64(0)
    else:
        long_static_block_arr = _build_static_block_arr(
            long_static_conds, ohlc_data, indicators, T, n_combo, combo_columns
        )
        n_long_exit_blocks_nb = np.int64(n_long_exit_blocks)

    # Wenn keine Short-Exit-Blöcke: Platzhalter
    if n_short_exit_blocks == 0:
        short_static_block_arr = np.ones((1, T, n_combo), dtype=bool)
        short_block_start = np.array([0, 0], dtype=np.int64)
        n_short_exit_blocks_nb = np.int64(0)
    else:
        short_static_block_arr = _build_static_block_arr(
            short_static_conds, ohlc_data, indicators, T, n_combo, combo_columns
        )
        n_short_exit_blocks_nb = np.int64(n_short_exit_blocks)

    # Date-Range-Mask auf Entry-Signale anwenden (falls angegeben)
    if date_start is not None or date_end is not None:
        idx = ohlc_data.get('Close').index
        date_mask = pd.Series(True, index=idx)
        if date_start is not None:
            date_mask &= (idx >= date_start)
        if date_end is not None:
            date_mask &= (idx <= date_end)
        dm_vals = date_mask.values.reshape(-1, 1)
        if isinstance(entries, pd.DataFrame):
            entries = entries & dm_vals
        else:
            entries = entries & date_mask
        if isinstance(short_entries_raw, pd.DataFrame):
            short_entries_raw = short_entries_raw & dm_vals
        else:
            short_entries_raw = short_entries_raw & date_mask

    # Entry-Masken immer als 2D (T, N) — auch Single-Combo als (T, 1)
    def _to_2d(mask: Any) -> np.ndarray:
        if isinstance(mask, pd.DataFrame):
            arr = mask.fillna(False).astype(bool).values
            if arr.ndim == 1:
                arr = arr.reshape(T, 1)
        else:
            arr = mask.fillna(False).astype(bool).values.reshape(T, 1)
        return arr

    entry_mask_2d = _to_2d(entries)
    short_entry_mask_2d = _to_2d(short_entries_raw)

    # Defensiv: 1-spaltige Masken auf die n_combo Indikator-Spalten verbreitern
    if entry_mask_2d.shape[1] == 1 and n_combo > 1:
        entry_mask_2d = np.repeat(entry_mask_2d, n_combo, axis=1)
    if short_entry_mask_2d.shape[1] == 1 and n_combo > 1:
        short_entry_mask_2d = np.repeat(short_entry_mask_2d, n_combo, axis=1)

    # GEÄNDERT: Ticket 47 Bugfix — n_total = n_combo * n_stops (Portfolio-Spaltenzahl).
    # combo_col_map[col] = col % n_combo mappt jede Portfolio-Spalte auf die Indikator-
    # Spalte der 2D-Masken (Stop außen, Indikator innen). Bei reinem Single-/Multi-Combo
    # ohne Stop-Sweep ist n_stops == 1 und combo_col_map == [0..n_combo-1].
    n_stops = _count_stop_combos(pf_kwargs)
    n_total = n_combo * n_stops
    combo_col_map = np.arange(n_total, dtype=np.int64) % n_combo

    # GEÄNDERT: Ticket 47 Bugfix — close auf die n_combo Indikator-Spalten bringen, damit
    # die Indikator-Param-Achse im Portfolio existiert. Bei Stop-Sweep kreuzt die
    # Stop-vbt.Param-Achse dann mit dieser Indikator-Achse (Stop außen, Indikator innen).
    # Die Spaltenwerte sind alle der reale Close — sie tragen nur die Spalten-Struktur.
    # Auch für n_combo==1 wird close mit dem Indikator-Param-Label versehen (combo_columns),
    # damit Single-Combo-Chunks ihren Spalten-Label behalten (statt Default 0).
    if n_combo > 1 or combo_columns is not None:
        close_1d = (
            close_series.iloc[:, 0].values if isinstance(close_series, pd.DataFrame)
            else close_series.values
        )
        close_mc = pd.DataFrame(
            np.repeat(close_1d.reshape(-1, 1), n_combo, axis=1),
            index=close_series.index,
            columns=combo_columns,
        )
    else:
        close_mc = close_series

    # OHLCV-Arrays für max/min-Tracking
    close_arr = np.asarray(ohlc_data.get('Close').values, dtype=np.float64).ravel()
    high_arr  = np.asarray(ohlc_data.get('High').values,  dtype=np.float64).ravel()
    low_arr   = np.asarray(ohlc_data.get('Low').values,   dtype=np.float64).ravel()

    # Pro-Spalte-Tracking-Arrays initialisieren (Länge n_total = Portfolio-Spalten,
    # da jede Stop-Variante eigenen Trade-State hat)
    track_entry_idx = np.full(n_total, -1, dtype=np.int64)
    track_max_price = np.full(n_total, np.nan, dtype=np.float64)
    track_min_price = np.full(n_total, np.nan, dtype=np.float64)

    # Spalten-Mapping für series_bundle (Long- und Short-Exit getrennt), Länge n_total
    long_series_col_map = _build_series_col_map(
        long_spec['series_bundle'],
        n_total,
        n_combo,
        is_multi_combo,
    )
    short_series_col_map = _build_series_col_map(
        short_spec['series_bundle'],
        n_total,
        n_combo,
        is_multi_combo,
    )

    # signal_args zusammenbauen (alles als numpy-Arrays für Numba)
    # GEÄNDERT: Ticket 47 — Short-Entry-Maske + Short-Exit-Kodierung hinzugefügt
    # GEÄNDERT: Ticket 47 Bugfix — combo_col_map als erstes Arg (Multi-Combo-Mapping)
    signal_args = (
        combo_col_map,
        entry_mask_2d,
        short_entry_mask_2d,
        n_long_exit_blocks_nb,
        long_block_start,
        long_static_block_arr,
        long_spec['op_codes'],
        long_spec['lhs_kind'],
        long_spec['lhs_state_idx'],
        long_spec['lhs_series_col'],
        long_spec['lhs_scalar'],
        long_spec['rhs_kind'],
        long_spec['rhs_state_idx'],
        long_spec['rhs_series_col'],
        long_spec['rhs_scalar'],
        long_spec['series_bundle'],
        np.int64(long_spec['n_series_cols']),
        long_series_col_map,
        n_short_exit_blocks_nb,
        short_block_start,
        short_static_block_arr,
        short_spec['op_codes'],
        short_spec['lhs_kind'],
        short_spec['lhs_state_idx'],
        short_spec['lhs_series_col'],
        short_spec['lhs_scalar'],
        short_spec['rhs_kind'],
        short_spec['rhs_state_idx'],
        short_spec['rhs_series_col'],
        short_spec['rhs_scalar'],
        short_spec['series_bundle'],
        np.int64(short_spec['n_series_cols']),
        short_series_col_map,
        close_arr,
        high_arr,
        low_arr,
        track_entry_idx,
        track_max_price,
        track_min_price,
    )

    # Portfolio via from_signals mit signal_func_nb aufbauen (N1: KEIN entries/exits)
    # GEÄNDERT: Ticket 47 — upon_opposite_entry='Reverse' für Long/Short-Umkehr
    pf_build_kwargs = {k: v for k, v in pf_kwargs.items() if k != 'close'}
    portfolio = vbt.Portfolio.from_signals(
        close_mc,
        signal_func_nb=_state_exit_signal_func_nb,
        signal_args=signal_args,
        upon_opposite_entry='Reverse',
        **pf_build_kwargs,
    )
    return portfolio


def _assert_flat_group(group: dict, name: str) -> None:
    """Validiert die Block-Struktur einer Gruppe (N3).

    Erlaubt ist genau eine Ebene: group['blocks'] -> block['conditions'] ->
    Conditions mit 'lhs'/'rhs'. Tiefer verschachtelte Strukturen (eine Condition,
    die selbst 'conditions'/'blocks' enthält) werden explizit abgewiesen.

    Raises:
        ValueError: Wenn eine Condition eine Untergruppe enthält.
    """
    for block in (group.get('blocks') or []):
        for cond in (block.get('conditions') or []):
            if isinstance(cond, dict) and ('conditions' in cond or 'blocks' in cond):
                raise ValueError(
                    f"Verschachtelte Rule-Gruppen sind nicht unterstützt (Gruppe: '{name}'). "
                    f"Die Engine ist flach — Blöcke mit Condition-Listen. "
                    f"Bitte die Spec in flache Blöcke umstrukturieren."
                )
            # Auch 'logic' auf Condition-Ebene deutet auf Verschachtelung hin
            if isinstance(cond, dict) and 'logic' in cond and 'lhs' not in cond:
                raise ValueError(
                    f"Verschachtelte Rule-Gruppen sind nicht unterstützt (Gruppe: '{name}'). "
                    f"Condition-Objekt mit 'logic' aber ohne 'lhs' gefunden."
                )


def _cond_has_state_ref(cond: dict) -> bool:
    """Gibt True zurück wenn die Condition mind. eine State-Ref enthält."""
    for side in ('lhs', 'rhs'):
        ref = cond.get(side)
        if isinstance(ref, str) and ref in _STATE_REFS:
            return True
    return False


