# scripts/dev-all.ps1
# One-command development starter for repo-cartographer:
# Opens API, worker, and frontend each in its own new PowerShell window,
# runs system diagnostics with scripts/doctor.py, and outputs the frontend link.
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$VenvPython = Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"

Write-Host "=== Starting repo-cartographer development environment ===" -ForegroundColor Cyan

# 1. Start FastAPI backend server in a new window
Write-Host "Starting API server in a new window..." -ForegroundColor Green
Start-Process powershell.exe -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $ProjectRoot "scripts\dev-api.ps1") -WorkingDirectory $ProjectRoot
Start-Sleep -Seconds 2

# 2. Start ARQ background worker in a new window
Write-Host "Starting background worker in a new window..." -ForegroundColor Green
Start-Process powershell.exe -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $ProjectRoot "scripts\dev-worker.ps1") -WorkingDirectory $ProjectRoot
Start-Sleep -Seconds 2

# 3. Start Frontend Vite server in a new window
Write-Host "Starting frontend server in a new window..." -ForegroundColor Green
Start-Process powershell.exe -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $ProjectRoot "scripts\dev-frontend.ps1") -WorkingDirectory $ProjectRoot
Start-Sleep -Seconds 2

# 4. Run Doctor verification script
Write-Host "`nRunning system doctor health checks..." -ForegroundColor Cyan
if (Test-Path $VenvPython) {
    & $VenvPython (Join-Path $ProjectRoot "scripts\doctor.py")
} else {
    python (Join-Path $ProjectRoot "scripts\doctor.py")
}

# 5. Print access link
Write-Host "`nAll development services started!" -ForegroundColor Green
Write-Host "Open the application in your browser: http://localhost:5173" -ForegroundColor Yellow
