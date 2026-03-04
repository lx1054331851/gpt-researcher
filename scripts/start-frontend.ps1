Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $projectRoot "frontend\nextjs"

if (-not (Test-Path $frontendRoot)) {
    Write-Error "Frontend directory not found: $frontendRoot"
}

Push-Location $frontendRoot
try {
    & npm run dev
}
finally {
    Pop-Location
}

