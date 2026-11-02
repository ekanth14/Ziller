@echo off
setlocal enabledelayedexpansion

echo =====================================================================
echo   ZILLERS Quantitative Crypto Terminal - Startup (Windows)
echo =====================================================================

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.11+ is not found on PATH. Please install Python.
    exit /b 1
)

:: Validate .env configuration file exists
if not exist .env (
    if exist .env.example (
        echo [WARN] .env not found. Copying .env.example to .env...
        copy .env.example .env >nul
        echo [ACTION REQUIRED] Please edit .env to set a strong ADMIN_INITIAL_PASSWORD before launching.
        exit /b 1
    ) else (
        echo [ERROR] Neither .env nor .env.example found!
        exit /b 1
    )
)

:: Ensure runtime directories exist
if not exist work\runtime mkdir work\runtime
if not exist data mkdir data

:: Launch production terminal on port 8900
set PORT=8900
if not "%~1"=="" set PORT=%~1

echo [INFO] Starting ZILLERS terminal on http://127.0.0.1:%PORT%
python -m cryptoscope.dashboard --port %PORT%

endlocal
