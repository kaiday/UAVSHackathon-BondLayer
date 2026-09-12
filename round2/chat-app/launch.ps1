#!/usr/bin/env pwsh
# BondLayer Demo Chat App - one-command launch (Windows / PowerShell)
#
# Starts the UCP merchant service (:8000) and the agent service (:8001), then
# the Vite dev server (:5173) if Node is installed. Node is optional: the agent
# serves a no-build fallback UI at http://127.0.0.1:8001, which is what the
# demo machine actually uses.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".env")) {
    Write-Host "No .env found. Copy .env.example to .env and add OPENAI_API_KEY." -ForegroundColor Red
    exit 1
}

Write-Host "Installing Python dependencies..." -ForegroundColor Cyan
python -m pip install -q -r requirements.txt

if (-not (Test-Path "data/records/voltway.signed.json")) {
    Write-Host "Signing demo records..." -ForegroundColor Cyan
    python scripts/make_records.py
}

# Each service gets its own window with the project as its working directory.
# Start-Job would inherit the user's home directory instead, and the relative
# package import would fail.
Write-Host "Starting merchant service on :8000..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$PSScriptRoot'; python -m src.merchant.main"
Start-Sleep -Seconds 2

Write-Host "Starting agent service on :8001..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$PSScriptRoot'; python -m src.agent.main"
Start-Sleep -Seconds 2

$npm = Get-Command npm -ErrorAction SilentlyContinue
if ($npm) {
    Write-Host "Starting Vite dev server on :5173..." -ForegroundColor Green
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$PSScriptRoot/src/ui'; npm install -q; npm run dev"
    $url = "http://localhost:5173"
} else {
    Write-Host "Node not found - skipping the Vite UI." -ForegroundColor Yellow
    Write-Host "Using the built-in fallback UI instead." -ForegroundColor Yellow
    $url = "http://127.0.0.1:8001"
}

Start-Sleep -Seconds 3
Write-Host ""
Write-Host "Merchant : http://127.0.0.1:8000/health" -ForegroundColor Yellow
Write-Host "Agent    : http://127.0.0.1:8001/health" -ForegroundColor Yellow
Write-Host "Demo UI  : $url" -ForegroundColor Yellow
Start-Process $url
