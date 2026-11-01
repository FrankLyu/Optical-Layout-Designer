@echo off
rem Opens the first layout (A to Z) in 421nm_system in the Optical Layout Designer.
cd /d "%~dp0"
for /f "delims=" %%f in ('dir /b /a-d /on "421nm_system\*.json"') do (
    py -3.13 run.py "421nm_system\%%f"
    goto done
)
echo No layouts found in 421nm_system.
:done
if errorlevel 1 pause
