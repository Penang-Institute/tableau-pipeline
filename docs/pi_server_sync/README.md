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
   - Open File Explorer. Is there an `H:\Shared drives\` path with the
     `Raw Data` folder visible inside?
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

## Before the first run — preview what will be copied

Neither script can delete anything on the Shared Drive (robocopy is
strictly one-way: `SRC → DEST`, never reverse). Still, walk through
this sequence once before scheduling anything, so there are no
surprises.

### Step 1 — Inspect the manifest

Open [`tableau-pipeline/opendosm.tsv`](../../opendosm.tsv). This is the
authoritative list of files the Python pipeline uploads to the Shared
Drive. Today it contains **114 CSVs** across ~20 subfolders
(Demography, Economy/GDP, Labour, Health, Finance, etc). No other file
types should appear in `Raw Data/` under normal operation.

If you see `.xlsx`, `.zip`, `.pdf`, or similar in the Shared Drive,
they got there through a route other than this pipeline — note them
before running cleanup so they aren't mistakenly deleted.

### Step 2 — Eyeball the Shared Drive

On the laptop:

```
File Explorer → H:\Shared drives\Raw Data\
```

Right-click the folder → *Properties*. Confirm the file count is in
the expected range (well above 50). If it looks mostly empty, Drive
for Desktop is still syncing or signed out — **stop and resolve before
proceeding**.

### Step 3 — Read-only preview of the daily copy

From Command Prompt (no script needed, no edits to any file):

```bat
robocopy "H:\Shared drives\Raw Data" "\\192.168.0.2\e\Research\SESP\Database\Raw Data" /E /FFT /L /NP /TEE /LOG+:"%USERPROFILE%\Desktop\preview_%DATE:/=-%.log"
```

The `/L` flag means *list only, write nothing*. `/TEE` echoes output
to the console **and** appends it to a timestamped log on the Desktop
(`preview_<today>.log`), so you have a file to review afterwards
rather than just scrollback.

Expected output on first run: lots of `New File` lines. On subsequent
runs: nearly empty output (only changed files).

### Step 4 — Compare both sides via the cleanup dry-run

```bat
sync_drive_to_pi_server_cleanup.bat
```

Log lands in
`%USERPROFILE%\Documents\PI_Sync_Cleanup_Logs\cleanup_DRYRUN_<timestamp>.log`.

Interpret the lines:

| Prefix | Meaning | Destructive? |
|---|---|---|
| `New File` | Missing on PI server, would be copied | No — same as daily job |
| `Newer` / `Older` | Different timestamps, would be overwritten on PI server | No — updates PI server only |
| `*EXTRA File` | Present on PI server, missing on Drive — would be **deleted** if you later run with `CONFIRM` | **Yes — read these carefully** |
| `*EXTRA Dir` | Same as above, for whole folders | **Yes** |

If step 4 shows zero `*EXTRA` lines, the cleanup script would change
nothing and is safe to skip entirely.

### Step 5 — Only now, schedule the daily job

Proceed to *One-time setup* below. Do **not** run the cleanup script
with `CONFIRM` on day one — let the daily job run for a few weeks so
you have a baseline understanding of what normal logs look like before
ever deleting anything.

---

## One-time setup

### 1. Copy the script to the laptop

Put `sync_drive_to_pi_server.bat` somewhere persistent, e.g.
`C:\Scripts\sync_drive_to_pi_server.bat`. Do not put it on the Desktop
or in Downloads — Task Scheduler will lose it if the file moves.

### 2. Edit the paths

Open the `.bat` file in Notepad and confirm the two paths near the top:

```bat
set "SRC=H:\Shared drives\Raw Data"
set "DEST=\\192.168.0.2\e\Research\SESP\Database\Raw Data"
```

- `SRC` — the exact Drive-for-Desktop path. The drive letter (H: on
  Hajar's laptop) can vary by machine; open `H:\Shared drives\` in
  Explorer and copy the real folder name if it differs.
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
| Description | Mirrors H:\Shared drives\Raw Data to \\192.168.0.2\e\… once a day |
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

- **Does:** one-way **add-only** copy Drive → PI server. Files that
  appear on the Shared Drive end up on the SMB share. Files deleted on
  the Shared Drive are **kept** on the PI server (because `/E`, not
  `/MIR`). This is deliberate — it protects against a signed-out or
  glitchy Drive client wiping the server.
- **Does not:** fetch anything from OpenDOSM. That is still the Python
  pipeline's job, which runs every Monday on GitHub Actions.
- **Does not:** touch Google Sheets or Tableau workbooks. Separate
  concern — see `REPORT/PIC_meeting_2026-04-14.md`.

If you ever need a true mirror (e.g. quarterly cleanup of orphans on
the PI server), change `/E` to `/MIR` in the `.bat` file, run once
manually, then change it back.

---

## What a daily log looks like

Each run writes a single file at
`%USERPROFILE%\Documents\PI_Sync_Logs\sync_YYYY-MM-DD.log`. The three
lines you want to glance at are:

```
==== Sync started Fri 24/04/2026 09:15:02.11 ====
Source file count: 6550
...
==== Sync finished Fri 24/04/2026 09:18:47.92 (robocopy exit=3) ====
RESULT: SUCCESS - files copied + DEST extras preserved (source files seen: 6550, robocopy exit=3)
```

- **`Source file count`** — objective sanity signal. If this number ever
  drops sharply compared to previous days, something is wrong with the
  Shared Drive (signed out, folder renamed, permissions changed).
- **`RESULT: ...`** — one-line human-readable verdict. Anything starting
  with `SUCCESS` is operationally fine. `WARNING` means review the log
  in detail. `FAILURE` means robocopy itself reported fatal errors.

Between those two lines is robocopy's own output — you rarely need it
unless the RESULT line is not `SUCCESS`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Log says `source folder not reachable` | Drive for Desktop not running, or signed out | Open Drive for Desktop from the system tray; sign in with an org account |
| Log says `source folder not reachable` but `robocopy …/L` from cmd works fine | Drive for Desktop's virtual filesystem didn't respond to the pre-flight check. Fixed in script by using `dir` (forces enumeration) instead of `if not exist` (lazy `GetFileAttributes()` call that can lie against virtual filesystems). | No action — update to the latest script version. Open `H:\Shared drives\Raw Data` once in Explorer to warm the driver cache if it still happens. |
| Log says `destination folder not reachable` | Laptop is off-LAN (e.g. on a hotspot) | Check Wi-Fi is on the office network; retry |
| Scheduled run never fires | Laptop sleeping at the scheduled time | Adjust the time, or enable *Wake the computer to run this task* in the trigger |
| Some files copy every run even when unchanged | Clock drift >2s between systems | Already handled by `/FFT`. If still an issue, check time-sync (`w32tm /resync`) on both ends |
| Permission denied on a specific file | Another user has it open | Expected; robocopy retries 2× per `/R:2` flag |

---

## Quarterly cleanup (optional, manual)

The daily job never deletes anything on the PI server — that is
intentional (see above). Over time orphan files accumulate on the
server because they were deleted from the Shared Drive. To reconcile,
use `sync_drive_to_pi_server_cleanup.bat`.

**This script is destructive. Do not schedule it.**

### Workflow

1. Open a Command Prompt in the same folder as the script.
2. Run a **dry-run** first (no arguments):

   ```bat
   sync_drive_to_pi_server_cleanup.bat
   ```

   A log appears in
   `%USERPROFILE%\Documents\PI_Sync_Cleanup_Logs\cleanup_DRYRUN_<timestamp>.log`.
   Lines marked `*EXTRA File` are what *would* be deleted from the PI
   server. Read through them.

3. If the list is correct, re-run with `CONFIRM`:

   ```bat
   sync_drive_to_pi_server_cleanup.bat CONFIRM
   ```

   This performs the actual `/MIR` and writes a `cleanup_REAL_*.log`.

### Built-in safeguards

- **Dry-run by default.** Must pass `CONFIRM` to delete anything.
- **Minimum source file count.** Aborts (exit 5) if the Shared Drive
  has fewer than 50 files — catches the Drive-signed-out scenario
  before it wipes the server. Adjust `MIN_FILES` inside the script if
  the real folder is smaller.
- **Same path pre-flight checks** as the daily script (exits 2 or 3 if
  `SRC` or `DEST` is unreachable).
- **Separate log folder** (`PI_Sync_Cleanup_Logs`) so dry-run records
  don't clutter the daily history.

### When to run it

- Quarterly, as routine hygiene.
- After a deliberate big deletion on the Shared Drive (e.g. archive
  folder moved elsewhere).
- **Never** on a cron / scheduled task.

---

## Rollback

If this ever needs to be disabled, just delete the scheduled task in
Task Scheduler. The script itself does nothing on its own. No other
system depends on it.
