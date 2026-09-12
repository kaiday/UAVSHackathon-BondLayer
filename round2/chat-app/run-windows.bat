@echo off
REM BondLayer Demo Chat App - Windows Launch Script
REM This script starts all services needed for Issue #15 demo

echo.
echo =====================================
echo BondLayer Demo - Issue #15
echo =====================================
echo.

REM Check if .env file exists
if not exist .env (
    echo ERROR: .env file not found!
    echo.
    echo Please create a .env file with your OpenAI API key:
    echo.
    echo   1. Copy .env.example to .env
    echo   2. Add your OPENAI_API_KEY to .env
    echo.
    echo   cp .env.example .env
    echo.
    pause
    exit /b 1
)

REM Install dependencies if needed
echo Checking dependencies...
pip install -q -r requirements.txt

echo.
echo =====================================
echo Starting Services...
echo =====================================
echo.

REM Start Merchant Service in a new window
echo [1/3] Starting Merchant Service on :8000...
start "BondLayer Merchant Service" cmd /k python -m src.merchant.main

REM Wait a moment for merchant service to start
timeout /t 2 /nobreak

REM Start Agent Service in a new window
echo [2/3] Starting Agent Service on :8001...
start "BondLayer Agent Service" cmd /k python -m src.agent.main

REM Wait a moment for agent service to start
timeout /t 2 /nobreak

REM Start UI in a new window
echo [3/3] Starting Web UI on :5173...
start "BondLayer UI" cmd /k cd src\ui && npm install -q && npm run dev

echo.
echo =====================================
echo All services started!
echo =====================================
echo.
echo Merchant Service : http://localhost:8000/health
echo Agent Service    : http://localhost:8001/health
echo Web UI           : http://localhost:5173
echo.
echo Press any key to open the demo in your browser...
pause

REM Open browser
start http://localhost:5173
