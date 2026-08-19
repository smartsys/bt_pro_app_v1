"""Serverseitige Ermittlung der vier Bestwert-Kandidaten eines Laufs.

Die vier Kriterien sind dieselben, die der Toolbox-Lauf `run-bestwerte` markiert
(`_bestwerte_for_run` in `.claude/skills/ds-strategie-session/scripts/toolbox.py`).
Die Toolbox ist ein reiner HTTP-Client ohne Zugriff auf Projekt-Module und kann
diese Definition nicht importieren; der Befund läuft umgekehrt im Worker ohne HTTP.
Deshalb steht die Rechenregel hier ein zweites Mal — mit denselben Zahlen und
demselben Wortlaut. Die stabilen Keys und die Klartext-Labels kommen dagegen aus der
einen Quelle `best_criteria_labels.py`, damit wenigstens die Benennung nicht driften
kann.

**Kein Gesamtsieger.** Die vier Kandidaten stehen nebeneinander; es gibt keine
Rangfolge und keine Verdichtung zu einer Note.
"""

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.engine import Connection

from services.api.utils.best_criteria_labels import BEST_CRITERIA_LABELS
from user_data.utils.metrics.metric_sets import METRIC_GROUPS

# Bandbreiten und Trade-Floor — identisch zu _bestwerte_for_run in der Toolbox.
WINRATE_BAND_FRACTION: float = 0.20
SHARPE_BAND_FRACTION: float = 0.10
PF_MIN_TRADES: int = 30

# Kennzahlen, die je Kandidat ausgewiesen werden (Anforderung 3 des Tickets).
CANDIDATE_METRIC_FIELDS: Tuple[str, ...] = (
    'sharpe_ratio',
    'total_return_pct',
    'profit_factor',
    'win_rate_pct',
    'total_trades',
    'max_drawdown_pct',
)

# Kennzahl-Felder, die ein Kriterium zum Rechnen braucht. Fehlt eine davon, weil ihre
# Metrik-Gruppe abgewählt war, bleibt der Kandidat leer mit Grund.
_CRITERION_REQUIREMENTS: Dict[str, Tuple[str, ...]] = {
    'max_return': ('total_return_pct',),
    'winrate_band': ('win_rate_pct', 'total_return_pct'),
    'sharpe_band': ('sharpe_ratio', 'total_return_pct'),
    'pf_min30': ('profit_factor', 'total_trades'),
}

# Feld -> Metrik-Gruppe (Umkehrung von METRIC_GROUPS, eine Quelle bleibt metric_sets).
_FIELD_TO_GROUP: Dict[str, str] = {
    field: group for group, fields in METRIC_GROUPS.items() for field in fields
}

_SELECT_COLUMNS = (
    'id, actual_params_json, sharpe_ratio, total_return_pct, profit_factor, '
    'win_rate_pct, total_trades, max_drawdown_pct'
)


def missing_group_reason(field: str, metrics_selection: Any) -> str:
    """Formuliert den Grund für ein Feld, dessen Metrik-Gruppe nicht gerechnet wurde.

    Args:
        field: Name des Kennzahl-Feldes.
        metrics_selection: Rohwert der Metrik-Auswahl des Laufs
            (`backtest_config_json['metrics']`), None entspricht 'auto'.

    Returns:
        Grund im Klartext, wie er im Befund hinterlegt wird.
    """
    group = _FIELD_TO_GROUP.get(field, 'unbekannt')
    selection = 'auto' if metrics_selection is None else metrics_selection
    return f'Metrik-Gruppe nicht gerechnet (Auswahl: {selection}); fehlende Gruppe: {group}'


def _row_to_candidate(
    row, active_groups: frozenset, metrics_selection: Any,
) -> Dict[str, Any]:
    """Baut den Kandidaten-Eintrag eines Sieger-Results.

    Kennzahlen abgewählter Gruppen bleiben leer und tragen ihren Grund — sie werden
    nicht mit 0 gefüllt und nicht weggelassen.

    Args:
        row: Ergebniszeile mit den Spalten aus `_SELECT_COLUMNS`.
        active_groups: Gerechnete Metrik-Gruppen des Laufs.
        metrics_selection: Rohwert der Metrik-Auswahl des Laufs.

    Returns:
        Kandidat mit Result-ID, Parametern und den sechs Kennzahlen.
    """
    metrics: Dict[str, Any] = {}
    reasons: Dict[str, str] = {}
    for field in CANDIDATE_METRIC_FIELDS:
        if _FIELD_TO_GROUP.get(field) not in active_groups:
            metrics[field] = None
            reasons[field] = missing_group_reason(field, metrics_selection)
            continue
        value = getattr(row, field)
        if value is None:
            metrics[field] = None
        else:
            metrics[field] = int(value) if field == 'total_trades' else float(value)
    return {
        'result_id': row.id,
        'params': row.actual_params_json,
        'metrics': metrics,
        'metrics_missing_reason': reasons or None,
    }


def _best_by(
    conn: Connection, run_id: int, order_field: str, where: str = '',
    binds: Optional[Dict[str, Any]] = None,
):
    """Holt das Result mit dem höchsten Wert in `order_field` (NULL zuletzt)."""
    params: Dict[str, Any] = {'run_id': run_id}
    params.update(binds or {})
    clause = f' AND {where}' if where else ''
    return conn.execute(
        text(
            f'SELECT {_SELECT_COLUMNS} FROM backtest_results '
            f'WHERE run_id = :run_id{clause} '
            f'ORDER BY {order_field} DESC NULLS LAST LIMIT 1'
        ),
        params,
    ).fetchone()


def _band_best_return(
    conn: Connection, run_id: int, metric_field: str, fraction: float,
) -> Tuple[Any, Optional[str]]:
    """Bestes Total Return im oberen Band einer Metrik — wie `_band_best_return` der Toolbox.

    Nimmt den Höchstwert der Metrik im Lauf, zieht den Bandanteil vom Betrag des
    Höchstwerts ab und wählt aus dem Band das Result mit dem höchsten Total Return.
    Ein Ausreißer mit wenigen Trades kann den Bestwert damit nicht kapern. Der Abzug
    nutzt den Betrag, damit das Band auch bei durchweg negativem Höchstwert unterhalb
    des Maximums liegt.

    Args:
        conn: Offene Verbindung.
        run_id: Lauf, in dem gesucht wird.
        metric_field: Spalte, die das Band aufspannt.
        fraction: Bandanteil vom Betrag des Höchstwerts.

    Returns:
        Tupel aus Ergebniszeile (oder None) und lesbarer Band-Beschreibung.
    """
    max_value = conn.execute(
        text(f'SELECT MAX({metric_field}) FROM backtest_results WHERE run_id = :run_id'),
        {'run_id': run_id},
    ).scalar()
    if max_value is None:
        return None, None
    max_value = float(max_value)
    threshold = max_value - abs(max_value) * fraction
    n_band = conn.execute(
        text(
            f'SELECT COUNT(*) FROM backtest_results '
            f'WHERE run_id = :run_id AND {metric_field} >= :threshold'
        ),
        {'run_id': run_id, 'threshold': threshold},
    ).scalar()
    row = _best_by(
        conn, run_id, 'total_return_pct',
        where=f'{metric_field} >= :threshold', binds={'threshold': threshold},
    )
    band = f'Band {threshold:.4f}..{max_value:.4f} ({n_band} im Band)'
    return row, band


def select_best_candidates(
    conn: Connection, run_id: int, active_groups: frozenset, metrics_selection: Any,
) -> Dict[str, Dict[str, Any]]:
    """Ermittelt je Bestwert-Kriterium den Sieger eines Laufs.

    Args:
        conn: Offene SQLAlchemy-Verbindung.
        run_id: Lauf, dessen Results durchsucht werden.
        active_groups: Gerechnete Metrik-Gruppen des Laufs (aus `resolve_metric_groups`).
        metrics_selection: Rohwert der Metrik-Auswahl (für den Grund-Text).

    Returns:
        Dict `criterion_key -> {label, band, winner, reason}` in der kanonischen
        Reihenfolge von `BEST_CRITERIA_LABELS`. `winner` ist None, wenn kein Result
        das Kriterium erfüllt oder eine nötige Metrik-Gruppe nicht gerechnet wurde;
        `reason` trägt dann den Grund im Klartext.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for key, label in BEST_CRITERIA_LABELS.items():
        entry: Dict[str, Any] = {
            'label': label, 'band': None, 'winner': None, 'reason': None,
        }
        out[key] = entry

        missing = [
            field for field in _CRITERION_REQUIREMENTS[key]
            if _FIELD_TO_GROUP.get(field) not in active_groups
        ]
        if missing:
            entry['reason'] = missing_group_reason(missing[0], metrics_selection)
            continue

        if key == 'max_return':
            row = _best_by(conn, run_id, 'total_return_pct')
        elif key == 'winrate_band':
            row, entry['band'] = _band_best_return(
                conn, run_id, 'win_rate_pct', WINRATE_BAND_FRACTION,
            )
        elif key == 'sharpe_band':
            row, entry['band'] = _band_best_return(
                conn, run_id, 'sharpe_ratio', SHARPE_BAND_FRACTION,
            )
        else:
            row = _best_by(
                conn, run_id, 'profit_factor',
                where='total_trades >= :floor', binds={'floor': PF_MIN_TRADES},
            )
            entry['band'] = f'mindestens {PF_MIN_TRADES} Trades'

        if row is None:
            entry['reason'] = 'kein Result erfüllt dieses Kriterium in diesem Lauf'
            continue
        entry['winner'] = _row_to_candidate(row, active_groups, metrics_selection)
    return out


def candidate_params(candidates: Dict[str, Dict[str, Any]]) -> List[Tuple[str, dict]]:
    """Sammelt die Parameter der Sieger, jede Kombination nur einmal.

    Args:
        candidates: Rückgabe von `select_best_candidates`.

    Returns:
        Liste aus (Kriterium-Key, Parameter-Dict). Gewinnt ein Result mehrere
        Kriterien, steht es nur einmal drin — mit dem zuerst gefundenen Kriterium.
    """
    seen: set = set()
    out: List[Tuple[str, dict]] = []
    for key, entry in candidates.items():
        winner = entry.get('winner')
        if not winner or not isinstance(winner.get('params'), dict):
            continue
        fingerprint = tuple(sorted(winner['params'].items()))
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        out.append((key, winner['params']))
    return out
