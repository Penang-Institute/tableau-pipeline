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
set "LOGDIR=%USERPROFILE%\Documents\PI_Sync_Logs"
REM ---------------------------------------------------------------------

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

REM Locale-safe date stamp via PowerShell (works regardless of Windows
REM regional date format; %date% parsing breaks under US/EU locales).
for /f %%a in ('powershell -NoLogo -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "DATESTAMP=%%a"
set "LOG=%LOGDIR%\sync_%DATESTAMP%.log"

echo ==== Sync started %date% %time% ==== >> "%LOG%"
echo Source: %SRC% >> "%LOG%"
echo Dest  : %DEST% >> "%LOG%"

REM Pre-flight checks -- bail out loudly if the source or dest is missing
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
robocopy "%SRC%" "%DEST%" /E /FFT /R:2 /W:5 /NP /NDL /TEE >> "%LOG%" 2>&1

set RC=%ERRORLEVEL%
echo ==== Sync finished %date% %time% (robocopy exit=%RC%) ==== >> "%LOG%"

REM Robocopy exit codes: 0 = no change, 1 = files copied, 2 = extra files,
REM 3 = 1+2, >=8 = real failure. Treat 0-7 as success for Task Scheduler.
if %RC% GEQ 8 (exit /b %RC%) else (exit /b 0)
