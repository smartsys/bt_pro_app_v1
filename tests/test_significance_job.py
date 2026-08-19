"""Integrationstests des Permutationstest-Jobs (Ticket 79).

Gerechnet wird mit **kleinem N** auf synthetischen Eingangsdaten (Muster
``_make_synthetic_ohlc_data`` aus test_combo_batching.py, hier als echtes
``vbt.Data``, weil die Bar-Permutation ein Data-Objekt braucht). Kein Mock für die
Backtest-Logik: der Job läuft über ``run_spec_strategy`` und ``_extract_metrics``.

Abgesichert wird:

* Die Selbstprüfung greift — ein manipulierter Referenzwert am Result bricht den
  Test sichtbar ab (Status ``failed``, Grund in ``error_message``).
* Der Ergebnis-Datensatz ist vollständig: echte Werte, volle Null-Verteilung mit
  genau N Werten je Metrik, Kennwerte und p-Wert je Metrik.
* Nach Abschluss ist der Datensatz unveränderlich.
* **Kein Neben-Schreiben:** während des Tests entstehen keine neuen Zeilen in
  ``backtest_results`` oder ``backtest_runs`` (Bestandszählung vorher = nachher).

Diese Tests brauchen vectorbtpro und laufen deshalb im Test-Container
(``docker compose -f docker-compose-local.yml run --rm test``).
"""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest
import vectorbtpro as vbt
from sqlalchemy.orm import sessionmaker

from services.api import significance_runner
from user_data.utils.database.models import (
    BacktestResult,
    BacktestRun,
    SignificanceTest,
    SignificanceTestImmutableError,
    StrategyConcept,
    StrategyIteration,
)
from user_data.utils.database.repository import _extract_metrics
from user_data.utils.database.repository_significance import create_significance_test

_METRICS = ('sharpe_ratio', 'profit_factor', 'total_return_pct')

# Genau eine Kombination: alle Parameter skalar. Der Permutationstest rechnet immer
# die eingefrorene Kombination des Kandidaten, nie ein Raster.
_INDICATORS = {
    'fast_sma': {
        'indicator': 'custom:dwsFastSMA',
        'tf': '4h',
        'enabled': True,
        'source': 'close',
        'length': 12,
        'multiplier': 3,
    },
}

_STOPS = {
    'tp_stop': None, 'sl_stop': None, 'tsl_th': None, 'tsl_stop': None,
    'td_stop': None, 'delta_format': None, 'time_delta_format': None,
}

_RULES = {
    'entry': {'blocks': [{'conditions': [
        {'lhs': 'close', 'op': '>', 'rhs': 'indicator:fast_sma:result'},
    ]}]},
    'exit': {'blocks': [{'conditions': [
        {'lhs': 'close', 'op': '<', 'rhs': 'indicator:fast_sma:result'},
    ]}]},
}


def _backtest_config() -> dict:
    """BacktestConfig eines Einzelkombinations-Laufs über die Testreihe."""
    return {
        'symbols': ['BTCUSDT'],
        'exchange': 'binance',
        'timeframe': '4h',
        'start': '2020-01-05',
        'end': '2020-04-01',
        'ohlc_start': '2020-01-01',
        'ohlc_end': '2020-04-01',
        'import_path': 'user_data.strategies.generic.spec_runner.run_spec_strategy',
        'portfolio': {
            'size': 100.0,
            'size_type': 'value',
            'init_cash': 100.0,
            'fees': 0.001,
            'slippage': 0.0,
            'stop_exit_price': None,
            'stop_order_type': None,
        },
    }


def _make_real_frame(n: int = 540, seed: int = 5) -> pd.DataFrame:
    """Konsistente OHLCV-Reihe mit Trend und Volatilitäts-Clustern."""
    rng = np.random.default_rng(seed)
    vol = 0.005 + 0.005 * (1.0 + np.sin(np.linspace(0.0, 9.0, n))) / 2.0
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0004, 1.0, size=n) * vol))
    open_ = np.empty(n)
    open_[0] = 100.0
    open_[1:] = close[:-1] * np.exp(rng.normal(0.0, 0.0006, size=n - 1))
    top, bottom = np.maximum(open_, close), np.minimum(open_, close)
    return pd.DataFrame(
        {
            'Open': open_,
            'High': top * np.exp(rng.uniform(0.0, 0.005, size=n)),
            'Low': bottom * np.exp(-rng.uniform(0.0, 0.005, size=n)),
            'Close': close,
            'Volume': rng.uniform(1000.0, 10000.0, size=n),
        },
        index=pd.date_range('2020-01-01', periods=n, freq='4h', tz='UTC'),
    )


@pytest.fixture(scope='module')
def real_data() -> vbt.Data:
    """Echte Eingangsreihe als konfiguriertes vbt.Data (wie load_ohlc_data liefert)."""
    data = vbt.Data.from_data({'BTCUSDT': _make_real_frame()})
    data.use_feature_config_of(vbt.BinanceData)
    return data


@pytest.fixture(scope='module')
def true_metrics(real_data) -> dict:
    """Kennzahlen des echten Laufs — die Werte, die am Result stehen müssen.

    Bewusst über denselben Weg gerechnet wie der Referenzlauf des Jobs: kein
    hartcodierter Erwartungswert, sondern die Messung selbst.
    """
    from user_data.strategies.generic.spec_runner import run_spec_strategy

    config = _backtest_config()
    config['_disable_chunked'] = True
    indicators = {**_INDICATORS, '_stops': dict(_STOPS)}
    results = run_spec_strategy(real_data, indicators, config, _RULES)
    portfolios = results['portfolios']
    columns = portfolios.wrapper.columns
    assert len(columns) == 1, f'Einzelkombination erwartet, sind {len(columns)}'
    return _extract_metrics(portfolios, columns, config)[0]


@pytest.fixture
def wired(monkeypatch, test_engine, real_data):
    """Verdrahtet Runner-Session und OHLC-Laden auf die Testumgebung.

    ``load_ohlc_data`` wird am Herkunftsmodul ersetzt, weil der Runner es erst zur
    Laufzeit importiert.
    """
    session_factory = sessionmaker(bind=test_engine)
    monkeypatch.setattr(significance_runner, 'get_session', session_factory)
    monkeypatch.setattr(
        'user_data.utils.ohlc.loader.load_ohlc_data', lambda config: real_data,
    )
    return session_factory


def _seed_candidate(session, metrics: dict, overrides: dict = None) -> int:
    """Legt Konzept, Iteration, Run und Result des Kandidaten an.

    Args:
        session: Aktive Session.
        metrics: Kennzahlen, die am Result gespeichert werden.
        overrides: Einzelne Kennzahlen bewusst abweichend setzen (für die
            Selbstprüfungs-Probe).

    Returns:
        Die Result-ID des Kandidaten.
    """
    concept = StrategyConcept(slug='signifikanz-test', name='Signifikanz-Testkonzept')
    session.add(concept)
    session.flush()
    iteration = StrategyIteration(
        concept_id=concept.id,
        version=1,
        spec_json={'indicators': _INDICATORS, 'rules': _RULES},
    )
    session.add(iteration)
    session.flush()

    config = _backtest_config()
    run = BacktestRun(
        strategy_family='generic',
        strategy_name='signifikanz-test',
        symbol='BTCUSDT',
        exchange='binance',
        timeframe='4h',
        start_date=datetime(2020, 1, 5),
        end_date=datetime(2020, 4, 1),
        backtest_config_json=config,
        indicators_config_json={**_INDICATORS, '_stops': dict(_STOPS)},
        n_combinations=1,
        status='completed',
        iteration_id=iteration.id,
    )
    session.add(run)
    session.flush()

    stored = {key: metrics.get(key) for key in _METRICS}
    stored.update(overrides or {})
    result = BacktestResult(
        run_id=run.id,
        params_hash='signifikanz-test-hash',
        actual_params_json={},
        resolved_config_json=dict(_INDICATORS),
        iteration_id=iteration.id,
        **stored,
    )
    session.add(result)
    session.commit()
    return result.id


def _table_counts(session) -> dict:
    """Bestandszählung der Rechenspur-Tabellen."""
    return {
        'results': session.query(BacktestResult).count(),
        'runs': session.query(BacktestRun).count(),
    }


def _start_test(session, result_id: int, n_series: int, method: str = 'permutation') -> int:
    """Legt den significance_tests-Datensatz an, wie der API-Endpunkt es tut."""
    test = create_significance_test(
        session=session,
        result_id=result_id,
        run_id=None,
        iteration_id=None,
        method=method,
        n_iterations=n_series,
        seed=99,
    )
    return test.id


# ---------------------------------------------------------------------------
# Vollständiger Ergebnis-Datensatz
# ---------------------------------------------------------------------------

def test_permutation_test_writes_full_result_record(wired, true_metrics):
    """Ein Lauf mit kleinem N liefert je Metrik echten Wert, volle Verteilung und p-Wert."""
    session = wired()
    result_id = _seed_candidate(session, true_metrics)
    test_id = _start_test(session, result_id, n_series=4)

    assert significance_runner.run_permutation_test(test_id, metrics=_METRICS) is True

    test = session.get(SignificanceTest, test_id)
    session.refresh(test)
    assert test.status == 'completed'
    assert test.error_message is None
    assert test.duration_seconds is not None and test.duration_seconds > 0

    for metric in _METRICS:
        assert metric in test.real_values_json
        assert len(test.distribution_json[metric]) == 4, 'volle Werteliste, ein Wert je Reihe'
        entry = test.summary_json['metrics'][metric]
        assert entry['n_iterations'] == 4
        assert set(entry['null_distribution']) >= {'mean', 'median', 'p05', 'p95', 'max'}
        if entry['p_value'] is not None:
            assert 1 / 5 <= entry['p_value'] <= 1.0

    assert test.summary_json['no_trade_runs']['count'] >= 0
    assert test.summary_json['reference_check']['compared']
    session.close()


def test_permutation_test_is_deterministic_for_the_same_seed(wired, true_metrics):
    """Gleicher Seed und gleiches N liefern dieselbe Null-Verteilung."""
    session = wired()
    result_id = _seed_candidate(session, true_metrics)
    first_id = _start_test(session, result_id, n_series=3)
    second_id = _start_test(session, result_id, n_series=3)

    significance_runner.run_permutation_test(first_id, metrics=('sharpe_ratio',))
    significance_runner.run_permutation_test(second_id, metrics=('sharpe_ratio',))

    first = session.get(SignificanceTest, first_id)
    second = session.get(SignificanceTest, second_id)
    session.refresh(first)
    session.refresh(second)
    assert first.distribution_json == second.distribution_json
    session.close()


# ---------------------------------------------------------------------------
# Selbstprüfung
# ---------------------------------------------------------------------------

def test_manipulated_stored_metric_aborts_the_test_visibly(wired, true_metrics):
    """Weicht der Result-Wert vom Referenzlauf ab, bricht der Test mit Grund ab."""
    session = wired()
    manipulated = float(true_metrics['sharpe_ratio']) + 0.5
    result_id = _seed_candidate(
        session, true_metrics, overrides={'sharpe_ratio': manipulated},
    )
    test_id = _start_test(session, result_id, n_series=2)

    assert significance_runner.run_permutation_test(test_id, metrics=_METRICS) is False

    test = session.get(SignificanceTest, test_id)
    session.refresh(test)
    assert test.status == 'failed'
    assert 'Selbstprüfung fehlgeschlagen' in test.error_message
    assert 'sharpe_ratio' in test.error_message
    assert test.distribution_json is None, 'kein stilles Weiterrechnen'
    session.close()


def test_reference_check_reports_unchecked_metrics_instead_of_skipping(wired, true_metrics):
    """Eine am Result nicht gespeicherte Kennzahl wird als ungeprüft ausgewiesen."""
    session = wired()
    result_id = _seed_candidate(session, true_metrics, overrides={'profit_factor': None})
    test_id = _start_test(session, result_id, n_series=2)

    assert significance_runner.run_permutation_test(test_id, metrics=_METRICS) is True

    test = session.get(SignificanceTest, test_id)
    session.refresh(test)
    check = test.summary_json['reference_check']
    assert 'profit_factor' in check['unchecked']
    assert 'sharpe_ratio' in check['compared']
    session.close()


def test_test_fails_when_no_requested_metric_is_stored(wired, true_metrics):
    """Ohne eine einzige vergleichbare Kennzahl ist die Selbstprüfung nicht möglich."""
    session = wired()
    result_id = _seed_candidate(
        session, true_metrics,
        overrides={metric: None for metric in _METRICS},
    )
    test_id = _start_test(session, result_id, n_series=2)

    assert significance_runner.run_permutation_test(test_id, metrics=_METRICS) is False
    test = session.get(SignificanceTest, test_id)
    session.refresh(test)
    assert test.status == 'failed'
    assert 'Selbstprüfung nicht durchführbar' in test.error_message
    session.close()


# ---------------------------------------------------------------------------
# Kein Neben-Schreiben
# ---------------------------------------------------------------------------

def test_permutation_test_creates_no_rows_in_results_or_runs(wired, true_metrics):
    """Bestandszählung von backtest_results/backtest_runs vorher = nachher."""
    session = wired()
    result_id = _seed_candidate(session, true_metrics)
    test_id = _start_test(session, result_id, n_series=5)

    before = _table_counts(session)
    assert significance_runner.run_permutation_test(test_id, metrics=_METRICS) is True
    session.expire_all()
    after = _table_counts(session)

    assert after == before, (
        f'Der Permutationstest hat Rechenspuren geschrieben: {before} -> {after}'
    )
    session.close()


# ---------------------------------------------------------------------------
# Unveränderlichkeit
# ---------------------------------------------------------------------------

def test_completed_test_rejects_any_further_write(wired, true_metrics):
    """Nach Abschluss weist jeder Schreibversuch ab — auch am Freitext-Feld."""
    session = wired()
    result_id = _seed_candidate(session, true_metrics)
    test_id = _start_test(session, result_id, n_series=2)
    significance_runner.run_permutation_test(test_id, metrics=('sharpe_ratio',))

    test = session.get(SignificanceTest, test_id)
    session.refresh(test)
    assert test.status == 'completed'
    test.summary_json = {'metrics': {}}
    with pytest.raises(SignificanceTestImmutableError, match='unveränderlich'):
        session.commit()
    session.rollback()
    session.close()


def test_failed_test_rejects_any_further_write(wired, true_metrics):
    """Auch ein gescheiterter Test ist ein Endzustand und bleibt unverändert."""
    session = wired()
    result_id = _seed_candidate(
        session, true_metrics,
        overrides={'sharpe_ratio': float(true_metrics['sharpe_ratio']) + 1.0},
    )
    test_id = _start_test(session, result_id, n_series=2)
    significance_runner.run_permutation_test(test_id, metrics=_METRICS)

    test = session.get(SignificanceTest, test_id)
    session.refresh(test)
    assert test.status == 'failed'
    test.error_message = 'nachträglich geschönt'
    with pytest.raises(SignificanceTestImmutableError):
        session.commit()
    session.rollback()
    session.close()
