@echo off
setlocal
cd /d "%~dp0"

echo.
echo =====================================
echo  BondLayer Demo - Issue #15
echo =====================================
echo.

if not exist ".env" (
    echo ERROR: .env file not found.
    echo.
    echo   copy .env.example .env
    echo   then put your OPENAI_API_KEY in it
    echo.
    pause
    exit /b 1
)

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: python is not on PATH.
    pause
    exit /b 1
)

echo Installing Python dependencies...
python -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed. Run it manually to see the error:
    echo   python -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo.
echo [1/2] Starting Merchant Service on :8000 ...
start "BondLayer Merchant :8000" cmd /k "cd /d "%~dp0" && python -m src.merchant.main"

echo [2/2] Starting Agent Service on :8001 ...
start "BondLayer Agent :8001" cmd /k "cd /d "%~dp0" && python -m src.agent.main"

echo.
echo Waiting for services to come up ...
powershell -NoProfile -Command "$e=$null; 1..30 | %%{ try { Invoke-WebRequest -Uri 'http://127.0.0.1:8001/health' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep -Milliseconds 700 } }; exit 1"
if errorlevel 1 (
    echo.
    echo WARNING: the agent service did not answer on :8001.
    echo Check the "BondLayer Agent :8001" window for the error.
    echo.
    pause
    exit /b 1
)

echo.
echo =====================================
echo  Ready
echo =====================================
echo   Demo UI          http://127.0.0.1:8001/
echo   Agent API docs   http://127.0.0.1:8001/docs
echo   Merchant API     http://127.0.0.1:8000/docs
echo.
echo Close the two service windows to stop the demo.
echo.

start http://127.0.0.1:8001/
endlocal
