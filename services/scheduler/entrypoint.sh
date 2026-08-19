#!/bin/bash
set -euo pipefail

# GEÄNDERT: cron startet seine Jobs mit einer minimalen Eigen-Umgebung und
# vererbt die per Compose gesetzten Variablen (POSTGRES_SERVER und die übrigen
# DB-/Redis-Zugänge) nicht an die Job-Prozesse. Deshalb wird die echte Container-
# Umgebung hier einmal beim Start weggeschrieben; die crontab sourced die Datei vor
# jedem Job (siehe services/scheduler/crontab). Kein hartkodierter Wert — die Datei
# entsteht aus der tatsächlichen, von Compose/.env gesetzten Prozessumgebung.
#
# Die Datei liegt bewusst außerhalb der mit App/Worker geteilten Mounts
# (/app/services, /app/user_data) — der Scheduler läuft als root, die anderen
# Container als uid 1000; eine root-eigene Datei in einem geteilten Mount
# würde deren Zugriff stören.
env -0 | while IFS='=' read -r -d '' name value; do
    printf 'export %s=%q\n' "$name" "$value"
done > /etc/cron_env.sh
chmod 0600 /etc/cron_env.sh

exec "$@"
