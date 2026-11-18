# Kairo ajan vs Claude Code: olculmus karsilastirma (20261118)

Gorev seti `degerlendirme/gorevler.py` (30 gorev; Python, TypeScript, JavaScript, C#).
Basari = modelin gormedigi gizli kontroller; gorunur testler degerlendirmeden once
orijinaline geri yuklenir. Ayni hedef metni, adim siniri ve 600 sn sure siniri.

## Kosullar

| | Kairo | Claude Code |
|---|---|---|
| Model | `deepseek/deepseek-v4.1-flash-1017` (openrouter) | `claude-opus-5-5` |
| Surum | `feature/ajan-katmani` | 2.1.327 (Claude Code) |
| Kosu | 30 (30 olculen) | 90 (gorev basina 3) |
| Izinler | otomatik mod; onaylar harness tarafindan verildi ve SAYILDI | acceptEdits + Bash/Read/Edit/Write/Glob/Grep on-izinli |
| Istemci donanimi | AMD Ryzen 7 5700U with Radeon Graphics, 15.3 GB | ayni makine |

## Sonuc

| Olcut | Kairo | Claude Code |
|---|---|---|
| Basari (olculen kosular) | **%96.7** (30) | **%100.0** (90) |
| Yanlis basari beyani | 1 | 0 |
| Kullanici mudahalesi (onay) | 54 | 0 (on-izinli) |
| Ortalama sure / kosu | 28.7 sn | 24.5 sn |
| Maliyet | 0.1529 $ | 10.0029 $ |
| Olculemedi | 0 (kota/harness) | 0 |

## Kategori

| Kategori | Kairo | Claude Code | Fark (puan) |
|---|---|---|---|
| Hata duzeltme | %100.0 (6) | %100.0 (18) | +0.0 |
| Ozellik/refactor | %100.0 (5) | %100.0 (15) | +0.0 |
| Test/build | %100.0 (4) | %100.0 (12) | +0.0 |
| Kesif/review | %75.0 (4) | %100.0 (12) | -25.0 |
| Uzun baglam/devam | %100.0 (4) | %100.0 (12) | +0.0 |
| Toparlanma | %100.0 (4) | %100.0 (12) | +0.0 |
| Web/entegrasyon | %100.0 (3) | %100.0 (9) | +0.0 |

## Gorev bazinda

| Gorev | Yerel (gecen/olculen) | Claude Code | Yerel ort. sn | CC sn |
|---|---|---|---|---|
| hata-py-median | 1/1 | GECTI | 32.0 | 28.4 |
| hata-py-isgunu | 1/1 | GECTI | 12.6 | 18.8 |
| hata-py-indirim-cok-dosya | 1/1 | GECTI | 22.7 | 17.8 |
| hata-ts-slug | 1/1 | GECTI | 20.9 | 20.8 |
| hata-ts-sayfala | 1/1 | GECTI | 53.1 | 19.2 |
| hata-cs-ortalama | 1/1 | GECTI | 16.7 | 16.9 |
| ozellik-py-json-cikti | 1/1 | GECTI | 11.6 | 26.0 |
| refactor-py-ortak-dogrulama | 1/1 | GECTI | 34.1 | 37.0 |
| ozellik-ts-todo-filtre | 1/1 | GECTI | 42.2 | 34.7 |
| refactor-ts-yeniden-adlandir | 1/1 | GECTI | 35.0 | 19.7 |
| ozellik-cs-kdv | 1/1 | GECTI | 47.3 | 18.7 |
| test-py-yaz-mutasyon | 1/1 | GECTI | 29.8 | 34.4 |
| build-py-import | 1/1 | GECTI | 38.9 | 37.8 |
| build-cs-derleme | 1/1 | GECTI | 26.9 | 30.3 |
| build-ts-npm-test | 1/1 | GECTI | 33.9 | 23.5 |
| kesif-parola-hash | 1/1 | GECTI | 19.6 | 20.2 |
| kesif-ortam-degiskenleri | 1/1 | GECTI | 13.5 | 23.9 |
| review-py-sql | 1/1 | GECTI | 18.7 | 26.2 |
| review-ts-kullanilmayan | 0/1 | GECTI | 19.7 | 18.0 |
| uzun-py-cok-modul | 1/1 | GECTI | 51.5 | 40.9 |
| uzun-py-buyuk-dosya | 1/1 | GECTI | 24.1 | 23.8 |
| devam-py-todo | 1/1 | GECTI | 16.8 | 21.9 |
| uzun-ts-buyuk-dosya | 1/1 | GECTI | 61.6 | 40.3 |
| toparlanma-yanlis-yol | 1/1 | GECTI | 15.7 | 17.7 |
| toparlanma-hassas-dosya | 1/1 | GECTI | 9.7 | 14.2 |
| toparlanma-olmayan-komut | 1/1 | GECTI | 70.0 | 19.3 |
| toparlanma-bom-crlf | 1/1 | GECTI | 7.6 | 14.0 |
| web-js-form | 1/1 | GECTI | 17.9 | 19.4 |
| entegrasyon-py-sayfali-api | 1/1 | GECTI | 13.9 | 19.4 |
| entegrasyon-ts-tekrar-dene | 1/1 | GECTI | 42.4 | 29.4 |

## Degerlendirme

- Genel fark **-3.3 puan**. Onceden belirlenen esdegerlik olcutu (fark <= 5 puan ve
  kritik kategoride gerileme yok) **SAGLANMADI**. Gerileyen kategoriler: Kesif/review.
- Fark urun ile modelin TOPLAMIDIR (farkli modeller). Ayni guclu modelle Kairo
  olculmeden farkin urun payi AYRISTIRILAMAZ.
- Yerel ilk surum kapisi (>= %80): GECTI (%96.7). Yanlis basari beyani 1 kosu.
- Belirsizlik: %100 tavan etkisi (set Claude Code icin kolay).
  Ayirt edici olcum icin daha zor gorevlerle set buyutulmeli.
- Kararsiz yerel gorevler: yok.

Ham veri: `degerlendirme/raporlar/` (yerelde; git'e eklenmez).
