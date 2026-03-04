param(
    [string]$Host = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$NoReload
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonPath)) {
    Write-Error "Missing venv python: $pythonPath. Create/install dependencies first (for example: uv sync)."
}

$uvicornArgs = @("-m", "uvicorn", "main:app", "--host", $Host, "--port", "$Port")
if (-not $NoReload) {
    $uvicornArgs += "--reload"
}

Push-Location $projectRoot
try {
    & $pythonPath @uvicornArgs
}
finally {
    Pop-Location
}

