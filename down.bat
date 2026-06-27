@echo off
setlocal enabledelayedexpansion

echo Stoppe Anwendung...

:: Stoppe die Container
docker-compose -f docker-compose-local.yml down

if %ERRORLEVEL% neq 0 (
    echo Fehler