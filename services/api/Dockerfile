FROM bt_pro_app_v1-vbt:latest

WORKDIR /app

# GEÄNDERT: PostgreSQL-Client 17 für Seed-Export/-Import über die GUI (pg_dump/pg_restore).
# Debian 13 (trixie, Basis dieses Images) liefert postgresql-client-17 nativ — passend zur
# TimescaleDB-Server-Version (pg17), kein PGDG-Repo nötig. Ohne diese Tools kann der
# App-Container nicht per TCP dumpen/restoren.
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client-17 \
    && rm -rf /var/lib/apt/lists/*

# Web-spezifische Dependencies nachinstallieren
COPY services/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# GEÄNDERT: --reload-dir auf services/api eingeschränkt. Vorher pollte StatReload das komplette /app
# (inkl. user_data/ mit hunderten Files) - das verursachte ~12% Idle-CPU im Frontend-Container.
# Jinja-Templates (services/frontend/templates) brauchen kein Reload (werden pro Request gerendert),
# Static-Files erst recht nicht.
# GEÄNDERT: Start läuft über services/api/entrypoint.sh - wartet auf die DB (TimescaleDB-
# Erststart-Race), migriert (alembic upgrade head, bringt Schema + Grundausstattung mit) und
# startet dann uvicorn. So braucht es keinen manuellen Migrations-Schritt und keinen
# Crash-Restart-Zyklus, wenn die DB beim ersten Hochfahren noch nicht bereit ist.
CMD ["sh", "services/api/entrypoint.sh"]
