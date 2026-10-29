# Desktop Wellness Buddy

Desktop Wellness Buddy is a small, local Windows companion that gives gentle workday reminders, breathing prompts, stretch breaks, and short focus questions. It is intentionally offline: it does not call an API, read company systems, or send files anywhere.

## What it does

- Runs as a transparent desktop avatar with a tray icon.
- Walks using an optional full-body walk-sheet, then pauses for prompts.
- Supports click-to-pet, double-click jokes, drag-to-move, a right-click menu, and a close button.
- Provides water, check-in, stretch, and breathing reminders on a configurable weekday schedule.
- Hides temporarily when closed and returns at the next scheduled reminder.
- Starts at Windows sign-in through a per-user Task Scheduler entry.

## Requirements

- Windows 10 or Windows 11
- Python 3.10 or newer
- Permission to install user-level Python packages

## Install

Open PowerShell in this folder and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\Install-DesktopWellnessBuddy.ps1
```

The installer installs Pillow and pystray for the current user, creates a desktop shortcut, generates a generic icon, starts the buddy, and registers a per-user sign-in task.

To remove the shortcut and scheduled task:

```powershell
powershell -ExecutionPolicy Bypass -File .\Install-DesktopWellnessBuddy.ps1 -Remove
```

## Personalize it

1. Copy `config.example.json` to `config.json`.
2. Change the display name.
3. Optionally add a local `avatar.png` or `me.jpg`. These files are ignored by Git and should never be uploaded unless you deliberately choose to share them.
4. For a walking animation, add a transparent `avatar_walk.png` sprite sheet containing aligned full-body poses.
5. Run the installer again to regenerate the icon.

## Run manually

```powershell
python .\desktop_wellness_buddy.py
```

Useful flags:

- `--solid` uses a solid background if transparency does not work on a particular Windows setup.
- `--pomodoro` enables the optional focus timer.
- `--make-assets` generates the local desktop icon and exits.

## Privacy and safety

- No network calls, API keys, telemetry, or company-system connections.
- No customer data or corporate files are required.
- The app reads only the files placed in its own folder.
- The schedule is local to the Windows user who installs it.

## Current implementation

The active implementation is `desktop_wellness_buddy.py` with artwork helpers in `buddy_art.py`. The older Ember and hummingbird experiments are intentionally not part of this repository.
