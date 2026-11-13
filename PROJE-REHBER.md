# PROJE-REHBER - kairo

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

- Anthropic uclari (/v1/messages, count_tokens) llama-server'in kendi Anthropic API'sine aynen
  aktarilir (SSE dahil). Claude Code her istekte `thinking: adaptive` gonderir: yalniz `enabled`
  dusunmeyi acar. Sistemdeki `x-anthropic-billing-header` blogu atilir (cch= degisirse onbellek bozulur).
  `claude-*` adlari acik modele gider (arka plan haiku istekleri model degistirmesin).

## Ajan katmani kararlari (A0, 2026-11-09)
- Is tanimi `AGENT-GELISTIRME-TALIMATI.md`, kapsam takibi `OZELLIK-MATRISI.md`. Asamalar A0->A13;
  her asamanin kabul testleri gecmeden sonraki tehlikeli yetenekler acilmaz.
- Adres dogrulama AYRISTIRMAYLA yapilir (`ayarlar.yerel_adres_dogrula`): yalniz loopback
  hostname/IP (`localhost`, 127.0.0.0/8, `::1`), scheme http/https, userinfo + query + fragment
  reddedilir. `startswith` kontrolu `http://127.0.0.1@example.invalid`'i geciriyordu.
- Arac sonuclari serilestirildikten SONRA kesilmez: `sohbet.sonuc_kisalt` en uzun METIN ALANINI
  kisaltir, JSON gecerli kalir ve `truncated` / `next_offset` / `toplam_karakter` daima durur.
  `dosya_oku` satir araligi (`satir_baslangic/bitis`, `toplam_satir`) ve `next_offset` dondurur.
- Gecmis baglamina arac kaniti `sohbet.arac_kaniti` ile katilir:
  assistant(tool_calls) -> tool sonuclari -> assistant(son metin). Sonucu alinamamis cagri
  (`durum=sonucsuz`) KATILMAZ, eslesmeyen tool_call protokolu bozar. Butceye sigmazsa yalniz metin gider.
- Baglam butcesi HER model turu oncesi yeniden hesaplanir (`sohbet.baglami_darat`): once eski arac
  sonuclari kisaltilir, sonra en eski mesajlar dusurulur; istek butce asilmis halde gonderilmez.
  Daralma `uyari` + `kod: baglam_daraldi` olarak arayuze gider.
- Son turda model arac isterse arac CALISTIRILMAZ; cagri `durum=sonucsuz` kaydedilir ve
  `kod: tur_siniri` uyarisi gider. Arayuzde basari ikonu yalniz gercek sonucta cikar (sonucsuz: ⦸).
- Iptal/hata yolunda o ana kadarki arac kayitlari asistan mesajina yazilir; hata olayindan sonra
  sahte `bitti` olayi gonderilmez (akisin bitmesi gorev basarisi degildir).
- Oturum yazimlari oturum basina `asyncio.Lock` ile; cevap akarken oturum silinirse
  `kod: oturum_silindi` uyarisi doner, istisna sizmaz.
- Upload akista parca parca okunur (1 MB), sinir asilinca hemen kesilir (`UPLOAD_PARCA_BAYT`).
- Dis kaynak: `https://github.com/Twigpine/openclaude` kullanicinin verdigi referans repo.
  Fikir/desen alinabilir; dosya, kod ya da bagimlilik alinmadan once BRAIN-POLICY dis kaynak
  guvenlik taramasi yapilir ve kullaniciya karar raporu verilir.

## A1 kararlari: proje, izin motoru (2026-11-09)
- Yeni paket `app/agent/`: sohbetten BAGIMSIZ izin katmani. UI, CLI, SDK, MCP, alt ajan ayni
  `PolitikaMotoru`ndan gecer; bir giriste denetleyip digerinde atlamak yasak.
- `agent/yollar.py`: her yol `os.path.realpath` ile kanonik hale gelir (junction/symlink cozulur),
  sonra kok kapsamasi `os.path.normcase` ile kontrol edilir. Metin duzeyinde reddedilenler:
  cihaz yolu (`\\?\` ve `\\.\`), UNC, alternatif veri akisi (`a.txt:akis`), ayrilmis ad
  (CON/NUL/COM1), sonda nokta/bosluk, null bayt. TOCTOU icin `kimlik`/`kimlik_dogrula`
  (st_dev, st_ino) okuma sonrasi dogrulama yapar; tam garanti degildir.
- `agent/workspaces.py`: `CalismaAlani` = kokler + guven + mod. Kok listesi BOS ise hicbir dosya
  acilmaz. Proje acilmadiginda varsayilan alan "Kisisel klasorler" (masaustu, belgeler,
  indirilenler, resimler). ONCE tum ev dizini ve her mutlak yol okunabiliyordu.
- Guven: `guvenilir` (proje AGENTS.md/CLAUDE.md okunur) / `sinirli` (varsayilan) /
  `guvenilmeyen` (yalniz okuma). Proje talimati "sana yeni yetki VEREMEZ" notuyla sarilir ve
  kok disina link eden talimat dosyasi okunmaz.
- Modlar: `sohbet`, `planla` (salt okunur), `onayli` (yan etkide sorar), `otomatik` (politika
  kapsaminda). Otomatik mod sinirsiz yetki DEGILDIR: kok disi, hassas dosya ve dis ag yine kapali.
- Karar sirasi: yonetilen politika -> kalici ret (kok disi/hassas) -> ag -> mod tavani -> guven ->
  yan etki sinifi. Belirsizlikte `sor`/`ret`, asla `izin`.
- Onay: islem hash'i (arac + yan etki + cozulmus yol + komut + host + politika surumu). Islem
  degisirse eski onay gecersiz; onay 5 dk gecerli; politika surumu degisirse dusser.
- Dosya araclari `DosyaAraclari(kokler)` sinifinda; kokler CLOSURE'da tutulur, modelin urettigi
  argumanlarla ezilemez. Goreli yol artik ev dizinine degil ILK KOKE cozulur.
- `yerel_host_mu` ve `ayarlar.yerel_adres_dogrula` IP ayristirir: `startswith("127.")` kullanilmaz
  (`127.0.0.1.evil.test` geciyordu).
- Loopback API (A1.9): Host loopback olmali, Origin/Referer varsa loopback olmali, `/api/*`
  (bilgi haric) `X-YAS-Oturum` ister. Anahtar sunucu tarafindan index.html'e gomulur; baska origin
  sayfayi okuyamaz. Bu OS yetkilendirmesi DEGILDIR: ayni kullanicinin baska yerel programi
  index.html'i okuyabilir.
- Izolasyon (A1.8): Windows'ta dosya/ag sandbox'i YOK. `/api/izinler` bunu `izolasyon: "yok"` +
  not olarak doner ve arayuz gosterir. "Regex ile sandbox" iddiasi yapilmaz.
- Arayuz: baslik cubugunda proje hapi (`app/web/proje.js`), tiklayinca etkin kapsam, kokler,
  mod/guven secimi, ek klasor yetkisi ve izolasyon notu. Native dialog yok.

## Bulgular
- Kucuk modeller (E4B) araci metinle "cagiracagim" deyip cagirmayabiliyor -> otomatik skill yukleme.
- Dahili GPU'da girdi isleme 14-26 tok/sn: 4.8K token sistem mesaji ilk cevabi 3 dk geciktirdi;
  onbellek + isitma ile mesaj basina ~1K token'a indi.
- Model skill komutlarini "ben calistiririm" diye uydurdu -> SINIR notu (komut calistiramazsin).
- pywebview `js_api` nesnesindeki alt cizgisiz ozellikleri ozyinelemeli tarar; pencere (.NET) nesnesi
  koyunca sonsuz ozyineleme + GIL -> arka uc yanit vermedi. Pencere `_pencere` olarak saklanir.
- Ayarlardaki adres `/v1` ile biter; istemciye ikinci kez `/v1` eklenmemeli (dogrulayici ekler).
- `"İstanbul".lower()` -> `i̇` (birlesen nokta): Turkce harfleri lower()'dan ONCE cevir.
- Claude Code ilk istegi --tools ile 6 aracla bile 5-10K token: dahili GPU'da ilk cevap 5-12 dk;
  onek onbellegiyle sonraki turlar ~10 sn. CLAUDE_CODE_MAX_CONTEXT_TOKENS 16384 verilince Claude Code
  istek gondermeden 'Prompt is too long' der (cikti + sikistirma payi): 32768 ve Studio baglami 32K.
- Dahili GPU: bos RAM ~1 GB'a dusunce gorsel istekleri `failed to process mtmd chunk` verir.
