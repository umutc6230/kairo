// Review (/diff, /review) ve artifact onizleme (A5.4, A5.5).
// GUVENLIK: model/dosya metni kacir() ile basilir. HTML/SVG artifact YALNIZ
// <iframe sandbox="allow-scripts" srcdoc> icinde ve en basta kisitli CSP ile calisir:
// opak origin -> ust pencere, oturum anahtari, cerez/localStorage ve uygulama API'si erisilemez;
// connect-src 'none' -> ag istegi yok. allow-same-origin ASLA eklenmez.
import { ikonlariYerlestir } from "./ikonlar.js";
import { kacir, md } from "./md.js";
import { $, $$, api, bildir, el, modal, onayla } from "./ortak.js";

const ONEM_RENK = { kritik: "kirmizi", yuksek: "kirmizi", orta: "sari", dusuk: "" };
const KONUM_TR = {
  dogru: ["konum diff'te", "yesil"],
  dosya_diff_disi: ["dosya diff'te yok", "kirmizi"],
  satir_diff_disi: ["satır değişikliğin dışında", "sari"],
};

function diffHtml(metin) {
  return metin.split("\n").map((s) => {
    const sinif = s.startsWith("+") && !s.startsWith("+++") ? "diff-arti"
      : s.startsWith("-") && !s.startsWith("---") ? "diff-eksi"
        : s.startsWith("@@") ? "soluk" : "";
    return `<div class="${sinif}">${kacir(s) || "&nbsp;"}</div>`;
  }).join("");
}

export async function diffGoster() {
  try {
    const d = await api("/api/review/diff");
    const govde = d.diff?.trim()
      ? `<div class="diff">${diffHtml(d.diff)}</div>${d.truncated ? '<div class="uyari-kutu kucuk">Diff kesildi.</div>' : ""}`
      : `<div class="soluk">${kacir(d.hata || "Değişiklik yok (git diff boş). Yeni ve izlenmeyen dosyalar git diff'te görünmez.")}</div>`;
    modal({ baslik: "Çalışma ağacı diff'i", icerik: govde, genis: true, dugmeler: [{ metin: "Kapat" }] });
  } catch (e) { bildir(e.message, "hata"); }
}

function bulguHtml(b) {
  const [konum, renk] = KONUM_TR[b.konum] || [b.konum, ""];
  return `<div class="kart bulgu">
    <div class="kart-baslik"><b>${kacir(b.baslik)}</b>
      <span class="rozet ${ONEM_RENK[b.onem] || ""}">${kacir(b.onem)}</span></div>
    <div class="kucuk"><code>${kacir(b.dosya)}:${kacir(b.satir)}</code>
      <span class="rozet ${renk}">${kacir(konum)}</span>
      <span class="rozet sari" title="Model bulgusu; test/komut ile doğrulanmadı">model varsayımı</span>${b.gorus_sayisi > 1 ? ` <span class="rozet" title="Aynı modelin farklı odaklı geçişleri; bağımsız kanıt değildir">${kacir(b.gorus_sayisi)} geçişte (${kacir(b.odaklar.join(", "))})</span>` : ""}</div>
    <div><b class="kucuk">Neden:</b> ${kacir(b.neden)}</div>
    ${b.yeniden_uretme ? `<div><b class="kucuk">Yeniden üretme:</b> ${kacir(b.yeniden_uretme)}</div>` : ""}
    ${b.dogrulama_onerisi ? `<div><b class="kucuk">Doğrulama:</b> <code>${kacir(b.dogrulama_onerisi)}</code></div>` : ""}
  </div>`;
}

export async function reviewYap(derin = false) {
  const govde = el('<div class="diff-modal"><div class="parilti">Diff inceleniyor… (yerel modelde birkaç dakika sürebilir)</div></div>');
  const m = modal({ baslik: "Kod review", icerik: govde, genis: true, dugmeler: [{ metin: "Kapat" }] });
  try {
    const r = await api(`/api/review${derin ? "?derin=true" : ""}`, { method: "POST" });
    govde.innerHTML = `
      <div>${kacir(r.ozet)}</div>
      <div class="soluk kucuk">${kacir(r.dosyalar.length)} dosya · ${kacir(r.bulgular.length)} bulgu${r.review_md ? " · REVIEW.md kuralları uygulandı" : ""}${r.diff_kesildi ? " · diff kesildi" : ""}</div>
      <div class="uyari-kutu kucuk">Bulgular modelin değerlendirmesidir. "Konum diff'te" yalnız dosya/satırın gerçekten değiştiğini gösterir; hatanın doğruluğu önerilen test/komutla ayrıca doğrulanmalıdır.</div>
      ${r.bulgular.map(bulguHtml).join("") || '<div class="soluk">Bulgu yok.</div>'}`;
  } catch (e) {
    govde.innerHTML = `<div class="uyari-kutu">${kacir(e.message)}</div>`;
  }
  return m;
}

// ---------------- artifact ----------------
export function onizlemeSrcdoc(icerik, csp, tur) {
  // CSP EN BASTA: model HTML'i ikinci bir CSP ekleyebilir ama politikalar birlesir, gevsetemez.
  const meta = `<meta http-equiv="Content-Security-Policy" content="${kacir(csp)}">`;
  if (tur === "svg") return `<!doctype html><html><head>${meta}</head><body style="margin:0">${icerik}</body></html>`;
  return `<!doctype html><html><head>${meta}</head><body>${icerik}</body></html>`;
}

export async function artifactOnizle(id) {
  let a;
  try { a = await api(`/api/artifactler/${encodeURIComponent(id)}`); } catch (e) { bildir(e.message, "hata"); return; }
  const govde = el('<div class="artifact-onizleme"></div>');
  if (a.tur === "html" || a.tur === "svg") {
    const iframe = document.createElement("iframe");
    iframe.setAttribute("sandbox", "allow-scripts"); // allow-same-origin YOK: opak origin
    iframe.setAttribute("referrerpolicy", "no-referrer");
    iframe.setAttribute("title", `Artifact önizlemesi: ${a.ad}`);
    iframe.className = "artifact-cerceve";
    iframe.srcdoc = onizlemeSrcdoc(a.icerik, a.csp, a.tur);
    govde.append(iframe);
  } else if (a.tur === "md") {
    govde.innerHTML = `<div class="md">${md(a.icerik)}</div>`;
  } else {
    govde.innerHTML = `<pre class="adim-cikti">${kacir(a.icerik)}</pre>`;
  }
  modal({
    baslik: `${a.ad} (${a.tur})`,
    icerik: govde,
    genis: true,
    dugmeler: [
      { metin: "İndir", eylem: () => { artifactIndir(a); return true; } },
      { metin: "Kapat" },
    ],
  });
}

function artifactIndir(a) {
  const tip = { html: "text/html", svg: "image/svg+xml", json: "application/json", csv: "text/csv", md: "text/markdown" }[a.tur] || "text/plain";
  const url = URL.createObjectURL(new Blob([a.icerik], { type: `${tip};charset=utf-8` }));
  const link = Object.assign(document.createElement("a"), { href: url, download: `${a.ad}.${a.tur}` });
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function artifactListesiCiz(kap) {
  try {
    const { artifactler } = await api("/api/artifactler");
    kap.innerHTML = artifactler.slice().reverse().slice(0, 30).map((a) => `<li class="artifact-oge" data-art="${kacir(a.id)}">
      <span class="rozet">${kacir(a.tur)}</span><span class="gr-oge-hedef">${kacir(a.ad)}</span>
      <span class="soluk kucuk">${kacir(a.tarih.slice(5, 16).replace("T", " "))}</span>
      <button class="btn" data-is="onizle">Önizle</button><button class="ikon-btn" data-is="sil" title="Sil" aria-label="Artifact sil: ${kacir(a.ad)}" data-ikon="cop"></button></li>`).join("")
      || '<li class="soluk kucuk">Henüz artifact yok. Ajan rapor/HTML/SVG üretince burada görünür.</li>';
    ikonlariYerlestir(kap);
    $$("[data-art]", kap).forEach((li) => {
      $("[data-is=onizle]", li).onclick = () => artifactOnizle(li.dataset.art);
      $("[data-is=sil]", li).onclick = async () => {
        if (!(await onayla("Artifact sil", "Bu artifact kalıcı olarak silinsin mi?", { evet: "Sil", tehlike: true }))) return;
        try { await api(`/api/artifactler/${li.dataset.art}`, { method: "DELETE" }); artifactListesiCiz(kap); } catch (e) { bildir(e.message, "hata"); }
      };
    });
  } catch (e) {
    kap.innerHTML = `<li class="uyari-kutu kucuk">${kacir(e.message)}</li>`;
  }
}
