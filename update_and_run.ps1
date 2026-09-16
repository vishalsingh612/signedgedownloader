# Signedge Downloader - PowerShell Script to Pull & Run on VM
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host " Signedge Downloader - Update & Launch Dashboard" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Pulling latest code from GitHub..." -ForegroundColor Yellow
git pull origin main

if (Test-Path "venv\Scripts\Activate.ps1") {
    Write-Host "Activating virtual environment..." -ForegroundColor Yellow
    .\venv\Scripts\Activate.ps1
}

Write-Host ""
Write-Host "Launching Dashboard & Scheduler Server..." -ForegroundColor Green
python src/dashboard.py
