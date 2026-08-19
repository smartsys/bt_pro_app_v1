"""Robustheits-Gruppe des Befunds: DSR mit N und SR0, Plateau, Streuung (Ticket 56).

Drei Blöcke, die alle drei dieselbe Frage beantworten — „trägt der Kandidat oder ist
er ein Zufallsfund?":

* **Deflated Sharpe Ratio** aus der korrigierten Eigenrechnung (Ticket 54). Sie steht
  hier grundsätzlich zusammen mit der Rastergröße `N` und der Rauschlatte `SR0` in
  **einem** Objekt. Eine DSR ohne die beiden ist nicht lesbar: bei 371.943
  Kombinationen liegt die Latte bei annualisiert 2,80, während der beste je real
  erreichte Sharpe 2,26 war. Genau deshalb wird die Zahl nirgends allein ausgewiesen.
* **Plateau-Score der Nachbarschaft** über die vorhandene Serverlogik
  (`lookup_result_rows_by_params` / `get_run_param_steps`), also dieselbe Mechanik wie
  das Toolbox-Verb `result-lookup --summary --tolerance-steps`.
* **Streuung über die Symbole** — bewusst ohne `N_eff`, das am Testset nicht
  ausgewiesen ist (siehe `N_EFF_MISSING_REASON`).
"""

import statistics
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from services.api.utils.best_criteria_selection import candidate_params
from user_data.utils.database.repository import lookup_result_rows_by_params
from user_data.utils.metrics.deflated_sharpe import noise_floor_sr0

# Grund für jedes Feld, das N_eff bräuchte. N_eff ist am Testset noch nicht ausgewiesen
# (Ticket 56, Out of Scope — zurückgestellt bis zum Testset-Neuaufbau).
N_EFF_MISSING_REASON = (
    'N_eff ist am Testset nicht ausgewiesen (Ticket 56, ausdrücklich Out of Scope). '
    'Die Symbolzahl ist kein Ersatz: gemessen entsprechen vier Symbole rund zwei '
    'unabhängigen Tests.'
)

# Nachbarschaft für den Plateau-Score: ein Raster-Schritt je Achse in beide Richtungen.
PLATEAU_TOLERANCE_STEPS: int = 1
# Obergrenze der Treffermenge einer Nachbarschaft (wie das Toolbox-Verb mit --summary).
_PLATEAU_LIMIT: int = 100_000


def _sr0_for_run(conn: Connection, run_id: int, n_combinations: int) -> Dict[str, Any]:
    """Rauschlatte SR0 und ihre Bausteine für einen Lauf.

    `SR0` wird aus der Varianz der **annualisierten** Sharpes gebildet und ist damit
    selbst annualisiert — direkt vergleichbar mit `backtest_results.sharpe_ratio`.
    Die Formel ist dieselbe, die in die DSR eingeht (`noise_floor_sr0`); der Umweg
    über die nicht annualisierten Sharpes ist unnötig, weil sich der Faktor
    `sqrt(ann_factor)` aus Varianz und Latte gleichermaßen herauszieht.

    Args:
        conn: Offene SQLAlchemy-Verbindung.
        run_id: Lauf, dessen Latte gebildet wird.
        n_combinations: Rastergröße des Laufs (`backtest_runs.n_combinations`) — nicht
            die Zahl der vorliegenden Results, die bei ausgedünnten Läufen kleiner ist.

    Returns:
        Dict mit `sr0`, `sr0_basis`, `var_sharpe`, `n_sharpe_values` und `sr0_reason`.
    """
    row = conn.execute(
        text(
            'SELECT var_samp(sharpe_ratio) AS var_sharpe, '
            'COUNT(sharpe_ratio) AS n_values '
            'FROM backtest_results WHERE run_id = :run_id'
        ),
        {'run_id': run_id},
    ).fetchone()
    var_sharpe = None if row.var_sharpe is None else float(row.var_sharpe)
    out: Dict[str, Any] = {
        'var_sharpe': var_sharpe,
        'n_sharpe_values': int(row.n_values or 0),
        'sr0': None,
        'sr0_basis': 'annualisiert, direkt vergleichbar mit sharpe_ratio',
        'sr0_reason': None,
    }
    if n_combinations <= 1:
        out['sr0_reason'] = (
            'N <= 1: ohne Mehrfachvergleich gibt es keine Rauschlatte'
        )
        return out
    if var_sharpe is None:
        out['sr0_reason'] = (
            'weniger als zwei Results mit Sharpe — die Streuung des Rasters ist nicht bildbar'
        )
        return out
    out['sr0'] = noise_floor_sr0(var_sharpe, n_combinations)
    return out


def _dsr_for_results(conn: Connection, result_ids: List[int]) -> Dict[int, Optional[float]]:
    """Liest die gespeicherte DSR mehrerer Results (Nachlauf aus Ticket 54)."""
    if not result_ids:
        return {}
    rows = conn.execute(
        text(
            'SELECT id, deflated_sharpe_ratio FROM backtest_results '
            'WHERE id = ANY(:ids)'
        ),
        {'ids': list(result_ids)},
    ).fetchall()
    return {
        row.id: (None if row.deflated_sharpe_ratio is None else float(row.deflated_sharpe_ratio))
        for row in rows
    }


def build_dsr_block(
    conn: Connection, run: Any, candidates: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """DSR eines Laufs samt `N` und `SR0` — die drei Werte in einem Objekt.

    Args:
        conn: Offene SQLAlchemy-Verbindung.
        run: Zeile aus `backtest_runs` mit `id`, `symbol`, `n_combinations`, `ann_factor`.
        candidates: Bestwert-Kandidaten des Laufs (`select_best_candidates`).

    Returns:
        Dict mit Rastergröße, Rauschlatte und den DSR-Werten der Kandidaten sowie dem
        höchsten DSR-Wert des Laufs.
    """
    n_combinations = int(run.n_combinations or 0)
    block: Dict[str, Any] = {
        'run_id': run.id,
        'symbol': run.symbol,
        'n': n_combinations,
        'n_source': 'backtest_runs.n_combinations (nicht count(*) der Results)',
        'ann_factor': None if run.ann_factor is None else float(run.ann_factor),
    }
    block.update(_sr0_for_run(conn, run.id, n_combinations))

    winner_ids = [
        entry['winner']['result_id']
        for entry in candidates.values()
        if entry.get('winner')
    ]
    dsr_map = _dsr_for_results(conn, winner_ids)
    block['candidates'] = [
        {
            'criterion': key,
            'result_id': entry['winner']['result_id'],
            'deflated_sharpe_ratio': dsr_map.get(entry['winner']['result_id']),
        }
        for key, entry in candidates.items()
        if entry.get('winner')
    ]

    best = conn.execute(
        text(
            'SELECT id, deflated_sharpe_ratio FROM backtest_results '
            'WHERE run_id = :run_id AND deflated_sharpe_ratio IS NOT NULL '
            'ORDER BY deflated_sharpe_ratio DESC LIMIT 1'
        ),
        {'run_id': run.id},
    ).fetchone()
    if best is None:
        block['best'] = None
        block['best_reason'] = (
            'kein Result trägt eine Deflated Sharpe Ratio — sie entsteht als Nachlauf '
            'aus Sharpe, Schiefe, Wölbung und Balkenzahl'
        )
    else:
        block['best'] = {
            'result_id': best.id,
            'deflated_sharpe_ratio': float(best.deflated_sharpe_ratio),
        }
        block['best_reason'] = None
    return block


def _neighborhood_summary(items: List[dict]) -> Dict[str, Any]:
    """Verdichtet eine Nachbarschafts-Treffermenge zum Plateau-Score.

    Feldnamen und Rundung entsprechen dem Toolbox-Verb `result-lookup --summary`,
    damit ein Befund und eine Toolbox-Ausgabe derselben Nachbarschaft dieselben
    Zahlen zeigen.

    Args:
        items: Result-Zeilen der Nachbarschaft (aus `lookup_result_rows_by_params`).

    Returns:
        Median, Mittel, Streuung und Anteil profitabel des Total Return sowie bester
        und schlechtester Treffer.
    """
    values = [
        (float(r['total_return_pct']), r['id']) for r in items
        if isinstance(r.get('total_return_pct'), (int, float))
    ]
    if not values:
        return {'n': len(items), 'n_mit_return': 0}
    returns = [v for v, _ in values]
    best = max(values)
    worst = min(values)
    return {
        'n': len(items),
        'n_mit_return': len(returns),
        'anteil_profitabel_pct': round(100.0 * sum(1 for v in returns if v > 0) / len(returns), 1),
        'return_median': round(statistics.median(returns), 2),
        'return_mittel': round(statistics.fmean(returns), 2),
        'return_streuung': round(statistics.stdev(returns), 2) if len(returns) > 1 else 0.0,
        'return_bester': {'result_id': best[1], 'total_return_pct': round(best[0], 2)},
        'return_schlechtester': {'result_id': worst[1], 'total_return_pct': round(worst[0], 2)},
    }


def build_plateau_block(
    engine: Engine, run_id: int, candidates: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Plateau-Score der Nachbarschaft je Kandidaten-Kombination.

    Nutzt die vorhandene Serverlogik (`lookup_result_rows_by_params` mit
    `tolerance_steps`), die die Schrittweite je Achse aus dem Lauf selbst ableitet —
    eine echte Ein-Schritt-Nachbarschaft auch bei ungleichen Rasterweiten.

    Args:
        engine: Engine der Arbeits-DB.
        run_id: Lauf, in dem die Nachbarschaft gebildet wird.
        candidates: Bestwert-Kandidaten des Laufs.

    Returns:
        Ein Eintrag je unterschiedlicher Kandidaten-Kombination.
    """
    out: List[Dict[str, Any]] = []
    for criterion, params in candidate_params(candidates):
        numeric = {
            name: float(value) for name, value in params.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
        entry: Dict[str, Any] = {
            'criterion': criterion,
            'params': params,
            'tolerance_steps': PLATEAU_TOLERANCE_STEPS,
            'summary': None,
            'reason': None,
        }
        if not numeric:
            entry['reason'] = (
                'keine numerischen Parameter am Sieger — eine Nachbarschaft ist nicht bildbar'
            )
            out.append(entry)
            continue
        items, _ = lookup_result_rows_by_params(
            engine, run_id, numeric, tolerance=0.0, limit=_PLATEAU_LIMIT,
            tolerance_steps=PLATEAU_TOLERANCE_STEPS,
        )
        entry['summary'] = _neighborhood_summary(items)
        out.append(entry)
    return out


def _dispersion(values: List[float]) -> Dict[str, Any]:
    """Kennzahlen der Streuung einer Werteliste (leer -> None-Felder)."""
    if not values:
        return {'min': None, 'max': None, 'mittel': None, 'streuung': None, 'spanne': None}
    return {
        'min': round(min(values), 4),
        'max': round(max(values), 4),
        'mittel': round(statistics.fmean(values), 4),
        'streuung': round(statistics.stdev(values), 4) if len(values) > 1 else 0.0,
        'spanne': round(max(values) - min(values), 4),
    }


def build_symbol_dispersion(
    conn: Connection, per_run: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Streuung über die Symbole — je Lauf ein Symbol.

    Zwei Sichten nebeneinander: die Spitzen (Sieger des Kriteriums `max_return` je
    Lauf) und der Median des ganzen Rasters je Lauf. Die zweite Sicht ist die
    robustere, weil sie nicht an einer einzelnen Kombination hängt.

    Args:
        conn: Offene SQLAlchemy-Verbindung.
        per_run: Ergebnis-Einträge je Lauf mit `run_id`, `symbol` und `candidates`.

    Returns:
        Streuungs-Kennzahlen samt Roh-Werten je Lauf; `n_eff` bleibt leer mit Grund.
    """
    tops: List[Dict[str, Any]] = []
    medians: List[Dict[str, Any]] = []
    for run_entry in per_run:
        winner = (run_entry['candidates'].get('max_return') or {}).get('winner')
        if winner:
            tops.append({
                'run_id': run_entry['run_id'],
                'symbol': run_entry['symbol'],
                'result_id': winner['result_id'],
                'total_return_pct': winner['metrics'].get('total_return_pct'),
                'sharpe_ratio': winner['metrics'].get('sharpe_ratio'),
            })
        median = conn.execute(
            text(
                'SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY total_return_pct) '
                'FROM backtest_results WHERE run_id = :run_id'
            ),
            {'run_id': run_entry['run_id']},
        ).scalar()
        medians.append({
            'run_id': run_entry['run_id'],
            'symbol': run_entry['symbol'],
            'median_total_return_pct': None if median is None else round(float(median), 4),
        })

    top_returns = [t['total_return_pct'] for t in tops if t['total_return_pct'] is not None]
    top_sharpes = [t['sharpe_ratio'] for t in tops if t['sharpe_ratio'] is not None]
    median_values = [
        m['median_total_return_pct'] for m in medians
        if m['median_total_return_pct'] is not None
    ]
    return {
        'basis': (
            'je Lauf ein Symbol; Spitzen = Sieger des Kriteriums "max_return", '
            'Median = Median des gesamten Rasters'
        ),
        'n_symbols': len({m['symbol'] for m in medians}),
        'n_eff': None,
        'n_eff_reason': N_EFF_MISSING_REASON,
        'spitzen': tops,
        'spitzen_total_return_pct': _dispersion(top_returns),
        'spitzen_sharpe_ratio': _dispersion(top_sharpes),
        'median_je_lauf': medians,
        'median_total_return_pct': _dispersion(median_values),
    }
