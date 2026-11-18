// Modeller sayfasi > Ollama: yuklu modeller (kullan/detay/sil), ollama.com aramasi, surum (etiket)
// secimi, bu PC'ye uyumluluk, indirme ilerlemesi. Hugging Face bolumunun Ollama karsiligi.
import { ikonlariYerlestir } from "./ikonlar.js";
import { kacir } from "./md.js";
import { $, api, bildir, durum, el, modal, onayla, sayi } from "./ortak.js";

const UYUM = {
  calisir: ["yesil", "✓ Bu PC'de çalışır"],
  zorlanir: ["sari", "⚠ Zorlanır"],
  calismaz: ["kirmizi", "✗ Çalışmaz"],
  bilinmiyor: ["", "? Bilinmiyor"],
};
const YET_TR = { tools: "araç", vision: "görsel", thinking: "düşünme", embedding: "embedding", cloud: "bulut", audio: "ses", completion: "metin" };
const arama = { sayfa: 1, liste: [], daha: false };
let yenile = async () => {};
let izleme = null;

export function ollamaKur(cb) {
  yenile = cb;
  $("#ol-ara-btn").onclick = () => ara();
  $("#ol-ara").onkeydown = (e) => { if (e.key === "Enter") ara(); };
  $("#ol-f-yetenek").onchange = () => ara();
  $("#ol-f-sira").onchange = () => ara();
  $("#ol-f-yerel").onchange = ciz;
  $("#ol-daha").onclick = () => ara(true);
}

export async function ollamaYukle() {
  await yukluYukle();
  indirmeleriIzle();
  if (!arama.liste.length) ara();
}

async function yukluYukle() {
  const kap = $("#ol-yuklu");
  let d;
  try { d = await api("/api/ollama/durum"); } catch { d = {}; }
  if (!d.kurulu && !d.calisiyor) {
    $("#ol-durum").innerHTML = '<span class="rozet kirmizi">kurulu değil</span>';
    kap.innerHTML = '<div class="bos-not soluk">Ollama bu bilgisayarda kurulu değil. <a href="https://ollama.com/download" target="_blank" rel="noopener">ollama.com/download</a> adresinden kur; arama yine çalışır.</div>';
    return;
  }
  $("#ol-durum").innerHTML = '<span class="parilti">Ollama başlatılıyor…</span>';
  let v;
  try { v = await api("/api/ollama/yuklu"); } catch (e) {
    $("#ol-durum").innerHTML = `<span class="rozet kirmizi">hata</span> ${kacir(e.message)}`;
    return;
  }
  const s = await api("/api/ollama/durum").catch(() => ({}));
  $("#ol-durum").innerHTML = `<span class="rozet yesil">çalışıyor</span> v${kacir(s.surum || "")} · ${v.modeller.length} model`;
  kap.innerHTML = v.modeller.length ? "" : '<div class="bos-not soluk">Ollama\'da yüklü model yok. Aşağıdan ara ve indir.</div>';
  for (const m of v.modeller) {
    const secili = durum.ayarlar.saglayici === "ollama" && durum.ayarlar.ollama_model === m.ad;
    const r = el(`<div class="skill-satir">
      <div class="skill-bilgi"><div class="ust"><b>${kacir(m.ad)}</b>
        ${m.acik ? '<span class="rozet yesil">açık</span>' : ""}${secili ? '<span class="rozet">seçili</span>' : ""}
        <span class="rozet">${sayi(m.boyut_gb)} GB</span>${m.parametre ? `<span class="rozet">${kacir(m.parametre)}</span>` : ""}
        ${m.niceleme ? `<span class="rozet">${kacir(m.niceleme)}</span>` : ""}</div>
        <div class="alt soluk">${kacir(m.aile)} · indirildi ${kacir(m.degisim)} · <code>ollama:${kacir(m.ad)}</code></div></div>
      <div class="skill-eylem">
        <button class="btn kucuk detay">Detay</button>
        ${secili ? "" : '<button class="btn kucuk ana kullan">Kullan</button>'}
        <button class="ikon-btn sil" title="Ollama'dan sil" data-ikon="cop"></button></div></div>`);
    r.querySelector(".kullan")?.addEventListener("click", async () => {
      try {
        await api("/api/ayarlar", { method: "PUT", govde: { saglayici: "ollama", ollama_model: m.ad } });
        bildir(`Model: ${m.ad} (Ollama)`, "basari");
      } catch (e) { bildir(e.message, "hata"); }
      await yenile();
      yukluYukle();
    });
    r.querySelector(".detay").onclick = () => detayGoster(m.ad);
    r.querySelector(".sil").onclick = async () => {
      if (!(await onayla("Modeli sil", `"${m.ad}" (${sayi(m.boyut_gb)} GB) Ollama'dan kalıcı olarak silinecek. Yeniden kullanmak için tekrar indirmen gerekir.`, { evet: "Sil", tehlike: true }))) return;
      try {
        await api(`/api/ollama/yuklu?ad=${encodeURIComponent(m.ad)}`, { method: "DELETE" });
        bildir("Model silindi", "basari");
      } catch (e) { bildir(e.message, "hata"); }
      await yenile();
      yukluYukle();
    };
    kap.append(r);
  }
  ikonlariYerlestir(kap);
}

async function detayGoster(ad) {
  const govde = el('<div class="proje-modal"><div class="parilti">Ayrıntılar alınıyor…</div></div>');
  modal({ baslik: ad, icerik: govde, genis: true });
  try {
    const d = await api(`/api/ollama/detay?ad=${encodeURIComponent(ad)}`);
    const a = d.ayrintilar || {};
    govde.innerHTML = `<div class="olcum-satiri">${d.yetenekler.map((y) => `<span class="rozet">${kacir(YET_TR[y] || y)}</span>`).join("")}</div>
      <div class="kutu"><div class="izin-satiri"><span class="soluk">Aile</span><span>${kacir(a.family || "")}</span></div>
      <div class="izin-satiri"><span class="soluk">Parametre</span><span>${kacir(a.parameter_size || "")}</span></div>
      <div class="izin-satiri"><span class="soluk">Niceleme</span><span>${kacir(a.quantization_level || "")}</span></div>
      <div class="izin-satiri"><span class="soluk">Biçim</span><span>${kacir(a.format || "")}</span></div>
      <div class="izin-satiri"><span class="soluk">Bağlam (model sınırı)</span><span>${d.baglam ? sayi(d.baglam, 0) : "?"} token</span></div>
      <div class="izin-satiri"><span class="soluk">Kairo'nun kullandığı bağlam</span><span>${sayi(durum.ayarlar.baglam_token, 0)} token</span></div></div>
      ${d.parametreler ? `<div class="kutu"><div class="kutu-baslik">Varsayılan parametreler</div><pre class="kucuk">${kacir(d.parametreler)}</pre></div>` : ""}
      ${d.lisans ? `<details class="kutu"><summary>Lisans</summary><pre class="kucuk" style="white-space:pre-wrap">${kacir(d.lisans)}</pre></details>` : ""}
      <a class="kucuk" href="https://ollama.com/library/${encodeURIComponent(ad.split(":")[0])}" target="_blank" rel="noopener">ollama.com'da aç</a>`;
  } catch (e) {
    govde.innerHTML = `<div class="hata-kutu">${kacir(e.message)}</div>`;
  }
}

async function ara(devam = false) {
  const kap = $("#ol-sonuclar");
  if (!devam) { arama.sayfa = 1; arama.liste = []; kap.innerHTML = ""; }
  $("#ol-daha").hidden = true;
  const bekle = el('<div class="bos-not"><span class="parilti">ollama.com\'dan yükleniyor…</span></div>');
  kap.after(bekle);
  const q = encodeURIComponent($("#ol-ara").value.trim());
  try {
    const v = await api(`/api/ollama/ara?q=${q}&sayfa=${arama.sayfa}&sira=${$("#ol-f-sira").value}&yetenek=${$("#ol-f-yetenek").value}`);
    const gorulen = new Set(arama.liste.map((x) => x.ad));
    arama.liste.push(...v.sonuclar.filter((x) => !gorulen.has(x.ad)));
    arama.daha = v.daha;
    arama.sayfa += 1;
  } catch (e) {
    kap.innerHTML = `<div class="hata-kutu">${kacir(e.message)}</div>`;
  } finally { bekle.remove(); }
  ciz();
}

function ciz() {
  const kap = $("#ol-sonuclar");
  const yerel = $("#ol-f-yerel").checked;
  // bulut modelleri Ollama hesabi ister ve bu PC'de calismaz; varsayilan gizli
  const liste = arama.liste.filter((a) => !yerel || !(a.yetenekler.includes("cloud") && !a.boyutlar.length));
  $("#ol-sayac").textContent = `${liste.length} / ${arama.liste.length} model`;
  $("#ol-daha").hidden = !arama.daha;
  kap.innerHTML = liste.length ? "" : '<div class="bos-not soluk">Sonuç yok.</div>';
  for (const a of liste) {
    const r = el(`<div class="skill-satir ol-aday">
      <div class="skill-bilgi"><div class="ust"><b>${kacir(a.ad)}</b>
        ${a.yetenekler.map((y) => `<span class="rozet">${kacir(YET_TR[y] || y)}</span>`).join("")}</div>
        <div class="alt soluk">${kacir(a.aciklama)}</div>
        <div class="olcum-satiri" style="margin-top:4px">
          ${a.boyutlar.map((b) => `<span class="rozet">${kacir(b)}</span>`).join("")}
          <span class="rozet">↓ ${sayi(a.indirme, 0)}</span>${a.etiket_sayisi ? `<span class="rozet">${a.etiket_sayisi} sürüm</span>` : ""}
          ${a.guncelleme ? `<span class="rozet">${kacir(a.guncelleme)}</span>` : ""}
          <a class="kucuk" href="https://ollama.com/library/${encodeURIComponent(a.ad)}" target="_blank" rel="noopener">ollama.com</a></div>
        <div class="ol-etiketler"></div></div>
      <div class="skill-eylem"><button class="btn kucuk ana">Sürümler</button></div></div>`);
    const b = r.querySelector("button");
    b.onclick = () => etiketleriGoster(a.ad, r.querySelector(".ol-etiketler"), b);
    kap.append(r);
  }
}

async function etiketleriGoster(ad, kutu, dugme) {
  if (kutu.childElementCount) { kutu.innerHTML = ""; dugme.textContent = "Sürümler"; return; }
  kutu.innerHTML = '<span class="parilti kucuk">Sürümler alınıyor…</span>';
  let v;
  try { v = await api(`/api/ollama/etiketler?ad=${encodeURIComponent(ad)}`); } catch (e) {
    kutu.innerHTML = `<div class="hata-kutu">${kacir(e.message)}</div>`;
    return;
  }
  dugme.textContent = "Gizle";
  kutu.innerHTML = v.etiketler.length ? "" : '<div class="soluk kucuk">Sürüm bulunamadı.</div>';
  for (const e of v.etiketler) {
    // MLX surumleri yalniz Apple Silicon'da calisir
    const uy = e.mlx ? { durum: "calismaz", neden: "MLX sürümü yalnız Apple Silicon (Mac) içindir." } : e.uyumluluk;
    const [renk, etiket] = UYUM[uy.durum] || UYUM.bilinmiyor;
    const engel = uy.durum === "calismaz" || uy.disk_yetmez;
    const r = el(`<div class="ol-etiket satir-arasi">
      <span><code>${kacir(e.tam_ad)}</code> <span class="rozet ${renk}" title="${kacir(uy.neden || "")}">${etiket}</span>
        ${e.boyut_gb ? `<span class="rozet">${sayi(e.boyut_gb)} GB</span>` : ""}${e.baglam ? `<span class="rozet">${kacir(e.baglam)} bağlam</span>` : ""}
        ${e.girdi ? `<span class="rozet">${kacir(e.girdi)}</span>` : ""}<span class="soluk kucuk">${kacir(e.guncelleme)}</span></span>
      <button class="btn kucuk ${engel ? "" : "ana"}" ${e.yuklu ? "disabled" : ""}>${e.yuklu ? "Yüklü" : "İndir"}</button></div>`);
    r.querySelector("button").onclick = () => indir(e, uy, engel);
    kutu.append(r);
  }
}

async function indir(e, uy, engel) {
  const metin = engel
    ? `${e.tam_ad} bu bilgisayarda büyük ihtimalle ÇALIŞMAZ (${uy.neden}). Yine de indirilsin mi?`
    : `${e.tam_ad} Ollama ile indirilecek (${e.boyut_gb ? `~${sayi(e.boyut_gb)} GB` : "boyut bilinmiyor"}).`;
  if (!(await onayla("Model indir", metin, { evet: "İndir", tehlike: engel }))) return;
  try {
    await api("/api/ollama/indir", { method: "POST", govde: { ad: e.tam_ad } });
    bildir("İndirme başladı", "basari");
    indirmeleriIzle();
  } catch (err) { bildir(err.message, "hata", 8000); }
}

function indirmeleriIzle() {
  if (izleme) return;
  const tur = async () => {
    let liste = [];
    try { liste = await api("/api/ollama/indirmeler"); } catch { /* sessiz */ }
    const kap = $("#ol-indirmeler");
    kap.innerHTML = "";
    let suren = false;
    for (const i of liste.slice().reverse()) {
      suren ||= ["bekliyor", "iniyor"].includes(i.durum);
      const etiket = { bekliyor: "bekliyor", iniyor: i.asama || "iniyor", bitti: "bitti", hata: "hata", iptal: "iptal edildi" }[i.durum];
      const r = el(`<div class="indirme"><div class="satir-arasi"><b>${kacir(i.ad)}</b>
        <span class="soluk kucuk">${kacir(etiket)}${i.toplam ? ` · ${sayi(i.inen / 1024 ** 3)} / ${sayi(i.toplam / 1024 ** 3)} GB` : ""}${i.hiz ? ` · ${sayi(i.hiz / 1024 ** 2)} MB/sn` : ""}${i.kalan_sn ? ` · ~${Math.ceil(i.kalan_sn / 60)} dk` : ""}</span>
        ${["bekliyor", "iniyor"].includes(i.durum) ? '<button class="btn kucuk tehlike">İptal</button>' : ""}</div>
        <div class="ilerleme"><div style="width:${i.yuzde}%" class="${i.durum === "hata" ? "hata" : ""}"></div></div>
        ${i.hata ? `<div class="hata-kutu">${kacir(i.hata)}</div>` : ""}</div>`);
      r.querySelector("button")?.addEventListener("click", () => api(`/api/ollama/indirmeler/${i.id}/iptal`, { method: "POST" }));
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
