"""
Repository-Funktionen

Speichert Strategie-Ergebnisse in PostgreSQL/TimescaleDB.
- backtest_runs: immer neuer INSERT
- backtest_results: Upsert per params_hash (MD5 aus run_id + actual_params)
- Kennzahlen: genau eine Funktion für jeden Lauf — `_extract_metrics`. Ein Result
  trägt denselben Satz Kennzahlen, unabhängig davon, ob es aus einem Einzellauf
  oder aus einem Multiparameterlauf stammt (Ticket 64). Die Zeitreihen (Equity,
  Trades, Orders, Positionen, Indikatorwerte) bleiben davon getrennt — sie
  skalieren mit Kombinationen x Balken und entstehen nur beim Einzellauf
  beziehungsweise auf Anforderung ("Analyse starten").
- Welche Kennzahl-Gruppen ein Lauf rechnet, ist wählbar (Ticket 68). Die
  Zuordnung Gruppe -> Felder steht ausschließlich in
  `user_data/utils/metrics/metric_sets.py`. Geschrieben werden immer alle
  Kennzahl-Spalten: nicht gerechnete Felder ausdrücklich als NULL, damit ein
  Result nie ein Gemisch aus zwei Läufen mit verschiedener Auswahl trägt.
- Deflated Sharpe Ratio: die einzige rasterweite Kennzahl und deshalb kein Teil
  von `_extract_metrics`, sondern ein Nachlauf über den ganzen Lauf
  (`_calculate_deflated_sharpe`, Ticket 54).
"""

import hashlib
import json
import logging
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine

from user_data.utils.database.db import get_engine
from user_data.utils.database.models import (
    BacktestRun, BacktestResult, BacktestTrade, BacktestOrder,
    BacktestPosition, BacktestIndicator, BacktestEquity, BacktestParam
)
# GEÄNDERT: Ticket 58 — Kennzahlen laufen ausschließlich über das Handelsfenster
# start..end der BacktestConfig. Der Zuschnitt steht einmal in trading_window.py.
from user_data.utils.metrics.trading_window import (
    count_open_trades,
    slice_to_trading_window,
)
# GEÄNDERT: Ticket 54 — die Deflated Sharpe Ratio kommt aus der eigenen, korrigierten
# Rechnung und läuft als Nachlauf über den ganzen Lauf (siehe _calculate_deflated_sharpe).
from user_data.utils.metrics.deflated_sharpe import deflated_sharpe_ratio
# GEÄNDERT: Ticket 68 — Metrik-Gruppen und Feldliste kommen aus der einzigen Quelle.
# Das Modul selbst (nicht nur einzelne Namen) wird zusätzlich importiert, damit die
# Selbstauskunft-Notiz immer den LIVE-Wert von AUTO_FULL_COMBINATION_THRESHOLD zeigt
# (relevant für Tests, die die Schwelle testweise klein stellen).
from user_data.utils.metrics import metric_sets
from user_data.utils.metrics.metric_sets import (
    ALL_GROUPS,
    ALL_METRIC_FIELDS,
    STAGE_AUTO,
    normalize_groups,
    resolve_metric_groups,
    skipped_fields,
)

logger = logging.getLogger(__name__)


def _safe_float(value) -> Optional[float]:
    """Konvertiert einen Wert sicher zu float, None bei NaN/Inf."""
    if value is None:
        return None
    try:
        f = float(value)
        if np.isnan(f) or np.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _safe_int(value) -> Optional[int]:
    """Konvertiert einen Wert sicher zu int, None bei NaN."""
    if value is None:
        return None
    try:
        f = float(value)
        if np.isnan(f) or np.isinf(f):
            return None
        return int(f)
    except (TypeError, ValueError):
        return None


def _safe_duration(value) -> Optional[str]:
    """Konvertiert Timedelta zu String, None bei NaT.

    GEÄNDERT: Ticket 64 — die Prüfung fasst jetzt jeden fehlenden Wert, nicht nur
    `pd.Timedelta`-Instanzen. `pd.NaT` ist selbst keine `Timedelta` und lief vorher
    durch: `str(pd.NaT)` hätte die Zeichenkette "NaT" in die Datenbank geschrieben.
    Vorher konnte das nicht auffallen, weil die Dauer-Felder nur im Einzellauf-Pfad
    entstanden; seit sie in jedem Lauf mitlaufen, trifft der Fall jedes Result ohne
    Gewinn- beziehungsweise Verlust-Trade.

    Args:
        value: Zeitspanne (`pd.Timedelta`), `pd.NaT` oder None.

    Returns:
        Zeitspanne als Zeichenkette, None wenn nicht bestimmbar.
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def _safe_datetime(value) -> Optional[datetime]:
    """Konvertiert Pandas Timestamp zu Python datetime."""
    if value is None or pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().replace(tzinfo=None)
    return None


def _safe_json_value(val):
    """Konvertiert numpy-Typen zu JSON-kompatiblen Python-Typen."""
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val)
    if isinstance(val, np.ndarray):
        return val.tolist()
    return val


def _make_params_hash(run_id: int, actual_params: dict) -> str:
    """Erzeugt MD5-Hash aus run_id + actual_params für Duplikat-Erkennung."""
    raw = f"{run_id}|{json.dumps(actual_params, sort_keys=True)}"
    return hashlib.md5(raw.encode()).hexdigest()


def _extract_metrics(
    portfolios,
    columns,
    backtest_config: dict,
    groups: Optional[Iterable[str]] = None,
) -> list[dict]:
    """Extrahiert den Kennzahlensatz je Kombination — für jeden Lauf.

    Die einzige Kennzahl-Funktion des Systems (Ticket 64). Sie ersetzt die drei
    früheren Funktionen `_extract_partial_metrics` (Multiparameterlauf, 24 Felder),
    `_extract_chart_metrics` (Einzellauf, 34 Felder) und `_extract_full_metrics`
    (Hintergrund-Job, 13 Felder mit vier Dubletten). Ein Result trägt damit
    denselben Satz Kennzahlen, unabhängig davon, wie es entstanden ist — die Frage
    „welchen Rechenpfad ist dieses Result gelaufen?" ist strukturell nicht mehr
    stellbar, weil es nur noch einen Weg gibt.

    Alle Größen werden **vektorisiert über alle Spalten** gerechnet, nie über
    `pf.stats()` je Kombination. Die Zuordnung zu den `stats()`-Feldern ist am
    VBT-Quelltext abgelesen (`Portfolio._metrics`) und am laufenden Kernel gegen
    `pf.stats(column=...)` gemessen: 24 von 26 gemeinsamen Feldern sind bitgleich,
    `benchmark_return_pct` und `max_drawdown_pct` weichen um rund 1e-13 ab, weil
    sie über eine andere VBT-Route laufen (`total_market_return`/`max_drawdown`
    statt `bm_returns.vbt.returns.total`/`drawdowns.max_drawdown`).

    Handelsfenster (Ticket 58): Das Portfolio wird vor jeder Messung auf
    `start`..`end` der BacktestConfig zugeschnitten — im gechunkten Lauf je Chunk,
    sonst einmal. Der Vorlauf (`ohlc_start`..`ohlc_end`) wärmt nur die Indikatoren
    auf und geht in keine Kennzahl ein, weder in den Buy-and-Hold-Vergleichsmaßstab
    noch in Sharpe oder die annualisierten Größen.

    Randfall „am Fensterende offene Position" — die getroffene Entscheidung:
    Eine Position, die über `end` hinausläuft, wird von vbt zur Fenstergrenze
    marktbewertet und erscheint als offener Trade.

    * `total_return_pct`, `end_value` und alle Drawdown-/Risikogrößen zählen diese
      Marktbewertung **mit**. Das Vermögen zum Fensterende ist eine Tatsache,
      keine Schätzung.
    * `win_rate_pct`, `profit_factor`, `expectancy`, `best_trade_pct`,
      `worst_trade_pct`, die Avg-Trade-Felder sowie `sqn` und `edge_ratio` rechnen
      **ausschließlich über geschlossene Trades** (`trades.status_closed`). Ein
      unrealisierter Buchgewinn ist kein Ergebnis. Das ist zugleich der
      vbt-Standard: der Stats-Builder läuft mit `incl_open=False` und ersetzt
      `trades` dann intern durch `trades.status_closed`
      (`Portfolio.post_resolve_attr`, am Quelltext gelesen).
    * `total_trades` zählt die offene Position weiterhin mit (vbt-Konvention);
      `open_trades` weist sie aus. `total_trades - open_trades` ist die
      Grundgesamtheit der oben genannten Kennzahlen. Ohne geschlossene Trades
      liefert vbt `NaN` → `None` (`_safe_float`), nicht `0`.
    * `long_trades`/`short_trades` zählen wie `total_trades` inklusive einer
      offenen Position; ihre Summe ist `total_trades`.

    Die Kennzahlen-Gruppen sind unten als **Abschnitte** gegliedert, bewusst nicht
    als eigene aufrufbare Funktionen — sonst kehrt die aufgelöste Zweiteilung durch
    die Hintertür zurück.

    Auswahl (Ticket 68): `groups` benennt, welche Gruppen gerechnet werden. Ein
    abgewählter Abschnitt wird **samt seinen Zwischenobjekten** übersprungen — der
    Sinn der Auswahl ist gesparte Rechenzeit, nicht das nachträgliche Verwerfen
    fertiger Werte. Die Pflichtgruppen (`user_data/utils/metrics/metric_sets.py`)
    laufen immer mit; ihre Felder sind zugleich die Eingänge des DSR-Nachlaufs.

    Nicht enthalten (Ticket 54): die `deflated_sharpe_ratio`. Sie ist die einzige
    **rasterweite** Kennzahl — ihr Wert hängt davon ab, wie viele andere
    Kombinationen mitgelaufen sind — und gehört damit nicht in eine Funktion, die
    je Kombination rechnet. Sie entsteht als Nachlauf über den ganzen Lauf in
    `_calculate_deflated_sharpe`. Diese Funktion liefert nur ihre Bausteine
    (`skew`, `kurtosis`, `sharpe_ratio`, `bar_count`).

    Args:
        portfolios: Portfolio über eine oder viele Kombinationen (ungeschnitten).
        columns: Spalten-Index der Kombinationen; seine Länge bestimmt die Zahl der
            zurückgegebenen Datensätze und ihre Reihenfolge.
        backtest_config: BacktestConfig-Dict mit 'start' und 'end'.
        groups: Aufgelöste Gruppenmenge aus `metric_sets.resolve_metric_groups`.
            None rechnet alle Gruppen.

    Returns:
        Liste mit je einem Metrik-Dict pro Kombination (Schlüssel = Spaltennamen
        von BacktestResult). Enthalten sind nur die Felder der aktiven Gruppen.

    Raises:
        ValueError: Bei einem unbekannten Gruppen-Key in `groups`.
    """
    import time as _time
    from scipy import stats as scipy_stats
    # Lokale Imports, damit das DB-Repository ohne vectorbtpro importierbar bleibt —
    # diese Funktion läuft ausschließlich im Run-Kontext, wo vbt verfügbar ist.
    from vectorbtpro.base.reshaping import to_2d_array
    from vectorbtpro.generic.enums import WType
    from vectorbtpro.indicators.nb import atr_nb

    # GEÄNDERT: Ticket 68 — aktive Gruppen bestimmen. Ohne Angabe wird alles gerechnet.
    active_groups = ALL_GROUPS if groups is None else normalize_groups(groups)

    # GEÄNDERT: Ticket 58 — Zuschnitt auf das Handelsfenster vor jeder Messung.
    portfolios = slice_to_trading_window(portfolios, backtest_config)
    n_combinations = len(columns)

    # GEÄNDERT: Ticket 44 Bugfix — atleast_1d(...) wandelt VBT-Skalare (eine Spalte) in
    # 1-Element-Arrays, bevor .values geholt wird. Bei mehreren Spalten ein No-Op.
    def _vals(x):
        x = np.atleast_1d(x)
        return x.values if hasattr(x, 'values') else x

    def _durations(x) -> list:
        """Zeitspannen je Kombination als Liste; ein Skalar wird zur 1-Element-Liste.

        Nötig, weil Zeitspalten nicht über den DataFrame laufen: `pd.Timedelta`
        würde dort zu `timedelta64` und `str(...)` läge daneben.
        """
        if isinstance(x, pd.Series):
            return list(x)
        return [x] * n_combinations

    # =====================================================================
    # Abschnitt 1 — Gerechneter Zeitraum und Umfang
    # =====================================================================
    # Der zugeschnittene Index ist über alle Spalten identisch (dasselbe
    # OHLCV-Fenster), deshalb einmal gebildet statt je Kombination.
    # total_duration = bar_count * wrapper.freq — dieselbe Definition wie vbt in
    # pf.stats()['Total Duration'] (im vbt-Kernel gemessen), NICHT
    # index[-1] - index[0]. Letzteres ist um eine Balkenbreite kürzer.
    _index = portfolios.wrapper.index
    _bar_count = _safe_int(_index.shape[0])
    _start_index = _safe_datetime(_index[0])
    _end_index = _safe_datetime(_index[-1])
    _total_duration = _safe_duration(_index.shape[0] * portfolios.wrapper.freq)

    # Einmal binden statt je Kennzahl neu auflösen.
    _wrapper = portfolios.wrapper
    _trades = portfolios.trades
    # GEÄNDERT: Ticket 68 — die Auswahl auf geschlossene Trades ist selbst schon Arbeit
    # (sie filtert die Trade-Records) und wird nur von 'trade_quality' und 'sqn_edge'
    # gebraucht. Sind beide abgewählt, entsteht sie gar nicht erst.
    _closed = (
        _trades.status_closed
        if active_groups & {'trade_quality', 'sqn_edge'}
        else None
    )

    # =====================================================================
    # Abschnitt 2 — Portfolio-Werte und Rendite
    # =====================================================================
    t0 = _time.time()
    start_value = portfolios.init_value
    min_value = portfolios.value.vbt.min()
    max_value = portfolios.value.vbt.max()
    final_value = portfolios.final_value
    total_return = portfolios.total_return * 100
    total_market_return = portfolios.total_market_return * 100
    position_coverage = portfolios.position_coverage * 100
    max_gross_exposure = portfolios.gross_exposure.vbt.max() * 100
    print(f"  [DB] Portfolio-Werte: {_time.time() - t0:.1f}s")

    # =====================================================================
    # Abschnitt 3 — Drawdown (Gruppe 'drawdown')
    # =====================================================================
    if 'drawdown' in active_groups:
        t0 = _time.time()
        # pf.max_drawdown liefert den Wert bereits negativ; so wird er auch gespeichert.
        max_dd = portfolios.max_drawdown * 100
        max_dd_duration = portfolios.drawdowns.max_duration
        print(f"  [DB] Drawdown: {_time.time() - t0:.1f}s")

    # =====================================================================
    # Abschnitt 4 — Orders und Trades
    # =====================================================================
    t0 = _time.time()
    total_orders = portfolios.orders.count()
    total_fees_paid = portfolios.orders.fees.sum()
    trade_count = _trades.count()
    open_trade_count = count_open_trades(portfolios)
    long_trade_count = _trades.direction_long.count()
    short_trade_count = _trades.direction_short.count()
    print(f"  [DB] Orders/Trades: {_time.time() - t0:.1f}s")

    # Gruppe 'trade_quality'
    if 'trade_quality' in active_groups:
        t0 = _time.time()
        win_rate = _closed.win_rate * 100
        profit_factor = _closed.profit_factor
        expectancy = _closed.expectancy
        best_trade = _closed.returns.max() * 100
        worst_trade = _closed.returns.min() * 100
        avg_winning_trade = _closed.winning.returns.mean() * 100
        avg_losing_trade = _closed.losing.returns.mean() * 100
        avg_winning_duration = _wrapper.arr_to_timedelta(_closed.winning.duration.mean())
        avg_losing_duration = _wrapper.arr_to_timedelta(_closed.losing.duration.mean())
        print(f"  [DB] Trade-Kennzahlen: {_time.time() - t0:.1f}s")

    # GEÄNDERT: Ticket 64 — sqn und edge_ratio laufen wieder in jedem Lauf mit. Sie
    # waren 2026 ungemessen zu den teuren Kennzahlen sortiert worden; gemessen kostet
    # sqn bei 3.600 Kombinationen 0,40 s und skaliert überhaupt nicht (es reduziert
    # über die Trade-Records, nicht über die Renditematrix), edge_ratio 0,81 s.
    #
    # edge_ratio bekommt seine Volatilität ausdrücklich mitgegeben. Grund, am
    # VBT-Quelltext gefunden und am laufenden Kernel gemessen: Ohne das Argument baut
    # `Trades.get_edge_ratio` sie selbst über
    # `atr_nb(high=to_2d_array(self._high), low=..., close=to_2d_array(self._close))`.
    # `atr_nb` greift dort mit `high[:, col]` unmittelbar auf die Spalte zu, statt sie
    # flexibel auszuwählen. In diesem System trägt ein Portfolio aber genau **eine**
    # OHLC-Spalte für beliebig viele Kombinationen — alle rechnen auf demselben Symbol
    # und Zeitfenster, nur die Signale unterscheiden sich. `high` ist damit (T, 1),
    # `close` dagegen (T, N). Für jede Spalte ab der zweiten liest `high[:, col]` in
    # numba ohne Bereichsprüfung an einer um `col` Zeilen versetzten Stelle weiter,
    # teilweise über das Pufferende hinaus. Folge: ab Spalte 1 falsche Volatilität und
    # damit falsche edge_ratio. Gemessen an einem Raster aus drei Kombinationen:
    # VBT-Default 2,3878 / 2,7244 / 2,6314 gegen die Referenz aus drei einzeln
    # gerechneten Portfolios 2,3878 / 2,7740 / 2,7333 — nur die erste Spalte stimmte.
    #
    # Die Korrektur rechnet denselben VBT-ATR, nur auf so vielen Spalten, wie OHLC
    # tatsächlich hat, und übergibt ihn über den dafür vorgesehenen Parameter. Innerhalb
    # von `edge_ratio_nb` wird die Volatilität über `flex_select_nb` gelesen — eine
    # (T, 1)-Matrix gilt dort korrekt für alle Spalten. Fehlen high/low, rechnet VBT
    # ohnehin über `msd_nb` allein auf `close`; dort gibt es den Formfehler nicht, und
    # die Volatilität bleibt VBT überlassen (None).
    #
    # Gruppe 'sqn_edge'
    if 'sqn_edge' in active_groups:
        t0 = _time.time()
        sqn = _closed.sqn
        edge_volatility = None
        if _closed._high is not None and _closed._low is not None:
            _high_2d = to_2d_array(_closed._high)
            _low_2d = to_2d_array(_closed._low)
            _close_2d = to_2d_array(_closed._close)
            _ohlc_cols = min(_high_2d.shape[1], _low_2d.shape[1], _close_2d.shape[1])
            edge_volatility = atr_nb(
                high=_high_2d[:, :_ohlc_cols],
                low=_low_2d[:, :_ohlc_cols],
                close=_close_2d[:, :_ohlc_cols],
                window=14,
                wtype=WType.Wilder,
            )[1]
        edge_ratio = _closed.get_edge_ratio(volatility=edge_volatility)
        print(f"  [DB] sqn/edge_ratio: {_time.time() - t0:.1f}s")

    # =====================================================================
    # Abschnitt 5 — Risiko- und Rendite-Verhältnisse
    # =====================================================================
    t0 = _time.time()
    sharpe = portfolios.sharpe_ratio
    sortino = portfolios.sortino_ratio
    calmar = portfolios.calmar_ratio
    omega = portfolios.omega_ratio
    ann_return = portfolios.annualized_return * 100
    ann_vol = portfolios.annualized_volatility * 100
    down_risk = portfolios.downside_risk * 100
    print(f"  [DB] Risiko-Verhältnisse: {_time.time() - t0:.1f}s")

    # =====================================================================
    # Abschnitt 6 — Extremrisiko (perzentil-basiert, parallel gerechnet; 'tail_risk')
    # =====================================================================
    # GEÄNDERT: Ticket 64 — parallel gerechnet. tail_ratio_nb/value_at_risk_nb/
    # cond_value_at_risk_nb sind laut VBT-Quelltext mit
    # @register_jitted(cache=True, tags={"can_parallel"}) und einer prange-Schleife
    # über die Spalten markiert, werden über die Property (pf.tail_ratio etc.) aber
    # sequenziell ausgeführt. Die get_*-Methode nimmt das jitted-Argument entgegen
    # und reicht es an resolve_jitted_option durch — dieselbe Rechnung, nur auf
    # mehreren Kernen (am VBT-Quelltext belegt, nicht angenommen; die Werte sind
    # bei 3.600 Kombinationen bitgenau gegen den sequenziellen Stand geprüft).
    if 'tail_risk' in active_groups:
        t0 = _time.time()
        tail_ratio = portfolios.get_tail_ratio(jitted=dict(parallel=True))
        value_at_risk = portfolios.get_value_at_risk(jitted=dict(parallel=True))
        cond_value_at_risk = portfolios.get_cond_value_at_risk(jitted=dict(parallel=True))
        print(f"  [DB] Extremrisiko (parallel): {_time.time() - t0:.1f}s")

    # =====================================================================
    # Abschnitt 7 — Benchmark-relative Kennzahlen (Gruppe 'benchmark')
    # =====================================================================
    if 'benchmark' in active_groups:
        t0 = _time.time()
        alpha = portfolios.alpha
        beta = portfolios.beta
        information_ratio = portfolios.information_ratio
        print(f"  [DB] Benchmark-relativ: {_time.time() - t0:.1f}s")

    # =====================================================================
    # Abschnitt 8 — Verteilungsform der Renditen (Bausteine der Deflated Sharpe Ratio)
    # =====================================================================
    # GEÄNDERT: Ticket 64 — skew und kurtosis je Kombination persistieren. Ohne sie
    # ist die Deflated Sharpe Ratio nicht nachrechenbar; dass sie nie gespeichert
    # wurden, ist der Grund, warum der Altbestand nicht neu gerechnet werden kann.
    # Rechenweg exakt so, wie VBT ihn intern für die DSR nutzt (am Quelltext von
    # ReturnsAccessor.deflated_sharpe_ratio gelesen): NaN der Renditematrix vorher
    # auf 0 setzen, scipy mit bias=True. EINZIGER Unterschied: fisher=False —
    # gespeichert wird die ROHE Wölbung (Normalverteilung rund 3), nicht die
    # Excess-Wölbung. scipy liefert per Default fisher=True; dass VBT diesen Default
    # in die Formel (kurtosis - 1) / 4 einsetzt, die die rohe Wölbung erwartet, war
    # einer der beiden Formelfehler, die Ticket 54 behoben hat.
    # GEÄNDERT: Ticket 54 — die DSR selbst wird hier NICHT mehr gerechnet. Sie ist
    # rasterweit und läuft als Nachlauf über den ganzen Run
    # (_calculate_deflated_sharpe); diese Funktion liefert nur ihre Bausteine.
    t0 = _time.time()
    _returns_2d = np.asarray(portfolios.returns)
    if _returns_2d.ndim == 1:
        _returns_2d = _returns_2d.reshape(-1, 1)
    _nanmask = np.isnan(_returns_2d)
    if _nanmask.any():
        _returns_2d = _returns_2d.copy()
        _returns_2d[_nanmask] = 0.0
    skew = np.atleast_1d(scipy_stats.skew(_returns_2d, axis=0, bias=True))
    kurtosis = np.atleast_1d(
        scipy_stats.kurtosis(_returns_2d, axis=0, bias=True, fisher=False)
    )
    del _returns_2d
    print(f"  [DB] Verteilungsform (skew/kurtosis): {_time.time() - t0:.1f}s")

    # =====================================================================
    # Zusammenbau
    # =====================================================================
    # GEÄNDERT: Ticket 68 — der DataFrame trägt nur die Spalten der aktiven Gruppen.
    # Reihenfolge unverändert zum Stand vor dem Ticket, damit die Auswahl 'voll' Feld
    # für Feld dasselbe Ergebnis liefert wie bisher.
    t0 = _time.time()
    data = {
        'start_value': _vals(start_value),
        'min_value': _vals(min_value),
        'max_value': _vals(max_value),
        'end_value': _vals(final_value),
        'total_return_pct': _vals(total_return),
        'benchmark_return_pct': _vals(total_market_return),
        'position_coverage_pct': _vals(position_coverage),
        'max_gross_exposure_pct': _vals(max_gross_exposure),
    }
    if 'drawdown' in active_groups:
        data['max_drawdown_pct'] = _vals(max_dd)
    data.update({
        'total_orders': _vals(total_orders),
        'total_fees_paid': _vals(total_fees_paid),
        'total_trades': _vals(trade_count),
        'open_trades': _vals(open_trade_count),
        'long_trades': _vals(long_trade_count),
        'short_trades': _vals(short_trade_count),
    })
    if 'trade_quality' in active_groups:
        data.update({
            'win_rate_pct': _vals(win_rate),
            'best_trade_pct': _vals(best_trade),
            'worst_trade_pct': _vals(worst_trade),
            'avg_winning_trade_pct': _vals(avg_winning_trade),
            'avg_losing_trade_pct': _vals(avg_losing_trade),
            'profit_factor': _vals(profit_factor),
            'expectancy': _vals(expectancy),
        })
    if 'sqn_edge' in active_groups:
        data.update({
            'sqn': _vals(sqn),
            'edge_ratio': _vals(edge_ratio),
        })
    data.update({
        'sharpe_ratio': _vals(sharpe),
        'sortino_ratio': _vals(sortino),
        'calmar_ratio': _vals(calmar),
        'omega_ratio': _vals(omega),
        'annualized_return': _vals(ann_return),
        'annualized_volatility': _vals(ann_vol),
        'downside_risk': _vals(down_risk),
    })
    if 'tail_risk' in active_groups:
        data.update({
            'tail_ratio': _vals(tail_ratio),
            'value_at_risk': _vals(value_at_risk),
            'cond_value_at_risk': _vals(cond_value_at_risk),
        })
    if 'benchmark' in active_groups:
        data.update({
            'alpha': _vals(alpha),
            'beta': _vals(beta),
            'information_ratio': _vals(information_ratio),
        })
    data.update({
        'skew': skew,
        'kurtosis': kurtosis,
    })
    df = pd.DataFrame(data)

    # GEÄNDERT: NaN/Inf echt zu None konvertieren. Das frühere df.where(np.isfinite(df), None)
    # war ein No-Op für Float-Spalten — pandas wandelt None dort sofort zurück in NaN, sodass
    # NaN ungefiltert in die DB lief und u.a. die Sortierung verfälschte (NaN gilt in PostgreSQL
    # als größter Wert). Konvertierung daher erst auf Record-Ebene nach to_dict.
    for _int_col in ('total_orders', 'total_trades', 'open_trades', 'long_trades', 'short_trades'):
        df[_int_col] = df[_int_col].apply(
            lambda x: int(x) if pd.notna(x) and np.isfinite(x) else None
        )
    print(f"  [DB] DataFrame: {_time.time() - t0:.1f}s, {len(df)} Zeilen")

    if 'drawdown' in active_groups:
        _max_dd_durations = _durations(max_dd_duration)
    if 'trade_quality' in active_groups:
        _avg_win_durations = _durations(avg_winning_duration)
        _avg_lose_durations = _durations(avg_losing_duration)

    records = df.to_dict('records')
    for idx, r in enumerate(records):
        for key, value in r.items():
            if isinstance(value, float) and not np.isfinite(value):
                r[key] = None
        # Für jede Kombination identisch (dasselbe geschnittene Fenster).
        r['start_index'] = _start_index
        r['end_index'] = _end_index
        r['total_duration'] = _total_duration
        r['bar_count'] = _bar_count
        # GEÄNDERT: Ticket 64 — die drei Dauer-Felder laufen jetzt in jedem Lauf mit.
        # Dass VBT sie über ein Multi-Spalten-Portfolio vektorisiert liefert, war offen
        # und ist am vbt-Kernel gemessen: drawdowns.max_duration sowie
        # trades.status_closed.winning/losing.duration.mean() geben eine Series über die
        # Spalten zurück, deren Werte mit pf.stats() der Einzelspalte bitgleich sind.
        if 'drawdown' in active_groups:
            r['max_drawdown_duration'] = _safe_duration(_max_dd_durations[idx])
        if 'trade_quality' in active_groups:
            r['avg_winning_trade_duration'] = _safe_duration(_avg_win_durations[idx])
            r['avg_losing_trade_duration'] = _safe_duration(_avg_lose_durations[idx])
    return records


def _calculate_deflated_sharpe(conn, run_id: int) -> int:
    """Rechnet die Deflated Sharpe Ratio als Nachlauf über den ganzen Lauf.

    Die DSR ist die einzige rasterweite Kennzahl: `var_sharpe` läuft über alle
    Kombinationen des Laufs und die Rastergröße `N` geht direkt in die
    Deflationsschwelle ein. Je Kombination oder je Chunk gerechnet ist sie damit
    strukturell falsch — deshalb entsteht sie hier, nachdem alle Results
    geschrieben sind, in einem Durchgang über den kompletten Lauf (Ticket 54).

    Braucht kein Portfolio: alle Eingaben stehen in der Datenbank. Damit ist der
    Nachlauf speicherneutral und im gechunkten Fall automatisch richtig — der
    gechunkte und der ungechunkte Lauf gehen durch exakt denselben Code.

    Zwei Punkte, die leicht falsch gemacht werden:

    * **`N` kommt aus `backtest_runs.n_combinations`, nicht aus `count(*)`.** Ein
      Lauf kann auf einzelne Ergebnisse ausgedünnt sein; die Zahl der vorliegenden
      Results ist dann nicht die Zahl der tatsächlich gelaufenen Versuche, und die
      Kennzahl fiele zu milde aus.
    * **Der gespeicherte Sharpe ist annualisiert, die Formel braucht ihn je
      Balken.** Rückgerechnet wird mit `SR_bar = SR_ann / sqrt(ann_factor)`. Das ist
      exakt, keine Näherung: VBTs `sharpe_ratio_1d_nb` schließt mit
      `mean / std * sqrt(ann_factor)` (am Quelltext gelesen).

    Results ohne Momente (`skew`/`kurtosis` NULL) oder ohne Sharpe tragen NaN durch
    die Rechnung und bekommen NULL geschrieben — ein leeres Feld ist ehrlich.

    Args:
        conn: Offene SQLAlchemy-Verbindung. Der Nachlauf läuft bewusst in derselben
            Transaktion wie das Speichern des Laufs, damit der Zustand atomar bleibt
            (Results, `n_combinations`, `ann_factor` und DSR gehören zusammen).
        run_id: ID des Laufs, dessen Results bewertet werden.

    Returns:
        Anzahl der Results, für die ein Wert geschrieben wurde (auch NULL zählt —
        die Spalte wurde angefasst).

    Raises:
        ValueError: Wenn der Lauf nicht existiert oder kein `ann_factor` trägt. Ohne
            ihn ist der Sharpe je Balken nicht rekonstruierbar; ein geschätzter oder
            geratener Faktor käme nicht in Frage.
    """
    run_row = conn.execute(
        text(
            'SELECT n_combinations, ann_factor FROM backtest_runs WHERE id = :run_id'
        ),
        {'run_id': run_id},
    ).fetchone()
    if run_row is None:
        raise ValueError(
            f'Deflated Sharpe Ratio: Lauf {run_id} existiert nicht.'
        )
    ann_factor = run_row.ann_factor
    if ann_factor is None or ann_factor <= 0:
        raise ValueError(
            f'Deflated Sharpe Ratio: Lauf {run_id} trägt keinen gültigen '
            f'Annualisierungsfaktor (ann_factor={ann_factor!r}). Ohne ihn lässt sich '
            f'der nicht annualisierte Sharpe nicht rekonstruieren.'
        )

    rows = conn.execute(
        text(
            'SELECT id, sharpe_ratio, skew, kurtosis, bar_count '
            'FROM backtest_results WHERE run_id = :run_id ORDER BY id'
        ),
        {'run_id': run_id},
    ).fetchall()
    if not rows:
        return 0

    def _as_float(value) -> float:
        """NULL wird zu NaN, damit es durch die Rechnung propagiert."""
        return np.nan if value is None else float(value)

    # Rückrechnung auf den Sharpe je Balken (siehe Docstring).
    sharpe_per_bar = np.array(
        [_as_float(r.sharpe_ratio) for r in rows], dtype='float64'
    ) / np.sqrt(float(ann_factor))

    dsr_values = deflated_sharpe_ratio(
        sharpe=sharpe_per_bar,
        skew=np.array([_as_float(r.skew) for r in rows], dtype='float64'),
        kurtosis=np.array([_as_float(r.kurtosis) for r in rows], dtype='float64'),
        n=int(run_row.n_combinations),
        t=np.array([_as_float(r.bar_count) for r in rows], dtype='float64'),
    )

    payload = [
        {'result_id': row.id, 'dsr': _safe_float(value)}
        for row, value in zip(rows, dsr_values)
    ]
    update_stmt = text(
        'UPDATE backtest_results SET deflated_sharpe_ratio = :dsr WHERE id = :result_id'
    )
    batch_size = 5000
    for i in range(0, len(payload), batch_size):
        conn.execute(update_stmt, payload[i:i + batch_size])
    return len(payload)


def _count_combinations(indicators_config: dict) -> int:
    """Vorab-Schätzung der Parameterkombinationen für einen neuen Run.

    Delegiert an die einzige Zähl-Wahrheit count_total_combos (Indikator-Kombis x
    Stop-Kombis, Listen und gekoppeltes TSL-Paar inklusive) — exakt die Zahl, die
    nach dem Lauf als len(columns) persistiert wird. Lokaler Import, damit das
    DB-Repository ohne vectorbtpro importierbar bleibt (count_total_combos wird nur
    im Run-Kontext aufgerufen, wo vbt verfügbar ist).

    Args:
        indicators_config: Indikator-Konfiguration mit Ranges/Listen (+ optional '_stops')

    Returns:
        Anzahl Kombinationen (mindestens 1)
    """
    from user_data.strategies.generic.indicator_factory import count_total_combos
    return count_total_combos(indicators_config)


def create_backtest_run(
    backtest_config: dict,
    indicators_config: dict,
    parent_run_id: Optional[int] = None,
    parent_result_id: Optional[int] = None,
    selection_metric: Optional[str] = None,
    spec_runner_version: Optional[str] = None,
    testset_run_id: Optional[int] = None,
    iteration_id: Optional[int] = None,
    backtest_config_id: Optional[int] = None,
    indicator_config_id: Optional[int] = None,
) -> int:
    """Erstellt einen neuen BacktestRun mit status='queued'.

    Wird VOR der Strategie-Ausführung aufgerufen, damit der Run
    sofort in der UI sichtbar ist. Der Worker setzt den Status auf 'running'
    wenn der Job tatsächlich startet.

    Args:
        backtest_config: Backtest-Konfiguration (enthält strategy_family, strategy_name,
                         symbols, exchange, timeframe, start, end). Optionaler Key
                         'metrics' (Ticket 68): Stufenname ('kern'/'voll'/'auto'), eine
                         Liste zusätzlich gewünschter Gruppen-Keys, oder fehlend (= 'auto').
                         Wird hier zur konkreten Gruppenmenge aufgelöst und als
                         'metrics_resolved' in den gespeicherten backtest_config_json
                         geschrieben — Runner und Persistenz lesen nur noch dieses Feld.
        indicators_config: Indikator-Konfiguration
        parent_run_id: Optionale Parent-Run-ID für Walk-Forward Verkettung
        parent_result_id: Optionale Result-ID die die Config geliefert hat
        selection_metric: Metrik nach der das Parent-Result ausgewählt wurde
        spec_runner_version: Versionsnummer des spec_runner-Moduls (Ticket 01)
        testset_run_id: Optionale TestSet-Run-ID (Ticket 04) — NULL bei Einzelstarts
        iteration_id: Optionale Iteration-ID (Ticket 10) — kein Auto-Lookup, kein
                      Fallback (Ticket 83): wer einen Run startet, muss sie explizit
                      mitgeben, sonst bleibt der Run ohne Iteration.
        backtest_config_id: Optionale Herkunfts-Referenz auf die gespeicherte BacktestConfig
        indicator_config_id: Optionale Herkunfts-Referenz auf die gespeicherte IndicatorConfig

    Returns:
        int: Die neue Run-ID
    """
    n_combinations = _count_combinations(indicators_config)

    # iteration_id wird vom Aufrufer explizit mitgegeben (Playground, Start-Run, Testset).
    # Kein Auto-Lookup, kein Fallback — wer einen Run startet, wählt die Iteration.

    # GEÄNDERT: Ticket 68 — Metrik-Auswahl wird HIER, ein einziges Mal, aufgelöst: das ist
    # die Stelle, an der n_combinations für Einzel- und Multiparameterlauf exakt dieselbe
    # Zahl ist wie später backtest_runs.n_combinations. Runner, Chunks und Persistenz lesen
    # danach nur noch 'metrics_resolved' — nie mehr die Rohangabe 'auto'. Ein zweiter
    # Auflösungsort (z.B. je Chunk) käme dort auf die kleinere Chunk-Größe statt der
    # Gesamtzahl und würde Einzel- und Multiparameterlauf auseinanderlaufen lassen.
    _raw_metrics_selection = backtest_config.get('metrics')
    _resolved_metric_groups = resolve_metric_groups(
        _raw_metrics_selection, n_combinations=n_combinations
    )
    backtest_config = {
        **backtest_config,
        'metrics_resolved': sorted(_resolved_metric_groups),
    }
    # GEÄNDERT: 'metrics_auto_note' explizit entfernen, BEVOR sie ggf. neu gesetzt wird.
    # Walk-Forward und Leaderboard-Promotion-Reruns kopieren backtest_config_json des
    # Eltern-Runs 1:1 (siehe api_backtest.py:start_walk_forward) — trug der Eltern-Run
    # eine Kürzungs-Notiz, aber der neue Lauf liegt diesmal unter der Schwelle, bliebe
    # sonst eine veraltete Notiz stehen, obwohl gar nicht gekürzt wurde.
    backtest_config.pop('metrics_auto_note', None)
    # Selbstauskunft (Ticket 60/68): nur wenn 'auto' selbst gekürzt hat — bei expliziter
    # Auswahl bleibt usability_note frei für echte Warnungen (worker_tasks liest dieses
    # Feld nach dem Lauf und hängt es an die Note an).
    if (
        _raw_metrics_selection in (None, STAGE_AUTO)
        and _resolved_metric_groups != ALL_GROUPS
    ):
        _skipped = ', '.join(skipped_fields(_resolved_metric_groups))
        backtest_config['metrics_auto_note'] = (
            f"Metrik-Auswahl auto: {n_combinations} Kombinationen ≥ Schwelle "
            f"{metric_sets.AUTO_FULL_COMBINATION_THRESHOLD} — nur Kern-Gruppen "
            f"gerechnet, tail_risk übersprungen ({_skipped})."
        )

    engine = get_engine()
    with engine.begin() as conn:
        run_stmt = insert(BacktestRun).values(
            strategy_family=backtest_config['strategy_family'],
            strategy_name=backtest_config['strategy_name'],
            symbol=backtest_config['symbols'][0],
            exchange=backtest_config['exchange'],
            timeframe=backtest_config['timeframe'],
            start_date=datetime.strptime(backtest_config['start'], '%Y-%m-%d'),
            end_date=datetime.strptime(backtest_config['end'], '%Y-%m-%d'),
            # GEÄNDERT: Ticket 15 — _json-Suffix
            backtest_config_json=backtest_config,
            indicators_config_json=indicators_config,
            n_combinations=n_combinations,
            status='queued',
            parent_run_id=parent_run_id,
            parent_result_id=parent_result_id,
            selection_metric=selection_metric,
            # GEÄNDERT: Spec-Runner-Version mitschreiben (Ticket 01)
            spec_runner_version=spec_runner_version,
            # GEÄNDERT: TestSet-Run-Zuordnung (Ticket 04)
            testset_run_id=testset_run_id,
            # GEÄNDERT: Ticket 10 — Iterations-FK
            iteration_id=iteration_id,
            # GEÄNDERT: Herkunfts-Referenzen auf gespeicherte Configs (lose, kein FK)
            backtest_config_id=backtest_config_id,
            indicator_config_id=indicator_config_id,
        ).returning(BacktestRun.id)
        result = conn.execute(run_stmt)
        run_id = result.scalar()

    print(f"[DB] BacktestRun {run_id} angelegt (status=queued, {n_combinations} Kombinationen, parent_run={parent_run_id}, iteration_id={iteration_id})")
    return run_id


def update_backtest_run_status(
    run_id: int,
    status: str,
    error_message: Optional[str] = None,
    n_combinations: Optional[int] = None,
) -> None:
    """Aktualisiert den Status eines BacktestRun.

    Args:
        run_id: ID des Runs
        status: Neuer Status ('completed' oder 'failed')
        error_message: Fehlermeldung bei status='failed'
        n_combinations: Anzahl der Kombinationen (optional aktualisieren)
    """
    engine = get_engine()
    values: dict = {'status': status}
    # GEÄNDERT: Verarbeitungsstart festhalten — Moment, in dem der Worker den Run
    # aufgreift. Grundlage für die echte Rechendauer (ohne Queue-Wartezeit).
    if status == 'running':
        values['started_at'] = datetime.now()
    if status in ('completed', 'failed'):
        values['completed_at'] = datetime.now()
    if error_message:
        values['error_message'] = error_message[:2000]
    if n_combinations is not None:
        values['n_combinations'] = n_combinations

    with engine.begin() as conn:
        conn.execute(
            BacktestRun.__table__.update()
            .where(BacktestRun.id == run_id)
            .values(**values)
        )


def update_backtest_run_progress(
    run_id: int,
    current_chunk: int,
    total_chunks: int,
) -> None:
    """Schreibt den Chunk-Fortschritt eines laufenden Runs (ein UPDATE pro Chunk).

    Bewusst schlank gehalten und vom Status entkoppelt: wird vom Spec-Runner per
    Callback einmal je Chunk aufgerufen, damit das Frontend "Chunk X/Y" anzeigen kann.

    Args:
        run_id: ID des Runs
        current_chunk: 1-basierter Index des aktuell bearbeiteten Chunks
        total_chunks: Gesamtzahl der Chunks
    """
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            BacktestRun.__table__.update()
            .where(BacktestRun.id == run_id)
            .values(current_chunk=current_chunk, total_chunks=total_chunks)
        )


def update_backtest_run_warmup(run_id: int, warmup: dict) -> None:
    """Schreibt das Ergebnis der Vorlauf-Prüfung an den Run.

    Erwartet die Rückgabe von ``warmup.check_warmup``. Der Wert wird beim Run-Start
    hinterlegt, damit er ohne JSON-Auspacken abfragbar ist.

    Args:
        run_id: ID des Runs.
        warmup: Dict mit 'warmup_bars', 'required_bars' und 'note'.
    """
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            BacktestRun.__table__.update()
            .where(BacktestRun.id == run_id)
            .values(
                warmup_bars=warmup['warmup_bars'],
                warmup_required_bars=warmup['required_bars'],
                warmup_note=warmup['note'],
            )
        )


def update_backtest_run_usability(run_id: int, usability: str, note: str) -> None:
    """Kennzeichnet, ob ein Lauf verwertbar ist, samt lesbarem Grund.

    Ausdrücklich nur eine Kennzeichnung: Results eines nicht verwertbaren Laufs bleiben
    vollständig erhalten und sichtbar — ein Null-Trade-Ergebnis behält seinen
    Informationswert.

    Args:
        run_id: ID des Runs.
        usability: 'usable', 'no_signals' oder 'insufficient_history'.
        note: Lesbarer Grund (deutscher Satz).
    """
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            BacktestRun.__table__.update()
            .where(BacktestRun.id == run_id)
            .values(usability=usability, usability_note=note)
        )


def assess_run_usability(
    run_id: int,
    warmup: Optional[dict] = None,
    metrics_note: Optional[str] = None,
) -> dict:
    """Bewertet nach dem Lauf, ob er verwertbar ist, und schreibt das Urteil an den Run.

    Ein Lauf ist nicht verwertbar, wenn schon die Historie für die konfigurierten
    Indikatoren nicht reichte ('insufficient_history') oder wenn keine einzige
    Kombination einen Trade erzeugt hat ('no_signals'). Beides wird gekennzeichnet, nicht
    verworfen — die Results bleiben unangetastet.

    Args:
        run_id: ID des abgeschlossenen Runs.
        warmup: Rückgabe von ``check_warmup`` aus dem Run-Start. Ist sie
            'insufficient_history', hat dieser Grund Vorrang vor 'no_signals', weil er
            die Ursache benennt statt nur die Folge.
        metrics_note: Selbstauskunft der 'auto'-Metrik-Auswahl (Ticket 68), wenn sie den
            Lauf gekürzt hat (`backtest_config_json['metrics_auto_note']`). Wird an die
            sonst berechnete Note angehängt, nicht anstelle von ihr geschrieben — bei
            expliziter Auswahl bleibt dieser Parameter None, und usability_note trägt
            ausschließlich die Verwertbarkeits-Bewertung.

    Returns:
        Dict mit 'usability', 'note', 'n_results' und 'total_trades'.
    """
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text(
                'SELECT count(*) AS n_results, '
                'coalesce(sum(total_trades), 0) AS total_trades '
                'FROM backtest_results WHERE run_id = :run_id'
            ),
            {'run_id': run_id},
        ).fetchone()
    n_results = int(row.n_results or 0)
    total_trades = int(row.total_trades or 0)

    if warmup is not None and warmup.get('level') == 'insufficient_history':
        usability = 'insufficient_history'
        note = (
            f"{warmup['note']} Ergebnis: {n_results} Kombinationen, "
            f'{total_trades} Trades insgesamt.'
        )
    elif total_trades == 0:
        usability = 'no_signals'
        note = (
            f'Keine der {n_results} Kombinationen hat einen Trade erzeugt — der Lauf '
            f'trägt keine Kennzahlen, an denen sich die Regeln messen lassen. Die '
            f'Results bleiben erhalten: dass die Regeln nie auslösen, ist selbst ein '
            f'Befund.'
        )
    else:
        usability = 'usable'
        note = f'Verwertbar: {n_results} Kombinationen, {total_trades} Trades insgesamt.'

    # GEÄNDERT: Ticket 68 — Selbstauskunft der 'auto'-Metrik-Kürzung wird angehängt, nicht
    # die obige Note ersetzt.
    if metrics_note:
        note = f'{note} {metrics_note}'

    update_backtest_run_usability(run_id, usability, note)
    return {
        'usability': usability,
        'note': note,
        'n_results': n_results,
        'total_trades': total_trades,
    }


def _build_full_config_snapshot(
    backtest_config: dict,
    indicators_config: dict,
    actual_params: dict,
    rules: dict,
) -> dict:
    """Baut den vollständigen Config-Snapshot für ein einzelnes Result.

    Enthält alle drei Teile, die für eine bit-genaue Reproduktion nötig sind:
    - backtest_config: Symbol, Exchange, Zeitraum, Sizing, alle Stops, Formate
    - indicators: aufgelöste Indikator-Config als Dict (Key=Name, feste Werte)
    - rules: {entry, exit} aus der Strategie-Spec

    Args:
        backtest_config: Backtest-Konfiguration aus dem Run (backtest_config_json)
        indicators_config: Indikator-Config mit Ranges (indicators_config_json)
        actual_params: Konkrete Parameterwerte dieses Results
        rules: Regeln {entry, exit} aus der Strategie-Spec

    Returns:
        dict mit Schlüsseln 'backtest_config', 'indicators', 'rules'
    """
    # Portfolio-Felder können verschachtelt unter 'portfolio' liegen (Playground)
    # oder flach auf oberster Ebene (Worker/BacktestConfig aus DB).
    # Beide Strukturen werden unterstützt — flache Felder haben Vorrang.
    _portfolio = backtest_config.get('portfolio') or {}

    def _bc(key: str):
        """Liest Feld erst von oberster Ebene, dann aus 'portfolio'-Block."""
        val = backtest_config.get(key)
        if val is None:
            val = _portfolio.get(key)
        return val

    # GEÄNDERT: Schritt 3d — Die Stops und ihre Formate (delta_format/
    # time_delta_format) gehören jetzt zu '_stops' (Eigentümer IndicatorConfig),
    # nicht mehr zur BacktestConfig. Muss VOR _stop() gebunden sein, da _stop()
    # daraus liest.
    _stops_cfg = indicators_config.get('_stops') or {}

    # GEÄNDERT: Schritt 4c-pre — skalare Stops aus _stops statt backtest_config.
    # Wird ein Stop als Sweep-Achse gefahren, erscheint sein konkreter Wert als
    # MultiIndex-Level in actual_params (Level-Name = vbt.Param-Name, z.B. 'sl_stop').
    # Dieser per-Result-Wert hat Vorrang. Andernfalls gilt der SKALARE Wert aus
    # '_stops'. Kein Rückgriff mehr auf backtest_config (toter Pfad nach dem
    # Stop-Umbau, Eigentümerschaft liegt bei der IndicatorConfig).
    def _stop(key: str):
        """Per-Result-Stop: actual_params (Sweep) vor Skalar aus _stops."""
        if key in actual_params:
            return _safe_json_value(actual_params[key])
        sval = _stops_cfg.get(key)
        # Range-Dicts erscheinen bei Sweep in actual_params; ein hier verbliebenes
        # dict ist kein skalarer Stop-Wert und gilt als nicht gesetzt.
        if isinstance(sval, dict):
            return None
        return _safe_json_value(sval)

    # Backtest-Config-Felder die für Reproduktion zwingend benötigt werden
    _symbols = backtest_config.get('symbols')
    bc_snapshot = {
        'symbol': _symbols[0] if isinstance(_symbols, list) and _symbols else backtest_config.get('symbol'),
        'exchange': _bc('exchange'),
        'timeframe': _bc('timeframe'),
        'start': _bc('start'),
        'end': _bc('end'),
        'ohlc_start': _bc('ohlc_start'),
        'ohlc_end': _bc('ohlc_end'),
        'size': _bc('size'),
        'size_type': _bc('size_type'),
        'init_cash': _bc('init_cash'),
        'fees': _bc('fees'),
        # GEÄNDERT: Ticket 59 — die drei Portfolio-Parameter mit einfrieren, damit ein
        # Result selbst-reproduzierbar bleibt. Bei Alt-Runs, deren portfolio-Block die
        # Keys nicht trug, steht hier None = "nicht gesetzt" (nicht 0).
        'slippage': _bc('slippage'),
        'stop_exit_price': _bc('stop_exit_price'),
        'stop_order_type': _bc('stop_order_type'),
        'td_stop': _stop('td_stop'),
        'tp_stop': _stop('tp_stop'),
        'sl_stop': _stop('sl_stop'),
        'tsl_stop': _stop('tsl_stop'),
        'tsl_th': _stop('tsl_th'),
        'delta_format': _stops_cfg.get('delta_format'),
        'time_delta_format': _stops_cfg.get('time_delta_format'),
    }

    # Aufgelöste Indikator-Config (feste Werte statt Ranges)
    resolved_indicators = _build_resolved_config(indicators_config, actual_params)

    return {
        'backtest_config': bc_snapshot,
        'indicators': resolved_indicators,
        'rules': rules,
    }


def _build_resolved_config(indicators_config: dict, actual_params: dict) -> dict:
    """Erstellt eine aufgelöste Indicator-Config mit festen Werten statt Ranges.

    Nimmt die Struktur der indicators_config (tf, indicator, enabled, etc.)
    und ersetzt Range-Parameter durch die konkreten Werte aus actual_params.

    Args:
        indicators_config: Indicator-Config des Runs (mit Ranges)
        actual_params: Flache Parameter des Results (z.B. fastsma_length: 16)

    Returns:
        dict: Gleiche Struktur wie indicators_config aber mit festen Werten
    """
    import copy
    # GEÄNDERT: Schritt 1 — Meta-Keys ('_'-Präfix, z.B. '_stops') gehören nicht in den
    # aufgelösten Indikator-Block. Die Stops liegen im backtest_config-Block des Snapshots.
    resolved = copy.deepcopy({k: v for k, v in indicators_config.items() if not k.startswith('_')})

    for config_key, config_val in resolved.items():
        if not isinstance(config_val, dict):
            continue
        # GEÄNDERT: Level-Präfix der param_product-Columns = vbt-Klassenname,
        # also der Namespace-Teil NACH 'custom:'/'vbt:', kleingeschrieben. Die
        # actual_params-Keys heißen z.B. 'fastsma_length' bzw. 'supertrend_period'
        # — NICHT 'custom:fastsma_length'. Früher wurde der volle Typ-String
        # ('custom:fastSMA') als Präfix genutzt, wodurch nie ein Param matchte und
        # der Recompute den vollen Sweep statt der Einzel-Kombination rechnete.
        # GEÄNDERT: Zweites Präfix-Schema — _uniquify_param_levels (rules_engine)
        # benennt Param-Level auf '<spec_key>_<param>' um (z.B. 'vwma_length' bei
        # Spec-Key 'vwma' und Klasse dwsVWMA). Ohne dieses Präfix blieben Ranges
        # solcher Indikatoren unaufgelöst im Snapshot stehen.
        indicator_type = config_val.get('indicator', config_key)
        short_name = indicator_type.split(':', 1)[1] if ':' in indicator_type else indicator_type
        prefixes = [short_name.lower() + '_', config_key.lower() + '_']

        for param_key, param_val in config_val.items():
            if not isinstance(param_val, dict) or 'start' not in param_val:
                continue
            # Exakter Match: prefix + param_key (beide Präfix-Schemata)
            matched_value = None
            for prefix in prefixes:
                matched_value = actual_params.get(prefix + param_key.lower())
                if matched_value is not None:
                    break

            # Kein exakter Match: Prefix-basiert suchen (Abkürzungen)
            if matched_value is None:
                for prefix in prefixes:
                    for ap_key, ap_val in actual_params.items():
                        if not ap_key.lower().startswith(prefix):
                            continue
                        ap_suffix = ap_key.lower()[len(prefix):]
                        if ap_suffix.startswith(param_key.lower()) or param_key.lower().startswith(ap_suffix):
                            matched_value = ap_val
                            break
                    if matched_value is not None:
                        break

            if matched_value is not None:
                # GEÄNDERT: Ticket 18 — Skalar statt Pseudo-Range schreiben, dtype-Erhaltung
                dtype = param_val.get('dtype', 'float64')
                if 'int' in dtype:
                    resolved[config_key][param_key] = int(matched_value)
                else:
                    resolved[config_key][param_key] = float(matched_value)

    return resolved


def _load_run_context(conn, run_id: int, backtest_config: Optional[dict]) -> tuple:
    """Liest die Lauf-Zeile und liefert den Kontext fürs Schreiben der Results.

    Args:
        conn: Offene SQLAlchemy-Verbindung.
        run_id: ID des Laufs.
        backtest_config: Backtest-Konfiguration des Aufrufers. Hat Vorrang vor der
            am Lauf gespeicherten; None nimmt die des Laufs.

    Returns:
        Tupel (indicators_config, iteration_id, snapshot_backtest_config).
    """
    run_row = conn.execute(
        BacktestRun.__table__.select().where(BacktestRun.id == run_id)
    ).fetchone()
    # GEÄNDERT: Ticket 15 — _json-Suffix
    run_indicators_config = run_row.indicators_config_json if run_row else {}
    # Ticket 10 — iteration_id aus Run konsistent in Results übernehmen
    run_iteration_id = run_row.iteration_id if run_row else None
    # GEÄNDERT: Ticket 41 — backtest_config für Snapshot: Parameter hat Vorrang, sonst aus Run
    snapshot_backtest_config = backtest_config if backtest_config is not None else (
        run_row.backtest_config_json if run_row else {}
    )
    return run_indicators_config, run_iteration_id, snapshot_backtest_config


def _write_result_rows(
    conn,
    run_id: int,
    all_metrics: list,
    columns,
    run_indicators_config: dict,
    run_iteration_id: Optional[int],
    spec_runner_version: Optional[str],
    rules: Optional[dict],
    snapshot_backtest_config: dict,
) -> list:
    """Schreibt einen Satz Kennzahl-Zeilen samt Parametern (Upsert per params_hash).

    Einzige Schreibstelle für `backtest_results` und `backtest_result_params`. Sie
    wird sowohl vom Lauf in einem Stück als auch je Chunk eines gechunkten Laufs
    benutzt (Ticket 71) — deshalb steht hier nichts Lauf-Abschließendes: kein
    Status, kein `n_combinations`, kein Nachlauf. Der Upsert auf
    (run_id, params_hash) macht das wiederholte Schreiben desselben Chunks
    ergebnisgleich; ein fortgesetzter Lauf kann einen unterbrochenen Chunk deshalb
    gefahrlos noch einmal rechnen.

    Args:
        conn: Offene SQLAlchemy-Verbindung (Transaktion des Aufrufers).
        run_id: ID des Laufs.
        all_metrics: Fertige Kennzahl-Dicts, ein Eintrag je Spalte in `columns`.
        columns: Spalten-Index (pd.Index / MultiIndex) der Parameter-Kombinationen.
        run_indicators_config: Indikator-Konfiguration des Laufs (für resolved_config).
        run_iteration_id: Iterations-ID des Laufs (wird in jedes Result übernommen).
        spec_runner_version: Versionsnummer des Spec-Runners (Ticket 01).
        rules: Regeln der Spec; None lässt den Config-Snapshot weg (Ticket 41).
        snapshot_backtest_config: Backtest-Konfiguration für den Snapshot.

    Returns:
        Die geschriebenen Datensätze (list[dict]) in Spalten-Reihenfolge.

    Raises:
        ValueError: Wenn ein Kennzahl-Feld keiner Gruppe in metric_sets.py zugeordnet ist.
    """
    import time as _time

    # Batch aufbauen
    _t0 = _time.time()
    print("[DB] Batch aufbauen ...")
    # Parameter aus MultiIndex extrahieren (vektorisiert)
    col_names = list(columns.names) if hasattr(columns, 'names') else []
    if col_names and hasattr(columns[0], '__iter__') and not isinstance(columns[0], str):
        all_params = [
            {name: _safe_json_value(val) for name, val in zip(col_names, col)}
            for col in columns
        ]
    else:
        all_params = [{'param': str(col)} for col in columns]

    # GEÄNDERT: Ticket 68 — Persistenz-Semantik der Metrik-Auswahl. Geschrieben werden
    # immer ALLE 46 Kennzahl-Spalten; nicht gerechnete Felder ausdrücklich als NULL.
    # Damit trägt ein Result nie einen Mix aus zwei Läufen mit verschiedener Auswahl,
    # und ein Re-Run mit schmalerer Auswahl lässt keine Altwerte stehen (die
    # update_cols unten decken dieselben Spalten ab).
    _unknown_metric_fields = sorted(set(all_metrics[0]) - set(ALL_METRIC_FIELDS))
    if _unknown_metric_fields:
        raise ValueError(
            f"Kennzahl-Felder ohne Gruppe in metric_sets.py: "
            f"{', '.join(_unknown_metric_fields)}. Die Gruppen-Zuordnung ist die "
            f"einzige Quelle — neue Felder müssen dort eingetragen werden."
        )

    batch = []
    for idx in range(len(columns)):
        actual_params = all_params[idx]
        resolved = _build_resolved_config(run_indicators_config, actual_params)
        record = {
            'run_id': run_id,
            'params_hash': _make_params_hash(run_id, actual_params),
            # GEÄNDERT: Ticket 15 — _json-Suffix
            'actual_params_json': actual_params,
            'resolved_config_json': resolved,
            **{field: all_metrics[idx].get(field) for field in ALL_METRIC_FIELDS},
        }
        # GEÄNDERT: Spec-Runner-Version mitschreiben (Ticket 01)
        if spec_runner_version is not None:
            record['spec_runner_version'] = spec_runner_version
        # GEÄNDERT: Ticket 10 — iteration_id konsistent zum Run setzen
        record['iteration_id'] = run_iteration_id
        # GEÄNDERT: Ticket 41 — vollständigen Config-Snapshot schreiben (nur wenn rules vorhanden)
        if rules is not None:
            record['full_config_snapshot_json'] = _build_full_config_snapshot(
                backtest_config=snapshot_backtest_config,
                indicators_config=run_indicators_config,
                actual_params=actual_params,
                rules=rules,
            )
        batch.append(record)

    print(f"[DB] Batch aufgebaut ({_time.time() - _t0:.1f}s)")

    # Bulk-Upsert in Batches à 5000
    _t0 = _time.time()
    batch_size = 5000
    for i in range(0, len(batch), batch_size):
        chunk = batch[i:i + batch_size]
        result_stmt = insert(BacktestResult).values(chunk)
        update_cols = {col: result_stmt.excluded[col] for col in ALL_METRIC_FIELDS}
        # GEÄNDERT: Ticket 15 — _json-Suffix
        update_cols['resolved_config_json'] = result_stmt.excluded['resolved_config_json']
        # GEÄNDERT: spec_runner_version beim Upsert mitschreiben (Ticket 01)
        if spec_runner_version is not None:
            update_cols['spec_runner_version'] = result_stmt.excluded['spec_runner_version']
        # GEÄNDERT: Ticket 10 — iteration_id beim Upsert mitschreiben
        update_cols['iteration_id'] = result_stmt.excluded['iteration_id']
        # GEÄNDERT: Ticket 41 — vollständigen Config-Snapshot beim Upsert mitschreiben
        if rules is not None:
            update_cols['full_config_snapshot_json'] = result_stmt.excluded['full_config_snapshot_json']
        result_stmt = result_stmt.on_conflict_do_update(
            index_elements=['run_id', 'params_hash'],
            set_=update_cols,
        )
        conn.execute(result_stmt)
        print(f"  [DB] {min(i + batch_size, len(batch))}/{len(batch)} geschrieben")
    print(f"[DB] Results geschrieben ({_time.time() - _t0:.1f}s)")

    # Parameter in backtest_params speichern
    _t0 = _time.time()
    print("[DB] Parameter speichern ...")
    # Result-IDs der gerade geschriebenen Kombinationen holen (nach Upsert)
    # Nur id + params_hash lesen: backtest_results ist sehr breit, und diese Abfrage
    # läuft im gechunkten Lauf einmal je Chunk. Der Filter auf die gerade
    # geschriebenen Hashes (statt auf den ganzen Lauf) ist Voraussetzung fürs
    # chunkweise Schreiben — sonst zöge Chunk 2 die Results von Chunk 1 mit.
    written_hashes = [record['params_hash'] for record in batch]
    result_id_map = {}
    for i in range(0, len(written_hashes), batch_size):
        rows = conn.execute(
            select(BacktestResult.id, BacktestResult.params_hash)
            .where(BacktestResult.run_id == run_id)
            .where(BacktestResult.params_hash.in_(written_hashes[i:i + batch_size]))
        ).fetchall()
        result_id_map.update({r.params_hash: r.id for r in rows})

    # Bestehende Parameter der geschriebenen Results löschen (verhindert Duplikate
    # bei Re-Runs und beim erneuten Rechnen eines unterbrochenen Chunks)
    existing_result_ids = list(result_id_map.values())
    if existing_result_ids:
        for i in range(0, len(existing_result_ids), batch_size):
            conn.execute(
                BacktestParam.__table__.delete().where(
                    BacktestParam.result_id.in_(existing_result_ids[i:i + batch_size])
                )
            )

    params_batch = []
    for idx in range(len(columns)):
        actual_params = all_params[idx]
        rid = result_id_map.get(batch[idx]['params_hash'])
        if rid is None:
            continue
        for param_name, param_value in actual_params.items():
            if param_name == 'symbol':
                continue
            params_batch.append({
                'result_id': rid,
                'param_name': param_name,
                'param_value': _safe_float(param_value),
            })

    if params_batch:
        for i in range(0, len(params_batch), batch_size):
            conn.execute(insert(BacktestParam), params_batch[i:i + batch_size])
        print(f"  [DB] {len(params_batch)} Parameter gespeichert ({_time.time() - _t0:.1f}s)")

    return batch


def save_result_chunk(
    run_id: int,
    metrics_table: list,
    columns,
    chunk_index: int,
    ann_factor: float,
    spec_runner_version: Optional[str] = None,
    rules: Optional[dict] = None,
    backtest_config: Optional[dict] = None,
) -> int:
    """Speichert die Results EINES fertig gerechneten Chunks (Ticket 71).

    Der gechunkte Multiparameterlauf hielt seine Ergebnisse früher bis zum letzten
    Chunk im Speicher und schrieb sie erst danach — ein hart beendeter Lauf verlor
    damit seine gesamte Rechenarbeit. Jeder Chunk landet jetzt sofort in der
    Datenbank, zusammen mit dem Fortsetzungspunkt `completed_chunks` in derselben
    Transaktion: entweder sind Results UND Zähler da oder keins von beidem.

    Der Lauf wird hier ausdrücklich NICHT abgeschlossen. Status, `n_combinations`
    und die rasterweite Deflated Sharpe Ratio entstehen erst in
    `finalize_backtest_run` über den gesamten Lauf — die DSR je Chunk zu rechnen
    wäre strukturell falsch (Ticket 54).

    Args:
        run_id: ID des Laufs.
        metrics_table: Fertige Kennzahl-Dicts des Chunks (aus `_extract_metrics`).
        columns: Spalten-Index der Kombinationen dieses Chunks.
        chunk_index: 0-basierter Index des Chunks. `completed_chunks` wird auf
            `chunk_index + 1` gesetzt — die Chunks laufen strikt der Reihe nach.
        ann_factor: Annualisierungsfaktor des Laufs (aus VBT). Wird am Lauf
            hinterlegt, damit der DSR-Nachlauf ihn auch dann hat, wenn beim
            Fortsetzen kein Chunk mehr gerechnet werden muss.
        spec_runner_version: Versionsnummer des Spec-Runners (Ticket 01).
        rules: Regeln der Spec für den Config-Snapshot (Ticket 41).
        backtest_config: Backtest-Konfiguration für den Snapshot.

    Returns:
        Anzahl der geschriebenen Kombinationen.
    """
    engine = get_engine()
    with engine.begin() as conn:
        run_indicators_config, run_iteration_id, snapshot_backtest_config = (
            _load_run_context(conn, run_id, backtest_config)
        )
        _write_result_rows(
            conn=conn,
            run_id=run_id,
            all_metrics=metrics_table,
            columns=columns,
            run_indicators_config=run_indicators_config,
            run_iteration_id=run_iteration_id,
            spec_runner_version=spec_runner_version,
            rules=rules,
            snapshot_backtest_config=snapshot_backtest_config,
        )
        conn.execute(
            BacktestRun.__table__.update()
            .where(BacktestRun.id == run_id)
            .values(completed_chunks=chunk_index + 1, ann_factor=float(ann_factor))
        )
    print(
        f"[DB] Chunk {chunk_index + 1} gespeichert: {len(columns)} Kombinationen "
        f"(Run {run_id})"
    )
    return len(columns)


def _finalize_run(conn, run_id: int, ann_factor: Optional[float]) -> int:
    """Abschluss-Arbeit eines Laufs innerhalb einer bestehenden Transaktion.

    Args:
        conn: Offene SQLAlchemy-Verbindung.
        run_id: ID des Laufs.
        ann_factor: Annualisierungsfaktor oder None (dann bleibt der gespeicherte stehen).

    Returns:
        Die geschriebene Kombinationszahl.
    """
    import time as _time

    n_combinations = conn.execute(
        text('SELECT count(*) FROM backtest_results WHERE run_id = :run_id'),
        {'run_id': run_id},
    ).scalar() or 0

    values: dict = {
        'status': 'completed',
        'completed_at': datetime.now(),
        'n_combinations': n_combinations,
    }
    # GEÄNDERT: Ticket 54 — ann_factor mitschreiben. Er ist die Voraussetzung dafür,
    # dass der Nachlauf gleich darunter den Sharpe je Balken rekonstruieren kann.
    if ann_factor is not None:
        values['ann_factor'] = float(ann_factor)
    conn.execute(
        BacktestRun.__table__.update()
        .where(BacktestRun.id == run_id)
        .values(**values)
    )

    # GEÄNDERT: Ticket 54 — Nachlauf für die Deflated Sharpe Ratio. Er steht hier
    # bewusst am Ende und INNERHALB derselben Transaktion: die Results sind
    # geschrieben, n_combinations und ann_factor stehen am Lauf, und der Zustand
    # bleibt atomar.
    _t0 = _time.time()
    n_dsr = _calculate_deflated_sharpe(conn, run_id)
    print(
        f"[DB] Deflated Sharpe Ratio nachgelaufen: {n_dsr} Results, "
        f"N={n_combinations} ({_time.time() - _t0:.1f}s)"
    )
    return n_combinations


def finalize_backtest_run(
    run_id: int, ann_factor: Optional[float] = None, conn=None,
) -> int:
    """Schließt einen Lauf ab: Kombinationszahl, Annualisierungsfaktor, Status, DSR.

    Der Abschluss ist von der Result-Schreibung getrennt (Ticket 71), weil ein
    gechunkter Lauf seine Results je Chunk schreibt, aber genau einmal abgeschlossen
    wird. Die Deflated Sharpe Ratio läuft hier als Nachlauf über den gesamten Lauf
    (Ticket 54) — sie ist rasterweit und je Chunk gerechnet strukturell falsch.

    `n_combinations` kommt aus der Zahl der tatsächlich vorliegenden Results des
    Laufs. Für einen Lauf in einem Stück ist das dieselbe Zahl wie die Spaltenzahl
    des Portfolios; für einen fortgesetzten Lauf ist es die einzige Zahl, die auch
    die vor dem Abbruch geschriebenen Chunks mitzählt.

    Args:
        run_id: ID des Laufs.
        ann_factor: Annualisierungsfaktor. None lässt den am Lauf gespeicherten
            stehen — den Fall gibt es, wenn ein fortgesetzter Lauf keinen einzigen
            Chunk mehr rechnen musste.
        conn: Offene Verbindung des Aufrufers. Wird sie mitgegeben, läuft der
            Abschluss in dessen Transaktion (der Lauf in einem Stück schreibt
            Results und Abschluss atomar); None öffnet eine eigene.

    Returns:
        Die geschriebene Kombinationszahl.

    Raises:
        ValueError: Wenn der Lauf keinen gültigen Annualisierungsfaktor trägt
            (über `_calculate_deflated_sharpe`).
    """
    if conn is not None:
        return _finalize_run(conn, run_id, ann_factor)
    engine = get_engine()
    with engine.begin() as own_conn:
        return _finalize_run(own_conn, run_id, ann_factor)


def save_strategy_results(
    run_id: int,
    strategy_results: dict,
    spec_runner_version: Optional[str] = None,
    rules: Optional[dict] = None,
    backtest_config: Optional[dict] = None,
) -> int:
    """
    Speichert Backtest-Ergebnisse für einen existierenden Run in die Datenbank.

    Der Run muss vorher mit create_backtest_run() angelegt worden sein.

    Nimmt drei Ergebnis-Formen entgegen:

    * ``portfolios`` — Lauf in einem Stück: Kennzahlen werden hier extrahiert.
    * ``metrics_table`` + ``columns`` — gechunkter Lauf ohne Chunk-Senke: die
      Kennzahlen sind fertig und werden in einem Rutsch geschrieben.
    * ``chunks_saved`` — gechunkter Lauf MIT Chunk-Senke (Ticket 71): die Results
      stehen bereits in der Datenbank, hier folgt nur noch der Abschluss.

    Args:
        run_id: ID des bereits angelegten BacktestRun
        strategy_results: Return-Dict der Strategie-Funktion (enthält 'portfolios')
        spec_runner_version: Versionsnummer des spec_runner-Moduls (Ticket 01)
        rules: Regeln {entry, exit} aus der Strategie-Spec (Ticket 41 — für Snapshot)
        backtest_config: Backtest-Konfiguration (Ticket 41 — für Snapshot).
            Wird für den full_config_snapshot_json benötigt. Falls None, wird aus dem Run geladen.
            Trägt sie einen Key 'metrics_resolved' (Ticket 68, von create_backtest_run
            gesetzt), bestimmt der den 'portfolios'-Pfad (nicht 'metrics_table' — der
            ist bereits fertig extrahiert): welche Kennzahl-Gruppen _extract_metrics
            rechnet. Fehlt der Key, rechnet _extract_metrics wie vor diesem Ticket alles.

    Returns:
        int: Anzahl der Parameter-Kombinationen
    """
    # GEÄNDERT: Ticket 71 — Der gechunkte Lauf mit Chunk-Senke hat seine Results schon
    # während der Rechnung geschrieben (save_result_chunk). Hier bleibt nur der
    # Abschluss über den ganzen Lauf: Status, Kombinationszahl und der rasterweite
    # DSR-Nachlauf. Genau dieselbe Abschluss-Funktion nutzt der Lauf in einem Stück.
    if 'chunks_saved' in strategy_results:
        n_combinations = finalize_backtest_run(
            run_id, strategy_results.get('ann_factor')
        )
        print(
            f"[DB] BacktestRun {run_id} abgeschlossen, {n_combinations} Kombinationen "
            f"(chunkweise gespeichert)"
        )
        return n_combinations

    # GEÄNDERT: Ticket 44 — Chunked-Pfad: metrics_table + columns statt portfolios.
    # Der spec_runner liefert dieses Format, wenn der Grid in Chunks aufgeteilt wurde.
    # Die Metriken sind bereits fertig extrahiert — kein _extract_metrics nötig.
    if 'metrics_table' in strategy_results:
        all_metrics = strategy_results['metrics_table']   # list[dict]
        columns = strategy_results['columns']              # pd.Index / MultiIndex
        n_combinations = len(columns)
        if n_combinations == 0:
            raise ValueError(
                "Keine Parameter-Kombinationen im Chunked-Ergebnis (leere columns) — "
                "vermutlich fehlende oder leere OHLCV-Daten für den gewählten Zeitraum. "
                "Run kann nicht gespeichert werden."
            )
        portfolios = None  # nicht verfügbar im Chunked-Pfad
        # GEÄNDERT: Ticket 54 — im gechunkten Pfad gibt es kein Portfolio mehr, aus dem
        # sich der Annualisierungsfaktor holen ließe. Der Spec-Runner liefert ihn
        # deshalb im Ergebnis-Dict mit; er stammt auch dort aus VBT selbst
        # (ReturnsAccessor.ann_factor) und wird nirgends nachgebaut.
        ann_factor = float(strategy_results['ann_factor'])
    else:
        portfolios = strategy_results['portfolios']
        columns = portfolios.wrapper.columns
        n_combinations = len(columns)

        # GEÄNDERT: Audit-Fund — 0 Kombinationen = Fehlzustand sichtbar abweisen.
        # Ein leeres Portfolio (keine Spalten) entsteht, wenn keine OHLCV-Daten geladen
        # wurden (fehlendes Symbol oder leerer Zeitbereich). Ohne diesen Guard liefe der
        # Code in einen kryptischen IndexError (all_metrics[0] auf leerer Liste), und der
        # Backtest-Run würde je nach Aufrufer still als 'completed' gewertet. Stattdessen
        # eine klare Fehlermeldung — der aufrufende Job markiert den Run dann als 'failed'.
        if n_combinations == 0:
            raise ValueError(
                "Keine Parameter-Kombinationen im Portfolio (leere Spalten) — vermutlich "
                "fehlende oder leere OHLCV-Daten für den gewählten Zeitraum. "
                "Run kann nicht gespeichert werden."
            )

        # GEÄNDERT: Ticket 54 — Annualisierungsfaktor aus dem Portfolio, also genau der
        # Wert, den VBT für den annualisierten Sharpe benutzt. Er hängt nur an
        # Jahres- und Balkenfrequenz, der spätere Zuschnitt auf das Handelsfenster
        # ändert ihn nicht.
        ann_factor = float(portfolios.returns_acc.ann_factor)

        # Metriken werden weiter unten extrahiert (nach engine.begin())
        all_metrics = None

    engine = get_engine()
    import time as _time
    _t_start = _time.time()
    print(f"[DB] {n_combinations} Kombinationen in strategy_results")

    with engine.begin() as conn:

        # Indicators-Config und iteration_id des Runs laden für resolved_config
        # GEÄNDERT: Ticket 58 — der Run-Datensatz wird jetzt VOR der Metrik-Extraktion
        # geladen, weil _snapshot_backtest_config das Handelsfenster (start/end) für den
        # Portfolio-Zuschnitt liefert.
        run_row = conn.execute(
            BacktestRun.__table__.select().where(BacktestRun.id == run_id)
        ).fetchone()
        # GEÄNDERT: Ticket 15 — _json-Suffix
        run_indicators_config = run_row.indicators_config_json if run_row else {}
        # Ticket 10 — iteration_id aus Run konsistent in Results übernehmen
        run_iteration_id = run_row.iteration_id if run_row else None
        # GEÄNDERT: Ticket 41 — backtest_config für Snapshot: Parameter hat Vorrang, sonst aus Run
        _snapshot_backtest_config = backtest_config if backtest_config is not None else (
            run_row.backtest_config_json if run_row else {}
        )

        # Metriken extrahieren (nur im Original-Pfad — im Chunked-Pfad bereits fertig)
        if portfolios is not None:
            # GEÄNDERT: Ticket 64 — keine Verzweigung nach Kombinationszahl mehr. Ein Lauf
            # mit einer Kombination und ein Lauf mit vielen gehen durch denselben Code und
            # liefern denselben Satz Kennzahlen.
            _t0 = _time.time()
            print("[DB] Metriken extrahieren ...")
            # GEÄNDERT: Ticket 68 — 'metrics_resolved' kommt aus create_backtest_run
            # (einzige Auflösungsstelle). Fehlt der Key (Aufrufer außerhalb des
            # Run-Start-Wegs, z.B. Direktaufrufe in Tests), rechnet _extract_metrics
            # wie vor diesem Ticket alles — kein Regress für Bestandsaufrufer.
            all_metrics = _extract_metrics(
                portfolios, columns, _snapshot_backtest_config,
                groups=_snapshot_backtest_config.get('metrics_resolved'),
            )
            print(f"[DB] Metriken extrahiert ({_time.time() - _t0:.1f}s)")

            # Zeitreihen bleiben getrennt (Ticket 64, ausdrücklich nicht angefasst): sie
            # skalieren mit Kombinationen x Balken und entstehen nur beim Einzellauf.
            if n_combinations == 1:
                pf = portfolios[columns[0]]
                trades_records = pf.trades.records_readable
                orders_records = pf.orders.records_readable
                positions_records = pf.positions.records_readable
        else:
            # Chunked-Pfad: Metriken bereits gesetzt, keine Trades/Orders/Positions
            print(f"[DB] Chunked-Pfad: {len(all_metrics)} Metriken bereits extrahiert")

        _write_result_rows(
            conn=conn,
            run_id=run_id,
            all_metrics=all_metrics,
            columns=columns,
            run_indicators_config=run_indicators_config,
            run_iteration_id=run_iteration_id,
            spec_runner_version=spec_runner_version,
            rules=rules,
            snapshot_backtest_config=_snapshot_backtest_config,
        )

        # Bei 1 Kombination: Trades und Orders speichern (nicht im Chunked-Pfad)
        if n_combinations == 1 and portfolios is not None:
            # Result-ID holen
            result_row = conn.execute(
                BacktestResult.__table__.select().where(BacktestResult.run_id == run_id)
            ).fetchone()
            result_id = result_row.id

            # Trades speichern
            if len(trades_records) > 0:
                trades_batch = []
                for _, row in trades_records.iterrows():
                    trades_batch.append({
                        'result_id': result_id,
                        'exit_trade_id': int(row['Exit Trade Id']),
                        'position_id': _safe_int(row.get('Position Id')),
                        'direction': str(row.get('Direction', 'Long')),
                        'status': str(row.get('Status', 'Closed')),
                        'size': _safe_float(row['Size']),
                        'entry_order_id': _safe_int(row.get('Entry Order Id')),
                        'entry_index': _safe_datetime(row['Entry Index']),
                        'avg_entry_price': _safe_float(row['Avg Entry Price']),
                        'entry_fees': _safe_float(row.get('Entry Fees')),
                        'exit_order_id': _safe_int(row.get('Exit Order Id')),
                        'exit_index': _safe_datetime(row.get('Exit Index')),
                        'avg_exit_price': _safe_float(row.get('Avg Exit Price')),
                        'exit_fees': _safe_float(row.get('Exit Fees')),
                        'pnl': _safe_float(row.get('PnL')),
                        'return_pct': _safe_float(row.get('Return', 0) * 100),
                    })
                conn.execute(insert(BacktestTrade), trades_batch)
                print(f"  [DB] {len(trades_batch)} Trades gespeichert")

            # Orders speichern
            if len(orders_records) > 0:
                orders_batch = []
                for _, row in orders_records.iterrows():
                    stop_type = str(row.get('Stop Type', ''))
                    orders_batch.append({
                        'result_id': result_id,
                        'order_id': int(row['Order Id']),
                        'signal_index': _safe_datetime(row.get('Signal Index')),
                        'creation_index': _safe_datetime(row.get('Creation Index')),
                        'fill_index': _safe_datetime(row.get('Fill Index')),
                        'size': _safe_float(row['Size']),
                        'price': _safe_float(row['Price']),
                        'fees': _safe_float(row.get('Fees')),
                        'side': str(row['Side']),
                        'type': str(row.get('Type', '')) or None,
                        'stop_type': stop_type if stop_type and stop_type != 'None' else None,
                    })
                conn.execute(insert(BacktestOrder), orders_batch)
                print(f"  [DB] {len(orders_batch)} Orders gespeichert")

            # Positions speichern
            if len(positions_records) > 0:
                positions_batch = []
                for _, row in positions_records.iterrows():
                    positions_batch.append({
                        'result_id': result_id,
                        'position_id': int(row['Position Id']),
                        'direction': str(row.get('Direction', 'Long')),
                        'status': str(row.get('Status', 'Closed')),
                        'size': _safe_float(row['Size']),
                        'entry_order_id': _safe_int(row.get('Entry Order Id')),
                        'entry_index': _safe_datetime(row['Entry Index']),
                        'avg_entry_price': _safe_float(row['Avg Entry Price']),
                        'entry_fees': _safe_float(row.get('Entry Fees')),
                        'exit_order_id': _safe_int(row.get('Exit Order Id')),
                        'exit_index': _safe_datetime(row.get('Exit Index')),
                        'avg_exit_price': _safe_float(row.get('Avg Exit Price')),
                        'exit_fees': _safe_float(row.get('Exit Fees')),
                        'pnl': _safe_float(row.get('PnL')),
                        'return_pct': _safe_float(row.get('Return', 0) * 100),
                    })
                conn.execute(insert(BacktestPosition), positions_batch)
                print(f"  [DB] {len(positions_batch)} Positions gespeichert")

            # Equity-Kurve speichern
            equity_series = pf.value
            equity_batch = []
            for ts, val in equity_series.items():
                safe_val = _safe_float(val)
                if safe_val is not None:
                    equity_batch.append({
                        'result_id': result_id,
                        'timestamp': _safe_datetime(ts),
                        'value': safe_val,
                    })
            if equity_batch:
                batch_size = 2000
                for i in range(0, len(equity_batch), batch_size):
                    chunk = equity_batch[i:i + batch_size]
                    conn.execute(insert(BacktestEquity), chunk)
                print(f"  [DB] {len(equity_batch)} Equity-Werte gespeichert")

            # Indikatoren speichern
            indicators_results = strategy_results.get('indicators_results', {})
            indicators_batch = []
            for ind_name, ind_data in indicators_results.items():
                data_obj = ind_data.get('data')
                if data_obj is None:
                    continue

                # Output-Namen ermitteln (z.B. ['result'] oder ['trend', 'direction', 'long', 'short']).
                # GEÄNDERT: M7 — kein stilles Raten von ['result'] mehr. Ein Datenobjekt ohne
                # output_names ist ein unbekanntes Format; in einer Trading-Software werden solche
                # Unbekannten nicht stillschweigend halb gespeichert. Stattdessen harter Abbruch:
                # die Transaktion rollt zurück, der aufrufende Job markiert den Run als 'failed'
                # mit dieser Meldung (sichtbar in der Runs-Liste).
                output_names = getattr(data_obj, 'output_names', None)
                if not output_names:
                    raise ValueError(
                        f"Indikator '{ind_name}': Datenobjekt vom Typ '{type(data_obj).__name__}' "
                        f"hat keine 'output_names' — die Output-Kanäle sind nicht bestimmbar. "
                        f"Run wird abgebrochen, um keine unvollständigen Indikator-Daten zu speichern."
                    )

                for output_name in output_names:
                    series = getattr(data_obj, output_name, None)
                    if series is None:
                        continue
                    # Bei MultiIndex-Columns die erste Spalte nehmen (n_combinations == 1)
                    if hasattr(series, 'columns'):
                        series = series.iloc[:, 0]
                    for ts, val in series.items():
                        safe_val = _safe_float(val)
                        if safe_val is not None:
                            indicators_batch.append({
                                'result_id': result_id,
                                'indicator_name': ind_name,
                                'indicator_output': output_name,
                                'timestamp': _safe_datetime(ts),
                                'value': safe_val,
                            })

            if indicators_batch:
                batch_size = 2000
                for i in range(0, len(indicators_batch), batch_size):
                    chunk = indicators_batch[i:i + batch_size]
                    conn.execute(insert(BacktestIndicator), chunk)
                print(f"  [DB] {len(indicators_batch)} Indikator-Werte gespeichert")

        # Run abschließen (Status, n_combinations, ann_factor und der rasterweite
        # DSR-Nachlauf) — in derselben Transaktion wie die Results, damit der Zustand
        # atomar bleibt.
        n_combinations = finalize_backtest_run(run_id, ann_factor, conn=conn)

    print(f"[DB] BacktestRun {run_id} gespeichert, {n_combinations} Kombinationen (Gesamt: {_time.time() - _t_start:.1f}s)")

    return n_combinations


# ---------------------------------------------------------------------------
# GEÄNDERT: Result-Lookup per Parameter-Werten für die Route
# GET /api/backtest/runs/{run_id}/results/lookup (exakt + Nachbarschafts-Modus).
# Liegt hier statt in api_backtest.py, damit die Query-Logik ohne die
# Container-Abhängigkeiten der Route (rq/redis) testbar ist.
# ---------------------------------------------------------------------------

def get_run_param_names(engine: Engine, run_id: int) -> List[str]:
    """Parameter-Namen eines Runs (aus einem beliebigen Result des Runs), sortiert."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT DISTINCT param_name FROM backtest_result_params
            WHERE result_id = (SELECT id FROM backtest_results WHERE run_id = :run_id LIMIT 1)
            ORDER BY param_name
        """), {'run_id': run_id}).fetchall()
    return [r.param_name for r in rows]


def _param_exists_conditions(filters: Dict[str, float], tolerances: Dict[str, float],
                             binds: dict, suffix: str = "") -> List[str]:
    """EXISTS-Bedingungen je Parameter gegen backtest_result_params (Index idx_bpa_result_param).

    tolerances liefert je Parameter die halbe Fenster-Breite (0 = exakter Lookup);
    ein winziges Epsilon fängt zusätzlich Float-Artefakte der arange-Raster ab.
    Der Suffix hält Bind-Namen und Tabellen-Alias eindeutig, wenn die Bedingungen
    mehrfach (z.B. je Run mit eigener Toleranz) in dieselbe Query eingebaut werden.
    Befüllt binds in-place.
    """
    conditions = []
    for i, (name, value) in enumerate(filters.items()):
        tol = tolerances.get(name, 0.0)
        eps = 1e-9 * max(1.0, abs(value))
        key = f"{i}{suffix}"
        binds[f'name{key}'] = name
        binds[f'lo{key}'] = value - tol - eps
        binds[f'hi{key}'] = value + tol + eps
        conditions.append(
            f"EXISTS (SELECT 1 FROM backtest_result_params p{key} "
            f"WHERE p{key}.result_id = r.id AND p{key}.param_name = :name{key} "
            f"AND p{key}.param_value BETWEEN :lo{key} AND :hi{key})"
        )
    return conditions


def get_run_param_steps(engine: Engine, run_id: int, param_names: List[str]) -> Dict[str, float]:
    """Schrittweite je Parameter = kleinster positiver Abstand der sortierten distinct-Werte des Runs.

    Grundlage für den schrittweiten Nachbarschafts-Modus (tolerance_steps): damit
    lässt sich eine echte ±N-Schritt-Nachbarschaft auch bei ungleichen
    Schrittweiten je Achse bilden (z.B. ema_fast Schritt 5, ema_slow Schritt 25).
    Parameter mit nur einem distinct-Wert (eingefrorene Achse) bekommen Schritt
    0.0 und matchen damit wie tolerance=0 exakt.
    """
    steps: Dict[str, float] = {}
    with engine.connect() as conn:
        for name in param_names:
            rows = conn.execute(text("""
                SELECT DISTINCT p.param_value AS v
                FROM backtest_result_params p
                JOIN backtest_results r ON r.id = p.result_id
                WHERE r.run_id = :run_id AND p.param_name = :name
                ORDER BY v
            """), {'run_id': run_id, 'name': name}).fetchall()
            values = [r.v for r in rows]
            gaps = [b - a for a, b in zip(values, values[1:]) if b - a > 1e-12]
            steps[name] = min(gaps) if gaps else 0.0
    return steps


def _resolve_tolerances(engine: Engine, run_id: int, filters: Dict[str, float],
                        tolerance: float, tolerance_steps) -> Dict[str, float]:
    """Baut die Toleranz je Parameter — schrittweit (aus distinct-Werten) oder skalar.

    Ist tolerance_steps gesetzt, wird die Schrittweite je Achse aus dem Run
    abgeleitet und mit N multipliziert; sonst gilt die skalare tolerance für alle.
    """
    if tolerance_steps is not None:
        step_map = get_run_param_steps(engine, run_id, list(filters.keys()))
        return {name: tolerance_steps * step_map.get(name, 0.0) for name in filters}
    return {name: (tolerance or 0.0) for name in filters}


def lookup_result_rows_by_params(engine: Engine, run_id: int, filters: Dict[str, float],
                                 tolerance: float, limit: int,
                                 tolerance_steps=None) -> Tuple[List[dict], int]:
    """Results eines Runs, deren Parameter je Nachbarschaft um die Zielwerte liegen.

    Nachbarschaft ist entweder skalar (±tolerance je Parameter) oder schrittweit
    (±tolerance_steps Raster-Schritte je Parameter, aus dem Run abgeleitet).
    Gibt (items, total) zurück; total wird nur bei vollem Limit separat gezählt.
    """
    binds: dict = {'run_id': run_id, 'lim': limit}
    tolerances = _resolve_tolerances(engine, run_id, filters, tolerance, tolerance_steps)
    conditions = _param_exists_conditions(filters, tolerances, binds)
    where = f"r.run_id = :run_id AND {' AND '.join(conditions)}"
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT id, run_id, actual_params_json, total_return_pct, sharpe_ratio,
                   sortino_ratio, max_drawdown_pct, win_rate_pct, profit_factor,
                   total_trades, open_trades, long_trades, short_trades, end_value
            FROM backtest_results r
            WHERE {where}
            ORDER BY total_return_pct DESC NULLS LAST
            LIMIT :lim
        """), binds).fetchall()
        total = len(rows)
        if total == limit:
            total = conn.execute(
                text(f"SELECT COUNT(*) FROM backtest_results r WHERE {where}"), binds
            ).scalar()
    items = [
        {
            'id': r.id,
            'run_id': r.run_id,
            'actual_params': r.actual_params_json,
            'total_return_pct': r.total_return_pct,
            'sharpe_ratio': r.sharpe_ratio,
            'sortino_ratio': r.sortino_ratio,
            'max_drawdown_pct': r.max_drawdown_pct,
            'win_rate_pct': r.win_rate_pct,
            'profit_factor': r.profit_factor,
            'total_trades': r.total_trades,
            # GEÄNDERT: Ticket 58 — Nenner der Trefferquote mitliefern.
            'open_trades': r.open_trades,
            # GEÄNDERT: Ticket 60 — Long/Short-Aufteilung mitliefern.
            'long_trades': r.long_trades,
            'short_trades': r.short_trades,
            'end_value': r.end_value,
        }
        for r in rows
    ]
    return items, total


def get_scope_param_names(engine: Engine, run_ids: List[int]) -> List[str]:
    """Parameter-Namen einer Run-Menge (aus je einem Result pro Run), sortiert."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT DISTINCT param_name FROM backtest_result_params
            WHERE result_id IN (
                SELECT MIN(id) FROM backtest_results
                WHERE run_id = ANY(:run_ids) GROUP BY run_id
            )
            ORDER BY param_name
        """), {'run_ids': list(run_ids)}).fetchall()
    return [r.param_name for r in rows]


def lookup_results_across_runs(engine: Engine, run_ids: List[int], filters: Dict[str, float],
                               tolerance: float, limit: int,
                               tolerance_steps=None) -> Tuple[List[dict], int]:
    """Kombinations-Verfolgung: Results mit passenden Parametern über mehrere Runs.

    Wie lookup_result_rows_by_params, aber über eine Run-Menge, mit Run-Kontext
    (Symbol/Timeframe) im Ergebnis, sortiert nach run_id und Total Return.
    Im Schritt-Modus wird die Schrittweite je Run einzeln abgeleitet (Raster
    können differieren) und die Zweige werden OR-verknüpft.
    Gibt (items, total) zurück; total wird nur bei vollem Limit separat gezählt.
    """
    binds: dict = {'lim': limit}
    if tolerance_steps is not None:
        branches = []
        for j, rid in enumerate(run_ids):
            tolerances = _resolve_tolerances(engine, rid, filters, None, tolerance_steps)
            conds = _param_exists_conditions(filters, tolerances, binds, suffix=f"_r{j}")
            binds[f'rid{j}'] = rid
            branches.append(f"(r.run_id = :rid{j} AND {' AND '.join(conds)})")
        where = "(" + " OR ".join(branches) + ")"
    else:
        binds['run_ids'] = list(run_ids)
        tolerances = {name: (tolerance or 0.0) for name in filters}
        conditions = _param_exists_conditions(filters, tolerances, binds)
        where = f"r.run_id = ANY(:run_ids) AND {' AND '.join(conditions)}"
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT r.id, r.run_id, br.symbol, br.timeframe, r.actual_params_json,
                   r.total_return_pct, r.sharpe_ratio, r.sortino_ratio,
                   r.max_drawdown_pct, r.win_rate_pct, r.profit_factor,
                   r.total_trades, r.open_trades, r.long_trades, r.short_trades, r.end_value
            FROM backtest_results r
            JOIN backtest_runs br ON br.id = r.run_id
            WHERE {where}
            ORDER BY r.run_id, r.total_return_pct DESC NULLS LAST
            LIMIT :lim
        """), binds).fetchall()
        total = len(rows)
        if total == limit:
            total = conn.execute(
                text(f"SELECT COUNT(*) FROM backtest_results r WHERE {where}"), binds
            ).scalar()
    items = [
        {
            'id': r.id,
            'run_id': r.run_id,
            'symbol': r.symbol,
            'timeframe': r.timeframe,
            'actual_params': r.actual_params_json,
            'total_return_pct': r.total_return_pct,
            'sharpe_ratio': r.sharpe_ratio,
            'sortino_ratio': r.sortino_ratio,
            'max_drawdown_pct': r.max_drawdown_pct,
            'win_rate_pct': r.win_rate_pct,
            'profit_factor': r.profit_factor,
            'total_trades': r.total_trades,
            # GEÄNDERT: Ticket 58 — Nenner der Trefferquote mitliefern.
            'open_trades': r.open_trades,
            # GEÄNDERT: Ticket 60 — Long/Short-Aufteilung mitliefern.
            'long_trades': r.long_trades,
            'short_trades': r.short_trades,
            'end_value': r.end_value,
        }
        for r in rows
    ]
    return items, total
