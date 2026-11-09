# OZELLIK-MATRISI - YerelAIStudio ajan yetenekleri

Kaynak is tanimi: `AGENT-GELISTIRME-TALIMATI.md`. Inceleme: `AGENT-INCELEME-2026-11-09.md`.
Guncel: 2026-11-09 | referans commit: `3ed71de` + A0 ve A1 dilimleri.

Durum degerleri: **yok** / **kismi** / **uygulaniyor** / **test edildi** / **dis bagimlilik bekliyor**.
"test edildi" yalniz otomatik test ya da kayitli canli olcum kaniti varsa yazilir. Yalniz UI eklenmesi
"test edildi" saymaz. Kanit yolu bos ise o satir icin dogrulama yapilmamistir.

Kullanicinin 9 Kasim 2026 tarihli Claude Code ozellik listesi kapsam girdisidir; listedeki surum
(v2.1.318) ve erisim iddialari bu belgede bagimsiz olarak dogrulanmamistir. Claude Code'un kapali
servislerine erisim taklit edilmez; her satir YerelAIStudio'nun kendi calisan karsiligini tanimlar.

## A0 - Mevcut hatalar ve baslangic olcumu

| Kimlik | Mevcut durum | Hedef davranis | Bagimlilik | Asama | Test kimligi | Kanit yolu | Kisit |
|---|---|---|---|---|---|---|---|
| A0.1 Baslangic olcumu | test edildi | Testler, ruff ve kapsam kayitli | - | A0 | `pytest --cov`, `ruff` | `DURUM.md` son oturum | Donanim/surum kaydi gerekir |
| A0.2 Adres dogrulama | test edildi | URL ayristirma: yalniz loopback hostname/IP, izinli scheme/port, userinfo reddi | - | A0 | `test_a0_regresyon.py::test_adres_*` | `tests/test_a0_regresyon.py` | Uzak saglayici ayri mod olacak |
| A0.3 Arac cikti kisaltma | test edildi | Alan bazli kisaltma; gecerli JSON, `truncated`, `next_offset`, toplam uzunluk korunur | - | A0 | `test_a0_regresyon.py::test_arac_sonucu_*` | `tests/test_a0_regresyon.py` | Buyuk sonuc artifact'i A2'de |
| A0.4 Gecmiste arac kaniti | test edildi | tool_call/tool_result cifti sirayla gecmise katilir | A0.3 | A0 | `test_a0_regresyon.py::test_gecmis_arac_*` | `tests/test_a0_regresyon.py` | Token butcesine tabi |
| A0.5 Iptalde arac kaydi | test edildi | Iptal/hata/tur siniri yolunda uretilmis arac sonuclari saklanir, sonucsuz cagri isaretlenir | - | A0 | `test_a0_regresyon.py::test_iptalde_*` | `tests/test_a0_regresyon.py` | Yan etki geri alma A2'de |
| A0.6 Tur basi butce | test edildi | Her model cagrisi oncesi butce yeniden hesaplanir; asimda once arac sonuclari kisaltilir, sonra eski mesajlar dusurulur, yetim arac ciftleri ayiklanir | A0.3 | A0 | `test_a0_regresyon.py::test_butce_*`, `test_protokol_temizle_*`, `test_gorsel_base64_*` | `tests/test_a0_regresyon.py` | Karakter tabanli tahmin; gorsel/ses sabit profil maliyetiyle sayilir |
| A0.7 Upload siniri | test edildi | Akista 1 MB'lik parcalarla okuma, sinir asilinca kesme | - | A0 | `test_a0_regresyon.py::test_upload_*` | `tests/test_a0_regresyon.py` | Sinira kadar RAM'de tutulur; disk kotasi A1'de |
| A0.8 Eszamanli mesaj | test edildi | Ayni oturumda sira ve yazma tutarliligi; silinmis oturuma gec cevap kaybolmaz/çökmez | - | A0 | `test_a0_regresyon.py::test_eszamanli_*`, `test_silinmis_oturum_*` | `tests/test_a0_regresyon.py` | Tam kuyruk A3'te |

## A1 - Proje, izin ve guvenli calistirma

| Kimlik | Mevcut durum | Hedef davranis | Bagimlilik | Asama | Test kimligi | Kanit yolu | Kisit |
|---|---|---|---|---|---|---|---|
| A1.1 Proje/workspace | test edildi | Proje ac/sec/kapat, son projeler, cok koklu workspace, ek klasor yetkisi | A0 | A1 | `test_a1_izinler.py::test_proje_*`, `test_cok_koklu_*` | `tests/test_a1_izinler.py` | Klasor secici native degil (in-app yol girisi) |
| A1.2 Talimat kapsami | test edildi | Proje talimati yalniz GUVENILIR projede; "yetki veremez" notuyla sarilir | A1.1 | A1 | `test_guvenilmeyen_proje_talimati_yuklenmez`, `test_proje_talimati_*` | `tests/test_a1_izinler.py` | Metin yine de modele gider; karar backend'de |
| A1.3 Allow/ask/deny | test edildi | Arac, yol, komut, ag hedefi ve yan etki turune gore backend karari | A1.1 | A1 | `test_planla_modu_*`, `test_onayli_mod_*`, `test_yerel_olmayan_ag_*` | `app/agent/policy.py` | Komut/yazma araclari henuz yok (A2) |
| A1.4 Modlar ve onay | test edildi | Sohbet/Planla/Onayli/Otomatik; islem hash'li, sureli onay | A1.3 | A1 | `test_onay_akisi_ve_degisen_islem`, `test_suresi_gecmis_*` | `tests/test_a1_izinler.py` | Onay UI akisi A5'te genisler |
| A1.5 Windows yol guvenligi | test edildi | junction/symlink, UNC, cihaz yolu, ADS, ayrilmis ad, sonda nokta, harf buyuklugu | - | A1 | `test_tehlikeli_yol_metni_reddedilir`, `test_junction_*`, `test_symlink_*` | `app/agent/yollar.py` | TOCTOU tam kapatilmadi: kimlik kontrolu pencereyi daraltir |
| A1.6 Sir maskeleme | test edildi | Hassas dosya reddi (kanonik yolda) + cikti/log maskeleme | A1.5 | A1 | `test_sir_maskeleme`, `test_dosya_araclari_hassas_*` | `app/agent/policy.py` | Maskeleme desen tabanli; her bicimi yakalamaz |
| A1.7 Komut sureci | yok | Env allowlist, timeout, cikti siniri, process-tree iptali | A2 | A2 | - | - | Terminal araciyla birlikte gelir |
| A1.8 Izolasyon adaptoru | kismi | Gercek izolasyon yok; UI'da ACIKCA "izolasyon: yok" gosterilir | A1.7 | A1-A2 | `test_proje_uclari` (izolasyon alani) | `app/agent/policy.py` `bilgi()` | Windows'ta dosya/ag sandbox'i YOK; iddia edilmiyor |
| A1.9 Loopback API | test edildi | Host/Origin kontrolu, oturum anahtari (sayfaya gomulu), CSRF | - | A1 | `test_oturum_anahtari_olmadan_*`, `test_dis_origin_*` | `tests/test_a1_izinler.py` | Ayni kullanicinin baska yerel programi sayfayi okuyabilir |
| A1.10 Yonetilen politika | test edildi | Kurumsal ust sinir yalniz DARALTIR; bozuk dosya gevsetmez | A1.3 | A1 | `test_yonetilen_politika_daraltir_genisletmez`, `test_bozuk_*` | `tests/test_a1_izinler.py` | Dosya korumasi isletim sistemi ACL'ine birakilmadi |

## F01-F24 - Yetenek gruplari

| Kimlik | Ozellik grubu | Mevcut durum | Hedef davranis | Bagimlilik | Asama | Test kimligi | Kanit yolu | Kisit |
|---|---|---|---|---|---|---|---|---|
| F01 | Kod yazma, refactoring, hata duzeltme, test/build | yok | `apply_patch`/`write_file`/terminal + eski hash + checkpoint; test kosup sonucu dogrulayan dongu | A1, A2 | A2-A3 | - | - | Yazma araci A1 izin motoru olmadan acilmaz |
| F02 | Plan, goal, uzun gorev, background isler | yok (sohbette sabit 6 tur) | Kalici Run/Step durum makinesi, butce, pause/resume/cancel/retry | A0.5, A0.6, A1 | A3 | - | - | Tek yerel model: inference sirali |
| F03 | Proje talimatlari, memory, compact, resume, fork | kismi (CLAUDE.md + @import, oturum kaydi) | Kaynakli/butceli baglam, compact ozeti, memory kayit+kaynak+gecersizlesme, fork/export | A0.4, A0.6 | A4 | `tests/test_skiller.py` (talimat importu) | `tests/test_skiller.py` | Guvenilmeyen repo talimati yetki yukseltmez |
| F04 | Diff, checkpoint, rewind, Git/worktree | yok | Dosya bazli snapshot/diff, conflict-aware geri alma, worktree secenegi | A2 | A2-A5 | - | - | `reset --hard` kullanilmaz |
| F05 | Skills, slash komutlari, referans ve scriptler | kismi (kesif + otomatik yukleme; script calistirma yok) | Surumlu metadata, kaynak/hash/trust, registry'li slash komutlari | A1, A6 | A6 | `tests/test_skiller.py` | `tests/test_skiller.py` | Manifestte izin istemek izin degildir |
| F06 | Hooks ve fail-closed denetimler | yok | Surumlu olay sozlesmeleri; guvenlik hook'u basarisizsa islem engellenir | A1, A6 | A6 | - | - | Timeout + recursion siniri zorunlu |
| F07 | MCP, OAuth ve dis servisler | yok | stdio + streamable HTTP MCP istemcisi, backend token, ayni policy katmani | A1, A7 | A7 | - | - | Varsayilan kapali |
| F08 | Plugin, marketplace, bagimlilik, eval | yok | Manifest/surum/karantina/kaynak inceleme/rollback | A7 | A7 | - | - | BRAIN-POLICY kaynak taramasi zorunlu |
| F09 | Mods karsiligi (panel, komut, olay) | yok | Izole worker + dar uzantı API'si | A7 | A7 | - | - | Claude Mods API uyumlulugu iddia edilmez |
| F10 | Subagents, teams, agent view | yok | Dar yetki, ortak butce, dosya sahipligi, mesaj kutusu | A3, A8 | A8 | - | - | Tek model: paralel inference yok |
| F11 | Dynamic workflows | yok | Tipli adimlar, bagimlilik, tekrar; model kodu ana surecte eval edilmez | A8 | A8 | - | - | - |
| F12 | Web arastirmasi, Chrome/Edge, DOM/console, GIF | yok | Izole otomasyon profili, DOM/a11y agaci, screenshot, E2E kaniti | A1, A9 | A9 | - | - | Sayfa icerigi talimat sayilmaz |
| F13 | Windows computer use | yok | Pencere kapsamli UI Automation + gorsel fallback | A9 | A9 | - | - | UAC/secure desktop asilmaz |
| F14 | LSP, VS Code, JetBrains | yok | Sembol/referans/diagnostic; dosya/satir/secim/diff | A2, A10 | A10 | - | - | Dis bagimlilik bekliyor (IDE kurulumu) |
| F15 | Yerel/PR review, derin review, guvenlik incelemesi | yok | Kanitli bulgu, yeniden dogrulama, REVIEW.md | A2, A5 | A5-A8 | - | - | Ayni modelin iki kez demesi kanit degil |
| F16 | CLI, headless, Python/TS SDK, API | kismi (`python -m app --sunucu`, gecit uclari) | Ayni ajan cekirdegine headless/SDK erisimi, JSON event stream, resume | A3 | A10 | `tests/test_agecidi.py` | `tests/test_agecidi.py` | CLI/SDK ayri motor kurmaz |
| F17 | Schedule, loop, channels, CI/webhook | yok | Kalici zamanlayici, imzali olay, idempotency | A3, A11 | A11 | - | - | Uygulama kapaliyken calismaz (iddia edilmez) |
| F18 | Remote control, mobil, cloud | yok | Varsayilan kapali, cihaz eslestirme, kisa omurlu token | A1, A12 | A12 | - | - | Loopback internete acilmaz |
| F19 | Model, effort, fallback, maliyet | kismi (model secimi, dusunme seviyesi, sure/token istatistigi) | ModelCapability profilleri, gorunur fallback, RAM/sure maliyeti | A4 | A4 | `tests/test_yerel_llm.py`, `karsilastir.py` | `tests/test_yerel_llm.py` | Desteklenmeyen effort gizlenir |
| F20 | Permissions, Auto mode, sandbox, politika | kismi (backend izin motoru + modlar + yonetilen politika; OS izolasyonu yok) | Backend allow/ask/deny + OS siniri; mod secimi | A0, A1 | A1 | `tests/test_a1_izinler.py` | `app/agent/policy.py` | OS duzeyinde sandbox YOK; UI'da acikca yazar |
| F21 | OTel, doctor, status, logs, butce | kismi (loguru, istatistik cipleri) | Tanilama uclari, butce gostergesi, redakte log | - | A0-A12 | - | - | Sir maskeleme A1 |
| F22 | Voice, artifacts, preview, status line | kismi (ses eki, OCR, markdown) | Izole origin artifact onizlemesi, dictation adaptoru, durum cubugu | A5 | A5-A10 | `tests/test_api.py` | `tests/test_api.py` | Model HTML'ine bridge token verilmez |
| F23 | GitHub/GitLab, issue -> PR, Actions | yok | Yetkilendirilmis repo islemleri; model metni tek basina gonderim yetkisi degil | A2, A10 | A10-A11 | - | - | Dis bagimlilik bekliyor (yetki) |
| F24 | Dev containers, gateway auth, uzak saglayicilar | yok | Istege bagli adaptorler | A1, A12 | A1-A4-A12 | - | - | Yerel urun icin zorunlu degil |

## Korunan mevcut ozellikler (gerileme yasagi)

| Kimlik | Ozellik | Durum | Test kimligi |
|---|---|---|---|
| K01 | Sohbet + dusunce akisi + iptal | test edildi | `tests/test_api.py`, `tests/test_servisler.py` |
| K02 | Ekler: resim, PDF/OCR, ses, metin | test edildi | `tests/test_api.py`, `tests/test_yerel_llm.py` |
| K03 | Salt okunur sohbet araclari | test edildi | `tests/test_sohbet_araclari.py` |
| K04 | Skill + talimat sistemi | test edildi | `tests/test_skiller.py` |
| K05 | Model magazasi (HF) | test edildi | `tests/test_magaza.py` |
| K06 | Yerel gecit (Ollama/OpenAI/Anthropic) | test edildi | `tests/test_agecidi.py` |
| K07 | Karsilastir / OCR / arac / test paketi ekranlari | test edildi | `tests/test_api.py` |
| K08 | Portable paketleme + `data/` korunmasi | test edildi (2026-11-08 canli) | `paketleme/derle.bat` |
| K09 | Urun sahibi atfi (Hakkinda + X/GitHub) | test edildi | `tests/test_api.py` |

## A13 kalite kapisi durumu

| Olcut | Hedef | Mevcut | Kanit |
|---|---|---|---|
| Python testleri | hepsi gecer | 247 gecti, 3 atladi (2026-11-09, sahte model) | `pytest -q` |
| Python kapsami | >= %90 | %94 (2026-11-09) | `pytest --cov` |
| Ruff format/check | temiz | temiz | `ruff check .` |
| JS birim + E2E | gecer | yok | - |
| 30 gorevlik model eval | >= %80 cekirdek basari | yok | - |
| Claude Code karsilastirmasi | olculmus | yapilmadi | kalite esitligi **dogrulanmadi** |

Model kalite esitligi hicbir satirda iddia edilmez; karsilastirmali olcum yapilana kadar
"dogrulanmadi" durumu gecerlidir.

## Kaynaklar ve dis bagimliliklar

| Kaynak | Durum | Not |
|---|---|---|
| `AGENT-GELISTIRME-TALIMATI.md` | kullanimda | Is tanimi |
| `AGENT-INCELEME-2026-11-09.md` | kullanimda | P1/P2 bulgular |
| Kullanicinin Claude Code ozellik listesi (9 Kasim 2026) | kapsam girdisi | Surum/erisim iddialari dogrulanmadi |
| https://github.com/Twigpine/openclaude | **taranmadi** | Kullanicinin verdigi referans repo. Fikir/desen alinabilir; dosya, kod ya da bagimlilik alinmadan once BRAIN-POLICY dis kaynak guvenlik taramasi + karar raporu zorunlu. |
