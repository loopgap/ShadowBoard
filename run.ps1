param(
    [switch]$SkipInstall,
    [ValidateSet("web", "cli")]
    [string]$Mode = "web"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

$PythonExe = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$StateDir = Join-Path $PSScriptRoot ".semi_agent"
if (-not (Test-Path $StateDir)) {
    New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
}
$SetupStamp = Join-Path $StateDir "setup_stamp.json"
$ReqPath = Join-Path $PSScriptRoot "requirements.txt"

function Get-FileFingerprint([string]$path) {
    if (-not (Test-Path $path)) {
        return "missing"
    }
    $item = Get-Item $path
    return "{0}|{1}" -f $item.Length, $item.LastWriteTimeUtc.Ticks
}

$NeedsSetupCheck = $true
$CurrentReqFingerprint = Get-FileFingerprint $ReqPath

if (Test-Path $SetupStamp) {
    try {
        $stamp = Get-Content -Path $SetupStamp -Raw | ConvertFrom-Json
        if ($stamp.req_fingerprint -eq $CurrentReqFingerprint -and $stamp.mode -eq "ok") {
            $NeedsSetupCheck = $false
        }
    } catch {
        $NeedsSetupCheck = $true
    }
}

if (-not $SkipInstall -and $NeedsSetupCheck) {
    $needsPackages = & $PythonExe -c "import importlib.util as u; print(not(u.find_spec('playwright') and u.find_spec('gradio') and u.find_spec('pytest') and u.find_spec('ruff')))"
    if ($needsPackages -eq "True") {
        & $PythonExe -m pip install --disable-pip-version-check -r requirements.txt
        & $PythonExe -m pip install --disable-pip-version-check pytest ruff
    }

    $browserReady = & $PythonExe -c "from pathlib import Path; import os; p=Path(os.environ.get('LOCALAPPDATA',''))/'ms-playwright'; print(any(p.glob('chromium-*')))"
    if ($browserReady -ne "True") {
        Write-Host "[Hint] Playwright Chromium browser is missing. Run this once before first login:" -ForegroundColor Yellow
        Write-Host "       .venv\Scripts\python.exe -m playwright install chromium" -ForegroundColor Yellow
    }

    @{ mode = "ok"; req_fingerprint = $CurrentReqFingerprint; updated_at = (Get-Date).ToUniversalTime().ToString("o") } |
        ConvertTo-Json | Set-Content -Path $SetupStamp -Encoding UTF8
}

if ($Mode -eq "cli") {
    & $PythonExe main.py
} else {
    & $PythonExe web_app.py
}
