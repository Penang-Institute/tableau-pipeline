# PI Server Sync — Setup Guide for Hajar's Laptop

This folder contains a one-script replacement for the old
`copy_opendosm.R` LAN-copy workflow. It mirrors the organisational
Shared Drive (synced by Google Drive for Desktop) to the internal file
server at `\\192.168.0.2\e\Research\SESP\Database\Raw Data`.

The Python pipeline on GitHub Actions already keeps the Shared Drive
current — this script just closes the last-mile gap to the PI server,
which the cloud runner cannot reach.

---

## Pre-flight checklist (ask Hajar to confirm before doing anything)

1. **Google Drive for Desktop installed and signed in?**
   - Open File Explorer. Is there a `G:\Shared drives\` path with the
     SESP folder visible inside?
   - Which Google account is signed in (system tray → Drive icon → gear)?
     It must be an org account with access to the Shared Drive.
2. **SMB share reachable?**
   - Paste `\\192.168.0.2\e\Research\SESP\Database` into File Explorer
     address bar. Does it open?
3. **Is this laptop left on during office hours?**
   - The scheduled task only fires while the laptop is awake. If it
     usually sleeps, wake-from-schedule must be enabled (see step 4
     below).

If any answer is "no" → stop and resolve that first. Do not run the
script until all three are "yes".

---

## One-time setup

### 1. Copy the script to the laptop

Put `sync_drive_to_pi_server.bat` somewhere persistent, e.g.
`C:\Scripts\sync_drive_to_pi_server.bat`. Do not put it on the Desktop
or in Downloads — Task Scheduler will lose it if the file moves.

### 2. Edit the paths

Open the `.bat` file in Notepad and confirm the two paths near the top:

```bat
set "SRC=G:\Shared drives\SESP\Raw Data"
set "DEST=\\192.168.0.2\e\Research\SESP\Database\Raw Data"
```

- `SRC` — the exact Drive-for-Desktop path. Names vary by drive; open
  `G:\Shared drives\` in Explorer and copy the real folder name.
- `DEST` — keep as-is unless the IT department has moved the share.

### 3. Test-run manually first

Double-click the `.bat` file. A black console window will open for a
few seconds. When it closes:

- Check `%USERPROFILE%\Documents\PI_Sync_Logs\sync_YYYY-MM-DD.log`.
  It should end with `(robocopy exit=0)` through `(robocopy exit=7)`.
  Exit code ≥ 8 means a real failure — the log will say why.
- Open the destination folder and confirm files appear / update.

Do this at least once before scheduling.

### 4. Schedule with Windows Task Scheduler

Open **Task Scheduler** → *Create Basic Task…*

| Field | Value |
|---|---|
| Name | `Sync Drive to PI Server` |
| Description | Mirrors G:\Shared drives\SESP\Raw Data to \\192.168.0.2\e\… once a day |
| Trigger | Daily, 09:15 (or whenever the office PC is reliably awake) |
| Action | Start a program |
| Program/script | `C:\Scripts\sync_drive_to_pi_server.bat` |
| Start in (optional) | `C:\Scripts` |

After creating, open the task → *Properties*:

- **General** tab → tick *Run whether user is logged on or not* and
  *Run with highest privileges*.
- **Conditions** tab → untick *Start the task only if the computer is
  on AC power* (safer if the laptop runs on battery sometimes).
- **Settings** tab → tick *Run task as soon as possible after a
  scheduled start is missed* (covers weekends/holidays).

Click *OK*. Windows will prompt for the account password — this is
whatever account Hajar uses to log into the laptop.

### 5. Right-click → *Run* once

Confirms the task actually runs end-to-end with the stored credentials,
not just when the file is double-clicked interactively.

---

## What the script does (and doesn't do)

- **Does:** one-way copy Drive → PI server. Files that appear on the
  Shared Drive end up on the SMB share. Files deleted on the Shared
  Drive will also be deleted on the PI server (because `/MIR`).
- **Does not:** fetch anything from OpenDOSM. That is still the Python
  pipeline's job, which runs every Monday on GitHub Actions.
- **Does not:** touch Google Sheets or Tableau workbooks. Separate
  concern — see `REPORT/PIC_meeting_2026-04-14.md`.

If you want add-only (never delete on dest), change `/MIR` to `/E` in
the `.bat` file.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Log says `source folder not reachable` | Drive for Desktop not running, or signed out | Open Drive for Desktop from the system tray; sign in with an org account |
| Log says `destination folder not reachable` | Laptop is off-LAN (e.g. on a hotspot) | Check Wi-Fi is on the office network; retry |
| Scheduled run never fires | Laptop sleeping at the scheduled time | Adjust the time, or enable *Wake the computer to run this task* in the trigger |
| Some files copy every run even when unchanged | Clock drift between systems | Add `/FFT` to the robocopy flags (FAT file time, 2-second tolerance) |
| Permission denied on a specific file | Another user has it open | Expected; robocopy retries 2× per `/R:2` flag |

---

## Rollback

If this ever needs to be disabled, just delete the scheduled task in
Task Scheduler. The script itself does nothing on its own. No other
system depends on it.
