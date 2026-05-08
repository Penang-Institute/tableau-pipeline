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
`%PUBLIC%\Documents\PI_Sync_Cleanup_Logs\cleanup_DRYRUN_<timestamp>.log`.

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

> **Important: do NOT right-click → "Run as administrator".** Just
> double-click. The script depends on Drive for Desktop's `H:\` mount,
> which is per-user. Elevating into a different account (an admin /
> supervisor account) loses that mount and the script will fail at
> the pre-flight check. Plain double-click in the regular user session
> is the correct invocation.

Double-click the `.bat` file. A black console window will open for a
few seconds (or up to several minutes on first run, while ~1.7 GB of
new files get copied). When it closes:

- Check `%PUBLIC%\Documents\PI_Sync_Logs\sync_<weekday>_DD-MM-YYYY.log`
  (filename is locale-shaped, e.g. `sync_Fri_08-05-2026.log`). The very
  last line should start with `RESULT: SUCCESS …`. Anything starting
  with `WARNING` or `FAILURE` needs review.
- Also check `%PUBLIC%\Documents\PI_Sync_Logs\_invocations.log` —
  every attempted run appends one line here even if the main log was
  not produced. Useful for diagnosing hangs.
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

- **General** tab:
  - Tick *Run only when user is logged on* (NOT "whether user is
    logged on or not"). Drive for Desktop only mounts `H:\` for an
    interactively logged-on user, so the task must run in a live
    session of the operator's account.
  - **Do NOT tick *Run with highest privileges***. Elevation runs the
    task under a different security context that has no `H:\` mount —
    the task will fail at the pre-flight check exactly like a
    right-click → "Run as administrator" double-click would.
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
- **Does not:** copy Google Drive shortcut files — `.gdoc`, `.gsheet`,
  `.gslides`, `.gform`, `.gdraw`, `.gmap`, `.glnk`, `.glink`. These are
  180-byte JSON pointers to online Google Workspace documents, not real
  files. Robocopy cannot replicate their special Drive-only filesystem
  attributes to the SMB destination (it returns `Incorrect function`),
  and even if it could, the pointer only resolves from a Drive-aware
  client — they would be dead weight on the PI server. The script
  excludes them via `/XF`. Real `.xlsx`/`.csv`/`.pdf` counterparts
  alongside the shortcuts (where they exist) copy normally.
- **Does not:** fetch anything from OpenDOSM. That is still the Python
  pipeline's job, which runs every Monday on GitHub Actions.
- **Does not:** touch Google Sheets or Tableau workbooks. Separate
  concern — see `REPORT/PIC_meeting_2026-04-14.md`.

If you ever need a true mirror (e.g. quarterly cleanup of orphans on
the PI server), change `/E` to `/MIR` in the `.bat` file, run once
manually, then change it back.

---

## What a daily log looks like

Logs land in `%PUBLIC%\Documents\PI_Sync_Logs\` — that's
`C:\Users\Public\Documents\PI_Sync_Logs\` on Hajar's laptop. This
location is readable by every account on the machine (no admin
needed), so logs from any run — under her account or an admin
elevation — are always accessible to her.

Two files live there:

- `_invocations.log` — one line per attempted run, written **before**
  any external command. If this grows but `sync_<date>.log` doesn't,
  the script started but choked on something downstream (typically
  PowerShell/WMIC blocked, or a hung external call).
- `sync_<date>.log` — the per-day operational log. The three lines you
  want to glance at are:

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

### What you should see on the console (interactive runs)

When the operator double-clicks the script, the console window shows
three timestamped status lines while the run progresses:

```
[10:35:27.55] Starting sync as philip.khor (elevated=no)...
[10:35:35.10] Pre-flight OK (6550 source files). Starting robocopy (5-15 min on first run, seconds afterwards)...
[robocopy file lines stream here via /TEE during the run]
[11:10:38.19] SUCCESS - files copied + DEST extras preserved
```

These echoes exist purely to show the operator the script is alive.
Without them, the cmd window stays blank for the first 30–60 seconds
(because all internal echoes are redirected to the log file), which
historically looked indistinguishable from a hang and triggered
"close it and re-run" panic — leading to multiple concurrent robocopy
processes and self-inflicted file-lock contention. Under Task
Scheduler the console output isn't visible, but it costs nothing
there either.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Log says `source folder not reachable` | Drive for Desktop not running, or signed out | Open Drive for Desktop from the system tray; sign in with an org account |
| Log says `source folder not reachable` but `robocopy …/L` from cmd works fine | Drive for Desktop's virtual filesystem didn't respond to the pre-flight check. Fixed in script by using `dir` (forces enumeration) instead of `if not exist` (lazy `GetFileAttributes()` call that can lie against virtual filesystems). | No action — update to the latest script version. Open `H:\Shared drives\Raw Data` once in Explorer to warm the driver cache if it still happens. |
| Double-click opens a blank Command Prompt that hangs forever; no `sync_<date>.log` is produced | The script reached an external command that was blocked or stalled. Two historical culprits, both fixed in the current script: (1) PowerShell — blocked by `ExecutionPolicy=Restricted` for non-admin users on managed laptops; (2) WMIC — deprecated in Windows 11 22H2 and removed as a default feature in 24H2, where it hangs silently with no output. The current `.bat` uses neither; the date stamp comes from pure `%DATE%`/`%TIME%` parsing inside `cmd.exe` itself, which has no runtime dependency that can hang or be blocked. | Verify the operator has the **current** `.bat` (post-WMIC removal — search the file for `wmic` and confirm there are no matches). If a hang still occurs against the current script, look at `_invocations.log`: a fresh line there means the script started but choked at robocopy itself (network blip on the SMB share); no fresh line means AppLocker or antivirus is blocking `.bat` execution from that path — escalate to IT. |
| Script "ran fine" only with right-click → Run as administrator; logs end up in admin's profile and the operator can't read them | Elevation runs the script under the admin account, which has no Drive for Desktop `H:\` mount, so the script likely failed silently at pre-flight. With the latest script, all logs land in `%PUBLIC%\Documents\PI_Sync_Logs\` — readable by any account — so you can read the admin run's log too. The very last `RESULT:` line will reveal whether anything was actually copied. | Stop running with admin elevation. Use plain double-click in the operator's normal session. If IT policy blocks unelevated `.bat` execution from `C:\Scripts\`, request a whitelist exception. |
| Log says `destination folder not reachable` | Laptop is off-LAN (e.g. on a hotspot) | Check Wi-Fi is on the office network; retry |
| Scheduled run never fires | Laptop sleeping at the scheduled time | Adjust the time, or enable *Wake the computer to run this task* in the trigger |
| Some files copy every run even when unchanged | Clock drift >2s between systems | Already handled by `/FFT`. If still an issue, check time-sync (`w32tm /resync`) on both ends |
| Permission denied on a specific file | Another user has it open | Expected; robocopy retries 2× per `/R:2` flag |
| `RESULT: FAILURE` with `ERROR 1 (0x00000001) Incorrect function` on `.gdoc` / `.gsheet` files | Robocopy is trying to replicate a Google Drive shortcut file's special filesystem attributes to the SMB destination, which doesn't speak Drive. Fixed in the current script by excluding these filetypes via `/XF` (the shortcuts are useless on the PI server anyway — they only resolve from a Drive-aware client). | Verify the operator has the **current** `.bat`: open it in Notepad and confirm it contains `/XF *.gdoc *.gsheet …`. If older copies are running on other machines, replace them from the GitHub raw URL. |
| `RESULT: FAILURE` with multiple `ERROR 32 (0x00000020) The process cannot access the file because it is being used by another process` | Two or more `robocopy.exe` instances are running concurrently against the same destination, causing self-inflicted file locks. Almost always caused by an operator double-clicking the script multiple times thinking the first run had hung. | Open Task Manager → Details → kill all `robocopy.exe` processes. Wait 10 seconds. Run the script **once** and let it complete (5–15 min on first run; seconds afterwards). The newer script's console echoes prevent this footgun. |

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
   `%PUBLIC%\Documents\PI_Sync_Cleanup_Logs\cleanup_DRYRUN_<timestamp>.log`.
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
