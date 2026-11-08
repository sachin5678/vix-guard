@echo off
cd /d "%~dp0"
python -m vixguard run
if errorlevel 1 pause
