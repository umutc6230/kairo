// Giris noktasi: acilis, gezinme, kenar cubugu, durum cubugu, menuler, kisayollar.
import { uzantiYuzeyleriKur } from "./uzantilar.js";
import { ikon, ikonlariYerlestir } from "./ikonlar.js";
import { kacir } from "./md.js";
import { aramaAc, ayarKaydet, ayarlarAc, ayarlarKur, modelYukle, sunucuDurdur } from "./ayarlar.js";
import { $, $$, api, bildir, durum, el, menuAc, modal, modelAdi, modelProfil, onayla, oturumBasligi, sayi, sor, turkcelestir } from "./ortak.js";
import { sayfaModelleriniYenile, sayfalarKur } from "./sayfalar.js";
import { modelSayfasiYukle, modellerKur } from "./modeller.js";
import { ollamaKur, ollamaYukle } from "./ollama.js";
import { projeAc, projeDurumu, projeKur, projeYenile } from "./proje.js";
import { skillSayfasiYukle, skillerKur } from "./skiller.js";
import { eklentilerKur, yukle as eklentileriYukle } from "./eklentiler.js";
import { gorevBildirimIzle, gorevSayfasiYukle, gorevlerKur } from "./gorevler.js";
import { dikteDurumuYenile, dikteKur } from "./dikte.js";
import { baglamYenile, sagPanelKur } from "./sagpanel.js";
import { dockAcKapa, dockKur, degisiklikYenile } from "./dock.js";
import { gorunumUygula, kisayolEslesir } from "./ayarlar2.js";
import { rutinleriYukle, rutinlerKur } from "./rutinler.js";
import { ajanlarKur, ajanlarYukle } from "./ajanlar.js";
import { ajanBloklariniCiz, ajanKayitlariniBirlestir, ajanliOturum, akisVar, durdur, mesajlariCiz, sohbetKur, sohbetRunlari, yeniSohbetEkrani } from "./sohbet.js";

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
    if (hedef.tur === "modeller") { modelSayfasiYukle(); ollamaYukle(); }
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

// Sohbet dosyasinda yalniz duz sohbet mesajlari var; ajan turlari ayri gorev kayitlarinda.
// Paylasim ikisini birlestirir (ajan istegi + sonucu + adim ozeti).
async function sohbetMarkdown(o) {
  const r = await fetch(`/api/oturumlar/${o.id}/disa-aktar?bicim=md`, { headers: oturumBasligi() });
  if (!r.ok) throw new Error(`Dışa aktarılamadı (${r.status})`);
  let metin = await r.text();
  for (const k of sohbetRunlari(o.id)) {
    try {
      const g = await api(`/api/gorevler/${k.run}`);
      const adimlar = (g.adimlar || []).map((a) => `${a.no}. ${a.arac} - ${a.durum}${a.cikis_kodu != null ? ` (çıkış ${a.cikis_kodu})` : ""}`);
      metin += `\n## kullanici\n${k.metin || g.hedef || ""}\n\n## asistan (ajan, ${g.durum})\n`;
      if (adimlar.length) metin += `\n<details><summary>Adımlar</summary>\n\n${adimlar.join("\n")}\n\n</details>\n\n`;
      metin += `${g.sonuc?.ozet || g.hata || ""}\n`;
    } catch { metin += `\n_(ajan görevi ${k.run} okunamadı)_\n`; }
  }
  return metin;
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
    { metin: "Tüm sohbeti kopyala", ikon: "kopyala", eylem: async () => {
      try {
        await navigator.clipboard.writeText(await sohbetMarkdown(o));
        bildir("Sohbetin tamamı (ajan cevapları dahil) panoya kopyalandı.", "basari", 2000);
      } catch (e) { bildir(e.message, "hata"); }
    } },
    { metin: "Dosyaya kaydet (.md)", ikon: "dis", eylem: async () => {
      try {
        const metin = await sohbetMarkdown(o);
        const ad = `${(o.baslik || "sohbet").replace(/[\\/:*?"<>|]+/g, "-").slice(0, 60)}.md`;
        if (window.pywebview?.api?.dosya_kaydet) {
          const yol = await window.pywebview.api.dosya_kaydet(ad, metin);
          if (yol) bildir(`Kaydedildi: ${yol}`, "basari", 3000);
        } else {
          const a = el(`<a download="${kacir(ad)}"></a>`);
          a.href = URL.createObjectURL(new Blob([metin], { type: "text/markdown" }));
          a.click();
          URL.revokeObjectURL(a.href);
        }
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
    // sohbet projeye ozgu: baska projenin sohbeti acilinca o proje etkin olur
    if (o.alan && o.alan !== projeDurumu.etkin?.id) await projeyeGec(o.alan);
    durum.oturumId = o.id;
    document.getElementById("girdi").dispatchEvent(new Event("oturum-degisti"));
    gorunumGoster("sohbet");
    mesajlariCiz(o);
    ajanKayitlariniBirlestir(o);
    ajanBloklariniCiz(o.id);
    baslikAyarla(o.baslik);
    oturumListesiCiz();
  } catch (e) {
    bildir(e.message, "hata");
  }
}

async function projeyeGec(alan) {
  try {
    await api(`/api/projeler/${alan}/etkin`, { method: "POST" });
    await projeYenile();
  } catch { /* proje silinmis: sohbet yine acilir, etkin proje degismez */ }
}

// ---------------- oturum listesi ----------------
const KISISEL = "0".repeat(12); // sunucudaki VARSAYILAN_ALAN_ID (proje kapali)
let listeDuzeni = localStorage.getItem("listeDuzeni") === "proje" ? "proje" : "tarih";

function projeAdi(alan) {
  if (!alan) return "Proje yok";
  if (alan === KISISEL) return "Kişisel klasörler";
  return (projeDurumu.liste || []).find((a) => a.id === alan)?.ad || "Kapatılmış proje";
}

const kapaliGruplar = new Set(JSON.parse(localStorage.getItem("kapaliGruplar") || "[]"));
const kapaliAltlar = new Set(JSON.parse(localStorage.getItem("kapaliAltlar") || "[]"));

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
  const p = $("#sp-proje-metni");
  if (p) p.textContent = projeDurumu.etkin?.ad || projeDurumu.aktif?.ad || "Proje seç (açınca sohbet ajan olur)";
}
document.addEventListener("oturumlar-degisti", () => { oturumlariYenile(); sagPanelOrtam(); });

async function oturumlariYenile() {
  try {
    durum.oturumlar = await api("/api/oturumlar");
  } catch { /* sessiz */ }
  oturumListesiCiz();
  if (!$("#bos-durum")?.hidden) bosDurumKartlari(); // proje sirasi sohbet sayisina bagli
}

// Telefon (TermFlow koprusu) ayni API'ye yazar; pencere bunu ancak yoklayarak gorur.
const imza = (o) => `${o.id}|${o.guncelleme}|${o.mesaj_sayisi}|${o.baslik}`;
async function disDegisiklikleriAl() {
  let yeni;
  try { yeni = await api("/api/oturumlar"); } catch { return; }
  const eski = new Map((durum.oturumlar || []).map((o) => [o.id, imza(o)]));
  if (yeni.length === eski.size && yeni.every((o) => eski.get(o.id) === imza(o))) return;
  durum.oturumlar = yeni;
  oturumListesiCiz();
  if (!$("#bos-durum")?.hidden) bosDurumKartlari();
  const acik = yeni.find((o) => o.id === durum.oturumId);
  // kendi akisimiz suruyorsa ekran zaten guncel; bitince bir kez yeniden cizilir
  if (acik && eski.get(acik.id) !== imza(acik) && !akisVar()) oturumAc(acik.id, true);
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

function oturumListesiCiz() {
  const kap = $("#oturum-listesi");
  kap.innerHTML = "";
  // Claude Desktop gibi: sohbetler tarihe ya da projeye gore; projede "+" o projede yeni sohbet
  const duzen = el(`<div class="liste-duzen" role="group" aria-label="Sohbetleri grupla">${[["tarih", "Tarih"], ["proje", "Proje"]]
    .map(([k, m]) => `<button class="liste-duzen-btn" data-duzen="${k}" aria-pressed="${listeDuzeni === k}">${m}</button>`).join("")}</div>`);
  duzen.querySelectorAll("[data-duzen]").forEach((b) => {
    b.onclick = () => {
      listeDuzeni = b.dataset.duzen;
      localStorage.setItem("listeDuzeni", listeDuzeni);
      oturumListesiCiz();
    };
  });
  kap.append(duzen);
  const gruplar = new Map();
  const gorunur = durum.oturumlar.filter((o) => o.mesaj_sayisi || o.ajan_sayisi || o.id === durum.oturumId || ajanliOturum(o.id));
  const idler = new Set(gorunur.map((o) => o.id));
  // Claude Desktop gibi: alt oturumlar ana oturumun altinda acilir/kapanir (ana gorunmuyorsa ustte)
  const altlar = new Map();
  for (const o of gorunur) {
    if (o.ust && idler.has(o.ust)) altlar.set(o.ust, [...(altlar.get(o.ust) || []), o]);
  }
  for (const o of gorunur) {
    if (o.ust && idler.has(o.ust)) continue;
    const g = listeDuzeni === "proje" ? `p:${o.alan || ""}` : grupAdi(o.guncelleme);
    if (!gruplar.has(g)) gruplar.set(g, []);
    gruplar.get(g).push(o);
  }
  if (listeDuzeni === "proje") { // sohbeti olmayan projeler de gorunsun: "+" ile ilk sohbet acilir
    for (const a of projeDurumu.liste || []) if (!gruplar.has(`p:${a.id}`)) gruplar.set(`p:${a.id}`, []);
  }
  for (const [ad, liste] of gruplar) {
    const projeMi = ad.startsWith("p:");
    const alan = projeMi ? ad.slice(2) : "";
    const baslik = projeMi ? projeAdi(alan) : ad;
    const grup = el(`<div class="grup ${kapaliGruplar.has(ad) ? "kapali" : ""}"><div class="grup-baslik"><span class="grup-ad" title="${kacir(baslik)}">${kacir(baslik)}</span><span class="grup-sag">${projeMi ? `<button class="ikon-btn grup-yeni" title="${kacir(baslik)}: yeni sohbet" aria-label="${kacir(baslik)} projesinde yeni sohbet" data-ikon="arti"></button>` : ""}<span data-ikon="asagi"></span></span></div><div class="grup-ogeler"></div></div>`);
    grup.querySelector(".grup-yeni")?.addEventListener("click", async (e) => {
      e.stopPropagation();
      await projeyeGec(alan || KISISEL);
      git({ tur: "yeni" });
    });
    grup.querySelector(".grup-baslik").onclick = () => {
      grup.classList.toggle("kapali");
      kapaliGruplar[grup.classList.contains("kapali") ? "add" : "delete"](ad);
      localStorage.setItem("kapaliGruplar", JSON.stringify([...kapaliGruplar]));
    };
    const satir = (o, alt = false) => {
      const cocuk = altlar.get(o.id) || [];
      const kapali = kapaliAltlar.has(o.id) && !cocuk.some((c) => c.id === durum.oturumId);
      const s = el(`<div class="oturum ${alt ? "alt-oturum" : ""} ${durum.gorunum === "sohbet" && o.id === durum.oturumId ? "aktif" : ""}" data-id="${o.id}">
        <span class="ad" title="${kacir(o.baslik)}">${kacir(o.baslik)}</span>${cocuk.length ? `<button class="ikon-btn alt-ac ${kapali ? "kapali" : ""}" title="Alt oturumlar (${cocuk.length})" aria-label="Alt oturumları ${kapali ? "göster" : "gizle"}" aria-expanded="${!kapali}" data-ikon="asagi"></button>` : ""}<button class="ikon-btn daha" title="Diger" data-ikon="daha"></button></div>`);
      s.querySelector(".alt-ac")?.addEventListener("click", (e) => {
        e.stopPropagation();
        kapaliAltlar[kapali ? "delete" : "add"](o.id);
        localStorage.setItem("kapaliAltlar", JSON.stringify([...kapaliAltlar]));
        oturumListesiCiz();
      });
      return [s, kapali ? [] : cocuk];
    };
    const ekle = (o, alt = false) => {
      const [s, cocuk] = satir(o, alt);
      oturumSatiriBagla(s, o, grup);
      cocuk.forEach((c) => ekle(c, true));
    };
    liste.forEach((o) => ekle(o));
    kap.append(grup);
  }
  if (!gruplar.size) kap.append(el(`<div class="ayar-not" style="padding:16px 10px">Henüz sohbet yok.</div>`));
  ikonlariYerlestir(kap);
}

function oturumSatiriBagla(s, o, grup) {
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

/** OpenRouter ya da Ollama seciliyse yerel (llama.cpp) modeller arayuzde gorunmez ve kullanilmaz. */
const uzakMi = () => ["openrouter", "ollama"].includes(durum.ayarlar?.saglayici);
const SAG_AD = { openrouter: "OpenRouter", ollama: "Ollama" };
const uzakModel = () => (durum.ayarlar?.saglayici === "ollama" ? durum.ayarlar.ollama_model : durum.ayarlar?.or_model) || "";

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
    const um = uzakModel();
    const sag = SAG_AD[a.saglayici];
    $("#sunucu-nokta").className = `nokta ${um ? "hazir" : "hata"}`;
    // model adi yalniz mesaj kutusunun altindaki secicide (tekrar etmesin); burada baglanti durumu
    $("#sunucu-metni").textContent = um ? sag : `${sag} · model seçilmedi`;
    const km = projeDurumu.aktif?.koordinator_model; // proje sohbeti bu modelle calisir
    $("#hap-model-metni").textContent = (km || um) ? (km || um).replace(/^ollama:/, "").split("/").pop() : "Model seç"; // Claude gibi kisa ad
    $("#hap-model").title = km ? `Proje koordinatör modeli: ${km}` : um ? `${sag}: ${um}` : "";
    const dus0 = durum.bilgi.dusunme_secenekleri.find((d) => d.deger === a.dusunme);
    $("#hap-dusunme-metni").textContent = dus0 ? dus0.kisa : a.dusunme;
    bantGuncelle();
    bosDurumKartlari();
    agecidiGuncelle();
    return;
  }
  $("#sunucu-nokta").className = `nokta ${s.durum}`;
  $("#hap-nokta").className = `nokta buyuk ${s.durum}`;
  $("#sunucu-metni").textContent = s.durum === "kapali" ? "Model kapalı" : `Yerel model · ${DURUM_METNI[s.durum] || s.durum}`;
  $("#sunucu-metni").title = s.durum === "kapali" ? "" : modelAdi(aktif);
  const b = s.bellek || {};
  $("#ram-metni").textContent = b.bos_gb != null ? `RAM ${sayi(b.bos_gb)}/${sayi(b.toplam_gb, 0)} GB boş` : "";
  $("#hap-model-metni").textContent = a.saglayici === "openrouter" && a.or_model ? a.or_model.split("/").pop() : modelAdi(projeDurumu.aktif?.koordinator_model || a.model);
  const dus = durum.bilgi.dusunme_secenekleri.find((d) => d.deger === a.dusunme);
  $("#hap-dusunme-metni").textContent = dus ? dus.kisa : a.dusunme;
  $("#klasor-metni").textContent = `Model klasörü: ${a.llm_dizin}`;
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
  if (uzakMi() && uzakModel()) {
    // Uzak / Ollama model: yerel RAM/dosya/llama.cpp uyarilari ilgisiz; bant onay kartini da ortuyordu
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

// Claude Code "New session" gibi: ortada PROJE secici (model/dusunme alttaki cubukta kalir).
// En cok kullanilan projeler (sohbet sayisi; esitlikte en son kullanilan), acik olan tikli;
// fazlasi "Daha fazla" menusunde; altta klasor sec.
const ILK_PROJE = 4;
const ONERI_TAZE_MS = 60_000;
const oneriOnbellek = { zaman: 0, liste: [] };
function bosDurumKartlari() {
  const kap = $("#model-kartlari");
  const etkin = projeDurumu.etkin?.id;
  const kullanim = {};
  for (const o of durum.oturumlar || []) if (o.alan) kullanim[o.alan] = (kullanim[o.alan] || 0) + 1;
  const projeler = [...(projeDurumu.liste || [])].sort((x, y) =>
    (kullanim[y.id] || 0) - (kullanim[x.id] || 0) || String(y.guncelleme).localeCompare(String(x.guncelleme)));
  const satir = (p) => {
    const b = el(`<button class="kart-satir ${p.id === etkin ? "secili" : ""}" title="${kacir((p.kokler || []).join("\n"))}">
      <span data-ikon="klasor"></span><span class="kart-ad">${kacir(p.ad)}</span>
      ${p.id === etkin ? '<span class="tik" data-ikon="tik"></span>' : ""}</button>`);
    b.onclick = async () => { await projeyeGec(p.id); bosDurumKartlari(); };
    return b;
  };
  // Durum yoklamasi bunu birkac saniyede bir cagirir: veri ayniysa DOM'a dokunma (titreme/hover kaybi)
  if (Date.now() - oneriOnbellek.zaman > ONERI_TAZE_MS) onerileriYenile();
  const imza = JSON.stringify([etkin, projeler.map((p) => [p.id, p.ad]), oneriOnbellek.liste]);
  if (kap.dataset.imza === imza && kap.childElementCount) return;
  kap.dataset.imza = imza;
  kap.innerHTML = "";
  kap.append(el('<div class="kart-baslik-satir soluk kucuk">Hangi projede çalışalım?</div>'));
  projeler.slice(0, ILK_PROJE).forEach((p) => kap.append(satir(p)));
  const fazla = projeler.slice(ILK_PROJE);
  if (fazla.length) {
    const b = el(`<button class="kart-satir"><span data-ikon="daha"></span><span class="kart-ad">Daha fazla</span><span class="sag">${fazla.length}</span><span data-ikon="sag" class="kucuk-ikon"></span></button>`);
    b.onclick = (e) => menuAc(e.currentTarget, fazla.map((p) => ({
      metin: p.ad, ikon: "klasor", secili: p.id === etkin, eylem: async () => { await projeyeGec(p.id); bosDurumKartlari(); },
    })), { sagaHizali: true });
    kap.append(b);
  }
  kap.append(el('<div class="kart-ayrac"></div>'));
  const yok = el(`<button class="kart-satir ${etkin === KISISEL ? "secili" : ""}"><span data-ikon="ekran"></span><span class="kart-ad">Proje olmadan (kişisel klasörler)</span>${etkin === KISISEL ? '<span class="tik" data-ikon="tik"></span>' : ""}</button>`);
  yok.onclick = async () => { await projeyeGec(KISISEL); bosDurumKartlari(); };
  kap.append(yok);
  const yeni = el('<button class="kart-satir"><span data-ikon="arti"></span><span class="kart-ad">Klasör seç…</span></button>');
  yeni.onclick = () => projeAc();
  kap.append(yeni);
  ikonlariYerlestir(kap);
  onerileriCiz(kap);
}

// Proaktif oneriler (Grok Bot gibi): DURUM.md yarim/acik maddeleri, seni bekleyen thread'ler, yaklasan rutinler.
// Onbellekten senkron cizilir (bos -> dolu ziplamasi yok); sunucudan en fazla dakikada bir yenilenir.
const ONERI_IKON = { durum: "plan", thread: "logo", rutin: "saat" };
async function onerileriYenile() {
  oneriOnbellek.zaman = Date.now(); // istek surerken tekrar tetiklenmesin
  try { oneriOnbellek.liste = (await api("/api/oneriler")).oneriler; } catch { return; }
  if (!$("#bos-durum")?.hidden) bosDurumKartlari(); // degistiyse imza farkli -> bir kez cizilir
}
function onerileriCiz(kap) {
  const liste = oneriOnbellek.liste;
  if (!liste.length) return;
  kap.append(el('<div class="kart-ayrac"></div>'), el('<div class="kart-baslik-satir soluk kucuk">Öneriler</div>'));
  for (const o of liste) {
    const b = el(`<button class="kart-satir" title="${kacir(o.metin)}"><span data-ikon="${ONERI_IKON[o.tur] || "bilgi"}"></span>
      <span class="kart-ad">${kacir(o.metin)}</span><span class="sag soluk kucuk">${kacir(o.ayrinti)}</span></button>`);
    b.onclick = async () => {
      if (o.tur !== "durum") { $(`.nav-oge[data-git="${o.tur === "rutin" ? "rutinler" : "ajanlar"}"]`)?.click(); return; }
      if (o.proje_id && o.proje_id !== projeDurumu.etkin?.id) { await projeyeGec(o.proje_id); bosDurumKartlari(); }
      const g = $("#girdi");
      g.value = `DURUM.md'deki şu maddeye devam et: ${o.metin}`;
      g.dispatchEvent(new Event("input"));
      g.focus();
    };
    kap.append(b);
  }
  ikonlariYerlestir(kap);
}
document.addEventListener("oturumlar-degisti", () => { if (!$("#bos-durum")?.hidden) bosDurumKartlari(); });

function dusunmeMenusu(capa, yukari = true) {
  menuAc(capa, durum.bilgi.dusunme_secenekleri.map((d) => ({
    metin: d.ad, sag: d.sure, secili: d.deger === durum.ayarlar.dusunme, eylem: () => ayarKaydet({ dusunme: d.deger }, true),
  })), { yukari });
}

async function modelMenusu(capa) {
  const a = durum.ayarlar;
  const ogeler = [{ baslik: uzakMi() ? `Model · ${SAG_AD[a.saglayici]}` : "Model" }];
  if (a.saglayici === "ollama") { // Ollama'daki yuklu modeller: tiklayinca secilir
    let liste = [];
    try { liste = (await api("/api/ollama/yuklu")).modeller; } catch (e) { bildir(e.message, "hata"); }
    for (const m of liste) ogeler.push({ metin: m.ad, sag: `${sayi(m.boyut_gb)} GB`, secili: m.ad === a.ollama_model, eylem: () => ayarKaydet({ ollama_model: m.ad }, true) });
    if (!liste.length) ogeler.push({ metin: "Ollama'da model yok", pasif: true });
  } else if (uzakMi()) ogeler.push({ metin: a.or_model || "Model seçilmedi", sag: "uzak", secili: !!a.or_model, eylem: () => ayarlarAc() });
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
    menuAc(capa, [{ baslik: `${SAG_AD[durum.ayarlar.saglayici]} · ${uzakModel() || "model seçilmedi"}` }, "ayrac",
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
  sohbetKur({ oturumlarYenile: oturumlariYenile, baslikAyarla, oturumAc });
  ayarlarKur(hepsiniYenile, (sekme) => {
    git({ tur: "modeller" });
    if (sekme === "ollama") setTimeout(() => $("#ol-kart")?.scrollIntoView({ behavior: "smooth" }), 300);
  });
  sayfalarKur();
  projeKur();
  skillerKur(hepsiniYenile);
  gorevlerKur();
  ozellestirSekmeleri();
  $("#sp-proje").onclick = () => projeAc();
  sagPanelKur({ baglayiciAc: () => ayarlarAc("mcp"), ayarAc: () => ayarlarAc(), degisiklikAc: () => dockAcKapa("degisiklik", true) });
  uzantiYuzeyleriKur();
  dockKur();
  rutinlerKur();
  ajanlarKur();
  eklentilerKur({ git });
  document.addEventListener("oturumlar-degisti", degisiklikYenile);
  $("#baslik-menu").onclick = (e) => baslikMenusu(e.currentTarget);
  $("#btn-paylas").onclick = (e) => baslikMenusu(e.currentTarget);
  $("#btn-daha").onclick = (e) => menuAc(e.currentTarget, [
    { metin: "Yan sohbet (Ctrl+;)", ikon: "yanSohbet", eylem: () => dockAcKapa("yan", true) },
    { metin: "Plan", ikon: "plan", eylem: () => dockAcKapa("plan", true) },
    { metin: "Arka plan işleri", ikon: "arkaPlan", eylem: () => arkaPlanIsleri() },
    { metin: "Ajan görevleri", ikon: "gorevler", eylem: () => git({ tur: "gorevler" }) },
    { metin: "Etkinlik (ne yapıldı)", ikon: "saat", eylem: () => etkinlikAc() },
    { metin: uyanikAcik ? "Uyanık tutmayı kapat" : "Bilgisayarı uyanık tut", ikon: "kahve", eylem: () => uyanikDegistir() },
    "ayrac",
    { metin: "Eklentiler (bağlayıcı, skill, plugin)", ikon: "eklenti", eylem: () => git({ tur: "eklentiler" }) },
    ...(uzakMi() ? [] : [{ metin: "Modeller", ikon: "model", eylem: () => git({ tur: "modeller" }) }]),
    { metin: "Ayarlar", ikon: "disli", eylem: () => ayarlarAc() },
    { metin: "Hakkında", ikon: "bilgi", eylem: () => ayarlarAc("hakkinda") },
  ], { sagaHizali: true });
  dikteKur();
  modellerKur(hepsiniYenile);
  ollamaKur(hepsiniYenile);

  $$(".nav-oge").forEach((n) => {
    n.onclick = () => {
      const h = n.dataset.git;
      if (h === "ara") aramaAc(oturumAc);
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
  setInterval(() => { if (!document.hidden) { durumYenile(); disDegisiklikleriAl(); } }, 3000);
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
