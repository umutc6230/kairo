# Superajan (is emirleri) plani - dsh-superagent tasarimindan

Kaynak: github.com/deepseek-ai/dsh-superagent-prototype (MIT). Kod KOPYALANMAZ; kavramlar Python'da yeniden yazilir.
Neden port: orijinal DeepSeek Harness runtime + ~20 alfa paket + tmux/fcntl (Linux/macOS) ister, Windows'ta calismaz.
Plan 2026-11-14 (Fable 5.2 entegrasyon plani, kod okunarak dogrulandi).

## Kapsam
- Yeni varlik yalniz 2: Is emri (Ticket), Tetik (Trigger, degismez; ayni tetik iki kez is emri acmaz).
- Is emrinin alanlari: yetki {yazan, guc, mod} (Mandate), runlar[] (Assignment = AgentRunner Run), konular[]
  ("owner/repo#12"; Thread+Subscription+Channel).
- Saf fonksiyonlar: kapi(tetik, ayar) -> acik|yok (Eval gate); asama(is, run) (003 tablosu, ilk eslesen satir).
- Ayar: tek GitHub deposu, izinli login listesi, mod gozle (varsayilan) | yap.
- Atlananlar: LLM assessment, kurallar/admission tablosu, bot listesi, Policy surumu, Correlation, handoff,
  orchestrator oturumu, prompt override, Feishu, auto-merge.
- Sapma: gozle modunda GitHub'dan gelen acik istek de calismaz; panelde "Baslat" bekler, GitHub'a yazilmaz.
- Kalici Ajan (ajanlar.py) kullanilmaz (is emri basina ayri worktree gerekir). Webhook/rutin degismez.

## Kaynaklar (sira: c, b, a)
- (c) Elle: panelde "Yeni is emri" -> POST /api/superajan/isler.
- (b) Sohbet: mevcut alt_oturum_oner kartina 2. dugme "Arka planda yaptir (ayri dal)"; ALT_OTURUM_ARACI
  aciklamasina "uygulama/ozellik yapim isteklerinde oner".
- (a) GitHub: gh api -i, sabit URL + If-None-Match (ETag): repos/{depo}/issues/comments?sort=updated&direction=desc&per_page=30
  ve repos/{depo}/issues?state=all&sort=updated&direction=desc&per_page=30. Hitap: satir basinda /kairo
  (ajan_hesabi varsa @hesap). Kendi yorumu: ilk satirda <!-- kairo --> isareti; [bot] loginleri atlanir.

## Yurutucu
- Is emri = ajan.baslat(...) + izole_kur (wt.olustur, api.py gorev_baslat ile ayni). Takip: calisma_koku + onceki.
- Calisan run'a yorum: AgentRunner.mesaj. Proje acik degilse "sirada".
- tmux yerine asyncio gorevleri; fcntl yerine RLock + json_yaz; dinleyici yerine _ajan_dongusu icinden _superajan_tick (60 sn).
- Eszamanlilik 2. Rapor eslemesi: basarili -> inceleme; dogrulanmadi -> taslak; cevap/onay bekliyor -> insan;
  basarisiz -> basarisiz; ozet basinda IS_YOK -> yapilacak yok.
- Teslim host tarafinda: wt.commit_et (entegre_et'ten cikarilir) + git push + gh pr create; gozle'de yalniz
  "PR ac" tiklamasiyla, yap'ta yalniz dogrulandi ise. Sonuc yorumu gh issue comment.

## Veri / dosyalar
- YENI app/agent/superajan.py: IsEmri, Tetik, SuperajanDeposu (<veri>/superajan.json), kapi, asama, gorev_metni,
  github_yokla, teslim_et, _gh (api.py github_baglan'daki gh bulma buraya).
- api.py: depo + _superajan_tick + rotalar GET /api/superajan, PUT /ayar, POST /isler, /isler/{id}/baslat|durdur|tekrar|teslim, POST /yokla.
- Arayuz: YENI app/web/superajan.js; Ajanlar sayfasinda <details id="aj-isler">; yalniz insan bekleyenler + sayac.
- NOTICE-dsh-superagent.md.

## Guvenlik
- Izinsiz/hitapsiz: yalniz tetik kaydi. izinli varsayilan = gh api user.
- Issue metni veri zarfinda (webhook.hedef_olustur kalibi). Mod/izinli/depo yalniz panelden.
- maskele: tetik metni + GitHub'a giden her govde. gh token modele gitmez.
- ACIK: tam yetkide komut_calistir ile git push / gh pr create sorulmadan gecer -> is emri worktree'lerinde
  git push|gh (pr|issue|api|release) reddi.

## Dilimler
- D1: cekirdek + elle is emri + tick + worktree run + panel + NOTICE. Test tests/test_superajan.py.
- D2: sohbet karti dugmesi. D3: GitHub salt okunur (adaylar). D4: disa yazma (commit/push/PR/yorum, yap modu, komut engeli).
- D5: takip yorumlari, yeniden acma, PR kapanisi, kalici Durdur.

## Kullaniciya sorulacak
1. Git deposu olmayan bos klasorde "uygulama yap": onayla git init + ilk commit mi, izolesiz mi?
2. Sohbette her zaman onay karti mi (onerilen), kartsiz otomatik baslatma da mi?
3. GitHub hitabi /kairo komutu mu (onerilen, ayri hesap gerekmez), ayri ajan hesabi + @mention mi?
