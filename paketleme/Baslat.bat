@echo off
rem Yerel AI Studio (portable) - kurulum gerektirmez. Ayarlar ve sohbetler bu klasordeki data\ altinda.
cd /d "%~dp0"
if not exist "%~dp0YerelAIStudio.exe" (
  echo YerelAIStudio.exe bulunamadi. Klasoru eksiksiz kopyalayin.
  pause
  exit /b 1
)
start "" "%~dp0YerelAIStudio.exe" %*
