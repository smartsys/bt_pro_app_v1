#!/usr/bin/env bash
#
# Frische lokale (Neu-)Installation in einem Aufruf:
#   1. .env sicherstellen (aus .env.example)
#   2. VBT_SSH_KEY pruefen
#   3. Sicherheitsabfrage (destruktiv)
#   4. Stack stoppen + DB-/App-Zustand loeschen (postgres, postgres_test, redis, pgadmin)
#   5. VBT-Pro-Basis-Image bauen
#   6. Docker-Stack starten
#
# ACHTUNG: Schritt 4 ist destruktiv - Configs, Strategien, Runs, Leaderboard und
# Queue gehen verloren. Kursdaten (data/ohlc_data) bleiben erhalten.
#
# Das DB-Schema und die Grundausstattung spielt der App-Container beim Start
# selbst ein (alembic upgrade head im Entrypoint, siehe services/api/Dockerfile).
#
# Aufruf:  ./install.sh        (mit Sicherheitsabfrage)
#          ./install.sh --yes  (ohne Abfrage, z.B. aus install.bat)
#
set -euo pipefail

cd "$(dirname "$0")"
COMPOSE_FILE="docker-compose-local.yml"

ASSUME_YES=0
if [ "${1:-}" = "--yes" ] || [ "${1:-}" = "-y" ]; then
  ASSUME_YES=1
fi

# 1. .env sicherstellen
if [ ! -f .env ]; then
  echo "[install] Keine .env gefunden - lege sie aus .env.example an."
  cp .env.example .env
  echo "[install] Bitte VBT_SSH_KEY in der .env eintragen und install.sh erneut starten."
  exit 1
fi

# 2. VBT_SSH_KEY aus .env lesen (Wert nach dem ersten '='; umschliessende Quotes entfernen)
VBT_SSH_KEY="$(grep -E '^VBT_SSH_KEY=' .env | head -1 | cut -d= -f2- | sed -e 's/^["'"'"']//' -e 's/["'"'"']$//')"
if [ -z "$VBT_SSH_KEY" ]; then
  echo "[install] FEHLER: VBT_SSH_KEY ist in der .env nicht gesetzt." >&2
  echo "          Trage den Pfad zum SSH-Key ein, der Zugriff auf polakowo/vectorbt.pro hat." >&2
  exit 1
fi

# 3. Sicherheitsabfrage (destruktiv)
if [ "$ASSUME_YES" -ne 1 ]; then
  echo ""
  echo "ACHTUNG: Diese Installation LOESCHT die bestehende Datenbank und den"
  echo "App-Zustand (Configs, Strategien, Runs, Leaderboard, Queue, pgAdmin)"
  echo "und baut alles neu auf. Kursdaten (data/ohlc_data) bleiben erhalten."
  echo ""
  printf "Wirklich fortfahren? (j/N): "
  read -r answer
  case "$answer" in
    j|J|y|Y) ;;
    *) echo "Abgebrochen."; exit 1 ;;
  esac
fi

# 4. Stack stoppen und DB-/App-Zustand loeschen
echo "[install] Stoppe laufende Container..."
docker compose -f "$COMPOSE_FILE" down --remove-orphans || true

echo "[install] Loesche DB- und App-Zustand (postgres, postgres_test, redis, pgadmin)..."
# Bind-Mount-Daten sind teils root-owned (Container schreiben als root) - daher per
# kurzlebigem Container als root loeschen, statt sudo auf dem Host zu verlangen.
docker run --rm -v "$(pwd)/data:/data" alpine:latest \
  sh -c "rm -rf /data/postgres /data/postgres_test /data/redis /data/pgadmin"

# 5. VBT-Pro-Basis-Image bauen
echo "[install] Baue VBT-Pro-Basis-Image (bt_pro_app_v1-vbt:latest)..."
services/vbt/build.sh "$VBT_SSH_KEY"

# 6. Docker-Stack starten (App-Images bei Bedarf neu bauen)
echo "[install] Starte Docker-Stack..."
docker compose -f "$COMPOSE_FILE" up -d --build

echo ""
echo "[install] Fertig. Der App-Container migriert die Datenbank automatisch und ist"
echo "          nach kurzer Startzeit erreichbar:"
echo "            http://localhost:5570          (App)"
echo "            http://localhost:5570/install  (Installations-Uebersicht)"
