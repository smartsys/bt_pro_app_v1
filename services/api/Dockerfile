# GEÄNDERT (Ticket 88): Zwei benannte Stages. "runtime" ist unverändert das Laufzeit-Image
# für app/worker; "test" setzt darauf auf und ergänzt nur die Test-Abhängigkeiten. Die
# Compose-Dienste bauen ausdrücklich mit target: runtime, damit kein pytest ins produktive
# Image gerät.
FROM bt_pro_app_v1-vbt:latest AS runtime

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


# GEÄNDERT (Ticket 88): Test-Stage. Erbt Python, vectorbtpro und alle Laufzeit-Pakete vom
# runtime-Stage — damit läuft die Suite gegen exakt die Version, die ausgeliefert wird.
# Ergänzt wird nur pytest samt der von fastapi.testclient benötigten httpx.
FROM runtime AS test

COPY services/api/requirements-test.txt .
RUN pip install --no-cache-dir -r requirements-test.txt

# Ohne Pfadangabe: Es gibt zwei Test-Ordner (tests/ und services/api/tests/), pytest
# sammelt von der rootdir /app aus beide ein.
CMD ["python", "-m", "pytest"]
