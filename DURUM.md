# DURUM - yerel-ai-studio
guncel: 2026-11-09 | son arac: Claude Code (Opus 5.5) | dal: feature/ajan-katmani

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
- [ ] A1.8 gercek izolasyon adaptoru  <- SIRADAKI
- [ ] A3 kalici Run/Step ajan dongusu | A4 baglam/hafiza/model profilleri | A5 ajan ekrani
- [ ] A6 skills/komut/hooks | A7 MCP/plugin/mods | A8 alt ajanlar | A9-A12 | A13 kalite kapisi

## Son oturum
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
- A1.8 izolasyon (Windows kisitli token/ACL ya da istege bagli WSL), sonra A3 kalici Run/Step ajan dongusu.
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
