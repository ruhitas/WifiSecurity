# Wireless IDS + AI Platform — Phase 2 one-command setup (Windows / PowerShell)
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "== Wireless IDS dev environment setup ==" -ForegroundColor Cyan

# 1. .env
if (-not (Test-Path "$root\.env")) {
    Copy-Item "$root\.env.example" "$root\.env"
    Write-Host "Created .env from .env.example (edit ES credentials before use)." -ForegroundColor Yellow
}

# 2. Infra containers
Write-Host "`n-- Starting infrastructure (Kafka, Prometheus, Grafana, MLflow) --" -ForegroundColor Cyan
docker compose up -d

# 3. Python venv + core deps
if (-not (Test-Path "$root\.venv")) {
    Write-Host "`n-- Creating Python virtual environment (.venv) --" -ForegroundColor Cyan
    python -m venv "$root\.venv"
}
$py = "$root\.venv\Scripts\python.exe"
& $py -m pip install --upgrade pip | Out-Null
Write-Host "-- Installing core Python dependencies --" -ForegroundColor Cyan
& $py -m pip install -r "$root\requirements.txt"

# 4. Wait for Kafka, create topics
Write-Host "`n-- Waiting for Kafka to become ready --" -ForegroundColor Cyan
Start-Sleep -Seconds 20
& $py "$root\scripts\create_topics.py"

# 5. Verify
Write-Host "`n-- Verifying environment --" -ForegroundColor Cyan
& $py "$root\scripts\verify_env.py"

Write-Host "`nDone. UIs: Kafka=http://localhost:8081  Grafana=http://localhost:3000  Prometheus=http://localhost:9090  MLflow=http://localhost:5000" -ForegroundColor Green
