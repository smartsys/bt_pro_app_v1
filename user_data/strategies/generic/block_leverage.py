"""Hebel je Entry-Block (Feld ``leverage`` in ``spec_json.rules.entry.blocks[]``).

Ein Entry-Block darf einen eigenen Hebel tragen: „unter diesen Bedingungen
Einstieg mit Hebel 1, unter jenen mit Hebel 2". Feuert ein Block mit Hebel 2, ist
die Position doppelt so groß wie bei Hebel 1 — bei unveränderter Basisgröße aus
der BacktestConfig.

Umsetzung: Die Signal-Funktion schreibt am Einstiegsbalken den Hebel des
feuernden Blocks in ein ``leverage``-Array, das zugleich als ``leverage``-Argument
an ``from_signals`` geht; der Lauf rechnet dann im Modus ``lazymult``. Das ist
derselbe Mechanismus wie beim Size-Array der risikobasierten Größe (Ticket 104):
VBT kopiert das übergebene Array beim Broadcast nicht, solange sich seine Form
nicht ändert, und die Signal-Funktion läuft vor allen Lesestellen. Die
Verhaltenszusagen dahinter sind in
``tests/test_block_leverage_vbt_behavior.py`` festgeschrieben.

Feuern mehrere Blöcke im selben Balken, gilt der höchste Hebel — die Rechnung ist
ein Maximum und damit unabhängig von der Reihenfolge der Blöcke. Ein Block mit
Hebel 1 oder ohne Feld verändert das Rechenergebnis nicht: dann liefert diese
Datei gar keine Spezifikation und der Lauf bleibt der alte.

Grenzen, die hier bewusst als Abbruch statt als stille Näherung enden:

- **Stop-Sweep.** Eine ``vbt.Param``-Stop-Achse legt VBT erst nach dem Broadcast
  über die Spalten und vervielfältigt dabei das ``leverage``-Array; die
  Schreibzugriffe der Signal-Funktion gingen ins Leere. Gleiche Begründung wie
  bei ``risk_sizing.build_risk_sizing_spec``.
- **``from_ago != 0``.** ``from_signals`` liest den Hebel dann an einem anderen
  Balken als dem, an dem die Signal-Funktion ihn schreibt.
- **``leverage`` der BacktestConfig ungleich 1.** Block-Hebel und Config-Hebel
  schließen sich aus; zwei Hebel werden nicht miteinander verrechnet.
- **Ein ``leverage`` an einem Exit-Block.** Der Hebel gehört zum Einstieg; ein
  Exit-Block, der ihn trägt, ist ein Missverständnis und kein stiller
  Ignorierfall.

Reicht das Konto für die gewollte Nominale nicht, kürzt VBT die Order still auf
Konto x Hebel (Messung 4 des Tickets). Das bricht den Lauf nicht ab — es wäre
auch in der Wirklichkeit so —, wird aber gemeldet:
``summarize_leverage_truncation`` hält nach dem Lauf die gewollte gegen die
ausgeführte Größe aus den Order-Records.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

# Feldname des Block-Hebels in der Spec.
BLOCK_LEVERAGE_FIELD = 'leverage'

# Hebelmodus, in dem der Block-Hebel wirkt. Nur die multiplizierenden Modi
# vervielfachen die Ordergröße (Messung 1); 'lazy'/'eager' wären eine reine
# Kreditlinie und der Block-Hebel bliebe wirkungslos.
BLOCK_LEVERAGE_MODE = 'lazymult'

# Größenarten, für die sich die gewollte Nominale ohne Kontostand ausrechnen
# lässt — nur dort kann die Kürzungsprüfung eine Aussage treffen.
_ABSOLUTE_SIZE_TYPES = ('value', 'amount')


@dataclass
class BlockLeverageSpec:
    """Alles, was der Lauf für den Block-Hebel braucht.

    Attributes:
        blocks: Die Entry-Blöcke mit Hebel ungleich 1 als Dicts mit 'index'
            (Position in ``rules.entry.blocks``), 'is_short' und 'leverage'.
        n_entry_blocks: Zahl der aktiven Entry-Blöcke insgesamt (für den Ausweis).
        applied_leverage: Wird von ``evaluate_rules_native`` gefüllt: das
            ``leverage``-Array (n_bars, n_total), das die Signal-Funktion
            beschrieben hat.
        entry_bars: Wird von ``evaluate_rules_native`` gefüllt: Maske
            (n_bars, n_total), die markiert, an welchen Balken die
            Signal-Funktion einen Hebel geschrieben hat — also welche Order ein
            Einstieg ist. Ohne sie wäre eine Ausstiegs-Order von einer
            Einstiegs-Order nicht zu unterscheiden.
    """

    blocks: list[dict]
    n_entry_blocks: int
    applied_leverage: Optional[np.ndarray] = field(default=None, repr=False)
    entry_bars: Optional[np.ndarray] = field(default=None, repr=False)


def read_block_leverage(block: dict) -> float:
    """Liest den Hebel eines Blocks; fehlt das Feld, gilt 1.

    Args:
        block: Ein Block aus ``rules.entry.blocks``.

    Returns:
        Der Hebel als Fließkommazahl.

    Raises:
        ValueError: Wenn der Wert keine positive endliche Zahl ist (auch bei
            einem Sweep-Dict — ein Raster über den Block-Hebel ist nicht
            vorgesehen).
    """
    raw = block.get(BLOCK_LEVERAGE_FIELD)
    if raw is None:
        return 1.0
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError(
            f"Der Block-Hebel muss eine Zahl sein, gefunden: {raw!r}. Ein Raster "
            f"über den Hebel (Liste/Range) ist nicht vorgesehen — je Block gilt "
            f"genau ein Wert."
        )
    value = float(raw)
    if not np.isfinite(value) or value <= 0.0:
        raise ValueError(
            f"Der Block-Hebel muss eine positive endliche Zahl sein, gefunden: "
            f"{raw!r}."
        )
    return value


def _assert_no_exit_leverage(rules_json: dict) -> None:
    """Weist ein ``leverage`` an einem Exit-Block ab.

    Raises:
        ValueError: Wenn ein Exit-Block das Feld trägt.
    """
    exit_spec = rules_json.get('exit') or {}
    for pos, block in enumerate(exit_spec.get('blocks') or []):
        if block.get(BLOCK_LEVERAGE_FIELD) is not None:
            # GEÄNDERT: Ticket 106 — Blocknummer 1-basiert wie in der Toolbox
            # und im Ausweis (describe_block_leverage).
            raise ValueError(
                f"Exit-Block {pos + 1} trägt ein '{BLOCK_LEVERAGE_FIELD}'-Feld "
                f"({block[BLOCK_LEVERAGE_FIELD]!r}). Der Hebel gehört zum "
                f"Einstieg und wirkt nur an Entry-Blöcken — an einem Exit-Block "
                f"hätte er keine Bedeutung. Feld dort entfernen."
            )


def build_block_leverage_spec(
    rules_json: dict,
    pf_cfg: dict,
    stops_swept: bool,
) -> Optional[BlockLeverageSpec]:
    """Prüft die Konfiguration und baut die Spezifikation des Block-Hebels.

    Args:
        rules_json: Die Regeln der Iteration ({'entry': ..., 'exit': ...}).
        pf_cfg: Der 'portfolio'-Block der BacktestConfig.
        stops_swept: True, wenn mindestens ein Stop-Feld eine Sweep-Achse trägt.

    Returns:
        Die Spezifikation, oder ``None``, wenn kein aktiver Entry-Block einen
        Hebel ungleich 1 trägt (dann bleibt der Lauf bit-genau unverändert).

    Raises:
        ValueError: Bei einem ``leverage`` an einem Exit-Block, einem
            ungültigen Hebelwert, einem Stop-Sweep, ``from_ago != 0`` oder
            einem Config-Hebel ungleich 1. Jede Meldung nennt die Stelle, an der
            es hängt, und den Ausweg.
    """
    _assert_no_exit_leverage(rules_json)

    entry_spec = rules_json.get('entry') or {}
    raw_blocks = entry_spec.get('blocks') or []

    levered: list[dict] = []
    n_active = 0
    for pos, block in enumerate(raw_blocks):
        leverage = read_block_leverage(block)
        if not block.get('enabled', True):
            # Ein abgeschalteter Block feuert nie — sein Hebel ist gegenstandslos.
            continue
        n_active += 1
        if leverage != 1.0:
            levered.append({
                'index': pos,
                'is_short': bool(block.get('is_short', False)),
                'leverage': leverage,
            })

    if not levered:
        return None

    # GEÄNDERT: Ticket 106 — Stop-Sweep und Block-Hebel schließen sich aus.
    # Gleiche Mechanik wie bei der risikobasierten Größe: VBT legt die
    # vbt.Param-Achse erst nach dem Broadcast über die Spalten und vervielfältigt
    # dabei das leverage-Array — die Schreibzugriffe der Signal-Funktion landen
    # in der Kopie und wirken nicht.
    if stops_swept:
        raise ValueError(
            "Ein Hebel je Entry-Block verträgt sich nicht mit einem Stop-Sweep "
            "(Range/Liste in '_stops'). VBT legt die Sweep-Achse erst nach dem "
            "Broadcast über die Spalten und vervielfältigt dabei das "
            "leverage-Array — der zur Laufzeit geschriebene Hebel würde "
            "verworfen, ohne dass es auffiele. Entweder die Stops als feste "
            "Werte bzw. Indikator-Referenz setzen oder den Block-Hebel auf 1 "
            "lassen."
        )

    from_ago = pf_cfg.get('from_ago')
    if from_ago is not None and int(from_ago) != 0:
        raise ValueError(
            f"Ein Hebel je Entry-Block verträgt sich nicht mit "
            f"from_ago={from_ago!r}. from_signals liest den Hebel an "
            f"leverage_arr[i - from_ago], die Signal-Funktion schreibt ihn an "
            f"leverage_arr[i] — die Order bekäme still den falschen Hebel. "
            f"Anzupassende Stelle, falls from_ago einmal gebraucht wird: "
            f"rules_engine._state_exit_signal_func_nb (Schreibstelle des "
            f"leverage-Arrays) zusammen mit block_leverage.build_block_leverage_spec "
            f"(dieser Riegel)."
        )

    config_leverage = pf_cfg.get('leverage')
    if config_leverage is not None and float(config_leverage) != 1.0:
        raise ValueError(
            f"Ein Hebel je Entry-Block und der Hebel der BacktestConfig "
            f"(leverage={config_leverage!r}) schließen sich aus — zwei Hebel "
            f"werden nicht miteinander verrechnet. Entweder 'leverage' im "
            f"portfolio-Block der BacktestConfig auf 1 setzen und den Hebel "
            f"ausschließlich über die Entry-Blöcke steuern, oder den Block-Hebel "
            f"auf 1 lassen."
        )

    return BlockLeverageSpec(blocks=levered, n_entry_blocks=n_active)


def describe_block_leverage(spec: BlockLeverageSpec, config_mode: Any) -> str:
    """Formuliert den Ausweis für Preflight und Lauf-Protokoll.

    Ticket 106, Anforderung 6: vor dem Lauf und im Protokoll muss erkennbar
    sein, welche Blöcke welchen Hebel tragen und dass der Hebelmodus der
    BacktestConfig für diesen Lauf ersetzt wurde.

    Args:
        spec: Die Spezifikation aus ``build_block_leverage_spec``.
        config_mode: Der 'leverage_mode' der BacktestConfig (nur für den Text).

    Returns:
        Ein deutscher Satz.
    """
    # GEÄNDERT: Ticket 106 — Blocknummern 1-basiert, wie die Toolbox sie seit
    # jeher zählt ('Block 1' ist der erste). Das Feld 'index' bleibt die
    # 0-basierte Position in rules.entry.blocks; nur die Beschriftung zählt ab 1,
    # damit Preflight-Ausweis und Toolbox-Ausgabe nebeneinander dieselbe Nummer
    # für denselben Block nennen.
    teile = [
        f"Block {b['index'] + 1} ({'short' if b['is_short'] else 'long'}): "
        f"Hebel {b['leverage']:g}"
        for b in spec.blocks
    ]
    n_neutral = spec.n_entry_blocks - len(spec.blocks)
    text = (
        f"Hebel je Entry-Block aktiv — {', '.join(teile)}; "
        f"{n_neutral} weitere aktive Entry-Blöcke rechnen mit Hebel 1. "
        f"Feuern mehrere Blöcke im selben Balken, gilt der höchste Hebel."
    )
    if config_mode is not None and str(config_mode) != BLOCK_LEVERAGE_MODE:
        text += (
            f" Der Hebelmodus der BacktestConfig ({config_mode!r}) ist für "
            f"diesen Lauf durch '{BLOCK_LEVERAGE_MODE}' ersetzt — nur die "
            f"multiplizierenden Modi vervielfachen die Ordergröße."
        )
    else:
        text += f" Der Lauf rechnet im Hebelmodus '{BLOCK_LEVERAGE_MODE}'."
    return text


def _desired_nominal(
    size_type: Any,
    size_value: Any,
    leverage: np.ndarray,
    price: np.ndarray,
    desired_size: Optional[np.ndarray],
) -> Optional[np.ndarray]:
    """Rechnet die gewollte Nominale je Einstiegs-Order.

    Args:
        size_type: Die Größenart der BacktestConfig.
        size_value: Der 'size'-Wert der BacktestConfig.
        leverage: Der geschriebene Hebel je Order.
        price: Der Ausführungspreis je Order.
        desired_size: Das size-Array der risikobasierten Größe (Stückzahlen)
            an den Order-Stellen, oder ``None``.

    Returns:
        Die gewollte Nominale je Order, oder ``None``, wenn sich für diese
        Größenart ohne Kontostand keine gewollte Nominale bestimmen lässt.
    """
    if desired_size is not None:
        return np.abs(desired_size) * leverage * np.abs(price)

    normalized = str(size_type).strip().lower() if size_type is not None else ''
    if normalized not in _ABSOLUTE_SIZE_TYPES:
        return None
    if isinstance(size_value, bool) or not isinstance(size_value, (int, float)):
        return None
    size_float = float(size_value)
    if not np.isfinite(size_float) or size_float <= 0.0:
        return None

    if normalized == 'value':
        return np.full(leverage.shape, size_float) * leverage
    return size_float * leverage * np.abs(price)


def summarize_leverage_truncation(
    portfolio: Any,
    spec: BlockLeverageSpec,
    size_type: Any,
    size_value: Any,
    desired_size: Optional[np.ndarray] = None,
) -> dict:
    """Vergleicht die gewollte mit der ausgeführten Ordergröße.

    Ticket 106, Anforderung 3: Reicht das Konto für die gehebelte Nominale
    nicht, kürzt VBT die Order still auf Konto x Hebel (Messung 4). Die
    Kennzahlen sehen dann plausibel aus, messen aber eine kleinere Position, als
    der Block-Hebel verlangt. Der Abgleich läuft über die Order-Records: an
    jedem Balken, an dem die Signal-Funktion einen Hebel geschrieben hat, wird
    die ausgeführte gegen die gewollte Nominale gehalten.

    Bei einer Prozent-Größe (``percent``/``percent100``) gibt es keine gewollte
    Nominale ohne den laufenden Kontostand — eine Prozent-Order ist per
    Konstruktion bezahlbar. Der Bericht sagt dann ausdrücklich, dass nicht
    geprüft wurde, statt „keine Kürzung" zu behaupten.

    Args:
        portfolio: Das fertige ``vbt.Portfolio``.
        spec: Die Spezifikation mit dem geschriebenen Hebel-Array und der
            Einstiegs-Maske.
        size_type: Die Größenart der BacktestConfig.
        size_value: Der 'size'-Wert der BacktestConfig.
        desired_size: Optional das size-Array der risikobasierten Größe
            (Ticket 104) — dann ist die gewollte Stückzahl von dort bekannt.

    Returns:
        Dict mit 'blocks', 'leverage_mode', 'checked', 'check_note',
        'n_entries', 'n_truncated', 'max_shortfall_pct' und 'note'
        (Klartext-Meldung oder ``None``, wenn nichts zu melden ist).
    """
    report = {
        'blocks': list(spec.blocks),
        'leverage_mode': BLOCK_LEVERAGE_MODE,
        'checked': False,
        'check_note': None,
        'n_entries': 0,
        'n_truncated': 0,
        'max_shortfall_pct': 0.0,
        'note': None,
    }
    leverage_arr = spec.applied_leverage
    entry_bars = spec.entry_bars
    if leverage_arr is None or entry_bars is None:
        report['check_note'] = (
            'Kein Hebel-Array vom Lauf zurückgekommen — nicht geprüft.'
        )
        return report

    n_bars, n_cols = leverage_arr.shape
    records = portfolio.orders.values
    if not len(records):
        report['checked'] = True
        return report

    order_col = records['col'].astype(np.int64)
    order_idx = records['idx'].astype(np.int64)
    in_range = (order_col < n_cols) & (order_idx < n_bars)
    order_col = order_col[in_range]
    order_idx = order_idx[in_range]
    order_size = np.abs(records['size'].astype(np.float64)[in_range])
    order_price = np.abs(records['price'].astype(np.float64)[in_range])

    is_entry = entry_bars[order_idx, order_col]
    order_col = order_col[is_entry]
    order_idx = order_idx[is_entry]
    order_size = order_size[is_entry]
    order_price = order_price[is_entry]
    report['n_entries'] = int(order_size.size)

    leverage = leverage_arr[order_idx, order_col]
    wanted_size = (
        desired_size[order_idx, order_col] if desired_size is not None else None
    )
    wanted = _desired_nominal(
        size_type, size_value, leverage, order_price, wanted_size
    )
    if wanted is None:
        report['check_note'] = (
            f"Größenart {size_type!r}: eine Prozent-Größe rechnet gegen den "
            f"laufenden Kontostand und ist per Konstruktion bezahlbar — eine "
            f"Kürzung wegen Unterdeckung ist dort nicht bestimmbar und wurde "
            f"nicht geprüft."
        )
        return report

    report['checked'] = True
    executed = order_size * order_price
    comparable = np.isfinite(wanted) & (wanted > 0.0)
    short = comparable & (executed < wanted * (1.0 - 1e-9))
    n_truncated = int(np.count_nonzero(short))
    report['n_truncated'] = n_truncated
    if n_truncated:
        shortfalls = (wanted[short] - executed[short]) / wanted[short] * 100.0
        report['max_shortfall_pct'] = float(np.max(shortfalls))
        report['note'] = _truncation_note(
            n_truncated, report['n_entries'], report['max_shortfall_pct']
        )
    return report


def _truncation_note(n_truncated: int, n_entries: int, max_shortfall_pct: float) -> str:
    """Formuliert die Kürzungs-Meldung.

    Args:
        n_truncated: Zahl der gekürzten Einstiegs-Orders.
        n_entries: Zahl der geprüften Einstiegs-Orders.
        max_shortfall_pct: Größte Kürzung in Prozent.

    Returns:
        Ein deutscher Satz.
    """
    return (
        f"{n_truncated} von {n_entries} Einstiegs-Orders wurden von VBT auf "
        f"Konto x Hebel gekürzt (größte Kürzung {max_shortfall_pct:.1f} %). "
        f"Der Block-Hebel wirkt dort nicht voll — die Kennzahlen messen eine "
        f"kleinere, vom Kontostand begrenzte Position. Abhilfe: die Ordergröße "
        f"im portfolio-Block senken oder das Startkapital erhöhen."
    )


def merge_reports(reports: list[dict]) -> dict:
    """Fasst die Berichte mehrerer Chunks zu einem Lauf-Bericht zusammen.

    Args:
        reports: Die Einzelberichte aus ``summarize_leverage_truncation``.

    Returns:
        Ein Bericht im selben Format; 'note' wird aus den Summen neu formuliert,
        damit sie den ganzen Lauf beschreibt statt den letzten Chunk.

    Raises:
        ValueError: Wenn die Liste leer ist — dann gibt es nichts zu berichten
            und der Aufrufer darf gar nicht erst zusammenfassen.
    """
    if not reports:
        raise ValueError(
            'merge_reports braucht mindestens einen Bericht — eine leere Liste '
            'bedeutet, dass kein Chunk mit Block-Hebel gerechnet hat.'
        )
    first = reports[0]
    merged = {
        'blocks': list(first.get('blocks') or []),
        'leverage_mode': first.get('leverage_mode', BLOCK_LEVERAGE_MODE),
        'checked': all(bool(r.get('checked')) for r in reports),
        'check_note': next(
            (r.get('check_note') for r in reports if r.get('check_note')), None
        ),
        'n_entries': sum(int(r.get('n_entries') or 0) for r in reports),
        'n_truncated': sum(int(r.get('n_truncated') or 0) for r in reports),
        'max_shortfall_pct': max(
            [float(r.get('max_shortfall_pct') or 0.0) for r in reports], default=0.0
        ),
        'note': None,
    }
    if merged['n_truncated']:
        merged['note'] = _truncation_note(
            merged['n_truncated'], merged['n_entries'], merged['max_shortfall_pct']
        )
    return merged
