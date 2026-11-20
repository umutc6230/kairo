// Sohbet ici kartlar: mini arayuz (arayuz_goster) ve dev sunucu onizlemesi (onizleme_baslat).
// GUVENLIK: model HTML'i YALNIZ sandbox="allow-scripts" srcdoc + CSP ile calisir (inceleme.js):
// opak origin, ag yok, ust pencereye/oturum anahtarina erisim yok. allow-same-origin EKLENMEZ.
// Onizleme yalniz localhost adresini acar (farkli origin; uygulamanin API'sine erisemez).
import { ikonlariYerlestir } from "./ikonlar.js";
import { onizlemeSrcdoc } from "./inceleme.js";
import { kacir } from "./md.js";
import { api, bildir, el, modal } from "./ortak.js";

async function kopyala(metin) {
  try { await navigator.clipboard.writeText(metin || ""); bildir("Kopyalandı", "basari", 1500); } catch { bildir("Kopyalanamadı", "hata"); }
}

const CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; media-src data: blob:";
// iframe yuksekligini icerige gore ayarlar (yalniz sayi gonderir)
const YUKSEKLIK = "<script>(()=>{const g=()=>parent.postMessage({kairoYukseklik:document.documentElement.scrollHeight},'*');new ResizeObserver(g).observe(document.documentElement);addEventListener('load',g);g();[150,500,1500].forEach(t=>setTimeout(g,t))})()</script>";
const TEMEL_STIL = "<style>html{color-scheme:dark}body{margin:0;padding:12px;font:14px 'Segoe UI',system-ui,sans-serif;color:#ecebe7;background:transparent}</style>";

const iframeler = new Set();
window.addEventListener("message", (e) => {
  const h = Number(e.data?.kairoYukseklik);
  if (!h) return;
  for (const f of iframeler) {
    if (!f.isConnected) { iframeler.delete(f); continue; }
    if (f.contentWindow === e.source && !f.dataset.sabit) f.style.height = `${Math.min(Math.max(h, 60), 900)}px`;
  }
});

function sandboxIframe(html, sabitYukseklik) {
  const f = document.createElement("iframe");
  f.className = "arayuz-cerceve";
  f.setAttribute("sandbox", "allow-scripts");
  f.setAttribute("referrerpolicy", "no-referrer");
  f.title = "Mini arayüz";
  if (sabitYukseklik) { f.dataset.sabit = "1"; f.style.height = sabitYukseklik; }
  f.srcdoc = onizlemeSrcdoc(TEMEL_STIL + html + YUKSEKLIK, CSP, "html");
  iframeler.add(f);
  return f;
}

export function arayuzKarti(o, kap) {
  const { baslik = "Arayüz", html = "" } = o.argumanlar || {};
  const k = el(`<div class="arayuz-kart" data-id="${kacir(o.id)}">
    <div class="arayuz-ust"><span class="arayuz-baslik" data-ikon="ekran"></span><b>${kacir(baslik)}</b><span class="dc-bosluk"></span>
      <button class="ikon-btn kucuk-ikon" data-kopya title="HTML'i kopyala" aria-label="HTML'i kopyala" data-ikon="kopyala"></button>
      <button class="ikon-btn kucuk-ikon" data-buyut title="Büyüt" aria-label="Büyüt" data-ikon="kare"></button></div>
    <div class="arayuz-govde"></div></div>`);
  if (html) k.querySelector(".arayuz-govde").append(sandboxIframe(html));
  else k.querySelector(".arayuz-govde").append(el('<div class="soluk kucuk">Arayüz içeriği yok.</div>'));
  k.querySelector("[data-kopya]").onclick = () => kopyala(html);
  k.querySelector("[data-buyut]").onclick = () => {
    const g = el('<div class="arayuz-buyuk"></div>');
    g.append(sandboxIframe(html, "70vh"));
    modal({ baslik, icerik: g, genis: true, dugmeler: [{ metin: "Kapat" }] });
  };
  ikonlariYerlestir(k);
  kap.append(k);
  return k;
}

const YEREL = /^http:\/\/(localhost|127\.0\.0\.1):\d{1,5}(\/[^\s"'<>]*)?$/;

export function onizlemeKarti(o, kap) {
  let s = {};
  try { s = JSON.parse(o.sonuc || "{}"); } catch { return null; }
  if (!s.url || !YEREL.test(s.url)) return null;
  const k = el(`<div class="arayuz-kart onizleme-kart" data-id="${kacir(o.id)}">
    <div class="arayuz-ust"><span class="canli-nokta" aria-hidden="true"></span><b>Önizleme</b><code class="soluk kucuk">${kacir(s.url)}</code><span class="dc-bosluk"></span>
      <button class="ikon-btn kucuk-ikon" data-yenile title="Yenile" aria-label="Yenile" data-ikon="yenile"></button>
      <a class="ikon-btn kucuk-ikon" href="${kacir(s.url)}" target="_blank" rel="noopener" title="Tarayıcıda aç" aria-label="Tarayıcıda aç" data-ikon="dis"></a>
      ${s.is_id ? '<button class="btn kucuk" data-durdur>Durdur</button>' : ""}</div>
    <div class="arayuz-govde"><iframe class="arayuz-cerceve onizleme-cerceve" title="Önizleme" referrerpolicy="no-referrer"
      sandbox="allow-scripts allow-forms allow-same-origin allow-popups allow-modals" src="${kacir(s.url)}"></iframe></div></div>`);
  const f = k.querySelector("iframe");
  k.querySelector("[data-yenile]").onclick = () => { f.src = s.url; };
  const d = k.querySelector("[data-durdur]");
  if (d) d.onclick = async () => {
    try {
      await api(`/api/komutlar/${encodeURIComponent(s.is_id)}/durdur`, { method: "POST", govde: {} });
      k.classList.add("durdu");
      d.disabled = true;
      d.textContent = "Durduruldu";
    } catch (e) { bildir(e.message, "hata"); }
  };
  ikonlariYerlestir(k);
  kap.append(k);
  return k;
}
