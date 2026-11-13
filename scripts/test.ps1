# scripts/test.ps1 - Run all backend and frontend tests and exit non-zero on failure
[CmdletBinding()]
param()

$repoRoot = (Split-Path -Parent $PSScriptRoot)
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "frontend"

$machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
$userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
$env:Path = "C:\Program Files\nodejs;$machinePath;$userPath;$env:Path"

$venvPython = Join-Path $backendDir ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Error "Run scripts\setup.ps1 first"
    exit 1
}

$backendSuccess = $true
$frontendTypecheckSuccess = $true
$frontendTestSuccess = $true

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Running MARSWALK Test Suite" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. Backend tests
Write-Host "`n[1/3] Running Backend Tests (pytest)..." -ForegroundColor Yellow
Push-Location $backendDir
try {
    & $venvPython -m pytest tests
    if ($LASTEXITCODE -ne 0) {
        $backendSuccess = $false
    }
} catch {
    $backendSuccess = $false
} finally {
    Pop-Location
}

# 2. Frontend typecheck
Write-Host "`n[2/3] Running Frontend Typecheck (tsc)..." -ForegroundColor Yellow
Push-Location $frontendDir
try {
    npm run typecheck
    if ($LASTEXITCODE -ne 0) {
        $frontendTypecheckSuccess = $false
    }
} catch {
    $frontendTypecheckSuccess = $false
} finally {
    Pop-Location
}

# 3. Frontend unit tests
Write-Host "`n[3/3] Running Frontend Unit Tests (vitest)..." -ForegroundColor Yellow
Push-Location $frontendDir
try {
    npm run test
    if ($LASTEXITCODE -ne 0) {
        $frontendTestSuccess = $false
    }
} catch {
    $frontendTestSuccess = $false
} finally {
    Pop-Location
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host " Test Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Backend pytest:       $(if ($backendSuccess) { 'PASSED' } else { 'FAILED' })" -ForegroundColor $(if ($backendSuccess) { 'Green' } else { 'Red' })
Write-Host "Frontend typecheck:   $(if ($frontendTypecheckSuccess) { 'PASSED' } else { 'FAILED' })" -ForegroundColor $(if ($frontendTypecheckSuccess) { 'Green' } else { 'Red' })
Write-Host "Frontend vitest:      $(if ($frontendTestSuccess) { 'PASSED' } else { 'FAILED' })" -ForegroundColor $(if ($frontendTestSuccess) { 'Green' } else { 'Red' })

if ($backendSuccess -and $frontendTypecheckSuccess -and $frontendTestSuccess) {
    Write-Host "`nOverall Result: ALL TESTS PASSED (exit code 0)" -ForegroundColor Green
    exit 0
} else {
    Write-Host "`nOverall Result: TEST FAILURES DETECTED (exit code 1)" -ForegroundColor Red
    exit 1
}
