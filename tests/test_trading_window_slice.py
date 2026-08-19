"""Tests für den Kennzahlen-Zuschnitt auf das Handelsfenster.

Deckt die beiden Bausteine aus `user_data/utils/metrics/trading_window.py` ab:
die Bildung der Fenstergrenzen aus der BacktestConfig und den Zuschnitt eines
fertigen Portfolios darauf. Geprüft wird das Verhalten, das die Kennzahlen
tragen muss — Spalten überleben, das Strategie-Ergebnis bleibt unangetastet,
Buy-and-Hold-Vergleichsmaßstab und Sharpe rechnen auf dem Fenster neu, und eine
über das Fensterende laufende Position wird als offen ausgewiesen.

ergänzt: die Long/Short-Aufteilung und der
tatsächlich gerechnete Zeitraum (Balkenzahl, Start-/End-Index) je Result, sowie
die Vereinheitlichung von `expectancy`, `sqn` und `edge_ratio` auf geschlossene
Trades (dieselbe Konvention wie `win_rate_pct`/`profit_factor`).

Die Umstellung hat die drei früheren Extraktionsfunktionen zu `_extract_metrics`
zusammengeführt. Die Tests unterscheiden deshalb nicht mehr nach Rechenpfad,
sondern nach der Zahl der Spalten des Portfolios — eine Kombination gegen viele.
"""

import numpy as np
import pandas as pd
import pytest
import vectorbtpro as vbt

from user_data.utils.database.repository import _extract_metrics
from user_data.utils.metrics.trading_window import (
    build_trading_window,
    count_open_trades,
    slice_to_trading_window,
)

_START = '2020-02-01'
_END = '2020-02-20'


def _config(start: str = _START, end: str = _END) -> dict:
    """Minimale BacktestConfig mit Handelsfenster."""
    return {'start': start, 'end': end}


def _price_series(n: int = 1600) -> pd.Series:
    """Deterministische Preisreihe über n Stundenbalken ab 2020-01-01."""
    idx = pd.date_range('2020-01-01', periods=n, freq='1h', tz='UTC')
    rng = np.random.default_rng(11)
    values = 100 * np.cumprod(1 + rng.normal(0.0005, 0.01, n))
    return pd.Series(values, index=idx)


def _portfolio_with_window_entries(close: pd.Series, sweep: bool = False):
    """Portfolio, dessen Einstiege wie im Runner auf start..end maskiert sind.

    Alle Trades schließen noch innerhalb des Fensters — das ist die Bedingung,
    unter der der Zuschnitt das Strategie-Ergebnis unangetastet lassen muss.
    """
    start, end = build_trading_window(_config())
    idx = close.index
    in_window = (idx >= start) & (idx <= end)
    last_in_window = int(np.max(np.flatnonzero(in_window)))
    entries = pd.Series(False, index=idx)
    exits = pd.Series(False, index=idx)
    # Einstiege nur im Handelsfenster, Ausstiege jeweils 20 Balken später — und nur,
    # wenn dieser Ausstieg noch vor der Fenstergrenze liegt.
    entry_positions = [
        i for i in range(len(idx))
        if in_window[i] and i % 40 == 0 and i + 20 <= last_in_window
    ]
    for pos in entry_positions:
        entries.iloc[pos] = True
        exits.iloc[pos + 20] = True
    kwargs = dict(
        close=close, entries=entries, exits=exits, freq='1h',
        init_cash=100, size=100, size_type='value',
    )
    if sweep:
        kwargs['fees'] = vbt.Param([0.0, 0.001])
    return vbt.PF.from_signals(**kwargs)


# ============================================================================
# build_trading_window
# ============================================================================

def test_window_bounds_are_utc_timestamps():
    """start und end werden als tz-bewusste UTC-Zeitstempel gebildet."""
    start, end = build_trading_window(_config())
    assert start == pd.Timestamp(_START, tz='UTC')
    assert end == pd.Timestamp(_END, tz='UTC')


def test_date_without_time_is_midnight():
    """Ein end ohne Uhrzeit ist Mitternacht — dieselbe Auslegung wie die Entry-Maske."""
    _start, end = build_trading_window(_config(end='2020-02-20'))
    assert end.hour == 0 and end.minute == 0


@pytest.mark.parametrize('config', [
    {},
    {'start': _START},
    {'end': _END},
    {'start': None, 'end': _END},
    {'start': _START, 'end': ''},
])
def test_missing_bounds_raise(config):
    """Fehlende oder leere Fenstergrenzen brechen sichtbar ab, statt still zu rechnen."""
    with pytest.raises(ValueError, match='Handelsfenster nicht bestimmbar'):
        build_trading_window(config)


def test_unreadable_bounds_raise():
    """Ein nicht lesbarer Zeitstempel bricht mit klarer Meldung ab."""
    with pytest.raises(ValueError, match='keine lesbaren Zeitstempel'):
        build_trading_window(_config(start='kein-datum'))


def test_reversed_bounds_raise():
    """start hinter end ist ein Fehlzustand, kein leeres Fenster."""
    with pytest.raises(ValueError, match='Handelsfenster ungültig'):
        build_trading_window(_config(start='2020-03-01', end='2020-02-01'))


def test_window_without_bars_raises():
    """Ein Fenster ganz außerhalb der geladenen Daten meldet sich klar, statt tief in vbt zu crashen."""
    pf = _portfolio_with_window_entries(_price_series())
    with pytest.raises(ValueError, match='keinen einzigen geladenen Balken'):
        slice_to_trading_window(pf, _config(start='2031-01-01', end='2031-02-01'))


# ============================================================================
# slice_to_trading_window
# ============================================================================

def test_slice_limits_index_to_window():
    """Der Index des zugeschnittenen Portfolios liegt vollständig im Fenster."""
    pf = _portfolio_with_window_entries(_price_series())
    window = slice_to_trading_window(pf, _config())
    start, end = build_trading_window(_config())
    assert window.wrapper.index[0] >= start
    assert window.wrapper.index[-1] <= end
    assert len(window.wrapper.index) < len(pf.wrapper.index)


def test_slice_keeps_total_return():
    """Das Strategie-Ergebnis bleibt unangetastet — im Vorlauf liegt kein Trade."""
    pf = _portfolio_with_window_entries(_price_series())
    window = slice_to_trading_window(pf, _config())
    assert float(window.total_return) == pytest.approx(float(pf.total_return), rel=1e-12)


def test_slice_recomputes_benchmark_and_sharpe():
    """Buy-and-Hold-Vergleichsmaßstab und Sharpe rechnen auf dem Fenster neu."""
    pf = _portfolio_with_window_entries(_price_series())
    window = slice_to_trading_window(pf, _config())
    assert float(window.total_market_return) != pytest.approx(float(pf.total_market_return))
    assert float(window.sharpe_ratio) != pytest.approx(float(pf.sharpe_ratio))


def test_slice_keeps_multi_combination_columns():
    """Der Spalten-Index einer Multi-Kombination überlebt den Zuschnitt."""
    pf = _portfolio_with_window_entries(_price_series(), sweep=True)
    window = slice_to_trading_window(pf, _config())
    assert list(window.wrapper.columns) == list(pf.wrapper.columns)
    assert len(window.wrapper.columns) == 2


def test_slice_is_idempotent():
    """Ein zweiter Zuschnitt auf dasselbe Fenster ändert nichts.

    Der gechunkte Pfad schneidet einmal in _run_chunked und ein zweites Mal in
    _extract_metrics — das darf die Kennzahlen nicht verschieben.
    """
    pf = _portfolio_with_window_entries(_price_series())
    once = slice_to_trading_window(pf, _config())
    twice = slice_to_trading_window(once, _config())
    assert list(twice.wrapper.index) == list(once.wrapper.index)
    assert float(twice.sharpe_ratio) == pytest.approx(float(once.sharpe_ratio), rel=1e-12)
    assert float(twice.total_market_return) == pytest.approx(
        float(once.total_market_return), rel=1e-12
    )


# ============================================================================
# Randfall: am Fensterende offene Position
# ============================================================================

def test_open_position_at_window_end_is_counted():
    """Eine über end hinauslaufende Position wird als offener Trade ausgewiesen."""
    close = _price_series()
    idx = close.index
    start, end = build_trading_window(_config())
    entries = pd.Series(False, index=idx)
    exits = pd.Series(False, index=idx)
    # Ein Einstieg kurz vor dem Fensterende, Ausstieg erst deutlich danach.
    entry_pos = int(np.argmax(idx > end)) - 5
    entries.iloc[entry_pos] = True
    exits.iloc[entry_pos + 40] = True
    pf = vbt.PF.from_signals(
        close=close, entries=entries, exits=exits, freq='1h',
        init_cash=100, size=100, size_type='value',
    )
    window = slice_to_trading_window(pf, _config())

    assert int(count_open_trades(pf)) == 0, 'im vollen Lauf ist die Position geschlossen'
    assert int(count_open_trades(window)) == 1
    assert int(window.trades.count()) == 1
    assert int(window.trades.status_closed.count()) == 0
    assert window.wrapper.index[-1] <= end


def test_win_rate_over_closed_trades_ignores_open_position():
    """Trefferquote und Profitfaktor rechnen über geschlossene Trades.

    Das ist die getroffene Entscheidung: Eine unrealisierte
    Position geht marktbewertet in total_return ein, aber nicht in die
    Trefferquote — sonst hinge diese davon ab, wo das Fenster endet.
    """
    close = _price_series()
    idx = close.index
    _start, end = build_trading_window(_config())
    entries = pd.Series(False, index=idx)
    exits = pd.Series(False, index=idx)
    entry_pos = int(np.argmax(idx > end)) - 5
    entries.iloc[entry_pos] = True
    exits.iloc[entry_pos + 40] = True
    pf = vbt.PF.from_signals(
        close=close, entries=entries, exits=exits, freq='1h',
        init_cash=100, size=100, size_type='value',
    )
    window = slice_to_trading_window(pf, _config())

    # Ohne geschlossenen Trade ist die Trefferquote über status_closed undefiniert (NaN),
    # während sie über alle Trades einen scheinbar belastbaren Wert liefern würde.
    closed_win_rate = float(window.trades.status_closed.win_rate)
    all_win_rate = float(window.trades.win_rate)
    assert np.isnan(closed_win_rate)
    assert not np.isnan(all_win_rate)


# ============================================================================
# Kein geschlossener Trade: Trefferquote und Profitfaktor sind nicht bestimmbar
# ============================================================================

def _portfolio_all_trades_open(sweep: bool = False):
    """Portfolio, dessen einzige Position über das Fensterende hinausläuft."""
    close = _price_series()
    idx = close.index
    _start, end = build_trading_window(_config())
    entries = pd.Series(False, index=idx)
    exits = pd.Series(False, index=idx)
    entry_pos = int(np.argmax(idx > end)) - 5
    entries.iloc[entry_pos] = True
    exits.iloc[entry_pos + 40] = True
    kwargs = dict(
        close=close, entries=entries, exits=exits, freq='1h',
        init_cash=100, size=100, size_type='value',
    )
    if sweep:
        kwargs['fees'] = vbt.Param([0.0, 0.001])
    return vbt.PF.from_signals(**kwargs)


def test_single_combination_reports_undetermined_win_rate_as_none():
    """Ohne geschlossenen Trade liefert eine einzelne Kombination None, nicht 0.

    „Nicht bestimmbar" und „0 % Trefferquote" sind verschiedene Aussagen. Landete
    NaN als 0 in der Datenbank, stünde ein Ergebnis mit unbestimmter Quote neben
    einem echten Totalausfall und sähe gleich aus.
    """
    pf = _portfolio_all_trades_open()
    metrics = _extract_metrics(pf, pf.wrapper.columns, _config())[0]
    assert metrics['open_trades'] == 1
    assert metrics['total_trades'] == 1
    assert metrics['win_rate_pct'] is None
    assert metrics['profit_factor'] is None


def test_multi_combination_reports_undetermined_win_rate_as_none():
    """Ohne geschlossenen Trade liefert auch ein Multi-Spalten-Portfolio None, nicht 0."""
    pf = _portfolio_all_trades_open(sweep=True)
    records = _extract_metrics(pf, pf.wrapper.columns, _config())
    assert len(records) == 2
    for record in records:
        assert record['open_trades'] == 1
        assert record['total_trades'] == 1
        assert record['win_rate_pct'] is None
        assert record['profit_factor'] is None


def test_closed_losing_trade_keeps_win_rate_zero():
    """Ein geschlossener Verlust-Trade bleibt 0 % — die Gegenprobe zu „nicht bestimmbar".

    Sonst wäre nicht belegt, dass None wirklich für „keine Grundgesamtheit" steht
    und nicht bloß jede niedrige Quote verschluckt.
    """
    idx = pd.date_range('2020-01-01', periods=1600, freq='1h', tz='UTC')
    # Streng fallender Preis im Fenster -> jeder Long-Trade ist ein Verlierer.
    close = pd.Series(np.linspace(200, 100, len(idx)), index=idx)
    start, end = build_trading_window(_config())
    in_window = (idx >= start) & (idx <= end)
    first = int(np.argmax(in_window))
    entries = pd.Series(False, index=idx)
    exits = pd.Series(False, index=idx)
    entries.iloc[first + 2] = True
    exits.iloc[first + 30] = True
    pf = vbt.PF.from_signals(
        close=close, entries=entries, exits=exits, freq='1h',
        init_cash=100, size=100, size_type='value',
    )
    metrics = _extract_metrics(pf, pf.wrapper.columns, _config())[0]
    assert metrics['total_trades'] == 1
    assert metrics['open_trades'] == 0
    assert metrics['win_rate_pct'] == 0.0
    assert metrics['profit_factor'] == 0.0


# ============================================================================
# Long/Short-Aufteilung je Result (Anforderung 1)
# ============================================================================

def _portfolio_with_long_and_short_entries(close: pd.Series, sweep: bool = False):
    """Portfolio mit Long- UND Short-Trades, alle innerhalb des Fensters geschlossen.

    Abwechselnd Long- und Short-Einstiege an denselben Positionen wie
    `_portfolio_with_window_entries` — jeder Trade schließt 20 Balken später,
    noch vor der Fenstergrenze.
    """
    start, end = build_trading_window(_config())
    idx = close.index
    in_window = (idx >= start) & (idx <= end)
    last_in_window = int(np.max(np.flatnonzero(in_window)))
    long_entries = pd.Series(False, index=idx)
    long_exits = pd.Series(False, index=idx)
    short_entries = pd.Series(False, index=idx)
    short_exits = pd.Series(False, index=idx)
    entry_positions = [
        i for i in range(len(idx))
        if in_window[i] and i % 40 == 0 and i + 20 <= last_in_window
    ]
    for n, pos in enumerate(entry_positions):
        if n % 2 == 0:
            long_entries.iloc[pos] = True
            long_exits.iloc[pos + 20] = True
        else:
            short_entries.iloc[pos] = True
            short_exits.iloc[pos + 20] = True
    kwargs = dict(
        close=close, entries=long_entries, exits=long_exits,
        short_entries=short_entries, short_exits=short_exits,
        freq='1h', init_cash=100, size=100, size_type='value',
    )
    if sweep:
        kwargs['fees'] = vbt.Param([0.0, 0.001])
    return vbt.PF.from_signals(**kwargs)


def test_single_combination_splits_long_short_sum_to_total():
    """long_trades + short_trades = total_trades bei einer Kombination."""
    pf = _portfolio_with_long_and_short_entries(_price_series())
    metrics = _extract_metrics(pf, pf.wrapper.columns, _config())[0]
    assert metrics['long_trades'] > 0
    assert metrics['short_trades'] > 0
    assert metrics['long_trades'] + metrics['short_trades'] == metrics['total_trades']


def test_multi_combination_splits_long_short_sum_to_total():
    """long_trades + short_trades = total_trades über mehrere Kombinationen."""
    pf = _portfolio_with_long_and_short_entries(_price_series(), sweep=True)
    records = _extract_metrics(pf, pf.wrapper.columns, _config())
    assert len(records) == 2
    for record in records:
        assert record['long_trades'] > 0
        assert record['short_trades'] > 0
        assert record['long_trades'] + record['short_trades'] == record['total_trades']


# ============================================================================
# gerechneter Zeitraum und Balkenzahl je Result (Anforderung 2)
# ============================================================================

def test_single_combination_includes_bar_count():
    """bar_count ist bei einer Kombination gesetzt und passt zum Fenster."""
    pf = _portfolio_with_window_entries(_price_series())
    window = slice_to_trading_window(pf, _config())
    metrics = _extract_metrics(pf, pf.wrapper.columns, _config())[0]
    assert metrics['bar_count'] == len(window.wrapper.index)


def test_multi_combination_includes_trading_window_fields():
    """start_index/end_index/total_duration/bar_count sind auch bei vielen Kombinationen gesetzt.

    Alle Kombinationen eines Laufs teilen sich denselben geschnittenen Index
    (dasselbe OHLCV-Fenster) — die Felder müssen deshalb über alle Records
    identisch sein.
    """
    pf = _portfolio_with_window_entries(_price_series(), sweep=True)
    window = slice_to_trading_window(pf, _config())
    records = _extract_metrics(pf, pf.wrapper.columns, _config())
    assert len(records) == 2
    for record in records:
        assert record['bar_count'] == len(window.wrapper.index)
        assert record['start_index'] == window.wrapper.index[0].to_pydatetime().replace(tzinfo=None)
        assert record['end_index'] == window.wrapper.index[-1].to_pydatetime().replace(tzinfo=None)
        assert record['total_duration'] is not None
    assert records[0]['bar_count'] == records[1]['bar_count']
    assert records[0]['start_index'] == records[1]['start_index']


def test_total_duration_identical_for_one_and_many_combinations():
    """total_duration ist für eine und für viele Kombinationen identisch definiert.

    Pinnt einen gefundenen Fehler: `index[-1] - index[0]` ist um eine Balkenbreite
    kürzer als vbt's eigene `pf.stats()['Total Duration']` (= bar_count * freq).
    Ohne diesen Test hätte ein Multi-Spalten-Portfolio einen künstlich abweichenden
    Zeitraum gemeldet, obwohl beide Fälle dasselbe Fenster rechnen.
    """
    pf_multi = _portfolio_with_window_entries(_price_series(), sweep=True)
    records = _extract_metrics(pf_multi, pf_multi.wrapper.columns, _config())
    pf_single = _portfolio_with_window_entries(_price_series())
    single_metrics = _extract_metrics(pf_single, pf_single.wrapper.columns, _config())[0]

    assert records[0]['total_duration'] == single_metrics['total_duration']


# ============================================================================
# expectancy/sqn/edge_ratio über beide Pfade vereinheitlicht (Anforderung 8)
# ============================================================================

def test_expectancy_identical_for_one_and_many_combinations():
    """expectancy rechnet über geschlossene Trades — bei einer wie bei vielen Kombinationen.

    Pinnt den behobenen Randfall: bis dahin rechnete der
    Multi-Kombinations-Pfad über ALLE Trades (trades.expectancy), der
    Einzel-Kombinations-Pfad über pf.stats() (geschlossene Trades) — für dieselben
    Parameter unterschiedliche Werte.
    """
    pf_multi = _portfolio_with_long_and_short_entries(_price_series(), sweep=True)
    records = _extract_metrics(pf_multi, pf_multi.wrapper.columns, _config())
    # Spalte 0 des Sweeps (fees=0.0) entspricht exakt der Einzel-Kombination unten.
    pf_single = _portfolio_with_long_and_short_entries(_price_series())
    single_metrics = _extract_metrics(pf_single, pf_single.wrapper.columns, _config())[0]

    assert records[0]['expectancy'] == pytest.approx(single_metrics['expectancy'], rel=1e-9)


def test_multi_combination_expectancy_is_none_without_closed_trades():
    """Ohne geschlossenen Trade liefert expectancy über mehrere Kombinationen None, nicht 0."""
    pf = _portfolio_all_trades_open(sweep=True)
    records = _extract_metrics(pf, pf.wrapper.columns, _config())
    for record in records:
        assert record['expectancy'] is None


def test_single_combination_expectancy_is_none_without_closed_trades():
    """Ohne geschlossenen Trade liefert expectancy bei einer Kombination None, nicht 0."""
    pf = _portfolio_all_trades_open()
    metrics = _extract_metrics(pf, pf.wrapper.columns, _config())[0]
    assert metrics['expectancy'] is None


def test_sqn_edge_ratio_over_closed_trades():
    """sqn/edge_ratio rechnen über trades.status_closed, dieselbe Konvention wie expectancy."""
    pf = _portfolio_with_long_and_short_entries(_price_series())
    window = slice_to_trading_window(pf, _config())
    metrics = _extract_metrics(pf, pf.wrapper.columns, _config())[0]
    assert metrics['sqn'] == pytest.approx(float(window.trades.status_closed.sqn), rel=1e-9)
    assert metrics['edge_ratio'] == pytest.approx(float(window.trades.status_closed.edge_ratio), rel=1e-9)


def test_sqn_edge_ratio_none_without_closed_trades():
    """Ohne geschlossenen Trade liefern sqn/edge_ratio None, nicht 0 oder NaN."""
    pf = _portfolio_all_trades_open()
    metrics = _extract_metrics(pf, pf.wrapper.columns, _config())[0]
    assert metrics['sqn'] is None
    assert metrics['edge_ratio'] is None
