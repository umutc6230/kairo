@echo off
rem Kairo (portable) - kurulum gerektirmez. Ayarlar ve sohbetler bu klasordeki data\ altinda.
cd /d "%~dp0"
if not exist "%~dp0Kairo.exe" (
  echo Kairo.exe bulunamadi. Klasoru eksiksiz kopyalayin.
  pause
  exit /b 1
)
start "" "%~dp0Kairo.exe" %*
