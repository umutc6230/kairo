# Ogrenen sistem plani (WrongStack incelemesinden, 2026-11-13)

Kaynak: github.com/WrongStack/WrongStack (MIT, TypeScript). Kod KOPYALANMADI; yalniz tasarim fikirleri.
Hedef (Umut): kendi karar veren, sonucu degerlendirip kendini duzelten, ogrenen, hatayi tekrarlamayan Kairo.

## Kairo'da olmayan, hedefe en cok hizmet eden ozellikler
| # | Ozellik | WrongStack kaynagi | Kairo'da su an | Deger / zorluk |
|---|---|---|---|---|
| 1 | Ders defteri: karar/hata + sonuc eslestirme, benzer gecmisi prompt'a koyma, tekrar basarisiz yolu reddetme | packages/core/src/brain/brain-ledger.ts, docs/slash/brain.md | Yok (hata_sayaci yalniz ayni run) | Cok yuksek / orta |
| 2 | Kanitli hafiza + geri bildirim (SAGE): dayanak dosya metni, yararli/eski/yanlis yargisi, revizyon | docs/sage-feedback-lifecycle.md, packages/sage | Kismi: app/services/hafiza.py (son 20 kayit ilgiye bakmadan) | Yuksek / orta |
| 3 | Sonuc-duyarli tekrar tespiti (A-B-A-B, farkli arguman ayni hata) + koc notlari | docs/agent-feedback.md, docs/tool-coach.md | Kismi: runner.py _ayni_cagri_sayisi yalniz ardisik ayni cagri | Yuksek / dusuk |
| 4 | BrainMonitor: hata yogunlugu/ilerlemesizlikte kendiliginden yon verme | docs/slash/brain.md | Kismi: DONGU_UYAR/DUR, ilerlemesiz | Orta / dusuk |
| 5 | Chimera: gorev sonu otomatik inceleme + duzeltme zinciri | docs/slash/chimera.md | Kismi: app/agent/review.py var, otomatik tetiklenmiyor | Yuksek / orta |
| 6 | Duzenleme sonrasi LSP tanisi arac sonucuna | docs/agent-feedback.md | app/agent/lsp.py var, baglanti dogrulanmadi | Orta / dusuk |
| 7 | Arastirma brief sozlesmesi (kaynak, API adi, surum, belirsizlik) | docs/agent-feedback.md | Yok | Orta / dusuk |

Alinmayacak: Kanban lease, Chronicle SQLite, vector-memory (ikinci model RAM ister), Antigravity HTTP saglayicisi
(belgesiz Google ic API'si + ikiliden cikarilmis OAuth sirri; ToS/kirilganlik).

## Sira
- [x] A. Ders defteri app/agent/dersler.py: <veri>/dersler.jsonl; runner.py hata/dongu/kanit reddi/basarisiz bitiste yazar
  (model cagrisi yok); yeni gorevde ilgili <=5 ders <=600 karakter sisteme; ayni hata tekrarlaninca arac sonucuna
  "daha once goruldu, ise yarayan: ...". Kabul: tekil imza+sayi, cozuldu+cozum, <=600 karakter, maskele.
- [x] B. Dongu tespiti: Adim.sonuc_ozeti, periyot 2-3 tekrar ve ayni hata farkli arguman; koc notlari (yazdiktan
  sonra dogrula, politika reddi kesin).
- [x] C. Kanitli hafiza: dayanak (max 4 source_contains), revizyon, yargilar, hafiza_yargila araci; ilgili en iyi 6, 800 karakter.
- [x] D. Chimera: run bitince review.py degisen dosyalarla, bulgular derslere.
- [x] E. CLI'lar: cli_ajan.py'ye antigravity (agy.exe; headless argumanlari once `agy --help` ile dogrulanmali),
  sohbet araci cli_ye_yaptir(saglayici, gorev, klasor?) -> YanEtki.komut onayi, oturum basina resume.

## Guvenlik notu (WrongStack reposu)
Gizli talimat/Unicode taramasi temiz. Riskli: curl|sh kurulum satirlari (docs/cli-reference.md:90 vb.),
HQ telemetri ham icerik yayini varsayilan acik (docs/configuration.md:2388), ACP katalogu pin'siz `npx -y`.
Kurulmadi, calistirilmadi; indirilen kopya %TEMP%\dis-tarama-wrongstack.
