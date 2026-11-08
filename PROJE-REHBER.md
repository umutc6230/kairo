# PROJE-REHBER - yerel-ai-studio

## Mimari
```
pywebview penceresi (frameless, WebView2)  <-- app/main.py (uvicorn ayri thread'de)
        |  fetch / SSE (text/event-stream)
FastAPI (app/api.py) --> services/
   ModelYonetici   tek YerelLLM; asyncio.Lock: model degistirme ile sohbet cakismaz
   SohbetServisi   mesaj -> ek parcalari -> gecmis -> cevap_akit (dusunce/parca olaylari)
   TestServisi     karsilastir / ocr / arac / paket (model_dongusu: modeller sirayla)
   OturumDeposu, EkDeposu, AyarDeposu  (JSON dosyalar, atomik yazim)
        |
yerel_llm.YerelLLM  --> llama-server (127.0.0.1:8080, Projects\llm)
```

## Klasor haritasi
- `app/main.py` baslatici (--tarayici, --port, --version); `PencereApi` = baslik cubugu butonlari.
- `app/api.py` uclar; uzun isler `sse()` ile akar. Hata: UygulamaHatasi -> {hata}, YerelLLMHatasi -> 503.
- `app/services/sohbet.py` `kuyruktan_akit`: uretici gorev + kuyruk. Dusunce de canli akar (uretici
  `dusunce_cb` ile kuyruga yazar); tuketici koparsa gorev iptal edilir (model yuklemesi dahil).
- `app/services/testler.py` test ekranlari; `araclar.py` demo araclar (AST ile guvenli hesap).
- `app/web/` vanilla ES modulleri: app.js (gezinme, durum, menuler), sohbet.js, sayfalar.js,
  ayarlar.js, ortak.js (api, sseOku, modal, menu; native dialog YOK), md.js (guvenli markdown), ikonlar.js.
- `tests/` sahte llama-server (conftest.SahteSunucu) ile tum uclar; skill testleri kopyasi.

## Kararlar
- pywebview + FastAPI (Electron degil): Python istemcisi (PDF/OCR/ses) dogrudan kullanilir, hafif.
- Ayni anda tek model (RAM + port 8080). Model degisince kendi sunucumuz yeniden baslar; kullanicinin
  disaridan actigi sunucuya yalniz acik onayla (modal) dokunulur.
- `durdur()` kilidi BEKLEMEZ: yukleme/cevap sirasinda da sureci hemen keser.
- Gecmis mesajlar yalniz metin olarak gider (ekler adiyla); gorsel/ses yalniz son mesajda. 16k karakter.
- Skill metinleri ASCII; arayuzde gorunen Turkce karsiliklar `ortak.js` DUSUNME_TR / MODEL_TR'de.

## Bulgular
- pywebview `js_api` nesnesindeki alt cizgisiz ozellikleri ozyinelemeli tarar; pencere (.NET) nesnesi
  koyunca sonsuz ozyineleme + GIL -> arka uc yanit vermedi. Pencere `_pencere` olarak saklanir.
- Ayarlardaki adres `/v1` ile biter; istemciye ikinci kez `/v1` eklenmemeli (dogrulayici ekler).
- `"İstanbul".lower()` -> `i̇` (birlesen nokta): Turkce harfleri lower()'dan ONCE cevir.
- Dahili GPU: bos RAM ~1 GB'a dusunce gorsel istekleri `failed to process mtmd chunk` verir.
