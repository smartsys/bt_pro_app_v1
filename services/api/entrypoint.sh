#!/usr/bin/env sh
#
# App-Entrypoint: wartet auf die Datenbank, migriert sie und startet uvicorn.
#
# Warum der Retry-Loop: TimescaleDB startet beim allerersten Hochfahren den
# Postmaster mehrfach neu (initdb -> Init-Scripts -> Restart). Der Compose-
# Healthcheck kann dabei kurz "healthy" melden, waehrend der naechste Connect
# noch auf "Connection refused" laeuft. Statt hart zu crashen (und sich auf
# restart: unless-stopped zu verlassen) warten wir hier sauber, bis die
# Migration durchlaeuft.
#
# VBT_TEST_DATABASE_URL wird geleert, weil alembic/env.py dieser Variable
# Vorrang gibt (fuer pytest gegen die Test-DB). Beim App-Start muss aber immer
# die Arbeits-DB (POSTGRES_*) migriert werden.
#
set -e

echo "[entrypoint] Warte auf die Datenbank und fuehre Migration aus..."
attempt=0
max_attempts=20
until VBT_TEST_DATABASE_URL= alembic upgrade head 2>/tmp/alembic_err; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge "$max_attempts" ]; then
    echo "[entrypoint] Migration nach $attempt Versuchen fehlgeschlagen:" >&2
    cat /tmp/alembic_err >&2
    exit 1
  fi
  echo "[entrypoint] Datenbank noch nicht bereit (Versuch $attempt/$max_attempts), warte 3s..."
  sleep 3
done

echo "[entrypoint] Migration erfolgreich. Starte uvicorn."
exec uvicorn services.api.app:app --host 0.0.0.0 --port 8000 --reload --reload-dir services/api
