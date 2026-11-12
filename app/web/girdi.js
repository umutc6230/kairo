// Yazma alani yardimcilari (Claude Code girdi kisayollari): "/" ile komut, "@" ile proje dosyasi
// tamamlama. Dis metin (dosya adi, komut aciklamasi) DAIMA kacir() ile basilir.
import { kacir } from "./md.js";
import { $, api, el } from "./ortak.js";
import { projeDurumu } from "./proje.js";

let kutu = null;
let ogeler = []; // {etiket, aciklama, deger, klasor}
let secili = 0;
let aralik = null; // {bas, son}: girdide degistirilecek parca
let komutKaynagi = () => [];
let sira = 0; // gec gelen dosya listesi yeni sorguyu ezmesin
const klasorOnbellek = new Map();

export function girdiYardimKur(komutlar) {
  komutKaynagi = komutlar;
  const g = $("#girdi");
  g.addEventListener("input", oneriGuncelle);
  g.addEventListener("click", oneriGuncelle);
  g.addEventListener("blur", () => setTimeout(kapat, 150)); // tiklama secimi kacmasin
}

function kapat() {
  kutu?.remove();
  kutu = null;
  ogeler = [];
  aralik = null;
}

function sirala(liste, aranan, ad) {
  const q = aranan.toLowerCase();
  const bas = liste.filter((x) => ad(x).toLowerCase().startsWith(q));
  const icinde = liste.filter((x) => !ad(x).toLowerCase().startsWith(q) && ad(x).toLowerCase().includes(q));
  return [...bas, ...icinde];
}

async function klasorOku(yol) {
  if (klasorOnbellek.has(yol)) return klasorOnbellek.get(yol);
  const r = await api(`/api/proje/dosyalar?yol=${encodeURIComponent(yol)}`);
  klasorOnbellek.set(yol, r.ogeler);
  setTimeout(() => klasorOnbellek.delete(yol), 15000); // yeni dosyalar gorunsun
  return r.ogeler;
}

export async function oneriGuncelle() {
  const g = $("#girdi");
  const imlec = g.selectionStart ?? g.value.length;
  const once = g.value.slice(0, imlec);
  const benim = ++sira;
  const komut = /^\/[^\s]*$/.exec(once);
  if (komut) {
    const liste = sirala(komutKaynagi(), once, (k) => k.ad).slice(0, 40);
    return goster(liste.map((k) => ({ etiket: k.ad, aciklama: k.aciklama || "", deger: `${k.ad} ` })), { bas: 0, son: imlec });
  }
  const dosya = /(^|\s)@([^\s@]*)$/.exec(once);
  if (dosya && projeDurumu.aktif) {
    const yazilan = dosya[2];
    const kesme = yazilan.lastIndexOf("/");
    const klasor = kesme >= 0 ? yazilan.slice(0, kesme) : "";
    const onEk = yazilan.slice(kesme + 1);
    let liste = [];
    try { liste = await klasorOku(klasor); } catch { liste = []; }
    if (benim !== sira) return undefined;
    const taban = klasor ? `${klasor}/` : "";
    const secenek = sirala(liste, onEk, (o) => o.ad).slice(0, 40).map((o) => ({
      etiket: `${o.ad}${o.klasor ? "/" : ""}`, aciklama: o.klasor ? "klasör" : "", klasor: o.klasor,
      deger: `@${taban}${o.ad}${o.klasor ? "/" : " "}`,
    }));
    return goster(secenek, { bas: imlec - yazilan.length - 1, son: imlec });
  }
  return kapat();
}

function goster(liste, yeniAralik) {
  if (!liste.length) return kapat();
  ogeler = liste;
  aralik = yeniAralik;
  secili = 0;
  if (!kutu) {
    kutu = el('<div class="oneri-kutu" role="listbox" aria-label="Öneriler"></div>');
    $("#yazma").append(kutu);
  }
  kutu.innerHTML = ogeler.map((o, i) => `<button class="oneri" role="option" data-i="${i}" tabindex="-1">
    <span class="oneri-ad">${kacir(o.etiket)}</span><span class="oneri-aciklama">${kacir(o.aciklama)}</span></button>`).join("");
  kutu.querySelectorAll(".oneri").forEach((b) => {
    b.onmousedown = (e) => { e.preventDefault(); sec(Number(b.dataset.i)); }; // odak girdide kalsin
  });
  return isaretle();
}

function isaretle() {
  kutu?.querySelectorAll(".oneri").forEach((b, i) => {
    b.classList.toggle("secili", i === secili);
    b.setAttribute("aria-selected", String(i === secili));
    if (i === secili) b.scrollIntoView({ block: "nearest" });
  });
}

function sec(i) {
  const o = ogeler[i];
  if (!o || !aralik) return;
  const g = $("#girdi");
  g.value = g.value.slice(0, aralik.bas) + o.deger + g.value.slice(aralik.son);
  const yer = aralik.bas + o.deger.length;
  g.setSelectionRange(yer, yer);
  g.focus();
  kapat();
  g.dispatchEvent(new Event("input")); // boyut + gonder dugmesi; klasor secildiyse alt liste acilir
}

/** Girdi keydown'unda ILK cagrilir; true donerse tus oneriler icin kullanilmistir (gonderilmez). */
export function oneriTusu(e) {
  if (!kutu || !ogeler.length) return false;
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    secili = (secili + (e.key === "ArrowDown" ? 1 : ogeler.length - 1)) % ogeler.length;
    isaretle();
  } else if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey && !e.isComposing)) {
    // tam yazilmis komutta Enter = calistir (Claude Code gibi); aksi halde tamamla
    const g = $("#girdi");
    if (e.key === "Enter" && ogeler[secili].deger.trim() === g.value.trim()) { kapat(); return false; }
    sec(secili);
  } else if (e.key === "Escape") {
    kapat();
  } else return false;
  e.preventDefault();
  e.stopPropagation();
  return true;
}
