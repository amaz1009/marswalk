# scripts/setup.ps1 - Environment setup for AresNav (Backend venv + Frontend dependencies)
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = (Split-Path -Parent $PSScriptRoot)

Write-Host "=== AresNav Setup ===" -ForegroundColor Cyan
Write-Host "Repository root: $repoRoot"

# 1. Ensure PATH has Node.js and Python if present in machine/user environment
$machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
$userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
$env:Path = "$machinePath;$userPath;$env:Path"
if (Test-Path "C:\Program Files\nodejs") {
    $env:Path = "C:\Program Files\nodejs;$env:Path"
}

# 2. Select Python 3.12 via Windows launcher
try {
    $pyVer = & py -3.12 --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "py -3.12 returned exit code $LASTEXITCODE"
    }
} catch {
    Write-Error "Python 3.12 was not found via the Windows launcher (py -3.12). Please ensure Python 3.12 and the Windows Python launcher are installed."
    exit 1
}

Write-Host "Using Python: $pyVer"

# 3. Create virtual environment at backend\.venv
$venvDir = Join-Path $repoRoot "backend\.venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment at backend\.venv..." -ForegroundColor Yellow
    & py -3.12 -m venv $venvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create virtual environment at $venvDir"
        exit 1
    }
} else {
    Write-Host "Virtual environment already exists at $venvDir" -ForegroundColor Green
}

# 4. Install backend editable with dev extras
Write-Host "Installing backend editable dependencies (backend[dev])..." -ForegroundColor Yellow
$backendPath = Join-Path $repoRoot "backend"
& $venvPython -m pip install -e "$backendPath[dev]"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install backend dependencies."
    exit 1
}

# 5. Frontend install and API type generation
$frontendDir = Join-Path $repoRoot "frontend"
Write-Host "Installing frontend dependencies via npm in $frontendDir..." -ForegroundColor Yellow
Push-Location $frontendDir
try {
    npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Error "npm install failed in $frontendDir"
        exit 1
    }

    Write-Host "Generating TypeScript types from OpenAPI schema..." -ForegroundColor Yellow
    npm run gen:api
    if ($LASTEXITCODE -ne 0) {
        Write-Error "npm run gen:api failed in $frontendDir"
        exit 1
    }
} finally {
    Pop-Location
}

Write-Host "`nSetup completed successfully!" -ForegroundColor Green
