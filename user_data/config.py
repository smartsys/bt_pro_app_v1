import os
from pathlib import Path
from dotenv import load_dotenv
from vectorbtpro import *

# .env aus Projekt-Root laden
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / '.env')


class Config:
    # Pfade und Dateinamen
    # GEÄNDERT: OHLC-Daten von user_data/ohlc_data/ nach data/ohlc_data/ verschoben
    # (Konsolidierung mit den übrigen Laufzeit-Daten unter data/)
    DATA_PATH = str(_project_root) + os.sep + 'data' + os.sep + 'ohlc_data' + os.sep
    vbt.make_dir(DATA_PATH)

    print("DATA_PATH", DATA_PATH)
    SQLITE_DB = f"sqlite:///{DATA_PATH}ohlcv_sqlite.db"

    # print('------ Config ----- ')
    # print('DATA_PATH:', DATA_PATH)
    # print('SQLITE_DB:', SQLITE_DB)
    # print('------------------\n ')
