@echo off
rem Double-click me: starts the QUANT//MONITOR server, then opens your browser.
cd /d "%~dp0"

rem Start the server in its own window (stays open so any error is readable).
start "QUANT-MONITOR server - close me to stop the dashboard" cmd /k python -m uvicorn dashboard.server:app --port 8600

rem Give it a moment to bind, then open the browser.
timeout /t 3 /nobreak >nul
start "" http://localhost:8600
