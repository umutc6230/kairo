// Oturum durumu (calisiyor / onay bekliyor / hata) ve sabitlenmis oturumlar.
// Kenar cubugu ve Ctrl+K oturum degistirici ortak kullanir.
import { api } from "./ortak.js";

const CALISAN = new Set(["calisiyor", "sirada"]);
const ONAY = new Set(["onay_bekliyor", "cevap_bekliyor", "duraklatildi"]);
const HATA = new Set(["basarisiz"]);

let onbellek = { zaman: 0, harita: new Map() };

// run id -> durum; 3 sn onbellek (liste her yenilemede tekrar istemesin)
export async function gorevDurumlari(zorla = false) {
  if (!zorla && Date.now() - onbellek.zaman < 3000) return onbellek.harita;
  try {
    const v = await api("/api/gorevler");
    onbellek = { zaman: Date.now(), harita: new Map((v.gorevler || []).map((r) => [r.id, r.durum])) };
  } catch { /* sunucu yoksa eski harita */ }
  return onbellek.harita;
}

export function oturumDurumu(o, harita) {
  if (o.akista) return "calisiyor";
  const d = o.son_run ? harita.get(o.son_run) : "";
  if (CALISAN.has(d)) return "calisiyor";
  if (ONAY.has(d)) return "onay";
  if (HATA.has(d)) return "hata";
  return "";
}

export const DURUM_ETIKET = { calisiyor: "Çalışıyor", onay: "Onay bekliyor", hata: "Hata" };

// shortcut: sabitler tarayici deposunda (tek kullanicili masaustu); cihazlar arasi gerekirse sunucuya tasi
const ANAHTAR = "kairo-sabit-oturumlar";
export function sabitler() {
  try { return new Set(JSON.parse(localStorage.getItem(ANAHTAR) || "[]")); } catch { return new Set(); }
}
export function sabitDegistir(id) {
  const s = sabitler();
  s[s.has(id) ? "delete" : "add"](id);
  try { localStorage.setItem(ANAHTAR, JSON.stringify([...s])); } catch { /* depolama kapali */ }
  return s.has(id);
}

export function goreceliZaman(iso) {
  const dk = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (dk < 1) return "şimdi";
  if (dk < 60) return `${dk} dk`;
  const sa = Math.round(dk / 60);
  return sa < 24 ? `${sa} sa` : `${Math.round(sa / 24)} g`;
}
