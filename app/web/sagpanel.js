// Sag panel (Claude Code Desktop gibi): proje dosya agaci, baglayicilar; alt durum cubugu.
import { ikon, ikonlariYerlestir } from "./ikonlar.js";
import { kacir } from "./md.js";
import { $, api, baglayiciDurumu, bildir, durum, el, modal } from "./ortak.js";

const PANEL_ANAHTAR = "kairo.sagPanel";
const DOSYA_ANAHTAR = "kairo.dosyaPanel";

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
  if (kap && !$("#dosya-panel").hidden) klasorCiz(kap, "");
}

const TOKEN = (n) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n));

// Claude Code'daki gibi satir tiklaninca panelin icinde acilan ayrinti
function detayAcKapa(satir, detay, acik) {
  detay.hidden = !acik;
  satir.setAttribute("aria-expanded", String(acik));
  satir.classList.toggle("acik", acik);
}

let sonBaglayicilar = [];
async function baglayicilariYenile() {
  try {
    const { sunucular } = await api("/api/mcp");
    sonBaglayicilar = sunucular;
    const kodlar = sunucular.map((s) => baglayiciDurumu(s).kod);
    const n = (k) => kodlar.filter((x) => x === k).length;
    const sorun = n("giris") + n("hata");
    const metin = !sunucular.length ? "yok" : n("giris") ? `${n("giris")} giriş gerekli` : n("hata") ? `${n("hata")} bağlanamadı` : `${n("bagli")}/${sunucular.length} bağlı`;
    $("#sp-baglayici").textContent = metin;
    $("#sp-baglayici").classList.toggle("uyari-metin", sorun > 0);
    $("#dc-baglayici").textContent = `Bağlayıcı: ${n("bagli")}/${sunucular.length} bağlı`;
    if (!$("#sp-baglayici-detay").hidden) baglayiciDetayCiz();
  } catch { /* sessiz */ }
}

function baglayiciDetayCiz() {
  const kap = $("#sp-baglayici-detay");
  const SIRA = { giris: 0, hata: 1, baglaniyor: 2, bagli: 3, kapali: 4 };
  const sira = [...sonBaglayicilar].sort((a, b) => SIRA[baglayiciDurumu(a).kod] - SIRA[baglayiciDurumu(b).kod] || a.ad.localeCompare(b.ad, "tr"));
  kap.innerHTML = sira.map((s) => {
    const d = baglayiciDurumu(s);
    const durumM = `<span class="rozet sp-durum ${d.sinif}" title="${kacir(d.ipucu)}">${kacir(d.etiket)}</span>`;
    return `<div class="sp-alt-satir" title="${kacir(s.aciklama || s.ad)}"><span class="sp-harf">${kacir((s.ad || "?")[0].toUpperCase())}</span><span class="sp-ad">${kacir(s.ad)}</span>${durumM}</div>`;
  }).join("") || '<div class="soluk kucuk">Bağlayıcı yok.</div>';
  kap.append(el('<button class="sp-alt-bag" type="button">Bağlayıcıları yönet</button>'));
  kap.lastChild.onclick = () => baglayiciAcGeri?.();
}
let baglayiciAcGeri = null;

let sonBaglam = null;
export async function baglamYenile() {
  const yazi = $("#sp-baglam");
  if (!yazi) return;
  if (!durum.oturumId) { yazi.textContent = "-"; $("#sp-baglam-dolu").style.width = "0"; sonBaglam = null; return; }
  try {
    const b = sonBaglam = await api(`/api/oturumlar/${durum.oturumId}/baglam`);
    yazi.textContent = `%${b.yuzde}`;
    yazi.title = `~${b.kullanilan} / ${b.boyut} token`;
    $("#sp-baglam-dolu").style.width = `${b.yuzde}%`;
    if (!$("#sp-baglam-detay").hidden) baglamDetayCiz();
  } catch { /* sessiz */ }
}

function baglamDetayCiz() {
  const kap = $("#sp-baglam-detay");
  const b = sonBaglam;
  if (!b) { kap.innerHTML = '<div class="soluk kucuk">Bir sohbet açınca bağlam dökümü görünür.</div>'; return; }
  const kalemler = b.kalemler || [{ ad: "Mesajlar", tur: "mesaj", token: b.kullanilan, yuzde: b.yuzde }];
  const cubuk = kalemler.map((k) => `<span class="bk-${kacir(k.tur)}" style="width:${Math.min(100, k.yuzde)}%"></span>`).join("");
  kap.innerHTML = `<div class="bk-ust"><b>%${b.yuzde} kullanıldı</b><span class="soluk">${TOKEN(b.kullanilan)} / ${TOKEN(b.boyut)}</span></div>
    <div class="bk-cubuk" role="img" aria-label="Bağlam %${b.yuzde} dolu">${cubuk}</div>
    ${kalemler.map((k) => `<div class="sp-alt-satir"><span class="bk-nokta bk-${kacir(k.tur)}"></span><span class="sp-ad">${kacir(k.ad)}${k.sayi ? ` <span class="soluk">(${k.sayi})</span>` : ""}</span><span class="soluk">${TOKEN(k.token)}</span><span class="bk-yuzde">${k.yuzde}%</span></div>`).join("")}
    <div class="sp-alt-satir"><span class="bk-nokta bk-bos"></span><span class="sp-ad">Boş alan</span><span class="soluk">${TOKEN(b.bos ?? 0)}</span><span class="bk-yuzde">${Math.max(0, 100 - b.yuzde)}%</span></div>
    <div class="soluk kucuk bk-not">Tahmini; bir sonraki istekte modele gidecek parçalar.</div>`;
}

async function uzakYenile() {
  try { $("#sp-uzak").checked = !!(await api("/api/uzak")).acik; } catch { /* sessiz */ }
}

function paneliAyarla(acik) {
  const p = $("#sag-panel");
  p.hidden = !acik;
  $("#btn-sag-panel").setAttribute("aria-pressed", String(acik));
  localStorage.setItem(PANEL_ANAHTAR, acik ? "1" : "0");
  if (acik) islerYenile();
}

// Dosyalar: oturum panelinden bagimsiz, kendi dugmesiyle acilip kapanan ayri yan panel
function dosyaPaneliAyarla(acik) {
  $("#dosya-panel").hidden = !acik;
  $("#btn-dosyalar").setAttribute("aria-pressed", String(acik));
  localStorage.setItem(DOSYA_ANAHTAR, acik ? "1" : "0");
  if (acik) dosyaAgaciniYenile();
}

const SURE = (sn) => (sn >= 60 ? `${Math.floor(sn / 60)} dk` : `${Math.max(0, Math.round(sn))} sn`);
const CALISAN = new Set(["calisiyor", "onay_bekliyor", "karar_bekliyor", "duraklatildi", "bekliyor"]);

// Claude Code'daki "Background tasks": calisan komut ve ajan gorevleri + biten sayisi
async function islerYenile() {
  const kap = $("#sp-isler");
  if (!kap || $("#sag-panel").hidden) return;
  try {
    const [{ isler }, { gorevler }] = await Promise.all([api("/api/komutlar"), api("/api/gorevler")]);
    const satirlar = [];
    let biten = 0;
    for (const i of isler) {
      if (i.durum !== "calisiyor") { biten++; continue; }
      satirlar.push(`<div class="sp-satir sp-is" title="${kacir(i.komut)}">${ikon("arkaPlan")}<span class="sp-ad">${kacir(i.komut)}</span></div>`);
    }
    for (const g of gorevler) {
      if (!CALISAN.has(g.durum)) { biten++; continue; }
      const sn = g.kullanim?.sure_sn ?? 0;
      satirlar.push(`<div class="sp-satir sp-is" title="${kacir(g.hedef || "")}">${ikon("gorevler")}<span class="sp-ad">${kacir(g.hedef || "Ajan görevi")}</span><span class="soluk kucuk">${SURE(sn)}</span></div>`);
    }
    if (biten) satirlar.push(`<div class="sp-satir soluk">${ikon("tik")}<span class="sp-ad">${biten} bitti</span></div>`);
    kap.innerHTML = satirlar.join("") || '<span class="soluk kucuk">Yok</span>';
  } catch { /* sessiz */ }
}

// Thread'ler (is emirleri), aktif proje: once kullanicinin elini bekleyenler, sonra calisanlar
const TH_GRUP = [
  ["Seni bekliyor", ["insan_bekliyor"], "sari"],
  ["İncelemeye hazır", ["inceleme", "taslak"], "yesil"],
  ["Sorun var", ["basarisiz"], "kirmizi"],
  ["Çalışıyor", ["calisiyor", "sirada"], "mavi"],
];
async function threadlerYenile() {
  const kap = $("#sp-threadler");
  if (!kap || $("#sag-panel").hidden) return;
  try {
    const v = await api("/api/superajan");
    const isler = v.isler.filter((x) => x.proje_kok === v.aktif_proje);
    const sn = (x) => Math.max(0, (Date.now() - new Date(x.olusturma).getTime()) / 1000);
    kap.innerHTML = TH_GRUP.map(([ad, asamalar, sinif]) => {
      const g = isler.filter((x) => asamalar.includes(x.asama));
      return g.length ? `<div class="sp-satir soluk kucuk"><span class="thread-nokta ${sinif}"></span><span class="sp-ad">${ad}</span><span>${g.length}</span></div>${g.map((x) =>
        `<button class="sp-satir sp-tik sp-is" data-git-ajanlar title="${kacir(x.baslik)}"><span class="sp-ad">${kacir(x.baslik)}</span><span class="soluk kucuk">${SURE(sn(x))}</span></button>`).join("")}` : "";
    }).join("") || '<span class="soluk kucuk">Yok</span>';
    kap.querySelectorAll("[data-git-ajanlar]").forEach((b) => { b.onclick = () => document.querySelector('.nav-oge[data-git="ajanlar"]')?.click(); });
  } catch { /* sessiz */ }
}

const DOLAR = (x) => `$${Number(x).toFixed(Math.abs(Number(x)) < 10 ? 2 : 0)}`;

// Durum cubugu: OpenRouter kalan limiti/bakiyesi (anahtar sunucuda; buraya yalniz tutarlar gelir)
export async function orLimitYenile() {
  const b = $("#dc-or-limit");
  if (!b) return;
  if (durum.ayarlar?.saglayici !== "openrouter") { b.hidden = true; return; }
  try {
    const l = await api("/api/openrouter/limit");
    if (!l.var) { b.hidden = true; return; }
    const kalan = l.kalan ?? l.bakiye;
    const parca = [l.kalan != null ? `Anahtar limiti: ${DOLAR(l.kalan)} / ${DOLAR(l.limit)}` : "Anahtar limiti: yok (sınırsız)"];
    if (l.bakiye != null) parca.push(`Hesap bakiyesi: ${DOLAR(l.bakiye)}`);
    if (l.kullanim != null) parca.push(`Kullanılan: ${DOLAR(l.kullanim)}`);
    if (l.ucretsiz) parca.push("Ücretsiz katman");
    if (l.uyari) parca.push(l.uyari);
    b.textContent = kalan != null ? `OpenRouter: ${DOLAR(kalan)} kalan` : "OpenRouter: limitsiz";
    b.title = parca.join(" · ");
    b.classList.toggle("az", kalan != null && kalan < 1);
    b.hidden = false;
  } catch { b.hidden = true; }
}

export function sagPanelKur({ baglayiciAc, ayarAc }) {
  $("#sp-ayar").onclick = ayarAc;
  baglayiciAcGeri = baglayiciAc;
  $("#sp-baglam-satir").onclick = (e) => {
    const acik = $("#sp-baglam-detay").hidden;
    detayAcKapa(e.currentTarget, $("#sp-baglam-detay"), acik);
    if (acik) { baglamDetayCiz(); baglamYenile(); }
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
  $("#btn-dosyalar").onclick = () => dosyaPaneliAyarla($("#dosya-panel").hidden);
  $("#sp-dosya-kapat").onclick = () => dosyaPaneliAyarla(false);
  $("#sp-dosya-yenile").onclick = dosyaAgaciniYenile;
  dosyaPaneliAyarla(localStorage.getItem(DOSYA_ANAHTAR) === "1");
  setInterval(islerYenile, 4000);
  setInterval(threadlerYenile, 5000);
  threadlerYenile();
  setTimeout(orLimitYenile, 1500); // ayarlar yuklendikten sonra
  setInterval(orLimitYenile, 60000);
  $("#dc-or-limit").onclick = async () => { await orLimitYenile(); bildir($("#dc-or-limit").title, "bilgi", 5000); };
  $("#sp-baglayici-baslik").onclick = (e) => {
    const acik = $("#sp-baglayici-detay").hidden;
    detayAcKapa(e.currentTarget, $("#sp-baglayici-detay"), acik);
    if (acik) { baglayiciDetayCiz(); baglayicilariYenile(); }
  };
  ikonlariYerlestir(document.getElementById("kok"));
  baglayicilariYenile();
  api("/api/bilgi").then((b) => { $("#dc-surum").textContent = `${b.urun} ${b.surum}`; }).catch(() => {});
  document.addEventListener("oturumlar-degisti", () => { dosyaAgaciniYenile(); baglamYenile(); }); // proje/sohbet degisince
}
