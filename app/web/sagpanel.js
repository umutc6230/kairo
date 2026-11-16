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
  if (acik) { islerYenile(); degisikliklerYenile(); }
}

// Dosyalar: oturum panelinden bagimsiz, kendi dugmesiyle acilip kapanan ayri yan panel
function dosyaPaneliAyarla(acik) {
  $("#dosya-panel").hidden = !acik;
  $("#btn-dosyalar").setAttribute("aria-pressed", String(acik));
  localStorage.setItem(DOSYA_ANAHTAR, acik ? "1" : "0");
  if (acik) dosyaAgaciniYenile();
}

// Claude Code gibi sure: "45s", "17m 54s", "2h 11m"
const SURE = (sn) => {
  sn = Math.max(0, Math.round(sn || 0));
  if (sn < 60) return `${sn}s`;
  if (sn < 3600) return `${Math.floor(sn / 60)}m ${sn % 60}s`;
  return `${Math.floor(sn / 3600)}h ${Math.floor((sn % 3600) / 60)}m`;
};
const CALISAN = new Set(["calisiyor", "onay_bekliyor", "karar_bekliyor", "duraklatildi", "bekliyor"]);

// Komut ve ajan gorevlerini tek listeye cevirir (en yeni once)
async function isListesi() {
  const [{ isler }, { gorevler }] = await Promise.all([api("/api/komutlar"), api("/api/gorevler")]);
  const simdi = Date.now();
  const komut = isler.map((i) => ({
    tur: "komut", id: i.id, ad: i.komut, calisiyor: i.durum === "calisiyor", bas: i.baslangic,
    sure: i.sure_sn ?? (simdi - new Date(i.baslangic).getTime()) / 1000,
  }));
  const gorev = gorevler.map((g) => ({
    tur: "gorev", id: g.id, ad: g.hedef || "Ajan görevi", calisiyor: CALISAN.has(g.durum), bas: g.olusturma,
    sure: g.kullanim?.sure_sn ?? 0, durum: g.durum,
  }));
  return [...komut, ...gorev].sort((a, b) => String(b.bas).localeCompare(String(a.bas)));
}

const durdurBtn = (x) => `<button class="ikon-btn kucuk-ikon is-durdur" data-durdur="${kacir(x.tur)}:${kacir(x.id)}" title="Durdur" aria-label="Durdur">${ikon("durdur")}</button>`;

async function isDurdur(deger) {
  const [tur, id] = deger.split(":");
  try {
    await api(tur === "komut" ? `/api/komutlar/${id}/durdur` : `/api/gorevler/${id}/iptal`, { method: "POST", govde: {} });
  } catch (e) { bildir(e.message, "hata"); }
}

// Claude Code'daki "Background tasks": calisanlar (sure + durdur) ve "N bitti"; tiklayinca ayrinti
async function islerYenile() {
  const kap = $("#sp-isler");
  if (!kap || $("#sag-panel").hidden) return;
  try {
    const liste = await isListesi();
    const calisan = liste.filter((x) => x.calisiyor);
    const biten = liste.length - calisan.length;
    kap.innerHTML = calisan.map((x) => `<div class="sp-satir sp-is sp-tik" data-ac="${kacir(x.id)}" title="${kacir(x.ad)}">${ikon(x.tur === "komut" ? "arkaPlan" : "gorevler")}<span class="sp-ad">${kacir(x.ad)}</span><span class="soluk kucuk">${SURE(x.sure)}</span>${durdurBtn(x)}</div>`).join("")
      + (biten ? `<button class="sp-satir sp-tik soluk" data-ac="">${ikon("tik")}<span class="sp-ad">${biten} bitti</span></button>` : "")
      || '<span class="soluk kucuk">Yok</span>';
    kap.querySelectorAll("[data-durdur]").forEach((b) => { b.onclick = (e) => { e.stopPropagation(); isDurdur(b.dataset.durdur).then(islerYenile); }; });
    kap.querySelectorAll("[data-ac]").forEach((b) => { b.onclick = () => arkaPlanAc(b.dataset.ac); });
    if (!$("#arka-panel")?.hidden) arkaPlanCiz();
  } catch { /* sessiz */ }
}

// Ayrinti gorunumu: calisanlar canli ciktiyla ustte, "Bitti N" altinda acilir kartlar
const acikKart = new Set();
function arkaPlanAc(id) {
  let p = $("#arka-panel");
  if (!p) {
    p = el(`<section id="arka-panel" class="arka-panel" aria-label="Arka plan işleri">
      <div class="arka-baslik"><b>Arka plan işleri</b><span class="sp-sag"><button class="ikon-btn kucuk-ikon" data-kapat title="Kapat" aria-label="Kapat">${ikon("x")}</button></span></div>
      <div class="arka-govde"></div></section>`);
    $("#sag-panel").append(p);
    $("[data-kapat]", p).onclick = () => { p.hidden = true; };
  }
  p.hidden = false;
  if (id) acikKart.add(id);
  arkaPlanCiz();
}

async function arkaPlanCiz() {
  const p = $("#arka-panel");
  if (!p || p.hidden) return;
  const govde = $(".arka-govde", p);
  let liste;
  try { liste = await isListesi(); } catch { return; }
  const calisan = liste.filter((x) => x.calisiyor);
  const biten = liste.filter((x) => !x.calisiyor);
  // bolum iskeleti bir kez: acik kartlarin kaydirma/icerigi her yenilemede bozulmasin
  if (!$(".arka-calisan", govde)) {
    govde.innerHTML = '<div class="arka-calisan"></div><details class="arka-biten" open><summary class="soluk">Bitti <span class="arka-sayi"></span></summary><div class="arka-biten-liste"></div></details>';
  }
  $(".arka-sayi", govde).textContent = biten.length;
  kartlariEsitle($(".arka-calisan", govde), calisan, true);
  kartlariEsitle($(".arka-biten-liste", govde), biten, false);
}

function kartlariEsitle(kap, isler, canli) {
  const idler = new Set(isler.map((x) => x.id));
  kap.querySelectorAll(".arka-kart").forEach((k) => { if (!idler.has(k.dataset.id)) k.remove(); });
  isler.forEach((x, i) => {
    let k = kap.querySelector(`.arka-kart[data-id="${CSS.escape(x.id)}"]`);
    if (!k) {
      k = el(`<div class="arka-kart" data-id="${kacir(x.id)}"><button class="arka-kart-bas"><span class="ok" data-ikon="sag"></span><span class="arka-ad"></span><span class="arka-sure soluk kucuk"></span></button><div class="arka-kart-govde" hidden></div></div>`);
      ikonlariYerlestir(k);
      $(".arka-kart-bas", k).onclick = () => kartAcKapa(k, x);
    }
    if (kap.children[i] !== k) kap.insertBefore(k, kap.children[i] || null);
    $(".arka-ad", k).textContent = x.ad;
    $(".arka-sure", k).innerHTML = SURE(x.sure) + (canli ? " " + durdurBtn(x) : "");
    $(".arka-sure [data-durdur]", k)?.addEventListener("click", (e) => { e.stopPropagation(); isDurdur(e.currentTarget.dataset.durdur).then(arkaPlanCiz); });
    if ((canli || acikKart.has(x.id)) && $(".arka-kart-govde", k).hidden) kartAcKapa(k, x);
    else if (canli && x.tur === "komut") kartGovdeCiz(k, x); // calisan komutun ciktisi canli akar
  });
}

function kartAcKapa(k, x) {
  const g = $(".arka-kart-govde", k);
  g.hidden = !g.hidden;
  k.classList.toggle("acik", !g.hidden);
  if (g.hidden) { acikKart.delete(x.id); return; }
  acikKart.add(x.id);
  kartGovdeCiz(k, x);
}

async function kartGovdeCiz(k, x) {
  const g = $(".arka-kart-govde", k);
  if (x.tur === "gorev") { // ajan gorevi: adim adim calisma akisi (gorevler.js ile ayni gorunum)
    if (!g.dataset.cizildi) {
      g.dataset.cizildi = "1";
      const { sohbetteGorevGoster } = await import("./gorevler.js");
      sohbetteGorevGoster(g, x.id);
    }
    return;
  }
  try {
    const d = await api(`/api/komutlar/${x.id}`);
    const altta = g.scrollHeight - g.scrollTop - g.clientHeight < 30;
    const sonuc = d.durum === "calisiyor" ? "" : `\n[${d.cikis_kodu != null ? `exited with code ${d.cikis_kodu}` : d.durum}]`;
    g.innerHTML = `<pre class="arka-komut">$ ${kacir(d.komut)}</pre><pre class="arka-cikti">${kacir(d.cikti || "")}${kacir(sonuc)}</pre>`;
    if (altta) g.scrollTop = g.scrollHeight;
  } catch (e) { g.innerHTML = `<div class="soluk kucuk">${kacir(e.message)}</div>`; }
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

// Claude Code'daki "Changes": dalin PR'i (varsa) + commit edilmemis degisiklik; tiklayinca diff dock'u
let degisiklikAcGeri = null;
const ARTI_EKSI = (e, s) => `<span class="yesil-metin">+${Number(e) || 0}</span> <span class="kirmizi-metin">-${Number(s) || 0}</span>`;
async function degisikliklerYenile() {
  const kap = $("#sp-degisiklik");
  if (!kap || $("#sag-panel").hidden) return;
  try {
    const d = await api("/api/proje/degisiklikler");
    if (!d.repo) { kap.innerHTML = '<span class="soluk kucuk">Yok</span>'; return; }
    const pr = d.pr && /^https:\/\/github\.com\//.test(d.pr.url || "") ? d.pr : null;
    kap.innerHTML = (pr ? `<a class="sp-satir sp-tik sp-is" href="${kacir(pr.url)}" target="_blank" rel="noopener" title="${kacir(pr.title)}">${ikon("dis")}<span class="sp-ad">${kacir(pr.title)}<span class="sp-alt soluk kucuk">#${Number(pr.number)} · ${kacir(String(pr.state || "").toLowerCase())} · ${ARTI_EKSI(pr.additions, pr.deletions)}</span></span></a>` : "")
      + `<button class="sp-satir sp-tik sp-is" data-diff title="Commit edilmemiş değişiklikleri göster">${ikon("diff")}<span class="sp-ad">${kacir(d.dal || "dal yok")}<span class="sp-alt soluk kucuk">${d.dosya ? `${Number(d.dosya)} dosya · ${ARTI_EKSI(d.ekle, d.sil)}` : "temiz"}</span></span></button>`;
    $("[data-diff]", kap).onclick = () => degisiklikAcGeri?.();
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

export function sagPanelKur({ baglayiciAc, ayarAc, degisiklikAc }) {
  $("#sp-ayar").onclick = ayarAc;
  baglayiciAcGeri = baglayiciAc;
  degisiklikAcGeri = degisiklikAc;
  setInterval(degisikliklerYenile, 10000);
  degisikliklerYenile();
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
  document.addEventListener("oturumlar-degisti", () => { dosyaAgaciniYenile(); baglamYenile(); degisikliklerYenile(); }); // proje/sohbet degisince
}
