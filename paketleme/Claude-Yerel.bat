@echo off
setlocal
rem Claude Code'u Yerel AI Studio'daki yerel modelle acar (bulut yok, API anahtari yok).
rem Kullanim: Claude-Yerel.bat [model]   (varsayilan gemma4-e4b-heretic)
rem Studio acik olmali (pencere ya da Sunucu.bat). Calisilacak klasorde acin.
set "MODEL=%~1"
if "%MODEL%"=="" set "MODEL=gemma4-e4b-heretic"
if "%PORT%"=="" set "PORT=11434"
curl -s -m 3 http://127.0.0.1:%PORT%/api/version | find "yerel_ai_studio" >nul
if errorlevel 1 (
  echo Yerel AI Studio calismiyor. Sunucu.bat ile baslatiliyor...
  start "" "%~dp0YerelAIStudio.exe" --sunucu
  timeout /t 8 >nul
)
where claude >nul 2>nul
if errorlevel 1 (
  echo Claude Code bulunamadi. Kurulum: npm install -g @anthropic-ai/claude-code
  pause
  exit /b 1
)
set "ANTHROPIC_BASE_URL=http://127.0.0.1:%PORT%"
set "ANTHROPIC_AUTH_TOKEN=local"
set "ANTHROPIC_API_KEY="
set "ANTHROPIC_MODEL=%MODEL%"
set "ANTHROPIC_DEFAULT_HAIKU_MODEL=%MODEL%"
set "ANTHROPIC_DEFAULT_SONNET_MODEL=%MODEL%"
set "ANTHROPIC_DEFAULT_OPUS_MODEL=%MODEL%"
set "CLAUDE_CODE_SUBAGENT_MODEL=%MODEL%"
set "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1"
set "CLAUDE_CODE_MAX_OUTPUT_TOKENS=4096"
set "CLAUDE_CODE_MAX_CONTEXT_TOKENS=32768"
set "API_TIMEOUT_MS=3600000"
echo Claude Code yerel modelle: %MODEL%  (ilk cevap dahili GPU'da birkac dakika surebilir)
claude --strict-mcp-config --tools "Bash,Read,Edit,Write,Glob,Grep"
