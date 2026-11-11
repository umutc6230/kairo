# Yerel AI Studio ajan vs Claude Code: olculmus karsilastirma (20261111)

Gorev seti `degerlendirme/gorevler.py` (30 gorev; Python, TypeScript, JavaScript, C#).
Basari = modelin gormedigi gizli kontroller; gorunur testler degerlendirmeden once
orijinaline geri yuklenir. Ayni hedef metni, adim siniri ve 600 sn sure siniri.

## Kosullar

| | Yerel AI Studio | Claude Code |
|---|---|---|
| Model | `nvidia/nemotron-3.5-super-vl:free` (openrouter) | `claude-opus-5-5` |
| Surum | `feature/ajan-katmani` | 2.1.322 (Claude Code) |
| Kosu | 108 (95 olculen) | 30 (gorev basina 1) |
| Izinler | otomatik mod; onaylar harness tarafindan verildi ve SAYILDI | acceptEdits + Bash/Read/Edit/Write/Glob/Grep on-izinli |
| Istemci donanimi | AMD Ryzen 7 5700U with Radeon Graphics, 15.3 GB | ayni makine |

## Sonuc

| Olcut | Yerel AI Studio | Claude Code |
|---|---|---|
| Basari (olculen kosular) | **%83.2** (95) | **%100.0** (30) |
| Yanlis basari beyani | 11 | 0 |
| Kullanici mudahalesi (onay) | 216 | 0 (on-izinli) |
| Ortalama sure / kosu | 53.1 sn | 26.0 sn |
| Maliyet | 0 $ (ucretsiz model) | 3.36 $ |
| Olculemedi | 13 (kota/harness) | 0 |

## Kategori

| Kategori | Yerel AI Studio | Claude Code | Fark (puan) |
|---|---|---|---|
| Hata duzeltme | %94.7 (19) | %100.0 (6) | -5.3 |
| Ozellik/refactor | %80.0 (15) | %100.0 (5) | -20.0 |
| Test/build | %100.0 (12) | %100.0 (4) | +0.0 |
| Kesif/review | %25.0 (12) | %100.0 (4) | -75.0 |
| Uzun baglam/devam | %100.0 (14) | %100.0 (4) | +0.0 |
| Toparlanma | %100.0 (14) | %100.0 (4) | +0.0 |
| Web/entegrasyon | %66.7 (9) | %100.0 (3) | -33.3 |

## Gorev bazinda

| Gorev | Yerel (gecen/olculen) | Claude Code | Yerel ort. sn | CC sn |
|---|---|---|---|---|
| hata-py-median | 3/3 | GECTI | 42.8 | 27.2 |
| hata-py-isgunu | 3/3 | GECTI | 27.2 | 23.9 |
| hata-py-indirim-cok-dosya | 3/3 | GECTI | 37.9 | 19.5 |
| hata-ts-slug | 3/4 | GECTI | 89.7 | 24.9 |
| hata-ts-sayfala | 3/3 | GECTI | 33.6 | 25.2 |
| hata-cs-ortalama | 3/3 | GECTI | 36.7 | 13.8 |
| ozellik-py-json-cikti | 3/3 | GECTI | 29.6 | 28.4 |
| refactor-py-ortak-dogrulama | 3/3 | GECTI | 48.5 | 40.7 |
| ozellik-ts-todo-filtre | 0/3 | GECTI | 56.0 | 29.6 |
| refactor-ts-yeniden-adlandir | 3/3 | GECTI | 76.1 | 21.8 |
| ozellik-cs-kdv | 3/3 | GECTI | 51.0 | 21.9 |
| test-py-yaz-mutasyon | 3/3 | GECTI | 55.6 | 33.5 |
| build-py-import | 3/3 | GECTI | 45.8 | 37.1 |
| build-cs-derleme | 3/3 | GECTI | 45.2 | 30.4 |
| build-ts-npm-test | 3/3 | GECTI | 72.8 | 26.4 |
| kesif-parola-hash | 0/3 | GECTI | 78.8 | 20.6 |
| kesif-ortam-degiskenleri | 0/3 | GECTI | 41.0 | 26.5 |
| review-py-sql | 3/3 | GECTI | 25.3 | 33.3 |
| review-ts-kullanilmayan | 0/3 | GECTI | 35.4 | 21.9 |
| uzun-py-cok-modul | 3/3 | GECTI | 48.7 | 39.3 |
| uzun-py-buyuk-dosya | 5/5 | GECTI | 67.6 | 28.7 |
| devam-py-todo | 3/3 | GECTI | 29.7 | 24.1 |
| uzun-ts-buyuk-dosya | 3/3 | GECTI | 164.8 | 19.2 |
| toparlanma-yanlis-yol | 3/3 | GECTI | 32.9 | 21.3 |
| toparlanma-hassas-dosya | 3/3 | GECTI | 24.4 | 14.1 |
| toparlanma-olmayan-komut | 3/3 | GECTI | 99.0 | 31.5 |
| toparlanma-bom-crlf | 5/5 | GECTI | 26.4 | 18.6 |
| web-js-form | 3/3 | GECTI | 36.5 | 22.8 |
| entegrasyon-py-sayfali-api | 3/3 | GECTI | 24.7 | 22.6 |
| entegrasyon-ts-tekrar-dene | 0/3 | GECTI | 106.9 | 31.0 |

## Degerlendirme

- Genel fark **-16.8 puan**. Onceden belirlenen esdegerlik olcutu (fark <= 5 puan ve
  kritik kategoride gerileme yok) **SAGLANMADI**. Gerileyen kategoriler: Hata duzeltme, Ozellik/refactor, Kesif/review, Web/entegrasyon.
- Fark urun ile modelin TOPLAMIDIR (farkli modeller). Ayni guclu modelle Yerel AI Studio
  olculmeden farkin urun payi AYRISTIRILAMAZ.
- Yerel ilk surum kapisi (>= %80): GECTI (%83.2). Yanlis basari beyani 11 kosu.
- Belirsizlik: Claude Code gorev basina 1 kosu; %100 tavan etkisi (set onun icin kolay).
  Ayirt edici olcum icin daha zor gorevlerle set buyutulmeli.
- Kararsiz yerel gorevler: hata-ts-slug.

Ham veri: `degerlendirme/raporlar/` (yerelde; git'e eklenmez).
