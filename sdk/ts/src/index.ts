/**
 * Kairo TypeScript SDK: calisan Kairo'nun yerel HTTP API'sine baglanir (Node 18+, yalniz fetch).
 * Ayri bir ajan motoru YOKTUR; izin, butce ve onay kurallari arayuzdekiyle aynidir.
 * Python karsiligi: app/sdk.py.
 */

export type GorevDurumu =
  | "calisiyor"
  | "duraklatildi"
  | "onay_bekliyor"
  | "karar_bekliyor"
  | "cevap_bekliyor"
  | "iptal"
  | "basarili"
  | "dogrulanmadi"
  | "basarisiz";

export type AdimDurumu =
  | "sirada"
  | "niyet"
  | "tamam"
  | "hata"
  | "onay_bekliyor"
  | "cevap_bekliyor"
  | "reddedildi"
  | "belirsiz"
  | "atlandi"
  | "tekrarla";

export const BITMIS: readonly GorevDurumu[] = ["basarili", "dogrulanmadi", "basarisiz", "iptal"];
/** Bitmis ya da kullanici girdisi bekleyen durumlar: bekle() burada doner. */
export const DURAN: readonly GorevDurumu[] = [
  ...BITMIS,
  "onay_bekliyor",
  "karar_bekliyor",
  "cevap_bekliyor",
  "duraklatildi",
];

export interface Butce {
  max_adim?: number;
  max_sure_sn?: number;
  max_token?: number;
  max_ayni_hata?: number;
  max_ilerlemesiz?: number;
  max_ardisik_ret?: number;
}

export interface Kullanim {
  adim: number;
  token: number;
  sure_sn: number;
  model_cagrisi: number;
  maliyet_usd?: number;
}

export interface Adim {
  no: number;
  arac: string;
  argumanlar: Record<string, unknown>;
  cagri_id: string;
  durum: AdimDurumu;
  yan_etkili: boolean;
  sonuc: string;
  onay_id: string;
  cikis_kodu: number | null;
  dosya: string;
  zaman: string;
}

export interface Sonuc {
  ozet: string;
  kanit: number[];
  dogrulandi: boolean;
}

export interface Gorev {
  id: string;
  hedef: string;
  kabul: string[];
  model: string;
  durum: GorevDurumu;
  butce: Required<Butce>;
  kullanim: Kullanim;
  adimlar: Adim[];
  sonuc: Sonuc;
  hata: string;
  calisma_koku: string;
  dal: string;
  olusturma: string;
  guncelleme: string;
  [alan: string]: unknown; // sunucu modeli genisleyebilir
}

export interface GorevSecenekleri {
  kabul?: string[];
  butce?: Butce;
  izole?: boolean;
  onceki?: string;
  etkilesimli?: boolean;
}

export type OnayKapsami = "tek" | "sohbet" | "her_zaman";
export type GorevIslemi = "duraklat" | "devam" | "iptal" | "tekrar";

export interface BekleSecenekleri {
  /** Yoklama araligi (ms). Varsayilan 1000. */
  aralikMs?: number;
  /** En fazla bekleme (ms). Varsayilan 24 saat; dolunca KairoHatasi firlatir. */
  zamanAsimiMs?: number;
  /** true ise yalniz bitmis durumda doner; onay/karar beklerken de beklemeyi surdurur. */
  yalnizBitmis?: boolean;
  /** Durum degistikce cagrilir. */
  degisince?: (gorev: Gorev) => void;
}

export class KairoHatasi extends Error {
  readonly durumKodu?: number;

  constructor(mesaj: string, durumKodu?: number) {
    super(mesaj);
    this.name = "KairoHatasi";
    this.durumKodu = durumKodu;
  }
}

export class Kairo {
  /** Kairo oturum anahtarini bu basliktan ister. */
  static readonly BASLIK = "X-YAS-Oturum";
  private readonly adres: string;
  private readonly anahtar: string;
  private readonly istekZamanAsimiMs: number;

  /**
   * @param adres Taban URL, ornek "http://127.0.0.1:8765"
   * @param anahtar Oturum anahtari (ana sayfadaki meta etiketi "yas-oturum")
   * @param istekZamanAsimiMs Tek istek zaman asimi (ms), varsayilan 60000
   */
  constructor(adres: string, anahtar: string, istekZamanAsimiMs = 60_000) {
    this.adres = adres.replace(/\/+$/, "");
    this.anahtar = anahtar;
    this.istekZamanAsimiMs = istekZamanAsimiMs;
  }

  /** Ana sayfadaki meta etiketinden anahtari okuyup baglanir (yalniz bu makinedeki Kairo). */
  static async baglan(adres: string): Promise<Kairo> {
    const r = await fetch(`${adres.replace(/\/+$/, "")}/`);
    const html = await r.text();
    const m = /<meta name="yas-oturum" content="([^"]+)"/.exec(html);
    if (!m) throw new KairoHatasi("Oturum anahtari bulunamadi.", r.status);
    return new Kairo(adres, m[1]);
  }

  private async istek<T>(yontem: string, yol: string, govde?: unknown): Promise<T> {
    const basliklar: Record<string, string> = { [Kairo.BASLIK]: this.anahtar };
    if (govde !== undefined) basliklar["Content-Type"] = "application/json";
    const r = await fetch(`${this.adres}/api${yol}`, {
      method: yontem,
      headers: basliklar,
      body: govde === undefined ? undefined : JSON.stringify(govde),
      signal: AbortSignal.timeout(this.istekZamanAsimiMs),
    });
    let veri: unknown = {};
    try {
      veri = await r.json();
    } catch {
      // govde JSON degil
    }
    if (!r.ok) {
      const hata = (veri as { hata?: string }).hata;
      throw new KairoHatasi(hata || `HTTP ${r.status}`, r.status);
    }
    return veri as T;
  }

  bilgi(): Promise<Record<string, unknown>> {
    return this.istek("GET", "/bilgi");
  }

  async projeAc(
    yol: string,
    guven: "guvenilmeyen" | "sinirli" | "guvenilir" = "sinirli",
    mod?: string,
  ): Promise<Record<string, unknown>> {
    const p = await this.istek<Record<string, unknown>>("POST", "/projeler", { yol, guven });
    if (mod) await this.istek("PUT", `/projeler/${p.id}/mod`, { mod });
    return p;
  }

  gorevBaslat(hedef: string, sec: GorevSecenekleri = {}): Promise<Gorev> {
    return this.istek("POST", "/gorevler", {
      hedef,
      kabul: sec.kabul ?? [],
      izole: sec.izole ?? false,
      ...(sec.butce ? { butce: sec.butce } : {}),
      ...(sec.onceki ? { onceki: sec.onceki } : {}),
      ...(sec.etkilesimli ? { etkilesimli: true } : {}),
    });
  }

  gorevDurumu(id: string): Promise<Gorev> {
    return this.istek("GET", `/gorevler/${encodeURIComponent(id)}`);
  }

  gorevMesaji(id: string, metin: string): Promise<Gorev> {
    return this.istek("POST", `/gorevler/${encodeURIComponent(id)}/mesaj`, { metin });
  }

  gorevIslemi(id: string, islem: GorevIslemi): Promise<Gorev> {
    return this.istek("POST", `/gorevler/${encodeURIComponent(id)}/${islem}`);
  }

  iptal(id: string): Promise<Gorev> {
    return this.gorevIslemi(id, "iptal");
  }

  onayVer(onayId: string, onayla: boolean, kapsam: OnayKapsami = "tek"): Promise<unknown> {
    return this.istek("POST", `/onaylar/${encodeURIComponent(onayId)}`, { onayla, kapsam });
  }

  /** Gorev bitene (ya da onay/karar bekleyene) kadar yoklar; son durumu doner. */
  async bekle(id: string, sec: BekleSecenekleri = {}): Promise<Gorev> {
    const aralik = sec.aralikMs ?? 1000;
    const sinir = Date.now() + (sec.zamanAsimiMs ?? 24 * 3600 * 1000);
    const bitecek = sec.yalnizBitmis ? BITMIS : DURAN;
    let son = "";
    for (;;) {
      const g = await this.gorevDurumu(id);
      const imza = `${g.durum}|${g.adimlar.length}|${g.guncelleme}`;
      if (imza !== son) {
        son = imza;
        sec.degisince?.(g);
      }
      if (bitecek.includes(g.durum)) return g;
      if (Date.now() > sinir) throw new KairoHatasi("Bekleme suresi doldu.");
      await new Promise((tamam) => setTimeout(tamam, aralik));
    }
  }
}
