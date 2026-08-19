"""Fold-Plan der Walk-Forward-Kette (Ticket 82).

Der Plan ist die Vorregistrierung: Fold-Zahl, Fensterlängen, die konkreten
Fold-Fenster als Datumsliste und das Auswahlkriterium stehen beim Anlegen der
Kette fest und werden danach stur vollzogen. Dieses Modul rechnet ihn — reine
Datums- und Prüflogik ohne FastAPI-, Queue- oder DB-Abhängigkeiten, damit sie
eigenständig testbar bleibt.

Fensterfolge (rollierend): Fold 1 rechnet auf dem Anker-Fenster, das
Testfenster (OOS) schließt unmittelbar daran an. Das nächste Optimierfenster
(IS) endet am Ende des vorigen Testfensters und behält seine Länge — es rollt
also um die OOS-Länge nach vorn. Jedes Fenster behält den Indikator-Vorlauf des
Ankers (Abstand ``ohlc_start`` → ``start``).
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from dateutil.relativedelta import relativedelta

from services.api.utils.walk_forward import DATE_FORMAT, warmup_span

# Zulässige Richtungen des Auswahlkriteriums.
SELECTION_DIRECTIONS: Tuple[str, ...] = ('max', 'min')

# Fester Methodenhinweis, der an jeder abgeschlossenen Kette hängt. Er benennt die
# bewusst in Kauf genommene Abweichung der Verkettung gegenüber einem
# Signal-Splice-Portfolio (Ticket 82, Out of Scope).
METHOD_NOTE: str = (
    'Die Gesamtbewertung entsteht aus den balkengenauen Kapitalkurven der '
    'Testfenster-Läufe, chronologisch aneinandergehängt und je Fold auf das '
    'Startkapital normiert. Es wird KEIN durchgehendes Portfolio über alle Folds '
    'gerechnet (Signal-Splice): Positionen enden an den Fold-Grenzen und es gibt '
    'kein fold-übergreifendes Compounding im Portfolio. Die Kette misst, sie '
    'urteilt nicht — es gibt kein Verdict.'
)


def _window(start: datetime, end: datetime, vorlauf: timedelta) -> Dict[str, str]:
    """Baut einen Fensterblock mit erhaltenem Indikator-Vorlauf.

    Args:
        start: Handelsbeginn des Fensters.
        end: Handelsende des Fensters.
        vorlauf: Abstand zwischen ohlc_start und start aus der Anker-Config.

    Returns:
        Dict mit start, end, ohlc_start und ohlc_end im Format YYYY-MM-DD.
    """
    return {
        'start': start.strftime(DATE_FORMAT),
        'end': end.strftime(DATE_FORMAT),
        'ohlc_start': (start - vorlauf).strftime(DATE_FORMAT),
        'ohlc_end': end.strftime(DATE_FORMAT),
    }


def build_fold_plan(
    anchor_config: Dict[str, Any],
    n_folds: int,
    oos_months: int,
    is_months: Optional[int] = None,
    selection_metric: str = 'total_return_pct',
    selection_direction: str = 'max',
    trade_floor: int = 0,
    metrics_level: Any = None,
) -> Dict[str, Any]:
    """Rechnet den vollständigen Fold-Plan aus der Anker-Config.

    Args:
        anchor_config: ``backtest_config_json`` des Anker-Laufs (start, end,
            optional ohlc_start).
        n_folds: Anzahl der Folds (>= 1).
        oos_months: Länge des Testfensters in Monaten (>= 1).
        is_months: Länge des Optimierfensters in Monaten. None = Länge des
            Anker-Fensters; dann ist das IS-Fenster von Fold 1 exakt das
            Anker-Fenster und der Anker-Lauf kann als IS-Lauf dienen.
        selection_metric: Kennzahl-Feld, nach dem der Sieger je Fold gewählt wird.
        selection_direction: 'max' oder 'min'.
        trade_floor: Mindestzahl Trades, die ein Kandidat haben muss.
        metrics_level: Metrik-Stufe der IS-Läufe (Stufenname, Gruppenliste oder
            None für den Default 'auto').

    Returns:
        Plan-Dict mit Eckdaten, Kriterium und der Fold-Fensterliste.

    Raises:
        ValueError: Bei ungültigen Eckdaten oder unbrauchbarem Anker-Fenster.
    """
    if n_folds < 1:
        raise ValueError(f'Fold-Zahl muss >= 1 sein, ist {n_folds}.')
    if oos_months < 1:
        raise ValueError(f'OOS-Länge muss >= 1 Monat sein, ist {oos_months}.')
    if is_months is not None and is_months < 1:
        raise ValueError(f'IS-Länge muss >= 1 Monat sein, ist {is_months}.')
    if selection_direction not in SELECTION_DIRECTIONS:
        raise ValueError(
            f"Unbekannte Richtung '{selection_direction}'. "
            f"Zulässig: {', '.join(SELECTION_DIRECTIONS)}."
        )
    if trade_floor < 0:
        raise ValueError(f'Trade-Floor muss >= 0 sein, ist {trade_floor}.')

    anchor_start = datetime.strptime(anchor_config['start'], DATE_FORMAT)
    anchor_end = datetime.strptime(anchor_config['end'], DATE_FORMAT)
    if anchor_end <= anchor_start:
        raise ValueError(
            f"Anker-Fenster ist leer oder rückwärts: {anchor_config['start']} bis "
            f"{anchor_config['end']}."
        )
    vorlauf = warmup_span(anchor_config)

    # IS-Fenster von Fold 1: ohne ausdrückliche IS-Länge exakt das Anker-Fenster
    # (dann ist der Anker-Lauf selbst der IS-Lauf und rechnet nicht doppelt).
    if is_months is None:
        is_start = anchor_start
        is_end = anchor_end
    else:
        is_end = anchor_end
        is_start = is_end - relativedelta(months=is_months)

    folds: List[Dict[str, Any]] = []
    for fold_index in range(1, n_folds + 1):
        oos_start = is_end
        oos_end = oos_start + relativedelta(months=oos_months)
        folds.append({
            'fold_index': fold_index,
            'is_window': _window(is_start, is_end, vorlauf),
            'oos_window': _window(oos_start, oos_end, vorlauf),
        })
        # Nächstes Optimierfenster endet am Ende des eben geplanten Testfensters
        # und behält seine Länge (rollierend, nicht wachsend).
        next_is_end = oos_end
        if is_months is None:
            next_is_start = next_is_end - (is_end - is_start)
        else:
            next_is_start = next_is_end - relativedelta(months=is_months)
        is_start, is_end = next_is_start, next_is_end

    return {
        'n_folds': n_folds,
        'is_months': is_months,
        'oos_months': oos_months,
        'anchor_window': {
            'start': anchor_config['start'],
            'end': anchor_config['end'],
            'ohlc_start': anchor_config.get('ohlc_start'),
            'ohlc_end': anchor_config.get('ohlc_end'),
        },
        'warmup_days': vorlauf.days,
        'selection_metric': selection_metric,
        'selection_direction': selection_direction,
        'trade_floor': trade_floor,
        'metrics_level': metrics_level,
        'folds': folds,
        'required_span': {
            'ohlc_start': folds[0]['is_window']['ohlc_start'],
            'end': folds[-1]['oos_window']['end'],
        },
    }


def plan_fold(plan: Dict[str, Any], fold_index: int) -> Dict[str, Any]:
    """Gibt den geplanten Fold-Block zu einem Index zurück.

    Args:
        plan: Das ``plan_json`` einer Kette.
        fold_index: 1-basierter Fold-Index.

    Returns:
        Der geplante Fold-Block mit IS- und OOS-Fenster.

    Raises:
        ValueError: Wenn der Index nicht im Plan steht.
    """
    for fold in plan.get('folds') or []:
        if fold.get('fold_index') == fold_index:
            return fold
    raise ValueError(
        f'Fold {fold_index} steht nicht im Plan (geplant sind '
        f"{plan.get('n_folds')} Folds)."
    )


def validate_plan_coverage(
    plan: Dict[str, Any],
    coverage: Dict[str, Optional[Tuple[str, str]]],
) -> None:
    """Prüft, dass alle Fold-Fenster in der vorhandenen OHLC-Abdeckung liegen.

    Läuft **vor** dem Anlegen der Kette: fehlen Daten am Rand, entsteht kein
    Datensatz und kein Teillauf — die Kette bricht mit klarer Meldung ab, statt
    mitten in Fold 4 auf ein leeres Fenster zu laufen.

    Args:
        plan: Das Plan-Dict aus :func:`build_fold_plan`.
        coverage: Je Symbol die vorhandene Datenspanne als (erster, letzter)
            Zeitstempel im ISO-Format, oder None wenn für das Symbol keine Daten
            vorliegen.

    Raises:
        ValueError: Wenn für ein Symbol Daten fehlen oder ein Fold-Fenster über
            die vorhandene Spanne hinausragt.
    """
    required_start = datetime.strptime(plan['required_span']['ohlc_start'], DATE_FORMAT)
    required_end = datetime.strptime(plan['required_span']['end'], DATE_FORMAT)

    for symbol, span in sorted(coverage.items()):
        if not span or not span[0] or not span[1]:
            raise ValueError(
                f'Für {symbol} liegen keine OHLC-Daten vor — der Plan verlangt '
                f'{plan["required_span"]["ohlc_start"]} bis '
                f'{plan["required_span"]["end"]}.'
            )
        available_start = datetime.fromisoformat(span[0]).replace(tzinfo=None)
        available_end = datetime.fromisoformat(span[1]).replace(tzinfo=None)
        if available_start > required_start:
            raise ValueError(
                f'Plan verlangt für {symbol} Daten ab '
                f'{plan["required_span"]["ohlc_start"]} (inkl. Vorlauf), vorhanden '
                f'erst ab {available_start.strftime(DATE_FORMAT)}. Fold-Zahl oder '
                f'Fensterlängen verkleinern.'
            )
        if available_end < required_end:
            raise ValueError(
                f'Plan verlangt für {symbol} Daten bis '
                f'{plan["required_span"]["end"]}, vorhanden nur bis '
                f'{available_end.strftime(DATE_FORMAT)}. Fold-Zahl oder '
                f'Fensterlängen verkleinern.'
            )
