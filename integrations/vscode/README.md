# Kairo Bridge (VS Code)

Lightweight zero-dependency VS Code extension that sends the active file, line range, and selected code snippet to a running Kairo instance (`POST /api/editor/baglam`).

**Product Owner: Umut Çelik** · [X](https://x.com/umutc6230) · [GitHub](https://github.com/umutc6230)

## Usage
1. Open Kairo on your machine. It writes `data/baglanti.json` with its active port and session token, which this extension discovers automatically.
2. Optionally, in VS Code configure `kairo.url`, `kairo.oturumAnahtari`, or `kairo.baglantiDosyasi`.
3. Select code or place your cursor in any file and press `Ctrl+Alt+K` (or run `Kairo: Secili kodu/dosyayi gonder` from the Command Palette).
