@echo off
echo ============================================
echo   StockAccounts Pro - Starting...
echo ============================================

REM Try different Python commands
set PYTHON_CMD=
where python >nul 2>&1 && set PYTHON_CMD=python
if "%PYTHON_CMD%"=="" where py >nul 2>&1 && set PYTHON_CMD=py
if "%PYTHON_CMD%"=="" where python3 >nul 2>&1 && set PYTHON_CMD=python3

if "%PYTHON_CMD%"=="" (
    echo ERROR: Python is not installed or not in PATH.
    echo.
    echo Please install Python 3.9+ from https://python.org
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo Found Python: %PYTHON_CMD%
%PYTHON_CMD% --version

REM Install dependencies if needed
%PYTHON_CMD% -c "import customtkinter" >nul 2>&1
if errorlevel 1 (
    echo.
    echo Installing required packages...
    %PYTHON_CMD% -m pip install -r requirements.txt
    echo.
)

REM Run the app
echo Launching StockAccounts Pro...
%PYTHON_CMD% main.py
