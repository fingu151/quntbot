@echo off
cd /d "%~dp0.."
powershell.exe -ExecutionPolicy Bypass -File "scripts\start_public_dashboard_with_refresh.ps1" -Port 8520 -HostAddress 0.0.0.0 -BrowserAddress localhost -RefreshIntervalMinutes 30 -RunTimeoutMinutes 10 -RefreshedThrough 2026-05-15
