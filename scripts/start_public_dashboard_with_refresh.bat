@echo off
cd /d "%~dp0.."
powershell.exe -ExecutionPolicy Bypass -File "scripts\start_public_dashboard_with_refresh.ps1" -Port 8520 -RefreshIntervalMinutes 30
