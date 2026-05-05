@echo off
REM =====================================================================
REM  Cleanup pass: mirror Drive -> PI Server, DELETING orphans on dest.
REM
REM  The daily job (sync_drive_to_pi_server.bat) is add-only (/E). Over
REM  time the PI server accumulates files that were deleted on the
REM  Shared Drive. This script reconciles them.
REM
REM  This script is DESTRUCTIVE. Run manually, not on a schedule.
REM
REM  Usage:
REM    sync_drive_to_pi_server_cleanup.bat            (dry-run, default)
REM    sync_drive_to_pi_server_cleanup.bat CONFIRM    (real run, deletes)
REM
REM  Standard workflow:
REM    1. Run without arguments. Review the preview log carefully.
REM    2. If the list of deletions looks correct, re-run with CONFIRM.
REM =====================================================================

REM ---- Keep paths identical to the daily script ------------------------
set "SRC=H:\Shared drives\Raw Data"
set "DEST=\\192.168.0.2\e\Research\SESP\Database\Raw Data"
REM Logs go to %PUBLIC% (C:\Users\Public\) so they are readable by both
REM the operator's account and any admin account that may have run the
REM script. Avoids the trap where elevated runs land logs in the admin's
REM profile, out of reach of the regular user.
set "LOGDIR=%PUBLIC%\Documents\PI_Sync_Cleanup_Logs"

REM Minimum file count the SRC must contain before we allow a real run.
REM Guards against Drive-for-Desktop being signed out (showing empty).
REM Tune upward if the Raw Data folder is known to have many more files.
set "MIN_FILES=50"
REM ---------------------------------------------------------------------

if /i "%~1"=="CONFIRM" (
    set "MODE=REAL"
    set "ROBOFLAGS=/MIR /FFT /R:2 /W:5 /NP /NDL /TEE"
) else (
    set "MODE=DRYRUN"
    REM /L = list only, no changes. /MIR still reports what would delete.
    set "ROBOFLAGS=/MIR /FFT /L /R:2 /W:5 /NP /NDL /TEE"
)

if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul

REM Locale-safe timestamp via WMIC (no PowerShell dependency, works for
REM restricted users where PowerShell may be blocked by execution
REM policy). WMIC LocalDateTime format: YYYYMMDDhhmmss.mmmmmm+TZN
for /f "skip=1" %%a in ('wmic os get LocalDateTime') do (
    if not defined DT set "DT=%%a"
)
set "STAMP=%DT:~0,4%-%DT:~4,2%-%DT:~6,2%_%DT:~8,2%-%DT:~10,2%-%DT:~12,2%"
set "LOG=%LOGDIR%\cleanup_%MODE%_%STAMP%.log"

echo ==== Cleanup (%MODE%) started %date% %time% ==== >> "%LOG%"
echo Source: %SRC% >> "%LOG%"
echo Dest  : %DEST% >> "%LOG%"
echo Flags : %ROBOFLAGS% >> "%LOG%"

REM Pre-flight: paths reachable?
REM Use `dir` rather than `if not exist` so Drive for Desktop's virtual
REM filesystem is forced to enumerate the path (GetFileAttributes lies
REM against that driver; see sync_drive_to_pi_server.bat for details).
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

REM Pre-flight: does SRC have a plausible number of files?
REM Counts files (not dirs) recursively. If fewer than MIN_FILES, abort.
set "COUNT=0"
for /f %%n in ('dir /s /b /a-d "%SRC%" 2^>nul ^| find /c /v ""') do set "COUNT=%%n"
echo Source file count: %COUNT% (min required: %MIN_FILES%) >> "%LOG%"

if %COUNT% LSS %MIN_FILES% (
    echo ERROR: source has only %COUNT% files, below MIN_FILES=%MIN_FILES%. >> "%LOG%"
    echo Refusing to run. Drive for Desktop may be signed out or still syncing. >> "%LOG%"
    exit /b 5
)

if /i "%MODE%"=="REAL" (
    echo. >> "%LOG%"
    echo *** REAL RUN: files missing from SRC WILL BE DELETED on DEST *** >> "%LOG%"
    echo. >> "%LOG%"
) else (
    echo. >> "%LOG%"
    echo *** DRY RUN: no files will be changed. Review actions below. *** >> "%LOG%"
    echo *** Re-run with CONFIRM argument to apply them. *** >> "%LOG%"
    echo. >> "%LOG%"
)

robocopy "%SRC%" "%DEST%" %ROBOFLAGS% >> "%LOG%" 2>&1

set RC=%ERRORLEVEL%
echo ==== Cleanup (%MODE%) finished %date% %time% (robocopy exit=%RC%) ==== >> "%LOG%"

REM Robocopy: 0-7 = ok (various combos of copied/extra/mismatch), >=8 = fail.
if %RC% GEQ 8 (exit /b %RC%) else (exit /b 0)
