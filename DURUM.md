# DURUM - yerel-ai-studio
guncel: 2026-11-08 | son arac: Claude Code (Opus 5.5) | dal: main

## Ne
Yerel sansursuz modelleri (DeepSeek-V4-Pro Qwen3.5 9B, Gemma 4 12B, Gemma 4 E4B heretic) sohbet,
OCR, arac cagirma ve karsilastirma testleriyle deneme masaustu uygulamasi. Claude Desktop duzeni.
Python 3.12 + FastAPI + pywebview; arayuz vanilla JS. Ayrinti: PROJE-REHBER.md.

## Calistir / test
- `baslat.bat` (pencere) | `python -m app --tarayici` | `python -m app --version`
- `pip install -r requirements-dev.txt` -> `ruff format . && ruff check .` -> `pytest --cov`
- Derleme: `paketleme\derle.bat` (temiz .venv-derle + PyInstaller) -> `dist\YerelAIStudio\`
- Model klasoru: `C:\Users\umuti\Projects\llm` (llama.cpp + models). Ayni anda tek model.

## Asama
- [x] Arka uc: ayarlar, oturumlar, ekler, model yonetici (tek kilit, durdur kilitsiz), SSE akis
- [x] Sohbet: dusunce blogu cevabin ustunde canli akar, sonra "Dustundu (N sn)" olarak katlanir
- [x] Ekler: resim (1600 px kucultme), PDF (metin katmani / OCR, sayfa ilerlemesi), ses, metin
- [x] Karsilastir, OCR testi, Arac testi, Test paketi ekranlari
- [x] AI Ayarlari (model ara/sec, RAM/yetenek etiketleri, dusunme, Test butonu) + Hakkinda (urun sahibi)
- [x] 91 test (sahte llama-server), coverage %94; pencere + sahte sunucuyla gorsel deneme
- [ ] Gercek modelle uctan uca deneme (E4B karsilastir.py olcumu suruyor)
- [ ] PyInstaller exe derleme + kurulu exe'nin acildiginin dogrulanmasi
- [ ] Installer (Inno Setup kurulu degil; kullaniciya soruldu)

## Son oturum
- 2026-11-08: proje sifirdan kuruldu. Bulgular: pywebview js_api'de pencere nesnesi -> sonsuz
  ozyineleme (alt cizgili ad); adres /v1 cift ekleniyordu; "İ".lower() hatasi; durdur kilitte asiliydi.

## Siradaki adim
- E4B olcumunu skill tablosuna isle; Gemma'da dusunme kapali iken davranisi incele.
- exe derle, kurulu halini ac ve dene.

## Acik sorunlar
- Backend hata metinleri ASCII Turkce (yerel_llm skill'inden); arayuz metinleri duzgun Turkce.
- Dahili GPU: bos RAM az iken gorsel istekler duser (BellekYetersiz mesaji gosterilir).

## Dokunulmayacak kararlar
- pywebview + FastAPI (Electron degil). Ayni anda tek model. Native dialog yok (in-app modal).
