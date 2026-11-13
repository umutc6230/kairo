# OZELLIK-MATRISI - Kairo ajan yetenekleri

Kaynak is tanimi: `AGENT-GELISTIRME-TALIMATI.md`. Inceleme: `AGENT-INCELEME-2026-11-09.md`.
Guncel: 2026-11-11 | dal: `feature/ajan-katmani`

Durum degerleri: **yok** / **kismi** / **uygulaniyor** / **test edildi** / **dis bagimlilik bekliyor**.
"test edildi" yalniz otomatik test ya da kayitli canli olcum kaniti varsa yazilir. Yalniz UI eklenmesi
"test edildi" saymaz. Kanit yolu bos ise o satir icin dogrulama yapilmamistir.

Kullanicinin 9 Kasim 2026 tarihli Claude Code ozellik listesi kapsam girdisidir; listedeki surum
(v2.1.318) ve erisim iddialari bu belgede bagimsiz olarak dogrulanmamistir. Claude Code'un kapali
servislerine erisim taklit edilmez; her satir Kairo'nun kendi calisan karsiligini tanimlar.

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
| F01 | Kod yazma, refactoring, hata duzeltme, test/build | test edildi | Yama/yaz (eski hash + checkpoint), terminal, test kosup dogrulayan dongu | A1, A2 | A2-A3 | `test_a2_araclar.py`, `test_a3_ajan.py` | `app/agent/araclar.py` | Gercek model: A13 degerlendirmesi |
| F02 | Plan, goal, uzun gorev, background isler | test edildi | Kalici Run/Adim, butce, duraklat/devam/iptal/tekrar, cokme sonrasi kurtarma | A0.5, A0.6, A1 | A3 | `test_a3_ajan.py`, `test_a13_kapi.py` | `app/agent/runner.py` | Tek yerel model: inference sirali |
| F03 | Proje talimatlari, memory, compact, resume, fork | test edildi | Kaynakli baglam, otomatik ozet, hafiza (kaynak + gecersizlesme) | A0.4, A0.6 | A4 | `test_a4_baglam.py` | `app/agent/ozet.py`, `app/services/hafiza.py` | Alt klasor talimat kapsami ertelendi |
| F04 | Diff, checkpoint, rewind, Git/worktree | test edildi | Dosya bazli checkpoint/geri alma, izole worktree | A2 | A2-A8 | `test_a2_kalan.py`, `test_a8_worktree.py` | `app/agent/checkpoints.py`, `worktree.py` | `reset --hard` kullanilmaz |
| F05 | Skills, slash komutlari, referans ve scriptler | test edildi | Surum/hash/guven, ilan edilmis scriptler ayni izin yolundan | A1, A6 | A6 | `test_a6_skill.py`, `test_a6_skill_script.py` | `app/services/skiller.py` | Manifestte izin istemek izin degildir |
| F06 | Hooks ve fail-closed denetimler | test edildi | Surumlu olaylar; guvenlik hook'u basarisizsa islem engellenir | A1, A6 | A6 | `test_a6_hooks.py` | `app/agent/hooks.py` | Timeout + recursion siniri |
| F07 | MCP, OAuth ve dis servisler | kismi | stdio + streamable HTTP MCP, ayni policy katmani | A1, A7 | A7 | `test_a7_mcp.py` | `app/agent/mcp.py` | MCP prompts yok; buyuk sunucular gecitle (arac_ara/sema/cagir); arac paketleri: REA ve Craft Anything kurulu |
| F08 | Plugin, marketplace, bagimlilik, eval | test edildi | Claude Code plugin formati birebir: .claude-plugin/plugin.json, skills, commands (/plugin:komut, $ARGUMENTS), agents (alt ajan profili), hooks.json (claude stdin, cikis 2), .mcp.json, marketplace.json, git kaynak; Claude Code kurulu pluginlerini ice aktarma | A7 | A7 | `test_a7_plugin.py`, `test_a7_cc_plugin.py` | `app/services/pluginler.py`, `cc_plugin.py` | Plugin eval yok; type:prompt hook, LSP, output-styles desteklenmez |
| F09 | Mods karsiligi (panel, komut, olay) | test edildi | Ayri surec + JSON satir protokolu, sandbox iframe panel, onayli arac | A7 | A7 | `test_a7_uzanti.py` | `app/services/uzantilar.py` | - |
| F10 | Subagents, teams, agent view | test edildi | Dar yetki, dosya sahipligi, takim panosu | A3, A8 | A8 | `test_a8_alt_ajan.py`, `test_a8_takim.py` | `app/agent/takim.py` | Tek model: paralel inference yok |
| F11 | Dynamic workflows | test edildi | Tipli adimlar (ajan/komut), bagimlilik, tekrar; eval yok | A8 | A8 | `test_a8_akis.py` | `app/agent/akis.py` | - |
| F12 | Web arastirmasi, tarayici, DOM/console | test edildi | Izole profil, a11y agaci, ekran goruntusu | A1, A9 | A9 | `test_a9_web.py`, `test_a9_tarayici.py` | `app/agent/tarayici.py` | GIF kaydi yok; Playwright istege bagli |
| F13 | Windows computer use | test edildi | Izinli programlarda UI Automation | A9 | A9 | `test_a9_masaustu.py` | `app/agent/masaustu.py` | Gorsel fallback yok; UAC asilmaz |
| F14 | LSP, VS Code, JetBrains | kismi | LSP tanim/referans/sembol/tani + metin yedegi | A2, A10 | A10 | `test_a10_lsp.py` | `app/agent/lsp.py` | IDE eklentileri ATLANDI (kullanici karari) |
| F15 | Yerel/PR review, derin review, guvenlik incelemesi | test edildi | Kanitli bulgu, derin gecisler | A2, A5 | A5-A8 | `test_a5_review_artifact.py` | `app/agent/review.py` | PR yorumu yok (GitHub atlandi) |
| F16 | CLI, headless, Python/TS SDK, API | kismi | Ayni motor: headless CLI + Python SDK, JSON olaylar, onayda kod 3 | A3 | A10 | `test_a10_cli_sdk.py` | `app/cli.py`, `app/sdk.py` | TS SDK yok |
| F17 | Schedule, loop, channels, CI/webhook | test edildi | Kalici zamanlayici (DST/idempotent), HMAC webhook, GitHub Actions | A3, A11 | A11 | `test_a11_zamanlayici.py`, `test_a11_webhook.py` | `.github/workflows/` | Uygulama kapaliyken calismaz; CI hesap faturasi nedeniyle baslamadi |
| F18 | Remote control, mobil, cloud | kismi | Tailscale uzerinden telefondan tam arayuz, eslesme/iptal/TLS | A1, A12 | A12 | `test_a12_uzak.py`, `test_a13_e2e.py` | `app/uzak.py` | Cloud worker dis bagimlilik bekliyor; canli telefon denemesi yok |
| F19 | Model, effort, fallback, maliyet | test edildi | Yetenek profili, OpenRouter, dusunme seviyesi | A4 | A4 | `test_openrouter.py`, `test_yerel_llm.py` | `app/agent/yetenek.py` | Desteklenmeyen effort gizlenir |
| F20 | Permissions, Auto mode, sandbox, politika | test edildi | Backend allow/ask/deny, modlar, yonetilen politika, istege bagli konteyner | A0, A1 | A1 | `test_a1_izinler.py`, `test_a1_8_izolasyon.py` | `app/agent/policy.py` | Konteyner yoksa OS sandbox YOK (acikca yazar) |
| F21 | OTel, doctor, status, logs, butce | kismi | /doctor, /status, redakte log, butce | - | A0-A12 | `test_a10_cli_sdk.py::test_doctor_*` | `app/doktor.py` | OTel yok |
| F22 | Voice, artifacts, preview, status line | test edildi | Yerel dikte, artifact onizleme | A5 | A5 | `test_a5_dikte_a11y.py`, `test_a5_review_artifact.py` | `app/services/artifactler.py` | - |
| F23 | GitHub/GitLab, issue -> PR, Actions | kismi | CI is akislari var; issue/PR araclari ATLANDI | A2, A10 | A10-A11 | - | `.github/workflows/` | Kullanici karari: A10 kalani atlandi |
| F24 | Dev containers, gateway auth, uzak saglayicilar | kismi | OpenRouter + konteyner izolasyonu; kurumsal gateway yok | A1, A12 | A1-A12 | `test_openrouter.py` | `app/services/openrouter.py` | Bedrock/Google/Microsoft dis bagimlilik bekliyor |

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
| Python testleri | hepsi gecer | 520 gecti, 3 atladi (2026-11-10) | `pytest -q` |
| Python kapsami | >= %90 | %91 (2026-11-10) | `pytest --cov` |
| Ruff format/check | temiz | temiz | `ruff check .` |
| Iptal kapisi | durum < 1 sn, surec agaci < 5 sn | olculdu: gecti | `tests/test_a13_kapi.py` |
| Arayuz E2E | gecer | masaustu + telefon (uzak TLS) gecti | `tests/test_a13_e2e.py` |
| JS birim testleri | gecer | yok (yalniz `node --check` + E2E) | - |
| 30 gorevlik model eval | >= %80 cekirdek basari | %83.2 (95 olculen kosu, nemotron-3.5-super-vl:free); kesif/review %25 | `degerlendirme/KARSILASTIRMA-2026-11-11.md` |
| Claude Code karsilastirmasi | olculmus | olculdu: CC %100 (30 kosu, Opus 5.5, 3.36 $); fark -16.8 puan, esdegerlik SAGLANMADI (farkli modeller) | `degerlendirme/KARSILASTIRMA-2026-11-11.md` |

Model kalite esitligi hicbir satirda iddia edilmez; karsilastirmali olcum yapilana kadar
"dogrulanmadi" durumu gecerlidir.

## Kaynaklar ve dis bagimliliklar

| Kaynak | Durum | Not |
|---|---|---|
| `AGENT-GELISTIRME-TALIMATI.md` | kullanimda | Is tanimi |
| `AGENT-INCELEME-2026-11-09.md` | kullanimda | P1/P2 bulgular |
| Kullanicinin Claude Code ozellik listesi (9 Kasim 2026) | kapsam girdisi | Surum/erisim iddialari dogrulanmadi |
| https://github.com/Twigpine/openclaude | **taranmadi** | Kullanicinin verdigi referans repo. Fikir/desen alinabilir; dosya, kod ya da bagimlilik alinmadan once BRAIN-POLICY dis kaynak guvenlik taramasi + karar raporu zorunlu. |
