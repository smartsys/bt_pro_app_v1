"""Tests für die Symbol-Korrelation und die effektive Symbolzahl.

Geprüft wird:
- Eine konstruierte Korrelation wird korrekt wiedergegeben (Reihen mit bekanntem
  Zusammenhang statt Zufallsdaten ohne Sollwert).
- Symbole ohne ausreichende Überlappung führen zu einem klaren Fehler statt zu einer Zahl.
- Die effektive Symbolzahl trifft die beiden Grenzfälle: vollständige
  Unkorreliertheit ergibt `n`, identische Reihen ergeben 1 — auf beiden Rechenwegen.
- Log-Renditen werden aus den Tagesschlusskursen gebildet und Datenlücken nicht
  still aufgefüllt.
"""

import numpy as np
import pandas as pd
import pytest

from services.api.utils.symbol_correlation import (
    analyze_symbol_correlation,
    daily_log_returns,
    effective_symbols_from_eigenvalues,
    effective_symbols_from_mean_correlation,
)


# ============================================================================
# Fixtures / Factories
# ============================================================================

@pytest.fixture
def days():
    """Factory für einen Tagesindex fester Länge ab einem Startdatum."""
    def _days(count: int, start: str = '2020-01-01') -> pd.DatetimeIndex:
        return pd.date_range(start=start, periods=count, freq='D', tz='UTC')
    return _days


@pytest.fixture
def close_from_returns():
    """Factory: baut Tagesschlusskurse aus vorgegebenen Log-Renditen.

    Vor die Reihe wird ein zusätzlicher Tag mit dem Startkurs gesetzt. Dadurch ergibt
    `daily_log_returns` auf dem Ergebnis exakt die vorgegebenen Renditen (die erste
    Zeile ist wie immer NaN) und eine konstruierte Korrelation bleibt exakt erhalten.
    """
    def _close(returns: pd.DataFrame, start_price: float = 100.0) -> pd.DataFrame:
        filled = returns.fillna(0.0)
        values = start_price * np.exp(filled.cumsum().to_numpy())
        step = returns.index[1] - returns.index[0]
        index = returns.index.insert(0, returns.index[0] - step)
        values = np.vstack([np.full((1, returns.shape[1]), start_price), values])
        return pd.DataFrame(values, index=index, columns=returns.columns)
    return _close


@pytest.fixture
def orthogonal_returns(days):
    """Vier exakt unkorrelierte Renditereihen (Vorzeichenmuster einer Hadamard-Matrix).

    Exakt statt zufällig: die Spalten sind orthogonal und mittelwertfrei, die
    Paarkorrelationen sind damit rechnerisch genau null.
    """
    def _returns(blocks: int = 40) -> pd.DataFrame:
        pattern = np.array([
            [+1, +1, +1, +1],
            [+1, -1, +1, -1],
            [+1, +1, -1, -1],
            [+1, -1, -1, +1],
        ], dtype='float64')
        # Erste Spalte weglassen (konstant) und um eine mittelwertfreie Spalte ergänzen
        base = np.column_stack([pattern[:, 1], pattern[:, 2], pattern[:, 3]])
        stacked = np.tile(base, (blocks, 1)) * 0.01
        index = days(stacked.shape[0])
        return pd.DataFrame(stacked, index=index, columns=['AUSDT', 'BUSDT', 'CUSDT'])
    return _returns


@pytest.fixture
def paired_returns(days):
    """Zwei Reihen mit konstruierter Korrelation: b = rho*a + sqrt(1-rho^2)*c.

    a und c sind orthogonale Muster, dadurch ist die Stichprobenkorrelation von a
    und b exakt `rho` (bis auf Gleitkomma-Rundung).
    """
    def _returns(rho: float, blocks: int = 60) -> pd.DataFrame:
        a_pattern = np.array([+1.0, -1.0, +1.0, -1.0])
        c_pattern = np.array([+1.0, +1.0, -1.0, -1.0])
        a = np.tile(a_pattern, blocks) * 0.01
        c = np.tile(c_pattern, blocks) * 0.01
        b = rho * a + np.sqrt(1.0 - rho ** 2) * c
        index = days(a.shape[0])
        return pd.DataFrame({'AUSDT': a, 'BUSDT': b}, index=index)
    return _returns


# ============================================================================
# Log-Renditen
# ============================================================================

class TestLogRenditen:
    def test_rendite_aus_tagesschlusskursen(self, days):
        close = pd.DataFrame({'AUSDT': [100.0, 110.0, 121.0]}, index=days(3))

        returns = daily_log_returns(close)

        assert np.isnan(returns['AUSDT'].iloc[0])
        assert returns['AUSDT'].iloc[1] == pytest.approx(np.log(1.1))
        assert returns['AUSDT'].iloc[2] == pytest.approx(np.log(1.1))

    def test_luecke_wird_nicht_still_aufgefuellt(self, days):
        close = pd.DataFrame({'AUSDT': [100.0, np.nan, 121.0]}, index=days(3))

        returns = daily_log_returns(close)

        # Weder der Lückentag noch der Folgetag bekommen einen erfundenen Wert
        assert np.isnan(returns['AUSDT'].iloc[1])
        assert np.isnan(returns['AUSDT'].iloc[2])

    def test_kurs_null_ist_ein_fehler(self, days):
        close = pd.DataFrame({'AUSDT': [100.0, 0.0, 121.0]}, index=days(3))

        with pytest.raises(ValueError, match='<= 0'):
            daily_log_returns(close)


# ============================================================================
# Bekannte Korrelation
# ============================================================================

class TestBekannteKorrelation:
    @pytest.mark.parametrize('rho', [0.0, 0.5, 0.8, 0.95])
    def test_konstruierte_korrelation_wird_wiedergegeben(self, paired_returns, close_from_returns, rho):
        close = close_from_returns(paired_returns(rho))

        result = analyze_symbol_correlation(close, window=30, min_overlap=30)

        assert result['pairs'][0]['correlation'] == pytest.approx(rho, abs=1e-6)
        assert result['mean_correlation'] == pytest.approx(rho, abs=1e-6)

    def test_ueberlappung_wird_ausgewiesen(self, paired_returns, close_from_returns):
        close = close_from_returns(paired_returns(0.8, blocks=50))
        # Das zweite Symbol startet 100 Tage später — nur der Rest überlappt
        close.iloc[:100, close.columns.get_loc('BUSDT')] = np.nan

        result = analyze_symbol_correlation(close, window=30, min_overlap=30)
        pair = result['pairs'][0]

        assert pair['overlap_days'] == len(close) - 100 - 1  # eine Zeile geht für die erste Rendite drauf
        assert pair['overlap_start'] > result['coverage'][0]['start']

    def test_rollierende_extremwerte(self, paired_returns, close_from_returns):
        close = close_from_returns(paired_returns(0.8))

        result = analyze_symbol_correlation(close, window=30, min_overlap=30)
        pair = result['pairs'][0]

        assert pair['rolling_windows'] > 0
        assert pair['rolling_min'] <= pair['rolling_median'] <= pair['rolling_max']

    def test_zu_kurze_reihe_liefert_keine_rollierenden_werte(self, paired_returns, close_from_returns):
        close = close_from_returns(paired_returns(0.8, blocks=10))  # 40 Tage

        result = analyze_symbol_correlation(close, window=90, min_overlap=30)
        pair = result['pairs'][0]

        assert pair['rolling_windows'] == 0
        assert pair['rolling_min'] is None
        assert pair['rolling_median'] is None
        assert pair['rolling_max'] is None


# ============================================================================
# Fehlende Überlappung
# ============================================================================

class TestFehlendeUeberlappung:
    def test_ohne_ueberlappung_klarer_fehler(self, paired_returns, close_from_returns):
        close = close_from_returns(paired_returns(0.8, blocks=50))
        half = len(close) // 2
        # Erstes Symbol nur in der ersten Hälfte, zweites nur in der zweiten — kein gemeinsamer Tag
        close.iloc[half:, close.columns.get_loc('AUSDT')] = np.nan
        close.iloc[:half, close.columns.get_loc('BUSDT')] = np.nan

        with pytest.raises(ValueError, match='AUSDT/BUSDT'):
            analyze_symbol_correlation(close, window=30, min_overlap=30)

    def test_zu_kurze_ueberlappung_klarer_fehler(self, paired_returns, close_from_returns):
        close = close_from_returns(paired_returns(0.8, blocks=50))
        close.iloc[:-10, close.columns.get_loc('BUSDT')] = np.nan

        with pytest.raises(ValueError, match='gemeinsame Tage'):
            analyze_symbol_correlation(close, window=30, min_overlap=30)

    def test_ein_einzelnes_symbol_ist_ein_fehler(self, days):
        close = pd.DataFrame({'AUSDT': np.linspace(100.0, 200.0, 50)}, index=days(50))

        with pytest.raises(ValueError, match='mindestens zwei Symbole'):
            analyze_symbol_correlation(close)


# ============================================================================
# Effektive Symbolzahl
# ============================================================================

class TestEffektiveSymbolzahl:
    def test_formel_grenzfaelle(self):
        assert effective_symbols_from_mean_correlation(4, 0.0) == pytest.approx(4.0)
        assert effective_symbols_from_mean_correlation(4, 1.0) == pytest.approx(1.0)
        assert effective_symbols_from_mean_correlation(4, 0.8) == pytest.approx(1.1765, abs=1e-4)

    def test_eigenwert_grenzfaelle(self):
        einheit = pd.DataFrame(np.eye(4), columns=list('ABCD'), index=list('ABCD'))
        vollstaendig = pd.DataFrame(np.ones((4, 4)), columns=list('ABCD'), index=list('ABCD'))

        assert effective_symbols_from_eigenvalues(einheit) == pytest.approx(4.0)
        assert effective_symbols_from_eigenvalues(vollstaendig) == pytest.approx(1.0)

    def test_negativer_nenner_ist_ein_fehler(self):
        with pytest.raises(ValueError, match='Nenner'):
            effective_symbols_from_mean_correlation(4, -0.5)

    def test_unkorrelierte_reihen_ergeben_n(self, orthogonal_returns, close_from_returns):
        close = close_from_returns(orthogonal_returns())
        n = close.shape[1]

        result = analyze_symbol_correlation(close, window=30, min_overlap=30)

        assert result['mean_correlation'] == pytest.approx(0.0, abs=1e-9)
        assert result['effective_symbols_mean_corr'] == pytest.approx(n, abs=1e-6)
        assert result['effective_symbols_eigenvalues'] == pytest.approx(n, abs=1e-6)

    def test_identische_reihen_ergeben_eins(self, paired_returns, close_from_returns):
        base = paired_returns(0.8)
        identisch = pd.DataFrame(
            {'AUSDT': base['AUSDT'], 'BUSDT': base['AUSDT'], 'CUSDT': base['AUSDT']},
        )
        close = close_from_returns(identisch)

        result = analyze_symbol_correlation(close, window=30, min_overlap=30)

        assert result['mean_correlation'] == pytest.approx(1.0, abs=1e-9)
        assert result['effective_symbols_mean_corr'] == pytest.approx(1.0, abs=1e-6)
        assert result['effective_symbols_eigenvalues'] == pytest.approx(1.0, abs=1e-6)


# ============================================================================
# Aufbau der Antwort
# ============================================================================

class TestAntwortAufbau:
    def test_matrix_und_abdeckung(self, orthogonal_returns, close_from_returns):
        close = close_from_returns(orthogonal_returns())

        result = analyze_symbol_correlation(close, window=30, min_overlap=30)

        assert result['symbols'] == ['AUSDT', 'BUSDT', 'CUSDT']
        assert result['correlation_matrix']['AUSDT']['AUSDT'] == pytest.approx(1.0)
        assert len(result['pairs']) == 3
        assert len(result['eigenvalues']) == 3
        assert all(entry['days'] == len(close) for entry in result['coverage'])

    def test_luecken_werden_gemeldet(self, orthogonal_returns, close_from_returns):
        close = close_from_returns(orthogonal_returns())
        close.iloc[50:55, close.columns.get_loc('BUSDT')] = np.nan

        result = analyze_symbol_correlation(close, window=30, min_overlap=30)
        eintrag = next(c for c in result['coverage'] if c['symbol'] == 'BUSDT')

        assert eintrag['missing_days'] == 5
