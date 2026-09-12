#!/usr/bin/env pwsh
# BondLayer Chat App — Phase P0 Launch (Windows/PowerShell)

Write-Host "🚀 BondLayer Chat App — Phase P0 Launch" -ForegroundColor Cyan
Write-Host ""

# Install Python dependencies
Write-Host "📦 Installing Python dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt -q
if ($LASTEXITCODE -ne 0) { exit 1 }

# Install Node dependencies
Write-Host "📦 Installing Node dependencies..." -ForegroundColor Yellow
Push-Location src/ui
npm install -q
if ($LASTEXITCODE -ne 0) { exit 1 }
Pop-Location

Write-Host ""
Write-Host "✓ Dependencies installed" -ForegroundColor Green
Write-Host ""
Write-Host "🔥 Starting services..." -ForegroundColor Cyan
Write-Host ""
Write-Host "Merchant Service (:8000)"
Write-Host "Agent Service (:8001)"
Write-Host "UI Server (:5173)"
Write-Host ""
Write-Host "Open http://localhost:5173" -ForegroundColor Green
Write-Host ""

# Function to handle cleanup
$jobs = @()

try {
    # Start merchant service in background
    $merchantJob = Start-Job -ScriptBlock {
        python -m src.merchant.main
    }
    $jobs += $merchantJob
    Write-Host "✓ Merchant service started (PID: $($merchantJob.Id))" -ForegroundColor Green

    # Start agent service in background
    $agentJob = Start-Job -ScriptBlock {
        python -m src.agent.main
    }
    $jobs += $agentJob
    Write-Host "✓ Agent service started (PID: $($agentJob.Id))" -ForegroundColor Green

    Write-Host ""

    # Start UI in current process
    Push-Location src/ui
    npm run dev
    Pop-Location
}
finally {
    # Cleanup: stop all background jobs
    Write-Host ""
    Write-Host "Stopping services..." -ForegroundColor Yellow
    foreach ($job in $jobs) {
        Stop-Job -Job $job -ErrorAction SilentlyContinue
        Remove-Job -Job $job -ErrorAction SilentlyContinue
    }
    Write-Host "✓ Services stopped" -ForegroundColor Green
}
