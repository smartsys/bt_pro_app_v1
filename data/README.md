# data/

Daten-Verzeichnisse, die als Bind-Mounts in die Docker-Services eingebunden
werden (siehe `docker-compose-local.yml`).

Aktuell enthaltene Ordner:

- `postgres/` — PostgreSQL/TimescaleDB-Daten (App-Datenbank)
- `postgres_test/` — PostgreSQL-Daten der Test-Datenbank
- `pgadmin/` — pgAdmin-Konfiguration und -Sessions
- `redis/` — Redis-Persistenz (RQ-Queue)
- `ohlc_data/` — OHLC-HDF5-Dateien (`ohlcv_{timeframe}_{exchange}.h5`).
  Manuell gezogene Eingangsdaten (nicht von Containern erzeugt), eingelesen
  über `Config.DATA_PATH` bzw. `user_data/utils/ohlc/loader.py`.

Diese Ordner werden zur Laufzeit von den Containern befüllt und sind per
`.gitignore` ausgeschlossen — nur diese README liegt im Repository, damit der
`data/`-Ordner nach dem Klonen vorhanden ist.
