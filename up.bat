@echo off
setlocal enabledelayedexpansion

echo Starte Anwendung...

:: Erstelle Docker-Netzwerk falls nicht vorhanden
docker network create proxy 2>nul

:: Starte die Container
docker-compose -f docker-compose-local.yml up -d

if %ERRORLEVEL% neq 0 (
    echo Fehler beim Starten der Container
    exit /b 1
)

echo Anwendung wurde erfolgreich gestartet!