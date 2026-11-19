// Arayuz cevirisi: kaynak metinler Turkce kalir; dil "en" ise en.json sozluguyle DOM cevrilir.
// Sozluk: tam eslesme {"Ayarlar": "Settings"} + sablon {"{0} adım": "{0} steps"}.
const ATLA = ".mesaj.kullanici, .md, .dusunce-icerik, pre, code, [contenteditable], .terminal, .xterm, [data-cevirme]";
const OZELLIKLER = ["title", "placeholder", "aria-label", "alt"];
let tam = null;
let sablonlar = [];

export const dil = () => (tam ? "en" : "tr");

// Yazili kod icin (DOM disi metinler, or. Windows bildirimi)
export function t(metin) {
  if (!tam || typeof metin !== "string") return metin;
  const s = metin.replace(/\s+/g, " ").trim(); // anahtarlar tek bosluklu
  if (!s) return metin;
  let c = tam[s];
  if (c === undefined) {
    for (const [re, hedef] of sablonlar) {
      const m = s.match(re);
      if (m) { c = hedef.replace(/\{(\d+)\}/g, (_, i) => t(m[+i + 1])); break; }
    }
  }
  if (!c) return metin; // yok ya da bos ceviri
  const [, bas, son] = metin.match(/^(\s*)[\s\S]*?(\s*)$/);
  return bas + c + son;
}

const kacisli = (x) => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function sablonDerle(sozluk) {
  return Object.entries(sozluk)
    .filter(([k]) => /\{\d+\}/.test(k))
    .map(([k, v]) => {
      // {1} ile baslayan anahtar olabilir: yer tutucuyu regex grup sirasina esle
      const sira = [...k.matchAll(/\{(\d+)\}/g)].map((x) => x[1]);
      const hedef = v.replace(/\{(\d+)\}/g, (_, i) => `{${sira.indexOf(i)}}`);
      return [new RegExp("^" + k.split(/\{\d+\}/).map(kacisli).join("(.+?)") + "$", "s"), hedef];
    })
    .sort((a, b) => b[0].source.length - a[0].source.length); // uzun (ozel) sablon once
}

function dugumCevir(n) {
  if (n.nodeType === 3) {
    const p = n.parentElement;
    if (!p || p.closest(ATLA)) return;
    const c = t(n.nodeValue);
    if (c !== n.nodeValue) n.nodeValue = c;
    return;
  }
  if (n.nodeType !== 1 || n.matches(ATLA)) return;
  if (n.dataset.en) { n.textContent = n.dataset.en; return; } // ayni Turkce kelimenin farkli anlami (Açık: On / Light)
  for (const o of OZELLIKLER) {
    const v = n.getAttribute(o);
    if (v) { const c = t(v); if (c !== v) n.setAttribute(o, c); }
  }
  if (n.tagName !== "TEXTAREA") n.childNodes.forEach(dugumCevir); // kullanicinin yazdigi metne dokunma
}

export async function dilKur(secilen) {
  try { localStorage.setItem("kairo-dil", secilen); } catch { /* gizli pencere */ }
  if (secilen !== "en" || tam) return;
  try {
    tam = window.KAIRO_EN || (await (await fetch("/web/en.json")).json()); // uzak.html sozlugu gomulu verir
  } catch { return; } // sozluk yoksa Turkce kalir
  sablonlar = sablonDerle(tam);
  document.documentElement.lang = "en";
  document.title = t(document.title);
  dugumCevir(document.body);
  const baslik = document.querySelector("title");
  if (baslik) new MutationObserver(() => { const c = t(document.title); if (c !== document.title) document.title = c; }).observe(baslik, { childList: true });
  new MutationObserver((kayitlar) => {
    for (const k of kayitlar) {
      if (k.type === "childList") k.addedNodes.forEach(dugumCevir);
      else if (k.type === "characterData") dugumCevir(k.target);
      else dugumCevir(k.target);
    }
  }).observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: OZELLIKLER });
}

// Ilk boyamada Turkce gorunmesin diye son secim hemen uygulanir; asil kaynak ayarlardir.
if (window.KAIRO_EN) dilKur("en");
else try { if (localStorage.getItem("kairo-dil") === "en") dilKur("en"); } catch { /* yok */ }
