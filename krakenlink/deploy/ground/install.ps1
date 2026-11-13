# KrakenLink ground station installer for Windows (PowerShell 5.1 or pwsh 7).
param([switch]$Help)
$ErrorActionPreference = 'Stop'
function Fail([string]$Message, [int]$Code = 1) { [Console]::Error.WriteLine($Message); exit $Code }
if ($Help) { Write-Output 'Usage: install.bat [-Help]'; Write-Output 'Creates .venv in this folder and installs the ground app requirements.'; exit 0 }
$here = $PSScriptRoot
# Ignore an inherited PYTHONPATH so the venv only sees its own packages.
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue

function Find-Python {
    $tooOld = 'Install Python 3.9+ from python.org and tick ''Add python.exe to PATH'''
    if (Get-Command py -ErrorAction SilentlyContinue) { $exe = 'py'; $pre = @('-3') }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { $exe = 'python'; $pre = @() }
    else { Fail "Python not found. $tooOld" }
    $null = & $exe @pre -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)'
    if ($LASTEXITCODE -ne 0) { Fail "Python 3.9 or newer is required. $tooOld" }
    return ,(@($exe) + $pre)
}

$python = Find-Python
$pyExe = $python[0]; $pyArgs = @($python | Select-Object -Skip 1)
$venv = Join-Path $here '.venv'
& $pyExe @pyArgs -m venv $venv
if ($LASTEXITCODE -ne 0) { Fail 'Could not create the virtual environment (.venv).' }
$py = [IO.Path]::Combine($here, '.venv', 'Scripts', 'python.exe')
& $py -m pip install -r (Join-Path $here 'requirements.txt')
if ($LASTEXITCODE -ne 0) { Fail 'pip install failed; check the internet connection and retry.' }
$env:PYTHONPATH = $here
& $py -c 'import krakenlink.ground.app'
$ok = $LASTEXITCODE -eq 0
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
if (-not $ok) { Fail 'Import check of krakenlink.ground.app failed.' }
Write-Output 'Ground app installed.'
exit 0
