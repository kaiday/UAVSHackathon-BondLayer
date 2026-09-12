# BondLayer Demo Chat App - Windows PowerShell Launch Script
# This script starts all services needed for Issue #15 demo

Write-Host ""
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "BondLayer Demo - Issue #15" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

# Check if .env file exists
if (-not (Test-Path ".env")) {
    Write-Host "ERROR: .env file not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please create a .env file with your OpenAI API key:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  1. Copy .env.example to .env" -ForegroundColor Gray
    Write-Host "  2. Add your OPENAI_API_KEY to .env" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Commands:" -ForegroundColor Yellow
    Write-Host "  cp .env.example .env" -ForegroundColor Gray
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# Install dependencies if needed
Write-Host "Checking dependencies..." -ForegroundColor Cyan
pip install -q -r requirements.txt

Write-Host ""
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "Starting Services..." -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

# Start Merchant Service
Write-Host "[1/3] Starting Merchant Service on :8000..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$PWD'; python -m src.merchant.main`"" -WindowStyle Normal
Start-Sleep -Seconds 2

# Start Agent Service
Write-Host "[2/3] Starting Agent Service on :8001..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$PWD'; python -m src.agent.main`"" -WindowStyle Normal
Start-Sleep -Seconds 2

# Start UI
Write-Host "[3/3] Starting Web UI on :5173..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$PWD\src\ui'; npm install -q; npm run dev`"" -WindowStyle Normal

Write-Host ""
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "All services started!" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Merchant Service : http://localhost:8000/health" -ForegroundColor Yellow
Write-Host "Agent Service    : http://localhost:8001/health" -ForegroundColor Yellow
Write-Host "Web UI           : http://localhost:5173" -ForegroundColor Yellow
Write-Host ""
Write-Host "Opening browser..." -ForegroundColor Cyan
Start-Sleep -Seconds 2

# Open browser
Start-Process "http://localhost:5173"

Write-Host ""
Write-Host "Demo is running! Press Ctrl+C in any window to stop services." -ForegroundColor Cyan
Write-Host ""
