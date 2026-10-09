@echo off
title VPS Sentinel — 24/7 Server Monitor
echo ========================================================
echo   Starting VPS Sentinel Server Monitor (24/7 Engine)
echo ========================================================
echo.

if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
    python -m pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

echo.
echo Opening Web Dashboard at http://localhost:8000 ...
start http://localhost:8000
echo.
echo Press Ctrl+C in this window to stop the monitoring server.
echo.
python app.py
pause
