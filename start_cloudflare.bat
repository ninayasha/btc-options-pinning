@echo off
title BTC Options Pinning Dashboard (Cloudflare Tunnel)
cd /d "%~dp0"
set PYTHONPATH=.

start "Web App Backend" .venv\Scripts\python.exe main.py
timeout /t 3 /nobreak >nul
start "Cloudflare Tunnel" cloudflared.exe tunnel --url http://127.0.0.1:8088
pause
