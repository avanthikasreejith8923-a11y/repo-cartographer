# scripts/dev-frontend.ps1
# Starts frontend Vite development server.
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$FrontendDir = Join-Path $ProjectRoot "frontend"

Write-Host "Starting Vite frontend server on http://localhost:5173..." -ForegroundColor Cyan
Set-Location $FrontendDir
npm run dev
