@echo off
rem Temiz venv'de PyInstaller ile derler (genis site-packages taramasi derlemeyi bozar; bkz. LESSONS).
rem Cikti: dist\YerelAIStudio\YerelAIStudio.exe
setlocal
cd /d "%~dp0.."
if not exist .venv-derle (
  python -m venv .venv-derle || exit /b 1
)
call .venv-derle\Scripts\activate.bat
python -m pip install -q --upgrade pip setuptools
rem pywebview ve bagimliliklari onceden taranmis yerel paketlerden (varsa) kurulur
if exist "%TEMP%\tarama-pywebview" (
  python -m pip install -q --no-index --find-links "%TEMP%\tarama-pywebview" --no-build-isolation pywebview==6.2.1 setuptools
)
python -m pip install -q -r requirements.txt pyinstaller==6.19.0 || exit /b 1
pyinstaller --noconfirm --clean paketleme\yerel-ai-studio.spec || exit /b 1

copy /y paketleme\Baslat.bat dist\YerelAIStudio\ >nul

copy /y paketleme\BENIOKU.txt dist\YerelAIStudio\ >nul
copy /y paketleme\Sunucu.bat dist\YerelAIStudio\ >nul
copy /y paketleme\Sunucu-Durdur.bat dist\YerelAIStudio\ >nul
echo.
echo Derlendi (portable): dist\YerelAIStudio\Baslat.bat
endlocal
