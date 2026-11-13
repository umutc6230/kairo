// Giris noktasi: acilis, gezinme, kenar cubugu, durum cubugu, menuler, kisayollar.
import { ikon, ikonlariYerlestir } from "./ikonlar.js";
import { kacir } from "./md.js";
import { aramaAc, ayarKaydet, ayarlarAc, ayarlarKur, modelYukle, sunucuDurdur } from "./ayarlar.js";
import { $, $$, api, bildir, durum, el, menuAc, modal, modelAdi, modelProfil, onayla, oturumBasligi, sayi, sor, turkcelestir } from "./ortak.js";
import { artifactListesiCiz } from "./inceleme.js";
import { sayfaModelleriniYenile, sayfalarKur } from "./sayfalar.js";
import { modelSayfasiYukle, modellerKur } from "./modeller.js";
import { projeAc, projeDurumu, projeKur } from "./proje.js";
import { skillSayfasiYukle, skillerKur } from "./skiller.js";
import { eklentilerKur, yukle as eklentileriYukle } from "./eklentiler.js";
import { gorevBildirimIzle, gorevSayfasiYukle, gorevlerKur } from "./gorevler.js";
import { dikteDurumuYenile, dikteKur } from "./dikte.js";
import { baglamYenile, sagPanelKur } from "./sagpanel.js";
import { dockAcKapa, dockKur, degisiklikYenile } from "./dock.js";
import { gorunumUygula, kisayolEslesir } from "./ayarlar2.js";
import { rutinleriYukle, rutinlerKur } from "./rutinler.js";
import { ajanlarKur, ajanlarYukle } from "./ajanlar.js";
import { ajanBloklariniCiz, ajanliOturum, akisVar, durdur, mesajlariCiz, sohbetKur, yeniSohbetEkrani } from "./sohbet.js";

const BASLIKLAR = { karsilastir: "Karşılaştır", ocr: "OCR testi", arac: "Araç testi", paket: "Test paketi", eklentiler: "Eklentiler", skiller: "Skill'ler ve talimatlar", modeller: "Modeller", gorevler: "Ajan görevleri", rutinler: "Rutinler", ajanlar: "Ajanlar" };
const gecmis = [];
let gecmisKonum = -1;

// ---------------- gezinme ----------------
function gorunumGoster(ad) {
  durum.gorunum = ad;
  $$(".gorunum").forEach((g) => { g.hidden = g.id !== `g-${ad}`; });
  $$(".nav-oge").forEach((n) => n.classList.toggle("aktif", n.dataset.git === ad || (n.dataset.git === "ozellestir" && ["eklentiler", "skiller", "modeller"].includes(ad))));
  $$(".oturum").forEach((o) => o.classList.toggle("aktif", ad === "sohbet" && o.dataset.id === durum.oturumId));
  if (BASLIKLAR[ad]) baslikAyarla(BASLIKLAR[ad]);
}

function git(hedef, { kaydetme = false } = {}) {
  if (!kaydetme) {
    gecmis.splice(gecmisKonum + 1);
    gecmis.push(hedef);
    gecmisKonum = gecmis.length - 1;
  }
  if (hedef.tur === "oturum") oturumAc(hedef.id, true);
  else if (hedef.tur === "yeni") { yeniSohbetEkrani({ girdiyiKoru: !!hedef.acilis }); gorunumGoster("sohbet"); baslikAyarla("Yeni sohbet"); oturumListesiCiz(); }
  else {
    gorunumGoster(hedef.tur);
    if (hedef.tur === "skiller") skillSayfasiYukle();
    if (hedef.tur === "eklentiler") eklentileriYukle().catch((e) => bildir(e.message, "hata"));
    if (hedef.tur === "gorevler") gorevSayfasiYukle();
    if (hedef.tur === "rutinler") rutinleriYukle();
    if (hedef.tur === "ajanlar") ajanlarYukle();
    if (hedef.tur === "modeller") modelSayfasiYukle();
  }
  $("#btn-geri").disabled = gecmisKonum <= 0;
  $("#btn-ileri").disabled = gecmisKonum >= gecmis.length - 1;
}

let uyanikAcik = false;
api("/api/uyanik").then((r) => { uyanikAcik = r.acik; }).catch(() => {});
async function uyanikDegistir() {
  try { uyanikAcik = (await api("/api/uyanik", { method: "PUT", govde: { acik: !uyanikAcik } })).acik; bildir(uyanikAcik ? "Uygulama açıkken bilgisayar uyumayacak." : "Uyanık tutma kapatıldı.", "basari", 1800); } catch (e) { bildir(e.message, "hata"); }
}

async function arkaPlanIsleri() {
  try {
    const { isler } = await api("/api/komutlar");
    modal({ baslik: "Arka plan işleri", genis: true, dugmeler: [{ metin: "Kapat" }], icerik: isler.length
      ? isler.map((i) => `<div class="kart"><div class="kart-baslik"><code>${kacir(i.komut)}</code><span class="rozet">${kacir(i.durum)}</span></div><pre class="dosya-gorunum" style="max-height:200px">${kacir(i.cikti.slice(-3000))}</pre></div>`).join("")
      : '<div class="soluk">Çalışan ya da biten arka plan işi yok.</div>' });
  } catch (e) { bildir(e.message, "hata"); }
}

// Claude Desktop gibi: basliga tiklaninca etkin sohbetin menusu
function baslikMenusu(capa) {
  const o = (durum.oturumlar || []).find((x) => x.id === durum.oturumId);
  if (!o || durum.gorunum !== "sohbet") return;
  menuAc(capa, [
    { metin: "Yeniden adlandır", ikon: "kalem", eylem: () => yenidenAdlandir(o) },
    { metin: "Çatalla (kopyasından devam)", ikon: "kopyala", eylem: async () => {
      try { const y = await api(`/api/oturumlar/${o.id}/catal`, { method: "POST" }); await oturumlariYenile(); git({ tur: "oturum", id: y.id }); } catch (e) { bildir(e.message, "hata"); }
    } },
    { metin: "Markdown olarak dışa aktar", ikon: "dis", eylem: async () => {
      try {
        const r = await fetch(`/api/oturumlar/${o.id}/disa-aktar?bicim=md`, { headers: oturumBasligi() });
        if (!r.ok) throw new Error(`Dışa aktarılamadı (${r.status})`);
        await navigator.clipboard.writeText(await r.text());
        bildir("Sohbet Markdown olarak panoya kopyalandı.", "basari", 1500);
      } catch (e) { bildir(e.message, "hata"); }
    } },
    "ayrac",
    { metin: "Sil", ikon: "cop", tehlike: true, eylem: () => oturumSil(o) },
  ]);
}

function baslikAyarla(metin) {
  $("#sayfa-basligi").textContent = metin || "Yeni sohbet";
  document.title = `${metin || "Yeni sohbet"} - Kairo`;
  baglamYenile();
}

async function oturumAc(id, kaydetme = false) {
  if (!kaydetme) return git({ tur: "oturum", id });
  if (akisVar() && durum.oturumId !== id) durdur();
  try {
    const o = await api(`/api/oturumlar/${id}`);
    durum.oturumId = o.id;
    gorunumGoster("sohbet");
    mesajlariCiz(o);
    ajanBloklariniCiz(o.id);
    baslikAyarla(o.baslik);
    oturumListesiCiz();
  } catch (e) {
    bildir(e.message, "hata");
  }
}

// ---------------- oturum listesi ----------------
const kapaliGruplar = new Set(JSON.parse(localStorage.getItem("kapaliGruplar") || "[]"));

function grupAdi(iso) {
  const t = new Date(iso);
  const bugun = new Date();
  bugun.setHours(0, 0, 0, 0);
  const gun = Math.floor((bugun - new Date(t.getFullYear(), t.getMonth(), t.getDate())) / 864e5);
  const arsiv = durum.ayarlar?.arsiv_gun || 0; // N gun dokunulmayan sohbet Arsiv'e (silinmez)
  if (arsiv && gun >= arsiv) return "Arşiv";
  if (gun <= 0) return "Bugün";
  if (gun === 1) return "Dün";
  if (gun < 7) return "Bu hafta";
  if (gun < 30) return "Bu ay";
  return "Daha eski";
}

function sagPanelOrtam() {
  const a = durum.ayarlar || {};
  const model = a.saglayici === "openrouter" && a.or_model ? a.or_model : modelAdi(a.model);
  const m = $("#sp-model");
  if (m) m.textContent = `Model: ${model || "-"}`;
  const p = $("#sp-proje-metni");
  if (p) p.textContent = projeDurumu.aktif?.ad || "Proje seç (açınca sohbet ajan olur)";
}
document.addEventListener("oturumlar-degisti", () => { oturumlariYenile(); sagPanelOrtam(); });

async function oturumlariYenile() {
  try {
    durum.oturumlar = await api("/api/oturumlar");
  } catch { /* sessiz */ }
  oturumListesiCiz();
}

// Claude Code Desktop gibi: ayri ozellik sayfasi yok. Ozellestir = skill/talimat + modeller
// (ayni gorunumde sekme), hafiza/hook/AI ayarlari Ayarlar penceresinde.
function ozellestirSekmeleri() {
  const sekmeler = [["eklentiler", "Eklentiler"], ["skiller", "Skill'ler ve talimatlar"], ["modeller", "Modeller"], ["mcp", "Bağlayıcılar"], ["plugin", "Plugin'ler"], ["uzanti", "Uzantılar"], ["hafiza", "Hafıza"], ["hooks", "Hook'lar"]];
  for (const ad of ["eklentiler", "skiller", "modeller"]) {
    const ic = document.querySelector(`#g-${ad} .sayfa-ic`);
    if (!ic || ic.querySelector(".ozellestir-sekmeler")) continue;
    const bar = el(`<div class="sekmeler ozellestir-sekmeler" role="tablist">${sekmeler.map(([k, m]) => `<button class="sekme ${k === ad ? "aktif" : ""}" ${k === "modeller" ? "data-yalniz-yerel" : ""} role="tab" aria-selected="${k === ad}" data-oz="${k}">${kacir(m)}</button>`).join("")}</div>`);
    bar.querySelectorAll("[data-oz]").forEach((b) => {
      b.onclick = () => (["mcp", "plugin", "uzanti", "hafiza", "hooks"].includes(b.dataset.oz) ? ayarlarAc(b.dataset.oz) : git({ tur: b.dataset.oz }));
    });
    ic.prepend(bar);
  }
}

function artifactPenceresi() {
  const kap = el('<ul class="artifact-liste"></ul>');
  modal({ baslik: "Artifact'ler", icerik: kap, genis: true, dugmeler: [{ metin: "Kapat" }] });
  artifactListesiCiz(kap);
}

function oturumListesiCiz() {
  const kap = $("#oturum-listesi");
  kap.innerHTML = "";
  const gruplar = new Map();
  for (const o of durum.oturumlar) {
    if (!o.mesaj_sayisi && o.id !== durum.oturumId && !ajanliOturum(o.id)) continue;
    const g = grupAdi(o.guncelleme);
    if (!gruplar.has(g)) gruplar.set(g, []);
    gruplar.get(g).push(o);
  }
  for (const [ad, liste] of gruplar) {
    const grup = el(`<div class="grup ${kapaliGruplar.has(ad) ? "kapali" : ""}"><div class="grup-baslik"><span>${ad}</span><span data-ikon="asagi"></span></div><div class="grup-ogeler"></div></div>`);
    grup.querySelector(".grup-baslik").onclick = () => {
      grup.classList.toggle("kapali");
      kapaliGruplar[grup.classList.contains("kapali") ? "add" : "delete"](ad);
      localStorage.setItem("kapaliGruplar", JSON.stringify([...kapaliGruplar]));
    };
    for (const o of liste) {
      const s = el(`<div class="oturum ${durum.gorunum === "sohbet" && o.id === durum.oturumId ? "aktif" : ""}" data-id="${o.id}">
        <span class="ad" title="${kacir(o.baslik)}">${kacir(o.baslik)}</span><button class="ikon-btn daha" title="Diger" data-ikon="daha"></button></div>`);
      s.onclick = () => oturumAc(o.id);
      s.querySelector(".daha").onclick = (e) => {
        e.stopPropagation();
        menuAc(e.currentTarget, [
          { metin: "Yeniden adlandır", ikon: "kalem", eylem: () => yenidenAdlandir(o) },
          { metin: "Sil", ikon: "cop", tehlike: true, eylem: () => oturumSil(o) },
        ]);
      };
      grup.querySelector(".grup-ogeler").append(s);
    }
    kap.append(grup);
  }
  if (!gruplar.size) kap.append(el(`<div class="ayar-not" style="padding:16px 10px">Henüz sohbet yok.</div>`));
  ikonlariYerlestir(kap);
}

async function yenidenAdlandir(o) {
  const yeni = await sor("Sohbeti yeniden adlandır", o.baslik);
  if (yeni == null || !yeni.trim()) return;
  try {
    await api(`/api/oturumlar/${o.id}`, { method: "PATCH", govde: { baslik: yeni } });
    if (o.id === durum.oturumId) baslikAyarla(yeni);
    oturumlariYenile();
  } catch (e) { bildir(e.message, "hata"); }
}

async function oturumSil(o) {
  if (!(await onayla("Sohbeti sil", `"${o.baslik}" kalıcı olarak silinecek.`, { evet: "Sil", tehlike: true }))) return;
  try {
    await api(`/api/oturumlar/${o.id}`, { method: "DELETE" });
    if (o.id === durum.oturumId) git({ tur: "yeni" });
    oturumlariYenile();
  } catch (e) { bildir(e.message, "hata"); }
}

// ---------------- durum / model ----------------
const DURUM_METNI = { hazir: "hazır", yukleniyor: "yükleniyor", kapali: "kapalı", hata: "hata", bilinmiyor: "…" };

/** OpenRouter seciliyse yerel (llama.cpp) modeller arayuzde gorunmez ve kullanilmaz. */
const uzakMi = () => durum.ayarlar?.saglayici === "openrouter";

async function durumYenile() {
  try {
    durum.sunucu = await api("/api/durum");
    turkcelestir(null, durum.sunucu);
  } catch {
    $("#sunucu-metni").textContent = "Uygulama sunucusu yanıt vermiyor";
    return;
  }
  const s = durum.sunucu;
  const a = durum.ayarlar;
  const aktif = s.yuklenen_model || a.model;
  document.body.classList.toggle("uzak-saglayici", uzakMi());
  if (uzakMi()) {
    $("#sunucu-nokta").className = `nokta ${a.or_model ? "hazir" : "hata"}`;
    $("#sunucu-metni").textContent = a.or_model ? `OpenRouter · ${a.or_model}` : "OpenRouter · model seçilmedi";
    $("#hap-model-metni").textContent = a.or_model || "Model seç";
    const dus0 = durum.bilgi.dusunme_secenekleri.find((d) => d.deger === a.dusunme);
    $("#hap-dusunme-metni").textContent = dus0 ? dus0.kisa : a.dusunme;
    bantGuncelle();
    bosDurumKartlari();
    agecidiGuncelle();
    return;
  }
  $("#sunucu-nokta").className = `nokta ${s.durum}`;
  $("#hap-nokta").className = `nokta buyuk ${s.durum}`;
  $("#sunucu-metni").textContent = s.durum === "kapali" ? "Model kapalı" : `${modelAdi(aktif)} · ${DURUM_METNI[s.durum] || s.durum}`;
  const b = s.bellek || {};
  $("#ram-metni").textContent = b.bos_gb != null ? `RAM ${sayi(b.bos_gb)}/${sayi(b.toplam_gb, 0)} GB boş` : "";
  $("#hap-model-metni").textContent = a.saglayici === "openrouter" && a.or_model ? a.or_model : modelAdi(a.model);
  const dus = durum.bilgi.dusunme_secenekleri.find((d) => d.deger === a.dusunme);
  $("#hap-dusunme-metni").textContent = dus ? dus.kisa : a.dusunme;
  $("#klasor-metni").textContent = `Model klasörü: ${a.llm_dizin}`;
  $("#hap-klasor-metni").textContent = a.llm_dizin.split(/[\\/]/).pop() || a.llm_dizin;
  bantGuncelle();
  bosDurumKartlari();
  agecidiGuncelle();
}

async function agecidiGuncelle() {
  let s;
  try { s = await api("/api/sunucu"); } catch { return; }
  const hap = $("#agecidi-hapi");
  hap.hidden = !s.ayar_acik;
  $("#agecidi-nokta").className = `nokta ${s.acik ? "hazir" : s.hata ? "hata" : ""}`;
  $("#agecidi-metni").textContent = s.acik ? `Sunucu :${s.port}` : s.hata ? "Sunucu açılamadı" : "Sunucu kapalı";
}

function bantGuncelle() {
  const s = durum.sunucu;
  const a = durum.ayarlar;
  const p = modelProfil(a.model);
  const bant = $("#uyari-bandi");
  let html = "";
  const bos = s.bellek?.bos_gb;
  if (a.saglayici === "openrouter" && a.or_model) {
    // Uzak model: yerel RAM/dosya/llama.cpp uyarilari ilgisiz; bant onay kartini da ortuyordu
  } else if (!s.motor_var) {
    html = `<span class="vurgu">${ikon("uyari")}llama.cpp bulunamadı</span><span>${kacir(a.llm_dizin)} içinde llama.cpp\\llama-server.exe yok.</span><button class="btn kucuk" data-eylem="ayar">Ayarlar</button>`;
  } else if (p && !p.dosya_var) {
    html = `<span class="vurgu">${ikon("uyari")}Model dosyası yok</span><span>${kacir(p.ad)} indirilmemiş. Başka model seç.</span><button class="btn kucuk" data-eylem="ayar">Model seç</button>`;
  } else if (s.durum === "hata" && s.son_hata) {
    html = `<span class="vurgu">${ikon("uyari")}Model açılamadı</span><span>${kacir(s.son_hata)}</span><button class="btn kucuk" data-eylem="yukle">Tekrar dene</button>`;
  } else if (s.sunucu_acik && !s.bizim_sunucu && s.acik_modeller.length && !s.acik_modeller.includes(a.model)) {
    html = `<span class="vurgu sari">${ikon("uyari")}Başka model açık</span><span>Dışarıda ${kacir(s.acik_modeller.join(", "))} çalışıyor; ${kacir(p?.ad || a.model)} için kapatılmalı.</span><button class="btn kucuk" data-eylem="harici">Kapat</button>`;
  } else if (p && bos != null && s.yuklenen_model !== a.model && bos < p.ram_gb + 1) {
    html = `<span class="vurgu sari">${ikon("uyari")}Bellek az</span><span>${sayi(bos)} GB boş; ${kacir(p.ad)} ~${sayi(p.ram_gb + 1, 0)} GB istiyor. Oyun, tarayıcı gibi programları kapat.</span>`;
  }
  bant.hidden = !html;
  bant.innerHTML = html;
  bant.querySelectorAll("[data-eylem]").forEach((btn) => {
    btn.onclick = () => ({ ayar: () => ayarlarAc(), yukle: () => modelYukle(), harici: () => sunucuDurdur(true) })[btn.dataset.eylem]();
  });
}

function bosDurumKartlari() {
  const kap = $("#model-kartlari");
  const a = durum.ayarlar;
  kap.innerHTML = "";
  // AI Ayarlari'ndaki saglayici ve model ne ise o gorunur
  kap.append(el(`<div class="kart-baslik-satir soluk kucuk">Sağlayıcı: ${uzakMi() ? "OpenRouter" : "Yerel (llama.cpp)"}</div>`));
  if (uzakMi()) {
    const k = el(`<button class="kart-satir secili"><span data-ikon="model"></span><span>${kacir(a.or_model || "Model seç")}</span><span class="sag">OpenRouter</span>${a.or_model ? '<span class="tik" data-ikon="tik"></span>' : ""}</button>`);
    k.onclick = () => ayarlarAc();
    kap.append(k);
  }
  for (const m of uzakMi() ? [] : durum.sunucu.modeller) {
    const k = el(`<button class="kart-satir ${m.anahtar === a.model ? "secili" : ""} ${m.dosya_var ? "" : "pasif"}">
      <span data-ikon="model"></span><span>${kacir(m.ad)}</span>
      <span class="sag">${m.dosya_var ? `~${m.ram_gb} GB${m.ses ? " · ses" : ""}` : "indirilmedi"}</span>
      ${m.anahtar === a.model ? '<span class="tik" data-ikon="tik"></span>' : ""}</button>`);
    k.onclick = () => m.dosya_var ? ayarKaydet({ model: m.anahtar }, true) : bildir("Bu model indirilmemiş.", "hata");
    kap.append(k);
  }
  kap.append(el(`<div class="kart-ayrac"></div>`));
  const dus = durum.bilgi.dusunme_secenekleri.find((d) => d.deger === a.dusunme);
  const d = el(`<button class="kart-satir"><span data-ikon="beyin"></span><span>Düşünme: ${kacir(dus?.ad || a.dusunme)}</span><span data-ikon="asagi" class="kucuk-ikon"></span></button>`);
  d.onclick = (e) => dusunmeMenusu(e.currentTarget, false);
  kap.append(d);
  ikonlariYerlestir(kap);
}

function dusunmeMenusu(capa, yukari = true) {
  menuAc(capa, durum.bilgi.dusunme_secenekleri.map((d) => ({
    metin: d.ad, sag: d.sure, secili: d.deger === durum.ayarlar.dusunme, eylem: () => ayarKaydet({ dusunme: d.deger }, true),
  })), { yukari });
}

function modelMenusu(capa) {
  const a = durum.ayarlar;
  const ogeler = [{ baslik: uzakMi() ? "Model · OpenRouter" : "Model" }];
  if (uzakMi()) ogeler.push({ metin: a.or_model || "Model seçilmedi", sag: "uzak", secili: !!a.or_model, eylem: () => ayarlarAc() });
  for (const m of uzakMi() ? [] : durum.sunucu.modeller) {
    ogeler.push({
      metin: m.ad, sag: m.dosya_var ? `~${m.ram_gb} GB` : "yok", secili: m.anahtar === a.model, pasif: !m.dosya_var,
      eylem: () => ayarKaydet({ model: m.anahtar }, true),
    });
  }
  ogeler.push("ayrac", { baslik: "Düşünme" });
  for (const d of durum.bilgi.dusunme_secenekleri) {
    ogeler.push({ metin: d.ad, sag: d.sure, secili: d.deger === a.dusunme, eylem: () => ayarKaydet({ dusunme: d.deger }, true) });
  }
  ogeler.push("ayrac", { metin: "AI Ayarları", ikon: "disli", eylem: () => ayarlarAc() });
  menuAc(capa, ogeler, { yukari: true, sagaHizali: true });
}

function sunucuMenusu(capa, yukari) {
  const s = durum.sunucu;
  if (uzakMi()) {
    menuAc(capa, [{ baslik: `OpenRouter · ${durum.ayarlar.or_model || "model seçilmedi"}` }, "ayrac",
      { metin: "AI Ayarları", ikon: "disli", eylem: () => ayarlarAc() }], { yukari, sagaHizali: !yukari });
    return;
  }
  menuAc(capa, [
    { baslik: s.sunucu_acik ? `Açık: ${s.acik_modeller.join(", ") || "?"}` : "Model sunucusu kapalı" },
    { metin: `Modeli yükle (${modelAdi(durum.ayarlar.model)})`, ikon: "guc", eylem: () => modelYukle() },
    { metin: "Sunucuyu durdur", ikon: "durdur", pasif: !s.bizim_sunucu, eylem: () => sunucuDurdur(false) },
    ...(s.sunucu_acik && !s.bizim_sunucu ? [{ metin: "Dışarıdan açılanı kapat", ikon: "x", tehlike: true, eylem: () => sunucuDurdur(true) }] : []),
    "ayrac",
    { metin: "AI Ayarları", ikon: "disli", eylem: () => ayarlarAc() },
  ], { yukari, sagaHizali: !yukari });
}

// OpenBot "Activity": ajanlarin yaptigi her islem, onay karari ve kapsami (denetim kaydi)
async function etkinlikAc() {
  const KAPSAM = { tek: "bir kez", sohbet: "bu görev", her_zaman: "her zaman" };
  const govde = el(`<div><div class="satir"><label class="onay"><input type="checkbox" id="et-yan"> Yalnız değişiklik yapanlar</label></div><div id="et-liste" class="kaynak-liste"></div></div>`);
  const ciz = async () => {
    const yan = govde.querySelector("#et-yan").checked;
    try {
      const { etkinlik } = await api(`/api/etkinlik?adet=300&yalniz_yan_etkili=${yan}`);
      govde.querySelector("#et-liste").innerHTML = etkinlik.map((x) => `<div class="etk-satir">
        <div><span class="soluk kucuk">${kacir(x.zaman.replace("T", " "))}</span> <code>${kacir(x.arac)}</code> <span class="rozet ${x.durum === "hata" ? "kirmizi" : ""}">${kacir(x.durum)}</span>${x.yan_etkili ? ' <span class="rozet sari">değişiklik</span>' : ""}${x.onay ? ` <span class="rozet">onay: ${kacir(x.onay.karar)}${x.onay.karar === "onayli" ? ` (${kacir(KAPSAM[x.onay.kapsam] || x.onay.kapsam)})` : ""}</span>` : ""}</div>
        <div class="soluk kucuk">${kacir(x.aciklama || x.dosya || "")}</div>
        <div class="soluk kucuk">Görev: ${kacir(x.gorev)}</div></div>`).join("") || '<div class="soluk">Henüz etkinlik yok.</div>';
    } catch (e) { bildir(e.message, "hata"); }
  };
  govde.querySelector("#et-yan").onchange = ciz;
  modal({ baslik: "Etkinlik", icerik: govde, genis: true });
  ciz();
}

async function hepsiniYenile() {
  durum.ayarlar = await api("/api/ayarlar");
  await durumYenile();
  sayfaModelleriniYenile();
  dikteDurumuYenile(); // model degisince dikte dugmesi durumu
  sagPanelOrtam();
}

// ---------------- acilis ----------------
async function baslat() {
  ikonlariYerlestir();
  durum.bilgi = await api("/api/bilgi");
  turkcelestir(durum.bilgi, null);
  durum.ayarlar = await api("/api/ayarlar");
  gorunumUygula(durum.ayarlar);
  gorevBildirimIzle();
  await durumYenile();
  sohbetKur({ oturumlarYenile: oturumlariYenile, baslikAyarla });
  ayarlarKur(hepsiniYenile);
  sayfalarKur();
  projeKur();
  skillerKur(hepsiniYenile);
  gorevlerKur();
  ozellestirSekmeleri();
  $("#sp-proje").onclick = () => projeAc();
  sagPanelKur({ baglayiciAc: () => ayarlarAc("mcp"), ayarAc: () => ayarlarAc() });
  dockKur();
  rutinlerKur();
  ajanlarKur();
  eklentilerKur({ git });
  document.addEventListener("oturumlar-degisti", degisiklikYenile);
  $("#baslik-menu").onclick = (e) => baslikMenusu(e.currentTarget);
  $("#btn-daha").onclick = (e) => menuAc(e.currentTarget, [
    { metin: "Yan sohbet (Ctrl+;)", ikon: "liste", eylem: () => dockAcKapa("yan", true) },
    { metin: "Plan", ikon: "liste", eylem: () => dockAcKapa("plan", true) },
    { metin: "Arka plan işleri", ikon: "terminal", eylem: () => arkaPlanIsleri() },
    { metin: "Ajan görevleri", ikon: "liste", eylem: () => git({ tur: "gorevler" }) },
    { metin: "Etkinlik (ne yapıldı)", ikon: "saat", eylem: () => etkinlikAc() },
    { metin: uyanikAcik ? "Uyanık tutmayı kapat" : "Bilgisayarı uyanık tut", ikon: "guc", eylem: () => uyanikDegistir() },
    "ayrac",
    { metin: "Eklentiler (bağlayıcı, skill, plugin)", ikon: "sihir", eylem: () => git({ tur: "eklentiler" }) },
    ...(uzakMi() ? [] : [{ metin: "Modeller", ikon: "model", eylem: () => git({ tur: "modeller" }) }]),
    { metin: "Ayarlar", ikon: "disli", eylem: () => ayarlarAc() },
    { metin: "Hakkında", ikon: "bilgi", eylem: () => ayarlarAc("hakkinda") },
  ], { sagaHizali: true });
  dikteKur();
  modellerKur(hepsiniYenile);

  $$(".nav-oge").forEach((n) => {
    n.onclick = () => {
      const h = n.dataset.git;
      if (h === "ara") aramaAc(oturumAc);
      else if (h === "artifactler") artifactPenceresi();
      else git({ tur: h === "ozellestir" ? "eklentiler" : h });
    };
  });
  $("#btn-kenar").onclick = () => $("#kok").classList.toggle("kenar-kapali");
  // Telefon (Tailscale uzak erisim, ince istemci): kenar cubugu ust katman; secim yapinca kapanir
  const dar = window.matchMedia("(max-width: 700px)");
  if (dar.matches) $("#kok").classList.add("kenar-kapali");
  $("#kenar").addEventListener("click", (e) => {
    if (dar.matches && e.target.closest(".nav-oge, .oturum, #btn-ayarlar")) $("#kok").classList.add("kenar-kapali");
  });
  $("#btn-geri").onclick = () => { if (gecmisKonum > 0) git(gecmis[--gecmisKonum], { kaydetme: true }); };
  $("#btn-ileri").onclick = () => { if (gecmisKonum < gecmis.length - 1) git(gecmis[++gecmisKonum], { kaydetme: true }); };
  $("#btn-ayarlar").onclick = () => ayarlarAc();
  $("#btn-hakkinda").onclick = () => ayarlarAc("hakkinda");
  $("#klasor-satiri").onclick = () => ayarlarAc();
  $("#hap-model").onclick = (e) => modelMenusu(e.currentTarget);
  $("#hap-bilgisayar").onclick = (e) => sunucuMenusu(e.currentTarget, true);
  $("#sunucu-hapi").onclick = (e) => sunucuMenusu(e.currentTarget, false);
  $("#agecidi-hapi").onclick = () => { ayarlarAc(); setTimeout(() => document.getElementById("ay-agecidi")?.scrollIntoView({ behavior: "smooth" }), 50); };

  document.addEventListener("keydown", (e) => {
    if (kisayolEslesir(e, durum.ayarlar?.dikte_kisayolu)) { e.preventDefault(); $("#btn-dikte")?.click(); return; }
    if (!e.ctrlKey) return;
    const k = e.key.toLowerCase();
    if (k === "n") { e.preventDefault(); git({ tur: "yeni" }); }
    else if (k === "k") { e.preventDefault(); aramaAc(oturumAc); }
    else if (k === "b") { e.preventDefault(); $("#kok").classList.toggle("kenar-kapali"); }
    else if (k === ",") { e.preventDefault(); ayarlarAc(); }
  });

  await oturumlariYenile();
  git({ tur: "yeni", acilis: true });
  setInterval(() => { if (!document.hidden) durumYenile(); }, 3000);
  document.documentElement.dataset.hazir = "1"; // tum isleyiciler bagli (E2E ve otomasyon bunu bekler)
}

// Cercevesiz pencere: kendi kucult/buyut/kapat butonlarimiz (yalniz pywebview icinde).
window.addEventListener("pywebviewready", () => {
  $("#pencere-btnleri").hidden = false;
  $("#btn-kucult").onclick = () => window.pywebview.api.kucult();
  $("#btn-buyut").onclick = () => window.pywebview.api.buyut();
  $("#btn-kapat").onclick = () => window.pywebview.api.kapat();
  $(".baslik-orta").ondblclick = () => window.pywebview.api.buyut();
});

baslat().catch((e) => bildir(`Açılış hatası: ${e.message}`, "hata", 15000));
