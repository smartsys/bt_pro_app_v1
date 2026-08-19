"""Tests für Indikator-Referenzen als Stop-Wert.

Ein Stop-Feld in '_stops' nimmt neben Zahl/None/Range-Dict auch ein Referenz-Dict
``{"ref": "indicator:<id>:<output>", "mult": ..., "live": ..., "ratchet": ...}``.
Geprüft wird:

  1. Notation: Parsen, Defaults und die Abweisung ungültiger Angaben.
  2. Auflösung: Der Stopabstand eines Trades entspricht dem Faktor mal dem Wert des
     referenzierten Indikators am Einstiegsbalken.
  3. Wirkung: Der Lauf mit Referenz liefert andere Kennzahlen als derselbe Lauf mit
     einem festen Skalar an derselben Stelle.
  4. Multi-Combo: Jede Portfolio-Spalte rechnet mit der Serie ihres eigenen
     Indikator-Parametersatzes; der gechunkte Lauf liefert dasselbe je Spalte.
  5. Kombinatorik: Eine Referenz ist keine Sweep-Achse.
  6. Fehler: Unbekannter Indikator/Output bricht mit Stop-Feld und Referenz ab.
  7. Laufende Nachführung ('"live": true'): Der Abstand folgt der Serie bis zum
     Ausstiegsbalken statt beim Einstieg einzufrieren.
  8. Ratsche ('"ratchet"', Default true): Das Stop-Niveau bewegt sich nur zugunsten
     der Position; ohne Ratsche folgt es der Serie in beide Richtungen.

Methodik: deterministische OHLCV-Reihe mit wechselnden Volatilitäts-Abschnitten,
damit der ATR von Trade zu Trade deutlich unterschiedliche Abstände liefert.
Kein Mocking, kein Ersatz-Portfolio — es läuft der echte Spec-Runner.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import vectorbtpro as vbt

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from user_data.strategies.generic.indicator_factory import (  # noqa: E402
    build_indicators,
    count_stop_combos,
    count_total_combos,
)
from user_data.strategies.generic.spec_runner import run_spec_strategy  # noqa: E402
from user_data.strategies.generic.stop_refs import (  # noqa: E402
    is_stop_ref,
    parse_stop_ref,
    parse_stop_refs,
)
from user_data.utils.database.repository import _extract_metrics  # noqa: E402
from user_data.utils.metrics.trading_window import slice_to_trading_window  # noqa: E402


# ============================================================================
# Fixtures / Hilfsmittel
# ============================================================================

_BACKTEST_CONFIG = {
    'timeframe': '1h',
    'start': '2023-01-05',
    'end': '2023-03-01',
    'portfolio': {
        'fees': 0.0,
        'init_cash': 10_000.0,
        'size': 1.0,
        'size_type': 'amount',
    },
}

# Long-Entry über dem gleitenden Durchschnitt; kein Exit-Block — die Positionen
# werden ausschließlich über den Stop geschlossen. Damit ist der Ausstiegspreis
# direkt der Stop-Preis und der Abstand exakt prüfbar.
_RULES = {
    'entry': {
        'blocks': [
            {
                'conditions': [
                    {
                        'lhs': 'close',
                        'lhs_shift': 0,
                        'op': '>',
                        'rhs': 'indicator:sma_trend:real',
                        'rhs_shift': 0,
                    }
                ]
            }
        ]
    },
}


def _make_ohlc_data(n: int = 1500) -> vbt.Data:
    """Deterministische OHLCV-Reihe mit abwechselnd ruhigen und bewegten Abschnitten."""
    rng = np.random.default_rng(7)
    idx = pd.date_range('2023-01-01', periods=n, freq='1h', tz='UTC')
    volatility = np.where((np.arange(n) // 120) % 2 == 0, 0.20, 1.10)
    steps = rng.normal(0, 1, n) * volatility
    close = 300.0 + np.cumsum(steps)
    open_ = np.empty(n)
    open_[0] = close[0]
    open_[1:] = close[:-1]
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 1, n)) * volatility
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 1, n)) * volatility
    df = pd.DataFrame(
        {
            'Open': open_,
            'High': high,
            'Low': low,
            'Close': close,
            'Volume': np.full(n, 1000.0),
        },
        index=idx,
    )
    data = vbt.Data.from_data({'X': df})
    data.use_feature_config_of(vbt.BinanceData)
    return data


def _indicators(atr_period=14, sma_period=20) -> dict:
    return {
        'atr_ref': {'indicator': 'talib:ATR', 'tf': 'same', 'timeperiod': atr_period},
        'sma_trend': {'indicator': 'talib:SMA', 'tf': 'same', 'timeperiod': sma_period},
    }


def _run(indicators_json: dict, data, chunk_size=None) -> dict:
    config = dict(_BACKTEST_CONFIG)
    if chunk_size is None:
        config['_disable_chunked'] = True
    else:
        config['chunk_size'] = chunk_size
    return run_spec_strategy(
        ohlc_data=data,
        indicators_json=indicators_json,
        backtest_config_json=config,
        rules_json=_RULES,
    )


def _atr_values(data, timeperiod) -> pd.DataFrame:
    """ATR-Serie(n) außerhalb des Runners gerechnet — unabhängige Gegenrechnung."""
    spec = {'atr_ref': {'indicator': 'talib:ATR', 'tf': 'same', 'timeperiod': timeperiod}}
    return build_indicators(spec, data, base_tf='1h')['atr_ref'].real


def _scalar(value) -> float:
    return float(value.iloc[0]) if isinstance(value, pd.Series) else float(value)


@pytest.fixture(scope='module')
def ohlc_data():
    return _make_ohlc_data()


@pytest.fixture(scope='module')
def reference_run(ohlc_data):
    """Lauf mit sl_stop = 5 x ATR(14) als Referenz, delta_format 'absolute'."""
    indicators_json = _indicators()
    indicators_json['_stops'] = {
        'sl_stop': {'ref': 'indicator:atr_ref:real', 'mult': 5.0},
        'delta_format': 'absolute',
    }
    return _run(indicators_json, ohlc_data)


@pytest.fixture(scope='module')
def multi_combo_indicators() -> dict:
    return {
        'atr_ref': {'indicator': 'talib:ATR', 'tf': 'same', 'timeperiod': [7, 14, 28]},
        'sma_trend': {'indicator': 'talib:SMA', 'tf': 'same', 'timeperiod': [20, 40]},
        '_stops': {
            'sl_stop': {'ref': 'indicator:atr_ref:real', 'mult': 5.0},
            'delta_format': 'absolute',
        },
    }


# ============================================================================
# 1. Notation
# ============================================================================

class TestReferenceNotation:
    """Parsen und Validieren des Referenz-Dicts."""

    def test_defaults_are_mult_one_no_live_with_ratchet(self):
        spec = parse_stop_ref({'ref': 'indicator:atr_ref:real'}, 'sl_stop')
        assert spec.ref == 'indicator:atr_ref:real'
        assert spec.mult == 1.0
        assert spec.live is False
        assert spec.ratchet is True

    def test_switches_are_taken_over_verbatim(self):
        spec = parse_stop_ref(
            {'ref': 'indicator:atr_ref:real', 'mult': 2.5, 'live': True, 'ratchet': False},
            'tsl_stop',
        )
        assert spec.mult == 2.5
        assert spec.live is True
        assert spec.ratchet is False

    def test_only_reference_dicts_are_recognized(self):
        assert is_stop_ref({'ref': 'indicator:atr_ref:real'}) is True
        assert is_stop_ref({'type': 'arange', 'start': 1, 'stop': 3, 'step': 1}) is False
        assert is_stop_ref(0.05) is False
        assert is_stop_ref(None) is False

    def test_all_stop_fields_accept_a_reference(self):
        stops = {
            'tp_stop': {'ref': 'indicator:atr_ref:real', 'mult': 3.0},
            'sl_stop': {'ref': 'indicator:atr_ref:real', 'mult': 5.0},
            'tsl_th': {'ref': 'indicator:atr_ref:real', 'mult': 2.5},
            'tsl_stop': {'ref': 'indicator:atr_ref:real', 'mult': 2.5},
            'td_stop': {'ref': 'indicator:atr_ref:real'},
            'delta_format': 'absolute',
        }
        specs = parse_stop_refs(stops)
        assert set(specs.keys()) == {'tp_stop', 'sl_stop', 'tsl_th', 'tsl_stop', 'td_stop'}

    def test_non_numeric_mult_is_rejected(self):
        with pytest.raises(ValueError) as exc:
            parse_stop_ref({'ref': 'indicator:atr_ref:real', 'mult': 'fünf'}, 'sl_stop')
        assert 'sl_stop' in str(exc.value)
        assert 'mult' in str(exc.value)

    def test_unknown_field_in_reference_dict_is_rejected(self):
        with pytest.raises(ValueError) as exc:
            parse_stop_ref({'ref': 'indicator:atr_ref:real', 'multi': 5.0}, 'sl_stop')
        assert 'multi' in str(exc.value)

    def test_non_indicator_reference_is_rejected(self):
        with pytest.raises(ValueError) as exc:
            parse_stop_ref({'ref': 'close'}, 'sl_stop')
        assert 'sl_stop' in str(exc.value)
        assert 'indicator:' in str(exc.value)

    def test_non_boolean_switch_is_rejected(self):
        with pytest.raises(ValueError) as exc:
            parse_stop_ref({'ref': 'indicator:atr_ref:real', 'live': 'ja'}, 'sl_stop')
        assert 'live' in str(exc.value)

    def test_live_is_rejected_for_target_and_time_stops(self):
        with pytest.raises(ValueError) as exc:
            parse_stop_ref({'ref': 'indicator:atr_ref:real', 'live': True}, 'tp_stop')
        assert 'tp_stop' in str(exc.value)


# ============================================================================
# 2. Auflösung im Spec-Runner
# ============================================================================

class TestReferenceResolution:
    """Der Stopabstand folgt der Serie am Einstiegsbalken."""

    def test_exit_distance_matches_factor_times_atr_at_entry_bar(
        self, reference_run, ohlc_data
    ):
        atr = np.asarray(_atr_values(ohlc_data, 14).values).ravel()
        trades = reference_run['portfolios'].trades.records
        closed = trades[trades['status'] == 1]
        assert len(closed) >= 3, 'Es müssen mindestens drei geschlossene Trades entstehen'

        abstaende = []
        for _, trade in closed.iterrows():
            entry_idx = int(trade['entry_idx'])
            abstand = float(trade['entry_price']) - float(trade['exit_price'])
            erwartet = 5.0 * atr[entry_idx]
            assert abstand == pytest.approx(erwartet, rel=1e-9), (
                f"Trade mit entry_idx={entry_idx}: Abstand {abstand} statt {erwartet}"
            )
            abstaende.append(round(abstand, 6))

        assert len(set(abstaende)) >= 3, (
            f"Die Abstände müssen sich je Trade unterscheiden, gefunden: {abstaende}"
        )

    def test_reference_and_median_scalar_differ_in_metrics(self, reference_run, ohlc_data):
        atr = np.asarray(_atr_values(ohlc_data, 14).values).ravel()
        median_stop = float(np.nanmedian(atr)) * 5.0

        scalar_json = _indicators()
        scalar_json['_stops'] = {'sl_stop': median_stop, 'delta_format': 'absolute'}
        scalar_run = _run(scalar_json, ohlc_data)

        pf_ref = reference_run['portfolios']
        pf_scalar = scalar_run['portfolios']
        assert _scalar(pf_ref.total_return) != _scalar(pf_scalar.total_return)
        assert _scalar(pf_ref.max_drawdown) != _scalar(pf_scalar.max_drawdown)
        assert _scalar(pf_ref.trades.profit_factor) != _scalar(pf_scalar.trades.profit_factor)

    def test_multiplier_scales_the_distance(self, ohlc_data):
        atr = np.asarray(_atr_values(ohlc_data, 14).values).ravel()
        indicators_json = _indicators()
        indicators_json['_stops'] = {
            'sl_stop': {'ref': 'indicator:atr_ref:real', 'mult': 2.0},
            'delta_format': 'absolute',
        }
        trades = _run(indicators_json, ohlc_data)['portfolios'].trades.records
        closed = trades[trades['status'] == 1]
        assert len(closed) >= 1
        for _, trade in closed.iterrows():
            entry_idx = int(trade['entry_idx'])
            abstand = float(trade['entry_price']) - float(trade['exit_price'])
            assert abstand == pytest.approx(2.0 * atr[entry_idx], rel=1e-9)


# ============================================================================
# 3. Multi-Combo und Chunk-Pfad
# ============================================================================

class TestMultiComboMapping:
    """Je Portfolio-Spalte die Serie des dort gerechneten Parametersatzes."""

    def test_every_column_uses_the_atr_of_its_own_parameter_set(
        self, multi_combo_indicators, ohlc_data
    ):
        result = _run(multi_combo_indicators, ohlc_data)
        portfolio = result['portfolios']
        columns = portfolio.wrapper.columns
        assert len(columns) == 6, f"Erwartet 6 Spalten, gefunden {list(columns)}"

        atr_level = list(columns.names).index('atr_ref_timeperiod')
        atr_frame = _atr_values(ohlc_data, [7, 14, 28])
        records = portfolio.trades.records

        geprüft = 0
        # Bewusst nicht Spalte 0: eine falsche Zuordnung fiele dort nicht auf.
        for col_pos in (1, 2, 4, 5):
            atr_period = columns[col_pos][atr_level]
            serie = np.asarray(
                atr_frame.loc[:, atr_frame.columns == atr_period].values
            ).ravel()
            closed = records[(records['col'] == col_pos) & (records['status'] == 1)]
            assert len(closed) >= 1, f"Spalte {col_pos} hat keine geschlossenen Trades"
            for _, trade in closed.iterrows():
                entry_idx = int(trade['entry_idx'])
                abstand = float(trade['entry_price']) - float(trade['exit_price'])
                assert abstand == pytest.approx(5.0 * serie[entry_idx], rel=1e-9), (
                    f"Spalte {col_pos} (ATR {atr_period}) passt nicht zu ihrer eigenen Serie"
                )
            geprüft += 1
        assert geprüft >= 2

    def test_swept_reference_indicator_keeps_its_column_level(
        self, multi_combo_indicators, ohlc_data
    ):
        result = _run(multi_combo_indicators, ohlc_data)
        columns = result['portfolios'].wrapper.columns
        assert 'atr_ref_timeperiod' in list(columns.names), (
            "Die Param-Achse des Referenz-Indikators muss im Spalten-Label stehen"
        )
        assert set(columns.get_level_values('atr_ref_timeperiod')) == {7, 14, 28}

    def test_reference_crosses_with_a_swept_second_stop(self, ohlc_data):
        """Referenz-Stop und gesweepter zweiter Stop kreuzen sich sauber.

        Das Portfolio hat dann n_combo * n_stops Spalten (Stop außen, Indikator
        innen); die Referenz-Serie muss dieser Achse folgen.
        """
        indicators_json = {
            'atr_ref': {'indicator': 'talib:ATR', 'tf': 'same', 'timeperiod': [7, 14]},
            'sma_trend': {'indicator': 'talib:SMA', 'tf': 'same', 'timeperiod': 20},
            '_stops': {
                'sl_stop': {'ref': 'indicator:atr_ref:real', 'mult': 5.0},
                'tp_stop': [20.0, 40.0],
                'delta_format': 'absolute',
            },
        }
        portfolio = _run(indicators_json, ohlc_data)['portfolios']
        columns = portfolio.wrapper.columns
        assert len(columns) == 4, f"Erwartet 4 Spalten, gefunden {list(columns)}"

        atr_level = list(columns.names).index('atr_ref_timeperiod')
        atr_frame = _atr_values(ohlc_data, [7, 14])
        records = portfolio.trades.records
        geprüft: set = set()
        for col_pos in range(1, 4):
            atr_period = columns[col_pos][atr_level]
            serie = np.asarray(
                atr_frame.loc[:, atr_frame.columns == atr_period].values
            ).ravel()
            closed = records[(records['col'] == col_pos) & (records['status'] == 1)]
            for _, trade in closed.iterrows():
                entry_idx = int(trade['entry_idx'])
                abstand = float(trade['entry_price']) - float(trade['exit_price'])
                # Ein Trade kann auch am Kursziel enden — dann ist der Abstand negativ.
                if abstand <= 0:
                    continue
                assert abstand == pytest.approx(5.0 * serie[entry_idx], rel=1e-9)
                geprüft.add(col_pos)
        assert len(geprüft) >= 2, (
            f'Zu wenige geprüfte Spalten: {sorted(geprüft)}'
        )

    def test_chunked_run_matches_unchunked_run_per_column(
        self, multi_combo_indicators, ohlc_data
    ):
        unchunked = _run(multi_combo_indicators, ohlc_data)
        portfolio = slice_to_trading_window(unchunked['portfolios'], _BACKTEST_CONFIG)
        expected_rows = _extract_metrics(
            portfolio, portfolio.wrapper.columns, _BACKTEST_CONFIG
        )
        expected_by_label = dict(zip(list(portfolio.wrapper.columns), expected_rows))

        chunked = _run(multi_combo_indicators, ohlc_data, chunk_size=2)
        chunk_labels = list(chunked['columns'])
        assert len(chunk_labels) == 6
        assert set(chunk_labels) == set(expected_by_label.keys()), (
            "Der gechunkte Lauf muss dieselben Spalten-Label tragen"
        )

        for row, label in zip(chunked['metrics_table'], chunk_labels):
            expected = expected_by_label[label]
            for key in sorted(set(row) | set(expected)):
                got, want = row.get(key), expected.get(key)
                if isinstance(got, float) and isinstance(want, float):
                    if np.isnan(got) and np.isnan(want):
                        continue
                assert got == want, f"Spalte {label}, Kennzahl {key}: {got} statt {want}"


# ============================================================================
# 4. Kombinatorik
# ============================================================================

class TestCombinationCount:
    """Eine Referenz ist keine Sweep-Achse."""

    def test_reference_counts_like_a_scalar(self):
        reference = {'sl_stop': {'ref': 'indicator:atr_ref:real', 'mult': 5.0}}
        scalar = {'sl_stop': 0.05}
        assert count_stop_combos(reference) == count_stop_combos(scalar) == 1

        with_reference = _indicators()
        with_reference['_stops'] = reference
        with_scalar = _indicators()
        with_scalar['_stops'] = scalar
        assert count_total_combos(with_reference) == count_total_combos(with_scalar) == 1

    def test_reference_does_not_multiply_a_swept_grid(self, multi_combo_indicators):
        with_scalar = dict(multi_combo_indicators)
        with_scalar['_stops'] = {'sl_stop': 0.05, 'delta_format': 'absolute'}
        assert count_total_combos(multi_combo_indicators) == count_total_combos(with_scalar) == 6


# ============================================================================
# 5. Fehler sichtbar, kein stiller Ersatz
# ============================================================================

class TestVisibleErrors:
    """Unauflösbare Referenzen beenden den Lauf mit Klartext."""

    def test_unknown_indicator_aborts_naming_field_and_reference(self, ohlc_data):
        indicators_json = _indicators()
        indicators_json['_stops'] = {
            'sl_stop': {'ref': 'indicator:gibtesnicht:real'},
            'delta_format': 'absolute',
        }
        with pytest.raises(ValueError) as exc:
            _run(indicators_json, ohlc_data)
        message = str(exc.value)
        assert 'sl_stop' in message
        assert 'indicator:gibtesnicht:real' in message
        assert 'gibtesnicht' in message

    def test_unknown_output_aborts_naming_field_and_reference(self, ohlc_data):
        indicators_json = _indicators()
        indicators_json['_stops'] = {
            'sl_stop': {'ref': 'indicator:atr_ref:gibtesnicht'},
            'delta_format': 'absolute',
        }
        with pytest.raises(Exception) as exc:
            _run(indicators_json, ohlc_data)
        message = str(exc.value)
        assert 'sl_stop' in message
        assert 'indicator:atr_ref:gibtesnicht' in message

    def test_disabled_indicator_aborts_naming_field_and_reference(self, ohlc_data):
        indicators_json = _indicators()
        indicators_json['atr_ref']['enabled'] = False
        indicators_json['_stops'] = {
            'sl_stop': {'ref': 'indicator:atr_ref:real', 'mult': 5.0},
            'delta_format': 'absolute',
        }
        with pytest.raises(ValueError) as exc:
            _run(indicators_json, ohlc_data)
        message = str(exc.value)
        assert 'sl_stop' in message
        assert 'indicator:atr_ref:real' in message
        assert 'deaktiviert' in message

    def test_live_reference_rejects_target_delta_format(self, ohlc_data):
        """Bei 'target' ist der Stop-Wert ein Kursniveau — kein Abstand, den man nachführt.

        Die laufende Nachführung und die Ratsche sind auf Abstände definiert. Eine
        Indikator-Serie dort als Kursniveau zu lesen wäre eine falsche Rechnung,
        deshalb bricht der Lauf ab statt still etwas anderes zu rechnen.
        """
        indicators_json = _indicators()
        indicators_json['_stops'] = {
            'sl_stop': {'ref': 'indicator:atr_ref:real', 'mult': 5.0, 'live': True},
            'delta_format': 'target',
        }
        with pytest.raises(ValueError) as exc:
            _run(indicators_json, ohlc_data)
        message = str(exc.value)
        assert 'sl_stop' in message
        assert 'target' in message

    def test_swept_reference_indicator_is_a_valid_use(self, ohlc_data):
        """Ein nur im Stop referenzierter Sweep gilt als Verwendung (kein Abbruch)."""
        indicators_json = {
            'atr_ref': {'indicator': 'talib:ATR', 'tf': 'same', 'timeperiod': [7, 14]},
            'sma_trend': {'indicator': 'talib:SMA', 'tf': 'same', 'timeperiod': 20},
            '_stops': {
                'sl_stop': {'ref': 'indicator:atr_ref:real', 'mult': 5.0},
                'delta_format': 'absolute',
            },
        }
        result = _run(indicators_json, ohlc_data)
        columns = result['portfolios'].wrapper.columns
        assert len(columns) == 2
        assert set(columns.get_level_values('atr_ref_timeperiod')) == {7, 14}


# ============================================================================
# 6. Laufend nachgeführter Abstand ('"live": true') und Ratsche
# ============================================================================

def _live_stops(stop_key: str, mult: float = 5.0, **extra) -> dict:
    """Baut einen '_stops'-Block mit einem Referenz-Stop im Absolut-Format."""
    ref = {'ref': 'indicator:atr_ref:real', 'mult': mult}
    ref.update(extra)
    return {stop_key: ref, 'delta_format': 'absolute'}


def _closed(portfolio):
    records = portfolio.trades.records
    return records[records['status'] == 1]


def _exit_fingerprint(portfolio) -> list:
    """Ausstiege als vergleichbare Liste (Einstieg, Ausstieg, Ausstiegspreis)."""
    return [
        (int(t['entry_idx']), int(t['exit_idx']), round(float(t['exit_price']), 9))
        for _, t in _closed(portfolio).iterrows()
    ]


@pytest.fixture(scope='module')
def live_sl_free_run(ohlc_data):
    """sl_stop als Live-Referenz ohne Ratsche — der Abstand folgt der Serie frei."""
    indicators_json = _indicators()
    indicators_json['_stops'] = _live_stops('sl_stop', live=True, ratchet=False)
    return _run(indicators_json, ohlc_data)


@pytest.fixture(scope='module')
def live_sl_ratchet_run(ohlc_data):
    """sl_stop als Live-Referenz ohne 'ratchet' — der Default muss ratschen."""
    indicators_json = _indicators()
    indicators_json['_stops'] = _live_stops('sl_stop', live=True)
    return _run(indicators_json, ohlc_data)


class TestLiveTracking:
    """Der Abstand wird bei jeder Kerze neu gesetzt statt beim Einstieg eingefroren."""

    def test_live_distance_matches_the_series_at_the_exit_bar(
        self, live_sl_free_run, ohlc_data
    ):
        atr = np.asarray(_atr_values(ohlc_data, 14).values).ravel()
        closed = _closed(live_sl_free_run['portfolios'])
        assert len(closed) >= 3

        abweichend = 0
        for _, trade in closed.iterrows():
            entry_idx = int(trade['entry_idx'])
            exit_idx = int(trade['exit_idx'])
            abstand = float(trade['entry_price']) - float(trade['exit_price'])
            assert abstand == pytest.approx(5.0 * atr[exit_idx], rel=1e-9), (
                f"Trade {entry_idx}->{exit_idx}: Abstand {abstand} passt nicht zum "
                f"ATR des Ausstiegsbalkens ({atr[exit_idx]})"
            )
            if abs(abstand - 5.0 * atr[entry_idx]) > 1e-9:
                abweichend += 1
        assert abweichend >= 1, (
            'Mindestens ein Trade muss sich vom eingefrorenen Abstand unterscheiden'
        )

    def test_frozen_and_live_run_differ_in_exits(self, reference_run, live_sl_free_run):
        frozen = _exit_fingerprint(reference_run['portfolios'])
        live = _exit_fingerprint(live_sl_free_run['portfolios'])
        assert frozen != live, 'Live-Nachführung muss andere Ausstiege liefern'

    def test_live_trailing_distance_matches_the_series_at_the_exit_bar(self, ohlc_data):
        """Dasselbe für tsl_stop — dort ist der Bezugspunkt der nachgezogene Extrempreis.

        VBT setzt ``peak_price`` beim Einstieg auf den Einstiegspreis; der Höchstkurs
        des Einstiegsbalkens geht nicht ein (die Stop-Prüfung läuft vor der Order).
        Ab dem Folgebalken zieht der Höchstkurs nach, im Ausstiegsbalken zählt
        zusätzlich die Eröffnung. Daraus lässt sich der wirksame Abstand
        zurückrechnen.
        """
        atr = np.asarray(_atr_values(ohlc_data, 14).values).ravel()
        high = np.asarray(ohlc_data.get('High').values).ravel()
        open_ = np.asarray(ohlc_data.get('Open').values).ravel()
        close = np.asarray(ohlc_data.get('Close').values).ravel()

        ergebnisse = {}
        for name, extra in (('frozen', {}), ('live', {'live': True, 'ratchet': False})):
            indicators_json = _indicators()
            indicators_json['_stops'] = _live_stops('tsl_stop', mult=2.5, **extra)
            portfolio = _run(indicators_json, ohlc_data)['portfolios']
            ergebnisse[name] = portfolio

            closed = _closed(portfolio)
            assert len(closed) >= 3
            exakt = 0
            for _, trade in closed.iterrows():
                entry_idx = int(trade['entry_idx'])
                exit_idx = int(trade['exit_idx'])
                exit_price = float(trade['exit_price'])
                erwartet = 2.5 * (atr[exit_idx] if name == 'live' else atr[entry_idx])

                zwischenhochs = high[entry_idx + 1:exit_idx]
                peak_vor = max(
                    float(trade['entry_price']),
                    float(np.max(zwischenhochs)) if len(zwischenhochs) else -np.inf,
                    float(open_[exit_idx]),
                )
                # VBT prüft den Stop zweimal je Balken: einmal mit dem Extrempreis
                # bis zur Eröffnung, danach noch einmal mit dem des ganzen Balkens.
                peak_inkl = max(peak_vor, float(high[exit_idx]))
                niveau_vor = peak_vor - erwartet
                niveau_inkl = peak_inkl - erwartet

                if (
                    abs(exit_price - niveau_vor) < 1e-9
                    or abs(exit_price - niveau_inkl) < 1e-9
                ):
                    # Regelfall: der Ausstieg liegt genau auf dem Stop-Niveau.
                    exakt += 1
                    continue
                if abs(exit_price - close[exit_idx]) < 1e-9:
                    # Das Niveau wurde erst nach dem Höchstkurs unterschritten —
                    # dann füllt VBT zum Schlusskurs, der unter dem Niveau liegt.
                    assert exit_price <= niveau_inkl + 1e-9
                    continue
                if abs(exit_price - open_[exit_idx]) < 1e-9:
                    # Eröffnungsluecke durch das Niveau.
                    assert exit_price <= niveau_vor + 1e-9
                    continue
                raise AssertionError(
                    f"{name}: Trade {entry_idx}->{exit_idx} steigt bei {exit_price} "
                    f"aus, passt aber weder zum Niveau {niveau_vor}/{niveau_inkl} "
                    f"noch zu Eröffnung/Schluss des Ausstiegsbalkens"
                )
            assert exakt >= 3, (
                f'{name}: nur {exakt} Trades liegen genau auf dem Stop-Niveau'
            )

        assert _exit_fingerprint(ergebnisse['frozen']) != _exit_fingerprint(
            ergebnisse['live']
        )


class TestRatchet:
    """Mit Ratsche darf sich das Stop-Niveau nur zugunsten der Position bewegen."""

    def test_ratchet_holds_the_level_when_volatility_rises(
        self, live_sl_ratchet_run, ohlc_data
    ):
        """Der Abstand ist das laufende Minimum seit Einstieg — das Niveau fällt nie.

        Beim sl_stop ist der Bezugspunkt der feste Einstiegspreis, das Niveau also
        ``einstieg − abstand``. Ein Abstand, der nur kleiner wird, ist damit
        gleichbedeutend mit einem Niveau, das nur steigt.
        """
        atr = np.asarray(_atr_values(ohlc_data, 14).values).ravel()
        closed = _closed(live_sl_ratchet_run['portfolios'])
        assert len(closed) >= 3

        mit_anstieg = 0
        for _, trade in closed.iterrows():
            entry_idx = int(trade['entry_idx'])
            exit_idx = int(trade['exit_idx'])
            abstand = float(trade['entry_price']) - float(trade['exit_price'])
            laufendes_min = 5.0 * float(np.min(atr[entry_idx:exit_idx + 1]))
            assert abstand == pytest.approx(laufendes_min, rel=1e-9), (
                f"Trade {entry_idx}->{exit_idx}: Abstand {abstand} statt des "
                f"laufenden Minimums {laufendes_min}"
            )
            # Niveau-Verlauf über die Haltedauer: mit Ratsche monoton, ohne nicht.
            niveaus_mit = float(trade['entry_price']) - 5.0 * np.minimum.accumulate(
                atr[entry_idx:exit_idx + 1]
            )
            niveaus_ohne = float(trade['entry_price']) - 5.0 * atr[entry_idx:exit_idx + 1]
            assert np.all(np.diff(niveaus_mit) >= 0), (
                'Mit Ratsche darf das Niveau nie fallen'
            )
            if np.any(np.diff(niveaus_ohne) < -1e-12):
                mit_anstieg += 1
        assert mit_anstieg >= 1, (
            'Mindestens ein Trade muss eine Phase steigender Volatilität enthalten, '
            'in der das Niveau ohne Ratsche zurückweicht'
        )

    def test_trailing_ratchet_tracks_the_level_not_the_distance(self, ohlc_data):
        """Beim tsl_stop wandert der Bezugspreis — Niveau-Ratsche ≠ Abstands-Ratsche.

        Die naheliegende Kurzform "der Abstand darf nur kleiner werden" ist beim
        ``sl_stop`` gleichbedeutend mit der Niveau-Ratsche (fester Bezugspreis),
        beim ``tsl_stop`` aber strenger: steigt der nachgezogene Extrempreis
        stärker als die Serie, darf der Abstand wachsen, ohne dass das Niveau
        fällt. Genau so macht es das auslösende Original in Pine
        (``stopLevel := math.max(stopLevel, high - trailAtr * atrVal)``).

        Der Test rechnet den Verlauf Balken für Balken nach und prüft dreierlei:
        das Niveau fällt nie, es weicht bei mindestens einem Trade von der
        Abstands-Form ab, und der tatsächliche Ausstieg liegt auf dem so
        gerechneten Niveau (das bindet das Modell an den echten Lauf).
        """
        mult = 2.5
        atr = np.asarray(_atr_values(ohlc_data, 14).values).ravel()
        high = np.asarray(ohlc_data.get('High').values).ravel()
        open_ = np.asarray(ohlc_data.get('Open').values).ravel()
        close = np.asarray(ohlc_data.get('Close').values).ravel()

        indicators_json = _indicators()
        indicators_json['_stops'] = _live_stops('tsl_stop', mult=mult, live=True)
        portfolio = _run(indicators_json, ohlc_data)['portfolios']

        closed = _closed(portfolio)
        assert len(closed) >= 3
        exakt = 0
        divergenz = 0
        for _, trade in closed.iterrows():
            entry_idx = int(trade['entry_idx'])
            exit_idx = int(trade['exit_idx'])
            entry_price = float(trade['entry_price'])

            # VBT setzt peak_price beim Einstieg auf den Einstiegspreis und den
            # Abstand auf den Serienwert des Einstiegsbalkens.
            peak = entry_price
            niveau = entry_price - mult * atr[entry_idx]
            abstand = mult * atr[entry_idx]
            kleinster_abstand = mult * atr[entry_idx]
            niveaus = []
            for bar in range(entry_idx + 1, exit_idx + 1):
                serienwert = mult * atr[bar]
                niveau = max(niveau, peak - serienwert)
                abstand = peak - niveau
                kleinster_abstand = min(kleinster_abstand, serienwert)
                niveaus.append(niveau)
                # danach zieht VBT den Extrempreis nach (Eröffnung, dann Hoch)
                peak_nach_eroeffnung = max(peak, float(open_[bar]))
                peak = max(peak_nach_eroeffnung, float(high[bar]))

            assert all(
                niveaus[k] >= niveaus[k - 1] - 1e-12 for k in range(1, len(niveaus))
            ), f'Trade {entry_idx}->{exit_idx}: das Niveau ist zurückgewichen'
            if abstand > kleinster_abstand + 1e-9:
                # Hier liefe die Abstands-Form auf einen engeren Stop hinaus.
                divergenz += 1

            niveau_vor = peak_nach_eroeffnung - abstand
            niveau_inkl = peak - abstand
            exit_price = float(trade['exit_price'])
            if (
                abs(exit_price - niveau_vor) < 1e-9
                or abs(exit_price - niveau_inkl) < 1e-9
            ):
                exakt += 1
            elif abs(exit_price - close[exit_idx]) < 1e-9:
                assert exit_price <= niveau_inkl + 1e-9
            elif abs(exit_price - open_[exit_idx]) < 1e-9:
                assert exit_price <= niveau_vor + 1e-9
            else:
                raise AssertionError(
                    f"Trade {entry_idx}->{exit_idx} steigt bei {exit_price} aus, "
                    f"passt aber nicht zum gerechneten Niveau "
                    f"{niveau_vor}/{niveau_inkl}"
                )
        assert exakt >= 3, f'Nur {exakt} Ausstiege liegen genau auf dem Niveau'
        assert divergenz >= 1, (
            'Kein Trade, bei dem sich Niveau- und Abstands-Ratsche unterscheiden — '
            'der Test würde den Unterschied gar nicht messen'
        )

    def test_ratchet_and_free_tracking_differ_in_exits(
        self, live_sl_ratchet_run, live_sl_free_run
    ):
        assert _exit_fingerprint(live_sl_ratchet_run['portfolios']) != _exit_fingerprint(
            live_sl_free_run['portfolios']
        )

    def test_missing_ratchet_flag_ratchets(self, live_sl_ratchet_run, ohlc_data):
        """Ohne 'ratchet' rechnet der Lauf identisch zum ausdrücklichen 'true'."""
        indicators_json = _indicators()
        indicators_json['_stops'] = _live_stops('sl_stop', live=True, ratchet=True)
        explizit = _run(indicators_json, ohlc_data)
        assert _exit_fingerprint(explizit['portfolios']) == _exit_fingerprint(
            live_sl_ratchet_run['portfolios']
        )


class TestLiveMultiCombo:
    """Auch live rechnet jede Portfolio-Spalte mit ihrer eigenen Serie."""

    def test_every_column_tracks_its_own_series(self, ohlc_data):
        indicators_json = {
            'atr_ref': {'indicator': 'talib:ATR', 'tf': 'same', 'timeperiod': [7, 14, 28]},
            'sma_trend': {'indicator': 'talib:SMA', 'tf': 'same', 'timeperiod': 20},
            '_stops': _live_stops('sl_stop', live=True, ratchet=False),
        }
        portfolio = _run(indicators_json, ohlc_data)['portfolios']
        columns = portfolio.wrapper.columns
        assert len(columns) == 3

        atr_level = list(columns.names).index('atr_ref_timeperiod')
        atr_frame = _atr_values(ohlc_data, [7, 14, 28])
        records = portfolio.trades.records

        geprüft = 0
        # Bewusst nicht nur Spalte 0 — eine falsche Zuordnung fiele dort nicht auf.
        for col_pos in (1, 2):
            atr_period = columns[col_pos][atr_level]
            serie = np.asarray(
                atr_frame.loc[:, atr_frame.columns == atr_period].values
            ).ravel()
            closed = records[(records['col'] == col_pos) & (records['status'] == 1)]
            assert len(closed) >= 1
            for _, trade in closed.iterrows():
                exit_idx = int(trade['exit_idx'])
                abstand = float(trade['entry_price']) - float(trade['exit_price'])
                assert abstand == pytest.approx(5.0 * serie[exit_idx], rel=1e-9), (
                    f"Spalte {col_pos} (ATR {atr_period}) folgt nicht ihrer eigenen Serie"
                )
            geprüft += 1
        assert geprüft == 2


class TestNoSideEffectOnScalarStops:
    """Ohne Live-Serie greift der neue Zweig nicht — rein skalare Stops rechnen wie zuvor."""

    # Kennzahlen desselben Laufs, gemessen mit dem Stand VOR der laufenden
    # Nachführung (Spec-Runner 4.2.0). Sie sind hier festgeschrieben, damit die
    # Zusage "ohne Live-Serie ändert sich nichts" dauerhaft geprüft wird und nicht
    # nur einmal von Hand gegenübergestellt wurde.
    ERWARTET = {
        'total_return_pct': -0.21101486642240216,
        'max_drawdown_pct': -0.3752530520820252,
        'profit_factor': 0.5288312170920401,
        'sharpe_ratio': -2.0999828012129855,
        'end_value': 9978.898513357759,
        'total_trades': 11,
        'win_rate_pct': 30.0,
    }

    def test_scalar_stop_run_matches_the_state_before_live_tracking(self, ohlc_data):
        indicators_json = _indicators()
        indicators_json['_stops'] = {
            'sl_stop': 0.03,
            'tsl_stop': 0.05,
            'tp_stop': 0.08,
            'delta_format': 'percent',
        }
        result = _run(indicators_json, ohlc_data)
        portfolio = slice_to_trading_window(result['portfolios'], _BACKTEST_CONFIG)
        row = _extract_metrics(portfolio, portfolio.wrapper.columns, _BACKTEST_CONFIG)[0]
        for key, erwartet in self.ERWARTET.items():
            assert row[key] == erwartet, f"{key}: {row[key]} statt {erwartet}"


# Short-Only-Regeln: Einstieg ÜBER dem gleitenden Durchschnitt (gegen die Bewegung),
# kein Exit-Block — geschlossen wird ausschließlich über den Stop. Die Richtung ist
# bewusst so gewählt, dass der Stop über dem Einstieg auch wirklich erreicht wird;
# in Richtung des Trends würde eine Short-Position der Reihe davonlaufen. Beim Short
# liegt das Stop-Niveau über dem Einstieg, der Abstand ist also 'exit − entry'.
_RULES_SHORT = {
    'entry': {
        'blocks': [
            {
                'conditions': [
                    {
                        'lhs': 'close',
                        'lhs_shift': 0,
                        'op': '>',
                        'rhs': 'indicator:sma_trend:real',
                        'rhs_shift': 0,
                    }
                ],
                'is_short': True,
            }
        ]
    },
}


class TestLiveTrackingShort:
    """Auf der Short-Seite wirkt die Nachführung spiegelbildlich.

    Geprüft am nachgezogenen Stop: beim Short zieht VBT den Tiefstkurs nach
    (``peak_price``) und legt das Stop-Niveau darüber. Ein Abstand, der nur kleiner
    werden darf, ist damit ein Niveau, das nur fallen darf — spiegelbildlich zum
    Long. Der einfache ``sl_stop`` taugt hier nicht als Nachweis: sein Bezugspunkt
    ist der feste Einstiegspreis, und in einer fallenden Reihe wird ein Niveau über
    dem Einstieg nach dem ersten Abtauchen nie wieder erreicht.
    """

    MULT = 2.5

    def _run_short(self, ohlc_data, **extra):
        indicators_json = _indicators()
        indicators_json['_stops'] = _live_stops(
            'tsl_stop', mult=self.MULT, live=True, **extra
        )
        config = dict(_BACKTEST_CONFIG)
        config['_disable_chunked'] = True
        return run_spec_strategy(
            ohlc_data=ohlc_data,
            indicators_json=indicators_json,
            backtest_config_json=config,
            rules_json=_RULES_SHORT,
        )

    def _pruefe(self, portfolio, ohlc_data, erwarteter_abstand) -> int:
        """Rechnet je Trade das Stop-Niveau nach und zählt die exakten Treffer.

        Spiegelbild der Long-Prüfung: Bezugspunkt ist der Tiefstkurs seit Einstieg
        (ohne den Einstiegsbalken, mit der Eröffnung des Ausstiegsbalkens), das
        Niveau liegt darüber.
        """
        low = np.asarray(ohlc_data.get('Low').values).ravel()
        open_ = np.asarray(ohlc_data.get('Open').values).ravel()
        close = np.asarray(ohlc_data.get('Close').values).ravel()

        closed = _closed(portfolio)
        assert len(closed) >= 3, f'Zu wenige geschlossene Trades: {len(closed)}'
        assert set(closed['direction']) == {1}, 'Es müssen Short-Trades sein'

        exakt = 0
        for _, trade in closed.iterrows():
            entry_idx = int(trade['entry_idx'])
            exit_idx = int(trade['exit_idx'])
            exit_price = float(trade['exit_price'])
            erwartet = erwarteter_abstand(entry_idx, exit_idx)

            zwischentiefs = low[entry_idx + 1:exit_idx]
            peak_vor = min(
                float(trade['entry_price']),
                float(np.min(zwischentiefs)) if len(zwischentiefs) else np.inf,
                float(open_[exit_idx]),
            )
            peak_inkl = min(peak_vor, float(low[exit_idx]))
            niveau_vor = peak_vor + erwartet
            niveau_inkl = peak_inkl + erwartet

            if (
                abs(exit_price - niveau_vor) < 1e-9
                or abs(exit_price - niveau_inkl) < 1e-9
            ):
                exakt += 1
                continue
            if abs(exit_price - close[exit_idx]) < 1e-9:
                assert exit_price >= niveau_inkl - 1e-9
                continue
            if abs(exit_price - open_[exit_idx]) < 1e-9:
                assert exit_price >= niveau_vor - 1e-9
                continue
            raise AssertionError(
                f"Short-Trade {entry_idx}->{exit_idx} steigt bei {exit_price} aus, "
                f"passt aber weder zum Niveau {niveau_vor}/{niveau_inkl} noch zu "
                f"Eröffnung/Schluss des Ausstiegsbalkens"
            )
        assert exakt >= 3, f'Nur {exakt} Trades liegen genau auf dem Stop-Niveau'
        return exakt

    def test_short_live_distance_matches_the_series_at_the_exit_bar(self, ohlc_data):
        atr = np.asarray(_atr_values(ohlc_data, 14).values).ravel()
        portfolio = self._run_short(ohlc_data, ratchet=False)['portfolios']
        self._pruefe(portfolio, ohlc_data, lambda ei, xi: self.MULT * atr[xi])

    def test_short_ratchet_only_tightens_the_level(self, ohlc_data):
        """Spiegelbild der Niveau-Ratsche: das Niveau über der Position steigt nie.

        Der Bezugspreis ist beim Short der nachgezogene Tiefstkurs; das Niveau
        liegt darüber und wird je Balken auf ``min(niveau, tief + serienwert)``
        gekappt. Wie beim Long darf der Abstand dabei wachsen, wenn der
        Bezugspreis stärker fällt als die Serie.
        """
        atr = np.asarray(_atr_values(ohlc_data, 14).values).ravel()
        low = np.asarray(ohlc_data.get('Low').values).ravel()
        open_ = np.asarray(ohlc_data.get('Open').values).ravel()
        close = np.asarray(ohlc_data.get('Close').values).ravel()

        portfolio = self._run_short(ohlc_data)['portfolios']
        closed = _closed(portfolio)
        assert len(closed) >= 3
        assert set(closed['direction']) == {1}, 'Es müssen Short-Trades sein'

        exakt = 0
        divergenz = 0
        for _, trade in closed.iterrows():
            entry_idx = int(trade['entry_idx'])
            exit_idx = int(trade['exit_idx'])
            entry_price = float(trade['entry_price'])

            tief = entry_price
            niveau = entry_price + self.MULT * atr[entry_idx]
            abstand = self.MULT * atr[entry_idx]
            kleinster_abstand = self.MULT * atr[entry_idx]
            niveaus = []
            for bar in range(entry_idx + 1, exit_idx + 1):
                serienwert = self.MULT * atr[bar]
                niveau = min(niveau, tief + serienwert)
                abstand = niveau - tief
                kleinster_abstand = min(kleinster_abstand, serienwert)
                niveaus.append(niveau)
                tief_nach_eroeffnung = min(tief, float(open_[bar]))
                tief = min(tief_nach_eroeffnung, float(low[bar]))

            assert all(
                niveaus[k] <= niveaus[k - 1] + 1e-12 for k in range(1, len(niveaus))
            ), f'Short-Trade {entry_idx}->{exit_idx}: das Niveau ist gestiegen'
            if abstand > kleinster_abstand + 1e-9:
                divergenz += 1

            niveau_vor = tief_nach_eroeffnung + abstand
            niveau_inkl = tief + abstand
            exit_price = float(trade['exit_price'])
            if (
                abs(exit_price - niveau_vor) < 1e-9
                or abs(exit_price - niveau_inkl) < 1e-9
            ):
                exakt += 1
            elif abs(exit_price - close[exit_idx]) < 1e-9:
                assert exit_price >= niveau_inkl - 1e-9
            elif abs(exit_price - open_[exit_idx]) < 1e-9:
                assert exit_price >= niveau_vor - 1e-9
            else:
                raise AssertionError(
                    f"Short-Trade {entry_idx}->{exit_idx} steigt bei {exit_price} "
                    f"aus, passt aber nicht zum gerechneten Niveau "
                    f"{niveau_vor}/{niveau_inkl}"
                )
        assert exakt >= 3, f'Nur {exakt} Ausstiege liegen genau auf dem Niveau'
        assert divergenz >= 1, (
            'Kein Short-Trade, bei dem sich Niveau- und Abstands-Ratsche '
            'unterscheiden'
        )

    def test_short_ratchet_and_free_tracking_differ(self, ohlc_data):
        mit = _exit_fingerprint(self._run_short(ohlc_data)['portfolios'])
        ohne = _exit_fingerprint(self._run_short(ohlc_data, ratchet=False)['portfolios'])
        assert mit != ohne
