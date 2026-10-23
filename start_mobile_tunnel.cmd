@echo off
chcp 65001 >nul
title Aviation Briefing Mobil & Cloudflare Tunnel
echo ============================================================
echo   Aviation Briefing Mobil Sunucu ve Guvenli Tunel
echo ============================================================
cd /d "Q:\DEV\aviation-briefing-app"
start "Aviation Dev Server" /b "..\.venv\Scripts\python.exe" scripts\dev_server.py 8090
timeout /t 2 >nul
echo.
echo [OK] Yerel sunucu 8090 portunda aktif.
echo [*] Guvenli Cloudflare tuneli baslatiliyor...
echo.
echo ============================================================
echo Asagida beliren https://....trycloudflare.com linkini 
echo telefonunuzun Safari tarayicisinda acabilirsiniz.
echo ============================================================
echo.
"..\tools\bin\cloudflared.exe" tunnel --url http://localhost:8090
pause
