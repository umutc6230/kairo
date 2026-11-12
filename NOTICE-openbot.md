# openbot'tan uyarlanan tasarim

Kairo'nun asagidaki ozellikleri openbot'un tasarimindan uyarlanmistir:

- Kalici ajanlar (kimlik, talimat, calisma klasoru, model, hafiza) - `app/agent/ajanlar.py`
- FIFO is kuyrugu ve ajanlar arasi mesaj (cevap gonderenin kuyruguna doner)
- Mesajlasma kanali (Telegram) - `app/services/telegram.py`
- Ilk acilista tek onayla tam yetki (`tam_yetki`)

Kaynak: https://github.com/nightly-labs/openbot

Required Notice: Copyright 2026 Synthetify Labs spółka z ograniczoną odpowiedzialnością.
Lisans: PolyForm Noncommercial License 1.0.0 (https://polyformproject.org/licenses/noncommercial/1.0.0).

openbot TypeScript/Electron ile yazilmistir; kod birebir kopyalanmamis, davranis Python'da yeniden
yazilmistir. Bu uyarlama kisisel, ticari olmayan kullanim icindir; ticari kullanim icin openbot'un
lisans sahibinden ayrica izin gerekir.
