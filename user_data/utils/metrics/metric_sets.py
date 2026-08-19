"""Metrik-Gruppen — die einzige Stelle, an der die Kennzahl-Zuordnung steht.

Die 46 Kennzahl-Felder eines Results (`_extract_metrics` in
`user_data/utils/database/repository.py`) sind hier in benannte Gruppen geteilt.
Runner, Persistenz und Anzeige beziehen die Zuordnung ausschließlich von hier —
eine zweite Liste an anderer Stelle wäre sofort Drift.

**Granularität ist die Gruppe, nicht das Einzelfeld.** Felder einer Gruppe teilen
dieselben teuren Zwischenobjekte; eine Feld-Granularität spart keine Rechenzeit und
vervielfacht nur die Kombinatorik der Auswahl.

**Pflichtgruppen sind in keiner Aufruf-Form abwählbar:**

* `scope` ist die Selbstauskunft des Laufs,
* `returns` und `trades` sind das Basisergebnis samt Vergleichsanker und Trade-Floor,
* `risk_ratios` liefert `sharpe_ratio`, `moments` liefert `skew`/`kurtosis` — zusammen
  mit `bar_count` aus `scope` sind das genau die Eingänge des Nachlaufs für die
  Deflated Sharpe Ratio (`repository._calculate_deflated_sharpe`). Wären
  sie abwählbar, fiele die Deflated Sharpe Ratio aus.

Die 47. Spalte `deflated_sharpe_ratio` steht bewusst in keiner Gruppe: Sie entsteht
nicht in `_extract_metrics`, sondern als rasterweiter Nachlauf, und läuft bei jeder
Auswahl mit.
"""

from typing import Iterable, Optional, Union

# ---------------------------------------------------------------------------
# Stufen-Namen (festgelegt, keine Arbeitstitel)
# ---------------------------------------------------------------------------
STAGE_CORE = 'kern'
STAGE_FULL = 'voll'
STAGE_AUTO = 'auto'

STAGES: tuple[str, ...] = (STAGE_CORE, STAGE_FULL, STAGE_AUTO)

# ---------------------------------------------------------------------------
# Gruppen-Zuordnung
# ---------------------------------------------------------------------------
# Reihenfolge der Gruppen und Felder entspricht der Ticket-Tabelle; die Feldnamen
# sind die Spaltennamen von BacktestResult.
METRIC_GROUPS: dict[str, tuple[str, ...]] = {
    'scope': (
        'start_index',
        'end_index',
        'total_duration',
        'bar_count',
    ),
    'returns': (
        'start_value',
        'min_value',
        'max_value',
        'end_value',
        'total_return_pct',
        'benchmark_return_pct',
        'position_coverage_pct',
        'max_gross_exposure_pct',
    ),
    'trades': (
        'total_orders',
        'total_fees_paid',
        'total_trades',
        'open_trades',
        'long_trades',
        'short_trades',
    ),
    'risk_ratios': (
        'sharpe_ratio',
        'sortino_ratio',
        'calmar_ratio',
        'omega_ratio',
        'annualized_return',
        'annualized_volatility',
        'downside_risk',
    ),
    'moments': (
        'skew',
        'kurtosis',
    ),
    'drawdown': (
        'max_drawdown_pct',
        'max_drawdown_duration',
    ),
    'trade_quality': (
        'win_rate_pct',
        'profit_factor',
        'expectancy',
        'best_trade_pct',
        'worst_trade_pct',
        'avg_winning_trade_pct',
        'avg_losing_trade_pct',
        'avg_winning_trade_duration',
        'avg_losing_trade_duration',
    ),
    'sqn_edge': (
        'sqn',
        'edge_ratio',
    ),
    'tail_risk': (
        'tail_ratio',
        'value_at_risk',
        'cond_value_at_risk',
    ),
    'benchmark': (
        'alpha',
        'beta',
        'information_ratio',
    ),
}

REQUIRED_GROUPS: frozenset[str] = frozenset({
    'scope', 'returns', 'trades', 'risk_ratios', 'moments',
})

ALL_GROUPS: frozenset[str] = frozenset(METRIC_GROUPS)

OPTIONAL_GROUPS: frozenset[str] = ALL_GROUPS - REQUIRED_GROUPS

# Die Stufe `kern` ist „alles außer den drei teuren Extremrisiko-Kennzahlen".
CORE_GROUPS: frozenset[str] = ALL_GROUPS - {'tail_risk'}

# Alle 46 Kennzahl-Felder in Gruppen-Reihenfolge. Die Persistenz schreibt genau diese
# Spalten — nicht gerechnete Felder ausdrücklich als NULL (siehe save_strategy_results).
ALL_METRIC_FIELDS: tuple[str, ...] = tuple(
    field for fields in METRIC_GROUPS.values() for field in fields
)

# ---------------------------------------------------------------------------
# Schwelle für die Stufe `auto`
# ---------------------------------------------------------------------------
# Unterhalb dieser Rastergröße rechnet `auto` voll, ab ihr nur noch `kern` — die drei
# `tail_risk`-Kennzahlen entfallen dann, weil sie mit der Kombinationszahl skalieren.
#
# Hergeleitet aus einer Laufzeit-Messreihe (derselbe Lauf je einmal 'voll' und 'kern';
# die Differenz ist der Preis der drei Kennzahlen). Messreihe und Herleitung:
# `documentation/knowledge/metriken-architektur.md`, Abschnitt 7.
#
# Zwei Befunde tragen die Zahl:
#
# 1. Die Kosten sind **linear** und der Anteil bleibt konstant — es gibt keinen Knick,
#    an dem sich eine Schwelle ablesen ließe. Sie ist deshalb eine ausgesprochene
#    Budget-Entscheidung, keine Bruchstelle der Messkurve.
# 2. Unter Last steigt der Aufpreis deutlich stärker als der Rest des Laufs: Die
#    Parallelisierung der drei Kennzahlen lebt davon, alle Kerne zu bekommen, und
#    gleichzeitige Läufe nehmen sie ihr weg. Maßgeblich ist deshalb der Wert unter
#    Last. Der konkrete Aufpreis hängt an der Kernzahl der Maschine — die Schwelle
#    unten ist auf einer vielkernigen Entwicklungsmaschine gesetzt und passt auf
#    kleinerer Hardware womöglich nicht.
#
# Budget: Was 'auto' ungefragt zusätzlich ausgibt, soll im Normalzustand der Maschine
# (vier Worker) unter etwa drei Minuten bleiben. Das sind 5.000 Kombinationen; jede
# weitere 5.000er-Stufe kostet noch einmal rund drei Minuten. Der Wert fällt zugleich
# mit der bestehenden Blockgrenze `chunk_size` zusammen: darunter ist ein Lauf ein
# einzelner Block und in aller Regel eine gezielte Messung, ab da ein großer Sweep —
# genau das Regime, für das die automatische Kürzung gedacht ist.
#
# 'voll' bleibt jederzeit ausdrücklich wählbar: Report, kein Gate.
AUTO_FULL_COMBINATION_THRESHOLD: int = 5_000


def normalize_groups(groups: Iterable[str]) -> frozenset[str]:
    """Prüft eine Gruppen-Menge und ergänzt die Pflichtgruppen.

    Args:
        groups: Gruppen-Keys. Pflichtgruppen dürfen enthalten sein, müssen aber
            nicht — sie werden immer ergänzt.

    Returns:
        Menge der zu rechnenden Gruppen (Pflichtgruppen inklusive).

    Raises:
        ValueError: Bei einem unbekannten Gruppen-Key oder wenn statt einer Menge
            eine Zeichenkette übergeben wurde. Unbekannte Keys werden nie still
            übergangen.
    """
    if isinstance(groups, str):
        raise ValueError(
            f"Gruppen-Menge erwartet, aber eine Zeichenkette bekommen: {groups!r}. "
            f"Für die Stufen {', '.join(STAGES)} ist resolve_metric_groups zuständig."
        )
    keys = list(groups)
    unknown = sorted({key for key in keys if key not in METRIC_GROUPS})
    if unknown:
        raise ValueError(
            f"Unbekannte Metrik-Gruppe(n): {', '.join(unknown)}. "
            f"Bekannt sind: {', '.join(sorted(METRIC_GROUPS))}."
        )
    return frozenset(keys) | REQUIRED_GROUPS


def resolve_metric_groups(
    selection: Union[str, Iterable[str], None] = None,
    n_combinations: Optional[int] = None,
) -> frozenset[str]:
    """Löst eine Auswahl-Angabe zur Menge der zu rechnenden Gruppen auf.

    Args:
        selection: `"kern"`, `"voll"`, `"auto"`, eine Liste von Gruppen-Keys
            (Pflichtgruppen kommen immer hinzu, leere Liste = nur Pflichtgruppen)
            oder None. None wird wie `"auto"` behandelt.
        n_combinations: Rastergröße des Laufs. Nur für `"auto"` nötig.

    Returns:
        Menge der zu rechnenden Gruppen (Pflichtgruppen inklusive).

    Raises:
        ValueError: Bei unbekannter Stufe, unbekanntem Gruppen-Key oder wenn `"auto"`
            ohne Rastergröße aufgelöst werden soll — geraten wird nicht.
    """
    if selection is None:
        selection = STAGE_AUTO
    if isinstance(selection, str):
        if selection == STAGE_FULL:
            return ALL_GROUPS
        if selection == STAGE_CORE:
            return CORE_GROUPS
        if selection == STAGE_AUTO:
            if n_combinations is None:
                raise ValueError(
                    "Die Stufe 'auto' braucht die Rastergröße (n_combinations), um "
                    "gegen die Schwelle entschieden zu werden."
                )
            if int(n_combinations) < AUTO_FULL_COMBINATION_THRESHOLD:
                return ALL_GROUPS
            return CORE_GROUPS
        raise ValueError(
            f"Unbekannte Metrik-Auswahl: {selection!r}. Zulässig sind "
            f"{', '.join(STAGES)} oder eine Liste aus: "
            f"{', '.join(sorted(METRIC_GROUPS))}."
        )
    return normalize_groups(selection)


def fields_for_groups(groups: Iterable[str]) -> tuple[str, ...]:
    """Liefert die Kennzahl-Felder der übergebenen Gruppen in Gruppen-Reihenfolge.

    Args:
        groups: Gruppen-Keys (werden über normalize_groups geprüft und um die
            Pflichtgruppen ergänzt).

    Returns:
        Feldnamen der aktiven Gruppen.

    Raises:
        ValueError: Bei einem unbekannten Gruppen-Key.
    """
    active = normalize_groups(groups)
    return tuple(
        field
        for group, fields in METRIC_GROUPS.items()
        if group in active
        for field in fields
    )


def validate_metrics_selection(
    selection: Union[str, Iterable[str], None],
) -> Union[str, list[str], None]:
    """Prüft eine `metrics`-Angabe aus einem Request-Body syntaktisch.

    Läuft am Rand des Systems (API-Route), bevor irgendein Run angelegt wird. Anders
    als `resolve_metric_groups` braucht diese Prüfung keine Rastergröße: `"auto"`
    ist immer syntaktisch gültig, seine Auflösung passiert erst beim Run-Start, wenn
    `n_combinations` feststeht (`create_backtest_run`).

    Args:
        selection: Rohwert aus dem Request-Body — Stufenname (`"kern"`/`"voll"`/
            `"auto"`), eine Liste von Gruppen-Keys, oder None (= `"auto"`).

    Returns:
        Der geprüfte Wert unverändert (Listen als `list`), zur Ablage in
        `backtest_config_json['metrics']`.

    Raises:
        ValueError: Bei unbekannter Stufe oder unbekanntem Gruppen-Key. Der Aufrufer
            meldet das als sauberen HTTP-Fehler — es wird kein Run angelegt.
    """
    if selection is None:
        return None
    if isinstance(selection, str):
        if selection == STAGE_AUTO:
            return selection
        # kern/voll brauchen keine Rastergröße — resolve_metric_groups prüft die
        # Stufe vollständig und wirft bei einer unbekannten Zeichenkette.
        resolve_metric_groups(selection)
        return selection
    groups = list(selection)
    normalize_groups(groups)
    return groups


def skipped_fields(groups: Iterable[str]) -> tuple[str, ...]:
    """Liefert die Kennzahl-Felder, die bei dieser Auswahl NICHT gerechnet werden.

    Args:
        groups: Gruppen-Keys der aktiven Auswahl.

    Returns:
        Feldnamen der abgewählten Gruppen in Gruppen-Reihenfolge. Genau diese Felder
        schreibt die Persistenz ausdrücklich als NULL.

    Raises:
        ValueError: Bei einem unbekannten Gruppen-Key.
    """
    active = normalize_groups(groups)
    return tuple(
        field
        for group, fields in METRIC_GROUPS.items()
        if group not in active
        for field in fields
    )
