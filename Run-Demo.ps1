# Desktop Wellness Buddy local demo launcher.
# This starts the generic mascot without installing a scheduled task or changing Windows startup.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

if (-not (Get-Command python.exe -ErrorAction SilentlyContinue)) {
    throw "Python 3.10 or newer is required. Install Python, then run this demo again."
}

python.exe .\desktop_wellness_buddy.py --solid
