@echo off
rem Yerel AI Studio - gelistirme baslaticisi (kaynak koddan). Paketli surum: dist\YerelAIStudio\YerelAIStudio.exe
cd /d "%~dp0"
python -m app %*
