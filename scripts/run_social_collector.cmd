@echo off
rem ==============================================================================
rem Aviation Briefing - Automated Social Collector Runner
rem Runs scripts\collect_social.py --publish using the project Python environment.
rem Output is appended to output\social_collector.log
rem ==============================================================================

setlocal
cd /d "Q:\DEV\aviation-briefing-app"
if not exist "output" mkdir "output"

echo ============================================================ >> "output\social_collector.log"
echo [START] Social collection triggered at %DATE% %TIME% >> "output\social_collector.log"

"Q:\DEV\.venv\Scripts\python.exe" "scripts\collect_social.py" --publish >> "output\social_collector.log" 2>&1

echo [FINISH] Exit code: %ERRORLEVEL% at %DATE% %TIME% >> "output\social_collector.log"
echo ============================================================ >> "output\social_collector.log"

endlocal
exit /b %ERRORLEVEL%
