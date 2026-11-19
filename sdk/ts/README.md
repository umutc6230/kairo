# kairo-sdk (TypeScript)

Çalışan Kairo'nun yerel HTTP API'sine bağlanan, bağımlılıksız küçük istemci (Node 18+, yalnız `fetch`).
Ayrı bir ajan motoru yoktur: izin, bütçe ve onay kuralları arayüzdekiyle birebir aynıdır.
Python karşılığı: `app/sdk.py`.

## Derleme

```
cd sdk/ts
npm install      # yalnız typescript (geliştirme)
npm run build    # dist/ içine derler
```

## Bağlantı

Her `/api` isteği oturum anahtarını `X-YAS-Oturum` başlığıyla ister. Anahtar Kairo her açıldığında
yeniden üretilir ve ana sayfaya (`/`) `<meta name="yas-oturum" content="...">` olarak gömülür.
`Kairo.baglan(adres)` bunu otomatik okur; anahtar elinizdeyse `new Kairo(adres, anahtar)`.

## Örnek

```ts
import { Kairo } from "kairo-sdk";

const k = await Kairo.baglan("http://127.0.0.1:8765");
await k.projeAc("C:/projem", "guvenilir", "onayli");

const gorev = await k.gorevBaslat("testleri geçir", { kabul: ["pytest geçsin"] });
let son = await k.bekle(gorev.id, {
  zamanAsimiMs: 10 * 60_000,
  degisince: (g) => console.log(g.durum, g.adimlar.length),
});

if (son.durum === "onay_bekliyor") {
  const adim = son.adimlar.find((a) => a.durum === "onay_bekliyor")!;
  await k.onayVer(adim.onay_id, true); // onaylanınca görev kaldığı yerden sürer
  son = await k.bekle(gorev.id);
}
console.log(son.sonuc.ozet);
```

## Yöntemler

| Yöntem | Uç |
|---|---|
| `bilgi()` | `GET /api/bilgi` |
| `projeAc(yol, guven, mod)` | `POST /api/projeler` (+ `PUT /api/projeler/{id}/mod`) |
| `gorevBaslat(hedef, seçenekler)` | `POST /api/gorevler` |
| `gorevDurumu(id)` | `GET /api/gorevler/{id}` |
| `bekle(id, seçenekler)` | durum yoklama; bitince ya da onay/karar beklerken döner, zaman aşımı var |
| `gorevMesaji(id, metin)` | `POST /api/gorevler/{id}/mesaj` |
| `iptal(id)` / `gorevIslemi(id, islem)` | `POST /api/gorevler/{id}/{duraklat,devam,iptal,tekrar}` |
| `onayVer(onayId, onayla, kapsam)` | `POST /api/onaylar/{id}` |

Hatalar `KairoHatasi` olarak fırlatılır (`durumKodu` HTTP kodudur).

---

Ürün sahibi: Umut Çelik - [X](https://x.com/umutc6230) - [GitHub](https://github.com/umutc6230)
