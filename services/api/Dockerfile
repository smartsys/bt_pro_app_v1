FROM bt_pro_app_v1-vbt:latest

WORKDIR /app

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
