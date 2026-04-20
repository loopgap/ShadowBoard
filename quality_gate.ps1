$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Script
    )

    Write-Host "[QualityGate] Running $Name..."
    & $Script
    if ($LASTEXITCODE -ne 0) {
        throw "[QualityGate] $Name failed with exit code $LASTEXITCODE"
    }
}

$pythonCmd = if (Test-Path ".venv/Scripts/python.exe") { "./.venv/Scripts/python.exe" } else { "python" }

Invoke-Step "Ruff" { & $pythonCmd -m ruff check . }
Invoke-Step "Pytest" { & $pythonCmd -m pytest -q }
Invoke-Step "UI Compatibility Probe" { & $pythonCmd -m pytest tests/test_ui_compatibility.py -q }
Invoke-Step "perf_check" { & $pythonCmd perf_check.py }

Write-Host "[QualityGate] All checks passed."
