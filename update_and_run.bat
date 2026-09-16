@echo off
cd /d "%~dp0"
echo ===================================================
echo  Signedge Downloader - Update & Launch Dashboard
echo ===================================================
echo.
echo Pulling latest code from GitHub...
git pull origin main

if exist venv\Scripts\activate.bat (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
)

echo.
echo Launching Dashboard & Scheduler Server...
python src/dashboard.py
pause
