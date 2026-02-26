param()

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$PythonExe = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

Write-Host "Running static checks" -ForegroundColor Cyan
& $PythonExe -m ruff check .

Write-Host "Running unit tests" -ForegroundColor Cyan
& $PythonExe -m pytest -q

Write-Host "Running performance checks" -ForegroundColor Cyan
& $PythonExe perf_check.py

Write-Host "All quality gates passed" -ForegroundColor Green
