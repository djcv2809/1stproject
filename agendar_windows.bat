@echo off
rem Cria a tarefa diária das 10:00. Clique duas vezes neste arquivo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0agendar_windows.ps1"
echo.
pause
