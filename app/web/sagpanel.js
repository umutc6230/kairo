// Sag panel (Claude Code Desktop gibi): proje dosya agaci, baglayicilar; alt durum cubugu.
import { ikon, ikonlariYerlestir } from "./ikonlar.js";
import { kacir } from "./md.js";
import { $, api, bildir, durum, el, modal } from "./ortak.js";

const PANEL_ANAHTAR = "kairo.sagPanel";

async function klasorCiz(kap, yol) {
  try {
    const { ogeler } = await api(`/api/proje/dosyalar?yol=${encodeURIComponent(yol)}`);
    kap.innerHTML = "";
    if (!ogeler.length) { kap.append(el('<span class="soluk kucuk">Boş</span>')); return; }
    for (const o of ogeler) {
      const tam = yol ? `${yol}/${o.ad}` : o.ad;
      const b = el(`<button class="oge" title="${kacir(tam)}">${ikon(o.klasor ? "klasor" : "dosya")}<span>${kacir(o.ad)}</span></button>`);
      kap.append(b);
      if (o.klasor) {
        const alt = el('<div class="alt" hidden></div>');
        kap.append(alt);
        b.onclick = () => {
          alt.hidden = !alt.hidden;
          if (!alt.hidden && !alt.childElementCount) klasorCiz(alt, tam);
        };
      } else {
        b.onclick = () => dosyaAc(tam);
      }
    }
  } catch (e) {
    kap.innerHTML = `<span class="soluk kucuk">${kacir(e.message)}</span>`;
  }
}

async function dosyaAc(yol) {
  try {
    const r = await api(`/api/proje/dosya?yol=${encodeURIComponent(yol)}`);
    const not = r.truncated ? `<div class="soluk kucuk">İlk ${r.satir_bitis} / ${r.toplam_satir} satır gösteriliyor.</div>` : "";
    modal({ baslik: r.goreli || yol, genis: true, icerik: `${not}<pre class="dosya-gorunum">${kacir(r.icerik)}</pre>`, dugmeler: [{ metin: "Kapat" }] });
  } catch (e) {
    bildir(e.message, "hata");
  }
}

export function dosyaAgaciniYenile() {
  const kap = $("#sp-agac");
  if (kap) klasorCiz(kap, "");
}

async function baglayicilariYenile() {
  try {
    const { sunucular } = await api("/api/mcp");
    const acik = sunucular.filter((s) => s.aktif !== false).length;
    const metin = sunucular.length ? `${acik}/${sunucular.length}` : "yok";
    $("#sp-baglayici").textContent = metin;
    $("#dc-baglayici").textContent = `Bağlayıcı: ${metin}`;
  } catch { /* sessiz */ }
}

export async function baglamYenile() {
  const yazi = $("#sp-baglam");
  if (!yazi) return;
  if (!durum.oturumId) { yazi.textContent = "-"; $("#sp-baglam-dolu").style.width = "0"; return; }
  try {
    const b = await api(`/api/oturumlar/${durum.oturumId}/baglam`);
    yazi.textContent = `%${b.yuzde}`;
    yazi.title = `~${b.kullanilan} / ${b.boyut} token`;
    $("#sp-baglam-dolu").style.width = `${b.yuzde}%`;
  } catch { /* sessiz */ }
}

async function uzakYenile() {
  try { $("#sp-uzak").checked = !!(await api("/api/uzak")).acik; } catch { /* sessiz */ }
}

function paneliAyarla(acik) {
  const p = $("#sag-panel");
  p.hidden = !acik;
  localStorage.setItem(PANEL_ANAHTAR, acik ? "1" : "0");
}

export function sagPanelKur({ baglayiciAc, ayarAc }) {
  $("#sp-ayar").onclick = ayarAc;
  $("#sp-baglam-satir").onclick = async () => {
    try {
      const y = await api("/api/model/yetenek");
      bildir(`${y.model}: bağlam ${y.baglam} token. ${$("#sp-baglam").title || ""}`, "bilgi", 3000);
    } catch (e) { bildir(e.message, "hata"); }
  };
  $("#sp-uzak").onchange = async (e) => {
    try {
      await api(e.target.checked ? "/api/uzak/ac" : "/api/uzak/kapat", { method: "POST" });
      bildir(e.target.checked ? "Uzak erişim açık. Telefonu eşlemek için /uzak kod yaz." : "Uzak erişim kapatıldı.", "basari", 2000);
    } catch (err) { bildir(err.message, "hata"); e.target.checked = !e.target.checked; }
  };
  uzakYenile();
  paneliAyarla(localStorage.getItem(PANEL_ANAHTAR) !== "0");
  $("#btn-sag-panel").onclick = () => paneliAyarla($("#sag-panel").hidden);
  $("#btn-dosyalar").onclick = () => { paneliAyarla(true); dosyaAgaciniYenile(); };
  $("#sp-dosya-yenile").onclick = dosyaAgaciniYenile;
  $("#sp-baglayici-baslik").onclick = baglayiciAc;
  ikonlariYerlestir(document.getElementById("kok"));
  dosyaAgaciniYenile();
  baglayicilariYenile();
  api("/api/bilgi").then((b) => { $("#dc-surum").textContent = `${b.urun} ${b.surum}`; }).catch(() => {});
  document.addEventListener("oturumlar-degisti", () => { dosyaAgaciniYenile(); baglamYenile(); }); // proje/sohbet degisince
}
