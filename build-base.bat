@echo off
setlocal enabledelayedexpansion

:: Baut NUR das VBT-Pro-Basis-Image (bt_pro_app_v1-vbt:latest), auf dem app/worker/
:: renderer/scheduler per FROM aufsetzen. Im Gegensatz zu install.bat bleibt der
:: Datenbestand (data\postgres, data\redis, data\pgadmin) unangetastet.

echo Baue VBT-Pro-Basis-Image (bt_pro_app_v1-vbt:latest)...

if not exist .env (
  echo FEHLER: Keine .env gefunden.
  exit /b 1
)

:: VBT_SSH_KEY aus .env lesen (alles nach dem ersten '=')
set "VBT_SSH_KEY="
for /f "tokens=1,* delims==" %%a in ('findstr /b /c:"VBT_SSH_KEY=" .env') do set "VBT_SSH_KEY=%%b"
if not defined VBT_SSH_KEY (
  echo FEHLER: VBT_SSH_KEY ist in der .env nicht gesetzt.
  exit /b 1
)

set DOCKER_BUILDKIT=1
pushd services\vbt
docker build --secret id=ssh_key,src="%VBT_SSH_KEY%" -t bt_pro_app_v1-vbt:latest .
set BUILD_RC=%ERRORLEVEL%
popd

if not "%BUILD_RC%"=="0" (
  echo FEHLER: Image-Build fehlgeschlagen.
  exit /b 1
)

echo Basis-Image steht. Jetzt up.bat starten.
