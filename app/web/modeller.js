// Modeller sayfasi: yuklu modeller, Hugging Face aramasi, uyumluluk gostergesi, indirme/silme.
import { ikonlariYerlestir } from "./ikonlar.js";
import { kacir } from "./md.js";
import { $, api, bildir, durum, el, onayla, sayi } from "./ortak.js";

const UYUM = {
  calisir: ["yesil", "✓ Bu PC'de çalışır"],
  zorlanir: ["sari", "⚠ Zorlanır"],
  calismaz: ["kirmizi", "✗ Çalışmaz"],
  bilinmiyor: ["", "? Bilinmiyor"],
};
let yenile = async () => {};
let izleme = null;

export function modellerKur(cb) {
  yenile = cb;
  $("#m-ara-btn").onclick = () => ara($("#m-ara").value);
  $("#m-ara").onkeydown = (e) => { if (e.key === "Enter") ara($("#m-ara").value); };
  $("#m-gorsel").onchange = () => ara($("#m-ara").value);
  document.querySelectorAll("#m-hazir .ornek").forEach((b) => {
    b.onclick = () => { $("#m-ara").value = b.dataset.q; ara(b.dataset.q); };
  });
}

export async function modelSayfasiYukle() {
  await yukluYukle();
  indirmeleriIzle();
  if (!$("#m-sonuclar").children.length) ara($("#m-ara").value || "heretic");
}

function sistemCiz(s) {
  $("#m-sistem").innerHTML = `
    <span class="rozet">RAM: ${sayi(s.bos_ram_gb)} / ${sayi(s.toplam_ram_gb, 0)} GB boş</span>
    <span class="rozet ${s.disk_bos_gb != null && s.disk_bos_gb < 10 ? "sari" : ""}">Disk: ${sayi(s.disk_bos_gb)} GB boş</span>
    <span class="soluk kucuk">Model klasörü: ${kacir(s.model_klasoru)}</span>`;
}

function aciklama(m) {
  // hazir gelen modellerin Turkce aciklamasi durum.sunucu'da (ortak.js turkcelestir)
  return durum.sunucu?.modeller?.find((x) => x.anahtar === m.anahtar)?.aciklama || m.aciklama;
}

async function yukluYukle() {
  let v;
  try { v = await api("/api/magaza/yuklu"); } catch (e) { bildir(e.message, "hata"); return; }
  sistemCiz(v.sistem);
  const kap = $("#m-yuklu");
  kap.innerHTML = "";
  const liste = v.modeller.filter((m) => m.dosya_var);  // silinen hazir modeller listede kalmasin
  if (!liste.length) kap.innerHTML = `<div class="bos-not soluk">Yüklü model yok. Aşağıdan indir.</div>`;
  for (const m of liste) {
    const secili = durum.ayarlar.model === m.anahtar;
    const r = el(`<div class="skill-satir ${m.dosya_var ? "" : "kapali"}">
      <div class="skill-bilgi"><div class="ust"><b>${kacir(m.ad)}</b>
        ${m.acik ? '<span class="rozet yesil">açık</span>' : ""}${secili ? '<span class="rozet">seçili</span>' : ""}
        ${m.yerlesik ? '<span class="rozet">hazır gelen</span>' : '<span class="rozet yesil">indirilen</span>'}
        <span class="rozet">${m.dosya_var ? `${sayi(m.boyut_gb)} GB` : "dosya yok"}</span>
        ${m.gorsel ? '<span class="rozet">resim/OCR</span>' : ""}${m.ses ? '<span class="rozet">ses</span>' : ""}</div>
        <div class="alt soluk">${kacir(aciklama(m))} · <code>${kacir(m.anahtar)}</code></div></div>
      <div class="skill-eylem">
        ${m.dosya_var && !secili ? '<button class="btn kucuk kullan">Kullan</button>' : ""}
        ${m.dosya_var ? '<button class="ikon-btn sil" title="Dosyalarını sil" data-ikon="cop"></button>' : ""}
      </div></div>`);
    r.querySelector(".kullan")?.addEventListener("click", async () => {
      await api("/api/ayarlar", { method: "PUT", govde: { model: m.anahtar } }).catch((e) => bildir(e.message, "hata"));
      await yenile();
      yukluYukle();
    });
    r.querySelector(".sil")?.addEventListener("click", () => modelSil(m));
    kap.append(r);
  }
  ikonlariYerlestir(kap);
}

export async function modelSil(m) {
  const metin = `"${m.ad}" dosyaları${m.boyut_gb ? ` (${sayi(m.boyut_gb)} GB)` : ""} bu bilgisayardan kalıcı olarak silinecek.${m.acik ? " Model şu an açık; önce kapatılacak." : ""}${m.yerlesik ? " Yeniden kullanmak için tekrar indirmen gerekir." : ""}`;
  if (!(await onayla("Modeli sil", metin, { evet: "Sil", tehlike: true }))) return false;
  try {
    await api(`/api/magaza/yuklu/${encodeURIComponent(m.anahtar)}`, { method: "DELETE" });
    bildir("Model silindi", "basari");
  } catch (e) { bildir(e.message, "hata"); }
  await yenile();
  if ($("#m-yuklu")) yukluYukle();
  return true;
}

async function ara(sorgu) {
  const kap = $("#m-sonuclar");
  kap.innerHTML = `<div class="bos-not"><span class="parilti">Hugging Face'te aranıyor…</span></div>`;
  let v;
  try {
    v = await api(`/api/magaza/ara?q=${encodeURIComponent(sorgu || "heretic")}&gorsel=${$("#m-gorsel").checked}`);
  } catch (e) {
    kap.innerHTML = `<div class="hata-kutu">${kacir(e.message)}</div>`;
    return;
  }
  sistemCiz(v.sistem);
  kap.innerHTML = v.sonuclar.length ? "" : `<div class="bos-not soluk">Sonuç yok.</div>`;
  for (const a of v.sonuclar) {
    const [renk, etiket] = UYUM[a.uyumluluk.durum] || UYUM.bilinmiyor;
    const engel = a.uyumluluk.durum === "calismaz" || a.uyumluluk.disk_yetmez;
    const r = el(`<div class="skill-satir">
      <div class="skill-bilgi"><div class="ust"><b>${kacir(a.ad)}</b><span class="rozet ${renk}">${etiket}</span>
        ${a.uyumluluk.disk_yetmez ? '<span class="rozet kirmizi">disk yetmez</span>' : ""}
        ${a.uyumluluk.durum !== "calismaz" && a.uyumluluk.simdi_acilir === false ? '<span class="rozet sari">şu an RAM az</span>' : ""}
        ${a.yuklu ? '<span class="rozet yesil">yüklü</span>' : ""}</div>
        <div class="alt soluk">${kacir(a.uyumluluk.neden || "")}</div>
        <div class="olcum-satiri" style="margin-top:4px">
          ${a.parametre_milyar ? `<span class="rozet">${sayi(a.parametre_milyar)}B parametre</span>` : ""}
          ${a.tahmini_gb ? `<span class="rozet">~${sayi(a.tahmini_gb)} GB</span>` : ""}
          ${a.gorsel ? '<span class="rozet">resim/OCR</span>' : '<span class="rozet">yalnız metin</span>'}
          ${a.arac ? '<span class="rozet">araç</span>' : ""}
          <span class="rozet">↓ ${sayi(a.indirme, 0)}</span><span class="rozet">♥ ${sayi(a.begeni, 0)}</span>
          <span class="rozet">${kacir(a.guncelleme)}</span>
          <a class="kucuk" href="https://huggingface.co/${kacir(a.repo)}" target="_blank" rel="noopener">${kacir(a.repo)}</a></div></div>
      <div class="skill-eylem"><button class="btn kucuk ${engel ? "" : "ana"}" ${a.yuklu || a.uyumluluk.disk_yetmez ? "disabled" : ""}>${a.yuklu ? "Yüklü" : "İndir"}</button></div></div>`);
    r.querySelector("button").onclick = () => indir(a, engel);
    kap.append(r);
  }
}

async function indir(a, engel) {
  const uyari = engel
    ? `Bu model bu bilgisayarda büyük ihtimalle ÇALIŞMAZ (${a.uyumluluk.neden}). Yine de indirilsin mi?`
    : `${a.repo} indirilecek (~${sayi(a.tahmini_gb)} GB). Topluluk yüklemesidir; dosya SHA256 ile doğrulanır, hiçbir şey çalıştırılmaz.`;
  if (!(await onayla("Model indir", uyari, { evet: "İndir", tehlike: engel }))) return;
  try {
    await api("/api/magaza/indir", { method: "POST", govde: { repo: a.repo } });
    bildir("İndirme başladı", "basari");
    indirmeleriIzle();
  } catch (e) { bildir(e.message, "hata", 8000); }
}

function indirmeleriIzle() {
  if (izleme) return;
  const tur = async () => {
    let liste = [];
    try { liste = await api("/api/magaza/indirmeler"); } catch { /* sessiz */ }
    const kap = $("#m-indirmeler");
    kap.parentElement.hidden = !liste.length;
    kap.innerHTML = "";
    let suren = false;
    for (const i of liste.slice().reverse()) {
      suren ||= ["bekliyor", "iniyor", "dogrulaniyor"].includes(i.durum);
      const etiket = { bekliyor: "bekliyor", iniyor: "iniyor", dogrulaniyor: "SHA256 doğrulanıyor", bitti: "bitti", hata: "hata", iptal: "iptal edildi" }[i.durum];
      const r = el(`<div class="indirme"><div class="satir-arasi"><b>${kacir(i.repo)}</b>
        <span class="soluk kucuk">${etiket} · ${sayi(i.inen / 1024 ** 3)} / ${sayi(i.toplam / 1024 ** 3)} GB${i.hiz ? ` · ${sayi(i.hiz / 1024 ** 2)} MB/sn` : ""}${i.kalan_sn ? ` · ~${Math.ceil(i.kalan_sn / 60)} dk` : ""}</span>
        ${["bekliyor", "iniyor"].includes(i.durum) ? '<button class="btn kucuk tehlike">İptal</button>' : ""}</div>
        <div class="ilerleme"><div style="width:${i.yuzde}%" class="${i.durum === "hata" ? "hata" : ""}"></div></div>
        ${i.hata ? `<div class="hata-kutu">${kacir(i.hata)}</div>` : ""}</div>`);
      r.querySelector("button")?.addEventListener("click", () => api(`/api/magaza/indirmeler/${i.id}/iptal`, { method: "POST" }));
      kap.append(r);
    }
    if (!suren) {
      clearInterval(izleme);
      izleme = null;
      if (liste.some((i) => i.durum === "bitti")) { await yenile(); yukluYukle(); }
    }
  };
  tur();
  izleme = setInterval(tur, 1000);
}
