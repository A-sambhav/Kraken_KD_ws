# Start the KrakenLink ground station on Windows (PowerShell 5.1 or pwsh 7).
param([string]$Port = '', [switch]$NoBrowser, [switch]$Help)
$ErrorActionPreference = 'Stop'
function Fail([string]$Message, [int]$Code = 1) { [Console]::Error.WriteLine($Message); exit $Code }
if ($Help) { Write-Output 'Usage: run_ground.bat [-Port COMx] [-NoBrowser] [-Help]'; exit 0 }
$here = $PSScriptRoot
# Ignore an inherited PYTHONPATH so the venv only sees its own packages.
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
$py = [IO.Path]::Combine($here, '.venv', 'Scripts', 'python.exe')
if (-not (Test-Path -LiteralPath $py)) { Fail 'Missing .venv; run install.bat first' }

if (-not $Port) {
    Push-Location $here
    try { $found = @(& $py -m krakenlink.tools.ports --esp | Where-Object { $_.Trim() }) } finally { Pop-Location }
    if ($found.Count -eq 0) { Fail 'No GROUND ESP32 port found (plug it into its COM port or pass -Port COMx)' }
    $Port = $found[0].Trim()
}
Write-Output "Using GROUND ESP32 on $Port"

# TOML basic strings treat backslash as an escape (e.g. \\.\COM10).
$template = [IO.File]::ReadAllText((Join-Path $here 'ground.toml.in'))
$text = $template.Replace('@GROUND_PORT@', $Port.Replace('\', '\\'))
[IO.File]::WriteAllText((Join-Path $here 'ground.toml'), $text, (New-Object Text.UTF8Encoding $false))

$url = 'http://127.0.0.1:8050'
$proc = Start-Process -FilePath $py -ArgumentList @('-m', 'krakenlink.ground', '--config', 'ground.toml') -WorkingDirectory $here -NoNewWindow -PassThru
$null = $proc.Handle  # keep a handle so ExitCode is available after exit
$code = 1
try {
    if (-not $NoBrowser) {
        for ($i = 0; $i -lt 60 -and -not $proc.HasExited; $i++) {
            try {
                Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 1 | Out-Null
                Start-Process $url
                break
            } catch { Start-Sleep -Seconds 1 }
        }
    }
    $proc.WaitForExit()
    $code = $proc.ExitCode
} finally {
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
}
exit $code
