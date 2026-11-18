# Kairo ajan vs Claude Code: olculmus karsilastirma (20261118)

Gorev seti `degerlendirme/gorevler.py` (30 gorev; Python, TypeScript, JavaScript, C#).
Basari = modelin gormedigi gizli kontroller; gorunur testler degerlendirmeden once
orijinaline geri yuklenir. Ayni hedef metni, adim siniri ve 600 sn sure siniri.

## Kosullar

| | Kairo | Claude Code |
|---|---|---|
| Model | `deepseek/deepseek-v4.1-flash-1017` (openrouter) | `claude-opus-5-5` |
| Surum | `feature/ajan-katmani` | 2.1.327 (Claude Code) |
| Kosu | 90 (90 olculen) | 90 (gorev basina 3) |
| Izinler | otomatik mod; onaylar harness tarafindan verildi ve SAYILDI | acceptEdits + Bash/Read/Edit/Write/Glob/Grep on-izinli |
| Istemci donanimi | AMD Ryzen 7 5700U with Radeon Graphics, 15.3 GB | ayni makine |

## Sonuc

| Olcut | Kairo | Claude Code |
|---|---|---|
| Basari (olculen kosular) | **%98.9** (90) | **%100.0** (90) |
| Yanlis basari beyani | 1 | 0 |
| Kullanici mudahalesi (onay) | 194 | 0 (on-izinli) |
| Ortalama sure / kosu | 28.4 sn | 24.5 sn |
| Maliyet | 0.5066 $ | 10.0029 $ |
| Olculemedi | 0 (kota/harness) | 0 |

## Kategori

| Kategori | Kairo | Claude Code | Fark (puan) |
|---|---|---|---|
| Hata duzeltme | %100.0 (18) | %100.0 (18) | +0.0 |
| Ozellik/refactor | %100.0 (15) | %100.0 (15) | +0.0 |
| Test/build | %100.0 (12) | %100.0 (12) | +0.0 |
| Kesif/review | %100.0 (12) | %100.0 (12) | +0.0 |
| Uzun baglam/devam | %100.0 (12) | %100.0 (12) | +0.0 |
| Toparlanma | %100.0 (12) | %100.0 (12) | +0.0 |
| Web/entegrasyon | %88.9 (9) | %100.0 (9) | -11.1 |

## Gorev bazinda

| Gorev | Yerel (gecen/olculen) | Claude Code | Yerel ort. sn | CC sn |
|---|---|---|---|---|
| hata-py-median | 3/3 | GECTI | 23.8 | 28.4 |
| hata-py-isgunu | 3/3 | GECTI | 16.3 | 18.8 |
| hata-py-indirim-cok-dosya | 3/3 | GECTI | 20.3 | 17.8 |
| hata-ts-slug | 3/3 | GECTI | 45.1 | 20.8 |
| hata-ts-sayfala | 3/3 | GECTI | 34.3 | 19.2 |
| hata-cs-ortalama | 3/3 | GECTI | 30.6 | 16.9 |
| ozellik-py-json-cikti | 3/3 | GECTI | 14.1 | 26.0 |
| refactor-py-ortak-dogrulama | 3/3 | GECTI | 34.5 | 37.0 |
| ozellik-ts-todo-filtre | 3/3 | GECTI | 58.6 | 34.7 |
| refactor-ts-yeniden-adlandir | 3/3 | GECTI | 59.4 | 19.7 |
| ozellik-cs-kdv | 3/3 | GECTI | 51.4 | 18.7 |
| test-py-yaz-mutasyon | 3/3 | GECTI | 24.8 | 34.4 |
| build-py-import | 3/3 | GECTI | 31.3 | 37.8 |
| build-cs-derleme | 3/3 | GECTI | 25.2 | 30.3 |
| build-ts-npm-test | 3/3 | GECTI | 21.6 | 23.5 |
| kesif-parola-hash | 3/3 | GECTI | 15.5 | 20.2 |
| kesif-ortam-degiskenleri | 3/3 | GECTI | 18.9 | 23.9 |
| review-py-sql | 3/3 | GECTI | 22.6 | 26.2 |
| review-ts-kullanilmayan | 3/3 | GECTI | 11.2 | 18.0 |
| uzun-py-cok-modul | 3/3 | GECTI | 32.5 | 40.9 |
| uzun-py-buyuk-dosya | 3/3 | GECTI | 22.4 | 23.8 |
| devam-py-todo | 3/3 | GECTI | 11.7 | 21.9 |
| uzun-ts-buyuk-dosya | 3/3 | GECTI | 42.2 | 40.3 |
| toparlanma-yanlis-yol | 3/3 | GECTI | 9.7 | 17.7 |
| toparlanma-hassas-dosya | 3/3 | GECTI | 9.6 | 14.2 |
| toparlanma-olmayan-komut | 3/3 | GECTI | 41.0 | 19.3 |
| toparlanma-bom-crlf | 3/3 | GECTI | 10.5 | 14.0 |
| web-js-form | 3/3 | GECTI | 27.0 | 19.4 |
| entegrasyon-py-sayfali-api | 3/3 | GECTI | 32.4 | 19.4 |
| entegrasyon-ts-tekrar-dene | 2/3 | GECTI | 52.0 | 29.4 |

## Degerlendirme

- Genel fark **-1.1 puan**. Onceden belirlenen esdegerlik olcutu (fark <= 5 puan ve
  kritik kategoride gerileme yok) **SAGLANMADI**. Gerileyen kategoriler: Web/entegrasyon.
- Fark urun ile modelin TOPLAMIDIR (farkli modeller). Ayni guclu modelle Kairo
  olculmeden farkin urun payi AYRISTIRILAMAZ.
- Yerel ilk surum kapisi (>= %80): GECTI (%98.9). Yanlis basari beyani 1 kosu.
- Belirsizlik: %100 tavan etkisi (set Claude Code icin kolay).
  Ayirt edici olcum icin daha zor gorevlerle set buyutulmeli.
- Kararsiz yerel gorevler: entegrasyon-ts-tekrar-dene.

Ham veri: `degerlendirme/raporlar/` (yerelde; git'e eklenmez).
