@echo off
cd /d "%~dp0"
if not exist logs mkdir logs
python -m vixguard check --quiet
if errorlevel 1 echo [%date% %time%] check failed with exit %errorlevel% >> logs\check-errors.log
