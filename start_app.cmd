@echo off
chcp 65001 >nul
title Aviation Briefing Mobile App
echo ============================================================
echo   Aviation Briefing Mobile Server Baslatiliyor...
echo ============================================================
cd /d "Q:\DEV\aviation-briefing-app"
"..\.venv\Scripts\python.exe" server.py 8090
pause
