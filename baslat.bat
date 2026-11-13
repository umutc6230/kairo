@echo off
rem Kairo - gelistirme baslaticisi (kaynak koddan). Paketli surum: dist\Kairo\Kairo.exe
cd /d "%~dp0"
python -m app %*
