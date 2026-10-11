# scripts/dev-api.ps1
# Starts FastAPI backend with auto-reload.
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$VenvPython = Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment not found at $VenvPython."
    exit 1
}

Write-Host "Starting FastAPI development server on http://127.0.0.1:8000 with reload..." -ForegroundColor Cyan
Set-Location (Join-Path $ProjectRoot "backend")
& $VenvPython -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
