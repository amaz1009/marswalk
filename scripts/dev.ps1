# scripts/dev.ps1 - Start backend and frontend in separate PowerShell windows
[CmdletBinding()]
param()

$repoRoot = (Split-Path -Parent $PSScriptRoot)
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "frontend"

$venvPython = Join-Path $backendDir ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Error "Run scripts\setup.ps1 first"
    exit 1
}

Write-Host "=== Starting AresNav Development Environment ===" -ForegroundColor Cyan

# Ensure PATH includes Node.js
$machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
$userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
$nodePath = "C:\Program Files\nodejs"

# Start Backend process in a new window
Write-Host "Launching Backend (FastAPI / Uvicorn) on http://127.0.0.1:8000..." -ForegroundColor Yellow
$backendCmd = "`$env:Path = '$nodePath;$machinePath;$userPath;`$env:Path'; Set-Location '$backendDir'; & '$venvPython' -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd

# Start Frontend process in a new window
Write-Host "Launching Frontend (Vite) on http://localhost:5173..." -ForegroundColor Yellow
$frontendCmd = "`$env:Path = '$nodePath;$machinePath;$userPath;`$env:Path'; Set-Location '$frontendDir'; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd

Write-Host "`nDevelopment services launched in separate windows." -ForegroundColor Green
Write-Host "Frontend: http://localhost:5173"
Write-Host "Backend API: http://127.0.0.1:8000/api/v1/health"
