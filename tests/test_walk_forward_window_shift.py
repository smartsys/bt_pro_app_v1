"""Tests für das Verschieben des Zeitfensters beim Walk-Forward.

Prüft `shift_backtest_window`:
- Der neue Zeitraum beginnt am bisherigen Ende und ist `months` lang.
- Der Indikator-Vorlauf (Abstand ohlc_start zu start) bleibt erhalten.
  Das ist der eigentliche Regressionsschutz: vorher wurde der alte Start erst
  gelesen, nachdem er bereits überschrieben war — der "Vorlauf" wuchs dadurch
  auf die gesamte bisherige Historie an.
- Fehlt ohlc_start, ist der Vorlauf null.
- Die übergebene Config wird nicht verändert.
"""

import pytest

from services.api.utils.walk_forward import shift_backtest_window


@pytest.fixture
def config() -> dict:
    """BacktestConfig mit 30 Tagen Indikator-Vorlauf (01.12. bis 01.01.)."""
    return {
        'symbols': ['FETUSDT'],
        'exchange': 'binance',
        'timeframe': '4h',
        'ohlc_start': '2019-12-01',
        'start': '2020-01-01',
        'end': '2020-07-01',
        'ohlc_end': '2020-07-01',
        'portfolio': {'init_cash': 100.0},
    }


class TestFensterVerschieben:
    def test_neuer_zeitraum_beginnt_am_alten_ende(self, config):
        shifted = shift_backtest_window(config, months=3)

        assert shifted['start'] == '2020-07-01'
        assert shifted['end'] == '2020-10-01'
        assert shifted['ohlc_end'] == '2020-10-01'

    def test_vorlauf_bleibt_erhalten(self, config):
        """31 Tage Vorlauf (2019-12-01 -> 2020-01-01) bleiben 31 Tage."""
        shifted = shift_backtest_window(config, months=3)

        # 2020-07-01 minus 31 Tage
        assert shifted['ohlc_start'] == '2020-05-31'

    def test_vorlauf_waechst_nicht_auf_die_ganze_historie(self, config):
        """Regressionsschutz: ohlc_start darf nicht auf den alten Wert zurückfallen."""
        shifted = shift_backtest_window(config, months=3)

        assert shifted['ohlc_start'] != config['ohlc_start']
        assert shifted['ohlc_start'] > config['start']

    def test_ohne_ohlc_start_kein_vorlauf(self, config):
        config.pop('ohlc_start')

        shifted = shift_backtest_window(config, months=6)

        assert shifted['ohlc_start'] == '2020-07-01'
        assert shifted['end'] == '2021-01-01'

    def test_eingabe_bleibt_unveraendert(self, config):
        original = dict(config)

        shift_backtest_window(config, months=12)

        assert config == original

    @pytest.mark.parametrize('months,erwartetes_ende', [
        (3, '2020-10-01'),
        (6, '2021-01-01'),
        (12, '2021-07-01'),
    ])
    def test_fensterlaenge(self, config, months, erwartetes_ende):
        assert shift_backtest_window(config, months)['end'] == erwartetes_ende
