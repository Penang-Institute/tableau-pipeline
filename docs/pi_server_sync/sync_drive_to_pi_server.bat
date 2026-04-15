@echo off
REM =====================================================================
REM  Sync Google Drive (Shared Drive) -> PI Server (SMB)
REM
REM  Runs on a Windows laptop that has BOTH:
REM    - Google Drive for Desktop mounted at G:\Shared drives\
REM    - LAN access to \\192.168.0.2\e\
REM
REM  Replaces the old Philip-Khor workflow. Does not require R, Python,
REM  or the GitHub Actions pipeline — it only mirrors the already-synced
REM  Drive folder to the office file server.
REM =====================================================================

REM ---- EDIT THESE TWO PATHS TO MATCH THE LAPTOP ------------------------
REM  SOURCE: the path Drive for Desktop mirrors the shared drive to.
REM          Confirm the exact drive name by opening Explorer ->
REM          "G:\Shared drives\" and seeing what folder appears.
set "SRC=G:\Shared drives\SESP\Raw Data"

REM  DEST: the PI server share path.
set "DEST=\\192.168.0.2\e\Research\SESP\Database\Raw Data"

REM  Where to keep a rolling log of each run (created if missing).
set "LOGDIR=%USERPROFILE%\Documents\PI_Sync_Logs"
REM ---------------------------------------------------------------------

if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set "LOG=%LOGDIR%\sync_%date:~-4%-%date:~3,2%-%date:~0,2%.log"

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
REM   /MIR   = mirror (copies new/changed, deletes files in dest that
REM            no longer exist in src). Drop /MIR -> /E if you want
REM            "add only, never delete".
REM   /R:2   = retry 2 times on a locked/network-blipped file
REM   /W:5   = wait 5 s between retries
REM   /NP    = no per-file % progress (keeps the log short)
REM   /NDL   = no directory listing
REM   /TEE   = write to console AND log
robocopy "%SRC%" "%DEST%" /MIR /R:2 /W:5 /NP /NDL /TEE >> "%LOG%" 2>&1

set RC=%ERRORLEVEL%
echo ==== Sync finished %date% %time% (robocopy exit=%RC%) ==== >> "%LOG%"

REM Robocopy exit codes: 0 = no change, 1 = files copied, 2 = extra files,
REM 3 = 1+2, >=8 = real failure. Treat 0-7 as success for Task Scheduler.
if %RC% GEQ 8 (exit /b %RC%) else (exit /b 0)
