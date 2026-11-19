<h1 align="center">Kairo</h1>

<p align="center">
  <strong>A desktop AI agent for Windows that runs on local or cloud models.</strong>
</p>

<p align="center">
  <img alt="Platform" src="https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6?logo=windows&logoColor=white">
  <img alt="Python" src="https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.129-009688?logo=fastapi&logoColor=white">
  <img alt="llama.cpp" src="https://img.shields.io/badge/llama.cpp-Vulkan-8A2BE2">
  <img alt="OpenRouter" src="https://img.shields.io/badge/OpenRouter-supported-6467F2">
  <img alt="Portable" src="https://img.shields.io/badge/install-portable-success">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-yellow.svg"></a>
</p>

<p align="center">
  <a href="#features">Features</a> ·
  <a href="#getting-started">Getting Started</a> ·
  <a href="#development">Development</a> ·
  <a href="#security">Security</a>
</p>

---

Kairo is a desktop AI agent for Windows. It works with local, uncensored models on your own machine
(via llama.cpp) or with cloud models through OpenRouter. It can chat, write code inside a project
folder, run commands, research the web, and drive both the browser and native desktop applications.
The interface follows the Claude Desktop layout, and its skills, plugins, hooks and MCP support are
compatible with Claude Code.

Built with Python 3.12, FastAPI and pywebview, with a vanilla JavaScript UI. Kairo is fully portable:
no installer and no administrator rights required.

**Product Owner: Umut Çelik** · [X](https://x.com/umutc6230) · [GitHub](https://github.com/umutc6230)

> The interface is available in Turkish and English: **Settings > Appearance > Dil / Language**.

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Getting Started](#getting-started)
- [Development](#development)
- [Security](#security)
- [License](#license)
- [Third-Party Notices](#third-party-notices)

## Features

### Models and providers
- **Local (llama.cpp, Vulkan):** GGUF models with RAM requirement, capability and file-status labels;
  8K / 16K / 32K context sizes; a warning when free RAM is insufficient.
- **OpenRouter:** add / validate / delete API keys (masked, kept on the backend only), live model
  list (24-hour cache with Refresh), search, "free only" filter, price / context / tools / vision
  badges, and a Test button that uses the real request format (latency, tokens, cost).
- **Model store (Hugging Face):** search GGUF models with a "Runs / Struggles / Won't run" indicator
  based on this machine's RAM and disk. Downloads resume where they stopped and are verified with SHA256.
- **Local server (Ollama-style):** while Kairo is running, its models are available to other apps.
  Ollama-compatible at `http://127.0.0.1:11434` (`/api/tags`, `/api/show`, `/api/chat`,
  `/api/generate`) and OpenAI-compatible under `/v1` (`/v1/models`, `/v1/chat/completions`).
  Headless mode: `Sunucu.bat` / `Sunucu-Durdur.bat`.
- **Claude Code with a local model:** the server also exposes Anthropic-compatible endpoints
  (`/v1/messages`, `/v1/messages/count_tokens`); `Claude-Yerel.bat [model]` runs Claude Code with
  no cloud and no API key.

### Chat
- Streaming responses, **Stop**, a live thinking block that collapses when done, thinking levels
  (Off / Balanced / Deep), history, search, rename, fork and export.
- **Attachments:** images (OCR / visual Q&A), PDFs (text layer or page-by-page OCR), audio
  (wav/mp3, Gemma 4) and text files. Drag-and-drop and paste. Context budget for earlier attachments.
- **Chat plan** and **tool groups:** consecutive tool steps collapse into a single row
  ("4 reads done"), and every step can be expanded and inspected.
- **Slash commands:** `/compact`, `/cost`, `/todos`, `/export`, `/rewind`, `/resume`, `/rename`,
  `/init`, `/loop`, `/add-dir`, `/bashes`, `/usage`, `/output-style`, `/diff`, `/review`,
  `/security-review`, plus custom commands from `.claude/commands`. `/` and `@` completion,
  `!command` and `#note` shortcuts.
- **Side chat panel** (Ctrl+;), **voice dictation** (local Gemma 4), **memory** (sourced, editable,
  import / export) and proactive suggestions on the empty screen.

### Agent
- **Projects / workspaces:** pick a folder, recent projects, multi-root workspaces.
- **Permission modes:** Plan / Ask / Auto and **Full access**. Approval scope can be once, per chat
  or always. Even in full access, risky actions (payments, deletion, sending, publishing, disk
  formatting, `git push --force`) still ask. Sensitive files (`.env`, SSH keys, passwords) are never read.
- **Tools:** read / list / search files, patch and write (hash check + atomic write + checkpoint),
  terminal (background jobs, stop), git status / diff / branch / commit, LSP definition / references / diagnostics.
- **Undo:** file- and hunk-level checkpoints; `reset --hard` is never used.
- **Persistent task loop:** step / time / token budgets, pause / resume / cancel, steering while
  running, crash recovery, and no "success" without evidence. Live step stream and terminal output.
- **Sub-agents and work orders:** parallel sub-agents on remote providers, isolated `git worktree`
  branches, a team board and typed workflows.
- **Code review:** evidence-based findings from `git diff` (severity, file:line, verification hint).
- **Isolation (optional):** run commands inside a Podman / Docker container with networking disabled.

### Persistent agents and automation
- **Agents:** long-lived agents with a name, instructions, folder, model and memory; job queue,
  agent-to-agent messaging and conversation logs.
- **CLI agents:** drive the Claude Code, Codex and Antigravity CLIs as agent providers.
- **Routines:** scheduled tasks (templates, one-off / recurring, end conditions, act or notify).
- **Telegram and webhooks:** assign work to an agent from an allowed chat; webhook events land in the agent's queue.
- **Activity (audit) window**, Windows notifications, and keep-awake.

### Web, browser and desktop
- **Web search and page reading** (DuckDuckGo; Exa and Parallel connectors).
- **Browser control:** isolated profile, accessibility tree, screenshots.
- **Computer use:** operate native apps through Windows UI Automation, with window and element
  highlighting before each action. Security dialogs (UAC, sign-in) are never controlled.
- **Image and video generation:** `gorsel_uret` (OpenRouter or Codex CLI) and `video_uret`
  (OpenRouter, paid, requires approval).

### Skills, plugins and MCP
- **Instructions:** `~/.claude/CLAUDE.md` with its `@import`s, plus project `KAIRO.md` / `AGENTS.md`, are added to every chat.
- **Skills:** `~/.claude/skills` is discovered automatically and the model picks the right skill;
  the agent can save and version its own skills (`skill_kaydet`). Built-in document skills: `docx`, `pdf`.
- **Claude Code plugin compatibility:** `.claude-plugin/plugin.json`, skills, commands, agents,
  `hooks.json`, `.mcp.json`, marketplaces and git sources; import installed Claude Code plugins.
- **Hooks:** versioned events; if a security hook fails, the action is blocked.
- **MCP:** stdio and streamable HTTP, OAuth sign-in (discovery + dynamic registration + PKCE), a
  directory of 25 official remote servers, import from Claude Code / Claude Desktop settings, and
  GitHub integration (`gh`).
- **On-demand tool loading:** MCP schemas are deferred and the model loads what it needs via
  `arac_bul` (measured: ~51K -> ~17K tokens per message on a 128-tool setup).
- **Tool packs:** REA, Craft Anything, agent-desktop; pinned version and digest, installed into the data folder.
- **Extensions:** an extension system running in a separate process with sandboxed panels.

### Interface
- **Terminal** (Ctrl+\`), **Changes** (git diff) and **Browser** panels in the top bar; a right panel
  with environment, context usage, connectors, threads and file tree; a bottom status bar.
- **Turkish / English interface**: switch under Settings > Appearance > "Dil / Language" (the page
  reloads in the new language). Model replies and some backend messages may stay in Turkish.
- Dark / light / system theme, font size, chat width, reduced-motion support, keyboard and
  screen-reader accessibility.
- System tray, global quick-launch shortcut, optional launch at startup.

### Model testing tools
- **Compare:** send the same prompt to several models and see answers, load time and tokens/sec side by side.
- **OCR test**, **Tool test** and a **Test suite** (reasoning, tool calling, JSON, Turkish OCR, refusal behavior).

## Requirements

- Windows 10/11 (WebView2 is preinstalled). Python 3.12 to run from source.
- For OpenRouter only, no model files are needed; an OpenRouter API key is enough.
- For local models, a model folder containing `llama.cpp\llama-server.exe` (Vulkan) and `models\*.gguf`.
  Models are not bundled; download GGUF files yourself or through the built-in model store.

- On machines with integrated graphics the model uses system RAM: plan for ~1-2 GB of free RAM
  above the model size.
- Optional: Git, `gh`, Node.js (some tool packs), Podman / Docker (isolation),
  Claude Code / Codex CLI (CLI agents).

## Getting Started

### Portable (recommended)

Run `Baslat.bat` or `Kairo.exe`. The folder can be copied anywhere. Settings, chats and attachments
live in the `data\` folder inside it; nothing is written to the registry or AppData (apart from a
single shortcut if launch at startup is enabled). To uninstall, delete the folder.

The model folder is searched in this order: the `YEREL_LLM_DIZIN` environment variable, an `llm`
folder inside or next to the app folder, then `Projects\llm` in the user folder. If none is found,
set it under Settings > Model folder.

### From source

```bat
pip install -r requirements.txt
baslat.bat                 :: desktop window
python -m app --tarayici   :: open in the default browser
python -m app --version
```

When running from source, data is stored in `data\` at the project root; override it with the
`YAS_VERI_DIZINI` environment variable. Kairo is Windows-only (llama-server.exe, WebView2 and
UI Automation are Windows-specific).

## Development

```bat
pip install -r requirements-dev.txt
ruff format . && ruff check .
pytest --cov
paketleme\derle.bat     :: PyInstaller in a clean venv -> dist\Kairo\ (portable folder)
```

The suite has roughly 800 tests; model calls run against a fake server without network access.

## Security

- The server binds to `127.0.0.1` only, with Host / Origin checks and a session token. Do not expose it to the network.
- API keys stay on the backend under `data\` and are masked in the UI and logs.
- **Full access** mode lets the agent write files, run commands and operate applications without
  approval. Enable it only for tasks you trust.
- Uncensored models apply no content filtering; responsibility for their use lies with the user.

## License

[MIT](LICENSE) (c) 2026 Umut Çelik. Built-in skills and third-party components are subject to their own licenses.

## Third-Party Notices

See `NOTICE-openbot.md`, `NOTICE-dsh-superagent.md` and `app/skills/NOTICE.txt` for design
inspirations and built-in skills.
