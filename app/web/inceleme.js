// Review (/diff, /review) ve sandbox onizleme srcdoc'u (A5.4; uzanti panelleri kullanir).
// GUVENLIK: model/dosya metni kacir() ile basilir. Uzanti paneli HTML'i YALNIZ
// <iframe sandbox="allow-scripts" srcdoc> icinde ve en basta kisitli CSP ile calisir:
// opak origin -> ust pencere, oturum anahtari, cerez/localStorage ve uygulama API'si erisilemez;
// connect-src 'none' -> ag istegi yok. allow-same-origin ASLA eklenmez.
import { kacir } from "./md.js";
import { api, bildir, el, modal } from "./ortak.js";

const ONEM_RENK = { kritik: "kirmizi", yuksek: "kirmizi", orta: "sari", dusuk: "" };
const KONUM_TR = {
  dogru: ["konum diff'te", "yesil"],
  dosya_diff_disi: ["dosya diff'te yok", "kirmizi"],
  satir_diff_disi: ["satır değişikliğin dışında", "sari"],
};

export function diffHtml(metin) {
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

// ---------------- sandbox onizleme (uzanti panelleri) ----------------
export function onizlemeSrcdoc(icerik, csp, tur) {
  // CSP EN BASTA: model HTML'i ikinci bir CSP ekleyebilir ama politikalar birlesir, gevsetemez.
  const meta = `<meta http-equiv="Content-Security-Policy" content="${kacir(csp)}">`;
  if (tur === "svg") return `<!doctype html><html><head>${meta}</head><body style="margin:0">${icerik}</body></html>`;
  return `<!doctype html><html><head>${meta}</head><body>${icerik}</body></html>`;
}
