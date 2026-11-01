@echo off
rem Start the web viewer / power logger. Settings: web\config.json
cd /d "%~dp0.."
py -3.13 web\server.py
pause
