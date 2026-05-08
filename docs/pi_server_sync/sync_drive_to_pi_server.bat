@echo off
REM =====================================================================
REM  Sync Google Drive (Shared Drive) -> PI Server (SMB)
REM
REM  Runs on a Windows laptop that has BOTH:
REM    - Google Drive for Desktop mounted at H:\Shared drives\
REM    - LAN access to \\192.168.0.2\e\
REM
REM  Replaces the old Philip-Khor workflow. Does not require R, Python,
REM  or the GitHub Actions pipeline — it only mirrors the already-synced
REM  Drive folder to the office file server.
REM =====================================================================

REM ---- EDIT THESE TWO PATHS TO MATCH THE LAPTOP ------------------------
REM  SOURCE: the path Drive for Desktop mirrors the shared drive to.
REM          Confirm the exact drive letter by opening Explorer ->
REM          "H:\Shared drives\" and seeing what folder appears.
set "SRC=H:\Shared drives\Raw Data"

REM  DEST: the PI server share path.
set "DEST=\\192.168.0.2\e\Research\SESP\Database\Raw Data"

REM  Where to keep a rolling log of each run (created if missing).
REM  %PUBLIC% = C:\Users\Public\ — readable AND writable by every account
REM  on the machine, with or without elevation. Avoids the trap where a
REM  script run "as administrator" lands its log in the admin's profile,
REM  out of reach of the regular user.
set "LOGDIR=%PUBLIC%\Documents\PI_Sync_Logs"
REM ---------------------------------------------------------------------

if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul

REM Always-on invocation marker: written BEFORE any external command so
REM that even if a downstream call hangs, we have evidence the script
REM was invoked, by whom, and whether it was elevated. One line per run
REM accumulates in _invocations.log (separate from the per-day sync log).
net session >nul 2>&1
if errorlevel 1 (set "ELEVATED=no") else (set "ELEVATED=yes")
echo %date% %time% invoked by %USERNAME% [elevated=%ELEVATED%] >> "%LOGDIR%\_invocations.log"

REM Console-visible status lines. Without these the cmd window stays blank
REM for the first 30-60 seconds until robocopy starts streaming via /TEE,
REM which looks indistinguishable from a hang and triggers "kill it and
REM re-run" panic. Three plain echoes (NOT redirected to the log) at the
REM moments that matter give clear "I'm working" signals on the console
REM while the log captures the full detail underneath.
echo [%TIME%] Starting sync as %USERNAME% (elevated=%ELEVATED%)...

REM Date stamp using only built-in cmd parsing -- no PowerShell, no WMIC.
REM Both have failure modes on managed laptops: PowerShell can be blocked
REM by ExecutionPolicy=Restricted for non-admin users; WMIC was deprecated
REM in Windows 11 22H2 and removed as a default feature in 24H2, where it
REM hangs silently with no output. Plain %DATE% is locale-dependent but
REM is available to every account on every supported Windows. We normalise
REM slashes and spaces so the result is a valid filename component.
REM Example on en-GB locale: "Fri 08/05/2026" -> "Fri_08-05-2026".
set "DATESTAMP=%DATE%"
set "DATESTAMP=%DATESTAMP:/=-%"
set "DATESTAMP=%DATESTAMP: =_%"
set "LOG=%LOGDIR%\sync_%DATESTAMP%.log"

echo ==== Sync started %date% %time% ==== >> "%LOG%"
echo Source: %SRC% >> "%LOG%"
echo Dest  : %DEST% >> "%LOG%"

REM Pre-flight checks -- bail out loudly if the source or dest is missing.
REM NOTE: use `dir` instead of `if not exist` because Drive for Desktop
REM exposes paths via a virtual filesystem. `if not exist` calls
REM GetFileAttributes() which can falsely report "no such file" against
REM that driver until the path is enumerated. `dir` forces enumeration.
dir "%SRC%" >nul 2>&1
if errorlevel 1 (
    echo ERROR: source folder not reachable: %SRC% >> "%LOG%"
    echo Is Google Drive for Desktop running and signed in? >> "%LOG%"
    exit /b 2
)
dir "%DEST%" >nul 2>&1
if errorlevel 1 (
    echo ERROR: destination folder not reachable: %DEST% >> "%LOG%"
    echo Is the laptop on the office LAN? >> "%LOG%"
    exit /b 3
)

REM Objective-evidence pre-check: count files visible on SRC and write to
REM the log. Gives a quick sanity signal ("does the tree look right?")
REM and a baseline you can compare across daily runs. A sudden drop in
REM this number is a red flag even when robocopy itself returns 0.
set "SRC_FILES=0"
for /f %%n in ('dir /s /b /a-d "%SRC%" 2^>nul ^| find /c /v ""') do set "SRC_FILES=%%n"
echo Source file count: %SRC_FILES% >> "%LOG%"
echo [%TIME%] Pre-flight OK (%SRC_FILES% source files). Starting robocopy (5-15 min on first run, seconds afterwards)...

REM Robocopy flags explained:
REM   /E     = copy all subdirs including empty ones, ADD-ONLY (never
REM            deletes on dest). Chosen over /MIR so a glitchy Drive
REM            sync cannot wipe the PI server. Orphans on dest are
REM            cleaned up manually or via a separate monthly /MIR run.
REM   /FFT   = use FAT file times (2-second granularity). Prevents
REM            robocopy from re-copying unchanged files due to tiny
REM            NTFS-vs-SMB timestamp drift.
REM   /R:2   = retry 2 times on a locked/network-blipped file
REM   /W:5   = wait 5 s between retries
REM   /NP    = no per-file % progress (keeps the log short)
REM   /NDL   = no directory listing
REM   /TEE   = write to console AND log
REM   /XF    = exclude Google Drive shortcut files. These are 180-byte
REM            JSON pointers (.gdoc/.gsheet/.gslides/...) that live on
REM            Drive's virtual filesystem with special attributes.
REM            Robocopy's default /COPY:DAT (data + attrs + timestamps)
REM            tries to replicate those attributes to the SMB destination,
REM            which returns "Incorrect function" (Win32 error 1) because
REM            plain SMB doesn't speak Drive-shortcut. Excluding them is
REM            correct: they are useless on the PI server anyway because
REM            the link only resolves from a Drive-aware client. Real
REM            .xlsx/.csv/.pdf files alongside (where they exist) still
REM            copy normally.
robocopy "%SRC%" "%DEST%" /E /FFT /R:2 /W:5 /NP /NDL /TEE /XF *.gdoc *.gsheet *.gslides *.gform *.gdraw *.gmap *.glnk *.glink >> "%LOG%" 2>&1

set RC=%ERRORLEVEL%
echo ==== Sync finished %date% %time% (robocopy exit=%RC%) ==== >> "%LOG%"

REM Translate the robocopy exit code into a one-line human summary so
REM the log is glanceable without reading the full robocopy block.
REM (Robocopy codes are additive bitflags: 1=copied, 2=extras, 4=mismatch,
REM 8+=failure. 0-7 are all operational success.)
set "SUMMARY=unknown state"
if %RC% EQU 0 set "SUMMARY=SUCCESS - no changes needed, DEST already matches SRC"
if %RC% EQU 1 set "SUMMARY=SUCCESS - new/changed files copied to DEST"
if %RC% EQU 2 set "SUMMARY=SUCCESS - extras on DEST preserved (expected with /E)"
if %RC% EQU 3 set "SUMMARY=SUCCESS - files copied + DEST extras preserved"
if %RC% EQU 4 set "SUMMARY=WARNING - mismatched files present, review log"
if %RC% EQU 5 set "SUMMARY=WARNING - copied + mismatches, review log"
if %RC% EQU 6 set "SUMMARY=WARNING - extras + mismatches, review log"
if %RC% EQU 7 set "SUMMARY=WARNING - copied + extras + mismatches, review log"
if %RC% GEQ 8 set "SUMMARY=FAILURE - robocopy reported fatal errors, see above"
echo RESULT: %SUMMARY% (source files seen: %SRC_FILES%, robocopy exit=%RC%) >> "%LOG%"
echo [%TIME%] %SUMMARY%

REM Robocopy exit codes: 0 = no change, 1 = files copied, 2 = extra files,
REM 3 = 1+2, >=8 = real failure. Treat 0-7 as success for Task Scheduler.
if %RC% GEQ 8 (exit /b %RC%) else (exit /b 0)
