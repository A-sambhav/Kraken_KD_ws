# Flash the KrakenLink ESP32-S3 firmware in this folder on Windows (PowerShell 5.1 or pwsh 7).
param([string]$Port = '', [switch]$Help)
$ErrorActionPreference = 'Stop'
function Fail([string]$Message, [int]$Code = 1) { [Console]::Error.WriteLine($Message); exit $Code }
if ($Help) { Write-Output 'Usage: flash.bat [-Port COMx] [-Help]'; exit 0 }
$here = $PSScriptRoot
$role = Split-Path -Leaf $here
if ($role -ne 'air' -and $role -ne 'ground') { Fail "flash.ps1 must be in a folder named air or ground (got: $role)" 2 }
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue

$bin = Join-Path $here 'firmware.bin'
$sha = Join-Path $here 'firmware.sha256'
if (-not (Test-Path -LiteralPath $bin)) { Fail 'Missing firmware.bin; run make_dist.sh --firmware' }
if (-not (Test-Path -LiteralPath $sha)) { Fail 'Missing firmware.sha256; run make_dist.sh --firmware' }
$expected = ((Get-Content -LiteralPath $sha -TotalCount 1).Trim() -split '\s+')[0]
$actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $bin).Hash
if ($actual -ne $expected) { Fail "firmware.bin: SHA-256 mismatch (expected $expected, got $actual)" }
Write-Output 'firmware.bin: OK'

function Find-Python {
    $tooOld = 'Install Python 3.9+ from python.org and tick ''Add python.exe to PATH'''
    if (Get-Command py -ErrorAction SilentlyContinue) { $exe = 'py'; $pre = @('-3') }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { $exe = 'python'; $pre = @() }
    else { Fail "Python not found. $tooOld" }
    $null = & $exe @pre -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)'
    if ($LASTEXITCODE -ne 0) { Fail "Python 3.9 or newer is required. $tooOld" }
    return ,(@($exe) + $pre)
}

$py = [IO.Path]::Combine($here, '.venv', 'Scripts', 'python.exe')
if (-not (Test-Path -LiteralPath $py)) {
    $python = Find-Python
    $pyExe = $python[0]; $pyArgs = @($python | Select-Object -Skip 1)
    & $pyExe @pyArgs -m venv (Join-Path $here '.venv')
    if ($LASTEXITCODE -ne 0) { Fail 'Could not create the virtual environment (.venv).' }
}
$null = & $py -c 'import importlib.util, sys; sys.exit(0 if importlib.util.find_spec(''esptool'') else 1)'
if ($LASTEXITCODE -ne 0) {
    & $py -m pip install esptool==4.8.1
    if ($LASTEXITCODE -ne 0) { Fail 'pip install esptool failed; check the internet connection and retry.' }
}

if (-not $Port) {
    $found = @(& $py (Join-Path $here 'find_port.py') | Where-Object { $_.Trim() })
    if ($found.Count -ne 1) {
        [Console]::Error.WriteLine("Expected exactly one CH343 (1a86) device; found $($found.Count):")
        foreach ($dev in $found) { [Console]::Error.WriteLine("  $dev") }
        Fail 'Pass the ESP32-S3 COM port with -Port COMx'
    }
    $Port = $found[0].Trim()
}
Write-Output "Flashing $role firmware to $Port"
& $py -m esptool --chip esp32s3 --port $Port --baud 460800 write_flash 0x0 $bin
if ($LASTEXITCODE -ne 0) { Fail 'Flash failed; hold BOOT, tap RESET, then retry.' }
exit 0
