# DURUM - yerel-ai-studio
guncel: 2026-11-10 | son arac: Claude Code (Opus 5.5) | dal: feature/ajan-katmani

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
- [x] Sohbet devami: onceki resim/PDF/ses ekleri baglam butcesiyle gider
- [x] Sohbette salt okunur araclar (klasor_listele, dosya_oku, dosya_ara...): gercek E4B masaustunu listeledi
- [x] Skill'ler + talimatlar: ~/.claude/skills (54) + CLAUDE.md/@BRAIN-POLICY; skill_kullan, otomatik yukleme,
      onbellek dostu sira + isitma; gercek E4B markitdown skill'ini kullandi
- [x] Model magazasi (HF): ara, calisir/zorlanir/calismaz gostergesi, indirme (devam, SHA256), silme
- [x] Yerel sunucu (Ollama + OpenAI uyumlu, :11434): gercek E4B ile GridMind bicimli /api/chat, arac
      cagrisi, akis ve /v1 denendi; Sunucu.bat/Sunucu-Durdur.bat portable'da calisiyor
- [x] Claude Code yerel modelle: Anthropic /v1/messages + count_tokens gecisi, Claude-Yerel.bat;
      gercek E4B ile Read araci kullanip dogru cevap verdi (ilk tur ~12 dk, sonraki turlar ~10 sn)
- [x] Portable derleme (72 MB): teslim klasorunden Baslat.bat ile acildi, veri data'da, AppData temiz, X ile tam kapandi

## Asama (ajan katmani)
- [x] A0 mevcut hatalar + baslangic olcumu (2026-11-09): 8 madde, `tests/test_a0_regresyon.py` 34 test
- [x] A1 proje/workspace + izin motoru + loopback sertlestirme (2026-11-09): `app/agent/`
      (yollar, workspaces, policy) + proje arayuzu; `tests/test_a1_izinler.py` 61 test
- [x] A1.7 komut sureci (env allowlist, timeout, cikti siniri, process-tree iptali)
- [x] A2 cekirdek: oku/listele/glob/ara (rg + python yedegi), yama/yaz/tasi/sil (hash + atomik +
      checkpoint), terminal (arka plan, durdur), git durum/diff/gecmis, dosya bazli geri alma.
      `tests/test_a2_araclar.py` 35 test; uctan uca Python/TS duzelt-test-geri al gecti
- [x] OpenRouter saglayici: AI Ayarlari'nda Yerel/OpenRouter secimi, anahtar ekle/sil (maskeli,
      yalniz backend data/openrouter.json), canli model listesi (24 saat onbellek, Yenile, hata->eski
      liste+uyari), ara + yalniz ucretsiz, fiyat/context/arac/resim rozetleri, Test (arac tanimli, sure+
      maliyet). Sohbet aktif_model ile uzak modele gider. tests/test_openrouter.py 9 test
- [x] A2 kalan: arka plan isine stdin (komut_girdi), git_dal/git_commit (YanEtki.git: otomatik modda da
      onay; onay islemin tam metnine bagli; commit yalniz adi verilen dosyalar), hunk bazli geri alma
      (/api/checkpointler/{id}/hunklar, /hunk-geri-al; cakismada dokunmaz). tests/test_a2_kalan.py 11 test
- [ ] A2 ertelenen: git worktree (A8 alt ajanlarla), push/merge (dis etki, ayri is), arayuzde hunk secimi
- [x] A1.8 izolasyon adaptoru (app/agent/izolasyon.py): yok (Job Object) | konteyner (Podman/Docker,
      --network none, yalniz proje koku bagli, cap-drop ALL, no-new-privileges, --pull=never). Konteyner
      kullanilamazsa komut CALISMAZ (sessiz dusus yok). Izolasyon yoksa otomatik modda da komut onay
      ister. Proje/izin penceresinde secim + durum. tests/test_a1_8_izolasyon.py 9 test
- [x] A3 kalici ajan dongusu (app/agent/runner.py): Run/Adim diske atomik; yan etkiden ONCE niyet
      kaydi, cokme sonrasi belirsiz -> kullanici karari (tamamlandi/atla/tekrarla), otomatik tekrar YOK;
      adim/sure/token butcesi, ayni hata ve ilerlemesizlik siniri; duraklat/devam/iptal/tekrar ayri;
      calisirken yonlendirme kuyrugu; onay bekleyince durur, onay verilince ayni adimdan surer;
      basarili icin arac kaniti (basarisiz test kanit olamaz), yoksa dogrulanmadi. API /api/gorevler.
      tests/test_a3_ajan.py 18 test
- [x] A4: model yetenek profili (app/agent/yetenek.py: araclar/json/goruntu/dusunme/baglam/tokenizer;
      aracsiz modelle gorev baslamaz, desteklenmeyen dusunme acik hata); baglam butce dokumu (sistem/
      arac/mesaj/kanit/cevap) run.baglam'da; runner'da kural tabanli ozet (app/agent/ozet.py: hedef,
      kabul, kullanici kisitlari, plan, adimlar, dosya/hash (ESKI notuyla), acik hatalar, sonraki eylem;
      gecersiz ozet eski baglamin yerine gecmez; cikarilan mesajlar runs/<id>.arsiv.jsonl);
      hafiza (app/services/hafiza.py: kaynak/tarih/kapsam/guven/gecerlilik, sir reddi, CRUD + disa
      aktar, otomatik ogrenme varsayilan KAPALI; Ayarlar > Hafiza sekmesi); oturum catal/temizle/disa
      aktar (temizle hafizaya dokunmaz); /api/model/yetenek. tests/test_a4_baglam.py 14 test
- [ ] A4 ertelenen: alt klasor talimat kapsami (A4.2), arac/skill tanimlarini ihtiyaca gore yukleme (A4.6)
- [x] A5 cekirdek (A5.1-3): 'Ajan gorevleri' sayfasi (app/web/gorevler.js): gorev baslat (hedef, kabul,
      butce), liste, canli adimlar + gercek terminal ciktisi + cikis kodu, plan, butce/baglam cubuklari,
      aktif model, duraklat/devam/iptal/tekrar, onay karti (degisiklik onizlemesi: diff/icerik/komut),
      belirsiz adim karari, yonlendirme; checkpoint diff + hunk secip geri alma + tum geri alma.
      Basari ikonu yalniz basarili+dogrulandi'dan. Tum dis metin kacir() ile. tests/test_a5_onay.py
- [x] A5.4 review (app/agent/review.py): git diff -> JSON semali bulgular (onem, dosya:satir, neden,
      yeniden uretme, dogrulama onerisi); model 'dogrulandi' diyemez (hep model_varsayimi), konum diff'e
      karsi kural tabanli denetlenir (uydurma dosya/satir isaretlenir); guvenilir projede REVIEW.md kural
      olur (yetki veremez). Gorevler sayfasi + sohbette /diff /review (modele mesaj gitmez).
- [x] A5.5 artifact (app/services/artifactler.py): tur beyaz listesi, 2 MB, siki kimlik; ajan araci
      artifact_olustur; onizleme iframe sandbox=allow-scripts (allow-same-origin YOK) + srcdoc basinda
      CSP (connect-src none). Icerik yalniz oturumlu API ile; acik uc yok. Indir/sil.
- [x] A5.6 a11y: modal role=dialog/aria-modal/aria-labelledby, odak tasima + Tab tuzagi + kapaninca odak
      geri; sohbet role=log; ikon dugmelere aria-label; :focus-visible; prefers-reduced-motion. Uzun sohbet
      pencereleme (son 40 mesaj, 'daha eski' parti parti, kaydirma korunur); akista markdown kare basina 1.
- [x] A5.7 yerel ses dikte (app/web/dikte.js + /api/dikte): mikrofon -> 16 kHz WAV -> yerel Gemma 4;
      Web Speech (bulut) YOK; model sesi anlamiyorsa / OpenRouter seciliyse dugme devre disi + neden.
      Kayit gostergesi, sure, 30 sn sinir, Esc iptal, izin hatasi.
- [ ] A5 kalan: gercek WebView2 penceresinde E2E (pywebview iframe kopru enjeksiyonu kontrolu)
- [x] A6.1 skill metadata (app/services/skiller.py): surum, required/allowed-tools, sha256 hash, guven
      (kullanici/proje), bozuk frontmatter satirli hata -> listelenir ama YUKLENMEZ (otomatik dahil);
      proje skill'i yalniz guvenilir projede (.claude/skills); PUT /api/skiller/{ad} duzenle,
      GET /api/skiller/{ad}/test (modelin gorecegi + eksik araclar). Manifest araci izin degildir.
- [x] A6.2 skill scriptleri: yalniz manifestte scripts: ile ilan edilen, skill klasoru icindeki
      py/ps1/sh/js; arguman cmd metakarakteri reddi; ajan komutuyla ayni PolitikaMotoru yolu
      (arac skill_scripti), onay script sha256'sina bagli; arac yalniz komut araci acikken sunulur.
- [x] A6.3 slash komut kaydi (app/web/komutlar.js): /help /status /context /model /config /effort /memory
      /hooks /permissions /diff /review /agents /goal /clear /compact; servisi olmayanlar 'henuz yok' der.
- [x] A6.4-5 hooks (app/agent/hooks.py): run_baslangic/run_bitis/prompt/pre_tool/post_tool/compact; stdin
      JSON (degerler maskeli), cikis 2 = engel; guvenlik hook'u hata/timeout'ta engeller, bilgi durdurmaz.
- [x] A6.6 Ayarlar > Hook'lar sekmesi (ekle, test, ac/kapat, sil). Skill duzenleme UI'i yok (API var).
- [x] ARAYUZ Claude Code Desktop duzeni: sol kenar Yeni/Ara/Artifact'ler/Ozellestir + tarihli sohbetler;
      ayri ozellik sayfalari kalkti (test sayfalari menude yok, kodu duruyor). Proje acikken SOHBET = AJAN:
      adimlar/onay/diff/sonuc mesaj akisinda; plan, baglam %, degisen dosyalar, butce SAG PANELDE;
      composer'da mod secici. Tarayicida uctan uca dogrulandi. Sohbet-gorev bagi localStorage'da (sunucuya tasinacak).
- [x] A7.1-3 MCP istemcisi (app/agent/mcp.py, bagimlilik yok): stdio JSON-RPC, initialize/tools list/call,
      mcp__<sunucu>__<arac> ad ayirma, bozuk arac/sema elenir, kopmada yeniden baglanma, 30 sn zaman asimi;
      sirlar backend'de (disari ****), cikti veri olarak + maskeli; her cagri izin motorundan (izinli arac=oku,
      digerleri dis=her zaman onay). /api/mcp CRUD+test. tests/test_a7_mcp.py (gercek stdio test sunucusu).
- [x] MCP arayuzu: Ayarlar > Baglayicilar (Ozellestir'de sekme, /mcp): ekle, baglan, araclari gor, onaysiz
      calisacak araclari isaretle, ac/kapat, sil; ortam sirlari arayuzde gorunmez (tarayicida dogrulandi).
- [x] A7.4/7 plugin (app/services/pluginler.py): plugin.json manifest, KARANTINA -> inceleme raporu (dosya/sha256,
      riskli desen, kurulum scripti; scriptler ASLA calismaz) -> onayla kur; surum sakla, geri al, ac/kapat, kaldir;
      kurum politikasi (plugin-politika.json yasak/izinli; sonradan yasak hemen etkili). Plugin yalniz skill tasir.
      Ayarlar > Plugin'ler + /plugin. Bulgu: Windows'ta kaydedilen plugin.json BOM'lu -> utf-8-sig.
- [x] A7.1 MCP streamable HTTP (JSON + SSE cevap, Mcp-Session-Id, 404'te yeniden initialize, 401 Turkce);
      uzak adres https (http yalniz loopback), URL'de parola yok; kimlik basligi backend'de, disari ****;
      uzak sunucunun araclari izinli isaretlense de HER ZAMAN onay ister; resources/list (ilan edilirse).
      Arayuz: Baglayicilar'da URL + Authorization, "uzak" rozeti. Sahte uzak sunucuyla 5 test.
- [x] A7.5 katalog: data/plugin-katalog.json {name, version, yol, sha256}; klasor hash'i uyusmazsa kurulmaz.
- [ ] A7 kalan: OAuth akisi (simdilik baslik elle), MCP prompts, uzanti/Mods API'si (A7.6: izole worker),
      plugin eval + token/sure raporu (ertelendi).
- [x] A8.1/A8.4 alt ajan (runner alt_ajan araci): ayri baglam, dar arac seti, YAZMA yalniz sahip olunan
      dosyalara, butce ebeveynin kalanindan KESILIR (cogalmaz, harcama ebeveyne yazilir), derinlik 1,
      ayni dosyaya iki calisan alt ajan olamaz, ebeveyn iptali cocugu da iptal eder, cokmede adim belirsiz.
      Model tek: cocuk sirali calisir. tests/test_a8_alt_ajan.py
- [x] A8.7 derin review (/review derin, ?derin=true): guvenlik + dogruluk odakli ayri gecisler, dosya/satir
      bazli birlestirme, en ciddi onem kalir; ayni modelin tekrari BAGIMSIZ KANIT SAYILMAZ (model_varsayimi).
- [x] Agent View: sag panelde alt ajanlar (durum, yazabildigi dosyalar, araclari, adim/butce, sonuc).
- [x] A8.3 izole worktree (app/agent/worktree.py): composer'da "Ayri dal" -> gorev ajan/<id> dalinda ayri
      worktree'de calisir; ana agaca dokunmaz. "Ana dala birlestir": istege bagli test once worktree'de;
      kullanici degisikligi varsa birlestirmez; catismada merge --abort + catisan dosyalar (sessiz cozum yok);
      "At" dali siler. Tarayicida uctan uca dogrulandi (gercek git). Bulgu: autocrlf satir sonu.
- [x] A8.6 dinamik is akislari (app/agent/akis.py, /api/akislar): tipli adimlar (ajan | komut; kod/eval YOK),
      bagimlilik + dongu tespiti, kosul (onceki adim basarili/basarisiz), sinirli tekrar (<=3), bagimlisi
      basarisizsa atlanir; komut izin motorundan gecer, onayda akis durur, devamda tamamlananlar yinelenmez.
- [x] A8.2 takim panosu (app/agent/takim.py): lider (ust gorev) + alt ajanlar ortak gorev listesi; bagimlilik,
      claim = sureli kiralama (600 sn), panoyu kullanmak heartbeat, suresi dolan (coken) ajanin gorevi geri
      acilir, yalniz sahibi tamamlar; mesaj kutusu (kisiye/hepsi), ayni mesaj_id tekrar teslim edilmez.
      Araclar takim_* (alt ajanlara da acik). /api/gorevler/{id}/takim.
- [x] A8 CANLI (OpenRouter nemotron-3-ultra:free): lider iki alt_ajan acti (her biri tek dosya + oku/yama);
      ilk deneme: alt ajanlar isi yapti ama plan_guncelle 5 adimlik butceyi yedi -> "basarisiz". Duzeltme:
      plan_guncelle butceden dusmez, alt ajan en az 8 adim. Ikinci deneme: iki alt ajan BASARILI, lider testi
      kosup kanitla bitirdi (17 adim, 144 sn).
- [ ] A8 kalan: is akisi + takim panosu arayuzu (su an API). Sonra A9  <- SIRADAKI
- 2026-11-10 (16): A6 bitti (hooks + slash + hook UI; tarayicida dogrulandi). DIKKAT: ayni dalda paralel
  bir oturum A6.1/A6.2 commit'ledi (14da54a, 1c791d4); benim skill commit'im (81b748a) onlarla ust uste.
  399 test geciyor.
- [ ] A5 ajan ekrani
- [ ] A7 MCP/plugin/mods | A8 alt ajanlar | A9-A12 | A13 kalite kapisi

## Son oturum
- 2026-11-10 (15): A6.2 tamamlandi; 16 yeni test (kapsam disi/yasak tur/zincir arguman/onay
  icerige bagli/salt okunur ret). Skill sistem metni script araci varken guncellendi. 388 test.
- 2026-11-09 (14): A6.1 tamamlandi. Bulgu: bozuk frontmatter'li skill otomatik yuklemede yine
  secilebiliyordu -> otomatik_skill bozuklari atlar. 372 test.
- 2026-11-09 (13): A5.6 + A5.7. Tarayicida: adsiz dugme/alan 0; 120 mesajlik sohbette 40 cizildi, 'daha
  eski' calisti; gercek klavyeyle 60 Tab + 25 Shift+Tab odak modalda kaldi, Esc kapatti, odak acan dugmeye
  dondu. Canli dikte: Windows TTS ile uretilen WAV -> gercek yerel Gemma E4B -> 'Please open the project
  and run all the unit tests.' birebir (32.8 sn, model yukleme dahil). 366 test, %92.
- 2026-11-09 (12): A5.4 + A5.5. Tarayicida kotu niyetli artifact: betik calisti ama ust DOM, oturum
  anahtari, top.location, localStorage, cerez, API fetch (mutlak+goreli), pywebview: HEPSI engellendi;
  origin null. Canli review (OpenRouter nemotron-3-ultra:free): kasitli SQL enjeksiyonunu 26 sn'de
  dogru konumla buldu. Bulgu: git olmayan projede ham git kullanim metni gosteriliyordu -> Turkce mesaj.
  362 test, %92.
- 2026-11-09 (11): A5 cekirdek. Gercek tarayicida E2E (izole veri YAS_VERI_DIZINI + betikli sahte
  OpenAI uyumlu model): proje ac -> gorev -> onay x2 (gercek tik) -> test gecti -> diff -> hunk geri
  al (diskte dogrulandi) -> ret yolu -> XSS (hedef + dosya icerigi) calismadi. E2E'nin buldugu
  GERCEK hatalar: (1) TEK SEFERLIK ONAY TUKETILMIYORDU: ikinci gorev yama+komutu onaysiz calistirdi
  -> uygula() onayi tuketir; (2) yazma/yama onayi yalniz YOLA bagliydi -> islem hash'ine degisiklik
  imzasi; (3) ekran her 1.5 sn yeniden ciziliyordu, tiklanan dugme DOM'dan kalkiyordu -> icerik
  imzasi degismedikce cizme; (4) Python yamasi JS dizesine satir sonu sokmus, node --check
  (CommonJS) kacirmisti -> modul kipinde JS testi eklendi. 353 test, %92.
- 2026-11-09 (10): A4 tamamlandi. Canli: OpenRouter nemotron-3-ultra:free, 9K baglam, 2 ozet,
  BASARILI (14 adim, 97 sn, kanit=gecen test, en fazla %84 dolu). Bulgular: ozet dosya/hash'i
  2000 karaktere kirpilmis sonuctan parse ediyordu (buyuk okumada kayboluyordu) -> Adim.dosya/hash
  alanlari; token butcesi (400K) cagri basina baglam toplami oldugu icin 32K'da ~16 cagrida
  doluyordu -> 2M. 347 test, %92.
- 2026-11-09 (9): A3 tamamlandi (backend + API; ekran A5). Genel {islem} rotasi /karar'i
  yutuyordu: ozel rota once tanimlandi. CANLI KABUL (2 dosya, 3 hata, pytest):
  * Yerel E4B: BASARISIZ, 40 adim butcesi doldu (28 dk); 16 yama reddedildi.
  * OpenRouter nemotron-3-ultra:free (son hal): BASARILI, 16 adim, 90 sn, kanit = gecen test.
  Canli denemelerin buldugu GERCEK hatalar (hepsi duzeltildi + test):
  1) proje_dosya_oku hash DONDURMUYORDU -> model beklenen_hash bilemiyordu (yama hep reddedildi).
  2) proje_dosya_sil hash'siz calisiyordu -> 'sil + yeniden yaz' ile bayat-yazim korumasi atlatiliyordu.
  3) Hash eksik mesaji yanlisti ('Dosya zaten var') -> model sahte hash uyduruyordu.
  4) Model adim numaralarini gormuyordu -> kanit numarasi uyduruyordu; sonuca 'adim' eklendi.
  5) Kanit: degisiklik oncesi/degisikligin kendisi kabul ediliyordu -> son degisiklikten SONRA olmali;
     gecersiz kanitta bitirme reddedilir (model duzeltir), bos kanit = dogrulanmadi.
  6) Cikis kodu 2000 karaktere kirpilmis metinden okunuyordu -> uzun BASARISIZ cikti kanit sayilabiliyordu;
     Adim.cikis_kodu alani.
  7) OpenRouter 429/5xx kalici sayiliyordu -> gecici (sinirli backoff 5/15 sn).
  OpenRouter anahtari yalniz deneme surecinin belleginde kullanildi, data/'ya yazilmadi.
  333 test, %92.
- 2026-11-09 (8): A1.8 tamamlandi. Bu makinede Podman 5.8.3 kurulu ama makine yok (podman machine
  init/start + imaj pull kullanicinin elle yapacagi indirme); WSL2 Ubuntu var. Bulgu: /web statik
  dosyalari Cache-Control'suz sunuluyordu, tarayici guncellemeden sonra ESKI JS calistiriyordu ->
  no-cache (ETag dogrulamasi). Davranis degisikligi: izolasyonsuz otomatik modda komut onay ister.
  311 test, %93.
- 2026-11-09 (7): A2 kalanlari tamamlandi (stdin, git dal/commit, hunk geri alma). Bulgu: Windows'ta
  write_text CRLF yazar; ajan LF yazinca tum dosya tek blok gorunur (satir sonu degisimi tek hunk).
  302 test, %93. feature/ajan-katmani push edildi (bu commit henuz push edilmedi).
- 2026-11-09 (6): OpenRouter saglayici eklendi (app/services/openrouter.py: YerelLLM alt sinifi,
  ModelYonetici yerel listede olmayan id'yi uzak istemciye yonlendirir, yerel kilit/RAM etkilenmez;
  akista 'reasoning' alani da okunur). Arayuz canli denendi: gercek listeden 467 model geldi.
  Gercek anahtarla sohbet DENENMEDI (anahtar yok). 291 test, %93.
- 2026-11-09 (5): A0-A2 `feature/ajan-katmani` dalina commit edildi (6eab028, push yok).
  3 hata duzeltildi: arka plan isi durdurulunca surec olmuyordu (process sizintisi);
  Windows'ta tirnakli yol iceren komutlar bozuluyordu (exec+liste `\"` kaciriyordu -> shell);
  `coz("")` kok yerine hata veriyordu. 282 test, %93, ruff temiz.
- 2026-11-09 (4): **A1 asamasi uygulandi**. Yeni `app/agent/` paketi: `yollar.py` (kanonik yol,
  junction/symlink/UNC/cihaz yolu/ADS/ayrilmis ad/sonda nokta reddi, TOCTOU kimlik kontrolu),
  `workspaces.py` (proje ac/kapat, cok kok, ek klasor, guven, mod), `policy.py` (allow/ask/deny,
  mod tavani, yonetilen politika, islem hash'li onay, sir maskeleme). Dosya araclari artik
  YETKILI KOKLERE bagli (closure); proje yokken kapsam 4 kisisel klasor (once tum ev diziniydi).
  Loopback API sertlestirildi: Host/Origin + `X-YAS-Oturum` (anahtar index.html'e gomulur).
  Arayuz: baslik cubugunda proje hapi + izin kapsami modali (`app/web/proje.js`), canli denendi.
  Kendi testim iki gercek acik buldu: `yerel_host_mu` `127.0.0.1.evil.test`'i gecireyordu ve
  arayuzde proje acma varsayilani "Guvenilir" geliyordu; ikisi de duzeltildi.
- 2026-11-09 (3): **A0 asamasi uygulandi** (ajan gelistirme talimati). `OZELLIK-MATRISI.md`
  olusturuldu (A0 + F01-F24 + korunan ozellikler + A13 kapisi). Baslangic olcumu: 152 gecti,
  1 atladi, %94, ruff temiz. 8 A0 maddesi once BASARISIZ test yazilarak duzeltildi
  (`tests/test_a0_regresyon.py`, 34 test): adres ayristirma, alan bazli arac sonucu kisaltma,
  gecmiste arac kaniti, iptalde arac kaydi, tur basina baglam butcesi, akista upload siniri,
  oturum kilidi + silinmis oturuma gec cevap. Davranis degisikligi: hata olayindan sonra artik
  sahte `bitti` olayi GONDERILMEZ (iki mevcut test buna gore guncellendi).
  Sonuc: 186 test gecti, 1 atladi, coverage %94, ruff temiz (sahte model; canli model/GUI denenmedi).
  Kullanicinin verdigi referans repo: https://github.com/Twigpine/openclaude (henuz taranmadi).
- 2026-11-09 (2): kullanicinin ozellik listesine gore AGENT-GELISTIRME-TALIMATI.md hazirlandi:
  24 yetenek grubu, A0-A13 asamalari, kabul testleri ve kalite olcumu. Kod degismedi.
- 2026-11-09: ajan mimarisi incelemesi; AGENT-INCELEME-2026-11-09.md raporu eklendi, kod degismedi.
  152 test gecti, 1 atladi, coverage %94, ruff temiz. URL allowlist acigi, kesik arac JSON'u ve
  gecmiste arac kaniti kaybi sentetik denemelerle dogrulandi; canli GUI/model denenmedi.
- 2026-11-08 (3): Claude Code destegi (Anthropic uclari, adaptive dusunme kapali, billing satiri
  ayiklama), Claude-Yerel.bat, TermFlow 'Add Local Models' provider'i. 152 test, %94.
- 2026-11-08 (2): sohbet devami ekleri, sohbet araclari, skill/talimat sistemi, HF model magazasi,
  baglam ayari (16K varsayilan). 139 test, %94. Portable yeniden derlendi ve teslim klasorunde denendi.
- 2026-11-08: proje sifirdan kuruldu. Bulgular: pywebview js_api'de pencere nesnesi -> sonsuz
  ozyineleme (alt cizgili ad); adres /v1 cift ekleniyordu; "İ".lower() hatasi; durdur kilitte asiliydi.

## Siradaki adim
- Kullanici anahtar girince OpenRouter ile gercek sohbet + Test denemesi.
- Yerel E4B ile canli gorevi duzeltmelerden sonra tekrar dene (RAM bosken; ~30 dk).
- A6 skills, komutlar ve hooks (AGENT-GELISTIRME-TALIMATI.md A6). WebView2 E2E ayrica.
- Konteyneri gercekten denemek icin (kullanici onayiyla, indirme): podman machine init; podman machine start; podman pull python:3.12-slim
- Arayuz: checkpoint ekraninda hunk secip geri alma, arka plan komutuna girdi kutusu.
- A1.8 gercek izolasyon: su an "yok" olarak raporlaniyor. A2 terminaliyle birlikte kisitli
  surec/ACL ya da istege bagli WSL/container adaptoru degerlendirilecek.
- `openclaude` reposu (Twigpine) kullanilacaksa once BRAIN-POLICY dis kaynak taramasi + rapor.
- Paketleme bu oturumda YAPILMADI; portable teslim klasoru guncellenmedi.
- Claude Code ilk turu hizlandir: llama-server -ub/-b (Vulkan girdi isleme) olc; ilk istek
  5-10K token, dahili GPU'da ~14-19 tok/sn. Kisa --system-prompt ile token sayisini olc.
- GridMind'da AI motoru -> Local model (Ollama) secip gercek arayuzden denemek.
- GitHub push (kullanici onayi bekleniyor; 5 commit yerelde).
- Dahili GPU'da ilk token yavas (talimatlar ~3K token, girdi isleme ~14-26 tok/sn): isitma var;
  gerekirse BRAIN-POLICY'nin ozet surumu ya da talimati sohbet bazinda kapatma.
- Gemma 4'te 'dusunme kapali' (enable_thinking false) gercekten kapaniyor mu incele.
- E4B ve (RAM bosken) 12B olcumlerini skill tablosuna isle.

## Acik sorunlar
- Backend hata metinleri ASCII Turkce (yerel_llm skill'inden); arayuz metinleri duzgun Turkce.
- Dahili GPU: bos RAM az iken gorsel istekler duser (BellekYetersiz mesaji gosterilir).
- Kucuk modeller araci 'cagiracagim' deyip cagirmayabiliyor (otomatik skill yukleme bunu azaltir).
- Skill'lerdeki komutlar calistirilamaz (komut araci yok); model buna gore uyariliyor.
- A0 sonrasi davranis degisikligi: hata olayindan sonra artik `bitti` olayi gelmiyor; arayuz
  `finally` blogunda kapatiyor. Gercek pencerede (WebView2) canli olarak DENENMEDI.
- `cevap_akit` son turunda araclar artik calistirilmiyor: varsayilan `max_tur=6` ile arac
  calistiran tur sayisi 6'dan 5'e indi (bos yere calisip cevapsiz bitme yerine acik uyari).
- Baglam butcesi karakter tabanli tahmin; gercek tokenizer A4'te. `/tokenize` ucu kullanilmiyor.

## Dokunulmayacak kararlar
- pywebview + FastAPI (Electron degil). Ayni anda tek model. Native dialog yok (in-app modal).
