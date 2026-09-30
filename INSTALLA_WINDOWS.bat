@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_windows.ps1"
if errorlevel 1 (
  echo.
  echo Installazione interrotta. Leggi il messaggio sopra oppure consulta la sezione Problemi comuni del README.
  pause
)
