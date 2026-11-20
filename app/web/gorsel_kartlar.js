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

// KOPRU: kart yalniz `window.kairo.komut(k)` ile istek yollar. Ana sayfa: kaynak = kayitli kart
// iframe'i mi, tur beyaz listede mi, oran sinirinda mi bakar; her komut uygulama ici modalla
// kullaniciya sorulur, sunucuda PolitikaMotoru'ndan gecer. Sonuc yalniz o iframe'e doner.
const KOPRU = "<script>(()=>{let n=0;const b=new Map();addEventListener('message',e=>{const y=e.data&&e.data.kairoKopruYanit;if(e.source!==parent||!y||!b.has(y.id))return;b.get(y.id)(y);b.delete(y.id)});window.kairo={komut:k=>new Promise(r=>{const id=++n;b.set(id,r);parent.postMessage({kairoKopru:{id,tur:'komut',komut:String(k)}},'*')})}})()</script>";
export const KOPRU_TURLERI = new Set(["komut"]);
export const KOPRU_ARALIK_MS = 2000;

const iframeler = new Set();
const sonIstek = new WeakMap(); // iframe -> son istek zamani (oran siniri; ayni anda tek istek)

// Saf denetim (test edilir): gecerli istek mi? Gecersizse neden doner.
export function kopruDenetle(veri, kaynakVar, son, simdi) {
  if (!kaynakVar) return "kaynak";
  if (!veri || typeof veri !== "object" || !KOPRU_TURLERI.has(veri.tur)) return "tur";
  if (typeof veri.komut !== "string" || !veri.komut.trim() || veri.komut.length > 2000) return "komut";
  if (son && simdi - son < KOPRU_ARALIK_MS) return "oran";
  return "";
}

function kopruYanit(f, id, yanit) {
  f.contentWindow?.postMessage({ kairoKopruYanit: { id, ...yanit } }, "*");
}

async function kopruIstegi(f, veri) {
  const neden = kopruDenetle(veri, true, sonIstek.get(f), Date.now());
  if (neden) return kopruYanit(f, veri?.id, { ok: false, hata: neden === "oran" ? "Çok sık istek." : "Geçersiz istek." });
  sonIstek.set(f, Date.now() + 10 ** 9); // onay/calisma bitene kadar yeni istek yok
  const onay = await new Promise((coz) => {
    const g = el('<div><p>Bu mini uygulama bir komut çalıştırmak istiyor:</p><pre class="kart-komut"></pre></div>');
    g.querySelector("pre").textContent = veri.komut;
    modal({ baslik: f.title, icerik: g, kapaninca: () => coz(false), dugmeler: [
      { metin: "Reddet" },
      { metin: "Çalıştır", tur: "ana", eylem: (kapat) => { coz(true); kapat(); } },
    ] });
  });
  try {
    if (!onay) return kopruYanit(f, veri.id, { ok: false, hata: "Kullanıcı reddetti." });
    const s = await api("/api/kart-komut", { method: "POST", govde: { komut: veri.komut, onay: true } });
    kopruYanit(f, veri.id, { ok: s.cikis_kodu === 0 || s.cikis_kodu == null, cikti: s.cikti || "", cikis_kodu: s.cikis_kodu });
  } catch (e) {
    kopruYanit(f, veri.id, { ok: false, hata: e.message });
  } finally {
    sonIstek.set(f, Date.now());
  }
}

window.addEventListener("message", (e) => {
  let kaynak = null;
  for (const f of iframeler) {
    if (!f.isConnected) { iframeler.delete(f); continue; }
    if (f.contentWindow === e.source) kaynak = f;
  }
  if (!kaynak) return; // yabanci kaynak: yok sayilir
  if (e.data?.kairoKopru) { kopruIstegi(kaynak, e.data.kairoKopru); return; }
  const h = Number(e.data?.kairoYukseklik);
  if (h && !kaynak.dataset.sabit) kaynak.style.height = `${Math.min(Math.max(h, 60), 900)}px`;
});

function sandboxIframe(html, sabitYukseklik, baslik = "Mini arayüz") {
  const f = document.createElement("iframe");
  f.className = "arayuz-cerceve";
  f.setAttribute("sandbox", "allow-scripts");
  f.setAttribute("referrerpolicy", "no-referrer");
  f.title = baslik;
  if (sabitYukseklik) { f.dataset.sabit = "1"; f.style.height = sabitYukseklik; }
  f.srcdoc = onizlemeSrcdoc(TEMEL_STIL + KOPRU + html + YUKSEKLIK, CSP, "html");
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
  if (html) k.querySelector(".arayuz-govde").append(sandboxIframe(html, "", baslik));
  else k.querySelector(".arayuz-govde").append(el('<div class="soluk kucuk">Arayüz içeriği yok.</div>'));
  k.querySelector("[data-kopya]").onclick = () => kopyala(html);
  k.querySelector("[data-buyut]").onclick = () => {
    const g = el('<div class="arayuz-buyuk"></div>');
    g.append(sandboxIframe(html, "70vh", baslik));
    modal({ baslik, icerik: g, genis: true, dugmeler: [{ metin: "Kapat" }] });
  };
  ikonlariYerlestir(k);
  kap.append(k);
  return k;
}

const YEREL = /^http:\/\/(localhost|127\.0\.0\.1):\d{1,5}(\/[^\s"'<>]*)?$/;

const onizlemeIframe = (url, sinif) => `<iframe class="arayuz-cerceve ${sinif}" title="Önizleme" referrerpolicy="no-referrer" ${sinif.includes("kucuk") ? 'scrolling="no" tabindex="-1"' : ""}
  sandbox="allow-scripts allow-forms allow-same-origin allow-popups allow-modals" src="${kacir(url)}"></iframe>`;

export function onizlemeKarti(o, kap) {
  let s = {};
  try { s = JSON.parse(o.sonuc || "{}"); } catch { return null; }
  if (!s.url || !YEREL.test(s.url)) return null;
  const k = el(`<div class="arayuz-kart onizleme-kart" data-id="${kacir(o.id)}">
    <div class="arayuz-ust"><span class="canli-nokta" aria-hidden="true"></span><b>Önizleme</b><code class="soluk kucuk">${kacir(s.url)}</code><span class="dc-bosluk"></span>
      <button class="ikon-btn kucuk-ikon" data-yenile title="Yenile" aria-label="Yenile" data-ikon="yenile"></button>
      <button class="ikon-btn kucuk-ikon" data-buyut title="Büyüt" aria-label="Büyüt" data-ikon="kare"></button>
      <a class="ikon-btn kucuk-ikon" href="${kacir(s.url)}" target="_blank" rel="noopener" title="Tarayıcıda aç" aria-label="Tarayıcıda aç" data-ikon="dis"></a>
      ${s.is_id ? '<button class="btn kucuk" data-durdur>Durdur</button>' : ""}</div>
    <button class="onizleme-kucuk" title="Büyütmek için tıkla" aria-label="Önizlemeyi büyüt">${onizlemeIframe(s.url, "onizleme-cerceve kucuk")}</button></div>`);
  const f = k.querySelector("iframe");
  // kucuk resim: sayfa %50 olcekte, kaydirmasiz ve tiklanamaz; etkilesim buyutulmus pencerede
  const buyut = () => {
    const g = el(`<div class="arayuz-buyuk">${onizlemeIframe(s.url, "onizleme-cerceve")}</div>`);
    modal({ baslik: s.url, icerik: g, genis: true, dugmeler: [{ metin: "Kapat" }] });
  };
  k.querySelector(".onizleme-kucuk").onclick = buyut;
  k.querySelector("[data-buyut]").onclick = buyut;
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
