// Uzantilar (A7.6): ayri surecte calisan eklentiler. Panel HTML'i sandbox iframe + CSP ile;
// uzanti metni kacir() ile basilir.
import { kacir } from "./md.js";
import { onizlemeSrcdoc } from "./inceleme.js";
import { $, $$, api, bildir, el, modal, onayla } from "./ortak.js";

let komutlar = [];

let pluginKomutlari = [];

export async function uzantiKomutlariniYukle() {
  try { pluginKomutlari = (await api("/api/pluginler/komutlar")).komutlar; } catch { pluginKomutlari = []; }
  try { komutlar = (await api("/api/uzantilar")).komutlar.map((k) => k.komut); } catch { komutlar = []; }
}

/** Ozel (proje/kullanici .claude/commands) ve plugin komutlari; "/" onerileri icin. */
export const ozelKomutListesi = () => pluginKomutlari;

/** Claude Code plugin komutu (/plugin:komut ya da /komut): govde genisletilip MESAJ olarak gider. */
export function pluginKomutuMu(ad, arg, gonder) {
  const k = ad.replace(/^\//, "");
  if (!pluginKomutlari.some((x) => x.komut === k || x.kisa === k)) return false;
  api("/api/pluginler/komut", { method: "POST", govde: { komut: k, arg } })
    .then((r) => gonder(r.istem))
    .catch((e) => bildir(e.message, "hata"));
  return true;
}

/** /<uzanti-komutu> arg -> uzantida calisir, sonucu pencerede gosterir. */
export function uzantiKomutuMu(ad, arg) {
  const k = ad.replace(/^\//, "").toLowerCase();
  if (!komutlar.includes(k)) return false;
  api("/api/uzantilar/komut", { method: "POST", govde: { komut: k, arg } })
    .then((r) => modal({ baslik: `/${k} (${r.uzanti})`, icerik: `<pre class="adim-cikti">${kacir(r.metin)}</pre>`, dugmeler: [{ metin: "Kapat" }] }))
    .catch((e) => bildir(e.message, "hata"));
  return true;
}

export async function uzantiPaneli(ad) {
  try {
    const p = await api(`/api/uzantilar/${encodeURIComponent(ad)}/panel`);
    const f = document.createElement("iframe");
    f.setAttribute("sandbox", "allow-scripts"); // allow-same-origin YOK: opak origin
    f.setAttribute("referrerpolicy", "no-referrer");
    f.setAttribute("title", `Uzantı paneli: ${ad}`);
    f.className = "artifact-cerceve";
    f.srcdoc = onizlemeSrcdoc(p.html, p.csp, "html");
    const g = el("<div></div>");
    g.append(f);
    modal({ baslik: `Uzantı: ${ad}`, icerik: g, genis: true, dugmeler: [{ metin: "Kapat" }] });
  } catch (e) { bildir(e.message, "hata"); }
}

export function uzantiSekmesiKur(govde) {
  const kap = $("#uz-liste", govde);
  const ciz = async () => {
    try {
      const { uzantilar } = await api("/api/uzantilar");
      kap.innerHTML = uzantilar.map((u) => `<div class="secenek-kart ${u.acik ? "" : "pasif"}" data-uz="${kacir(u.ad)}">
        <div style="flex:1"><div class="ust"><b>${kacir(u.ad)}</b> <span class="rozet">v${kacir(u.surum)}</span>
          ${u.yetenekler.map((y) => `<span class="rozet">${kacir(y)}</span>`).join(" ")}</div>
          <div class="alt">${kacir(u.description)}${u.komutlar.length ? ` · komutlar: ${kacir(u.komutlar.map((k) => "/" + k).join(" "))}` : ""}${u.araclar.length ? ` · araçlar (her zaman onay): ${kacir(u.araclar.join(", "))}` : ""}</div></div>
        ${u.yetenekler.includes("panel") && u.acik ? '<button class="btn" data-is="panel">Panel</button>' : ""}
        <button class="btn" data-is="ac">${u.acik ? "Kapat" : "Aç"}</button><button class="btn tehlike" data-is="sil">Kaldır</button></div>`).join("")
        || '<div class="ayar-not">Kurulu uzantı yok.</div>';
      $$("[data-uz]", kap).forEach((kart) => {
        const ad = kart.dataset.uz;
        const u = uzantilar.find((x) => x.ad === ad);
        $$("[data-is]", kart).forEach((b) => {
          b.onclick = async () => {
            try {
              if (b.dataset.is === "panel") { uzantiPaneli(ad); return; }
              if (b.dataset.is === "sil") {
                if (!(await onayla("Uzantıyı kaldır", `${ad} kaldırılsın mı?`, { evet: "Kaldır", tehlike: true }))) return;
                await api(`/api/uzantilar/${ad}`, { method: "DELETE" });
              } else {
                await api(`/api/uzantilar/${ad}/durum`, { method: "PUT", govde: { acik: !u.acik } });
              }
              await uzantiKomutlariniYukle();
              ciz();
            } catch (err) { bildir(err.message, "hata"); }
          };
        });
      });
    } catch (err) { kap.innerHTML = `<span class="rozet kirmizi">hata</span> ${kacir(err.message)}`; }
  };
  $("#uz-incele", govde).onclick = async () => {
    const rapor = $("#uz-rapor", govde);
    try {
      const k = await api("/api/uzantilar/karantina", { method: "POST", govde: { yol: $("#uz-yol", govde).value.trim() } });
      const r = k.rapor;
      const m = k.manifest;
      rapor.innerHTML = `<div class="kart"><div class="kart-baslik"><b>${kacir(m.name)} v${kacir(m.version)}</b><span class="soluk kucuk">${kacir(r.dosya_sayisi)} dosya</span></div>
        <div>${kacir(m.description)}</div>
        <div class="soluk kucuk">İlan ettiği yetenekler: ${kacir(m.yetenekler.join(", "))}. Ayrı süreçte çalışır; dosyalarına, anahtarlarına ve uygulamaya doğrudan erişemez. Araç çağrıları her seferinde onay ister.</div>
        ${r.riskler.length ? `<div class="uyari-kutu kucuk"><b>Dikkat:</b><ul>${r.riskler.map((x) => `<li><code>${kacir(x.dosya)}</code> ${kacir(x.neden)}</li>`).join("")}</ul></div>` : '<div class="soluk kucuk">Bilinen riskli desen bulunmadı (güvenlik garantisi değildir).</div>'}
        <div class="dugme-sira"><button class="btn ana" id="uz-kur">İnceledim, kur</button></div></div>`;
      $("#uz-kur", rapor).onclick = async () => {
        try { await api("/api/uzantilar/kur", { method: "POST", govde: { ad: k.karantina } }); rapor.innerHTML = ""; await uzantiKomutlariniYukle(); ciz(); bildir("Uzantı kuruldu.", "basari", 1500); } catch (err) { bildir(err.message, "hata"); }
      };
    } catch (err) { rapor.innerHTML = `<div class="uyari-kutu kucuk">${kacir(err.message)}</div>`; }
  };
  ciz();
}
