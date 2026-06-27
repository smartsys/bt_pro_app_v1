"""
OHLC-Daten laden

Lädt OHLC-Daten aus HDF5-Dateien basierend auf der Backtest-Konfiguration.
"""

import vectorbtpro as vbt
from user_data.config import Config

# Mapping: Exchange-Name → VBT Data-Klasse für Feature-Config
EXCHANGE_DATA_CLASS = {
    'binance': vbt.BinanceData,
}


def load_ohlc_data(backtest_config: dict) -> vbt.Data:
    """Lädt OHLC-Daten aus HDF5 basierend auf der Backtest-Konfiguration.

    Args:
        backtest_config: Dict mit symbols, exchange, timeframe, ohlc_start, ohlc_end

    Returns:
        vbt.Data Objekt mit den geladenen OHLC-Daten
    """
    data_path = Config.DATA_PATH
    exchange = backtest_config['exchange']
    data_file = data_path + f"ohlcv_{backtest_config['timeframe']}_{exchange}.h5"

    ohlc_data = vbt.Data.from_hdf(
        backtest_config['symbols'],
        paths=data_file,
        start=backtest_config['ohlc_start'],
        end=backtest_config['ohlc_end'],
        match_paths=False,
    )

    # Feature-Config der Exchange setzen (Spalten-Mapping für Open, Close, etc.)
    data_class = EXCHANGE_DATA_CLASS.get(exchange)
    if data_class and hasattr(ohlc_data, 'use_feature_config_of'):
        ohlc_data.use_feature_config_of(data_class)

    return ohlc_data
