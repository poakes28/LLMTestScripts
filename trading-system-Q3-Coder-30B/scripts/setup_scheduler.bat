@echo off
REM ============================================================================
REM Windows Task Scheduler Setup for Trading System
REM 
REM Run as Administrator to create scheduled tasks.
REM Adjust PYTHON_PATH and PROJECT_DIR for your environment.
REM ============================================================================

SET PYTHON_PATH=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe
SET PROJECT_DIR=%~dp0..
SET LOG_DIR=%PROJECT_DIR%\logs

REM --- Morning Price Pull (10:00 AM CT) ---
schtasks /create /tn "Trading_PricePull_Morning" ^
    /tr "\"%PYTHON_PATH%\" \"%PROJECT_DIR%\scripts\collect.py\"" ^
    /sc daily /st 10:00 ^
    /f /rl HIGHEST
echo Created: Morning Price Pull (10:00 AM)

REM --- Midday Price Pull (12:00 PM CT) ---
schtasks /create /tn "Trading_PricePull_Midday" ^
    /tr "\"%PYTHON_PATH%\" \"%PROJECT_DIR%\scripts\collect.py\"" ^
    /sc daily /st 12:00 ^
    /f /rl HIGHEST
echo Created: Midday Price Pull (12:00 PM)

REM --- Closing Price Pull (4:00 PM CT) ---
schtasks /create /tn "Trading_PricePull_Closing" ^
    /tr "\"%PYTHON_PATH%\" \"%PROJECT_DIR%\scripts\collect.py\" --update-paper" ^
    /sc daily /st 16:00 ^
    /f /rl HIGHEST
echo Created: Closing Price Pull (4:00 PM)

REM --- Fundamentals Pull (Saturday at 8:00 AM, weekly) ---
schtasks /create /tn "Trading_Fundamentals" ^
    /tr "\"%PYTHON_PATH%\" \"%PROJECT_DIR%\scripts\collect.py\" --fundamentals" ^
    /sc weekly /d SAT /st 08:00 ^
    /f /rl HIGHEST
echo Created: Weekly Fundamentals Pull (Sat 8:00 AM)

REM --- Analysis Engine (5:00 PM CT daily) ---
schtasks /create /tn "Trading_Analysis" ^
    /tr "\"%PYTHON_PATH%\" \"%PROJECT_DIR%\scripts\analyze.py\"" ^
    /sc daily /st 17:00 ^
    /f /rl HIGHEST
echo Created: Analysis Engine (5:00 PM)

REM --- Email Report (6:00 AM CT daily) ---
schtasks /create /tn "Trading_EmailReport" ^
    /tr "\"%PYTHON_PATH%\" \"%PROJECT_DIR%\scripts\report.py\"" ^
    /sc daily /st 06:00 ^
    /f /rl HIGHEST
echo Created: Email Report (6:00 AM)

echo.
echo ============================================================
echo All tasks created. Verify with: schtasks /query /tn "Trading_*"
echo.
echo Edit PYTHON_PATH and PROJECT_DIR if needed.
echo Tasks run Mon-Fri only in production (add /d MON,TUE,WED,THU,FRI)
echo ============================================================
pause
