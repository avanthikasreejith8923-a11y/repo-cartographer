# scripts/dev-migrate.ps1
# Runs Alembic database migrations to the latest revision.
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$VenvPython = Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment not found at $VenvPython. Please run: cd backend; python -m venv .venv; pip install -e .[dev]"
    exit 1
}

Write-Host "Running Alembic migrations against configured database..." -ForegroundColor Cyan
Set-Location (Join-Path $ProjectRoot "backend")
& $VenvPython -m alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    Write-Error "Alembic upgrade head failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}
Write-Host "Migrations successfully applied to head!" -ForegroundColor Green
