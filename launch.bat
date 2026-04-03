@echo off
REM timelapsrr Launcher for Windows

REM Change to the script's directory
cd /d "%~dp0"

echo ===================================
echo timelapsrr Launcher
echo ===================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [X] Error: Python is not installed!
    echo Please install Python 3.8 or higher from https://www.python.org/
    echo.
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [OK] Python %PYTHON_VERSION% found

REM Check if FFmpeg is installed
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [X] Error: FFmpeg is not installed!
    echo.
    echo To install FFmpeg:
    echo   1. Download from https://ffmpeg.org/download.html
    echo   2. Extract to a folder (e.g., C:\ffmpeg)
    echo   3. Add C:\ffmpeg\bin to your System PATH
    echo.
    echo Or use Chocolatey:
    echo   choco install ffmpeg
    echo.
    pause
    exit /b 1
)

echo [OK] FFmpeg found

REM Check if pip is installed
pip --version >nul 2>&1
if errorlevel 1 (
    echo [X] Error: pip is not installed!
    pause
    exit /b 1
)
echo [OK] pip found

REM Check if requirements.txt exists
if not exist "requirements.txt" (
    echo [X] Error: requirements.txt not found!
    pause
    exit /b 1
)

REM Install dependencies if needed
echo.
echo Checking dependencies...
pip install -q -r requirements.txt
if errorlevel 1 (
    echo [X] Error: Failed to install dependencies!
    pause
    exit /b 1
)
echo [OK] Dependencies installed

REM Launch the application
echo.
echo ===================================
echo Launching timelapsrr...
echo ===================================
echo.

python main.py

if errorlevel 1 (
    echo.
    echo [X] Application exited with an error.
    pause
)