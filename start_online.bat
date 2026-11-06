@echo off
title BTC Options Pinning Dashboard (Online - Ngrok Static Domain)
echo ========================================================
echo  Starting BTC Options Pinning Dashboard (Ngrok Static)
echo  Permanent URL: https://underuse-pamperer-dish.ngrok-free.dev
echo ========================================================
cd /d "%~dp0"
set PYTHONPATH=.

start "Web App Backend (Port 8088)" .venv\Scripts\python.exe main.py
timeout /t 3 /nobreak >nul
start "Ngrok Tunnel (Permanent Domain)" ngrok.exe http 8088 --url underuse-pamperer-dish.ngrok-free.dev
echo.
echo ========================================================
echo  System started successfully!
echo  Your permanent URL:
echo  https://underuse-pamperer-dish.ngrok-free.dev
echo ========================================================
pause
