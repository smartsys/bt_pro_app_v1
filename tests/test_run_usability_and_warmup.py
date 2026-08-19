"""Tests für die Selbstauskunft eines Laufs: Vorlauf-Prüfung und Verwertbarkeits-Kennzeichnung.

Zwei Verhaltensweisen:

1. ``warmup.check_warmup`` misst den Vorlauf zwischen ``ohlc_start`` und ``start`` gegen die
   längste konfigurierte Indikator-Periode und meldet ihn als lesbaren Satz. Bei einem
   Multiparameter-Lauf zählt der **größte** Rasterwert, nicht der Startwert.
2. ``repository.assess_run_usability`` kennzeichnet nach dem Lauf, ob er verwertbar ist —
   ohne die Results anzutasten.
"""

import pytest
from sqlalchemy import text

from user_data.strategies.generic.warmup import (
    check_warmup,
    is_period_param,
    longest_indicator_period,
)


# ============================================================================
# Fixtures / Hilfsdaten
# ============================================================================

def _indicators_with_range() -> dict:
    """Indikator-Spec mit einer Perioden-Achse als Wertebereich (arange 2..14, Schritt 4)."""
    return {
        'fast_sma': {
            'tf': 'same',
            'indicator': 'custom:dwsFastSMA',
            'source': 'close',
            'length': {'type': 'arange', 'start': 2, 'stop': 14, 'step': 4, 'dtype': 'int64'},
            'multiplier': 3,
        },
        '_stops': {'sl_stop': 0.15, 'tp_stop': 0.3, 'td_stop': 8, 'delta_format': 'percent'},
    }


def _backtest_config(ohlc_start: str, start: str, end: str, timeframe: str = '4h') -> dict:
    """Minimale BacktestConfig mit genau den Feldern, die check_warmup liest."""
    return {
        'symbols': ['FETUSDT'],
        'exchange': 'binance',
        'timeframe': timeframe,
        'ohlc_start': ohlc_start,
        'ohlc_end': end,
        'start': start,
        'end': end,
    }


# ============================================================================
# Perioden-Erkennung am Parameternamen
# ============================================================================

@pytest.mark.parametrize('name', [
    'length', 'k_length', 'window', 'period', 'timeperiod', 'fastperiod',
    'signalperiod', 'fastk_period', 'smooth1', 'smooth2', 'signal', 'span', 'lookback',
])
def test_period_params_are_recognized(name):
    """Namen, die eine Fensterlänge bezeichnen, zählen als Periode."""
    assert is_period_param(name) is True


@pytest.mark.parametrize('name', [
    'multiplier', 'below_pct', 'threshold', 'prob', 'seed', 'skill', 'value', 'lookahead',
])
def test_non_period_params_are_ignored(name):
    """Faktoren, Prozentwerte, Schwellen und Saatwerte sind keine Perioden."""
    assert is_period_param(name) is False


# ============================================================================
# Längste Periode
# ============================================================================

def test_longest_period_takes_largest_grid_value_not_start():
    """Bei einem Wertebereich zählt der größte Rasterwert, nicht der Startwert."""
    period = longest_indicator_period(_indicators_with_range(), base_timeframe='4h')
    # arange(2, 14, 4) -> [2, 6, 10] — der größte Wert ist 10, nicht der Startwert 2.
    assert period['value'] == 10
    assert period['bars'] == 10
    assert period['source'] == 'fast_sma.length'


def test_longest_period_ignores_non_period_params():
    """Ein größerer Nicht-Perioden-Parameter verdrängt die Periode nicht."""
    indicators = _indicators_with_range()
    # multiplier 999 ist ein Faktor, keine Fensterlänge.
    indicators['fast_sma']['multiplier'] = 999
    period = longest_indicator_period(indicators, base_timeframe='4h')
    assert period['param'] == 'length'
    assert period['bars'] == 10


def test_longest_period_takes_maximum_across_indicators():
    """Über mehrere Indikatoren gewinnt die größte Periode."""
    indicators = _indicators_with_range()
    indicators['slow_sma'] = {
        'tf': 'same',
        'indicator': 'custom:dwsFastSMA',
        'source': 'close',
        'length': 40,
        'multiplier': 1,
    }
    period = longest_indicator_period(indicators, base_timeframe='4h')
    assert period['source'] == 'slow_sma.length'
    assert period['bars'] == 40


def test_longest_period_converts_coarser_timeframe_to_base_bars():
    """Eine Periode auf gröberem tf zählt in Basis-Balken entsprechend mehr."""
    indicators = _indicators_with_range()
    indicators['daily_sma'] = {
        'tf': '1d',
        'indicator': 'custom:dwsFastSMA',
        'source': 'close',
        'length': 5,
        'multiplier': 1,
    }
    period = longest_indicator_period(indicators, base_timeframe='4h')
    # 1d = 6 Balken à 4h -> 5 Tage brauchen 30 Basis-Balken
    assert period['source'] == 'daily_sma.length'
    assert period['tf_factor'] == 6
    assert period['bars'] == 30


def test_longest_period_zero_without_period_params():
    """Ohne Perioden-Parameter gibt es keine Vorlauf-Anforderung."""
    indicators = {
        'entry': {
            'tf': 'same',
            'indicator': 'custom:dwsRandomEntry',
            'source': 'close',
            'seed': 1,
            'prob': 0.05,
        },
    }
    period = longest_indicator_period(indicators, base_timeframe='4h')
    assert period['bars'] == 0
    assert period['source'] is None


# ============================================================================
# Vorlauf-Prüfung
# ============================================================================

def test_warmup_warns_when_ohlc_start_equals_start():
    """Ohne Vorlauf ist die Warnung Pflicht und benennt den fehlenden Vorlauf."""
    config = _backtest_config('2023-06-01', '2023-06-01', '2023-09-01')
    warmup = check_warmup(config, _indicators_with_range())
    assert warmup['level'] == 'warning'
    assert warmup['warmup_bars'] == 0
    assert warmup['required_bars'] == 10
    assert 'Kein Vorlauf' in warmup['note']
    assert 'fast_sma.length' in warmup['note']


def test_warmup_ok_with_sufficient_lead():
    """Ein Monat Vorlauf gegen eine Periode von 10 Balken warnt nicht."""
    config = _backtest_config('2021-12-01', '2022-01-01', '2024-01-01')
    warmup = check_warmup(config, _indicators_with_range())
    assert warmup['level'] == 'ok'
    # 31 Tage à 6 4h-Balken
    assert warmup['warmup_bars'] == 186
    assert warmup['required_bars'] == 10
    assert 'Vorlauf ausreichend' in warmup['note']


def test_warmup_warns_when_lead_shorter_than_period():
    """Ein zu kurzer Vorlauf nennt die Zahl der ungenügend aufgewärmten Balken."""
    # 1 Tag Vorlauf = 6 Balken, Periode 10 -> 4 Balken fehlen
    config = _backtest_config('2022-01-01', '2022-01-02', '2024-01-01')
    warmup = check_warmup(config, _indicators_with_range())
    assert warmup['level'] == 'warning'
    assert warmup['warmup_bars'] == 6
    assert 'Vorlauf zu kurz' in warmup['note']


def test_warmup_reports_insufficient_history_when_window_shorter_than_period():
    """Reicht das gesamte Datenfenster nicht für die Periode, ist der Lauf nicht verwertbar."""
    indicators = _indicators_with_range()
    indicators['fast_sma']['length'] = 500
    config = _backtest_config('2023-06-01', '2023-06-01', '2023-06-02')
    warmup = check_warmup(config, indicators)
    assert warmup['level'] == 'insufficient_history'
    assert warmup['required_bars'] == 500
    assert 'Historie reicht nicht' in warmup['note']


def test_warmup_without_period_needs_no_lead():
    """Ohne konfigurierte Periode gibt es keine Vorlauf-Warnung."""
    indicators = {
        'entry': {
            'tf': 'same',
            'indicator': 'custom:dwsRandomEntry',
            'source': 'close',
            'seed': 1,
            'prob': 0.05,
        },
    }
    config = _backtest_config('2023-06-01', '2023-06-01', '2023-09-01')
    warmup = check_warmup(config, indicators)
    assert warmup['level'] == 'ok'
    assert warmup['required_bars'] == 0


# ============================================================================
# Verwertbarkeits-Kennzeichnung am Run
# ============================================================================

def _insert_run(session, run_id: int) -> None:
    """Legt einen minimalen backtest_runs-Datensatz an."""
    session.execute(text(
        "INSERT INTO backtest_runs (id, strategy_family, strategy_name, symbol, exchange, "
        "timeframe, start_date, end_date, backtest_config_json, indicators_config_json, "
        "n_combinations, status, created_at) "
        "VALUES (:id, 'test', 'v1', 'FETUSDT', 'binance', '4h', '2022-01-01', '2024-01-01', "
        "'{}', '{}', 2, 'completed', NOW())"
    ), {'id': run_id})


def _insert_result(session, result_id: int, run_id: int, total_trades: int) -> None:
    """Legt ein backtest_results-Zeile mit gegebener Trade-Zahl an."""
    session.execute(text(
        "INSERT INTO backtest_results (id, run_id, params_hash, actual_params_json, "
        "total_trades) "
        "VALUES (:id, :run_id, :hash, '{}', :trades)"
    ), {'id': result_id, 'run_id': run_id, 'hash': f'h{result_id}', 'trades': total_trades})


def test_run_without_any_trade_is_marked_unusable(session, monkeypatch):
    """Ein Lauf, in dem keine Kombination einen Trade erzeugt, ist als nicht verwertbar
    gekennzeichnet — mit lesbarem Grund und ohne dass die Results verschwinden."""
    import user_data.utils.database.repository as repo

    _insert_run(session, 900001)
    _insert_result(session, 900001, 900001, 0)
    _insert_result(session, 900002, 900001, 0)
    session.commit()

    monkeypatch.setattr(repo, 'get_engine', lambda: session.get_bind())
    verdict = repo.assess_run_usability(900001, warmup={'level': 'warning', 'note': 'x'})

    assert verdict['usability'] == 'no_signals'
    assert verdict['n_results'] == 2
    assert verdict['total_trades'] == 0
    assert 'Kombinationen' in verdict['note']

    row = session.execute(text(
        'SELECT usability, usability_note FROM backtest_runs WHERE id = 900001'
    )).fetchone()
    assert row.usability == 'no_signals'
    assert row.usability_note and len(row.usability_note) > 20

    # Kennzeichnung, kein Ausblenden: beide Results sind unverändert vorhanden.
    n_results = session.execute(text(
        'SELECT count(*) FROM backtest_results WHERE run_id = 900001'
    )).scalar()
    assert n_results == 2


def test_run_with_trades_is_marked_usable(session, monkeypatch):
    """Gegenprobe: ein Lauf mit Trades trägt die Kennzeichnung 'usable'."""
    import user_data.utils.database.repository as repo

    _insert_run(session, 900002)
    _insert_result(session, 900011, 900002, 17)
    _insert_result(session, 900012, 900002, 0)
    session.commit()

    monkeypatch.setattr(repo, 'get_engine', lambda: session.get_bind())
    verdict = repo.assess_run_usability(900002, warmup={'level': 'ok', 'note': 'x'})

    assert verdict['usability'] == 'usable'
    assert verdict['total_trades'] == 17
    row = session.execute(text(
        'SELECT usability FROM backtest_runs WHERE id = 900002'
    )).fetchone()
    assert row.usability == 'usable'


def test_insufficient_history_outranks_no_signals(session, monkeypatch):
    """Reichte schon die Historie nicht, wird die Ursache genannt, nicht nur die Folge."""
    import user_data.utils.database.repository as repo

    _insert_run(session, 900003)
    _insert_result(session, 900021, 900003, 0)
    session.commit()

    monkeypatch.setattr(repo, 'get_engine', lambda: session.get_bind())
    verdict = repo.assess_run_usability(
        900003,
        warmup={'level': 'insufficient_history', 'note': 'Historie reicht nicht: ...'},
    )

    assert verdict['usability'] == 'insufficient_history'
    assert 'Historie reicht nicht' in verdict['note']


def test_warmup_result_is_stored_on_the_run(session, monkeypatch):
    """Die Vorlauf-Prüfung ist am Run hinterlegt und ohne JSON-Auspacken abfragbar."""
    import user_data.utils.database.repository as repo

    _insert_run(session, 900004)
    session.commit()

    monkeypatch.setattr(repo, 'get_engine', lambda: session.get_bind())
    warmup = check_warmup(
        _backtest_config('2023-06-01', '2023-06-01', '2023-09-01'),
        _indicators_with_range(),
    )
    repo.update_backtest_run_warmup(900004, warmup)

    row = session.execute(text(
        'SELECT warmup_bars, warmup_required_bars, warmup_note '
        'FROM backtest_runs WHERE id = 900004'
    )).fetchone()
    assert row.warmup_bars == 0
    assert row.warmup_required_bars == 10
    assert 'Kein Vorlauf' in row.warmup_note


def test_usability_note_carries_the_risk_sizing_warning(session, monkeypatch):
    """Die Meldung der risikobasierten Größe landet am Run, nicht nur im Log.

    ``assess_run_usability`` hängt einen gesetzten ``risk_note`` an die
    Verwertbarkeits-Note an — das ist der Weg, über den die Kürzungs-Meldung
    dauerhaft am Lauf hängt und damit auch bei einem Testset-Lauf auffindbar
    bleibt (dessen Runs gehen durch dieselbe Funktion).
    """
    import user_data.utils.database.repository as repo

    _insert_run(session, 900004)
    _insert_result(session, 900031, 900004, 12)
    session.commit()

    monkeypatch.setattr(repo, 'get_engine', lambda: session.get_bind())
    verdict = repo.assess_run_usability(
        900004,
        warmup={'level': 'ok', 'note': 'x'},
        risk_note='7 von 9 risikobasierten Orders wurden gekürzt.',
    )

    assert verdict['usability'] == 'usable'
    assert 'Verwertbar' in verdict['note']
    assert 'Risikobasierte Größe: 7 von 9' in verdict['note']

    row = session.execute(text(
        'SELECT usability_note FROM backtest_runs WHERE id = 900004'
    )).fetchone()
    assert 'Risikobasierte Größe: 7 von 9' in row.usability_note


def test_usability_note_unchanged_when_no_risk_warning_is_reported(session, monkeypatch):
    """Gegenprobe: ohne Meldung bleibt die Note die reine Verwertbarkeits-Bewertung.

    Ein Lauf mit fester Ordergröße liefert gar keinen Bericht, ein Lauf mit
    ausreichender Kreditlinie einen ohne Meldung — in beiden Fällen kommt hier
    ``risk_note=None`` an und darf nichts anhängen.
    """
    import user_data.utils.database.repository as repo

    _insert_run(session, 900005)
    _insert_result(session, 900041, 900005, 12)
    session.commit()

    monkeypatch.setattr(repo, 'get_engine', lambda: session.get_bind())
    with_none = repo.assess_run_usability(
        900005, warmup={'level': 'ok', 'note': 'x'}, risk_note=None
    )
    without_argument = repo.assess_run_usability(900005, warmup={'level': 'ok', 'note': 'x'})

    assert with_none['note'] == without_argument['note']
    assert 'Risikobasierte Größe' not in with_none['note']
    row = session.execute(text(
        'SELECT usability_note FROM backtest_runs WHERE id = 900005'
    )).fetchone()
    assert 'Risikobasierte Größe' not in row.usability_note
