@echo off
rem Double-click me: starts the QUANT//MONITOR server and opens it in your browser.
cd /d "%~dp0"
start "" http://localhost:8600
echo Dashboard running at http://localhost:8600 - keep this window open.
echo Close this window (or press Ctrl+C) to stop the dashboard.
python -m uvicorn dashboard.server:app --port 8600
