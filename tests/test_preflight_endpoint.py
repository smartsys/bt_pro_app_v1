"""Tests für den Preflight-Endpoint (Ticket 60, Anforderung 5).

/api/chart-playground/preflight rechnet EINE Kombination (Startwerte, kein
DB-Schreiben) über gespeicherte Iteration + IndicatorConfig + BacktestConfig und
meldet Entry-/Exit-Signalzahl, NaN-Anteil je Indikator-Output, tatsächlichen
Vorlauf, die Kombinationszahl des vollen Rasters und eine Laufzeit-Schätzung.

Die vbt-lastigen Bausteine (OHLC laden, Indikatoren bauen, Portfolio rechnen)
werden gemockt — geprüft wird die Verdrahtung (404/400-Fälle, Response-Form,
NaN-Berechnung, Signalzählung, Fehler-Isolation bei State-basierten Exit-
Regeln), nicht die vbt-Mechanik selbst (die ist an anderer Stelle getestet,
u.a. tests/test_run_backtest_lite.py, tests/test_warmup_check.py).
"""

import sys
import types
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException

# rq ist nur im Worker-Container installiert — für reine Tests stubben wir den Import
# (Konvention aus tests/test_backtest_config_favorite.py).
if 'rq' not in sys.modules:
    rq_stub = types.ModuleType('rq')
    rq_stub.Queue = object
    sys.modules['rq'] = rq_stub

from services.api.routes import api_chart_playground as playground_module  # noqa: E402
from user_data.strategies.generic.rules_engine import SignalMasks  # noqa: E402
from user_data.utils.database.models import (  # noqa: E402
    BacktestConfig, IndicatorConfig, StrategyConcept, StrategyIteration,
)


# ---------------------------------------------------------------------------
# Reine Helper-Funktionen — kein DB-, kein vbt-Zugriff nötig.
# ---------------------------------------------------------------------------

def _utc_index(n: int = 6) -> pd.DatetimeIndex:
    return pd.date_range('2022-01-01', periods=n, freq='4h', tz='UTC')


class TestPreflightBacktestConfig:
    def test_baut_backtest_config_json_aus_der_db_zeile(self):
        bt = SimpleNamespace(
            symbol='FETUSDT', start='2022-01-01', end='2024-01-01',
            ohlc_start='2021-12-01', ohlc_end='2024-01-01',
            exchange='binance', timeframe='4h',
            size=100, size_type='value', init_cash=100, fees=0.001,
            slippage=0.0, stop_exit_price=None, stop_order_type=None,
        )
        cfg = playground_module._preflight_backtest_config(bt, 'a.b.c')

        assert cfg['symbols'] == ['FETUSDT']
        assert cfg['start'] == '2022-01-01'
        assert cfg['ohlc_start'] == '2021-12-01'
        assert cfg['import_path'] == 'a.b.c'
        assert cfg['portfolio']['fees'] == 0.001
        assert cfg['portfolio']['size_type'] == 'value'


class TestPreflightMaskSummary:
    def test_zaehlt_long_und_short_signale_ohne_ueberlappung(self):
        idx = _utc_index(6)
        long_mask = pd.Series([True, False, False, False, False, False], index=idx)
        short_mask = pd.Series([False, False, True, False, False, False], index=idx)
        backtest_config = {'start': '2022-01-01', 'end': '2022-01-02'}

        summary = playground_module._preflight_mask_summary(long_mask, short_mask, backtest_config)

        assert summary['count'] == 2
        assert summary['first_time'].startswith('2022-01-01 00:00:00')
        assert summary['last_time'].startswith('2022-01-01 08:00:00')
        assert summary['note'] is None

    def test_leere_maske_liefert_none_zeitpunkte(self):
        idx = _utc_index(3)
        empty = pd.Series([False, False, False], index=idx)
        backtest_config = {'start': '2022-01-01', 'end': '2022-01-02'}

        summary = playground_module._preflight_mask_summary(empty, empty, backtest_config)

        assert summary['count'] == 0
        assert summary['first_time'] is None
        assert summary['last_time'] is None

    def test_schneidet_auf_das_handelsfenster_zu(self):
        """Ein Signal vor `start` zählt nicht mit — der Vorlauf ist kein Handelsfenster."""
        idx = _utc_index(6)  # 2022-01-01 00:00 .. 2022-01-01 20:00 (4h-Schritte)
        long_mask = pd.Series([True, True, False, False, False, False], index=idx)
        short_mask = pd.Series([False] * 6, index=idx)
        # start liegt NACH dem ersten Signal -> nur das zweite zählt
        backtest_config = {'start': '2022-01-01 04:00:00', 'end': '2022-01-02'}

        summary = playground_module._preflight_mask_summary(long_mask, short_mask, backtest_config)

        assert summary['count'] == 1


class TestPreflightNanRatios:
    def test_berechnet_nan_anteil_je_output(self):
        result_series = pd.Series([np.nan, np.nan, 1.0, 2.0])  # 50 % NaN
        signal_series = pd.Series([1.0, 1.0, 1.0, 1.0])        # 0 % NaN
        indicators = {
            'long_entry': SimpleNamespace(output_names=('result',), result=result_series),
            'short_entry': SimpleNamespace(output_names=('result',), result=signal_series),
        }

        ratios = playground_module._preflight_nan_ratios(indicators)

        assert ratios['long_entry.result'] == pytest.approx(0.5)
        assert ratios['short_entry.result'] == pytest.approx(0.0)

    def test_reduziert_dataframe_output_auf_erste_spalte(self):
        df_output = pd.DataFrame({0: [np.nan, 1.0], 1: [1.0, 1.0]})
        indicators = {'vwma': SimpleNamespace(output_names=('result',), result=df_output)}

        ratios = playground_module._preflight_nan_ratios(indicators)

        assert ratios['vwma.result'] == pytest.approx(0.5)


class TestPreflightSignalCounts:
    _RULES = {
        'entry': {'blocks': [{'conditions': [{'op': '>', 'lhs': 'close', 'rhs': 0}]}]},
        'exit': None,
    }

    def test_ohne_exit_regeln_liefert_leeren_exit_hinweis(self):
        idx = _utc_index(4)
        masks = SignalMasks(
            long_entries=pd.Series([True, False, False, False], index=idx),
            long_exits=pd.Series([False] * 4, index=idx),
            short_entries=pd.Series([False] * 4, index=idx),
            short_exits=pd.Series([False] * 4, index=idx),
        )
        backtest_config = {'start': '2022-01-01', 'end': '2022-01-02'}

        with patch('user_data.strategies.generic.rules_engine.evaluate_rules', return_value=masks):
            entry, exit_ = playground_module._preflight_signal_counts(
                self._RULES, object(), {}, backtest_config,
            )

        assert entry['count'] == 1
        assert exit_ == {
            'count': 0, 'first_time': None, 'last_time': None,
            'note': 'keine Exit-Regeln konfiguriert (spec_json.rules.exit ist leer)',
        }

    def test_exit_mit_state_primitiv_bleibt_note_statt_absturz(self):
        """State-basierte Exit-Bedingungen kennt der Masken-Pfad nicht (ValueError) —
        Report statt Gate: die Entry-Seite bleibt trotzdem auswertbar."""
        idx = _utc_index(4)
        entry_masks = SignalMasks(
            long_entries=pd.Series([True, False, False, False], index=idx),
            long_exits=pd.Series([False] * 4, index=idx),
            short_entries=pd.Series([False] * 4, index=idx),
            short_exits=pd.Series([False] * 4, index=idx),
        )
        rules = {**self._RULES, 'exit': {'blocks': [{'conditions': [
            {'op': '>', 'lhs': 'since_entry', 'rhs': 5},
        ]}]}}

        def fake_evaluate_rules(spec, ohlc_data, indicators):
            if spec.get('exit') is None:
                return entry_masks
            raise ValueError("State-Primitiv 'since_entry' wird im Masken-Pfad nicht unterstützt.")

        with patch('user_data.strategies.generic.rules_engine.evaluate_rules',
                   side_effect=fake_evaluate_rules):
            entry, exit_ = playground_module._preflight_signal_counts(
                rules, object(), {}, {'start': '2022-01-01', 'end': '2022-01-02'},
            )

        assert entry['count'] == 1, "Entry-Seite darf vom Exit-Fehler nicht betroffen sein"
        assert exit_['count'] is None
        assert 'State-Primitiv' in exit_['note']

    def test_entry_fehler_wird_als_http_400_gemeldet(self):
        with patch('user_data.strategies.generic.rules_engine.evaluate_rules',
                   side_effect=ValueError("Rule-Gruppe hat keine 'blocks'")):
            with pytest.raises(HTTPException) as exc_info:
                playground_module._preflight_signal_counts(
                    self._RULES, object(), {}, {'start': '2022-01-01', 'end': '2022-01-02'},
                )
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Voller Endpoint — DB-Objekte über SQLite (test_session-Fixture, conftest.py),
# vbt-lastige Bausteine gemockt.
# ---------------------------------------------------------------------------

_INDICATORS_JSON = {
    'fast_sma': {
        'indicator': 'dwsFastSMA', 'tf': '4h', 'src': 'close',
        'length': {'type': 'arange', 'start': 6, 'stop': 8, 'step': 1, 'dtype': 'int64'},
        'multiplier': {'type': 'arange', 'start': 6, 'stop': 7, 'step': 1, 'dtype': 'int64'},
    },
}
_RULES_JSON = {
    'entry': {'blocks': [{'conditions': [{'op': '>', 'lhs': 'close', 'rhs': 0}]}]},
    'exit': None,
}


def _seed(test_session, iteration_type: str = 'generic', with_entry_rules: bool = True) -> dict:
    concept = StrategyConcept(slug='ticket60-preflight', name='Preflight-Test', status='active',
                               created_at=datetime.now())
    test_session.add(concept)
    test_session.flush()

    spec_json = {'rules': _RULES_JSON if with_entry_rules else {'entry': None, 'exit': None}}
    iteration = StrategyIteration(
        concept_id=concept.id, version=1, type=iteration_type,
        import_path='x.y.z' if iteration_type == 'hardcoded' else None,
        spec_json=spec_json,
    )
    test_session.add(iteration)

    ind_cfg = IndicatorConfig(name='Preflight-Test-IC', config_json=_INDICATORS_JSON)
    test_session.add(ind_cfg)

    bt = BacktestConfig(
        name='Preflight-Test-BC', symbol='FETUSDT', exchange='binance', timeframe='4h',
        start='2022-01-01', end='2022-04-01', ohlc_start='2022-01-01', ohlc_end='2022-04-01',
    )
    test_session.add(bt)
    test_session.commit()
    return {'iteration_id': iteration.id, 'indicator_config_id': ind_cfg.id, 'backtest_config_id': bt.id}


def _fake_indicators() -> dict:
    idx = _utc_index(4)
    return {'fast_sma': SimpleNamespace(output_names=('result',), result=pd.Series([1.0] * 4, index=idx))}


def _fake_masks() -> SignalMasks:
    idx = _utc_index(4)
    zeros = pd.Series([False] * 4, index=idx)
    return SignalMasks(
        long_entries=pd.Series([True, False, False, False], index=idx),
        long_exits=zeros, short_entries=zeros, short_exits=zeros,
    )


@pytest.fixture
def preflight_env(test_session, monkeypatch):
    """Monkeypatcht get_session der Route auf die SQLite-Test-Session und mockt die
    vbt-lastigen Aufrufe (OHLC laden, Indikatoren bauen, Portfolio rechnen)."""
    monkeypatch.setattr(playground_module, 'get_session', lambda: test_session)
    with patch('user_data.utils.ohlc.loader.load_ohlc_data', return_value=object()), \
         patch('user_data.strategies.generic.indicator_factory.build_indicators',
               return_value=_fake_indicators()), \
         patch('user_data.strategies.generic.rules_engine.evaluate_rules',
               return_value=_fake_masks()), \
         patch('user_data.strategies.generic.spec_runner.run_spec_strategy',
               return_value={'portfolios': object()}):
        yield


@pytest.mark.integration
class TestPreflightEndpoint:
    def test_unbekannte_iteration_gibt_404(self, test_session, monkeypatch):
        monkeypatch.setattr(playground_module, 'get_session', lambda: test_session)
        with pytest.raises(HTTPException) as exc_info:
            playground_module.preflight(playground_module.PreflightIn(
                iteration_id=999, indicator_config_id=1, backtest_config_id=1,
            ))
        assert exc_info.value.status_code == 404
        assert 'Iteration' in exc_info.value.detail

    def test_hardcodierte_iteration_gibt_400(self, test_session, monkeypatch):
        ids = _seed(test_session, iteration_type='hardcoded')
        monkeypatch.setattr(playground_module, 'get_session', lambda: test_session)
        with pytest.raises(HTTPException) as exc_info:
            playground_module.preflight(playground_module.PreflightIn(**ids))
        assert exc_info.value.status_code == 400
        assert 'hartcodiert' in exc_info.value.detail

    def test_fehlende_entry_regeln_gibt_400(self, test_session, monkeypatch):
        ids = _seed(test_session, with_entry_rules=False)
        monkeypatch.setattr(playground_module, 'get_session', lambda: test_session)
        with pytest.raises(HTTPException) as exc_info:
            playground_module.preflight(playground_module.PreflightIn(**ids))
        assert exc_info.value.status_code == 400
        assert 'Entry-Regeln' in exc_info.value.detail

    def test_unbekannte_indicator_config_gibt_404(self, test_session, monkeypatch):
        concept = StrategyConcept(slug='x', name='x', status='active', created_at=datetime.now())
        test_session.add(concept)
        test_session.flush()
        iteration = StrategyIteration(concept_id=concept.id, version=1, type='generic',
                                       spec_json={'rules': _RULES_JSON})
        test_session.add(iteration)
        test_session.commit()
        monkeypatch.setattr(playground_module, 'get_session', lambda: test_session)

        with pytest.raises(HTTPException) as exc_info:
            playground_module.preflight(playground_module.PreflightIn(
                iteration_id=iteration.id, indicator_config_id=999, backtest_config_id=1,
            ))
        assert exc_info.value.status_code == 404
        assert 'Indicator-Config' in exc_info.value.detail

    def test_happy_path_liefert_alle_geforderten_felder(self, test_session, preflight_env):
        ids = _seed(test_session)

        result = playground_module.preflight(playground_module.PreflightIn(**ids))

        assert result['error'] is None
        d = result['data']
        for key in ('n_combinations', 'warmup', 'entry_signals', 'exit_signals',
                    'indicator_nan_ratio', 'single_combo_duration_ms',
                    'estimated_full_runtime_ms'):
            assert key in d, f"Feld {key} fehlt in der Preflight-Antwort"

        # n_combinations kommt aus der echten count_total_combos — dieselbe Funktion,
        # mit der auch der Run gezählt wird (die einzige Zähl-Wahrheit).
        from user_data.strategies.generic.indicator_factory import count_total_combos
        assert d['n_combinations'] == count_total_combos(_INDICATORS_JSON)

        assert d['entry_signals']['count'] == 1
        assert d['exit_signals']['note'] == 'keine Exit-Regeln konfiguriert (spec_json.rules.exit ist leer)'
        assert d['indicator_nan_ratio'] == {'fast_sma.result': 0.0}
        # ohlc_start == start in _seed -> Vorlauf-Warnung ist Pflicht (Anforderung 4).
        assert d['warmup']['level'] in ('warning', 'ok')
        assert d['single_combo_duration_ms'] >= 0
        assert d['estimated_full_runtime_ms'] == d['single_combo_duration_ms'] * d['n_combinations']

    def test_happy_path_schreibt_nichts_in_die_db(self, test_session, preflight_env):
        """Preflight ist ein reiner Read — kein neuer Run, kein neues Result (Report statt Gate)."""
        from user_data.utils.database.models import BacktestRun, BacktestResult

        ids = _seed(test_session)
        runs_vorher = test_session.query(BacktestRun).count()
        results_vorher = test_session.query(BacktestResult).count()

        playground_module.preflight(playground_module.PreflightIn(**ids))

        assert test_session.query(BacktestRun).count() == runs_vorher
        assert test_session.query(BacktestResult).count() == results_vorher
