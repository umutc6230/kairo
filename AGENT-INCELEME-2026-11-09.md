# YerelAIStudio: tam kapsamli ajan incelemesi

Tarih: 2026-11-09. Kaynak: main / 3ed71de. Baslangicta calisma agaci temizdi.
Kapsam: kaynak kod, testler, paketleme ve resmi Claude Code belgeleri. Uygulama kodu degistirilmedi.
Canli GUI, gercek model kalitesi ve portable paket bu oturumda yeniden denenmedi.

## Karar

Mevcut urun, yerel model yoneticisi ve arac kullanabilen sohbet uygulamasi olarak anlamli bir temel.
Bagimsiz kodlama ajani olarak henuz hazir degil. En buyuk bosluk, guvenli degisiklik yapma ve
sonucu test ederek gorevi tamamlama zinciri. Daha fazla skill eklemek bu boslugu kapatmaz.
Mevcut pywebview + FastAPI ve tek model kararlarini koruyarak gelistirmek mumkun.

## Mimari ve mevcut yetenekler

`pywebview / vanilla JS -> FastAPI / SSE -> SohbetServisi -> ModelYonetici -> llama-server`

- Sohbet, dusunce/cevap akisi, iptal, sohbet arama ve JSON ile kalici kayit.
- Resim, PDF/OCR, ses ve metin ekleri; gecmis ekler icin baglam butcesi.
- Dosya/klasor okuma, dosya ADINDA arama; hesap, saat, birim cevirme.
- Skill kesfi, kelime eslesmesiyle secim, talimat importlari, aracla skill okuma.
- Model magazasi, indirme/devam/SHA256 kontrolu; model test ve karsilastirma ekranlari.
- Ollama/OpenAI/Anthropic uyumlu yerel gecit; ayri Claude Code baslaticisi.
- Tek model kilidi, atomik JSON yazimi, HTML kacirma, portable veri dizini.
- Urun sahibi sabitleri ve Hakkinda icin API alanlari mevcut.

## Dogrulanmis bulgular

### P1: yerel adres kontrolu asilabiliyor

`app/services/ayarlar.py`, KullaniciAyarlari._adres: URL startswith ile kontrol ediliyor.
Ag istegi gondermeden iki sentetik adres dogrulandi:
`http://localhost.example.invalid` ve `http://127.0.0.1@example.invalid` kabul ediliyor;
gercek hostname yerel degil. Bu, yerel kalmasi beklenen mesaj/ek/talimatlarin yanlis
yapilandirilmis adrese gonderilebilmesine yol acar; gercek veri sizintisi gozlenmedi.
Oneri: URL parcala; hostname, scheme, port ve userinfo'yu dogrula; yonlendirme politikasini
ayrica belirle. Yetkili uzak saglayici eklenecekse ayri, acikca gorunen bir mod olsun.

### P1: arac sonucu kesilirken protokol ve devam bilgisi kayboluyor

`app/services/sohbet.py:227-237`: sonuc once JSON'a donusuyor, sonra 6000 karakterde kesiliyor.
`app/services/sohbet_araclari.py:147-166`: dosya icerigi zaten 6000 karakter olabiliyor.
7000 karakterlik sentetik dosyada modelin aldigi sonuc gecersiz JSON oldu; `devam` alani yoktu.
Oneri: icerik alanini serilestirmeden once kisalt; gecerli JSON, satir araligi, toplam satir,
`truncated` ve `next_offset` daima kalsin. Buyuk sonuclar diskte artifact olarak tutulsun.

### P1: arac kaniti sonraki mesajin baglamina alinmiyor

`app/services/sohbet.py:131-187`: gecmis uretilirken asistanin yalniz metni kullaniliyor.
`Mesaj.araclar` diskte var, ancak tool-call/result cifti modele yeniden gonderilmiyor.
Sentetik kayittaki benzersiz arac sonucu yeni gecmiste bulunamadi.
Oneri: tam olay kaydi + token butceli kanit ozeti; dosya yolu/satir/hash bilgilerini koru.
Kullanici "az once okudugun dosyada duzelt" dediginde yeni okuma ve surum kontrolu yap.

### P1: uzun gorevlerin yasam dongusu yok

`app/services/sohbet.py:252-299`: dongu varsayilan 6 model turuyla sinirli; son turda da
araclar calisip yalniz uyariyla cikabiliyor. Tamamlandi/engellendi/butce doldu ayrimi yok.
`app/services/sohbet.py:432-456`: yalniz baslangicta bir arac sonucu icin pay ayriliyor;
sonraki turlarda eklenen tum sonuclar icin yeniden butceleme yok.
`app/services/sohbet.py:471-494`: arac kayitlari basarili sonuc geldiginde atanir;
iptal/hata yolunda o ana kadarki arac sonuclari asistan kaydina aktarilmiyor.
Oneri: kalici Run/Step durum makinesi, her arac sonrasi olay kaydi, tur/token/sure butcesi,
tekrar dongusu algilama, kontrollu retry, her model cagrisi oncesi baglam duzenleme.
Yazma araclari gelince yeniden baslatmada tamamlanmis yan etkiler tekrar uygulanmamali.

## Guvenlik ve olasi hatalar

- P1: Dosya araclarinda proje koku/izin listesi yok. `yol_coz` mutlak yollari kabul ediyor;
  `gizli_mi` dosya adina bakiyor, hedefi resolve etmiyor. Link/junction uzerinden gizli hedefe
  erisim riski koddan goruluyor; symlink testi Windows yetkisi olmadigi icin tamamlanamadi.
  Bunu canli istismar dogrulamasi olarak yorumlamamak gerekir.
- P1, yazma oncesi: Backend izin motoru ve OS duzeyinde izolasyon gerekli. Sistem prompt'unda
  "yapma" demek yetkilendirme degildir. Path kontrolu de tek basina shell sandbox'i degildir.
- P2: API/gecit loopback'e bagli, fakat uygulama kimlik token'i ve Host/Origin dogrulamasi yok.
  Yerel surecler erisebilir. Tarayicidan saldiri olasiligi ayrica test edilmeli; CORS tek basina
  tam koruma olarak kabul edilmemeli. Komut/yazma API'si eklenmeden once bu sinir sertlestirilmeli.
- P2: `app/api.py:255-258` upload'un tamamini bellege aldiktan sonra depoya gonderiyor.
  Buyuk dosyada RAM baskisi riski; akista toplam boyut siniri uygulanmali.
- P2: ayni oturuma iki eszamanli mesaj geldiginde kullanici mesajlari model kilidinden once
  kaydediliyor. Oturum siralamasi ve silme/yeniden adlandirma yarislari icin senaryo testi gerekli.
- P2: UI her token'da tum birikmis markdown'i tekrar isliyor (`sohbet.js`, parcaEkle).
  Uzun ciktilarda gruplanmis render ve uzun sohbetlerde sanallastirma degerli.
- Skill icerigi otomatik olarak sistem mesajina ekleniyor. Kaynak guveni, izin bildirimi,
  degisiklik hash'i ve incelenmemis kaynaklarin otomatik calistirilmamasi tasarlanmalı.
- Bagimliliklar pinli; guvenlik acigi taramasi bu incelemede yapilmadi. "Pinli" demek
  "guvenlik acigi yok" demek degil.

## En degerli bes yatirim

| Yatirim | Kullanici kazanci | Oncelik / sinif | Zorluk / etki |
|---|---|---|---|
| Proje/workspace + izin motoru | Yanlis projeye veya yetkisiz dosyaya dokunmaz | P1 / Kritik | Zor / Yuksek |
| Read/Grep/Glob + guvenli Patch/Write + terminal | Istenen isi gercekten yapar, test eder | P1 / Kritik | Zor / Yuksek |
| Kalici ajan dongusu + gorev plani | Uzun gorevi takip eder, kesintiden devam eder | P1 / Kritik | Zor / Yuksek |
| Diff + checkpoint + dogrulama | Degisiklik gorulur, geri alinir, sonuc kanitlanir | P1 / Kritik | Zor / Yuksek |
| Baglam yonetimi + model gorev olcumleri | Kucuk modelin sinirli baglamini verimli kullanir | P1 / Yuksek deger | Orta-Zor / Yuksek |

Arac tasarimi: satir numarali okuma, icerik arama ve gitignore destegi; patch oncesi eski
icerik hash'i; atomik yazma; kullanicinin mevcut degisikliklerini koruma. Terminalde cwd,
stdout/stderr, exit code, timeout, iptal, arka plan is kimligi ve Windows process-tree kontrolu.
Shell'in degistirdigi dosyalar icin de koruma gerekir; yalniz Patch aracini kaydetmek yetmez.
Git varsa izole worktree secenegi; Git olmayan projelerde de yerel snapshot. Otomatik commit,
push veya kullanici degisikliklerini silen genel reset kullanilmasin.

## Hedef mimari

Mevcut servisleri koru; SohbetServisi'ne tum sorumlulugu yigma:

`UI -> Run API -> AgentRunner -> ContextManager -> ModelYonetici`

`AgentRunner -> ToolRegistry -> PolicyEngine -> Workspace/Terminal/Connector`

`RunStore + EventStore + CheckpointStore + ArtifactStore`

Run: hedef, proje, plan, butce, durum. Step: arac, dogrulanmis girdiler, izin sonucu,
baslama/bitis, cikti referansi, yan etki, dogrulama. SSE bu kalici olay akisinin gorunumudur;
UI baglantisi kopunca olay kaydi kaybolmaz. Duraklatma ile iptal farkli davranislardir.
Veri hacmi buyuyunce SQLite dusunulebilir; yalniz teknoloji degistirmek icin gecis yapilmasin.

## Arayuz

- Sohbet / Planla / Uygula modlari ve aktif proje/izin kapsami gorunur olsun.
- Gorev adimlari, calisan komut, degisen dosyalar, diff, test ciktilari tek akista gorunsun.
- Durdur / devam et / geri al; onay penceresinde tam yol, komut ve etki gorunsun.
- Baglam dolulugu, atilan/ozetlenen bilgi, modelin gercek arac yetenekleri gorunsun.
- Klavye gezinme, focus yonetimi, ekran okuyucu etiketleri GUI testinde incelensin.
Bu oturumda gorsel kalite veya erisilebilirlik icin canli onay verilmedi.

## Model ve performans

Repo rehberindeki onceki olcumler: dahili GPU'da prompt isleme 14-26 token/sn;
Claude Code ilk turu 5-12 dakika, sonraki turlar onbellekle yaklasik 10 saniye.
Bunlar bu oturumda yeniden olculmedi; donanim/model secimi icin guncel benchmark gerekir.

Her skill'i ve araci her istege koymak yerine goreve gore kademeli yukle. Sabit onek
onbellegini koru. Buyuk terminal ciktilarini dosyada sakla; yalniz ilgili satirlari modele ver.
Model secimini OCR/JSON/hiz testine ek olarak gercek kod gorevleriyle yap: hatali testi
bulma, cok dosyali duzeltme, izin reddinden sonra devam, eksik baglamda yeniden okuma.
Her senaryoda basari, test sonucu, tekrar sayisi, toplam sure, ilk token ve RAM olculsun.
Mevcut kucuk modelin tek bir tool call yapmasi, uzun kod gorevinde guvenilir oldugunu kanitlamaz.
Yerel calisma varsayilan kalsin; bulut destegi ancak kullanicinin sectigi ayri mod olarak
dusunulsun. Ajan altyapisi eklemek tek basina model muhakemesini Claude seviyesine cikartmaz.

## Sirali yol haritasi ve kabul kriterleri

1. Mevcut P1 hatalari: URL kontrolu, yapisal sonuc kisaltma, arac kaniti ve iptal kaydi.
   Kabul: sentetik regresyonlar gecer, gecersiz URL reddedilir, devam bilgisi kaybolmaz.
2. Workspace/izin + dosya/terminal + snapshot. Kabul: gecici projede dosya duzenlenir,
   test calisir, yetkisiz erisim reddedilir, geri alma kullanici degisikligini korur.
3. Kalici Run/Step + baglam ozetleme + test-duzelt dongusu. Kabul: en az 10 arac adimli
   gorev, uygulama yeniden acildiginda devam, arada baglam daralmasi ve timeout senaryolari.
4. Diff/plan/progress UI + gercek model eval paketi. Kabul: kullanici ne degistigini ve
   hangi testin gectigini gorebilir; hedef benchmark'ta olculmus basari raporu vardir.
5. MCP istemcisi, guvenilir skill scriptleri, web/belge connector'lari ve IDE/LSP destegi.
   P2 / Yuksek deger / Orta-Zor: her arac ayni izin, zaman asimi ve olay kaydindan gecsin.
6. Izole alt ajanlar. P2 / Kosullu deger / Zor: ayri baglam, dar yetki, gorev sahibi,
   sonuc ozeti, ortak butce. Tek yerel modelle once sirali kuyruk; paralel GPU model yukleme yok.

Hemen eklenmemesi gerekenler: onlarca kontrolsuz MCP/skill, sinirsiz terminal, vektor DB'yi
baslangic kosulu yapma, model kapasitesi olculmeden coklu ajan ordusu, arayuzu bastan yazma.

## Claude Code koprusu ile bagimsiz ajan ayrimi

`paketleme/Claude-Yerel.bat` zaten ayri Claude Code surecini yerel gecide bagliyor ve
`Bash,Read,Edit,Write,Glob,Grep` araclarini seciyor. Bu yol mevcut ajan altyapisindan
yararlanmak icin kisa vadeli bir secenek; Studio'nun kendi sohbetine bu yetenekleri eklemez.
Model/surum/protokol uyumlulugu ve uzun gorev kalitesi ayrica dogrulanmali.
Bagimsiz urun hedefinde yukaridaki AgentRunner katmani gerekir.

## Test ve teslim degerlendirmesi

Mevcut testler agirlikla Python birim/API ve sahte model entegrasyonu. Arac okunmasi,
gecit, ekler ve iptal icin yararli temel var. Tarayici E2E, gercek modelle kod gorevi,
izin/sandbox, checkpoint ve crash-resume testleri eksik. `.github` altinda tracked CI yok.
Lint kontrolu temiz. Pytest: 152 gecti, 1 atladi; 65.52 saniye; Python coverage %94.
Yeni kod eklenmedi, paketleme/push/kurulum yapilmadi.

Statik incelemeye dayali muhendislik puanlari (benchmark degil): kod kalitesi 7/10,
mimari 7/10, bakim 7/10, test altyapisi 7/10, guvenlik 4/10, urun degeri 7/10,
Claude Code benzeri ajan kapsamı 3/10, otonom kodlama icin hazirlik 3/10.
Canli GUI/performance puani verilmedi; olcum yapilmadi. Yerel sohbet kullanimi icin
umut verici; guvenilir otonom kod degisikligi icin su an hazir degil.

## Resmi karsilastirma kaynaklari

- https://code.claude.com/docs/en/how-claude-code-works (baglam -> eylem -> dogrulama dongusu)
- https://code.claude.com/docs/en/permissions (arac, proje ve izin sinirlari)
- https://code.claude.com/docs/en/checkpointing (duzenleme takibi ve geri alma)

Claude Code'un checkpoint mekanizmasi da tum harici yan etkileri geri alan genel bir
transaction sistemi olarak dusunulmemeli; terminal/ag yan etkileri ayri ele alinmali.
