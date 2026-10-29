# Install Desktop Wellness Buddy. Run once from PowerShell in this folder.
# Adds user-level Python packages, a per-user sign-in task, and a desktop shortcut.
# Undo with: .\Install-DesktopWellnessBuddy.ps1 -Remove
param([switch]$Remove)
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$startupDir = [Environment]::GetFolderPath("Startup")
$desktopDir = [Environment]::GetFolderPath("Desktop")
$startup = Join-Path $startupDir "Desktop Wellness Buddy.lnk"
$desktop = Join-Path $desktopDir "Desktop Wellness Buddy.lnk"
$taskName = "Desktop Wellness Buddy"
# Old shortcut names from earlier versions, removed so two copies never start.
$old = @((Join-Path $startupDir "Byte.lnk"), (Join-Path $desktopDir "Byte.lnk"), (Join-Path $startupDir "Skye.lnk"), (Join-Path $desktopDir "Skye.lnk"))
if ($Remove) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Remove-Item $startup, $desktop, $old -ErrorAction SilentlyContinue
    Write-Host "Removed the Desktop Wellness Buddy scheduled task and shortcut."
    exit
}
Remove-Item $old -ErrorAction SilentlyContinue
Write-Host "Step 1 of 3: installing Pillow and pystray (your user only)..."
python -m pip install --user pillow pystray
if ($LASTEXITCODE -ne 0) { Write-Host "pip failed. Copy the error to C and stop here."; exit 1 }
Write-Host "Step 2 of 3: making her icon..."
Push-Location $here
python desktop_wellness_buddy.py --make-assets
Pop-Location
$exe = python -c "import sys; print(sys.executable)"
$pyw = $exe -replace "python\.exe$", "pythonw.exe"
if (-not (Test-Path $pyw)) { $pyw = $exe }
Write-Host "Step 3 of 3: creating the scheduled task and desktop shortcut..."
$sh = New-Object -ComObject WScript.Shell
$l = $sh.CreateShortcut($desktop)
$l.TargetPath = $pyw
$l.Arguments = '"' + (Join-Path $here "desktop_wellness_buddy.py") + '"'
$l.WorkingDirectory = $here
$l.IconLocation = (Join-Path $here "desktop_wellness_buddy.ico")
$l.WindowStyle = 7
$l.Save()
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $pyw -Argument ('"' + (Join-Path $here "desktop_wellness_buddy.py") + '"') -WorkingDirectory $here
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$trigger.Delay = 'PT30S'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Starts the local Desktop Wellness Buddy at sign in." -Force | Out-Null
Start-Process $pyw -ArgumentList ('"' + (Join-Path $here "desktop_wellness_buddy.py") + '"') -WorkingDirectory $here
Write-Host "Done. Desktop Wellness Buddy is starting and will also start 30 seconds after future sign-ins."
