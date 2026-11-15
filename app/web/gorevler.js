// Ajan gorevleri ekrani (A5): gorev baslat, canli adimlar, kontroller, onay, diff ve geri alma.
// GUVENLIK: model metni, dosya icerigi ve komut ciktisi DAIMA kacir() ile basilir; ham HTML yok.
import { ikon, ikonlariYerlestir } from "./ikonlar.js";
import { kacir, md } from "./md.js";
import { diffGoster, reviewYap } from "./inceleme.js";
import { $, $$, api, bildir, durum, el, modal, onayla, sayi } from "./ortak.js";
import { masaustuBildirimi } from "./ayarlar2.js";

// ---- bildirim: durum gecislerinde (onay istendi, rutin bitti) Windows bildirimi ----
const sonDurum = new Map();
function bildirimGerekirse(r) {
  const once = sonDurum.get(r.id);
  sonDurum.set(r.id, r.durum);
  if (once === undefined || once === r.durum) return; // ilk gorus ya da degisiklik yok
  const a = durum.ayarlar || {};
  const ad = (r.hedef || "").slice(0, 80);
  if (r.durum === "cevap_bekliyor" && a.bildirim_onay) masaustuBildirimi("Ajan bir soru soruyor", ad);
  else if (["onay_bekliyor", "karar_bekliyor"].includes(r.durum) && a.bildirim_onay) masaustuBildirimi("Onay bekleniyor", ad);
  else if (BITMIS.has(r.durum) && /^\[(rutin|zamanlanmis)/.test(r.hedef || "") && a.bildirim_zamanlama) masaustuBildirimi(`Rutin: ${(DURUM_TR[r.durum] || [r.durum])[0]}`, ad);
}
export function gorevBildirimIzle() {
  const tur = async () => {
    try { (await api("/api/gorevler")).gorevler.forEach(bildirimGerekirse); } catch { /* sessiz */ }
  };
  tur();
  setInterval(tur, 6000);
}

const DURUM_TR = {
  calisiyor: ["Çalışıyor", "mavi"],
  duraklatildi: ["Duraklatıldı", "sari"],
  onay_bekliyor: ["Onay bekliyor", "sari"],
  karar_bekliyor: ["Karar bekliyor", "sari"],
  cevap_bekliyor: ["Cevabını bekliyor", "sari"],
  iptal: ["İptal edildi", ""],
  basarili: ["Başarılı", "yesil"],
  dogrulanmadi: ["Doğrulanmadı", "sari"],
  basarisiz: ["Başarısız", "kirmizi"],
};
const ADIM_TR = {
  sirada: "sırada", niyet: "çalışıyor", tamam: "tamam", hata: "hata", onay_bekliyor: "onay bekliyor",
  reddedildi: "reddedildi", belirsiz: "belirsiz", atlandi: "atlandı", tekrarla: "tekrarlanacak",
  cevap_bekliyor: "cevap bekliyor",
};
const BITMIS = new Set(["iptal", "basarili", "dogrulanmadi", "basarisiz"]);
const YAZAN = new Set(["proje_dosya_yaz", "proje_dosya_yama", "proje_dosya_tasi", "proje_dosya_sil"]);

let secili = null;
let kapOverride = null; // sohbet icinde gosterimde gorev o mesajin kutusuna cizilir
const detayKabi = () => kapOverride || $("#gr-detay");
let sonCizilen = ""; // degismeyen gorevi yeniden cizme: tiklanan dugme DOM'dan kalkmasin
let zamanlayici = null;
const acikAdimlar = new Set();

function rozet(durum) {
  const [ad, renk] = DURUM_TR[durum] || [durum, ""];
  return `<span class="rozet ${renk}">${kacir(ad)}</span>`;
}

function cubuk(etiket, deger, sinir, birim = "") {
  if (!sinir) { // 0 = sinirsiz (adim butcesi varsayilani): cubuk yok, yalniz sayi
    return `<div class="butce-satir"><span class="soluk kucuk">${kacir(etiket)}</span><span class="kucuk">${kacir(sayi(deger, 0))}${kacir(birim)} · sınırsız</span></div>`;
  }
  const yuzde = Math.min(100, Math.round((100 * deger) / Math.max(1, sinir)));
  return `<div class="butce-satir" title="${kacir(etiket)}: ${kacir(deger)} / ${kacir(sinir)}">
    <span class="soluk kucuk">${kacir(etiket)}</span>
    <div class="butce-cubuk" role="progressbar" aria-label="${kacir(etiket)}" aria-valuenow="${yuzde}" aria-valuemin="0" aria-valuemax="100"><span style="width:${yuzde}%"></span></div>
    <span class="kucuk">${kacir(sayi(deger, 0))}${kacir(birim)} / ${kacir(sayi(sinir, 0))}${kacir(birim)}</span></div>`;
}

function argOzet(a) {
  return Object.entries(a.argumanlar || {})
    .filter(([k]) => !["icerik", "yeni_metin", "eski_metin", "beklenen_hash"].includes(k))
    .map(([k, v]) => `${k}=${String(typeof v === "string" ? v : JSON.stringify(v)).slice(0, 60)}`)
    .join(", ");
}

function sonucMetni(a) {
  try {
    const v = JSON.parse(a.sonuc);
    if (typeof v.cikti === "string") return v.cikti; // komut: gercek terminal ciktisi
    if (typeof v.icerik === "string") return v.icerik;
    if (v.hata) return v.hata;
    return JSON.stringify(v, null, 1);
  } catch {
    return a.sonuc || "";
  }
}

function adimSatiri(a) {
  const durumRenk = { tamam: "yesil", hata: "kirmizi", reddedildi: "kirmizi", belirsiz: "sari", onay_bekliyor: "sari" }[a.durum] || "";
  const kod = a.cikis_kodu === null || a.cikis_kodu === undefined ? "" : `<span class="rozet ${a.cikis_kodu === 0 ? "yesil" : "kirmizi"}">çıkış ${kacir(a.cikis_kodu)}</span>`;
  const acik = acikAdimlar.has(a.no);
  return `<li class="adim" data-no="${kacir(a.no)}">
    <button class="adim-baslik" aria-expanded="${acik}" data-ac="${kacir(a.no)}">
      <span class="soluk kucuk">${kacir(a.no)}</span> <code>${kacir(a.arac)}</code>
      <span class="adim-arg soluk">${kacir(argOzet(a))}</span>
      <span class="rozet ${durumRenk}">${kacir(ADIM_TR[a.durum] || a.durum)}</span>${kod}
      ${a.checkpoint && YAZAN.has(a.arac) ? `<span class="rozet">değişiklik</span>` : ""}
    </button>
    ${acik ? `<div class="adim-govde">
      <pre class="adim-cikti">${kacir(sonucMetni(a))}</pre>
      ${a.checkpoint ? `<button class="btn" data-diff="${kacir(a.checkpoint)}"><span data-ikon="dosya"></span>Diff ve geri alma</button>` : ""}
    </div>` : ""}
  </li>`;
}

// ---- Sohbet akisi Claude Code gibi: ardisik arac adimlari tek katlanir grup
// ("2 komut çalıştırıldı ›"); her adim okunur baslik, acilinca kutuda "$ komut" + cikti. ----
const KOMUTLAR = new Set(["komut_calistir", "komut_girdi", "skill_scripti"]);
function adimTuru(a) {
  if (KOMUTLAR.has(a.arac) || /(powershell|bash|shell|terminal|cmd)$/i.test(a.arac)) return "komut";
  if (YAZAN.has(a.arac)) return "yaz";
  if (/oku$/.test(a.arac)) return "oku";
  if (/(ara|glob|listele)$/.test(a.arac)) return "ara";
  return "diger";
}
const TUR_AD = { komut: "komut çalıştırıldı", oku: "dosya okundu", yaz: "dosyada değişiklik", ara: "arama yapıldı", diger: "araç kullanıldı" };
const SURUYOR = new Set(["sirada", "niyet", "onay_bekliyor", "cevap_bekliyor"]);

function adimBasligi(a) {
  const g = a.argumanlar || {};
  if (g.aciklama) return String(g.aciklama);
  const tur = adimTuru(a);
  if (tur === "komut") return String(g.komut || g.command || g.metin || a.arac);
  if (g.yol) return `${{ oku: "Okundu", yaz: "Değiştirildi" }[tur] || a.arac}: ${g.yol}`;
  if (g.desen) return `Arandı: ${g.desen}`;
  return `${a.arac} ${argOzet(a)}`.trim();
}

function ccAdim(a) {
  const g = a.argumanlar || {};
  const acik = acikAdimlar.has(a.no);
  const komut = adimTuru(a) === "komut";
  const giris = komut ? `$ ${g.komut || g.command || g.metin || ""}` : argOzet(a);
  const durumRozet = a.durum === "tamam" ? "" : `<span class="rozet ${{ hata: "kirmizi", reddedildi: "kirmizi" }[a.durum] || "sari"}">${kacir(ADIM_TR[a.durum] || a.durum)}</span>`;
  const kod = a.cikis_kodu ? `<span class="rozet kirmizi">çıkış ${kacir(a.cikis_kodu)}</span>` : "";
  return `<li class="cc-adim">
    <button class="cc-baslik" aria-expanded="${acik}" data-ac="${kacir(a.no)}">
      <span class="cc-ad">${kacir(adimBasligi(a))}</span>${durumRozet}${kod}<span class="cc-ok" aria-hidden="true">›</span>
    </button>
    ${acik ? `<div class="cc-kutu">
      ${giris ? `<pre class="cc-giris">${kacir(giris)}</pre>` : ""}
      ${a.sonuc ? `<pre class="cc-cikti">${kacir(sonucMetni(a))}</pre>` : ""}
      ${a.checkpoint ? `<button class="btn kucuk" data-diff="${kacir(a.checkpoint)}"><span data-ikon="dosya"></span>Diff ve geri alma</button>` : ""}
    </div>` : ""}
  </li>`;
}

function ccGrup(adimlar, sonGrupCalisiyor) {
  const sayac = new Map();
  for (const a of adimlar) sayac.set(adimTuru(a), (sayac.get(adimTuru(a)) || 0) + 1);
  const ozet = [...sayac].map(([t, n]) => `${n} ${TUR_AD[t]}`).join(", ");
  const anahtar = `g${adimlar[0].no}`;
  // calisan/onay bekleyen son grup acik baslar; kullanici tiklarsa varsayilanin tersi
  const varsayilan = sonGrupCalisiyor || adimlar.some((a) => a.durum === "onay_bekliyor");
  const acik = varsayilan !== acikAdimlar.has(anahtar);
  const hata = adimlar.some((a) => ["hata", "reddedildi"].includes(a.durum) || a.cikis_kodu);
  const suruyor = adimlar.some((a) => SURUYOR.has(a.durum));
  return `<li class="cc-grup">
    <button class="cc-grup-baslik" aria-expanded="${acik}" data-grup="${anahtar}">
      <span>${kacir(ozet)}</span>${suruyor ? '<span class="parilti kucuk">sürüyor</span>' : ""}${hata ? '<span class="rozet kirmizi">hata</span>' : ""}<span class="cc-ok" aria-hidden="true">›</span>
    </button>
    ${acik ? `<ol class="cc-liste">${adimlar.map(ccAdim).join("")}</ol>` : ""}
  </li>`;
}

function ccAkis(adimlar, calisiyor) {
  const parcalar = [];
  let grup = [];
  const kapat = (son = false) => {
    if (grup.length) parcalar.push(ccGrup(grup, son && calisiyor));
    grup = [];
  };
  for (const a of adimlar) {
    if (a.aciklama) {
      kapat();
      parcalar.push(`<li class="ajan-aciklama">${md(a.aciklama)}</li>`);
    }
    grup.push(a);
  }
  kapat(true);
  return parcalar.join("");
}

function kontroller(r) {
  const b = (is, ad, kosul, tehlike = false) =>
    `<button class="btn kucuk ${tehlike ? "tehlike" : ""}" data-islem="${is}" ${kosul ? "" : "disabled"}>${ad}</button>`;
  return `<div class="dugme-sira">
    ${b("duraklat", "Duraklat", r.durum === "calisiyor")}
    ${b("devam", "Devam", ["duraklatildi", "onay_bekliyor"].includes(r.durum))}
    ${b("iptal", "İptal", !BITMIS.has(r.durum), true)}
    ${b("tekrar", "Tekrar dene", ["basarisiz", "iptal", "dogrulanmadi"].includes(r.durum))}
  </div>`;
}

// Kullanici NEYI onayladigini gormeli: onay bu degisikligin kendisine baglidir (yola degil).
function onayOnizleme(a) {
  const g = a.argumanlar || {};
  const sinirla = (m) => String(m).split("\n").slice(0, 30).join("\n");
  if (a.arac === "proje_dosya_yama") {
    const satir = (on, m) => sinirla(m).split("\n").map((x) => `<div class="diff-${on === "-" ? "eksi" : "arti"}">${on} ${kacir(x)}</div>`).join("");
    return `<div class="diff">${satir("-", g.eski_metin || "")}${satir("+", g.yeni_metin || "")}</div>`;
  }
  if (a.arac === "proje_dosya_yaz") return `<pre class="adim-cikti">${kacir(sinirla(g.icerik || ""))}</pre>`;
  if (a.arac === "komut_calistir" || a.arac === "komut_girdi") return `<pre class="adim-cikti">${kacir(g.komut || g.command || g.metin || "")}</pre>`;
  return "";
}

function bekleyenKartlari(r) {
  const parcalar = [];
  for (const a of r.adimlar) {
    if (a.durum === "onay_bekliyor" && a.onay_id) {
      parcalar.push(`<div class="uyari-kutu" role="alert">
        <b>Onay gerekiyor:</b> adım ${kacir(a.no)} <code>${kacir(a.arac)}</code> ${kacir(argOzet(a))}
        ${onayOnizleme(a)}
        <div class="dugme-sira"><button class="btn ana" data-onay="${kacir(a.onay_id)}" data-karar="1" data-kapsam="tek">Bir kez izin ver</button>
        <button class="btn" data-onay="${kacir(a.onay_id)}" data-karar="1" data-kapsam="sohbet" title="Bu görevde aynı türden işlemler bir daha sorulmaz">Bu görev için izin ver</button>
        <button class="btn" data-onay="${kacir(a.onay_id)}" data-karar="1" data-kapsam="her_zaman" title="Aynı türden işlem bir daha hiç sorulmaz; Ayarlar > Onay kuralları'ndan kaldırılabilir">Her zaman izin ver</button>
        <button class="btn tehlike" data-onay="${kacir(a.onay_id)}" data-karar="0">Reddet</button></div></div>`);
    }
    if (a.durum === "cevap_bekliyor") { // soru_sor: ajan kullanicidan karar bekliyor
      const g = a.argumanlar || {};
      const secenekler = (Array.isArray(g.secenekler) ? g.secenekler : []).slice(0, 4).map((x) => String(x).slice(0, 200));
      parcalar.push(`<div class="uyari-kutu soru-kart" role="alert">
        <b>Ajan soruyor:</b> <span class="soru-metin">${kacir(g.soru || "")}</span>
        ${secenekler.length ? `<div class="dugme-sira">${secenekler.map((x) => `<button class="btn" data-cevap="${kacir(x)}">${kacir(x)}</button>`).join("")}</div>` : ""}
        <div class="satir"><input class="alan" id="gr-cevap" placeholder="Cevabını yaz (Enter)" maxlength="4000" style="flex:1" aria-label="Ajanın sorusuna cevap">
        <button class="btn ana" data-cevap-gonder>Gönder</button></div></div>`);
    }
    if (a.durum === "belirsiz") {
      parcalar.push(`<div class="uyari-kutu" role="alert">
        <b>Sonucu belirsiz adım:</b> ${kacir(a.no)} <code>${kacir(a.arac)}</code> - uygulama bu adım sırasında kapandı. Ne yapılsın?
        <div class="dugme-sira">
          <button class="btn" data-belirsiz="${kacir(a.no)}" data-k="tamamlandi">Tamamlandı say</button>
          <button class="btn" data-belirsiz="${kacir(a.no)}" data-k="atla">Uygulanmadı say</button>
          <button class="btn tehlike" data-belirsiz="${kacir(a.no)}" data-k="tekrarla">Tekrar çalıştır</button></div></div>`);
    }
  }
  return parcalar.join("");
}

// Claude Code Desktop gibi: sohbette sade akis (adim satirlari, onay kartlari, sonuc);
// plan, baglam, butce ve degisen dosyalar SAG PANELDE.
function sohbetCiz(r) {
  const kap = detayKabi();
  const basari = r.durum === "basarili" && r.sonuc?.dogrulandi;
  // Claude Code gibi: modelin "ne ve neden" cumlesi, ait oldugu aracin USTUNDE akar
  const aciklamalar = new Set(r.adimlar.map((a) => a.aciklama).filter(Boolean));
  const notlar = (r.guncellemeler || [])
    .filter((g) => !g.startsWith("Kullanici:") && !g.startsWith("Onay bekleniyor") && ![...aciklamalar].some((x) => x.startsWith(g.slice(0, 200))))
    .slice(-2);
  const calisiyor = !BITMIS.has(r.durum);
  const akis = ccAkis(r.adimlar.filter((a) => a.arac !== "plan_guncelle" && a.arac !== "gorevi_bitir"), calisiyor);
  kap.innerHTML = `
    <ol class="adim-liste sade">${akis}</ol>
    ${notlar.map((g) => `<div class="ajan-not md">${md(g)}</div>`).join("")}
    ${calisiyor ? `<div class="baykus-canli" data-mod="${r.durum === "calisiyor" ? "calisiyor" : "bekliyor"}" style="--bk-gecikme:-${(Date.now() / 1000 % 3600).toFixed(2)}s"><span class="baykus-kap">${ikon("logo")}</span><span class="baykus-etiket">${r.durum === "calisiyor" ? "Çalışıyor…" : "Onay bekliyor…"}</span></div>` : ""}
    ${bekleyenKartlari(r)}
    ${r.hata ? `<div class="uyari-kutu kucuk">${kacir(r.hata)}</div>` : ""}
    ${r.sonuc?.ozet ? `<div class="ajan-sonuc ajan-rapor"><div class="rapor-baslik">${basari ? '<span data-ikon="tik" class="yesil-ikon" aria-label="doğrulandı"></span> Tamamlandı' : "Sonuç"}${r.sonuc.kanit?.length ? ` <span class="soluk kucuk">(kanıt: adım ${kacir(r.sonuc.kanit.join(", "))})</span>` : ' <span class="rozet sari" title="Ajan, son dosya değişikliğinden sonra başarılı bir araç adımını kanıt olarak göstermedi. Cevap yanlış demek değil; otomatik kontrol edilmedi demek.">doğrulanmadı</span>'}<button class="ikon-btn" title="Cevabı kopyala" aria-label="Cevabı kopyala" data-kopya data-ikon="kopyala"></button></div><div class="md">${md(r.sonuc.ozet)}</div></div>` : ""}
    ${incelemeHtml(r.inceleme)}
    ${r.calisma_koku && r.dal ? `<div class="ajan-izole soluk kucuk">Ayrı dalda çalıştı: <code>${kacir(r.dal)}</code>${["basarili", "dogrulanmadi"].includes(r.durum) ? `
      <div class="satir"><input class="alan" data-entegre-test placeholder="Birleştirmeden önce test komutu (isteğe bağlı)" style="flex:1">
      <button class="btn ana" data-entegre>Ana dala birleştir</button><button class="btn tehlike" data-at>Değişiklikleri at</button></div>` : ""}</div>` : ""}
    <div class="ajan-kontrol">${rozet(r.durum)}${kontroller(r)}</div>`;
  const ent = kap.querySelector("[data-entegre]");
  if (ent) {
    ent.onclick = async () => {
      ent.disabled = true;
      try {
        const s = await api(`/api/gorevler/${r.id}/entegre`, { method: "POST", govde: { test_komutu: kap.querySelector("[data-entegre-test]").value } });
        const mesaj = { birlestirildi: "Ana dala birleştirildi.", degisiklik_yok: "Birleştirilecek değişiklik yok.",
          test_basarisiz: "Test başarısız; birleştirilmedi.", kullanici_degisikligi_var: s.not, catisma: `Çakışma: ${(s.catisan || []).join(", ")}. ${s.not}` }[s.durum] || s.durum;
        bildir(mesaj, s.durum === "birlestirildi" ? "basari" : "uyari", 6000);
      } catch (e) { bildir(e.message, "hata"); } finally { ent.disabled = false; }
    };
    kap.querySelector("[data-at]").onclick = async () => {
      if (!(await onayla("Değişiklikleri at", "Ajanın ayrı daldaki tüm değişiklikleri silinsin mi? Ana dala dokunulmaz.", { evet: "At", tehlike: true }))) return;
      try { await api(`/api/gorevler/${r.id}/at`, { method: "POST" }); bildir("Atıldı.", "basari", 1500); } catch (e) { bildir(e.message, "hata"); }
    };
  }
  ikonlariYerlestir(kap);
  baglantilar(r);
  sagPanelCiz(r);
}

function sagPanelCiz(r) {
  const p = document.getElementById("sag-panel-gorev");
  if (!p) return;
  const b = r.baglam || {};
  const degisen = r.adimlar.filter((a) => a.checkpoint && YAZAN.has(a.arac));
  p.innerHTML = `
    ${b.baglam ? `<div class="sp-baslik">Bağlam <span class="soluk">%${kacir(b.dolu_yuzde)}</span></div>
      <div class="butce-cubuk" role="progressbar" aria-label="Bağlam doluluğu" aria-valuenow="${kacir(b.dolu_yuzde)}"><span style="width:${Math.min(100, b.dolu_yuzde)}%"></span></div>` : ""}
    <div class="sp-baslik">Plan</div>
    <ul class="plan-liste">${(r.plan || []).map((x) => `<li class="plan-${kacir(x.durum)}">${kacir(x.baslik)}</li>`).join("") || '<li class="soluk">-</li>'}</ul>
    <div class="sp-baslik">Değişen dosyalar</div>
    <ul class="sp-dosyalar">${degisen.map((a) => `<li><button class="bag" data-diff="${kacir(a.checkpoint)}"><span data-ikon="dosya"></span>${kacir(a.dosya || a.argumanlar?.yol || a.arac)}</button></li>`).join("") || '<li class="soluk">-</li>'}</ul>
    <div class="sp-baslik">Bütçe</div>
    ${cubuk("Adım", r.kullanim.adim, r.butce.max_adim)}
    ${cubuk("Süre", r.kullanim.sure_sn, r.butce.max_sure_sn, " sn")}
    ${(r.cocuklar || []).length ? '<div class="sp-baslik">Alt ajanlar</div><div id="sp-cocuklar" class="soluk kucuk">yükleniyor…</div>' : ""}`;
  ikonlariYerlestir(p);
  $$("[data-diff]", p).forEach((x) => { x.onclick = () => diffAc(x.dataset.diff); });
  if ((r.cocuklar || []).length) altAjanlariCiz(r.cocuklar);
  takimCiz(p, r.id);
}

// Takim panosu (A8.2): ortak gorev listesi ve mesajlar; bos ise hic gosterilmez
async function takimCiz(panel, runId) {
  let t;
  try { t = await api(`/api/gorevler/${runId}/takim`); } catch { return; }
  if (!panel.isConnected || (!t.gorevler.length && !t.mesajlar.length)) return;
  const durumTr = { acik: "açık", alindi: "alındı", tamam: "tamam" };
  const kutu = el(`<div><div class="sp-baslik">Takım panosu</div>
    <ul class="plan-liste">${t.gorevler.map((g) => `<li class="plan-${g.durum === "tamam" ? "tamam" : "bekliyor"}">${kacir(g.baslik)} <span class="soluk kucuk">${kacir(durumTr[g.durum] || g.durum)}${g.sahip ? ` · ${kacir(g.sahip)}` : ""}${g.bagimli.length ? ` · bekler: ${kacir(g.bagimli.join(", "))}` : ""}</span></li>`).join("")}</ul>
    ${t.mesajlar.length ? `<div class="sp-baslik">Mesajlar</div>${t.mesajlar.slice(-8).map((m) => `<div class="kucuk"><b>${kacir(m.kimden)}</b> → ${kacir(m.kime)}: ${kacir(m.metin.slice(0, 160))}</div>`).join("")}` : ""}</div>`);
  panel.append(kutu);
}

// Agent View: hangi alt ajan, hangi dosyaya ve hangi araclara yetkili, durumu ne
async function altAjanlariCiz(idler) {
  const kap = document.getElementById("sp-cocuklar");
  const cocuklar = await Promise.all(idler.map((id) => api(`/api/gorevler/${id}`).catch(() => null)));
  if (!kap?.isConnected) return;
  kap.classList.remove("soluk", "kucuk");
  kap.innerHTML = cocuklar.filter(Boolean).map((c) => `<div class="alt-ajan">
    <div>${rozet(c.durum)} ${kacir(c.hedef.slice(0, 70))}</div>
    <div class="soluk kucuk">Yazabilir: ${kacir(c.sahip_dosyalar.join(", ") || "hiçbir dosya")}</div>
    <div class="soluk kucuk">Araçlar: ${kacir(c.izinli_araclar.join(", "))}</div>
    <div class="soluk kucuk">Adım ${kacir(c.kullanim.adim)}${c.butce.max_adim ? `/${kacir(c.butce.max_adim)}` : ""}${c.sonuc?.ozet ? ` · ${kacir(c.sonuc.ozet.slice(0, 80))}` : ""}</div></div>`).join("");
}

function detayCiz(r) {
  if (kapOverride) { sohbetCiz(r); return; }
  const kap = detayKabi();
  const basari = r.durum === "basarili" && r.sonuc?.dogrulandi; // ikon yalniz gercek kanittan
  const b = r.baglam || {};
  kap.innerHTML = `
    <div class="gr-ust">
      <div><div class="gr-hedef">${basari ? '<span data-ikon="tik" class="yesil-ikon" aria-label="doğrulandı"></span>' : ""}${kacir(r.hedef)}</div>
        <div class="soluk kucuk">${rozet(r.durum)} model <code>${kacir(r.model || "-")}</code> · deneme ${kacir(r.deneme)} · ${kacir(r.olusturma)}</div></div>
      ${kontroller(r)}
    </div>
    ${r.hata ? `<div class="uyari-kutu kucuk">${kacir(r.hata)}</div>` : ""}
    ${bekleyenKartlari(r)}
    ${r.sonuc?.ozet ? `<div class="kart"><div class="kart-baslik"><b>Sonuç</b>${r.sonuc.kanit?.length ? `<span class="soluk kucuk">kanıt: adım ${kacir(r.sonuc.kanit.join(", "))}</span>` : '<span class="rozet sari">kanıtsız</span>'}</div><div>${kacir(r.sonuc.ozet)}</div></div>` : ""}
    <div class="gr-izgara">
      <div class="kart"><div class="kart-baslik"><b>Adımlar</b><span class="soluk kucuk">${kacir(r.adimlar.length)}</span></div>
        <ol class="adim-liste">${r.adimlar.map(adimSatiri).join("") || '<li class="soluk">Henüz adım yok.</li>'}</ol></div>
      <div class="gr-yan">
        <div class="kart"><div class="kart-baslik"><b>Plan</b></div>
          <ul class="plan-liste">${(r.plan || []).map((p) => `<li class="plan-${kacir(p.durum)}">${kacir(p.baslik)}${p.kanit ? ` <span class="soluk kucuk">(${kacir(p.kanit)})</span>` : ""}</li>`).join("") || '<li class="soluk">Plan yok.</li>'}</ul></div>
        <div class="kart"><div class="kart-baslik"><b>Bütçe</b></div>
          ${cubuk("Adım", r.kullanim.adim, r.butce.max_adim)}
          ${cubuk("Süre", r.kullanim.sure_sn, r.butce.max_sure_sn, " sn")}
          ${cubuk("Token", r.kullanim.token, r.butce.max_token)}
          ${b.baglam ? `<div class="soluk kucuk">Bağlam: sistem ${kacir(b.sistem)} · araçlar ${kacir(b.araclar)} · mesaj ${kacir(b.mesajlar)} · kanıt ${kacir(b.kanit)} · cevap ${kacir(b.cevap)} = ${kacir(b.toplam)} / ${kacir(b.baglam)} (%${kacir(b.dolu_yuzde)})${r.ozet_sayisi ? ` · ${kacir(r.ozet_sayisi)} kez özetlendi` : ""}</div>` : ""}</div>
        <div class="kart"><div class="kart-baslik"><b>Güncellemeler</b></div>
          <ul class="guncelleme-liste">${(r.guncellemeler || []).slice(-12).map((g) => `<li>${kacir(g)}</li>`).join("") || '<li class="soluk">-</li>'}</ul>
          ${BITMIS.has(r.durum) ? "" : `<div class="satir"><input class="alan" id="gr-yonlendir" placeholder="Ajana yönlendirme yaz (sonraki adımdan önce işlenir)" style="flex:1" maxlength="4000" aria-label="Ajana yönlendirme">
            <button class="btn" id="gr-yonlendir-gonder">Gönder</button></div>`}</div>
      </div>
    </div>`;
  ikonlariYerlestir(kap);
  baglantilar(r);
}

function baglantilar(r) {
  const kap = detayKabi();
  const sarmala = (is) => async () => {
    try { await is(); await gorevYenile(); } catch (e) { bildir(e.message, "hata"); }
  };
  $$("[data-islem]", kap).forEach((b) => {
    b.onclick = sarmala(async () => {
      if (b.dataset.islem === "iptal" && !(await onayla("Görevi iptal et", "Çalışan görev durdurulsun mu? Yapılan dosya değişiklikleri geri alınmaz (checkpoint'ten ayrıca geri alabilirsiniz).", { evet: "İptal et", tehlike: true }))) return;
      await api(`/api/gorevler/${r.id}/${b.dataset.islem}`, { method: "POST" });
    });
  });
  $$("[data-kopya]", kap).forEach((b) => {
    b.onclick = async () => {
      try {
        await navigator.clipboard.writeText(r.sonuc?.ozet || "");
        bildir("Cevap kopyalandı.", "basari", 1500);
      } catch { bildir("Kopyalanamadı.", "hata"); }
    };
  });
  $$("[data-onay]", kap).forEach((b) => {
    b.onclick = sarmala(() => api(`/api/onaylar/${b.dataset.onay}`, { method: "POST", govde: { onayla: b.dataset.karar === "1", kapsam: b.dataset.kapsam || "tek" } }));
  });
  $$("[data-belirsiz]", kap).forEach((b) => {
    b.onclick = sarmala(() => api(`/api/gorevler/${r.id}/karar`, { method: "POST", govde: { adim: Number(b.dataset.belirsiz), karar: b.dataset.k } }));
  });
  const cevapla = (metin) => sarmala(async () => {
    if (!metin.trim()) return;
    await api(`/api/gorevler/${r.id}/mesaj`, { method: "POST", govde: { metin: metin.trim() } });
  })();
  $$("[data-cevap]", kap).forEach((b) => { b.onclick = () => cevapla(b.dataset.cevap); });
  const cevap = $("#gr-cevap", kap);
  if (cevap) {
    $("[data-cevap-gonder]", kap).onclick = () => cevapla(cevap.value);
    cevap.onkeydown = (e) => { if (e.key === "Enter") cevapla(cevap.value); };
  }
  $$("[data-ac]", kap).forEach((b) => {
    b.onclick = () => {
      const no = Number(b.dataset.ac);
      if (acikAdimlar.has(no)) acikAdimlar.delete(no); else acikAdimlar.add(no);
      detayCiz(r);
      $(`[data-ac="${no}"]`, kap)?.focus();
    };
  });
  $$("[data-grup]", kap).forEach((b) => {
    b.onclick = () => {
      const k = b.dataset.grup;
      if (acikAdimlar.has(k)) acikAdimlar.delete(k); else acikAdimlar.add(k);
      detayCiz(r);
      $(`[data-grup="${k}"]`, kap)?.focus();
    };
  });
  $$("[data-diff]", kap).forEach((b) => { b.onclick = () => diffAc(b.dataset.diff); });
  const g = $("#gr-yonlendir", kap);
  if (g) {
    const gonder = sarmala(async () => {
      if (!g.value.trim()) return;
      await api(`/api/gorevler/${r.id}/mesaj`, { method: "POST", govde: { metin: g.value.trim() } });
      g.value = "";
      bildir("Yönlendirme sıraya alındı.", "basari", 1500);
    });
    $("#gr-yonlendir-gonder", kap).onclick = gonder;
    g.onkeydown = (e) => { if (e.key === "Enter") gonder(); };
  }
}

// ---------------- diff / checkpoint geri alma ----------------
function hunkHtml(h) {
  const satirlar = (on, metin) => metin.split("\n").filter((s, i, d) => s || i < d.length - 1)
    .map((s) => `<div class="diff-${on === "-" ? "eksi" : "arti"}">${on} ${kacir(s)}</div>`).join("");
  return `<label class="hunk"><input type="checkbox" value="${kacir(h.no)}" aria-label="Blok ${kacir(h.no + 1)} seç">
    <div><div class="soluk kucuk">blok ${kacir(h.no + 1)} · satır ${kacir(h.satir)}</div>
    <div class="diff">${satirlar("-", h.eski)}${satirlar("+", h.yeni)}</div></div></label>`;
}

export async function diffAc(cpId) {
  let o;
  try { o = await api(`/api/checkpointler/${cpId}`); } catch (e) { bildir(e.message, "hata"); return; }
  const govde = el('<div class="diff-modal"></div>');
  const ciz = async () => {
    const parcalar = [];
    for (const d of o.dosyalar) {
      let hunk = "";
      if (d.islem === "degistir" && !d.cakisma) {
        try {
          const h = await api(`/api/checkpointler/${cpId}/hunklar?yol=${encodeURIComponent(d.yol)}`);
          hunk = h.hunklar.map(hunkHtml).join("") || '<div class="soluk">Fark yok.</div>';
        } catch (e) { hunk = `<div class="uyari-kutu kucuk">${kacir(e.message)}</div>`; }
      }
      parcalar.push(`<div class="kart" data-yol="${kacir(d.yol)}">
        <div class="kart-baslik"><b>${kacir(d.yol)}</b><span class="rozet ${d.cakisma ? "kirmizi" : ""}">${kacir(d.durum)}</span></div>
        ${d.cakisma ? '<div class="uyari-kutu kucuk">Dosya ajandan sonra değişmiş; senin değişikliğini korumak için geri alınamaz.</div>' : ""}
        ${hunk}
        ${d.islem === "degistir" && !d.cakisma ? '<button class="btn" data-hunk-geri>Seçili blokları geri al</button>' : ""}
      </div>`);
    }
    govde.innerHTML = `<div class="soluk kucuk">${kacir(o.aciklama)} · ${kacir(o.zaman)}${o.geri_alindi ? " · geri alındı" : ""}</div>${parcalar.join("")}`;
    $$("[data-hunk-geri]", govde).forEach((b) => {
      b.onclick = async () => {
        const kart = b.closest("[data-yol]");
        const hunklar = $$("input[type=checkbox]:checked", kart).map((c) => Number(c.value));
        if (!hunklar.length) { bildir("Önce blok seçin.", "uyari"); return; }
        try {
          await api(`/api/checkpointler/${cpId}/hunk-geri-al`, { method: "POST", govde: { yol: kart.dataset.yol, hunklar } });
          bildir("Seçili bloklar geri alındı.", "basari", 1500);
          o = await api(`/api/checkpointler/${cpId}`);
          await ciz();
        } catch (e) { bildir(e.message, "hata"); }
      };
    });
  };
  await ciz();
  modal({
    baslik: "Değişiklik ve geri alma",
    icerik: govde,
    genis: true,
    dugmeler: [
      {
        metin: "Tüm değişikliği geri al",
        tur: "tehlike",
        eylem: async (kapat) => {
          if (!(await onayla("Geri al", "Bu checkpoint'teki tüm dosyalar eski haline dönsün mü? Sonradan değişmiş dosyalara dokunulmaz.", { evet: "Geri al", tehlike: true }))) return;
          try {
            const s = await api(`/api/checkpointler/${cpId}/geri-al`, { method: "POST", govde: { yollar: [] } });
            bildir(s.cakisan.length ? `Çakışan dosyalar korundu: ${s.cakisan.length}` : "Geri alındı.", s.cakisan.length ? "uyari" : "basari");
            kapat();
          } catch (e) { bildir(e.message, "hata"); }
        },
      },
      { metin: "Kapat" },
    ],
  });
}

// ---------------- liste ve baslatma ----------------
async function listeCiz() {
  const kap = $("#gr-liste");
  try {
    const { gorevler } = await api("/api/gorevler");
    kap.innerHTML = gorevler.map((g) => `<li><button class="gr-oge ${g.id === secili ? "aktif" : ""}" data-gorev="${kacir(g.id)}" aria-current="${g.id === secili}">
      ${rozet(g.durum)}<span class="gr-oge-hedef">${kacir(g.hedef.slice(0, 80))}</span></button></li>`).join("")
      || '<li class="soluk kucuk">Henüz görev yok.</li>';
    $$("[data-gorev]", kap).forEach((b) => { b.onclick = () => sec(b.dataset.gorev); });
  } catch (e) {
    kap.innerHTML = `<li class="uyari-kutu kucuk">${kacir(e.message)}</li>`;
  }
}

async function gorevYenile(zorla = true) {
  if (!secili) return;
  try {
    const r = await api(`/api/gorevler/${secili}`);
    // guncelleme saniye hassasiyetinde: ayni saniyedeki degisiklik kacmasin diye tum icerik
    const imza = JSON.stringify(r) + [...acikAdimlar].join(",");
    if (!zorla && imza === sonCizilen) return;
    sonCizilen = imza;
    // kullanici yazarken yeniden cizme girdiyi silmesin
    const g = $("#gr-yonlendir");
    const yazilan = g?.value;
    const cevapYazilan = $("#gr-cevap", detayKabi())?.value;
    const odak = document.activeElement?.id;
    detayCiz(r);
    if (yazilan && $("#gr-yonlendir")) $("#gr-yonlendir").value = yazilan;
    if (cevapYazilan && $("#gr-cevap", detayKabi())) $("#gr-cevap", detayKabi()).value = cevapYazilan;
    if (odak) document.getElementById(odak)?.focus();
    if (BITMIS.has(r.durum) || ["onay_bekliyor", "karar_bekliyor", "cevap_bekliyor", "duraklatildi"].includes(r.durum)) {
      listeCiz();
    }
    bildirimGerekirse(r);
  } catch (e) {
    detayKabi().innerHTML = `<div class="uyari-kutu">${kacir(e.message)}</div>`;
  }
}

function sec(id) {
  secili = id;
  acikAdimlar.clear();
  listeCiz();
  gorevYenile();
}

async function ustBilgi() {
  try {
    const y = await api("/api/model/yetenek");
    $("#gr-model").innerHTML = `Model: <code>${kacir(y.model)}</code> (${kacir(y.saglayici)}) · bağlam ${kacir(y.baglam)}${y.araclar ? "" : ' · <span class="rozet kirmizi">araç desteği yok</span>'}`;
  } catch { $("#gr-model").textContent = ""; }
}

async function baslat() {
  const hedef = $("#gr-hedef").value.trim();
  if (!hedef) { bildir("Görev hedefini yazın.", "uyari"); return; }
  const kabul = $("#gr-kabul").value.split("\n").map((s) => s.trim()).filter(Boolean);
  const butce = { max_adim: Number($("#gr-adim").value) || 0, max_sure_sn: (Number($("#gr-sure").value) || 30) * 60 };
  const b = $("#gr-baslat");
  b.disabled = true;
  try {
    const r = await api("/api/gorevler", { method: "POST", govde: { hedef, kabul, butce } });
    $("#gr-hedef").value = "";
    $("#gr-kabul").value = "";
    sec(r.id);
  } catch (e) {
    bildir(e.message, "hata");
  } finally {
    b.disabled = false;
  }
}

export async function gorevSayfasiYukle() {
  ustBilgi();
  await listeCiz();
  if (secili) gorevYenile();
  clearInterval(zamanlayici);
  zamanlayici = setInterval(() => {
    if (document.getElementById("g-gorevler")?.hidden) return; // sayfa gizliyken yoklama yok
    if (kapOverride) return;
    gorevYenile(false);
  }, 1500);
}

export function gorevlerKur() {
  $("#gr-baslat").onclick = baslat;
  $("#gr-diff").onclick = diffGoster;
  $("#gr-review").onclick = reviewYap;
  $("#gr-hedef").onkeydown = (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) baslat(); };
}

/** Claude Code gibi: gorev SOHBETIN ICINDE canli cizilir (adimlar, onay, diff, kontroller). */
export function sohbetteGorevGoster(kap, id) {
  kapOverride = kap;
  secili = id;
  sonCizilen = "";
  acikAdimlar.clear();
  gorevYenile();
  clearInterval(zamanlayici);
  zamanlayici = setInterval(() => {
    if (!kap.isConnected) { clearInterval(zamanlayici); kapOverride = null; return; }
    gorevYenile(false);
  }, 1500);
}
// Gorev sonu otomatik inceleme (Chimera): model varsayimi, kanit degil
const ONEM_SINIF = { kritik: "kirmizi", yuksek: "kirmizi", orta: "sari", dusuk: "" };
function incelemeHtml(i) {
  if (!i || !i.ozet && !(i.bulgular || []).length) return "";
  const b = i.bulgular || [];
  return `<details class="ajan-sonuc ajan-inceleme" ${b.some((x) => ["kritik", "yuksek"].includes(x.onem)) ? "open" : ""}>
    <summary>Otomatik inceleme · ${b.length ? `${b.length} bulgu` : "sorun bulunmadı"} <span class="soluk kucuk">(model varsayımı)</span></summary>
    ${i.ozet ? `<div class="soluk kucuk">${kacir(i.ozet)}</div>` : ""}
    ${b.map((x) => `<div class="inceleme-bulgu"><span class="rozet ${ONEM_SINIF[x.onem] || ""}">${kacir(x.onem)}</span> <b>${kacir(x.baslik)}</b> <code>${kacir(x.dosya)}:${kacir(x.satir)}</code><div class="soluk kucuk">${kacir(x.neden)}</div></div>`).join("")}
  </details>`;
}
