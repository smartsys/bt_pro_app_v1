"""Gesamtbewertung einer Walk-Forward-Fold-Kette.

Die Rechnung lebt **einmal** und **serverseitig** — hier. Weder die Toolbox noch
eine Auswertung daneben rechnet sie nach: eine zweite Kopie würde unbemerkt
auseinanderlaufen (Drift-Warnung aus den Notizen).

Grundlage sind die balkengenauen Kapitalkurven der Testfenster-Läufe
(``backtest_result_equity``, entsteht beim Recompute eines
Einzelkombinations-Results), **zugeschnitten auf das Testfenster** des jeweiligen
Folds — die gespeicherte Kurve reicht über die geladene OHLC-Spanne und damit
über den flachen Indikator-Vorlauf, der zeitlich ins Testfenster des vorigen
Folds fällt. Sie werden chronologisch aneinandergehängt und je
Fold auf das Startkapital normiert — aus jedem Fold wird also seine
Renditereihe, und die Reihen werden verkettet. Es entsteht **kein** durchgehendes
Portfolio über alle Folds (Signal-Splice ist bewusst nicht gebaut); der
Methodenhinweis an der Kette weist das aus.

**Kein Verdict.** Die Funktion liefert Kennzahlen und Auszählungen, keine
Bewertung, keine Ampel und keinen Score.
"""

import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from user_data.utils.database.models import BacktestEquity, BacktestTrade


def _safe_number(value: Any) -> Optional[float]:
    """Gibt eine endliche Zahl zurück oder None.

    Args:
        value: Beliebiger Wert.

    Returns:
        Der Wert als float, oder None bei None, NaN, Inf oder nicht-Zahl.
    """
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def fold_returns(equity_values: Sequence[float]) -> List[float]:
    """Rechnet eine Kapitalkurve in ihre balkengenaue Renditereihe um.

    Die Normierung auf das Startkapital passiert implizit: aus Kapitalwerten
    werden Verhältnisse, und die sind vom Startwert des Folds unabhängig.

    Args:
        equity_values: Kapitalwerte in zeitlicher Reihenfolge.

    Returns:
        Renditen je Balken (ein Wert weniger als Kapitalwerte). Balken mit
        Vorgängerwert 0 liefern eine Rendite von 0 — sonst wäre die Reihe nicht
        fortsetzbar.
    """
    returns: List[float] = []
    previous: Optional[float] = None
    for raw in equity_values:
        value = _safe_number(raw)
        if value is None:
            continue
        if previous is not None:
            returns.append(value / previous - 1.0 if previous != 0 else 0.0)
        previous = value
    return returns


def chain_metrics(returns: Sequence[float], ann_factor: Optional[float]) -> Dict[str, Any]:
    """Rechnet die Gesamtkennzahlen der verketteten Renditereihe.

    Args:
        returns: Verkettete Renditen je Balken über alle Testfenster.
        ann_factor: Annualisierungsfaktor der Läufe (Jahresfrequenz je
            Balkenfrequenz). None, wenn er an keinem Lauf hängt — dann bleibt der
            Sharpe None statt falsch annualisiert zu sein.

    Returns:
        Dict mit ``total_return_pct``, ``sharpe_ratio``, ``max_drawdown_pct``
        (negativ, wie an ``backtest_results``) und ``bar_count``.
    """
    if not returns:
        return {
            'total_return_pct': None,
            'sharpe_ratio': None,
            'max_drawdown_pct': None,
            'bar_count': 0,
        }

    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for r in returns:
        equity *= (1.0 + r)
        if equity > peak:
            peak = equity
        if peak > 0:
            drawdown = equity / peak - 1.0
            if drawdown < max_drawdown:
                max_drawdown = drawdown

    n = len(returns)
    mean = sum(returns) / n
    sharpe: Optional[float] = None
    if n > 1 and ann_factor:
        variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
        std = math.sqrt(variance)
        if std > 0:
            sharpe = mean / std * math.sqrt(float(ann_factor))

    return {
        'total_return_pct': (equity - 1.0) * 100.0,
        'sharpe_ratio': sharpe,
        'max_drawdown_pct': max_drawdown * 100.0,
        'bar_count': n,
    }


def _window_bounds(window: Optional[Dict[str, Any]]) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Liest die Grenzen eines Fold-Fensters als Zeitstempel.

    Args:
        window: Fensterblock mit ``start``/``end`` (Datum oder ISO-Zeitstempel).

    Returns:
        Tupel (start, end); nicht lesbare oder fehlende Grenzen sind None.
    """
    bounds: List[Optional[datetime]] = []
    for key in ('start', 'end'):
        raw = (window or {}).get(key)
        if not raw:
            bounds.append(None)
            continue
        try:
            bounds.append(datetime.fromisoformat(str(raw)))
        except ValueError:
            bounds.append(None)
    return bounds[0], bounds[1]


def _load_equity_values(
    session: Session, result_id: int, window: Optional[Dict[str, Any]] = None,
) -> List[float]:
    """Liest die Kapitalkurve eines Results innerhalb seines Testfensters.

    Die Kurve eines Laufs reicht über die **geladene** OHLC-Spanne, also inklusive
    des Indikator-Vorlaufs vor dem Handelsfenster. In diesem Vorlauf maskiert der
    Motor jedes Entry weg — die Kurve ist dort flach. Ungefiltert verkettet würden
    diese flachen Balken die Gesamtrechnung verwässern (mehr Balken, gedämpfte
    Streuung) und der Vorlauf eines Folds läge zeitlich im Testfenster des
    vorigen. Deshalb wird auf das Testfenster zugeschnitten, halboffen
    (``start <= t < end``): aufeinanderfolgende Folds grenzen exakt aneinander und
    teilen sich keinen Balken.

    Args:
        session: Aktive SQLAlchemy-Session.
        result_id: Lose Referenz auf backtest_results.id.
        window: Testfenster des Folds. None = keine Einschränkung.

    Returns:
        Kapitalwerte, aufsteigend nach Zeitstempel.
    """
    query = (
        session.query(BacktestEquity.value)
        .filter(BacktestEquity.result_id == result_id)
    )
    start, end = _window_bounds(window)
    if start is not None:
        query = query.filter(BacktestEquity.timestamp >= start)
    if end is not None:
        query = query.filter(BacktestEquity.timestamp < end)
    rows = query.order_by(
        BacktestEquity.timestamp.asc(), BacktestEquity.id.asc(),
    ).all()
    return [row[0] for row in rows]


def _trade_summary(session: Session, result_ids: Sequence[int]) -> Dict[str, Any]:
    """Legt die Trade-Listen aller Testfenster zusammen.

    Args:
        session: Aktive SQLAlchemy-Session.
        result_ids: OOS-Result-IDs der Folds mit Sieger.

    Returns:
        Dict mit ``total_trades``, ``closed_trades``, ``open_trades``,
        ``profit_factor`` (über geschlossene Trades, wie im übrigen System) sowie
        Brutto-Gewinn und -Verlust.
    """
    if not result_ids:
        return {
            'total_trades': 0, 'closed_trades': 0, 'open_trades': 0,
            'profit_factor': None, 'gross_profit': 0.0, 'gross_loss': 0.0,
        }

    rows = (
        session.query(BacktestTrade.status, BacktestTrade.pnl)
        .filter(BacktestTrade.result_id.in_(list(result_ids)))
        .all()
    )
    gross_profit = 0.0
    gross_loss = 0.0
    closed = 0
    open_trades = 0
    for status, pnl in rows:
        if status == 'Open':
            open_trades += 1
            continue
        closed += 1
        value = _safe_number(pnl)
        if value is None:
            continue
        if value >= 0:
            gross_profit += value
        else:
            gross_loss += -value

    profit_factor: Optional[float] = None
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss

    return {
        'total_trades': len(rows),
        'closed_trades': closed,
        'open_trades': open_trades,
        'profit_factor': profit_factor,
        'gross_profit': gross_profit,
        'gross_loss': gross_loss,
    }


def build_chain_aggregate(
    session: Session, plan: Dict[str, Any], folds: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Rechnet die Gesamtbewertung einer Kette aus ihren Fold-Blöcken.

    Args:
        session: Aktive SQLAlchemy-Session (liest Kapitalkurven und Trades der
            OOS-Results).
        plan: Das ``plan_json`` der Kette (liefert das Auswahlkriterium).
        folds: Die angehängten Fold-Blöcke in Reihenfolge.

    Returns:
        Aggregat-Dict mit Gesamtkennzahlen, Fold-Auszählung und der
        Degradations-Sicht (IS-Wert neben OOS-Wert je Fold). Ausweis, keine
        Bewertung.
    """
    metric = plan.get('selection_metric')
    chained_returns: List[float] = []
    oos_result_ids: List[int] = []
    ann_factors: List[float] = []
    degradation: List[Dict[str, Any]] = []
    notes: List[str] = []
    profitable_folds = 0
    folds_with_winner = 0
    folds_measured = 0

    for fold in folds:
        fold_index = fold.get('fold_index')
        winner = fold.get('winner')
        oos_metrics = fold.get('oos_metrics') or {}
        is_value = _safe_number((winner or {}).get('selection_value'))
        oos_value = _safe_number(oos_metrics.get(metric)) if metric else None
        degradation.append({
            'fold_index': fold_index,
            'is_window': (fold.get('is_window') or {}),
            'oos_window': (fold.get('oos_window') or {}),
            'is_value': is_value,
            'oos_value': oos_value,
            'has_winner': winner is not None,
            'no_winner_reason': fold.get('no_winner_reason'),
        })

        if winner is None:
            notes.append(
                f'Fold {fold_index}: kein Sieger — {fold.get("no_winner_reason") or "Grund nicht angegeben"}.'
            )
            continue
        folds_with_winner += 1

        result_id = fold.get('oos_result_id')
        if not result_id:
            notes.append(f'Fold {fold_index}: kein OOS-Result hinterlegt, geht nicht in die Kurve ein.')
            continue

        values = _load_equity_values(session, int(result_id), fold.get('oos_window'))
        returns = fold_returns(values)
        if not returns:
            notes.append(
                f'Fold {fold_index}: keine Kapitalkurve zu Result {result_id} gefunden '
                f'(nicht nachgerechnet oder bereits aufgeräumt).'
            )
            continue

        chained_returns.extend(returns)
        oos_result_ids.append(int(result_id))
        folds_measured += 1
        fold_ann_factor = _safe_number(fold.get('ann_factor'))
        if fold_ann_factor:
            ann_factors.append(fold_ann_factor)
        fold_return = _safe_number(oos_metrics.get('total_return_pct'))
        if fold_return is not None and fold_return > 0:
            profitable_folds += 1

    ann_factor = ann_factors[0] if ann_factors else None
    if ann_factor and any(abs(f - ann_factor) > 1e-9 for f in ann_factors):
        notes.append(
            'Die Testfenster-Läufe tragen unterschiedliche Annualisierungsfaktoren; '
            f'der Sharpe nutzt den des ersten Folds ({ann_factor}).'
        )

    aggregate = chain_metrics(chained_returns, ann_factor)
    trades = _trade_summary(session, oos_result_ids)

    aggregate.update({
        'ann_factor': ann_factor,
        'profit_factor': trades['profit_factor'],
        'total_trades': trades['total_trades'],
        'closed_trades': trades['closed_trades'],
        'open_trades': trades['open_trades'],
        'gross_profit': trades['gross_profit'],
        'gross_loss': trades['gross_loss'],
        'selection_metric': metric,
        'folds_total': len(folds),
        'folds_with_winner': folds_with_winner,
        'folds_without_winner': len(folds) - folds_with_winner,
        'folds_in_curve': folds_measured,
        'profitable_folds': profitable_folds,
        'profitable_folds_pct': (
            round(profitable_folds / folds_measured * 100.0, 2) if folds_measured else None
        ),
        'degradation': degradation,
        'notes': notes,
    })
    return aggregate
