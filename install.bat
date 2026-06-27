@echo off
setlocal enabledelayedexpansion

set "COMPOSE_FILE=docker-compose-local.yml"

echo ============================================================
echo  BT Pro - Frisch-Installation
echo ============================================================
echo.
echo  ACHTUNG: Diese Installation entfernt die bestehende Datenbank
echo  und den App-Zustand (Configs, Strategien, Runs, Leaderboard,
echo  Queue, pgAdmin) und baut alles neu auf.
echo  Kursdaten (data\ohlc_data) bleiben erhalten.
echo.

set /p CONFIRM="Wirklich fortfahren? (j/N): "
if /i not "%CONFIRM%"=="j" (
  echo Abgebrochen.
  exit /b 1
)

:: .env sicherstellen
if not exist .env (
  copy .env.example .env >nul
  echo Keine .env gefunden - aus .env.example angelegt.
  echo Bitte VBT_SSH_KEY in der .env eintragen und install.bat erneut starten.
  exit /b 1
)

:: VBT_SSH_KEY aus .env lesen (alles nach dem ersten '=')
set "VBT_SSH_KEY="
for /f "tokens=1,* delims==" %%a in ('findstr /b /c:"VBT_SSH_KEY=" .env') do set "VBT_SSH_KEY=%%b"
if not defined VBT_SSH_KEY (
  echo FEHLER: VBT_SSH_KEY ist in der .env nicht gesetzt.
  echo Trage den Pfad zum SSH-Key ein, der Zugriff auf polakowo/vectorbt.pro hat.
  exit /b 1
)

:: Stack stoppen
echo [install] Stoppe Container...
docker compose -f "%COMPOSE_FILE%" down --remove-orphans

:: DB- und App-Zustand entfernen (Bind-Mounts sind teils root-owned -> per Container loeschen)
echo [install] Entferne DB- und App-Zustand (postgres, postgres_test, redis, pgadmin)...
docker run --rm -v "%cd%\data:/data" alpine:latest sh -c "rm -rf /data/postgres /data/postgres_test /data/redis /data/pgadmin"

:: VBT-Pro-Basis-Image bauen (BuildKit-Secret mit dem SSH-Key)
echo [install] Baue VBT-Pro-Basis-Image (bt_pro_app_v1-vbt:latest)...
set DOCKER_BUILDKIT=1
pushd services\vbt
docker build --secret id=ssh_key,src="%VBT_SSH_KEY%" -t bt_pro_app_v1-vbt:latest .
set BUILD_RC=%ERRORLEVEL%
popd
if not "%BUILD_RC%"=="0" (
  echo FEHLER: Image-Build fehlgeschlagen.
  exit /b 1
)

:: Docker-Stack starten (App migriert die DB beim Start automatisch)
echo [install] Starte Docker-Stack...
docker compose -f "%COMPOSE_FILE%" up -d --build

echo.
echo [install] Fertig. Der App-Container migriert die Datenbank automatisch und ist
echo           nach kurzer Startzeit erreichbar:
echo             http://localhost:5570          (App)
echo             http://localhost:5570/install  (Installations-Uebersicht)
