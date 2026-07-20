@echo off
REM WifiIDS - one-click launcher for the control panel GUI
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" wifiids_gui.py
) else (
    echo Virtual environment not found. Trying system Python...
    python wifiids_gui.py
)
if errorlevel 1 pause
