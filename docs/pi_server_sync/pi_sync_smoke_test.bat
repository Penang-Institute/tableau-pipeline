@echo off
setlocal EnableDelayedExpansion
REM =====================================================================
REM  pi_sync_smoke_test.bat -- pre-deployment smoke test
REM
REM  Run this BEFORE deploying the real sync_drive_to_pi_server.bat to
REM  confirm Hajar's laptop is in a state where the daily job will work.
REM
REM  This script is read-only -- it writes nothing to the Shared Drive
REM  or the PI server, and creates no log files anywhere. It only prints
REM  to the console and pauses at the end so the window stays open.
REM
REM  Six checks, each clearly labelled:
REM    [locale]    -- what %DATE% / %TIME% look like for this account
REM    [elevation] -- standard user vs administrator
REM    [source]    -- is H:\Shared drives\Raw Data reachable?
REM    [dest]      -- is the PI server SMB share reachable?
REM    [wmic]      -- diagnostic only; current script no longer uses WMIC
REM    [pwsh]      -- diagnostic only; current script no longer uses PS
REM
REM  Usage: plain double-click. Do NOT right-click "Run as administrator"
REM  -- elevation drops Drive for Desktop's H:\ mount and the [source]
REM  check will fail in a way that does not match production behaviour.
REM =====================================================================

echo.
echo ============================================================
echo  PI Server Sync -- Smoke Test
echo  User      : %USERNAME%
echo  Computer  : %COMPUTERNAME%
echo  Date raw  : %DATE%
echo  Time raw  : %TIME%
echo ============================================================
echo.

REM ---- 1. Locale: show what the real script's filenames will be ----
set "DATESTAMP=%DATE%"
set "DATESTAMP=!DATESTAMP:/=-!"
set "DATESTAMP=!DATESTAMP: =_!"
echo [locale]    Daily log filename will be:
echo               sync_!DATESTAMP!.log

set "STAMP=%DATE%_%TIME%"
set "STAMP=!STAMP:/=-!"
set "STAMP=!STAMP::=-!"
set "STAMP=!STAMP: =_!"
set "STAMP=!STAMP:.=_!"
set "STAMP=!STAMP:,=_!"
echo [locale]    Cleanup log filename will be:
echo               cleanup_DRYRUN_!STAMP!.log
echo.

REM ---- 2. Elevation: must NOT be admin for the real job ----
net session >nul 2>&1
if errorlevel 1 (
    echo [elevation] OK -- standard user. This is correct for daily sync.
) else (
    echo [elevation] WRONG -- running as ADMINISTRATOR.
    echo             Google Drive for Desktop's H:\ mount is per-user, so
    echo             an elevated session has no H:\. Close this window and
    echo             plain-double-click the smoke test in Hajar's normal
    echo             session.
)
echo.

REM ---- 3. Source: is the Drive H:\ mount visible? ----
set "SRC=H:\Shared drives\Raw Data"
echo [source]    Probing !SRC! ...
dir "!SRC!" >nul 2>&1
if errorlevel 1 (
    echo [source]    FAIL -- not reachable.
    echo             Likely causes:
    echo               - Google Drive for Desktop not running or signed out
    echo               - Wrong drive letter ^(open Explorer, check H:\^)
    echo               - Running this test elevated ^(see [elevation] above^)
) else (
    set "SRC_FILES=0"
    for /f %%n in ('dir /s /b /a-d "!SRC!" 2^>nul ^| find /c /v ""') do set "SRC_FILES=%%n"
    echo [source]    OK -- !SRC_FILES! files visible.
    if !SRC_FILES! LSS 50 (
        echo [source]    WARNING -- file count below the MIN_FILES=50 floor
        echo             enforced by the cleanup script. Drive for Desktop
        echo             may still be syncing or signed into the wrong
        echo             account. Resolve before running cleanup.
    )
)
echo.

REM ---- 4. Destination: is the PI server SMB share reachable? ----
set "DEST=\\192.168.0.2\e\Research\SESP\Database\Raw Data"
echo [dest]      Probing !DEST! ...
dir "!DEST!" >nul 2>&1
if errorlevel 1 (
    echo [dest]      FAIL -- not reachable.
    echo             Likely causes:
    echo               - Laptop is off the office LAN ^(hotspot, VPN off^)
    echo               - SMB share has moved or been renamed by IT
    echo               - File server at 192.168.0.2 is down
) else (
    echo [dest]      OK
)
echo.

REM ---- 5. WMIC: diagnostic only -- the current scripts do NOT use it ----
echo [wmic]      Testing whether WMIC responds...
wmic os get Caption /value >nul 2>&1
if errorlevel 1 (
    echo [wmic]      ABSENT or BLOCKED. Expected on Windows 11 24H2+.
    echo             The current sync scripts use plain %%DATE%% parsing,
    echo             so this is fine and not a blocker.
) else (
    echo [wmic]      Available. Current scripts ignore it regardless.
)
echo.

REM ---- 6. PowerShell: diagnostic only -- current scripts do NOT use it --
echo [pwsh]      Testing whether PowerShell can run a no-op command...
powershell -NoProfile -Command "exit 0" >nul 2>&1
if errorlevel 1 (
    echo [pwsh]      BLOCKED -- ExecutionPolicy or AppLocker denies pwsh.
    echo             The current sync scripts use plain %%DATE%% parsing,
    echo             so this is fine and not a blocker.
) else (
    echo [pwsh]      Available. Current scripts ignore it regardless.
)
echo.

echo ============================================================
echo  Smoke test complete.
echo.
echo  GO/NO-GO checklist for deploying the real script:
echo    [elevation] must say OK
echo    [source]    must say OK with file count well above 50
echo    [dest]      must say OK
echo  [wmic] and [pwsh] are diagnostic only -- ignore their results.
echo ============================================================
echo.
pause
endlocal
