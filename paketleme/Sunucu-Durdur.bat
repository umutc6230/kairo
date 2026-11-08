@echo off
rem Arka planda (Sunucu.bat ile) calisan Yerel AI Studio sunucusunu kapatir.
set "PORT=%1"
if "%PORT%"=="" set "PORT=11434"
curl -s -X POST http://127.0.0.1:%PORT%/api/yerel/kapat
echo.
timeout /t 3 >nul
