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
set "LOGDIR=%USERPROFILE%\Documents\PI_Sync_Cleanup_Logs"

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

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

for /f %%a in ('powershell -NoLogo -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm-ss"') do set "STAMP=%%a"
set "LOG=%LOGDIR%\cleanup_%MODE%_%STAMP%.log"

echo ==== Cleanup (%MODE%) started %date% %time% ==== >> "%LOG%"
echo Source: %SRC% >> "%LOG%"
echo Dest  : %DEST% >> "%LOG%"
echo Flags : %ROBOFLAGS% >> "%LOG%"

REM Pre-flight: paths reachable?
if not exist "%SRC%" (
    echo ERROR: source folder not reachable: %SRC% >> "%LOG%"
    echo Is Google Drive for Desktop running and signed in? >> "%LOG%"
    exit /b 2
)
if not exist "%DEST%" (
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
