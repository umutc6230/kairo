# Karsilastirma v2 - Yerel AI Studio vs Claude Code (2026-11-11)

Ayni 30 gorev, gizli kontroller, korunan testler. Tum olculen kosular sayilir (iyi secilmez).

| | Yerel AI Studio v1 | Yerel AI Studio v2 | Claude Code 2.1.322 |
|---|---|---|---|
| Model | nemotron-3.5-super-vl:free | deepseek/deepseek-v4.1-flash | Opus 5.5 |
| Kosu | 95 (13 olculemedi) | **90 / 90 olculdu** | 30 |
| Basari | %83.2 | **%98.9 (89/90)** | %100 |
| Yanlis basari beyani | 11 | **0** | 0 |
| Zaman asimi | - | 0 | 0 |
| Toplam sure | - | 53 dk (ort. 36 sn/kosu) | ort. 26 sn/kosu |

## Kategori (v2)

| Kategori | v1 | v2 |
|---|---|---|
| Hata duzeltme | %95-100 | %100 |
| Ozellik/refactor | %80 | %100 |
| Test/build | %95-100 | %100 |
| Kesif/review | %25 | %100 |
| Uzun baglam/devam | %95-100 | %91.7 (11/12) |
| Toparlanma | %95-100 | %100 |
| Entegrasyon | %66.7 | %100 |

## Kalan tek basarisizlik

`uzun-py-buyuk-dosya` 1 kosuda kaldi. Ajan gorevi kendisi "basarisiz" olarak bitirdi (yanlis
basari beyani yok). Ayni gorev ek 5 kosuda 5/5 gecti: toplam 7/8. Tekrarlanabilir bir urun hatasi
bulunamadi; model kararsizligi olarak siniflandi.

## Bu turdaki duzeltmeler

- OLCUM HATASI (2 kesif gorevi): gizli kontroller bicimi (tablo yerine yalniz `- madde`) ve aciklama
  bolumundeki adi cezalandiriyordu; dogru cevaplar KALDI sayiliyordu. Kontroller artik liste maddesi
  + tablo satirini sayar, basligi "okunmayan/kullanilan/referans" olan aciklama bolumunu saymaz.
  Dogrulama: model cevaplari ve referans cozum gecer; 4 farkli yanlis cevap (listede/tabloda
  LEGACY_PORT, kullanilan fonksiyonu listeleme, eksik liste) REDDEDILIR. Claude Code ayni kontrolle olculur.

## Yorum

Islevsel kapsama (ayni 30 gorev) %98.9 / %100. Fark artik urun eksigi degil, tek kosuluk model
kararsizligi. Modeller farkli oldugu icin bu bir "model+urun" karsilastirmasidir.
