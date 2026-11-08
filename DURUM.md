# DURUM - yerel-ai-studio
guncel: 2026-11-08 | son arac: Claude Code (Opus 5.5) | dal: main

## Ne
Yerel sansursuz modelleri (DeepSeek-V4-Pro Qwen3.5 9B, Gemma 4 12B, Gemma 4 E4B heretic) sohbet,
OCR, arac cagirma ve karsilastirma testleriyle deneme masaustu uygulamasi. Claude Desktop duzeni.
Python 3.12 + FastAPI + pywebview; arayuz vanilla JS. Paketleme: PORTABLE (kullanici secti). Ayrinti: PROJE-REHBER.md.

## Calistir / test
- `baslat.bat` (pencere) | `python -m app --tarayici` | `python -m app --version`
- `pip install -r requirements-dev.txt` -> `ruff format . && ruff check .` -> `pytest --cov`
- Derleme (PORTABLE): `paketleme\derle.bat` (temiz .venv-derle + PyInstaller onedir) -> `dist\YerelAIStudio\`
- Teslim: `Desktop\Portable Programlar\YerelAIStudio\` (Baslat.bat); guncellerken data\ korunur
- Model klasoru: `C:\Users\umuti\Projects\llm` (llama.cpp + models). Ayni anda tek model.

## Asama
- [x] Arka uc: ayarlar, oturumlar, ekler, model yonetici (tek kilit, durdur kilitsiz), SSE akis
- [x] Sohbet: dusunce blogu cevabin ustunde canli akar, sonra "Dustundu (N sn)" olarak katlanir
- [x] Ekler: resim (1600 px kucultme), PDF (metin katmani / OCR, sayfa ilerlemesi), ses, metin
- [x] Karsilastir, OCR testi, Arac testi, Test paketi ekranlari
- [x] AI Ayarlari (model ara/sec, RAM/yetenek etiketleri, dusunme, Test butonu) + Hakkinda (urun sahibi)
- [x] 91 test (sahte llama-server), coverage %94; pencere + sahte sunucuyla gorsel deneme
- [x] Gercek E4B olcumu: 10.4 tok/sn, arac/JSON/OCR %100/ses/sansursuz OK; dusunme kapali mantik sorusu token sinirina takildi
- [x] Portable derleme (72 MB): teslim klasorunden Baslat.bat ile acildi, veri data'da, AppData temiz, X ile tam kapandi

## Son oturum
- 2026-11-08: proje sifirdan kuruldu. Bulgular: pywebview js_api'de pencere nesnesi -> sonsuz
  ozyineleme (alt cizgili ad); adres /v1 cift ekleniyordu; "İ".lower() hatasi; durdur kilitte asiliydi.

## Siradaki adim
- Gemma 4'te 'dusunme kapali' (enable_thinking false) gercekten kapaniyor mu incele.
- E4B ve (RAM bosken) 12B olcumlerini skill tablosuna isle.

## Acik sorunlar
- Backend hata metinleri ASCII Turkce (yerel_llm skill'inden); arayuz metinleri duzgun Turkce.
- Dahili GPU: bos RAM az iken gorsel istekler duser (BellekYetersiz mesaji gosterilir).

## Dokunulmayacak kararlar
- pywebview + FastAPI (Electron degil). Ayni anda tek model. Native dialog yok (in-app modal).
