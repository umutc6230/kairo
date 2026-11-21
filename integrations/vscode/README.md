# Kairo Bridge (VS Code)

Lightweight zero-dependency VS Code extension that sends the active file, line range, and selected code snippet to a running Kairo instance (`POST /api/editor/baglam`).

**Product Owner: Umut Çelik** · [X](https://x.com/umutc6230) · [GitHub](https://github.com/umutc6230)

## Usage
1. Open Kairo on your machine.
2. In VS Code, configure `kairo.url` (and `kairo.oturumAnahtari` if needed).
3. Select code or place your cursor in any file and press `Ctrl+Alt+K` (or run `Kairo: Secili kodu/dosyayi gonder` from the Command Palette).
