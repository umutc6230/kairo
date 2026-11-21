// Eklentiler: Claude Desktop "Plugins" sayfasi gibi tek yer. Bagli bagliyicilar, skill'ler,
// Claude Code plugin'leri ve Composio uygulamalari; arama, filtre, "Ekle" menusu, Populer katalog.
// Baglanma: OAuth sunucusu ve Composio uygulamasi icin tarayicida o uygulamanin onay sayfasi acilir.
import { ikonlariYerlestir } from "./ikonlar.js";
import { kacir } from "./md.js";
import { $, $$, api, baglayiciDurumu, bildir, el, menuAc, modal, onayla } from "./ortak.js";
import { ayarlarAc } from "./ayarlar.js";
import { githubBaglan } from "./ayarlar2.js";

let filtre = "hepsi";
let arama = "";
let veri = { mcp: [], dizin: [], skiller: [], pluginler: [], composio: { bagli: false }, uygulamalar: [] };
let composioArama = "";
const acik = { yuklu: false, populer: false }; // "Tumunu goster"
const SINIR = { yuklu: 6, populer: 10 };

const RENKLER = ["#d97757", "#2bb6a8", "#6a8fd8", "#c7a14a", "#a36ad8", "#d86a8f", "#5aa86a"];
function avatar(ad, logo) {
  if (logo) return `<img class="ek-logo" src="${kacir(logo)}" alt="" loading="lazy" referrerpolicy="no-referrer">`;
  const r = RENKLER[[...ad].reduce((t, c) => t + c.charCodeAt(0), 0) % RENKLER.length];
  return `<span class="ek-logo harf" style="background:${r}">${kacir((ad[0] || "?").toUpperCase())}</span>`;
}

// Resmi uzak MCP sunucusu olmayan (ya da otomatik kayda izin vermeyen) populer uygulamalar
const COMPOSIO_ONERI = [
  { slug: "gmail", ad: "Gmail", aciklama: "E-posta oku, ara, taslak yaz ve gönder." },
  { slug: "googledrive", ad: "Google Drive", aciklama: "Dosya ara, oku ve yükle." },
  { slug: "googlecalendar", ad: "Google Takvim", aciklama: "Etkinlikleri gör ve oluştur." },
  { slug: "googlesheets", ad: "Google E-Tablolar", aciklama: "Tablo oku ve güncelle." },
  { slug: "googledocs", ad: "Google Dokümanlar", aciklama: "Doküman oku ve düzenle." },
  { slug: "slack", ad: "Slack", aciklama: "Kanal ve mesajlar." },
  { slug: "hubspot", ad: "HubSpot", aciklama: "CRM kişi ve anlaşmaları." },
  { slug: "outlook", ad: "Outlook", aciklama: "Microsoft e-posta ve takvim." },
  { slug: "trello", ad: "Trello", aciklama: "Pano ve kartlar." },
];

const TUR_ADI ={ baglayici: "Bağlayıcı", skill: "Skill", plugin: "Plugin", uygulama: "Uygulama" };

function satir(o) {
  return `<div class="ek-satir" data-anahtar="${kacir(o.anahtar)}">
    ${avatar(o.ad, o.logo)}
    <div class="ek-govde"><div class="ek-ad">${kacir(o.ad)}${o.dogrulanmis ? ' <span class="ek-tik" data-ikon="tik" title="Doğrulanmış"></span>' : ""}</div>
      <div class="ek-alt soluk">${kacir(TUR_ADI[o.tur] || o.tur)} · ${kacir(o.kaynak || "")}</div></div>
    ${o.durum ? `<span class="rozet ek-durum ${o.durumSinif || ""}" title="${kacir(o.ipucu || o.durum)}">${kacir(o.durum)}</span>` : ""}
    <button class="ikon-btn" data-ikon="daha" title="Seçenekler" data-menu></button></div>`;
}

function kart(o) {
  return `<div class="ek-kart" data-anahtar="${kacir(o.anahtar)}">
    ${avatar(o.ad, o.logo)}
    <div class="ek-govde"><div class="ek-ad">${kacir(o.ad)}${o.dogrulanmis ? ' <span class="ek-tik" data-ikon="tik"></span>' : ""}</div>
      <div class="ek-aciklama">${kacir(o.aciklama || "")}</div>
      <div class="ek-alt soluk">${kacir(TUR_ADI[o.tur] || o.tur)} · ${kacir(o.kaynak || "")}</div></div>
    <button class="btn kucuk" data-baglan>${kacir(o.eylemAdi || "Bağlan")}</button></div>`;
}

// ---- veri -> ortak oge bicimi ----
const urlHost = (u) => { try { return u ? new URL(u).host : ""; } catch { return u || ""; } };
function yukluOgeler() {
  const l = [];
  // sorun once (giris gerekli, baglanamadi), sonra baglaniyor, bagli, kapali
  const SIRA = { giris: 0, hata: 1, baglaniyor: 2, bagli: 3, kapali: 4 };
  for (const s of veri.mcp) {
    const d = baglayiciDurumu(s);
    l.push({ anahtar: `mcp:${s.ad}`, tur: "baglayici", ad: s.ad,
      kaynak: s.ek ? (s.ad === "composio" ? "Composio" : "plugin ile geldi") : s.uzak ? (urlHost(s.url) || "uzak") : (s.komut || "yerel"),
      durum: d.etiket, durumSinif: d.sinif, ipucu: d.ipucu, kod: d.kod, oncelik: SIRA[d.kod] ?? 2,
      ham: s, dogrulanmis: veri.dizin.some((x) => x.ad === s.ad) });
  }
  l.sort((a, b) => a.oncelik - b.oncelik);
  for (const u of veri.uygulamalar.filter((x) => x.bagli)) {
    l.push({ anahtar: `cmp:${u.slug}`, tur: "uygulama", ad: u.ad, logo: u.logo, kaynak: "Composio", durum: "Bağlı", durumSinif: "yesil", kod: "bagli", ham: u, dogrulanmis: true });
  }
  const acikKapali = (acik) => (acik ? { durum: "Açık", durumSinif: "yesil", kod: "bagli" } : { durum: "Kapalı", durumSinif: "", kod: "kapali" });
  for (const p of veri.pluginler) {
    l.push({ anahtar: `plg:${p.ad}`, tur: "plugin", ad: p.ad, kaynak: p.kaynak || (p.aktif ? `v${p.aktif}` : "") || p.surum || "plugin", ...acikKapali(p.acik !== false), ham: p });
  }
  for (const s of veri.skiller) {
    l.push({ anahtar: `skl:${s.ad}`, tur: "skill", ad: s.ad, kaynak: s.kaynak === "claude" ? "Claude Code" : s.kaynak === "brain" ? "Brain" : s.kaynak === "yerlesik" ? "Yerleşik" : s.kaynak || "Kairo", ...acikKapali(s.acik), ham: s });
  }
  return l;
}

function populerOgeler() {
  const var_ = new Set(veri.mcp.map((s) => s.ad));
  const l = veri.dizin.filter((d) => !var_.has(d.ad)).map((d) => ({
    anahtar: `dzn:${d.ad}`, tur: "baglayici", ad: d.baslik, aciklama: d.aciklama, kaynak: d.url ? urlHost(d.url) : d.komut, ham: d,
    dogrulanmis: true, eylemAdi: d.oauth || d.ad === "github" ? "Bağlan" : "Ekle",
  }));
  for (const u of veri.uygulamalar.filter((x) => !x.bagli)) {
    l.push({ anahtar: `cmp:${u.slug}`, tur: "uygulama", ad: u.ad, logo: u.logo, aciklama: u.aciklama, kaynak: "Composio", ham: u, dogrulanmis: true, eylemAdi: "Bağlan" });
  }
  // Composio bagli degilken Google vb. uygulamalar yine gorunsun; Bagla once Composio anahtarini ister
  // Connect (ck_) anahtarinda katalog yok: populer liste gorunur, Baglan dogrudan Composio'ya gider
  const connect = veri.composio.tur === "connect";
  if (!veri.composio.bagli || connect) {
    const once = COMPOSIO_ONERI.map((u) => ({ anahtar: `cmo:${u.slug}`, tur: "uygulama", ad: u.ad, aciklama: u.aciklama,
      kaynak: "Composio ile", ham: u, dogrulanmis: true, eylemAdi: "Bağlan", composioGerekli: !connect }));
    l.unshift(...once);
  }
  return l;
}

const FILTRE_TUR = { hepsi: null, baglayici: ["baglayici", "uygulama"], skill: ["skill"], plugin: ["plugin"] };
function suz(l) {
  const t = FILTRE_TUR[filtre];
  const a = arama.toLocaleLowerCase("tr");
  return l.filter((o) => (!t || t.includes(o.tur)) && (!a || `${o.ad} ${o.aciklama || ""} ${o.kaynak || ""}`.toLocaleLowerCase("tr").includes(a)));
}

// ---- eylemler ----
async function dizindenEkle(d) {
  if (d.ad === "github") { await githubBaglan(); return yukle(); }
  const deger = d.argumanlar?.some((x) => x.includes("{klasor}")) ? await klasorSor() : null;
  if (d.argumanlar?.some((x) => x.includes("{klasor}")) && !deger) return;
  const govde = d.url ? { ad: d.ad, url: d.url } : { ad: d.ad, komut: d.komut, argumanlar: d.argumanlar.map((x) => x.replace("{klasor}", deger)) };
  await api("/api/mcp", { method: "POST", govde });
  if (d.oauth) {
    await api(`/api/mcp/${d.ad}/oauth`, { method: "POST" });
    bildir(`${d.baslik}: tarayıcıda giriş sayfası açıldı. Onaylayınca bağlantı hazır.`, "bilgi", 6000);
  } else {
    try { const t = await api(`/api/mcp/${d.ad}/test`, { method: "POST" }); bildir(`${d.baslik} eklendi (${(t.araclar || []).length} araç).`, "basari", 3000); } catch (e) { bildir(`${d.baslik} eklendi ama bağlanamadı: ${e.message}`, "uyari", 6000); }
  }
}

function klasorSor() {
  return new Promise((ok) => {
    let cozuldu = false;
    const bitir = (v) => { if (!cozuldu) { cozuldu = true; ok(v); } };
    const g = el(`<div><label class="proje-alan">Klasör yolu<input class="alan" id="ek-klasor" placeholder="C:\\Users\\..."></label></div>`);
    modal({ baslik: "Klasör seç", icerik: g, kapaninca: () => bitir(null), dugmeler: [
      { metin: "İptal", eylem: (k) => { bitir(null); k(); } },
      { metin: "Ekle", tur: "ana", eylem: (k) => { bitir($("#ek-klasor", g).value.trim() || null); k(); } },
    ] });
  });
}

async function composioBaglan(u) {
  const r = await api(`/api/composio/baglan/${encodeURIComponent(u.slug)}`, { method: "POST" });
  bildir(`${u.ad}: tarayıcıda onay sayfası açıldı. Onaylayınca "Yenile"ye bas.`, "bilgi", 7000);
  return r;
}

function composioAnahtarModali() {
  const g = el(`<div>
    <p class="soluk">Composio ile Gmail, Slack, Google Drive/Sheets/Docs, Jira, HubSpot gibi 250+ uygulamaya tek tıkla bağlanırsın: "Bağlan"a basınca o uygulamanın kendi onay sayfası tarayıcıda açılır. Erişim anahtarları Composio'da kalır; Kairo'ya ve modele gelmez. Ücretsiz katman vardır; çağrılar Composio sunucularından geçer.</p>
    <p class="soluk kucuk">İki tür anahtar çalışır, Kairo hangisi olduğunu kendisi anlar:</p>
    <ul class="soluk kucuk"><li><b>Kişisel (önerilen):</b> <a href="https://dashboard.composio.dev" target="_blank" rel="noopener">dashboard.composio.dev</a> > For You > Sessions &amp; API Key. <code>ck_</code> ile başlar.</li>
    <li><b>Proje (geliştirici):</b> Platform > Settings > API Keys. Genelde <code>ak_</code> ile başlar.</li></ul>
    <input class="alan" id="cmp-anahtar" type="password" placeholder="Composio anahtarı (ck_... ya da proje anahtarı)" autocomplete="off"></div>`);
  modal({ baslik: "Composio'yu bağla", icerik: g, dugmeler: [
    { metin: "İptal" },
    { metin: "Kaydet", tur: "ana", eylem: async (k, b) => {
      b.disabled = true;
      try { await api("/api/composio/anahtar", { method: "POST", govde: { anahtar: $("#cmp-anahtar", g).value } }); bildir("Composio bağlandı.", "basari", 2500); k(); yukle(); } catch (e) { bildir(e.message, "hata", 6000); b.disabled = false; }
    } },
  ] });
}

function ekleMenusu(capa) {
  menuAc(capa, [
    { metin: "Bağlayıcı (URL ya da komut)", ikon: "arti", eylem: () => ayarlarAc("mcp") },
    { metin: veri.composio.bagli ? "Composio anahtarını değiştir" : "Composio ile uygulama bağla", ikon: "anahtar", eylem: composioAnahtarModali },
    { metin: "Claude Code / Desktop'tan içe aktar", ikon: "klasor", eylem: () => ayarlarAc("mcp") },
    { metin: "Plugin yükle (git, marketplace)", ikon: "model", eylem: () => ayarlarAc("plugin") },
    { metin: "Skill oluştur / düzenle", ikon: "sihir", eylem: skillSayfasinaGit },
  ], { sagaHizali: true });
}

let gitFn = () => {};
function skillSayfasinaGit() { gitFn({ tur: "skiller" }); }

function ogeMenusu(capa, o) {
  const s = o.ham;
  const ogeler = [];
  if (o.tur === "baglayici" && s.ek) {
    ogeler.push({ metin: "Bağlantıyı dene", ikon: "oynat", eylem: async () => { const t = await api(`/api/mcp/${s.ad}/test`, { method: "POST" }); bildir(`${s.ad}: ${(t.araclar || []).length} araç.`, "basari", 3000); yukle(); } });
    ogeler.push({ metin: s.ad === "composio" ? "Composio anahtarını değiştir" : "Plugin ayarları", ikon: "disli", eylem: () => (s.ad === "composio" ? composioAnahtarModali() : ayarlarAc("plugin")) });
  } else if (o.tur === "baglayici") {
    if (s.uzak && /githubcopilot|github\.com/.test(s.url || "")) ogeler.push({ metin: "GitHub ile giriş yap", ikon: "anahtar", eylem: async () => { await githubBaglan(); yukle(); } });
    else if (s.uzak) ogeler.push({ metin: s.oauth?.bagli ? "Yeniden giriş yap" : "Tarayıcıda giriş yap", ikon: "anahtar", eylem: async () => { await api(`/api/mcp/${s.ad}/oauth`, { method: "POST" }); bildir("Tarayıcıda giriş sayfası açıldı.", "bilgi", 5000); } });
    ogeler.push({ metin: "Bağlantıyı dene", ikon: "oynat", eylem: async () => { const t = await api(`/api/mcp/${s.ad}/test`, { method: "POST" }); bildir(`${s.ad}: ${(t.araclar || []).length} araç.`, "basari", 3000); yukle(); } });
    ogeler.push({ metin: s.aktif ? "Kapat" : "Aç", ikon: "guc", eylem: async () => { await api(`/api/mcp/${s.ad}`, { method: "PUT", govde: { aktif: !s.aktif } }); yukle(); } });
    ogeler.push({ metin: "Araçlar ve ayrıntılar", ikon: "disli", eylem: () => ayarlarAc("mcp") });
    ogeler.push("ayrac", { metin: "Kaldır", ikon: "cop", tehlike: true, eylem: async () => { if (await onayla("Bağlayıcıyı kaldır", `${s.ad} kaldırılsın mı?`, { evet: "Kaldır", tehlike: true })) { await api(`/api/mcp/${s.ad}`, { method: "DELETE" }); yukle(); } } });
  } else if (o.tur === "uygulama") {
    ogeler.push({ metin: "Yeniden bağlan", ikon: "anahtar", eylem: () => composioBaglan(s) });
    ogeler.push("ayrac", { metin: "Bağlantıyı kes", ikon: "cop", tehlike: true, eylem: async () => { if (await onayla("Bağlantıyı kes", `${s.ad} bağlantısı kesilsin mi?`, { evet: "Kes", tehlike: true })) { await api(`/api/composio/baglanti/${s.baglanti}`, { method: "DELETE" }); yukle(); } } });
  } else if (o.tur === "skill") {
    ogeler.push({ metin: s.acik ? "Kapat" : "Aç", ikon: "guc", eylem: async () => { await api(`/api/skiller/${encodeURIComponent(s.ad)}/durum`, { method: "PUT", govde: { acik: !s.acik } }); yukle(); } });
    ogeler.push({ metin: "Skill sayfasında aç", ikon: "dosya", eylem: skillSayfasinaGit });
  } else if (o.tur === "plugin") {
    ogeler.push({ metin: s.acik === false ? "Aç" : "Kapat", ikon: "guc", eylem: async () => { await api(`/api/pluginler/${encodeURIComponent(s.ad)}/durum`, { method: "PUT", govde: { acik: s.acik === false } }); yukle(); } });
    ogeler.push({ metin: "Plugin ayarları", ikon: "disli", eylem: () => ayarlarAc("plugin") });
  }
  menuAc(capa, ogeler.map((x) => (typeof x === "string" ? x : { ...x, eylem: async () => { try { await x.eylem(); } catch (e) { bildir(e.message, "hata", 6000); } } })), { sagaHizali: true });
}

// ---- cizim ----
// arama/filtre varken hepsi gosterilir; yoksa ilk N + "Tumunu goster"
const kes = (b, l) => (acik[b] || arama || filtre !== "hepsi" ? l : l.slice(0, SINIR[b]));
const tumu = (b, n) => (n > SINIR[b] && !arama && filtre === "hepsi"
  ? `<button class="ek-tumu" data-tumu="${b}">${acik[b] ? "Daha az" : "Tümünü göster"} <span data-ikon="sag"></span></button>` : "");
function ciz() {
  const kap = $("#ek-icerik");
  if (!kap) return;
  const yuklu = suz(yukluOgeler());
  const populer = suz(populerOgeler());
  const composioKart = !veri.composio.bagli && (filtre === "hepsi" || filtre === "baglayici") ? `<div class="ek-tanitim">
      <div><b>250+ uygulamaya tek tıkla bağlan</b><div class="soluk kucuk">Gmail, Slack, Google Drive, Sheets, Docs, Jira, HubSpot, Trello... Composio ile "Bağlan"a bas, uygulamanın onay sayfasında izin ver.</div></div>
      <button class="btn ana kucuk" id="ek-composio">Composio'yu bağla</button></div>` : "";
  const say = (k) => yuklu.filter((o) => o.tur !== "skill" && o.tur !== "plugin" && o.kod === k).length;
  const ozet = [["bagli", "bağlı", "yesil"], ["giris", "giriş gerekli", "sari"], ["hata", "bağlanamadı", "kirmizi"], ["baglaniyor", "bağlanıyor", "mavi"]]
    .map(([k, ad, sinif]) => [say(k), ad, sinif]).filter(([n]) => n)
    .map(([n, ad, sinif]) => `<span class="rozet ${sinif}">${n} ${ad}</span>`).join(" ");
  kap.innerHTML = `
    <div class="ek-bolum-baslik"><b>Senin eklentilerin <span class="soluk kucuk">${yuklu.length}</span></b><span class="ek-ozet">${ozet}</span>${tumu("yuklu", yuklu.length)}</div>
    <div class="ek-liste">${kes("yuklu", yuklu).map(satir).join("") || '<div class="soluk kucuk">Eşleşen eklenti yok.</div>'}</div>
    ${composioKart}
    <div class="ek-bolum-baslik"><b>Popüler</b><span class="ek-sag">${tumu("populer", populer.length)}${veri.composio.bagli ? `<input class="alan kucuk-alan" id="ek-cmp-ara" placeholder="Composio'da uygulama ara" value="${kacir(composioArama)}">` : ""}</span></div>
    <div class="ek-izgara">${kes("populer", populer).map(kart).join("") || '<div class="soluk kucuk">Eşleşen yok.</div>'}</div>`;
  ikonlariYerlestir(kap);
  $$("[data-tumu]", kap).forEach((b) => { b.onclick = () => { acik[b.dataset.tumu] = !acik[b.dataset.tumu]; ciz(); }; });
  const bul = (a) => [...yukluOgeler(), ...populerOgeler()].find((o) => o.anahtar === a);
  $$(".ek-satir [data-menu]", kap).forEach((b) => { b.onclick = (e) => ogeMenusu(e.currentTarget, bul(b.closest("[data-anahtar]").dataset.anahtar)); });
  $$(".ek-kart [data-baglan]", kap).forEach((b) => {
    b.onclick = async () => {
      const o = bul(b.closest("[data-anahtar]").dataset.anahtar);
      b.disabled = true;
      if (o.composioGerekli) { b.disabled = false; bildir(`${o.ad} Composio üzerinden bağlanır; önce Composio anahtarını ekle.`, "bilgi", 6000); composioAnahtarModali(); return; }
      try { if (o.tur === "uygulama") await composioBaglan(o.ham); else await dizindenEkle(o.ham); await yukle(); } catch (e) { bildir(e.message, "hata", 6000); } finally { b.disabled = false; }
    };
  });
  $("#ek-composio", kap)?.addEventListener("click", composioAnahtarModali);
  const ca = $("#ek-cmp-ara", kap);
  if (ca) ca.onchange = async () => { composioArama = ca.value.trim(); await composioYukle(); ciz(); };
}

async function composioYukle() {
  if (!veri.composio.bagli) { veri.uygulamalar = []; return; }
  try { veri.uygulamalar = (await api(`/api/composio/uygulamalar?arama=${encodeURIComponent(composioArama)}`)).uygulamalar; } catch (e) { veri.uygulamalar = []; bildir(e.message, "uyari", 5000); }
}

let yenileZamani = null;
export async function yukle() {
  clearTimeout(yenileZamani);
  const [m, d, s, p, c] = await Promise.all([
    api("/api/mcp").catch(() => ({ sunucular: [] })),
    api("/api/mcp/ice-aktar").catch(() => ({ dizin: [] })),
    api("/api/skiller").catch(() => ({ skiller: [] })),
    api("/api/pluginler").catch(() => ({ pluginler: [] })),
    api("/api/composio").catch(() => ({ bagli: false })),
  ]);
  veri = { ...veri, mcp: m.sunucular || [], dizin: d.dizin || [], skiller: s.skiller || [], pluginler: p.pluginler || [], composio: c };
  await composioYukle();
  ciz();
  // baglanan sunucu varken durum kendiliginden guncellensin (sayfa aciksa)
  if (veri.mcp.some((s) => baglayiciDurumu(s).kod === "baglaniyor") && document.querySelector("#ek-icerik")?.offsetParent) {
    yenileZamani = setTimeout(() => yukle().catch(() => {}), 3000);
  }
}

export function eklentilerKur({ git } = {}) {
  if (git) gitFn = git;
  $("#ek-ara").oninput = (e) => { arama = e.target.value.trim(); ciz(); };
  $$("#ek-filtre [data-f]").forEach((b) => {
    b.onclick = () => { filtre = b.dataset.f; $$("#ek-filtre [data-f]").forEach((x) => x.classList.toggle("aktif", x === b)); ciz(); };
  });
  $("#ek-ekle").onclick = (e) => ekleMenusu(e.currentTarget);
  $("#ek-yenile").onclick = () => yukle().then(() => bildir("Yenilendi.", "basari", 1200));
}
