@echo off
rem Kairo'yu PENCERE ACMADAN yalniz yerel sunucu olarak calistirir (Ollama gibi).
rem Diger uygulamalar: Ollama uyumlu http://127.0.0.1:11434 , OpenAI uyumlu http://127.0.0.1:11434/v1
rem Kapatmak icin: Sunucu-Durdur.bat (port Ayarlar'da degistirildiyse oradaki portu yazin).
cd /d "%~dp0"
start "" "%~dp0Kairo.exe" --sunucu
echo Yerel sunucu arka planda baslatildi: http://127.0.0.1:11434
timeout /t 3 >nul
