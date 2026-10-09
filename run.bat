@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting AutoHold Pro...
start "" pythonw main.py
if errorlevel 1 (
    start "" python main.py
)
exit
