"""Siegerwahl je Fold der Walk-Forward-Kette.

Die Auswahl trifft der Agent beim Start der Kette (Metrik, Richtung,
Trade-Floor) — dieses Modul vollzieht sie nur. Es bringt **kein eigenes**
Gütekriterium mit, kennt keinen Default-Schwellwert und wirft nichts weg, was
das Kriterium nicht ausdrücklich ausschließt.

Findet sich kein Kandidat über dem Trade-Floor, ist das ein Ergebnis und kein
Fehler: der Fold wird als „ohne Sieger" ausgewiesen, das Testfenster entfällt für
diesen Fold.
"""

from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import Float, Integer

from user_data.utils.database.models import BacktestResult
from user_data.utils.metrics.metric_sets import ALL_METRIC_FIELDS

# Zusätzlich wählbar, obwohl nicht Teil der im Lauf gerechneten Kennzahl-Gruppen:
# die Deflated Sharpe Ratio entsteht im Nachlauf am selben Result.
_EXTRA_SELECTABLE_FIELDS: Tuple[str, ...] = ('deflated_sharpe_ratio',)


def _numeric_result_fields() -> Tuple[str, ...]:
    """Sammelt alle numerischen Kennzahl-Spalten von ``backtest_results``.

    Returns:
        Feldnamen, nach denen sortiert werden kann (Float- und Integer-Spalten).
        Text- und Zeitfelder wie ``total_duration`` fallen heraus.
    """
    columns = BacktestResult.__table__.columns
    fields = []
    for name in ALL_METRIC_FIELDS + _EXTRA_SELECTABLE_FIELDS:
        column = columns.get(name)
        if column is None:
            continue
        if isinstance(column.type, (Float, Integer)):
            fields.append(name)
    return tuple(sorted(set(fields)))


# Zulässige Auswahlkriterien — direkt aus den Result-Spalten abgeleitet.
SELECTABLE_METRIC_FIELDS: Tuple[str, ...] = _numeric_result_fields()


def validate_selection_metric(metric: str) -> str:
    """Prüft das Auswahlkriterium gegen die Result-Spalten.

    Args:
        metric: Gewünschtes Kennzahl-Feld.

    Returns:
        Das geprüfte Feld unverändert.

    Raises:
        ValueError: Wenn das Feld keine numerische Result-Spalte ist.
    """
    if metric not in SELECTABLE_METRIC_FIELDS:
        raise ValueError(
            f"Unbekanntes Auswahlkriterium '{metric}'. Zulässig sind die "
            f"numerischen Result-Spalten: {', '.join(SELECTABLE_METRIC_FIELDS)}."
        )
    return metric


def json_safe_value(value: Any) -> Any:
    """Macht einen Kennzahl-Wert JSON-tauglich.

    Args:
        value: Wert aus einer Result-Spalte.

    Returns:
        Zeitstempel als ISO-Zeichenkette, sonst der unveränderte Wert.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def result_metrics(result: BacktestResult) -> Dict[str, Any]:
    """Kopiert alle Kennzahlen eines Results in ein JSON-taugliches Dict.

    Voll kopiert statt referenziert: die Kette muss lesbar bleiben, wenn das
    Result längst aufgeräumt ist.

    Args:
        result: Das Result.

    Returns:
        Kennzahl-Feld → Wert, dazu ``result_id`` und ``run_id``.
    """
    metrics: Dict[str, Any] = {
        'result_id': result.id,
        'run_id': result.run_id,
    }
    for field in ALL_METRIC_FIELDS + _EXTRA_SELECTABLE_FIELDS:
        if hasattr(result, field):
            metrics[field] = json_safe_value(getattr(result, field))
    return metrics


def select_fold_winner(
    session,
    run_id: int,
    metric: str,
    direction: str,
    trade_floor: int,
) -> Tuple[Optional[BacktestResult], Optional[str]]:
    """Wählt den Sieger eines IS-Laufs nach dem vorregistrierten Kriterium.

    Args:
        session: Aktive SQLAlchemy-Session.
        run_id: Lauf, aus dessen Results gewählt wird.
        metric: Kennzahl-Feld des Kriteriums.
        direction: 'max' oder 'min'.
        trade_floor: Mindestzahl Trades (``total_trades``) eines Kandidaten.

    Returns:
        Tupel (Sieger-Result, Grund). Bei Erfolg ist der Grund None, sonst ist
        das Result None und der Grund benennt im Klartext, warum kein Kandidat
        übrig blieb.
    """
    column = getattr(BacktestResult, metric)
    query = (
        session.query(BacktestResult)
        .filter(BacktestResult.run_id == run_id)
        .filter(column.isnot(None))
    )
    if trade_floor > 0:
        query = query.filter(BacktestResult.total_trades >= trade_floor)

    order = column.desc() if direction == 'max' else column.asc()
    winner = query.order_by(order, BacktestResult.id.asc()).first()
    if winner is not None:
        return winner, None

    total = (
        session.query(BacktestResult)
        .filter(BacktestResult.run_id == run_id)
        .count()
    )
    if total == 0:
        return None, f'Lauf {run_id} hat keine Results.'
    return None, (
        f'Kein Kandidat aus Lauf {run_id} erfüllt den Trade-Floor '
        f'({trade_floor} Trades) mit gesetztem {metric} — {total} Results geprüft.'
    )


def winner_block(result: BacktestResult, metric: str) -> Dict[str, Any]:
    """Baut den eingefrorenen Sieger-Block eines Folds.

    Args:
        result: Das gewinnende Result.
        metric: Kennzahl-Feld des Kriteriums.

    Returns:
        Dict mit Result-ID, Parameterkombination als Kopie, IS-Wert des
        Kriteriums und den vollen IS-Kennzahlen.
    """
    return {
        'result_id': result.id,
        'run_id': result.run_id,
        'actual_params': result.actual_params_json,
        'resolved_config': result.resolved_config_json,
        'full_config_snapshot': result.full_config_snapshot_json,
        'selection_metric': metric,
        'selection_value': json_safe_value(getattr(result, metric, None)),
        'is_metrics': result_metrics(result),
    }
