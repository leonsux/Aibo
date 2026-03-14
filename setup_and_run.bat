@echo off
chcp 65001 >nul
REM ============================================================
REM  Gaming Buddy AI - Windows One-Click Setup & Launch
REM  Double-click to run, or execute in cmd: setup_and_run.bat
REM ============================================================

echo.
echo  [Gaming Buddy AI] Setting up environment...
echo  ------------------------------------------------

REM 1. Check Python
python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo  [ERROR] Python not found.
    echo  Please install Python from: https://www.python.org/downloads/
    echo  Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)
echo  [OK] Python found.

REM 2. Create virtual environment
IF NOT EXIST "venv\" (
    echo  [1/3] Creating virtual environment...
    python -m venv venv
    echo  [OK] Virtual environment created.
) ELSE (
    echo  [OK] Virtual environment already exists, skipping.
)

REM 3. Install dependencies (use python -m pip to avoid permission issues)
echo  [2/3] Installing dependencies...
venv\Scripts\python.exe -m pip install --quiet --upgrade pip
venv\Scripts\python.exe -m pip install --quiet openai Pillow dashscope certifi
echo  [OK] Dependencies installed.

REM 4. Launch
echo  [3/3] Starting Gaming Buddy...
echo  ------------------------------------------------
echo  Open your browser and visit: http://localhost:7788
echo.
venv\Scripts\python.exe buddy.py

pause
