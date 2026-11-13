# Copy this bundle to ~/krakenlink on the Pi and run its installer, from a Windows laptop.
# Uses the OpenSSH client built into Windows 10/11 (ssh, scp) only.
param([Parameter(Position = 0)][string]$Pi = 'krakenrf@192.168.50.5', [switch]$Help)
$ErrorActionPreference = 'Stop'
function Fail([string]$Message, [int]$Code = 1) { [Console]::Error.WriteLine($Message); exit $Code }
if ($Help -or $Pi -eq '--help' -or $Pi -eq '-h' -or $Pi -eq '/?') { Write-Output 'Usage: deploy.bat [user@host] [-Help]'; exit 0 }
$here = $PSScriptRoot
foreach ($tool in 'ssh', 'scp') {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { Fail 'Install the Windows OpenSSH Client (Settings > Optional features)' }
}

# Same net effect as deploy.sh (mirror the folder, keeping the Pi's logs/ and bridge.toml).
# No double quotes inside the remote command: Windows PowerShell 5.1 mangles them for native commands.
$remote = @(
    'set -e'
    'rm -rf ~/krakenlink.incoming/logs ~/krakenlink.incoming/bridge.toml ~/krakenlink.incoming/.venv'
    'mkdir -p ~/krakenlink'
    'find ~/krakenlink -mindepth 1 -maxdepth 1 ! -name logs ! -name bridge.toml -exec rm -rf {} +'
    'cp -a ~/krakenlink.incoming/. ~/krakenlink/'
    'rm -rf ~/krakenlink.incoming'
    'find ~/krakenlink -name ''*.sh'' -exec sed -i ''s/\r$//'' {} +'
    'find ~/krakenlink -name ''*.sh'' -exec chmod +x {} +'
    'bash ~/krakenlink/install.sh'
) -join '; '

& ssh $Pi 'rm -rf ~/krakenlink.incoming'
if ($LASTEXITCODE -ne 0) { Fail "ssh to $Pi failed" }
& scp -r $here "${Pi}:krakenlink.incoming"
if ($LASTEXITCODE -ne 0) { Fail "scp to $Pi failed" }
& ssh -t $Pi $remote
if ($LASTEXITCODE -ne 0) { Fail "Install on $Pi failed" }
exit 0
