# scripts/dev-worker.ps1
# Starts ARQ background worker.
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$VenvPython = Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment not found at $VenvPython."
    exit 1
}

Write-Host "Starting ARQ background worker process (WorkerSettings)..." -ForegroundColor Cyan
Set-Location (Join-Path $ProjectRoot "backend")
$env:PYTHONIOENCODING = "utf-8"
while ($true) {
    & $VenvPython -m arq app.worker.WorkerSettings
    Write-Warning "Worker stopped or connection interrupted. Reconnecting in 2 seconds..."
    Start-Sleep -Seconds 2
}
