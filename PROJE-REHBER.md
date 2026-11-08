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
- Gecmis mesajlar EKLERIYLE gider (gorsel 1024 px, PDF/metin yazisi 4000 kar., ses): token butcesi
  (baglam - cevap payi - sistem - araclar) dolunca en eski ekler dusurulur ve kullaniciya uyari olur.
- Skill metinleri ASCII; arayuzde gorunen Turkce karsiliklar `ortak.js` DUSUNME_TR / MODEL_TR'de.
- Sohbet araclari YALNIZ OKUR (sohbet_araclari.py); gizli dosya deseni (ssh/.env/anahtar/tarayici) engellenir.
- Skill sistemi (skiller.py): kaynaklar ~/.claude/skills > ~/Documents/brain/skills > <veri>/skills;
  ayni dosya/ad bir kez. >=16K baglamda TUM skill'ler (ad + 110 karakter) sabit listede (onbellek),
  8K'da yalniz kelime puaniyla en uygun 6. Guclu eslesme (puan>=5, ikinciyle fark>=2) otomatik yuklenir.
- Sistem mesaji sirasi: arac notu -> talimatlar -> sistem istemi -> skill listesi -> (degisken) otomatik
  skill. Sabit onek llama-server prompt onbellegine girer; "Modeli yukle" sonrasi isitma istegi atilir.
- Talimatlar (talimatlar.py): ~/.claude/CLAUDE.md + @import (kod blogu haric, 4 seviye, dongu korumali).
- Model magazasi (model_magaza.py): HF /api/models?expand[]=gguf,siblings; boyut parametre*0.62 GB
  tahmini; gereken RAM = boyut*1.15+1; calisir <= toplam-5, zorlanir <= toplam-2. Indirme .part +
  Range ile devam, SHA256 (LFS) dogrulama, data/modeller.json kaydi -> MODELLER'e eklenir.

- Yerel sunucu (agecidi.py): ayni portta Ollama (/api/*) + OpenAI (/v1/*). UI sunucusuyla AYNI
  event loop'ta ikinci uvicorn.Server (ModelYonetici kilidi ve httpx istemcisi loop'a bagli; ayri
  thread olmaz). Port onceden denenir; doluysa kimin kullandigi /api/version ile soylenir. Ollama
  istemcileri dusunme istemezse enable_thinking=false. --sunucu: pencere yok, /api/yerel/kapat ile biter.

## Bulgular
- Kucuk modeller (E4B) araci metinle "cagiracagim" deyip cagirmayabiliyor -> otomatik skill yukleme.
- Dahili GPU'da girdi isleme 14-26 tok/sn: 4.8K token sistem mesaji ilk cevabi 3 dk geciktirdi;
  onbellek + isitma ile mesaj basina ~1K token'a indi.
- Model skill komutlarini "ben calistiririm" diye uydurdu -> SINIR notu (komut calistiramazsin).
- pywebview `js_api` nesnesindeki alt cizgisiz ozellikleri ozyinelemeli tarar; pencere (.NET) nesnesi
  koyunca sonsuz ozyineleme + GIL -> arka uc yanit vermedi. Pencere `_pencere` olarak saklanir.
- Ayarlardaki adres `/v1` ile biter; istemciye ikinci kez `/v1` eklenmemeli (dogrulayici ekler).
- `"İstanbul".lower()` -> `i̇` (birlesen nokta): Turkce harfleri lower()'dan ONCE cevir.
- Dahili GPU: bos RAM ~1 GB'a dusunce gorsel istekleri `failed to process mtmd chunk` verir.
