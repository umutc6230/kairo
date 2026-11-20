// Mesaj kutusuna yapistirilan API anahtarlari: kutuda ve sohbet balonunda maskeli gorunur,
// gonderirken sir kasasina alinir (bkz. anahtarCoz).
import { api } from "./ortak.js";

const ANAHTAR = /\b(sk-or-v1-[A-Za-z0-9]{20,}|sk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|xox[abpr]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|ck_[A-Za-z0-9]{20,}|\d{8,10}:[A-Za-z0-9_-]{35})\b/g;
const saklanan = new Map(); // yer tutucu -> gercek anahtar

export const maske = (s) => `${s.slice(0, 6)}…${s.slice(-4)}`;

export function maskele(metin) {
  return String(metin || "").replace(ANAHTAR, maske);
}

/** Yapistirma: anahtar varsa kutuya maskeli yer tutucu yazar; true = islendi. */
export function anahtarYapistir(e, alan) {
  const metin = e.clipboardData?.getData("text") || "";
  if (!ANAHTAR.test(metin)) return false;
  ANAHTAR.lastIndex = 0;
  e.preventDefault();
  const yeni = metin.replace(ANAHTAR, (k) => {
    const tutucu = `⟦${maske(k)}⟧`;
    saklanan.set(tutucu, k);
    return tutucu;
  });
  alan.setRangeText(yeni, alan.selectionStart, alan.selectionEnd, "end");
  alan.dispatchEvent(new Event("input"));
  return true;
}

/** Gonderim: slash komutunda gercek deger; sohbette anahtar sifreli kasaya girer, mesaja
 * yalniz adi ($GITHUB_TOKEN) gider. Model degeri hic gormez; komutlarda ortam degiskenidir. */
export async function anahtarCoz(metin) {
  let s = metin;
  const komut = s.startsWith("/");
  for (const [t, k] of saklanan) {
    if (!s.includes(t)) continue;
    const yerine = komut ? k : "$" + (await api("/api/sirlar", { method: "POST", govde: { deger: k } })).ad;
    s = s.split(t).join(yerine);
  }
  return s;
}
