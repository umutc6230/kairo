# DURUM - kairo
guncel: 2026-11-15 | son arac: Claude Code | dal: feature/ajan-katmani

- 2026-11-15 (21) [~] ARACLARI IHTIYACA GORE YUKLE (A4.6, kullanici istegi). Olcum (calisan Kairo /baglam): her mesajda
  128 MCP araci 34.5K token + 52 yerlesik 5.2K + skill 5.5K + talimat 3.8K = ~51K. Plan (Claude Code deferred tools):
  [x] 1 app/agent/arac_bul.py: ertele(araclar, isleyiciler, onceki_adlar): MCP semalari ESIK_TOKEN (4000) asarsa
        listeden cikar, tek 'arac_bul' (sorgu, 'select:ad' destekli; aciklamada sunucu + arac sayisi) ekler;
        bulunan semalar AYNI listeye eklenir (cevap_akit her turda ayni listeyi yollar). Isleyiciler/izin degismez.
  [x] 2 sohbet.baglam_hazirla sonunda ertele (onceki mesajlarin arac adlari yuklu gelir); runner: bul.yuklenen her
        turda semalara eklenir, run.mesajlar tool_calls select ile yuklenir, alt ajan izinli MCP'yi bekleyenden alir.
  [x] 3 arayuz: arac_bul "arama yapildi" grubunda. tests/test_arac_bul.py 4 (esik alti, erteleme+bulma+select,
        gecmis, cevap_akit 2. turda yuklu sema). OLCUM (kullanicinin mcp.json'u, yeni kod): MCP 91 arac 21.6K token
        -> 0 sema + arac_bul 245 token; toplam arac seti 5.5K. (Calisan Kairo eski kodla 128 arac 34.5K.)
        +1 runner testi (ajan gorevi 2. turda yuklu sema; duzeltmesiz DUSTUGU goruldu). Alt ajan yolu yalniz kodla.
        Gercek modelle arac_bul kullanimi GORULMEDI.
  [x] 4 tam paket (a9_masaustu haric): 798 gecti, 3 atladi, 14.2 dk; ruff temiz. COMMIT YOK.
  SIRADAKI: derle+teslim ve commit/push (kullanici onayi); gercek modelle arac_bul denemesi.

- 2026-11-14 (20) [~] SOHBET GECMISI MODELE GITMIYOR (mobil + masaustu ayni yol). Olcum (gercek ayar, OpenRouter
  deepseek-v4.1-flash, baglam_token 32768): sistem 6382 + 102 arac 19055 + paylar -> gecmise ~11 token (MCP'ler
  baglaninca eksi). Model her mesaji yeni sanip DURUM.md'yi bastan okuyordu. "Baglam boyutu" ayari data-yerel,
  OpenRouter'da gizli: kullanici degistiremiyordu. COMMIT 0b97bde + 52c1ea7 pushlandi.
  [x] 1 SohbetServisi.baglam(ayar): api.py model_baglami = model_yetenegi().baglam (goruntu_var kalibi);
        max(ayar, min(model, UZAK_BAGLAM_TAVAN=131072)). Yerelde degisiklik yok.
  [x] 2 gecmis butcesi cevap_payi ile (baglami_darat 8192 ayiriyor, gecmis 1024 ile hesaplaniyordu)
  [x] 3 gecmis_mesajlari kirpinca uyari kod=gecmis_kirpildi (eskiden sessizdi)
  [x] 4 test_a0_regresyon +2 (uzak pencere, 100 aracla gecmis gider). ruff temiz. Tam paket (a9_masaustu
        haric): 794 gecti, 3 atladi, 12.9 dk.
  [x] 5 (kullanici istegi) ARAC GRUPLARI Claude Code gibi: sohbet.js aracGrubu/ARAC_TURLERI ardisik ayni tur
        araclari katlanir satirda toplar ("4 okuma yapildi ›", "2 arac kullanildi · 1 hata"), acinca her adim
        yine ayri acilir; tek adimli grupta baslik gizli (CSS data-n=1); ayrintili modda acik. Onizlemede
        (8801, kullanicinin oturum kopyasi) goruldu: 6 adim -> 2 satir, ic ice acilma calisiyor, konsol temiz
        (tek 404 kopyalanan oturumun projesi). e2e+akis+api 35, webview2 e2e 1 gecti. Canli akista GORULMEDI.
  [x] 6 derle + teslim (kullanici "Derle ve teslim et" dedi): dist 08:14, eski Kairo (PID 15096) /T ile
        kapatildi, data korundu + yedek %TEMP%\kairo-data-yedek-081523 (json/md + oturumlar), _internal ve
        exe/bat yenilendi, Baslat.bat ile acildi 08:16 (log temiz, /web/sohbet.js yeni kod). Not: Git Bash'te
        `start "" /D` -> /D "D:/"ye cevrilip "surucu bulunamiyor" penceresi acti; PowerShell Start-Process kullan.
  SIRADAKI: telefondan canli deneme (gecmis + arac gruplari).
        Not: TermFlow mobil uyari olaylarini gostermiyor olabilir (kontrol edilmedi).
- 2026-11-14 (19): GERCEK PENCERE E2E (A5 kalan) yazildi, gecti. Buldugu 2 hata duzeltildi: (1) pencere
  kapaninca surec kapanmiyordu: acilistaki Claude Code plugin esitlemesi (telegram 3622 dosya taramasi ~1 dk)
  executor thread'inde kapanisi bekletiyordu -> daemon thread + kapanista cc_dur ile durur (api.py omur).
  (2) manifest'siz plugin yolu boyut siniri ve kurum politikasini atliyordu -> iki yol da denetleniyor
  (pluginler.karantinaya_al). test_a7_cc_plugin +2. Not: WebView2 iframe'lere chrome.webview verir ama
  pywebview yalniz ust cerceve mesajini isler (E2E bunu dogruluyor). Derleme/teslim YOK (kod degisti).
- 2026-11-14 (18): MENU HATASI: ortak.js menuAc her acilista { once: true } dis tiklama dinleyicisi kuruyordu; menu
  ogeden secilerek kapaninca (stopPropagation) dinleyici askida kaliyor, sonraki acilis tiklamasi yeni menuyu aninda
  kapatiyordu (baslik, mod, model menuleri "bir kez aciliyor, sonra acilmiyor"). Dinleyici menuKapat'ta kaldirilir,
  ayni dugmeye ikinci tik kapatir. Ayri test sayfasinda dogrulandi. Derlendi + kuruldu 16:59.
  CANLI THREAD DENEMESI (gecici veri + deneme git deposu, OpenRouter deepseek-v4.1-flash): iki isli mesaj ->
  is_emri_baslat 2 thread, ikisi kendi is/<id> dalinda bitti (carp eklendi, README aciklamasi), "her sey ne durumda?"
  -> is_emirleri_durum dogru ozet. Gecici veri silindi. Not: proje acik degilse arac "Once bir proje ac" doner.
- 2026-11-14 (17): COMMIT YOK. Telefondan (TermFlow koprusu) yazilan mesajlar acik Kairo penceresinde gorunmuyordu: oturum listesi yalniz acilista/kendi islemlerinde cekiliyordu. app.js disDegisiklikleriAl: 3 sn'lik durum yoklamasinda /api/oturumlar imzasi (guncelleme|mesaj_sayisi|baslik) karsilastirilir, degisince liste ve (akis yokken) acik sohbet yeniden cizilir. Ayri veri klasorlu sunucuda tarayicida disaridan baslik degisikligiyle dogrulandi. Portable derlendi; teslim klasorune kopyalama kullanici onayi bekliyor (acik Kairo kapanmali).
- 2026-11-13 (16): commit a4fc316 pushlandi. (1) BUYUT: cercevesiz pencere maximize() ile gorev cubugunu kapliyordu -> main.py PencereApi._calisma_alanina_sigdir: form.Bounds = Screen.WorkingArea, durum gercek sinirdan (bayrak acilista tutmuyordu). Gercek pencerede UIA ile olculdu: buyuk 0,0-1920,1140, gorev cubugu 1140-1200 acik, geri alma eski boyut. (2) AD: proje klasoru Projects\kairo, exe Kairo.exe, teslim Desktop\Portable Programlar\Kairo (data tasindi), spec paketleme/kairo.spec, pyproject/MCP clientInfo/User-Agent/OpenRouter Referer/version anahtari 'kairo' (eski 'yerel_ai_studio' anahtari arka plan tespitinde hala taniniyor). Baslangic kisayolu yeni exe'ye cevrildi. GitHub reposu henuz yerel-ai-studio adinda. Gecmis kayitlar ve degerlendirme raporlari eski adla birakildi.
- 2026-11-13 (15): TAM PAKET KOSULDU: 679 gecti, 3 atladi (test_a9_masaustu haric, 14.5 dk); test_a9_masaustu ayri 5/5; ruff temiz. Teslim exe (10:45) kaynaktan yeni, yeniden derleme gerekmedi. COMMIT YOK, push onayi bekliyor.
- 2026-11-13 (14): COMMIT YOK. MCP OAuth girisi (Vercel) "Dis kaynakli istek reddedildi" veriyordu: saglayici sitesinden /api/mcp/oauth/geri'ye yonlendirmede Referer dis oluyor, _loopback_koruma (api.py) reddediyordu. GET /api/mcp/oauth/geri kaynak kontrolunden muaf (state ile korunur); tum OAuth baglayicilari icin gecerli. test_mcp_oauth'a test eklendi (66 gecti). Portable derlendi, teslim klasorune kopyalandi (data korundu), Baslat.bat ile Kairo penceresi acildi. Gercek Vercel girisi kullanicida denenecek. (2) EKLENTILER: kullanicinin Vercel'i ekliydi ama girisi tamamlanmamisti ve "Senin eklentilerin" ilk 6'da kalmadigi icin gorunmuyordu -> OAuth'lu girisi yok baglayici "giris gerekli" rozetiyle en ustte (eklentiler.js, .rozet.uyari). Dizine 25 resmi uzak MCP eklendi (mcp_ice.DIZIN; 2026-11-13 canli yoklandi, hepsi 401 + DCR; DeepWiki anahtarsiz). Google (Gmail/Drive/Takvim/Sheets/Docs), Slack, HubSpot, Outlook, Trello: resmi DCR'li sunucu yok -> Composio bagli degilken Populer'de kart, Baglan Composio anahtar penceresini acar. Onizlemede goruldu. Tam paket test_a9_masaustu'da (gercek UIA, dusuk RAM) dustu; tek basina 5/5 gecti; tam paket yeniden KOSULMADI. Yeniden derlendi + teslim (data korundu), pencere acildi. Kullanicinin bagli giris gerektiren uygulamasi yok: Vercel girisi yok, GitHub kapali, Composio anahtari yok. Tam paket arka planda kosuyordu (sonuc yazilmadi).
- 2026-11-13 (13): COMMIT YOK (feature/ajan-katmani, son push caaf2d8). (1) NOT DEFTERI: TUR'a 50030 belge; masaustu_yaz ValuePattern yoksa/salt okunursa _klavye_yaz: pencereyi one getirir (AttachThreadInput), pano + Ctrl+V, eski pano geri konur (tek tek KEYEVENTF_UNICODE WinUI alaninda bosluktan sonra bozuyordu). Canli Not Defteri'nde dogru yazdi. (2) SOHBET PLANI: plan_guncelle sohbette (ajan araclari varken), arayuz mesaj ustunde canli liste; plan turu tur butcesinden dusmez; ajanli sohbet max_tur 20. Canli: 3 adim plan isaretlendi. (3) SAGLAYICI AYRIMI: OpenRouter seciliyken yerel model arayuzde gizli (body.uzak-saglayici, data-yalniz-yerel) ve ModelYonetici.kullan yerel modeli reddeder (or_model bossa sessizce yerele dusuyordu). (4) HIZ: her mesajda yeni httpx istemcisi + TLS ~1.5 sn -> paylasilan baglanti havuzu (_KapanmayanTasima, acilista on isitma); skill taramasi imza (stat) onbellekli. Mesaj basi uygulama yuku ~1.5 sn -> ~0.1-0.2 sn. (5) Ayarlar anahtari ezilip tasiyordu (.anahtar inline) -> inline-block + .ayar-kontrol. (6) Yuruyen canli baykus (bekliyor/dusunuyor/calisiyor/yaziyor; azalt hareket destekli). (7) GitHub MCP 'Giris yap' -> gh auth akisi (DCR desteklemiyor). (8) MESAJ GITMIYORDU: security-guidance plugin hook'u WSL bash ile calisip 127 veriyor, guvenlik hook'u diye sohbeti engelliyordu -> hook komutunda bash Git Bash'e, yol '/' ile; Claude plugin hook'u YALNIZ cikis 2 ile engeller. (9) OPENBOT (CopilotKit/OpenBot, MIT; kod kopyalanmadi): onay kapsamlari tek/sohbet(gorev, 24 sa)/her_zaman (BAGLAM contextvar, /api/onay-kurallari, Ayarlar'da liste); tam yetkide riskli eylem turleri (odeme/kimlik/silme/gonderme/paylasma/yayinlama, arac adi+ozet anahtar kelime) sorulur, siradan tiklama serbest; <dis_icerik> zarfi + kaynak gosterme kurali; Exa (anahtarsiz, dogrulandi) ve Parallel (oauth) baglayici dizininde; rutinlerde bir_kez / davranis yap|bildir / bitis_kosulu (rapor HEDEF_TAMAM -> rutin durur); Etkinlik (denetim) penceresi /api/etkinlik. (10) Tarayici canli testi gecti (giris + ekran goruntusu); tarayici_acik varsayilan True. (11) Kairo vs Claude Code ayni 6 gorev (kod, bug, cli, web, git, paralel alt ajan): ikisi de 6/6; Kairo 5/6'da daha hizli (Claude Code ilk cikti ~15 sn, kullanicinin agir plugin seti); modeller farkli (deepseek vs Claude). free-claude-code ve claude-code-best incelendi, EKLENMEDI, klonlar silindi (ikincisi Anthropic kodunun decompile'i). SIRADAKI: tam paket sonucu, derle+dagit, commit/push onayi. GORULMEDI: onay kapsam dugmeleri ve Etkinlik penceresi gercek pencerede; 'bildir' rutini yalniz talimatla (salt okunur mod zorlanmiyor).
- 2026-11-12 (12): OPENBOT ASAMA 2. (1) CLI SAGLAYICILARI app/agent/cli_ajan.py: kalici ajan saglayici=claude (Claude Code: claude.exe -p --output-format stream-json --verbose, --resume ile surekli oturum, --append-system-prompt ajan kimligi; tam yetkide bypassPermissions, degilse acceptEdits) ya da codex (node codex.js exec --json -C klasor, resume <thread>; tam yetkide danger-full-access, degilse workspace-write). Ortam ortam_allowlist (ust surecin Claude Desktop oturum degiskenleri tasinirsa ic ice CLI bos cikip cikiyordu). npm global yolu: %APPDATA%/npm/node_modules (System32\\claude 0 baytlik sahte dosya var, atlanir). Dagitim: CLI isi asyncio gorevi, aktif_run "cli:<id>", canli ilerleme satirlari /api/ajanlar/{id} "canli", /iptal surec agacini oldurur (taskkill /T). CANLI: Kairo Lider -> Claude Code Kodcu is verdi, 20 test %100 kapsama, cevap dondu, Lider dogruladi. Codex: protokol dogru ama KULLANICININ CODEX LIMITI DOLU (14 Kasim 10:18e kadar) -> hata konusmada gorunur. NOT: Claude Code ilk cagrida kullanicinin genis plugin/skill/hook seti yuzunden ~131K token onbellek yaratiyor (~$1 rapor). CLI ajanlari ajana_mesaj aracini kullanamaz (Kairo araci degil); mesaj alip cevap verebilirler. (2) SKILL OLUSTURMA: skill_kaydet araci (tum ajan gorevlerinde): yoksa olusturur, varsa okunan_revizyon guncelse gunceller; eski hal <skill>/.surumler/SKILL.r<n>.md; /api/skiller/{ad}/revizyonlar, /geri-al. Claude/brain/proje skilleri korunur. Izin: YanEtki.yaz (onayli modda sorar). skill_kullan uygulama skilinde revizyon dondurur. (3) MASAUSTU VURGUSU app/agent/vurgu.py: ctypes katmanli, tiklama gecirgen, odak almayan cerceve pencereleri (pencere MAVI, eleman TURUNCU), eylemden 0.45 sn once, 1.6 sn ekranda. DPI: is parcacigi per-monitor v2 (yoksa %125 olceklemede kayiyordu). CANLI: gercek Not Defteri'nde Sekmeyi Kapat dugmesi tiklanmadan once cerceveler ekranda (ekran goruntusu scratchpad/agir/vurgu-notepad.png). ACIK: Win11 Not Defteri yazi alani UIA Document (50030) TUR listesinde yok ve ValuePattern desteklemiyor -> ajan oraya yazamaz (SendInput yedegi gerekir).
- 2026-11-12 (11): OPENBOT OZELLIKLERI - ASAMA 1 (openbot tasarimindan, kod kopyalanmadi; NOTICE-openbot.md). (1) KALICI AJANLAR app/agent/ajanlar.py: ad/avatar/aciklama/talimat/klasor/model/hafiza, FIFO kuyruk (<=50), konusma kaydi, duraklat, her is onceki isin ozetiyle baslar (son_run). Runner: Run.ajan_id/ek_sistem, baslat(calisma_koku=ajan klasoru), ajanin kendi modeli (yonetici.kullan(model)). Kimlik metninde "dosyalari YALNIZ calisma klasorunde olustur" kurali (canli ilk denemede ajanlar BRAIN-POLICY yuzunden Desktop ve Projects altina klasor acti; o iki test klasoru scratchpad/agir/test-yan-etkileri altina TASINDI, silinmedi). (2) AJANLAR ARASI MESAJ: ajana_mesaj araci hedefin kuyruguna yazar; is bitince cevap gonderenin kuyruguna doner; zincir <=3; ajan_notu kalici hafiza. Dagitim dongusu 2 sn (_ajan_dagit), dinleyiciler (Telegram). /api/ajanlar CRUD, /mesaj, /kuyruk. (3) ARAYUZ: sol menu Ajanlar sayfasi (liste, olustur/duzenle formu, konusma, canli gorev akisi, kuyruk). (4) TELEGRAM app/services/telegram.py: Bot API getUpdates, YALNIZ izinli chat id; izinsize yalniz kendi kimligi; /ajan Ad mesaj, /durum; cevap parcali (4000). Token <veri>/telegram.json, maskeli. Ajanlar sayfasinda Telegram karti. GERCEK BOTLA DENENMEDI (token yok). (5) WEBHOOK -> AJAN: Webhook.ajan alani; olay ajanin kuyruguna veri olarak duser (proje gerekmez). CANLI: Lider->Kodcu is verdi, cevap dondu, Lider dogrulayip RAPOR.md yazdi; 22 test (bagimsiz kosuldu); klasor disina yazma yok. Testler: tests/test_ajanlar.py (6), test_a11 webhook->ajan. Tam paket 650 gecti. KALAN openbot ozellikleri (sonraki asamalar): Claude Code/Codex CLI'larini ajan saglayicisi olarak surmek, Discord/Slack/WhatsApp, mobil uygulama + WebRTC uzak erisim, hesap sistemi, marketplace, ajanin kendi skill'ini olusturmasi, capraz platform bilgisayar kullanimi + imlec vurgusu, sifre yoneticisi, ses, 15 dil, otomatik guncelleme.
- 2026-11-12 (10): AGIR CANLI TEST (OpenRouter deepseek-v4.1-flash, headless CLI + SDK, yalitilmis veri, tam yetki; betikler scratchpad/agir/kos.py, coklu.py). SONUCLAR (bagimsiz dogrulandi): (a) FastAPI+SQLite+HTML Gorev Takip uygulamasi 16 test, gercek HTTP dogrulamasi -> BASARILI (testleri ben de kosturdum). (b) books.toscrape.com scraping 60 kitap CSV/JSON + istatistik + web_ara -> BASARILI (ilk kayit siteyle ayni). (c) Tersine muhendislik: kucultulmus JS (base64+XOR) Craft Anything js_app_map + REA analyze_javascript_application + kendi betigi -> 9/9 gizli bilgi dogru (duzeltmelerden sonra). (d) Skill: application-deep-review ile inceleme + 2 gercek hata duzeltildi (16->25 test); github-readme-pro-writer + 3 referans ile README -> BASARILI. (e) TinyDB (gercek repo) gizli __le__ hatasi bulundu, between() + 5 test + docs, 233 test, git dal+commit -> BASARILI. (f) Tek sunucuda 3 ajan AYNI ANDA ~39 sn (sirali ~2 dk olurdu) + 2 paralel alt ajan (zamanlar ic ice) -> BASARILI. TESTIN BULDUGU VE DUZELTILEN KAIRO HATALARI: (1) ajan cevap payi 2048 sabit: uzun dosya tek cagriya sigmiyor, model kesilip duruyordu -> cevap_tokeni(baglam) 32K+:8192, 64K+:16384; finish_reason=length ise "parcala" uyarisi. (2) dist/build klasorleri listede hic gorunmuyordu -> gorunur ama icine inilmez; glob deseni acikca icerirse bulunur. (3) DONGU: model ayni komutu 40 kez kosup butceyi bitirdi -> ayni arac+arguman ardisik basarili 3. tekrarda calistirilmaz, 6.da gorev durur (komut_durumu vb. muaf). (4) Windows CRLF dosyada proje_dosya_yama hic eslesmiyordu (TinyDB'de 4 kez) -> LF metin CRLF'ye cevrilir, CRLF korunur. (5) komut_calistir cmd.exe ile: `;` ve cok satirli python -c bos cikti -> Git Bash varsa bash -c (windows_bash()). (6) alt ajan butcesi 12-15 adimda okumaya harcayip eli bos donuyordu -> min 15/varsayilan 25, 2 adim kala "raporla" uyarisi, butce dolarsa kismi sonuc ebeveyne. (7) token butcesi 2M cok kucuktu (47 cagrida doldu) -> 10M. (8) ALT AJANLAR SIRALI, uygulamadaki ESZAMANLI gorevler de tek model kilidi yuzunden SIRALIYDI -> uzak saglayicida (paralel_model) kilit yok, ayni mesajdaki alt_ajan cagrilari asyncio.gather ile paralel, kalan butce kardesler arasinda paylasilir; yerel modelde sira korunur. Testler: test_tam_yetki (dongu, dist, cevap_tokeni), test_a2 CRLF yama, test_a8 paralel alt ajan (zamanlama), test_a3 butce testi farkli argumanla. ACIK: model "ne/neden" cumlelerini cogu zaman Ingilizce yaziyor (deepseek; kural var); gorevi_bitir kanit kurali salt arastirma gorevinde "dogrulanmadi" verebiliyor (son yazmadan sonra okuma ister).
- 2026-11-12 (9): AJAN ACIKLAMALI AKIS (Claude Code gibi). Adim.aciklama: modelin arac cagrisiyla ayni mesajda yazdigi metin ilk cagriya baglanir; sohbette her adimin USTUNDE gosterilir (gorevler.js sohbetCiz, md). SISTEM: her cagridan once tek cumle ne/neden; gorevi_bitir ozeti rapor (yapildi/dogrulandi/dogrulanamadi/siradaki); sonuc md ile madde madde. SISTEM 8K baglama sigsin diye sikistirildi (uzayinca CLI testinde eski adimlar kirpiliyordu). Sahte model artik aciklama yaziyor; test_a10 aciklamanin kayda gectigini dogrular. Tam paket: 639 gecti, 0 kaldi. Tarayicida ornek gorevle goruldu. Portable derlenip teslim edildi (data korundu). GORULMEDI: gercek modelin bu cumleleri yazmasi (kucuk yerel modeller atlayabilir).
- 2026-11-12 (8): "HAYIR DEMEYEN AJAN" PAKETI (commit YOK; claw-code + openbot fikirleri, kod kopyalanmadi). (1) TAM YETKI: ayar tam_yetki (Ayarlar > AI > Yetkiler, acarken tek onay; ag_acik da acilir). policy.py: tam yetkide yaz/sil/komut/ag/dis(MCP, masaustu)/git ONAYSIZ; yine sorulan TEHLIKELI_KOMUT (disk/surucu silme, format, diskpart, shutdown, git push --force, reg delete HKLM, bcdedit); Planla, guvenilmeyen proje, hassas dosya, kok disi ve yonetilen politika aynen gecerli. (2) RET KAYNAKLARI KALDIRILDI: ajan SISTEM genel asistan ("yapamam/salt okunur deme, araci cagir, eksik programi kur, verilen token'i aracta kullan"); sohbet notu SISTEM_NOTU ("araclarin SALT OKUNUR, yazma aracin YOK") ve skill SINIR ("komutlari SEN CALISTIRAMAZSIN") ajan araclari varken AJAN_NOTU / SINIR_AJAN ile degisir; kapsam_notu(ajan=True). Bunlar "yapamam" cevaplarinin asil kaynagiydi. (3) WEB: ag_acik varsayilan True (eski kurulumda kayitli false kalir); DuckDuckGo arama hostu onaysiz (ARAMA_HOSTLARI), bos/202 sonucta lite.duckduckgo yedegi; gercek aramada sonuc geldi. (4) MASAUSTU: masaustu_izinli=["*"] = tum programlar (ASLA_KONTROL: consent/logonui/lockapp/credentialuibroker/securityhealth); ayarda "Bilgisayar kullanimi (tum programlar)" anahtari. Pencere vurgulama YAPILMADI. (5) GITHUB: POST /api/github/baglan: gh CLI token varsa github MCP (api.githubcopilot.com/mcp) Bearer ile eklenir/guncellenir; yoksa "gh auth login -w" ayri konsolda acilir, arayuz ?kontrol=true ile 5 sn arayla bekler; gh yoksa winget komutu soylenir. Dizindeki GitHub karti bunu kullanir. GERCEK GIRIS DENENMEDI. (6) Ayarlar arama kutusu (eslesmeyen satir/sekme gizlenir). (7) Kisisel alanda ajan araclari hafif: proje_listele/glob/ara, git_*, lsp verilmez (~900 token; 8K yerel model icin). "Sohbette araclar" kapaliysa kisisel alanda hic arac gitmez. Testler: yeni tests/test_tam_yetki.py 12; davranis degisikligiyle eskiyen beklentiler guncellendi (test_a2 kisisel alan, test_a9_tarayici, test_a9_web varsayilan ag, test_api eski resim testi araclar kapali). TAM PAKET: 638 gecti, 3 atladi, 1 kaldi (test_servisler portable: app/degerlendir.py surece YAS_VERI_DIZINI birakiyor, sira bagimli; teste delenv eklendi, tek basina gecti, tam paket yeniden KOSULMADI). Ajan SISTEM 8K baglama sigsin diye kisaltildi (uzun hali CLI testinde eski adimlari kirptiriyordu). test_a3/test_a8 proje-yok beklentileri guncellendi. Tarayicida goruldu: tam yetki onay penceresi + kayit, ayar aramasi. GORULMEDI: gercek modelle ajanin artik reddetmemesi, GitHub girisi, tum programlarda masaustu kontrolu. COMMIT 95fb7cb pushlandi (feature/ajan-katmani). Portable derlendi ve teslim klasorune kopyalandi (data korundu); yeni exe acildi, log temiz.
- 2026-11-12 (7): KULLANICI SIKAYETLERI (commit YOK). (1) "sohbet modu salt okunur" KOK NEDEN: proje acik degilken varsayilan alan Mod.sohbet idi ve ajan araclari yalniz projede veriliyordu; GitHub/MCP, yazma, komut reddediliyordu. Artik varsayilan alan Mod.onayli + ajan araclari kisisel klasorlerde de var (sohbet.py aktif_alan/ajan_araclari, sohbet.js ajanModu). Yan etkiler onay kartiyla gecer. Tarayicida /api/izinler mod=onayli goruldu. (2) OpenRouter 400 "Reasoning is mandatory": dusunme kapaliyken {enabled:false} gidiyordu. openrouter.py: gercek effort (dengeli=low, derin=high); _DusunmeDuzelten transport 400 gelince ayni istegi effort=low ile bir kez tekrar atar ve modeli ZORUNLU_DUSUNME kumesine ekler (bellekte). Sahte transportla dogrulandi; gercek OpenRouter ile DENENMEDI. (3) AI Ayarlari bolumlendi: Model / Dusunme / Yetkiler / Cevap / Yerel motor (yapiskan kisayol cubugu); OpenRouter seciliyken yerel-yalniz gruplar gizli; Dusunme secili modelin yetenegine gore (desteklemiyorsa kilitli "kapali"). Tarayicida goruldu. (4) claw-code (MIT, Rust) ve openbot (PolyForm Noncommercial, TS) incelendi; kod KOPYALANMADI (dil farki + openbot lisansi). Alinan fikir: model basina desteklenen effort listesi (openbot provider-models.ts), varsayilan izin = calisma alanina yazma + sor (claw-code permissions.rs). test_a2 eski beklentisi guncellendi. PORTABLE TESLIM GUNCELLENMEDI: kullanicinin actigi Kairo 0.1.0 eski; degisiklikleri gormesi icin paketleme\derle.bat + teslim kopyasi gerekir.
- 2026-11-12 (6): ARAYUZ INCELEMESI + DUZELTME (commit YOK; yalniz app/web/app.css, ayarlar.js, index.html). Tarayicida yalitilmis veriyle (model yok) koyu/acik tema, 1366/960/telefon genisliklerinde bakildi. Bulunan ve duzeltilen: (1) Ayarlar penceresi: 11 sekme yatay sigmiyordu ("Hakkinda" kesik, "AI Ayarlari" iki satir, yatay kaydirma cubugu), sekme degisince pencere boyu zipliyordu, sekmeler icerikle kayiyordu -> sol dikey sekme listesi + sabit boy (.modal.ayarlar / .ayar-pencere), role=tab/aria-selected. (2) ACIK TEMA: ana dugme (.btn.ana) ve gonder dugmesi koyu zemin + koyu yazi = okunmuyordu; anahtar (toggle) kapaliyken gorunmuyordu; kaydirma cubugu koyu; hata/uyari/tehlike yazilari acik pembe/sari; aktif sohbet ve hover zemini kenar cubuguyla ayni tondaydi -> sabit hex'ler tema degiskenine (--ana-metin, --tehlike-metin, --uyari-metin, --kaydirma, --vurgu tanimlandi; acik temada --yuzey2/3 koyulasti). (3) DAR PENCERE: dock (terminal/degisiklik/tarayici, 460px sabit) + kenar (300) + oturum paneli (280) acikken sohbet alani ~125px'e eziliyordu (en kucuk pencere 960) -> dock clamp(340,34vw,460), <=1500px'te dock acikken oturum paneli gizlenir, <=1100 dock 340, <=900 dock ust katman; kenar <=1200px'te 248px (--kenar-gen). (4) Bos durum kartlari 440px sabitti, dar alanda tasiyordu; alcak pencerede kart ezilip "Dusunme" satiri kayboluyordu -> min(440px,100%), flex-shrink 0, uzun ad uc nokta. (5) "Bellek az" etiketi iki satira bolunuyordu; alt satirdaki model hapi tasiyordu -> nowrap / sarma. (6) ASCII Turkce ipuclari (Kenar cubugunu, Ileri, Kucult, Buyut, Hakkinda, AI Ayarlari, Model klasoru) duzeltildi. Dogrulama: tarayicida oncesi/sonrasi goruldu, konsol hatasi yok; node --check ayarlar.js; pytest test_a13_e2e + test_a5_dikte_a11y + test_a5_onay + test_a5_review_artifact + test_a6_hooks + test_a8_akis + test_api: 63 gecti. Tam paket KOSULMADI. GORULMEDI: gercek pywebview penceresi, ajan/onay kartlari ve akan cevap (model gerekir), acik temada tum ayar sekmeleri. ACIK KALAN: <=1100px'te oturum paneli dugmesi islevsiz (panel CSS ile gizli); "Bellek az" bandi kapatilamiyor. Portable teslim guncellenmedi.
- 2026-11-12 (5): CC ESDEGERLIK ACIKLARI KAPATILDI (commit YOK). (1) E2E KARARSIZLIGI KOK NEDEN: test HAZIR'i durum cubuguna bakiyordu; o an sohbetKur (Enter isleyicisi) henuz baglanmamisti ve acilisin sonundaki git({tur:'yeni'}) -> yeniSohbetEkrani() girdiyi siliyordu (kullanicida da: acilirken yazilan metin kayboluyordu). Duzeltme: acilista girdi korunur (girdiyiKoru), baslat() sonunda html[data-hazir=1]; E2E bunu bekler. (2) CANLI GORULDU (OpenRouter deepseek-v4.1-flash, yalitilmis veri, tarayici): soru_sor karti -> 'Turkce' tiklandi -> ayni adimdan surdu -> yazma onayi -> README.md diskte Turkce; /compact duz sohbette 3 turu ozetledi, sonra 'adim/rengim ne' dogru cevaplandi (ajan sohbetinde /compact tasarim geregi yalniz bilgi notu). (3) ARAYUZ HATALARI: OpenRouter seciliyken model hapi yerel modeli gosteriyordu; 'Bellek az' bandi yerel model icin cikip onay kartinin dugmelerini ortuyordu -> uzak modelde yerel uyarilar bastirildi (tarayicida dogrulandi). (4) URUN HATASI: tepsi.py tipsiz ctypes cagrilari 64-bit tutamaci c_int'e kesiyordu -> RegisterClassW'de access violation (Windows yutuyordu); argtypes/restype eklendi, 3/3 temiz. (5) degerlendir --ajan claude-code None donduruyordu -> 0. (6) KAPSAM: yeni tests/test_cli_birim.py, test_degerlendir_birim.py, test_tepsi.py (GERCEK Shell_NotifyIcon), test_masaustu_ayar_birim.py (GERCEK RegisterHotKey): 43 test; dosya kapsamlari cli %83 (tek basina), degerlendir %30->%85, tepsi %0->%94, masaustu_ayar %46->%97. Tam paket ONCEKI kodla: 585 gecti, 3 atladi, 0 kaldi, %87 (E2E dahil gecti). YENI testlerle tam kosu YAPILAMADI: WinError 1450 (bos RAM 0.5 GB; portable Kairo Gemma E4B'yi acmisti, 7.5 GB). Tahmin ~%90.6, OLCULMEDI. Ruff temiz. Gozlem: ajan cevabinda 'plan_guncelle(...)' ham metin olarak gorundu (model metni).
- 2026-11-12 (4): MODEL GECIDI KULLANDI (canli, ilk kez goruldu). Headless CLI, yalitilmis veri (YAS_VERI_DIZINI, mcp.json'da yalniz craft-anything), OpenRouter deepseek/deepseek-v4.1-flash, --mod onayli --guven sinirli. Hedef: 2 dosyalik sentetik JS uygulamasi (main.js + sepet.js, bilinen cevapli). Akis: arac_ara("javascript static analysis") -> arac_sema(js_app_map) -> arac_cagir(js_app_map, format=directory) ONAY BEKLEDI (cikis 3) -> --onayla/--devam -> BASARILI, 7 adim, 6 model cagrisi, 17 sn, 77K token. Cevap gercekle birebir: taban adres, 2 uc nokta (satir no dahil), 2 modul. Kod degismedi; gercek data/ dokunulmadi. Asagidaki (3) ve (2) kayitlarindaki "commit bekliyor" ESKI: hepsi 8fc9e08'de ve push edildi. HALA GORULMEDI: native/apk hedefi (Ghidra/apktool/adb/frida kurulu degil), REA ile model isi, yerel modelle gecit, arayuzde (pencere) ayni akis. Not: 6 cagride 77K token = cagri basina ~13K; js_app_map ciktisi buyuk, kucuk baglamli yerel modelde sigmayabilir.
- 2026-11-12 (3): Craft Anything KULLANICI ONAYIYLA KURULDU: v0.6.1 windows-x64 portable, SHA256 eslesti, data/araclar/craft-anything (141 MB), baglayici "craft-anything" = craft-anything-cli.exe mcp --all-tools --deep. Arac sayisi kipe bagli (olculdu): bayraksiz 30, --all-tools 108, +--deep 323 (deep = hedefin kodunu okuyan araclar; onsuz clean-room). --allow-run EKLENMEDI. Gecitle modele giden sema ~2.4K karakter (REA + Craft birlikte 6 arac). Gercek cagri: core_session_show cevap verdi; arac_ara native/js/web araclarini buldu. GORULMEDI: bir hedef uzerinde gercek inceleme, bir modelin gecidi kullanmasi; Ghidra/apktool/adb/frida gibi motorlar kurulu degil (ilgili araclar onlarsiz calismaz). Asagidaki "(2)" kaydindaki "INDIRILMEDI/KURULMADI" artik gecersiz.
- 2026-11-12 (2): ARAC PAKETLERI (commit bekliyor). app/services/arac_paketleri.py: surumu+ozeti SABIT hazir arac setleri, <veri>/araclar/<ad> altina kurulur, paketin kendi setup komutu HIC calismaz (kullanicinin Claude/Codex ayarina dokunulmaz). Ayarlar > Baglayicilar > "Arac paketleri" (Kur/Kaldir, onay penceresi), API /api/arac-paketleri (istek govdesi adres/surum veremez). REA (rea-agents@6.3.0, npm --ignore-scripts, package-lock butunluk ozeti dogrulanir; skill <veri>/skills'e kopyalanir + Kairo kullanim notu) GERCEK kuruldu ve data/araclar/rea'da (101 MB), baglayici "rea" kayitli. Craft Anything (v0.6.1 windows-x64 portable zip, SHA256 sabit, zip-slip/symlink reddi, craft-anything-cli.exe mcp) KODU HAZIR ama INDIRILMEDI/KURULMADI: kullanici onayi bekliyor (hazir ikili, kaynakla ayni oldugu dogrulanamaz; depo 2026-10-31; kendini gunceller, ek arac indirir, ajan baslatir; kaynaktan derleme Rust 1.97 ister, makinede 1.90). MCP GECIDI (app/agent/mcp.py): semalari buyuk sunucu (TEMBEL_ESIK 40K karakter ya da tembel=True) modele tek tek degil 3 aracla sunulur: mcp__<ad>__arac_ara / arac_sema / arac_cagir; cagri GERCEK arac adiyla ayni izin motorundan gecer. Neden: REA 139 arac = ~2M karakter sema (~505K token), hicbir modele sigmaz; gecitle ~1K karakter. Dogrulama: tests/test_arac_paketleri.py 15 test (sahte npm/indirme, aga cikmaz); gercek REA: kur 32 sn, arac_ara/sema/cagir gercek sunucudan cevap aldi; tarayicida bolum + Baglan (139 arac) goruldu, konsol hatasi yok. Tam paket: 584 gecti, 3 atladi, 1 kaldi (test_a13_e2e /doctor zaman asimi; tek basina geciyor, bu degisiklikten once de vardi), kapsam %87. GORULMEDI: bir modelin gecidi kullanarak REA ile is yapmasi (model gerekir). Not: ~/.claude/skills'teki ayni adli skill once gelir (Kairo notu olmayan); bu yuzden kullanim ipucu arac_cagir aciklamasinda da var. Portable teslim klasoru guncellenmedi.
- 2026-11-12: "Claude Code esdegerlik" paketi TAMAMLANDI (commit bekliyor): konusma surekliligi (onceki gorev ozeti), soru_sor araci + cevap_bekliyor + soru karti, hook olaylari alt_ajan_bitis/bildirim (SubagentStop/Notification), ozel slash komutlari (.claude/commands; proje yalniz guvenilirde), sohbet /compact (/api/oturumlar/{id}/ozetle), girdi.js ("/" komut + "@" dosya tamamlama), "!komut" ve "#not" kisayollari, yeni komutlar (/cost /todos /export /rewind /resume /rename /init /loop /add-dir /bashes /usage /output-style /security-review). "Henuz yok" komut listesi kalkti (hepsi gercek). Dogrulama: ruff + format temiz, tum JS modul kipinde --check; tests/test_cc_esdegerlik.py 13 test; eskimis 2 beklenti guncellendi (test_a6_hooks slash, test_a7_cc_plugin Notification->SessionEnd). Tam paket: 570 gecti, 3 atladi, 1 KALDI (asagida), kapsam %87. Tarayicida GORULDU (yalitilmis veri, model yok): "/" onerileri + proje ozel komutu, Tab tamamlama, "@" klasor/dosya tamamlama, !echo ciktisi + Mesaja ekle, #not hafizaya yazildi, /help listesi, konsol hatasi yok. GORULMEDI: ajan soru karti ve /compact (model gerekir; bos RAM ~2 GB). ACIK: (1) tests/test_a13_e2e.py tam kosuda 4 denemenin 3'unde /doctor penceresini 15 sn icinde goremeyip dustu, tek basina 4/4 gecti; neden kanitlanmadi (aday: bilinen "acilisin ilk ~1 sn'sinde yazilan girdi temizleniyor" yarisi + dusuk RAM). (2) Kapsam %87 < hedef %90: dusus bu paketten degil; app/services/tepsi.py %0 (102 satir), app/degerlendir.py %30, app/main.py %42, app/services/masaustu_ayar.py %46, app/cli.py %56. Bu pakette runner %91.
- 2026-11-11: Urun adi Kairo yapildi (URUN_ADI, basliklar, X-Title), yeni piksel baykus karakteri ikonlar.js LOGO + app/web/kairo.svg favicon. Paket/klasor adi degismedi.
- 2026-11-11: Eksikler tamamlandi: sistem tepsisi (ctypes Shell_NotifyIcon, ek paket yok; kapat = tepsiye gizle, ayar sistem_tepsisi), yan sohbet paneli (Ctrl+;, ayri oturum), plan paneli (calisan ajanin plani, 3 sn), MCP OAuth girisi (kesif + dinamik kayit + PKCE + yenileme, /api/mcp/{ad}/oauth, geri: /api/mcp/oauth/geri; dizine Linear/Notion/Sentry). Masaustunde dogrulandi: kapat->tepsi, Ctrl+Alt+Space ile geri gelme, tepsi tiklamasi. OAuth: sahte sunucuyla uctan uca test + Linear/Notion'da kesif+kayit; gercek giris kullanicida.
- 2026-11-11: Claude Desktop ayarlari: Gorunum (tema sistem/acik/koyu, yazi boyutu, sohbet genisligi, hareket), Bildirimler (Windows toast: yanit/onay/rutin), Masaustu (baslangicta ac = Startup .lnk, genel hizli acma kisayolu RegisterHotKey, dikte kisayolu, depolama), Kod (ayrinti duzeyi, cikti stili, branch oneki, arsiv gunu, uyanik tut). Baglayicilar: Claude Code (~/.claude.json) + Claude Desktop (config + uzantilar) MCP ice aktarma ve 8'li hazir dizin. Toast ve Startup kisayolu gercek Windows'ta dogrulandi; genel kisayol kayit oluyor ama tetiklenmesi bu ortamda dogrulanamadi. Sistem tepsisi ve MCP OAuth yok.
- 2026-11-11: Claude Code plugin'leri acilista otomatik ice aktarilir (cc-esitleme.json; kullanicinin kaldirdigi geri gelmez; sembolik link/gizli Unicode varsa onay bekler; hook/MCP kapali) + 'Simdi esitle' dugmesi. 11/12 plugin kuruldu, 100 skill (46 plugin). Skill secimi artik modelle (kelime eslesmesi adaylari daraltir, model numara secer, sayi gelmezse eski yonteme duser); OpenRouter deepseek-v4.1-flash ile 7/7 dogru (eski 1/7).
- 2026-11-11: Claude Desktop paneli 2: ust cubukta Terminal (Ctrl+`, /api/terminal, proje kokunde, girdi + durdur), Degisiklikler (git diff), Tarayici (adres + iframe) dugmeleri; sol menude Rutinler sayfasi (6 sablon, olustur/duraklat/sil, Simdi calistir -> /api/zamanlamalar/{id}/calistir); ... menusu: Arka plan isleri, Ajan gorevleri, Bilgisayari uyanik tut (/api/uyanik, SetThreadExecutionState). Tarayicida dogrulandi: terminal echo, rutin sablonlari. Side chat ve Plan paneli eklenmedi.
- 2026-11-11: Claude Code Desktop duzeni: ust cubuk (baslik menusu: adlandir/catalla/disa aktar/sil; panel, gorevler, artifact, dosyalar, diger dugmeleri), sag panel (Ortam + ayar, proje, Uzak erisim anahtari, Baglam %, Baglayicilar, Ciktilar, Dosyalar agaci + dosya goruntuleyici), alt durum cubugu (sunucu, proje, RAM, baglayici, surum). Yeni API: /api/proje/dosyalar, /api/proje/dosya, /api/oturumlar/{id}/baglam, /favicon.ico. Gorev cubugu ikonu: AppUserModelID + WinForms Icon (app/web/kairo.ico); exe ikonu paketleme/ikon_uret.py ile baykus. Masaustunde dogrulandi: gorev cubugunda Kairo + baykus.
- 2026-11-11: Claude Code plugin uyumlulugu tamam: Plugin sekmesi "Claude Code'dan ice aktar", git/marketplace kurulumu, bilesen ozeti, hook/MCP ac-kapa (varsayilan kapali); /plugin:komut sohbette genisletilip mesaj olarak gider. Tarayicida code-review plugin'i ice aktarildi + komut genisledi. Uzanti (Mods) sistemi eklendi (F09). Testler: 331+ gecti.

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
- [ ] A2 ertelenen: arayuzde hunk secimi. (git worktree A8.3'te, push/PR superajan D4'te yapildi)
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
- [x] A5 kalan: gercek WebView2 penceresinde E2E (tests/test_a5_webview2_e2e.py; CDP ile gercek pencereye
  baglanir: kopru ana sayfada, sandbox iframe'lere sizmiyor, menu tekrar acilir, kapat sureci bitirir)
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
- [ ] A7 kalan: MCP prompts, plugin eval + token/sure raporu (ertelendi). (OAuth akisi ve Mods yapildi: mcp_oauth.py, fb16470)
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
- [x] A8 arayuz: sag panelde Takim panosu (gorevler, sahip, bagimlilik, mesajlar); /akis penceresi (JSON ile
      baslat, adim durumlari, onay sonrasi devam). Tarayicida GORULMEDI (oturumda tarayici araci yoktu).
- [x] A9.1 web okuma (app/agent/web.py, web_getir): izin motoru (YanEtki.ag, host); ag yonetilen politikada
      KAPALIYSA arac modele sunulmaz; yerel/ozel ag (SSRF) reddedilir; yonlendirmede yeni host yeniden izin;
      2 MB / 20 sn; HTML->metin (script atlanir); kaynak URL + tarih + "dis veri, talimat degil"; sir maskesi.
- [x] A9 internet ayari: Ayarlar'da 'Internet erisimi' (ag_acik, varsayilan kapali); kurum ag_yasak ile ezer
      (ust sinir). web_ara (DuckDuckGo HTML): web_getir ile ayni izin/SSRF/yonlendirme cekirdegi, javascript:
      linkleri elenir, ozetlerde sir maskeli, her istek onay ister. tests/test_a9_web.py
- [x] A9.2-4 tarayici (app/agent/tarayici.py, Playwright ISTEGE BAGLI, requirements'ta yok): yalniz <veri>/tarayici-profili
      (kullanici profili/cerez/sifre/debug portu yok); git/oku/tikla/yaz/sec/yukle/ekran/hatalar; gezinme ag kuralina
      bagli, dis sitede etkilesim HER ZAMAN onay (eleman+deger onizlemeli), yukleme yalniz proje kokunden.
      Ayarlar'da 'Tarayici kontrolu' (varsayilan kapali), /browser + /browser kapat (acil durdurma).
      Kabul: yerel fixture sitede GERCEK gorunmez Chrome ile form/select/yukleme/konsol hatasi/404/ekran.
- [x] A9.5-6 masaustu (app/agent/masaustu.py, comtypes UIA, ek paket yok): yalniz izinli programlar (Ayarlar:
      'Masaustu kontrolu: izinli programlar', varsayilan bos=kapali); her eylemde pencere YENIDEN dogrulanir
      (yanlis/izinsiz pencereye islem yok); tiklama/yazma YanEtki.dis = her zaman onay; /masaustu durdur|devam;
      UAC/kilit ekrani desteklenmez. Kabul: sentetik WinForms penceresinde yaz+tikla+sonuc okundu.
- [x] A10.3 headless CLI: python -m app agent "<hedef>" --proje P [--guven --mod --kabul --max-adim --izole --json];
      uygulama 127.0.0.1 gecici portta (Ollama gecidi KAPALI) + SDK; onayda BEKLEMEZ: kod 3 + bekleyen onaylar;
      --onayla ID --devam RUN surdurur. Kodlar 0 basarili/1 basarisiz-iptal/2 dogrulanmadi/3 onay/4 hata.
- [x] A10.4 Python SDK (app/sdk.py Studio): ayni /api (ayri motor yok); gorev/izle/islem/onay/mesaj.
      Kabul: ayni fixture gorevi CLI (gercek alt surec, sahte model) ve SDK ile ayni 'basarili' sonuc.
      Bulgu: oturum anahtari istisnasi startswith('/api/bilgi') idi -> tam esitlik.
- [x] A10.7 /doctor (/api/doctor): llama.cpp, modeller, disk, git, rg, node, Playwright, anahtar var/yok.
- [x] A10.1 LSP (app/agent/lsp.py): genel stdio istemci (Content-Length JSON-RPC, sunucu isteklerine cevap,
      publishDiagnostics); kod_tanim/referanslar/semboller/tanilar; proje disi sonuc elenir; sunucu yok/coker/
      takilirsa metin aramasi YEDEGI ('yedek': true + neden). Sunucular yalniz Ayarlar'dan (lsp_sunuculari).
      Makinede dil sunucusu kurulu degil: sozlesme kendi test sunucusuyla. Bulgu: Windows'ta tirnakli komut yolu
      tirnaklariyla calistiriliyordu -> komut_parcala.
- [~] A10 kalan ATLANDI (kullanici karari 2026-11-10): VS Code/JetBrains, TS SDK, GitHub/GitLab, deep link,
      guncelleme/rollback.
- [x] A11.1-2,5 zamanlayici (app/agent/zamanlayici.py): YALNIZ uygulama acikken (30 sn dongu); aralik/gunluk,
      saat dilimi (varsayilan ayar saat_dilimi), DST (yok olan saat ileri kayar, iki kez yasanan BIR kez),
      kacirilan = atla|bir_kez, idempotent anahtar (restart dahil), overlap atlanir, sinirli retry,
      gozetimsiz onay YOK (onay_bekliyor = overlap). Projesi acik degilse calismaz, acik proje degistirilmez.
      /api/zamanlamalar + sohbette /schedule. Kabul: sahte saatle 9 test.
- [x] A11.3 webhook (app/agent/webhook.py): /api/webhook/<id> oturum anahtarsiz ama HMAC imzali
      (zaman.teslim.govde), +-5 dk zaman penceresi, tek kullanimlik teslim kimligi (restart dahil), 64 KB,
      FIFO kuyruk (5), olay metni hedefe YALNIZ VERI olarak (mod/izin degismez), sir bir kez gosterilir.
- [x] A11.4 CI: .github/workflows/ci.yml (ruff + format + JS --check + pytest + junit/coverage artifact,
      contents:read, pull_request_target yok). ajan.yml: yalniz workflow_dispatch + korumali 'ajan' ortami,
      kisa omurlu YAS_OPENROUTER_ANAHTARI (diske yazilmaz, alt surece gecmez), CLI --openrouter-model,
      push/PR yok, diff+olaylar artifact.
- [x] A12.1-3 Remote Control (app/uzak.py, app/web/uzak.html): VARSAYILAN KAPALI. Kullanici karari (2026-11-10):
      telefon Tailscale uzerinden masaustu uygulamanin TAM arayuzunu kullanir (ince istemci, tum mantik PC'de).
      Masaustu uygulama DEGISMEDI (pywebview); uzak erisim ek ve istege bagli.
      - Varsayilan ag 'tailscale': yalniz Tailscale IP'sini dinler + 100.64/10, fd7a:115c:a1e0::/48 disi ret.
      - TLS (kendinden imzali, Tailscale IP SAN'da, parmak izi gosterilir); sunucu ANA event loop'ta.
      - Eslesme: 8 karakter, 5 dk, tek kullanimlik kod + rol (tam/izleyici/operator/onaylayici).
        Token 256 bit, yalniz ozet saklanir, 12 sa + sessiz dondurme, cihaz omru 30 gun, aninda iptal.
        Cerez HttpOnly+Secure+SameSite=Strict; Origin kontrolu (CSRF); rate limit; denetim (token yok).
      - tam rol: ayni surecteki ana uygulamaya ASGI gecidi; yerel oturum anahtari telefona GITMEZ
        (sayfaya 'uzak' gomulur, gecit gercek anahtari ekler). Diger roller yalniz sinirli beyaz liste.
      - Telefon duzeni: <=700px kenar cubugu ust katman. Sohbette /uzak, /uzak ac|kapat|kod tam|iptal.
      Kabul: 2 cihaz eslesme/revoke/reconnect, rol/beyaz liste/CSRF/IP reddi, GERCEK TLS ile tam arayuz.
      Canli telefon denemesi YAPILMADI (Windows guvenlik duvari izni ilk acilista sorulabilir).
- [~] A12.4-6 cloud worker / Projects handoff / Bedrock-Google-Microsoft gateway: DIS BAGIMLILIK BEKLIYOR
      (hesap/sunucu yok; ucretli kaynak ayrica yetkilendirilmeli).
- [~] A13 kalite kapisi (devam ediyor):
      - [x] Python kapsami %91 (hedef %90); ruff temiz.
      - [x] Iptal kapisi (tests/test_a13_kapi.py): BULGU: komut calisirken iptal 30 sn bekliyordu ve surec
            agaci oldurulmuyordu. Duzeltme: komutlar gorev kimligiyle isaretlenir (AKTIF_RUN contextvar),
            iptal o gorevin surec agaclarini hemen kapatir. Olcum: durum < 1 sn, cocuk+torun < 5 sn.
            Donanim: Windows 11 Pro, yerel gelistirme makinesi.
      - [x] Ag kapaliyken yerel ajan calisir; web_ara anlasilir hata doner.
      - [x] Arayuz E2E (tests/test_a13_e2e.py, kurulu Chrome + Playwright, gercek sunucular): masaustu
            1280x800 /doctor + /schedule; telefon 390x844 uzak TLS -> eslesme -> tam arayuz, yerel anahtar
            sayfada yok, yatay tasma yok, kenar cubugu ac/kapa, /status uzaktan. Ekranlar gorsel kontrol edildi.
            BULGU+DUZELTME: telefonda model kartlari/uyari bandi 440px sabit -> ekrandan tasiyordu.
            Kucuk bulgu (acik): acilisin ilk ~1 sn'sinde yazilan girdi, hazirlik bitince temizleniyor.
      - [x] Degerlendirme altyapisi: degerlendirme/gorevler.py (v1, 30 gorev: 6 hata, 5 ozellik/refactor,
            4 test/build, 4 kesif/review, 4 uzun/devam, 4 toparlanma, 3 web/entegrasyon; Python/TS/JS/C#).
            Gizli kontroller kosudan sonra kopyalanir; korunan test dosyasi degisirse kosu BASARISIZ;
            test yazma gorevi mutasyonla denetlenir. `python -m app degerlendir [--openrouter-model M]
            [--tekrar 3]` -> rapor JSON + MD (basari, yanlis basari beyani, mudahale, arac hatasi, sure,
            ilk adim, token, surumler/donanim). Gorev seti testi: 30/30 baslangicta kalir, cozumle gecer.
            BULGULAR: yeni veri klasorunde OpenRouter listesi bos -> her model 'aracsiz' sayiliyordu (CLI de);
            tirnakli ortam degiskeni anahtari gecersiz sayiliyordu. Ikisi duzeltildi.
            Duman testi (nemotron-3.5-super-vl:free): median GECTI; slug KALDI + yanlis basari beyani.
      - [x] Tam kosu + Claude Code karsilastirmasi (degerlendirme/KARSILASTIRMA-2026-11-11.md):
            Yerel (nemotron-3.5-super-vl:free) %83.2 / 95 olculen kosu (13 olculemedi: kota/harness);
            yanlis basari beyani 11; kesif/review %25, entegrasyon %66.7, ozellik %80, digerleri %95-100.
            Claude Code 2.1.322 (Opus 5.5) %100 / 30 kosu, 3.36 $, ort. 26 sn. Fark -16.8 puan:
            esdegerlik SAGLANMADI; fark urun+model toplami (farkli modeller), tavan etkisi var.
            Harness BULGULARI: onay sonrasi 'devam' yarisi; claude.cmd tirnak hatasi (exe dogrudan);
            test EKLEYEN ajan haksiz cezalaniyordu -> korunan testler orijinaline geri yuklenir;
            saglayici kotasi 'olculemedi' olarak ayrilir. Tum olculen kosular sayilir (iyi secilmez).
      - [x] Iyilestirme (kullanici: 'eksik yuzdeleri gelistir, Claude Code ile ayni olacak'). Testler/izinler
            GEVSETILMEDI. URUN HATALARI: (1) hassas dosya filtresi 'parola/password' kelimesini klasor ve kaynak
            kod adlarinda da ariyordu: adi 'parola' gecen PROJE KOKU tamamen okunamiyordu -> kelime kurali yalniz
            kod-disi dosyalara (credentials.json, passwords.txt; .env/anahtarlar her zaman gizli);
            (2) dosya_ara bos klasorde Masaustu'nu ariyordu -> proje acikken proje koku; (3) ardisik 6 izin
            reddinde gorev durur (40 adimlik ret dongusu vardi); (4) sistem istemi: cevabi yalniz okunan
            koddan cikar, yazilan dosyayi geri okuyup dogrula, test yoksa calistirarak dogrula.
            OLCUM HATASI: review-ts-kullanilmayan kontrolu dogru cevabi aciklama satiri yuzunden reddediyordu
            -> yalniz liste maddeleri sayilir (Claude Code icin de ayni).
            Yeniden olcum (ayni model): kesif 3/12 -> 12/12, todo-filtre 0/3 -> 3/3, tekrar-dene 0/3 (model).
      - [x] Tam yeniden olcum 30x3 (OpenRouter deepseek-v4.1-flash, ucretli): %98.9 (89/90), yanlis basari
            beyani 0, olculemeyen 0; kesif %25 -> %100. Kalan: uzun-py-buyuk-dosya 1/3 kaldi (ajan kendisi
            basarisiz dedi), ek 5 kosu 5/5 -> model kararsizligi. OLCUM HATASI duzeltildi: 2 kesif kontrolu
            tablo bicimini ve aciklama bolumunu cezalandiriyordu. degerlendirme/KARSILASTIRMA-v2-2026-11-11.md
      - [ ] Hedef >=%99: ayni kosuyu tekrarla ya da kararsiz gorev icin uzun-dosya stratejisini guclendir  <- SIRADAKI
- 2026-11-10 (16): A6 bitti (hooks + slash + hook UI; tarayicida dogrulandi). DIKKAT: ayni dalda paralel
  bir oturum A6.1/A6.2 commit'ledi (14da54a, 1c791d4); benim skill commit'im (81b748a) onlarla ust uste.
  399 test geciyor.
- [x] A5 ajan ekrani
- [x] A7 MCP/plugin/mods | A8 alt ajanlar | A9-A12 (A13 kalite kapisi ayri maddede: %98.9, hedef %99)

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
- GROK BOT KARSILASTIRMASI (kullanici istegi 2026-11-14): var olanlar: hafiza, bilgisayar kullanimi, coklu ajan + mesaj,
  rutinler/webhook, GitHub, MCP/plugin/Composio, artifact, uzak erisim + Telegram, onay kapsamlari. EKLENECEK:
  - [x] Hafiza ice aktarma: HafizaDeposu.ice_aktar + POST /api/hafiza/ice-aktar + Ayarlar>Hafiza 'Ice aktar' modali (ayarlar.js). tests/test_ogrenen_c.py +2. Pencerede GORULMEDI
  - [x] Proaktif oneriler: app/services/oneriler.py (DURUM.md [~]/[ ] maddeleri, INSAN_BEKLIYOR thread'ler, 24 sa icindeki rutinler) + GET /api/oneriler; bos ekranda 'Oneriler' (app.js onerileriCiz; durum maddesi -> projeye gecer + mesaj kutusunu doldurur, thread -> Ajanlar, rutin -> Rutinler). tests/test_oneriler.py
  - [x] gorsel_uret araci: OpenRouterDeposu.gorsel_uret (POST /images {model,prompt} -> b64_json), modeller(gorsel=True) (?output_modalities=image, ayri onbellek); ayar gorsel_model (vars. recraft/recraft-v4.1-flash-v2:free, bos = kapali); sohbet GORSEL_URET_ARACI yalniz uretim isteginde + OR anahtari varken, YanEtki.yaz onayi, media_type'a gore uzanti; AI Ayarlari > Model'de 'Gorsel uretim modeli' (datalist + Yalniz ucretsiz + Yenile). tests/test_gorsel_uret.py. GERCEK OpenRouter ile DENENMEDI
  - [x] gorsel_uret CODEX SAGLAYICISI (kullanici istegi: ChatGPT Plus): cli_ajan.codex_gorsel_uret (bos gecici klasorde codex exec, image_generation ozelligi; gorsel.png yoksa ~/.codex/generated_images/<thread>/ en yeni dosya). Ayar gorsel_saglayici otomatik|codex|openrouter (otomatik: Codex kuruluysa Codex). SohbetServisi._gorsel_saglayici. AI Ayarlari > 'Gorsel uretim' secimi + 'Codex kurulu' durumu. GERCEK Codex ile DENENDI: 88 sn, 1 MB PNG (codex-cli 0.169, ~135K girdi tokeni cogu onbellek). tests/test_gorsel_uret.py 7, ilgili 68 test gecti; bu ekten sonra tam paket KOSULMADI.
  - [x] SKILL codex-gorsel (kullanici istegi: sohbet OpenRouter olsa da gorsel Codex'le): ~/Documents/brain/skills/codex-gorsel (SKILL.md + scripts/codex_gorsel.py stdlib + tests 6, %85), ~/.claude/skills junction; Kairo kesfediyor (kaynak claude, scripts manifestte). Gercek Codex: 94 sn PNG. BULGU: sandbox'in gecici klasore yazdigi dosya PermissionError -> once ~/.codex/generated_images/<thread>/, okuma 5 deneme (cli_ajan.codex_gorsel_uret de ayni sira).
  - [x] TITREME (kullanici ekran goruntusu): bos ekran karti birkac sn'de bir titriyordu. Kok neden: durum yoklamasi her turda bosDurumKartlari() cagiriyor, o da karti bosaltip /api/oneriler'i yeniden istiyordu (oneriler kaybolup geliyordu). Duzeltme app.js: imza (etkin proje + projeler + oneriler) ayniysa DOM'a dokunulmaz; oneriler onbellekten senkron, en fazla 60 sn'de bir yenilenir. Onizlemede 10 sn'de 0 DOM degisimi.
  - [x] VIDEO (eski not 'OpenRouter'da video yok' ESKIMIS: 2026-11-14'te 32 video modeli, Grok Imagine Video/Veo 3.1/Kling/Seedance). OpenRouterDeposu.video_uret (POST /videos -> polling_url yokla 10 sn x90 -> GET /videos/{id}/content), modeller(cikti='image'|'video') ayri onbellek (eski gorsel=True parametresi kaldirildi), ayar video_model (bos = kapali), VIDEO_URET_ARACI yalniz video/klip/animasyon isteginde; tek onay: YanEtki.dis + 'Ucretli odeme' ozeti -> tam yetkide de sorulur, yol kapsam denetimli. AI Ayarlari > 'Video uretim modeli (ucretli)'. GUVENLIK: policy EYLEM_TURLERI odeme listesine ASCII 'odeme' eklendi (yoktu; 'odeme_yap' gibi arac tam yetkide sorulmadan gecerdi). tests/test_video_uret.py 5. Tam paket 789 gecti 3 atladi, derlendi 16:44, commit 9a3bb99, teslim 16:48 (kullanici onayiyla kapatildi, data korundu + %TEMP%/kairo-data-yedek-164506), acildi. GERCEK VIDEO DENENMEDI (ucretli, kullanici onayi gerekir).
  - 2026-11-14 SONUC: 3/3 tamam. Tam paket 782 gecti 3 atladi (test_a9_masaustu haric, 12.5 dk), ruff temiz. Onizlemede (8801) goruldu: Oneriler, Ice aktar modali (token satiri atlandi), Gorsel uretim modeli (72 model, ucretsiz 1). Sonra tam paket 784 gecti 3 atladi, derlendi (dist 16:03), commit+push (feature/ajan-katmani). Teslim 16:18 (eski Kairo kullanici onayiyla kapatildi, data korundu + %TEMP%\kairo-data-yedek-*), Baslat.bat ile acildi. KALAN: gercek OpenRouter ile gorsel_uret (anahtar gerekir); sohbetten gercek modelle gorsel_uret/skill denemesi.
- BOS EKRAN + ALT CUBUK (2026-11-14): ortada model/effort yerine proje secici (son 4 + Daha fazla + Proje olmadan + Klasor sec);
  mod menusu simge + ad + aciklama (menuAc 'aciklama'), cubukta kisa ad; model hapinda kisa ad.
- AI AYARLARI YENIDEN TASARIM (2026-11-14, Cursor/Open WebUI/Jan ornekleri): ustte 'Kullanilan model' ozet karti (baglam,
  fiyat, yetenekler, uyari; Degistir + Dene, test sonucu kartta), saglayici iki hap, API anahtari tek satir (Degistir/Sil,
  anahtar yoksa giris acik), 'Model sec' katlanir secici: arama + cipler (Ucretsiz, Arac, Gorsel, Dusunur), tek satirlik
  liste, secili model hep en ustte. Element id'leri korundu. Onizlemede gercek test: basarili 0.9 sn.
- AJANLAR ARASI MESAJ (Claude ekipleri gibi): alt_ajan 'ad' parametresi (Run.ad); takim_mesaj_gonder alici = uye adi /
  'lider' / 'hepsi'; TakimPanosu.teslim_al ile mesajlar her model cagrisindan once aliciya ITMELI eklenir
  ('[Takim mesaji - Yazar] ...'), okuma araci gerekmez. tests/test_a8_takim.py +2.
- ZOR KARSILASTIRMA (2026-11-14, ../karsilastirma-zor: hazirla.py girdiler+gizli beklenen, kos.py, degerlendir.py, sonuc.json):
  7 gorev (OCR fatura, kirli CSV, hata ayiklama + gizli test, kaynakli arastirma, CLI uygulama, alt ajan takimi, 3 kisilik ekip).
  IKISI DE tum olculen kontrolleri gecti. Claude Code: 45m46s, ~$15 (ekip tek basina $8.4, SendMessage 7 + Agent 3).
  Kairo (deepseek-v4.1-flash): 17m54s; alt_ajan 3 (takim), ekipte alt_ajan + takim panosu, 2/4 alt ajan adim butcesinde durdu.
  Bulunan Kairo eksikleri -> DUZELTILDI: (1) gorsel dosyayi modele verecek arac yoktu (OCR icin Tesseract'i winget ile kurdu,
  29 adim) -> sohbet.gorsel_oku + GORSEL_ARACI (yalniz model goruntu destekliyorsa VE istek gorselle ilgiliyse; tur sonunda
  ayri user mesaji, runner._gorseller), tests/test_gorsel_oku.py (2) alt ajan varsayilan butcesi 25 -> 50.
- ARAYUZ (kullanici istegi, Claude benzeri): mesajda 'Duzenliyor >' etkinlik basligi (tikla: adimlari katla), cerceveli plan karti
  (tik / donen / kesik daire), canli alt satir '••• 1m 54s · N tokens'; sag panel Arka plan isleri: calisan + sure + durdur,
  'N bitti', tiklayinca ust katman: kartlar (komut: $ komut + cikti + [exited with code N]; gorev: adim adim akis).
  Onizlemede gercek OpenRouter istegiyle goruldu (.claude/launch.json 'kairo-openrouter' 8802).
- 2026-11-14 HATA DUZELTME: Kairo sohbetinde 'Gecersiz arguman JSON'u' (GitHub raporu yazarken). Kok neden: sohbet cevap siniri ayardaki max_tokens (1024) idi; uzun rapor tek proje_dosya_yaz argumaninda kesiliyordu (ajan gorevleri cevap_tokeni ile cozulmustu, sohbet degil). Duzeltme sohbet.py: araclar varken max(max_tokens, cevap_tokeni(baglam)) (32K -> 8192) + kesik argumanda 'parcala' yonlendirmesi. Probe: DeepSeek akissiz cagrida tek tirnakli JSON gecerli (tirnak neden degil). test_api +2.
- EKSIKLERI TAMAMLA (2026-11-14) BITTI: tam paket 764 gecti + CLI regresyonu (uzanti_yaz semasi 16K baglami tasiriyordu -> yalniz uzanti/mod isteginde) giderildi, teslim 13:03, commit+push. Kararlar: GitHub hitabi /kairo; thread onayi tercih yok -> otomatik kalir;
  agent-desktop EKLE (sabit surum + SHA256); sosyal medya ajani ERTELENMIS kalir. RAM 3.4 GB -> model olcumleri yapilamaz.
  - [x] D2 alt oturum kartina "Arka planda yaptir (ayri dal)"
  - [x] D3 GitHub /kairo yoklama (gh api + ETag) -> tetik -> is emri (gozle: panelde Baslat)
  - [x] D4-D5 teslim (commit/push/PR/yorum, yap modu), worktree'de git push/gh komut engeli, takip yorumlari
  - [x] agent-desktop arac paketi (v1.3.1 x86_64 tar.gz, sha256 6ee4b1e0..., guvenli_ac tar.gz destegi; kurulum kullanici tiklamasiyla) (sabit surum + SHA256) + MCP
  - [x] MODS: arac_cagrisi (engelle/arguman/cevap), istem, tur_bitis, ui yetenegi (durum/bildirim/bant), dosya degisince yeniden yukleme, git'ten karantina, uzanti_yaz araci (yalniz karantina). tests/test_mods.py
  - [x] T3 thread sorusu secenekli kart (_is_ozet soru + superajan.js soruCiz)
  - [x] KARSILASTIRMA (2026-11-14, ../karsilastirma-github-rapor): 'github istatistiklerimi rapor yap, pdf+docx ver'.
    Claude Code: 11 tur, 3.5 dk, $1.52, 2 sayfa PDF/DOCX, 3 grafik, rapor.py+test, private repo uyarisi.
    Kairo (OpenRouter deepseek-v4.1-flash, tam yetki): 3. denemede basarili, 19 adim, 2 dk, 6 sayfa, 6 tablo, 4 grafik, kendi dogruladi.
    Kairo'da bulunan ve DUZELTILEN hatalar: (1) model onbellekte yoksa 'arac desteklemiyor' reddi -> openrouter.eksik_modeli_getir
    (2) model arguman adini Turkcelestiriyor ('açıklama') -> runner.arguman_adlari (ajan+sohbet) (3) CLI --json cp1254'te cokuyordu -> utf-8
    (4) private veri uyarisi yok / istenmeden Masaustu'ne kopyaladi -> AJAN_NOTU kisa kurali (SISTEM'e eklenince 16K CLI testi tasiyordu).
    Bulgu: 16K baglamda talimat+arac payi cok dar; her ek satir onay sonrasi arac sonucunu kirptiriyor.
- WRONGSTACK KALAN 4/6/7 TAMAM (2026-11-14): tam paket 747 gecti 3 atladi (test_a9_masaustu haric), derlendi + teslim 10:57 (data korundu), acildi, commit+push:
  - [x] 7 arastirma ozeti: runner SISTEM + sohbet AJAN_NOTU'na kural (kaynak URL, API adi, surum, belirsizlik, uydurma). tests/test_ogrenen_7.py
  - [x] 6 lsp.py LspIstemci.yenile (didClose + eski tani silinir; once didOpen tek seferdi, tanilar bayat kaliyordu) + KodZekasi.yazma_sonrasi_tani/tani_ekle; sohbet.py proje_dosya_yaz/yama sarilir -> 'lsp_tanilari' (yalniz severity 1, en fazla 10). Dil sunucusu tanimli degilse etkisiz. tests/test_a10_lsp.py (+2)
  - [x] 4 runner._izleyici: son 8 adimin >=5'i basarisiz ya da son 12 adimda farkli cagri <%50 -> modele '[Izleyici]' yon notu (en az 6 adim arayla; Run.izleyici_son). tests/test_ogrenen_4.py
- 2026-11-14: Baglayici arac listesine "Tumunu sec" (ara durum, tek PUT) eklendi (ayarlar.js); onizlemede denendi, derlendi + teslim, commit edildi.
- WRONGSTACK B-E (kullanici istegi 2026-11-14, OGRENEN-SISTEM-PLANI.md). Onceki tur (GitHub + thread'ler) derlendi + teslim 09:40, acildi. B-E sonrasi tam paket gecti (test_a9_masaustu haric), derlendi + teslim 09:59 (data korundu), acildi. Commit 3691830 pushlandi (46ea14f dahil):
  - [x] B dongu tespiti: runner.py _periyot_tekrari (2-3'luk desen >=3 tur -> DONGU_UYAR gibi atlanir) + _koc (ayni hata imzasi farkli argumanla 3 kez -> 'koc' notu; yazma sonrasi 'dogrula' notu). tests/test_ogrenen_b.py
  - [x] C kanitli hafiza: Hafiza.dayanak ('yol::metin', dosya metni kaybedince not sisteme girmez), yararli/eski/yanlis + revizyon, ilgili() sorgu kelimesine gore en iyi 6 / 800 krk, yanlis>=2 dusurur; hafiza_yargila araci (hafiza_acik), hafizaya_ekle dayanak alir. tests/test_ogrenen_c.py
  - [x] D runner._incelenmeli/_incele + api _gorev_incele: dosya yazan basarili/dogrulanmadi gorev bitince git diff HEAD -- yazilan dosyalar -> rv.istem/sonuclandir; Run.inceleme; kritik/yuksek bulgu dersler'e ('inceleme'). Ayar otomatik_inceleme (varsayilan acik, Ayarlar>Hafiza). gorevler.js incelemeHtml. tests/test_ogrenen_d.py. Gercek modelle DENENMEDI
  - [x] E cli_ajan antigravity (agy -p --output-format stream-json, --conversation, accept-edits / --dangerously-skip-permissions; agy --help + canli cikti ile dogrulandi; denied_actions ozete yazilir). Ajan formunda secenek. Sohbet araci cli_ye_yaptir (YanEtki.komut, proje disi klasor reddi, saglayici|klasor basina konusma surer). tests/test_ogrenen_e.py. cli_ye_yaptir gercek CLI ile DENENMEDI
- 2026-11-14 (llm oturumundan): GitHub 'Baglan' kapali (aktif:false) kaydi acmiyordu -> api.py github_baglan aktif:True (gh zaten girisli oldugu icin giris penceresi cikmaz, mevcut token kullanilir). test_api github testi. Video T1-T4 asagida [x]. Testler: superajan+api+alt_oturum+sohbet_araclari+baglam 65 gecti. KALAN: gercek modelle sohbetten thread acma denemesi, derle + teslim, commit/push onayi.
- DEVAM EDEN PLAN (2026-11-13, Claude Code oturumu, commit YOK):
  - [x] Proje formu Klasor sec (main.py PencereApi.klasor_sec, proje.js data-klasor-sec)
  - [x] MCP stdio tools/call suresi timeout argumanina uyar (mcp.py arac_suresi, taskkill /T); test_mcp_sure
  - [x] 'dogrulanmadi' yanlis alarmi: gorevin yazip sildigi gecici dosya degisiklik sayilmaz (runner.py net_degisiklikler)
  - [x] Ajan sonucunda Kopyala; basliktaki Paylas: tum sohbet (ajan turlari dahil) kopyala / .md kaydet (app.js sohbetMarkdown, main.py dosya_kaydet)
  - [x] Ajan kayitlari sunucuda kalici (Oturum.ajan_runlari, POST /api/oturumlar/{id}/ajan-run); eskiden port degisince kayboluyordu
  - [x] KAIRO.md: <veri>/KAIRO.md (eski AGENTS.md tasinir), @import, varsayilan BRAIN-POLICY importu, cift import tekillesir; projede KAIRO.md okunur
  - [x] Sag panel Claude Code gibi (Ortam/Baglam/Baglayicilar/Arka plan isleri), gizle-goster, Dosyalar ayri yan panel
  - [x] Derlendi + teslim (data korundu, KAIRO.md olustu) + commit ffc1187 pushlandi. Tam paket 686 gecti; 2 ilgisiz: pano testi (gercek pano mesgul), paralel alt ajan (zamanlama, tek basina gecer)
  - [x] WrongStack incelendi -> OGRENEN-SISTEM-PLANI.md (A ders defteri, B dongu, C kanitli hafiza, D chimera, E CLI)
  - [x] UI cilasi (commit YOK): baslik cubugu alt cizgisi; ayni ikonun farkli islerde kullanimi kaldirildi
    (ikonlar.js: panelSag, yanSohbet, plan, gorevler, arkaPlan, kahve, eklenti, uzak); sag panel ayraclari kenardan kenara;
    durum cubugu duz ogeler + ince ayraclar (app.css sonu)
  - [x] OpenRouter kalan limit durum cubugunda (openrouter.py OpenRouterDeposu.limit: /key + /credits, 60 sn onbellek;
    GET /api/openrouter/limit; sagpanel.js orLimitYenile). Canli anahtarla DENENMEDI.
  - [x] KAIRO.md ana talimat: kaynak sirasi once KAIRO.md + importlari, sonra CLAUDE.md (istege bagli); Ayarlar ekrani buna gore
    (index.html t-kairo-liste, skiller.js kaynaklariCiz). test_skiller sirasi guncellendi.
  - [x] Uzak erisim CALISMIYORDU: varsayilan port 8443 tailscaled ile cakisiyordu, uvicorn sys.exit(1) TUM uygulamayi kapatiyordu. Duzeltme: SystemExit yutulur (uzak.py UzakSunucu.ac), varsayilan 8765 + kayitli 8443 tasinir (ayarlar.py UZAK_PORT). Canli: ac -> https://100.89.62.116:8765 302, kod uretildi, kapandi. test_uzak_port
  - [x] Sag panel Baglam dokumu (Claude Code Context gibi): GET /api/oturumlar/{id}/baglam artik kalemler
    (mesaj/sistem/talimat/proje/hafiza/skill/arac/mcp) + bos; sohbet.py baglam_hazirla son_parcalar saklar;
    sagpanel.js baglamDetayCiz. Baglayicilar panelde acilir liste + "giris gerekli". test_baglam_dokumu.
    BULGU: bos sohbet 16K'nin %67'si (skill listesi 4.1k, KAIRO.md+BRAIN-POLICY 3.8k, araclar 2.9k) -> kucuk
    modelde ilk is bunu kucultmek (skill listesini 8K gibi uygun olanlarla sinirla?).
  - [x] Bu turun degisiklikleri: test + derle + teslim + commit (diger oturumun hooks/runner/api/test_a6 hunk'larina dikkat)
    2026-11-13 diger hesaptan devralindi: ruff temiz; tam paket (test_a9_masaustu haric) 690 gecti, 1 kaldi:
    test_a8 paralel alt ajan esigi 1.6 sn bu makinede HEAD'de de 1.62-1.66 (sabit ek yuk ~0.45 sn) -> esik 1.8
    (sirali en az 1.8 sn uyku; alti cakisma kaniti). test_servisler kacis uyarilari r"" ile giderildi. test_a9_masaustu 5/5.
    Derlendi + teslim (data korundu, 373 MB), Baslat.bat ile acildi 18:18, ana sayfa 200. Commit bu maddeyle.
  - [x] 2026-11-13 PAKETI (commit + push bu maddeyle). Kullanici istegiyle TAM PAKET KOSULMADI: yalniz degisen alanlarin 15 test dosyasi
    (203 gecti: alt_oturum_ajan, a3, a8, a2, a0, sohbet_plan, sohbet_araclari, a4, baglam_dokumu, api, a7_mcp, mcp_sure,
    mcp_oauth, arac_paketleri, masaustu_ayarlari); ruff temiz, JS --check. Derlendi + teslim (data korundu) 18:59,
    Baslat ile acildi, ana sayfa 200, yeni JS pakette.
    - [x] SOHBET TUR SINIRI KALDIRILDI: cevap_akit max_tur=0 sinirsiz (sohbet 20 ve 6 tur yok); ayni arac cagrisi ust uste
      3 kez -> durum "dongu", son cagri calistirilmaz, uyari kod "dongu". test_alt_oturum_ajan.
    - [x] read_media_file KOK COZUM: MCP roots. mcp._Baglanti initialize'da roots ilan eder, roots/list ve ping'e cevap verir;
      roots = aktif projenin izinli_kokler'i + sunucunun kendi arguman klasorleri (api.py mcp.kokler). Proje degisince
      stdio baglanti yeniden baslar (list_changed sonrasi sunucu eszamansiz uyguluyordu). Gercek filesystem uzantisi
      (2026.7.10) ile 3/3 ilk cagrida PNG okundu, proje disi yol reddedildi. Mevcut klasorsuz 'filesystem' kaydi artik calisir.
    - [x] SOHBET ADIM GORUNUMU Claude Code gibi: gorevler.js ccAkis/ccGrup/ccAdim (ardisik adimlar "2 komut çalıştırıldı ›",
      adim basligi, acilinca kutuda "$ komut" + cikti; MCP PowerShell/bash da komut sayilir); app.css .cc-*;
      araclar.py komut_calistir'a istege bagli `aciklama` basligi. Onizlemede goruldu.
    - [x] ALT OTURUMLAR: Oturum.ust + oneri_kararlari; POST /api/oturumlar/{id}/alt ve /oneri-reddet; sohbet araci
      alt_oturum_oner (yalniz oneri, sohbet.js altOturumKarti: "Alt oturumda başlat" -> alt oturum + gorev ilk mesaj /
      "Gerek yok"); app.js listede alt oturumlar ana oturumun altinda, ok ile katlanir (localStorage kapaliAltlar).
      Onizlemede liste, katlama, kart ve ret goruldu; "Başlat" onizlemede basilmadi (gercek modeli acar), API testle dogrulandi.
    - [x] SOHBETTEN AJAN OLUSTURMA: ajan_olustur araci (ad, avatar enum 12, aciklama, talimat, klasor, saglayici, model);
      politika YanEtki.yaz (onayli modda sorar); api.py sohbet.ajan_olusturucu = ajan_deposu.olustur. Gercek modelle DENENMEDI.
    - [x] ADIM BUTCESI KALDIRILDI (kullanici istegi): Butce.max_adim varsayilan 0 = sinirsiz; donguyu ayni hata/ilerlemesiz/
      ardisik ret korumalari durdurur; sure butcesi (1800 sn) ve alt ajan butcesi (25) duruyor; rutin/webhook kendi max_adim'i.
      Arayuz "sınırsız" gosterir. (Purge gorevi 8d847b67c836 41. adimda bu sinira takilmisti.)
    - [x] HATA DUZELTMELERI (Purge testindeki hatalar): MCP Wait(duration=45) 30 sn'de kesiliyordu -> mcp.arac_suresi
      duration'a da uyar. Claude Desktop filesystem uzantisi izinli klasorsuz aktariliyordu ("path outside allowed
      directories") -> mcp_ice._uzanti zorunlu ayari bos uzantiyi onermez + MCP roots (yukarida). klasor_listele reddi
      tasarim geregi (proje disi yol).
  - [x] PROJEYE OZGU SOHBET (2026-11-13, commit + push bu maddeyle): Oturum.alan (olusturuldugu proje; alt oturum ana oturumdan alir;
    /api/oturumlar listesi alan dondurur). Sohbet acilinca projesi etkin olur (POST /api/projeler/{id}/etkin,
    workspaces.etkinlestir: guven/mod SIFIRLANMAZ; kisisel alan id'si = proje kapat). Kenar listesi ustunde Tarih|Proje
    secici (localStorage listeDuzeni); Proje'de her grup basliginda "+" = o projede yeni sohbet, sohbeti olmayan
    projeler de listelenir, eski kayitlar "Proje yok". Test: test_alt_oturum_ajan (+ api, a1_izinler 92 gecti).
    Onizlemede: gruplar, sohbete tiklayinca proje gecisi, "+" ile termflow-lite'ta yeni sohbet, Tarih'e donus goruldu.
    Derlendi + kuruldu (data korundu) 19:12, ana sayfa 200.
  - [x] MODEL BILGISI TEK YERDE (2026-11-13, commit + push bu maddeyle): model adi yalniz mesaj kutusu seciciside (#hap-model-metni);
    durum cubugu "OpenRouter" / "Yerel model · Hazir" (yerel model adi ipucunda), sag paneldeki #sp-model satiri kaldirildi.
    Mesaj altindaki istatistik cipindeki model (hangi model cevapladi) duruyor. Onizlemede goruldu, derlendi + kuruldu 22:38.
  - [x] OGRENEN SISTEM A: DERS DEFTERI (2026-11-14, COMMIT YOK): app/agent/dersler.py (<veri>/dersler.json, en fazla 300;
    imza = arac + hatanin yol/sayi/tirnak atilmis hali, Windows yolunda bosluk dahil; sirlar maskeli). runner.py:
    _ders_isle hata/ret yazar, ayni aracin sonraki basarisi "ise yarayan" cozum olur (Run.bekleyen_dersler); tekrar eden
    hatada arac sonucuna "onceki_ders"; baslat'ta hedefe ilgili <=5 ders (<=600 karakter) ek_sistem'e; basarisiz gorev
    bitisi "gorev" dersi. api.py ajan.dersler. Yalniz AJAN GOREVLERI (sohbet modu cevap_akit bagli DEGIL). Arayuzde
    ders listesi YOK. Test: tests/test_dersler.py (4) + a3/a8/a6/alt_oturum 48 gecti. Derlendi + kuruldu 08:10.
  - [x] COMPOSIO CONNECT ANAHTARI (2026-11-14, COMMIT YOK): ck_ (For You) anahtari REST'e (x-api-key) gidip "gecersiz"
    sayiliyordu. composio.py: connect_mi -> https://connect.composio.dev/mcp + x-consumer-api-key (dogrulama MCP
    initialize; mcp_tanimi bu adres; Baglan = COMPOSIO_MANAGE_CONNECTIONS add, adres metinden; baglanti kesme
    dashboard'dan). Proje anahtari (ak_) eski yol. eklentiler.js: iki tur aciklamasi, connect'te populer kartlar Baglan.
    Test: test_composio (3). Canli: kullanicinin anahtariyla gecici klasorde kaydet + 12 arac. Kullanicinin
    Kairo'suna anahtar EKLENMEDI (kullanici yapistirir). Not: tarama sirasinda COMPOSIO_MANAGE_CONNECTIONS
    action=list Gmail icin bekleyen (onaysiz) bir baglanti baslatti. Derlendi + kuruldu.
  - [x] EKLENTI DURUM ROZETLERI (2026-11-14, COMMIT YOK, derlendi KURULMADI): mcp.durumlar() + /api/mcp her sunucuya
    baglanti {durum: bagli|baglaniyor|hata|kapali, arac, hata} ve ek (plugin/Composio) isareti; ortak.js baglayiciDurumu
    (Bagli · N arac yesil / Giris gerekli sari / Baglanamadi kirmizi / Baglaniyor mavi / Kapali); eklentiler.js ust ozet,
    sorunlular once, baglanirken 3 sn yenileme; sagpanel + Ayarlar MCP ayni etiket. test_a7_mcp rozet testi. Onizlemede goruldu.
  - [x] GITHUB'DAN SKILL ICE AKTARMA (2026-11-14): indir (git --depth 1, hook kapali) -> karantina -> kural taramasi
    (pluginler.inceleme_raporu + skill ekleri) -> Claude Code CLI denetimi (canli denendi: -p --restricted
    --strict-mcp-config --tools Read Grep Glob --disable-slash-commands --no-session-persistence --output-format json
    --json-schema; cwd=skill klasoru; ~19 sn, ~0.08$; kotu ornegi "reddet") -> reddet kurulmaz, sartli kullanici onayi,
    temiz kurulur -> <veri>/skills/<ad> + .kaynak.json. YAPILDI (COMMIT YOK): app/services/skill_ice.py, api /api/skill-ice
    (POST indir, /{id}/denetle, /{id}/kur, DELETE), skiller.js "GitHub'dan ekle" modali (kapaninca karantina silinir),
    Turkce prompt injection deseni ve ciddi sayilir; kurulumdan once klasor_hashi tekrar kontrol. tests/test_skill_ice.py (5).
    Onizlemede canli: anthropics/skills brand-guidelines indirildi, Claude Code 19 sn "Guvenli". Derlenmedi/kurulmadi.
  - [x] AYARLAR YENIDEN TASARIM (2026-11-14, COMMIT YOK): Baglayicilar/Plugin'ler/Uzantilar Eklentiler diliyle
    (ek-panel, ek-satir + ekAvatar + durum rozeti + tek ana dugme + menu, ek-izgara kartlar, ekleme formlari katlanir
    <details class="ek-ekle">). Baglayici sirasi: kendi listen, elle ekle, Claude'dan ice aktar, arac paketleri, dizin.
    aracPaketleriCiz/baglayiciIceAktarCiz artik #mc-paket/#mc-ice'e cizer. Onizlemede uc sekme goruldu, konsol temiz.
  - [x] klasor_sil (depo.py): Windows'ta salt okunur git paket dosyalari rmtree(ignore_errors) ile kaliyordu;
    skill_ice ve pluginler.git_karantina bunu kullanir.
  - [x] (2026-11-14, COMMIT YOK, kuruldu 09:02) Skill ice aktarma: ayni adli skill varsa kutu kapali kaliyordu ->
    farkli adla kur (yeni_adlar; kopyadaki SKILL.md name yeniden yazilir), kartta neden yazili, riskli onay kart icinde.
    Onizlemede obra/superpowers brainstorming -> brainstorming-github kuruldu. test_skill_ice 6.
  - [x] "Dogrulanmadi" yanlis alarmi: arastirma sonunda DURUM.md notu (BRAIN-POLICY) web kanitini gecersiz kiliyordu.
    runner.kayit_dosyasi_mi: DURUM.md/PROJE-REHBER.md/LESSONS.md/CHANGELOG.md, /journal/, /kayit/ yazimlari kanit
    kuralinda "son degisiklik" sayilmaz. Canli ornek run e4bdfd142a6a. test_dersler'e test.
  - [x] SUPERAJAN D1 (2026-11-14, COMMIT YOK, kuruldu 09:19): app/agent/superajan.py (IsEmri, asama tablosu, gorev_metni,
    SuperajanDeposu <veri>/superajan.json), worktree.git_mi/git_baslat (onayli git init + ilk commit), api.py
    _superajan_tick (_ajan_dongusu icinde, ESZAMANLI=2, yalniz projesi acikken) + /api/superajan rotalari (isler,
    git-baslat, mesaj, tekrar, durdur, birlestir, at, sil), app/web/superajan.js Ajanlar sayfasinda "Is emirleri"
    paneli (insan bekleyenler once + tek eylem, bitenler katli). NOTICE-dsh-superagent.md. tests/test_superajan.py (15).
    Onizlemede: GIT_YOK onayi -> git olustu -> is/<id> dalinda basladi; yerel 16K modelde baglam yetmedi -> Basarisiz +
    Tekrar dene goruldu. Kullanici kararlari (onerilenler): bos klasorde onayli git init; sohbette her zaman kart;
    GitHub hitabi /kairo. SIRADAKI: D2 sohbet karti dugmesi, D3 GitHub salt okunur, D4 teslim (PR), D5 takip.
  - [x] Plugin MCP eksik degisken (2026-11-14): github plugin "Bearer ${GITHUB_PERSONAL_ACCESS_TOKEN}" degisken yokken
    "Bearer " -> LocalProtocolError. cc_plugin.eksik_degiskenler + McpSunucu.eksik_degiskenler: baslik gonderilmez,
    durum "Kimlik bilgisi eksik: X ortam degiskeni tanimli degil", baglanmaya calisilmaz. context7 plugin'i
    ?client=claude-code-plugin adresi OAuth ister (401); duz adres anahtarsiz calisir, Claude Desktop'tan gelen
    Context7 zaten bagli -> plugin MCP'si yinelenen, kapatilabilir.
  - [x] VIDEO OZELLIKLERI (2026-11-14, COMMIT YOK, derlenmedi): Claude "proje sohbeti + thread'ler" (kullanici istegi 2026-11-14; videolar Desktop
Ukftd_yGittV8xV.mp4,
    ywaDohNHWf6fotse.mp4). Thread = superajan is emri. Maddeler:
    - [x] T1 sohbet araci is_emri_baslat (birden cok is -> her biri thread) + cevabin altinda canli thread listesi (durum noktasi, tikla ac)
      -> sohbet_araclari IS_EMRI_ARACI + is_emri_isleyicileri, api _sohbet_is_ac (aktif proje + git sart); superajan.js threadKarti (4 sn canli, nokta+rozet)
    - [x] T2 sohbet araci is_emirleri_durum ("her sey ne durumda?") + sag panelde Threads grubu: Incelemeye hazir / Seni bekliyor / Calisiyor + gecen sure
      -> IS_DURUM_ARACI (once insan bekleyen sirali); sagpanel.js threadlerYenile: Seni bekliyor / Incelemeye hazir / Sorun var / Calisiyor + gecen sure, tikla -> Ajanlar
    - [x] T3 thread'in soru_sor sorusu proje sohbetinde secenekli kart (A onerilen / B, "Thread'i ac"); cevap thread'e gider
      -> insan_bekliyor olunca kart satiri kendiliginden acilir, canli gorunumden (sohbetteGorevGoster) cevaplanir; ayri A/B karti YAPILMADI
    - [x] T4 thread gorunumu: "Bu thread'i yonlendir" girdisi, /btw (ana sohbete gider, yeni thread), /fork <talimat> (yeni thread)
      -> satir detayinda 'Bu thread'i yonlendir' (/mesaj), /btw -> ana sohbete gonderir, /fork <talimat> -> yeni thread (gorev 400 krk kesik ozetten)
  - [x] MODS (yapildi: commit fb16470, tests/test_mods.py; ayrinti yukarida "MODS:" maddesi) (kullanici istegi 2026-11-14; code.claude.com/docs/en/plugins/mods/*): Kairo uzantilari (app/services/uzantilar.py,
    ayri surec + JSON) Mods'a yaklastirilacak: olaylar arac_cagrisi (izle/engelle/arguman degistir/cevapla), istem
    (prompt rewrite), tur_bitis; UI yuzeyleri durum cubugu metni, bildirim (toast), istem ustu bant (md + dugme),
    baykus etiketi eki; dosya degisince yeniden yukleme; "Kairo mod yazsin" araci (+ karantina incelemesi);
    GitHub'dan kurulum skill_ice gibi Claude Code denetimli. Guvenlik: ayri surec kalir (Mods sandbox'siz; Kairo daha sikidir).
  - [x] (eskidi) SIRADA: dsh-superagent D2-D5 ve agent-desktop -> ikisi de yapildi (yukarida D2-D5 ve agent-desktop maddeleri, commit fb16470).
  - [x] DSH-SUPERAGENT WINDOWS PORTU (yapildi: D1-D5, commit 3691830/fb16470; bu not ilk gunden kalma): belgeler okundu (000, 001).
    Kavramlar: Source->Trigger->Thread->Eval(gate+assessment)->Ticket(Mandate)->Assignment(Executor)->Channel.
    Kairo karsiligi: kaynak=GitHub (gh api, ETag), politika=izinli loginler, yurutucu=AgentRunner + worktree,
    kanal=gh yorum/PR, panel. KALAN: 002-007 belgeleri, plan, uygulama. Repo: %TEMP%/tarama-dsh-superagent/repo.
  - [x] (2026-11-14 bitti, 3691830) Ogrenen sistem B-D (OGRENEN-SISTEM-PLANI.md): akilli dongu tespiti, kanitli hafiza, gorev sonu otomatik inceleme.
  - [x] dsh-superagent (deepseek-ai, MIT, 2026-11-14 tarandi, temiz; Kairo'ya port edildi): DeepSeek Harness (dsh) bundle'i; tmux + fcntl
    (Linux/macOS), GitHub ajan hesabi + issue dinleyicisi gerektirir, Windows'ta calismaz, Kairo'ya gomulemez. Kullanici
    karari bekliyor: tasarimindan (orchestrator/worker, kabul politikasi) Kairo'da "Uygulama Yapici" varsayilan ajan.
  - [x] agent-desktop (vercel-labs, Apache-2.0, Rust, 2026-11-14 tarandi; arac paketi olarak eklendi): erisilebilirlik agaciyla masaustu kontrolu,
    `agent-desktop mcp` stdio MCP. npm postinstall GitHub release'ten ikili indirir (ayni release'teki SHA256 ile).
    Telemetri/disari veri yok. Kullanici karari bekliyor: arac_paketleri ile sabit surum + sabit SHA256 kurulum + MCP.
  - [ ] ERTELENDI (kullanici 2026-11-13): langchain-ai/social-media-agent varsayilan ajan olarak eklenmedi; istenirse once guvenlik taramasi, sonra kod kopyalamadan talimatli 'Sosyal Medya' ajani (paylasim onayli)
  - [x] (2026-11-14 bitti: cli_ye_yaptir + antigravity) Claude Code / Codex / Antigravity CLI'larini sohbetten kullanma (cli_ajan.py'de claude+codex var, antigravity yok)
- [x] BRAIN BAGLANTISI (2026-11-13, Claude Code, COMMIT YOK): Kairo ajan gorevleri brain kayit sistemine bagli.
  - runner.py `_hook_kok`/`kok`: run_baslangic/run_bitis hook'larina cwd + hedef/ozet/model gider; SessionStart additionalContext run.ek_sistem'e eklenir (api.py `ajan.kok` = aktif proje koku).
  - hooks.py: HookSonucu.baglam, `_ek_baglam`; `_async_mi` ilk stdout satirini artik geri veriyor (tek satirlik JSON kayboluyordu).
  - data/hooks.json + portable data/hooks.json: "brain: DURUM + son kayitlar" (durum-context.py), "brain: ajan kaydi" (son-kayit.py kairo).
  - Test: test_a6_hooks + test_a3_ajan 32 gecti; gercek script'lerle e2e dogrulandi. Portable exe YENIDEN DERLENMEDI (eski exe cwd gondermez -> kayit dusmez).
- Commit + push (feature/ajan-katmani, ~42 dosya; kullanici onayi gerekli).
- Gercek pencerede: onay kapsam dugmeleri, Etkinlik penceresi. Gercek Vercel girisi (kullanici). Telegram gercek botla.
- Asagidaki eski maddeler (2026-11-09/10) hala gecerli ama oncelik dusuk:
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
