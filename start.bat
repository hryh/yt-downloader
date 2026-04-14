@echo off
cd /d "%~dp0"

echo Checking for virtual environment...
if not exist "venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv venv
)

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Installing / updating dependencies...
pip install -r requirements.txt --quiet

echo.
echo =============================================
echo   YT Batch Downloader
echo   Open your browser: http://localhost:8000
echo   Press Ctrl+C to stop
echo =============================================
echo.

uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
