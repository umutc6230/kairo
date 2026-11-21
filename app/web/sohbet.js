// Sohbet gorunumu: mesajlar, dusunce blogu, yazma alani, ekler, akis ve durdurma.
import { gorevRaporEylemleri, gorevRaporEylemleriniBagla, goreviIptalEt, sohbetteGorevGoster } from "./gorevler.js";
import { threadKarti } from "./superajan.js";
import { arayuzKarti, onizlemeKarti } from "./gorsel_kartlar.js";
import { masaustuBildirimi } from "./ayarlar2.js";
import { girdiYardimKur, oneriTusu } from "./girdi.js";
import { anahtarCoz, anahtarYapistir, maskele } from "./gizli.js";
import { komutListesi, komutMu } from "./komutlar.js";
import { projeDurumu } from "./proje.js";
import { ikon, ikonlariYerlestir } from "./ikonlar.js";
import { kacir, md } from "./md.js";
import { prKartlariKur } from "./pr_kart.js";
import { DURUM_ETIKET, gorevDurumlari, oturumDurumu } from "./oturum_durumu.js";
import { t } from "./i18n.js";
import { sesliModAcik } from "./dikte.js";
import { dosyaAc } from "./sagpanel.js";
import {
  $, $$, api, bildir, canliSayac, durum, el, istatistikCipleri, modal, modelAdi, modelProfil, onayla, sayi, sseOku,
  ekResimleriYukle,
} from "./ortak.js";

const bekleyenEkler = []; // {id?, ad, tur, onizleme, yukleniyor}
let akisKontrol = null; // AbortController
let aktifGorev = null;
const iptalBekleyenGorevler = new Set();
export let calisanOturumId = null; // kenar cubugunda animasyonlu gosterilir
let geriCagri = { oturumlarYenile: async () => {}, baslikAyarla: () => {}, oturumAc: async () => {} };
let oneriKararlari = {}; // acik oturumun alt oturum onerisi kararlari: kaynak -> alt id | "reddedildi"

// Claude Desktop gibi: acilan alt oturum ana oturumda canli kart olarak durur (durum, son etkinlik)
function altOturumCanli(id, kap) {
  const k = el(`<button class="alt-canli" type="button"><span class="alt-canli-nokta"></span><span class="alt-canli-metin"><b></b><span class="soluk kucuk"></span></span><span class="alt-canli-ok" data-ikon="sag"></span></button>`);
  k.onclick = () => geriCagri.oturumAc(id, true);
  kap.append(k);
  ikonlariYerlestir(k);
  let bekleme = 0;
  const ciz = async () => {
    // kart once olusturulup sonra sayfaya eklenir: eklenene kadar kisa aralikla bekle
    if (!k.isConnected) { if (bekleme++ < 40) setTimeout(ciz, 250); return; }
    let o;
    try {
      const [liste, harita] = await Promise.all([api("/api/oturumlar"), gorevDurumlari()]);
      o = liste.find((x) => x.id === id);
      if (!o) { $("b", k).textContent = t("Alt oturum silinmiş"); k.disabled = true; return; }
      const d = oturumDurumu(o, harita);
      $("b", k).textContent = o.baslik || t("Alt oturum");
      $(".soluk", k).textContent = d ? t(DURUM_ETIKET[d]) : (o.son_metin || t("Boşta"));
      k.querySelector(".alt-canli-nokta").className = `alt-canli-nokta ${d}`;
      k.title = `${o.baslik || ""}${o.son_metin ? `\n${o.son_metin}` : ""}`;
      if (d === "calisiyor" || d === "onay") setTimeout(ciz, 4000);
    } catch { setTimeout(ciz, 8000); }
  };
  ciz();
}

// Claude Code gibi: model alt oturum ONERIR, kullanici onaylarsa acilir ve gorev orada ilk mesaj olur.
function altOturumKarti(o, kap) {
  const g = o.argumanlar || {};
  const ust = durum.oturumId;
  const kart = el(`<div class="oneri-kart" data-id="${kacir(o.id)}"><div class="oneri-ust soluk kucuk"><span data-ikon="yanSohbet"></span>Alt oturum önerisi</div>
    <b class="oneri-baslik">${kacir(g.baslik || "")}</b><div class="oneri-gorev soluk kucuk">${kacir(String(g.gorev || "").slice(0, 400))}</div>
    <div class="dugme-sira"></div></div>`);
  const sira = kart.querySelector(".dugme-sira");
  const ciz = () => {
    const karar = oneriKararlari[o.id];
    if (karar === "reddedildi") { sira.innerHTML = '<span class="soluk kucuk">Geçildi</span>'; return; }
    if (karar?.startsWith("is:")) { sira.innerHTML = ""; threadKarti([karar.slice(3)], sira); return; }
    if (karar) { sira.innerHTML = ""; altOturumCanli(karar, sira); return; }
    sira.innerHTML = '<button class="btn ana kucuk" data-ac>Alt oturumda başlat</button><button class="btn kucuk" data-arka title="Ayrı git dalında, ajan arka planda yapar; bitince incelersin">Arka planda yaptır (ayrı dal)</button><button class="btn kucuk" data-red>Gerek yok</button>';
    sira.querySelector("[data-arka]").onclick = async (e) => {
      e.currentTarget.disabled = true;
      const ac = () => api("/api/superajan/isler", { method: "POST", govde: { baslik: g.baslik || "", gorev: String(g.gorev || ""), kaynak: "sohbet" } });
      try {
        let is_;
        try { is_ = await ac(); } catch (h) {
          if (!/GIT_YOK/.test(h.message)) throw h;
          if (!(await onayla("Git deposu oluşturulsun mu?", "İş ayrı bir git dalında yapılır; bu proje henüz git deposu değil. Depo oluşturulup ilk commit atılsın mı?", { evet: "Oluştur" }))) { ciz(); return; }
          await api("/api/superajan/git-baslat", { method: "POST", govde: {} });
          is_ = await ac();
        }
        await api(`/api/oturumlar/${ust}/oneri-reddet`, { method: "POST", govde: { kaynak: o.id, karar: `is:${is_.id}` } });
        oneriKararlari[o.id] = `is:${is_.id}`;
        ciz();
      } catch (hata) { bildir(hata.message, "hata", 7000); ciz(); }
    };
    sira.querySelector("[data-ac]").onclick = async (e) => {
      e.currentTarget.disabled = true;
      try {
        const alt = await api(`/api/oturumlar/${ust}/alt`, { method: "POST", govde: { baslik: g.baslik || "Alt oturum", kaynak: o.id } });
        oneriKararlari[o.id] = alt.id;
        await geriCagri.oturumAc(alt.id, true);
        $("#girdi").value = String(g.gorev || "");
        gonder();
      } catch (hata) { bildir(hata.message, "hata"); ciz(); }
    };
    sira.querySelector("[data-red]").onclick = async () => {
      try {
        await api(`/api/oturumlar/${ust}/oneri-reddet`, { method: "POST", govde: { kaynak: o.id } });
        oneriKararlari[o.id] = "reddedildi";
        ciz();
      } catch (hata) { bildir(hata.message, "hata"); }
    };
  };
  ciz();
  kap.append(kart);
  ikonlariYerlestir(kart);
  return kart;
}

export function sohbetKur(cb) {
  geriCagri = cb;
  document.addEventListener("dikte-gonder", () => gonder());
  document.addEventListener("kart-yenile", (e) => {
    const istem = (e.detail?.istem || "").trim();
    if (!istem) return;
    const g = $("#girdi");
    if (!g) return;
    g.value = istem;
    boyutla();
    gonderDurumu();
    gonder();
  });
  kaydirmaTakibiKur();
  prKartlariKur();
  const yolTik = (e) => {
    const y = e.target.closest(".yol-link");
    if (!y || (e.type === "keydown" && e.key !== "Enter")) return;
    e.preventDefault();
    yolAc(y.dataset.yol);
  };
  $("#mesajlar").addEventListener("click", yolTik);
  $("#mesajlar").addEventListener("keydown", yolTik);
  const girdi = $("#girdi");
  girdi.addEventListener("input", () => { boyutla(); gonderDurumu(); });
  girdi.addEventListener("keydown", (e) => {
    if (oneriTusu(e)) return; // "/" ve "@" onerileri acikken ok/Enter/Tab onlara gider
    if (e.key === "Tab" && !girdi.value && girdi.dataset.oneri) { // Claude Code: Tab = oneriyi al
      e.preventDefault();
      girdi.value = girdi.dataset.oneri;
      oneriTemizle();
      boyutla();
      gonderDurumu();
      return;
    }
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); gonder(); }
  });
  girdiYardimKur(komutListesi);
  girdi.addEventListener("oturum-degisti", () => {
    oneriTemizle(); // baska sohbetin onerisi kalmasin
    siradakiler.length = 0;
    siraCiz();
    window.speechSynthesis?.cancel();
  });
  girdi.addEventListener("paste", (e) => {
    const dosyalar = [...(e.clipboardData?.files || [])];
    if (dosyalar.length) { e.preventDefault(); dosyalar.forEach(ekYukle); return; }
    anahtarYapistir(e, girdi); // API anahtari kutuda maskeli gorunur
  });
  $("#btn-gonder").onclick = () => {
    if (akisKontrol) return durdur();
    const gorev = calisanGorev();
    return gorev ? ajanGoreviniDurdur(gorev) : gonder();
  };
  $("#btn-ek").onclick = () => $("#dosya-sec").click();
  $("#dosya-sec").onchange = (e) => { [...e.target.files].forEach(ekYukle); e.target.value = ""; };
  const yazma = $("#yazma");
  const alan = $("#g-sohbet");
  alan.addEventListener("dragover", (e) => { e.preventDefault(); yazma.classList.add("surukle"); });
  alan.addEventListener("dragleave", (e) => { if (!alan.contains(e.relatedTarget)) yazma.classList.remove("surukle"); });
  alan.addEventListener("drop", (e) => {
    e.preventDefault();
    yazma.classList.remove("surukle");
    [...e.dataTransfer.files].forEach(ekYukle);
  });
  $("#mesajlar").addEventListener("click", kodKopyala);
  secimMenusuKur();
}

// Claude gibi: mesajlarda metin secilince ustunde yuzen menu (yan sohbet / yanitla / kopyala).
function secimMenusuKur() {
  const kap = $("#mesajlar");
  const menu = el(`<div class="secim-menu" role="toolbar" aria-label="Seçili metin" hidden>
    <button data-yan><span data-ikon="yanSohbet"></span>Yan sohbet başlat</button>
    <button data-yanit><span data-ikon="sol"></span>Yanıtla</button>
    <button data-kopya title="Kopyala" aria-label="Kopyala"><span data-ikon="kopyala"></span></button></div>`);
  document.body.append(menu);
  ikonlariYerlestir(menu);
  let secili = "";
  const kapat = () => { menu.hidden = true; };
  const goster = () => {
    const s = window.getSelection();
    secili = s.toString().trim();
    if (!secili || !s.rangeCount || !kap.contains(s.getRangeAt(0).commonAncestorContainer)) return kapat();
    menu.querySelector("[data-yan]").hidden = !durum.oturumId; // yan sohbet acik bir oturum ister
    menu.hidden = false;
    const r = s.getRangeAt(0).getBoundingClientRect();
    const g = menu.offsetWidth;
    const y = menu.offsetHeight;
    menu.style.left = `${Math.max(8, Math.min(r.left + r.width / 2 - g / 2, innerWidth - g - 8))}px`;
    menu.style.top = `${r.top - y - 8 < 8 ? r.bottom + 8 : r.top - y - 8}px`;
  };
  kap.addEventListener("mouseup", () => setTimeout(goster, 0)); // tik sonrasi secim guncellensin
  kap.addEventListener("keyup", (e) => { if (e.shiftKey) goster(); });
  kap.addEventListener("scroll", kapat);
  document.addEventListener("mousedown", (e) => { if (!menu.contains(e.target)) kapat(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") kapat(); });
  menu.addEventListener("mousedown", (e) => e.preventDefault()); // tiklayinca secim kaybolmasin
  const alinti = () => `${secili.split("\n").map((s) => `> ${s}`).join("\n")}\n\n`;
  const girdiyeYaz = (metin) => {
    const g = $("#girdi");
    g.value = metin;
    boyutla();
    gonderDurumu();
    g.focus();
    g.setSelectionRange(metin.length, metin.length);
  };
  menu.querySelector("[data-yanit]").onclick = () => {
    kapat();
    const g = $("#girdi").value;
    girdiyeYaz(alinti() + g);
  };
  menu.querySelector("[data-kopya]").onclick = () => { kapat(); kopyala(secili); };
  menu.querySelector("[data-yan]").onclick = async () => {
    kapat();
    const metin = alinti();
    try {
      const alt = await api(`/api/oturumlar/${durum.oturumId}/alt`, { method: "POST", govde: { baslik: secili.slice(0, 60) } });
      await geriCagri.oturumAc(alt.id, true);
      girdiyeYaz(metin);
    } catch (hata) { bildir(hata.message, "hata"); }
  };
}

function boyutla() {
  const g = $("#girdi");
  g.style.height = "auto";
  g.style.height = `${Math.min(g.scrollHeight, 260)}px`;
  g.style.overflowY = g.scrollHeight > 260 ? "auto" : "hidden";
}

function calisanGorev() {
  return aktifGorev && aktifGorev.oturumId === durum.oturumId && aktifGorev.detay.isConnected
    ? aktifGorev : null;
}

async function ajanGoreviniDurdur(gorev) {
  if (iptalBekleyenGorevler.has(gorev.id)) return;
  iptalBekleyenGorevler.add(gorev.id);
  gonderDurumu();
  try {
    const sonuc = await goreviIptalEt(gorev.id);
    if (sonuc && aktifGorev?.id === gorev.id) aktifGorev = null;
  } catch (e) {
    bildir(e.message, "hata");
  } finally {
    iptalBekleyenGorevler.delete(gorev.id);
    gonderDurumu();
  }
}

function gonderDurumu() {
  const b = $("#btn-gonder");
  const gorev = calisanGorev();
  if (akisKontrol || gorev) {
    b.disabled = !akisKontrol && iptalBekleyenGorevler.has(gorev?.id);
    b.classList.add("durdur");
    b.innerHTML = ikon("durdur");
    b.title = "Durdur";
    b.setAttribute("aria-label", t("Durdur"));
    return;
  }
  b.classList.remove("durdur");
  b.innerHTML = ikon("yukari");
  b.title = "Gonder (Enter)";
  b.setAttribute("aria-label", t("Gönder"));
  const yukleniyor = bekleyenEkler.some((e) => e.yukleniyor);
  b.disabled = yukleniyor || (!$("#girdi").value.trim() && !bekleyenEkler.length);
}

// ---- ekler ----
const TUR_IKON = { resim: "resim", pdf: "dosya", ses: "muzik", metin: "dosya" };

function ekleriCiz() {
  const kap = $("#ek-listesi");
  kap.innerHTML = "";
  bekleyenEkler.forEach((e, i) => {
    const gorsel = e.onizleme ? `<img src="${e.onizleme}" alt="">` : `<span class="tur">${ikon(TUR_IKON[e.tur] || "dosya")}</span>`;
    const c = el(`<div class="ek-cip ${e.yukleniyor ? "yukleniyor" : ""}">${gorsel}
      <span class="ad" title="${kacir(e.ad)}">${kacir(e.ad)}</span>
      <button title="Kaldir" data-ikon="x"></button></div>`);
    c.querySelector("button").onclick = () => {
      if (e.onizleme) URL.revokeObjectURL(e.onizleme);
      bekleyenEkler.splice(i, 1);
      ekleriCiz();
    };
    kap.append(c);
  });
  gonderDurumu();
}

async function ekYukle(dosya) {
  const tur = /^image\//.test(dosya.type) ? "resim" : /pdf$/.test(dosya.type) ? "pdf" : /^audio\//.test(dosya.type) ? "ses" : "metin";
  if (tur === "ses" && !modelProfil(durum.ayarlar?.model)?.ses) {
    bildir("Secili model ses desteklemiyor; Gemma 4 modellerinden birini sec.", "hata");
  }
  const kayit = { ad: dosya.name || "yapistirilan.png", tur, yukleniyor: true, onizleme: tur === "resim" ? URL.createObjectURL(dosya) : "" };
  bekleyenEkler.push(kayit);
  ekleriCiz();
  const form = new FormData();
  form.append("dosya", dosya, kayit.ad);
  try {
    const ek = await api("/api/ekler", { method: "POST", form });
    Object.assign(kayit, { id: ek.id, tur: ek.tur, yukleniyor: false });
  } catch (e) {
    if (kayit.onizleme) URL.revokeObjectURL(kayit.onizleme);
    bekleyenEkler.splice(bekleyenEkler.indexOf(kayit), 1);
    bildir(e.message, "hata");
  }
  ekleriCiz();
}

// ---- mesaj cizimi ----
// Claude Desktop gibi: kullanici en alttaysa icerik buyudukce takip edilir; yukari kaydirinca birakilir
let yapisik = true;
function sonaKaydir(zorla = false) {
  if (zorla) yapisik = true;
  if (!yapisik) return okDurumu();
  const m = $("#mesajlar");
  m.scrollTop = m.scrollHeight;
  okDurumu();
}

// Sohbetteki yol: once uygulama icinde goster; yetkili klasor disindaysa Gezgin'de sec (calistirmaz)
async function yolAc(yol) {
  yol = yol.replace(/:\d+$/, "");
  try {
    await dosyaAc(yol, true);
  } catch {
    try { await api("/api/dosya/goster", { method: "POST", govde: { yol } }); } catch (e) { bildir(e.message, "hata"); }
  }
}

function okDurumu() {
  const ok = $("#alta-in");
  if (!ok) return;
  const m = $("#mesajlar");
  ok.hidden = m.scrollHeight - m.scrollTop - m.clientHeight < 80;
  ok.style.bottom = `${m.parentElement.clientHeight - m.offsetTop - m.clientHeight + 16}px`;
}

function kaydirmaTakibiKur() {
  const m = $("#mesajlar");
  const ok = el(`<button class="alta-in" id="alta-in" type="button" aria-label="En alta in" title="En alta in" hidden>${ikon("asagi")}</button>`);
  ok.onclick = () => sonaKaydir(true);
  m.after(ok);
  m.addEventListener("scroll", () => {
    yapisik = m.scrollHeight - m.scrollTop - m.clientHeight < 40;
    okDurumu();
  }, { passive: true });
  const takip = () => sonaKaydir(); // MutationObserver degisiklikleri zaten topluyor
  new MutationObserver(takip).observe(m, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["style", "open", "hidden"] });
  m.addEventListener("load", takip, true); // resim/iframe sonradan yuklenince yukseklik degisir
  new ResizeObserver(takip).observe(m);
}

function sutun() {
  let s = $("#mesajlar .mesaj-sutun");
  if (!s) {
    $("#bos-durum").hidden = true;
    s = el(`<div class="mesaj-sutun"></div>`);
    $("#mesajlar").append(s);
  }
  return s;
}

// Claude Code rewind: secilen mesaj ve sonrasi silinir, mesaj metni tekrar girdiye gelir
// Saat etiketi: kayitli zaman yoksa (canli mesaj) simdi
function saatYaz(saat, zaman) {
  const t = zaman ? new Date(zaman) : new Date();
  if (Number.isNaN(t.getTime())) return;
  saat.textContent = t.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
  saat.title = t.toLocaleString("tr-TR");
}

// Kayitli mesajlarda (id var) dallan + sabitle dugmeleri
function mesajDugmeleri(d, m) {
  if (!m?.id) return;
  d.dataset.id = m.id;
  d.classList.toggle("sabit", !!m.sabit);
  const dal = d.querySelector(".dallan");
  if (dal) dal.onclick = async () => {
    const oid = durum.oturumId;
    if (!oid || akisVar()) { bildir("Cevap sürerken dallanılamaz.", "hata"); return; }
    try {
      const y = await api(`/api/oturumlar/${oid}/catal`, { method: "POST", govde: { mesaj_id: m.id } });
      geriCagri.oturumlarYenile();
      await geriCagri.oturumAc(y.id, true);
      bildir("Yeni sohbete dallanıldı.");
    } catch (e) { bildir(e.message, "hata"); }
  };
  const pin = d.querySelector(".sabitle");
  if (pin) {
    pin.setAttribute("aria-pressed", String(!!m.sabit));
    pin.onclick = async () => {
      try {
        const y = await api(`/api/oturumlar/${durum.oturumId}/mesajlar/${m.id}/sabitle`, { method: "POST" });
        m.sabit = y.sabit;
        pin.setAttribute("aria-pressed", String(y.sabit));
        d.classList.toggle("sabit", y.sabit);
      } catch (e) { bildir(e.message, "hata"); }
    };
  }
}

// Duzenle (yalniz son kullanici mesaji): onaysiz, metin kutuya gelir; gonderilince bu mesaj ve cevabi kesilir.
let duzenlenen = null;
function duzenle(m) {
  if (!durum.oturumId || akisVar()) { bildir("Cevap sürerken düzenlenemez.", "hata"); return; }
  duzenlenen = { m, oid: durum.oturumId };
  const g = $("#girdi");
  g.value = m.metin || "";
  boyutla();
  gonderDurumu();
  g.focus();
  g.setSelectionRange(g.value.length, g.value.length);
  bildir("Düzenleyip gönder; bu mesaj ve cevabı yenisiyle değişir. İptal: kutuyu boşalt.", "bilgi", 4000);
}

async function geriSar(m, tekrar = false) {
  const oid = durum.oturumId;
  if (!oid || akisVar()) { bildir("Cevap sürerken geri sarılamaz.", "hata"); return; }
  if (tekrar && !(await onayla("Yeniden dene", "Bu mesaj ve sonrasındaki konuşma silinecek; mesaj tekrar gönderilecek. Ajanın yaptığı dosya değişiklikleri geri alınmaz (onlar için /rewind).", { evet: "Yeniden dene", tehlike: true }))) return;
  try {
    const v = await api(`/api/oturumlar/${oid}/geri-sar`, { method: "POST", govde: m.id ? { mesaj_id: m.id } : { run: m.run } });
    if (m.run) { // tarayici onbellegindeki ajan kayitlari da ayni noktaya kesilir
      const t = ajanKayitlari();
      t[oid] = (v.oturum.ajan_runlari || []).slice();
      try { localStorage.setItem(AJAN_ANAHTAR, JSON.stringify(t)); } catch { /* depolama kapali */ }
    }
    await geriCagri.oturumAc(oid, true);
    $("#girdi").value = v.metin || "";
    boyutla();
    gonderDurumu();
    $("#girdi").focus();
    if (tekrar && v.metin) await gonder();
  } catch (e) { bildir(e.message, "hata"); }
}

function kullaniciMesaji(m) {
  const ekler = (m.ekler || []).map((e) => e.tur === "resim"
    ? `<img data-ek="${e.id}" alt="${kacir(e.ad)}" data-buyut="${e.id}">`
    : `<span class="ek-cip"><span class="tur">${ikon(TUR_IKON[e.tur] || "dosya")}</span><span class="ad">${kacir(e.ad)}</span></span>`).join("");
  const d = el(`<div class="mesaj kullanici">
    ${ekler ? `<div class="mesaj-ekleri">${ekler}</div>` : ""}
    ${m.metin ? `<div class="balon">${kacir(maskele(m.metin))}</div>` : ""}
    <div class="mesaj-alt"><span class="mesaj-saat soluk"></span>
      ${m.id ? '<button class="ikon-btn dallan" title="Buradan yeni sohbete dallan" aria-label="Buradan dallan" data-ikon="dal"></button>' : ""}
      ${m.id || m.run ? `<button class="ikon-btn tekrar" title="Yeniden dene: bu mesaj ve sonrası silinir, mesaj tekrar gönderilir" aria-label="Yeniden dene" data-ikon="yenile"></button>
      <button class="ikon-btn geri-sar" title="Düzenle: bu mesaj ve sonrası silinir, mesaj kutuya gelir" aria-label="Düzenle" data-ikon="kalem"></button>` : ""}
      <button class="ikon-btn kopya" title="Kopyala" aria-label="Kopyala" data-ikon="kopyala"></button></div></div>`);
  d.querySelector(".kopya").onclick = () => kopyala(m.metin);
  saatYaz(d.querySelector(".mesaj-saat"), m.zaman);
  mesajDugmeleri(d, m);
  const gs = d.querySelector(".geri-sar");
  if (gs) gs.onclick = () => duzenle(m);
  const tk = d.querySelector(".tekrar");
  if (tk) tk.onclick = () => geriSar(m, true);
  ekResimleriYukle(d);
  d.querySelectorAll("[data-buyut]").forEach((img) => {
    img.onclick = () => modal({ baslik: img.alt, icerik: `<img class="resim-buyuk" src="${img.src}">`, genis: true });
  });
  return d;
}

// Claude Code gibi: ardisik ayni tur araclar tek katlanir satirda ("6 dosya okundu ›"); acinca her
// adim yine ayri acilir. Sira onemli: tarayici_* "ara" icerir, web once denenir.
const ARAC_TURLERI = [
  ["duzenle", /dosya_(yaz|yama|tasi|sil)|ajan_olustur|uzanti_yaz/, (n) => `${n} dosya düzenlendi`],
  ["komut", /komut_|cli_ye_yaptir/, (n) => `${n} komut çalıştırıldı`],
  ["web", /web_|tarayici_|fetch/, (n) => `${n} web işlemi`],
  ["ara", /_ara$|arac_bul|glob|grep|search/, (n) => `${n} arama yapıldı`],
  ["oku", /oku|listele|git_|kod_|read|list/, (n) => `${n} okuma yapıldı`],
];

function aracTuru(ad) {
  return ARAC_TURLERI.find(([, r]) => r.test(ad)) || ["diger", null, (n) => `${n} araç kullanıldı`];
}

/** Adimin ekleneceği grup: son gorunur oge ayni turde grupsa o, degilse yeni grup.
 *  Tek adimli grubun basligi CSS ile gizli; adim eskisi gibi duz gorunur. */
function aracGrubu(kap, ad) {
  const [tur, , etiket] = aracTuru(ad);
  let son = kap.lastElementChild;
  while (son && son.hidden) son = son.previousElementSibling; // gizli plan adimi grubu bolmesin
  if (son?.classList.contains("arac-grup") && son.dataset.tur === tur) return son.api;
  const g = el(`<div class="arac-grup" data-tur="${tur}" data-n="0">
    <button class="arac-grup-baslik" aria-expanded="false"><span class="grup-metin"></span><span class="ok" data-ikon="sag"></span></button>
    <div class="arac-grup-govde"></div></div>`);
  const baslik = g.querySelector(".arac-grup-baslik");
  baslik.onclick = () => baslik.setAttribute("aria-expanded", String(g.classList.toggle("acik")));
  g.grupGuncelle = () => {
    const adimlar = g.querySelectorAll(".arac-adim");
    g.dataset.n = String(adimlar.length);
    const calisan = g.querySelector(".ozet.parilti");
    const hata = g.querySelectorAll(".ozet.hata").length;
    const m = g.querySelector(".grup-metin");
    m.textContent = etiket(adimlar.length) + (hata ? ` · ${hata} hata` : "");
    m.classList.toggle("parilti", !!calisan);
    m.classList.toggle("hata", hata > 0);
  };
  g.api = { ekle: (a) => { g.querySelector(".arac-grup-govde").append(a); g.grupGuncelle(); } };
  kap.append(g);
  ikonlariYerlestir(g);
  return g.api;
}

/** Asistan mesaji: ustte dusunce blogu, altta cevap ve istatistik. Canli guncellenebilir. */
function asistanMesaji() {
  const d = el(`<div class="mesaj asistan">
    <div class="baykus-canli" data-mod="bekliyor" hidden><span class="baykus-kap"></span><span class="baykus-etiket"></span></div>
    <div class="durum-satiri" hidden><span class="parilti"></span><span class="sayac soluk"></span></div>
    <div class="dusunce" hidden>
      <button class="dusunce-baslik"><span data-ikon="beyin"></span><span class="dusunce-etiket">Düşünüyor…</span><span class="ok" data-ikon="sag"></span></button>
      <div class="dusunce-icerik"></div>
    </div>
    <button class="etkinlik-baslik" hidden aria-expanded="true"><span class="etkinlik-metin">Çalışıyor</span><span class="ok" data-ikon="sag"></span></button>
    <div class="etkinlik-govde">
      <div class="sohbet-plan" hidden></div>
      <div class="arac-adimlari"></div>
    </div>
    <div class="govde-metin md"></div>
    <div class="uyarilar"></div>
    <div class="canli-alt" hidden><span class="nokta3" aria-hidden="true"><i></i><i></i><i></i></span><span class="canli-sure"></span></div>
    <div class="mesaj-alt" hidden><button class="ikon-btn kopya" title="Kopyala" aria-label="Kopyala" data-ikon="kopyala"></button><button class="ikon-btn dallan" title="Buradan yeni sohbete dallan" aria-label="Buradan dallan" data-ikon="dal" hidden></button><button class="ikon-btn sabitle" title="Sabitle" aria-label="Sabitle" aria-pressed="false" data-ikon="raptiye" hidden></button><button class="ikon-btn sesli-oku" title="Sesli oku" aria-label="Sesli oku" aria-pressed="false" data-ikon="hoparlor"></button><span class="mesaj-saat soluk"></span><span class="istat istat-cipleri"></span></div>
  </div>`);
  const dusunceKutu = d.querySelector(".dusunce");
  d.querySelector(".baykus-kap").innerHTML = ikon("logo");
  d.querySelector(".dusunce-baslik").onclick = () => dusunceKutu.classList.toggle("acik");
  // Claude gibi "Editing ›": tiklayinca arac adimlari katlanir/acilir
  const etk = d.querySelector(".etkinlik-baslik");
  etk.onclick = () => {
    const kapali = d.classList.toggle("etkinlik-kapali");
    etk.setAttribute("aria-expanded", String(!kapali));
  };
  const o = {
    el: d,
    metin: "",
    dusunce: "",
    dusunceBas: null,
    sayac: null,
    sayacDurdur: null,
    model: "",
    mod(m) {
      // Claude'daki canli simge gibi: baykus isin asamasina gore hareket eder
      const b = d.querySelector(".baykus-canli");
      if (!m) { b.hidden = true; return; }
      b.hidden = false;
      b.dataset.mod = m;
      b.querySelector(".baykus-etiket").textContent = { bekliyor: "Hazırlanıyor…", dusunuyor: "Düşünüyor…", calisiyor: "Çalışıyor…", yaziyor: "Yazıyor…" }[m] || "";
    },
    canliBaslat(model) {
      this.mod("bekliyor");
      // beklerken "Model hazirlaniyor... 8 sn" gibi canli sayac
      this.model = model;
      this.sayacDurdur = canliSayac(d.querySelector(".durum-satiri .sayac"), "· ");
      // Claude gibi alt satir: "••• 1m 54s · 845 tokens" (token: akan metinden tahmin)
      const alt = d.querySelector(".canli-alt");
      const bas = performance.now();
      alt.hidden = false;
      const yaz = () => {
        const sn = Math.round((performance.now() - bas) / 1000);
        const sure = sn < 60 ? `${sn}s` : `${Math.floor(sn / 60)}m ${sn % 60}s`;
        const token = Math.round((this.metin.length + this.dusunce.length + (this.aracKarakter || 0)) / 4);
        alt.querySelector(".canli-sure").textContent = `${sure} · ${sayi(token, 0)} tokens`;
      };
      yaz();
      this.altSayac = setInterval(yaz, 500);
    },
    gecen() {
      clearInterval(this.altSayac);
      d.querySelector(".canli-alt").hidden = true;
      const etk = d.querySelector(".etkinlik-baslik");
      if (!etk.hidden) { // bitti: "Editing" yerine kac adim calistigi
        const n = d.querySelectorAll(".arac-adimlari .arac-adim:not([hidden])").length;
        etk.querySelector(".etkinlik-metin").textContent = n ? `${n} adım` : "Tamamlandı";
        etk.classList.remove("parilti");
      }
      return this.sayacDurdur ? this.sayacDurdur() : null;
    },
    etkinlik(ad, arg) {
      const etk = d.querySelector(".etkinlik-baslik");
      etk.hidden = false;
      etk.classList.toggle("parilti", !!this.altSayac); // kayitli mesajda canli parilti yok
      this.aracKarakter = (this.aracKarakter || 0) + JSON.stringify(arg || {}).length;
      const ETIKET = [[/dosya_(yaz|yama|tasi|sil)|ajan_olustur|uzanti_yaz/, "Düzenliyor"],
        [/komut_calistir|cli_ye_yaptir/, "Komut çalıştırıyor"], [/web_|tarayici_/, "Web'de arıyor"],
        [/oku|listele|ara|glob|git_|kod_|gorsel/, "Okuyor"], [/plan_guncelle/, "Planlıyor"],
        [/alt_ajan|is_emri|alt_oturum/, "Ajan başlatıyor"]];
      etk.querySelector(".etkinlik-metin").textContent = (ETIKET.find(([r]) => r.test(ad)) || [null, "Araç kullanıyor"])[1];
    },
    durum(metin) {
      const s = d.querySelector(".durum-satiri");
      s.hidden = !metin;
      s.querySelector("span").textContent = metin || "";
    },
    dusunceEkle(parca) {
      this.mod("dusunuyor");
      if (!this.dusunceBas) {
        this.dusunceBas = performance.now();
        this.durum("");
        dusunceKutu.hidden = false;
        dusunceKutu.classList.add("acik");
        const etiket = d.querySelector(".dusunce-etiket");
        etiket.classList.add("parilti");
        this.sayac = setInterval(() => {
          etiket.textContent = `Düşünüyor… ${Math.round((performance.now() - this.dusunceBas) / 1000)} sn`;
        }, 500);
      }
      this.dusunce += parca;
      const ic = d.querySelector(".dusunce-icerik");
      const altta = ic.scrollHeight - ic.scrollTop - ic.clientHeight < 40;
      ic.textContent = this.dusunce;
      if (altta) ic.scrollTop = ic.scrollHeight;
    },
    dusunceBitir(sn) {
      if (!this.dusunce) return;
      clearInterval(this.sayac);
      this.sayac = null;
      const sure = sn ?? (this.dusunceBas ? (performance.now() - this.dusunceBas) / 1000 : null);
      const etiket = d.querySelector(".dusunce-etiket");
      etiket.classList.remove("parilti");
      etiket.textContent = sure != null ? `Düşündü (${sayi(sure, 0)} sn)` : "Düşünce";
      dusunceKutu.classList.remove("acik");
    },
    parcaEkle(parca) {
      if (this.sayacDurdur) this.mod("yaziyor");
      if (this.dusunceBas && this.sayac) this.dusunceBitir();
      this.durum("");
      this.metin += parca;
      if (this.cizimBekliyor) return; // uzun cevapta her parcada tum metni yeniden isleme
      this.cizimBekliyor = true;
      requestAnimationFrame(() => {
        this.cizimBekliyor = false;
        const g = d.querySelector(".govde-metin");
        g.innerHTML = md(this.metin);
        ikonlariYerlestir(g);
      });
    },
    planCiz(adimlar) {
      // Claude Code gibi yapilacaklar listesi: model plan_guncelle cagirdikca yerinde guncellenir
      if (!Array.isArray(adimlar) || !adimlar.length) return;
      const k = d.querySelector(".sohbet-plan");
      const biten = adimlar.filter((a) => a.durum === "tamam" || a.durum === "atlandi").length;
      k.hidden = false;
      k.innerHTML = `<div class="sohbet-plan-baslik soluk kucuk">Plan · ${biten}/${adimlar.length}</div><ul class="plan-liste">${adimlar
        .map((a) => `<li class="plan-${kacir(a.durum || "bekliyor")}">${kacir(a.baslik || "")}</li>`).join("")}</ul>`;
    },
    aracCagrisi(o) {
      this.durum("");
      this.etkinlik(o.ad, o.argumanlar);
      if (this.sayacDurdur) this.mod("calisiyor");
      if (o.ad === "alt_oturum_oner") {
        if (this.sayac) this.dusunceBitir();
        return altOturumKarti(o, d.querySelector(".arac-adimlari"));
      }
      if (o.ad === "arayuz_goster") { // Claude gibi: sohbette sandbox'li mini arayuz karti
        if (this.sayac) this.dusunceBitir();
        if (!d.querySelector(`.arayuz-kart[data-id="${CSS.escape(o.id)}"]`)) arayuzKarti(o, d.querySelector(".arac-adimlari"));
        const g = el(`<div class="arac-adim" data-id="${kacir(o.id)}" hidden><span class="ozet"></span><pre class="arac-sonuc"></pre></div>`);
        d.querySelector(".arac-adimlari").append(g);
        return g;
      }
      if (o.ad === "plan_guncelle") {
        if (this.sayac) this.dusunceBitir();
        this.planCiz(o.argumanlar?.adimlar);
        const g = el(`<div class="arac-adim" data-id="${kacir(o.id)}" hidden><span class="ozet"></span><pre class="arac-sonuc"></pre></div>`);
        d.querySelector(".arac-adimlari").append(g);
        return g;
      }
      if (this.sayac) this.dusunceBitir();
      const arg = Object.entries(o.argumanlar || {}).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ");
      const a = el(`<div class="arac-adim" data-id="${kacir(o.id)}">
        <button class="arac-baslik"><span data-ikon="anahtar"></span><code>${kacir(o.ad)}(${kacir(arg)})</code>
        <span class="ozet parilti">çalışıyor…</span><span class="ok" data-ikon="sag"></span></button>
        <pre class="duz arac-sonuc"></pre></div>`);
      a.querySelector(".arac-baslik").onclick = () => a.classList.toggle("acik");
      aracGrubu(d.querySelector(".arac-adimlari"), o.ad).ekle(a);
      return a;
    },
    aracSonucu(o) {
      if (o.ad === "alt_oturum_oner") { // canli akista kart cagrida cizildi; kayitli mesajda burada
        if (![...d.querySelectorAll(".oneri-kart")].some((x) => x.dataset.id === o.id)) this.aracCagrisi(o);
        return;
      }
      const a = [...d.querySelectorAll(".arac-adim")].find((x) => x.dataset.id === o.id) || this.aracCagrisi(o);
      if ((o.ad === "is_emri_baslat" || o.ad === "is_emirleri_durum") && !d.querySelector(`.thread-kart[data-id="${o.id}"]`)) {
        let ids = [];
        try { ids = (JSON.parse(o.sonuc).threadler || []).map((t) => t.id); } catch { /* hata metni: kart yok */ }
        if (ids.length) threadKarti(ids, d.querySelector(".arac-adimlari")).dataset.id = o.id;
      }
      if (o.ad === "plan_guncelle") {
        try { this.planCiz(JSON.parse(o.sonuc).plan); } catch { /* hata/kesik: arguman cizimi kalir */ }
        return;
      }
      if (o.ad === "arayuz_goster" && o.durum !== "hata") return; // kart cagrida cizildi
      if (o.ad === "onizleme_baslat" && o.durum !== "hata" && !d.querySelector(`.onizleme-kart[data-id="${CSS.escape(o.id)}"]`)) {
        onizlemeKarti(o, d.querySelector(".arac-adimlari"));
      }
      const ozet = a.querySelector(".ozet");
      const hataVar = o.durum === "hata" || (o.ozet || "").startsWith("hata");
      const sonucsuz = o.durum === "sonucsuz";
      ozet.classList.remove("parilti");
      ozet.classList.toggle("hata", hataVar);
      ozet.classList.toggle("sonucsuz", sonucsuz);
      const isaret = hataVar ? "✗" : sonucsuz ? "⦸" : "✓"; // basari ikonu yalniz gercek sonucta
      ozet.textContent = `${isaret} ${o.ozet}${o.truncated ? " · kısaltıldı" : ""}`;
      a.closest(".arac-grup")?.grupGuncelle?.();
      let goster = o.sonuc;
      try { goster = JSON.stringify(JSON.parse(o.sonuc), null, 1); } catch { /* kesik JSON: oldugu gibi */ }
      a.querySelector(".arac-sonuc").textContent = goster;
    },
    uyari(mesaj) {
      d.querySelector(".uyarilar").append(el(`<div class="uyari-kutu">${kacir(mesaj)}</div>`));
    },
    hata(mesaj) {
      this.mod(null);
      clearInterval(this.sayac);
      this.hataVar = true;
      this.durum("");
      d.querySelector(".uyarilar").append(el(`<div class="hata-kutu">${kacir(mesaj)}</div>`));
    },
    bitir(ist, zaman, m) {
      this.mod(null);
      const gecen = this.gecen();
      this.sayacDurdur = null;
      this.durum("");
      this.dusunceBitir(ist?.dusunce_sn);
      if (!ist && gecen != null) ist = { model: this.model, sure_sn: Math.round(gecen * 10) / 10, durduruldu: true };
      const alt = d.querySelector(".mesaj-alt");
      alt.hidden = false;
      alt.querySelector(".istat").innerHTML = istatistikCipleri(ist);
      alt.querySelector(".kopya").onclick = () => kopyala(this.metin);
      saatYaz(alt.querySelector(".mesaj-saat"), zaman);
      if (m?.id) {
        alt.querySelector(".dallan").hidden = false;
        alt.querySelector(".sabitle").hidden = false;
        mesajDugmeleri(d, m);
      }
      sesliOkuBagla(alt.querySelector(".sesli-oku"), () => d.querySelector(".govde-metin").textContent);
    },
  };
  return o;
}

let okumaSayaci = 0;
// Sesli oku: tarayicinin kendi Turkce sesi (ek paket/ag yok). Ayni dugme durdurur.
function sesliOkuBagla(b, metin) {
  if (!("speechSynthesis" in window)) { b.hidden = true; return; }
  b.onclick = () => {
    const s = window.speechSynthesis;
    const bu = b.getAttribute("aria-pressed") === "true";
    const buId = ++okumaSayaci;
    s.cancel();
    document.querySelectorAll('.sesli-oku[aria-pressed="true"]').forEach((x) => x.setAttribute("aria-pressed", "false"));
    if (bu) return;
    const u = new SpeechSynthesisUtterance((metin() || "").replace(/\s+/g, " ").trim());
    u.lang = "tr-TR";
    u.onend = u.onerror = () => { if (buId === okumaSayaci) b.setAttribute("aria-pressed", "false"); };
    b.setAttribute("aria-pressed", "true");
    s.speak(u);
  };
}

function kaydedilmisAsistan(m) {
  const o = asistanMesaji();
  if (m.dusunce) {
    o.dusunce = m.dusunce;
    const k = o.el.querySelector(".dusunce");
    k.hidden = false;
    o.el.querySelector(".dusunce-icerik").textContent = m.dusunce;
  }
  for (const a of m.araclar || []) o.aracSonucu(a);
  if (m.metin) o.parcaEkle(m.metin);
  if (m.hata) o.hata(m.hata);
  o.bitir({ ...m.istatistik, model: m.istatistik?.model || m.model }, m.zaman, m);
  return o.el;
}

export function bosDurum(goster) {
  $("#bos-durum").hidden = !goster;
}

const PENCERE = 40;

export function mesajlariCiz(oturum) {
  aktifGorev = null;
  gonderDurumu();
  oneriKararlari = { ...(oturum?.oneri_kararlari || {}) };
  $("#mesajlar .mesaj-sutun")?.remove();
  if (!oturum || !oturum.mesajlar.length) { bosDurum(true); return; }
  const s = sutun();
  // Uzun sohbet: yalniz son PENCERE mesaj DOM'a girer; eskiler istenince parti parti eklenir.
  const ciz = (m) => (m.rol === "kullanici" ? kullaniciMesaji(m) : kaydedilmisAsistan(m));
  let bas = Math.max(0, oturum.mesajlar.length - PENCERE);
  for (const m of oturum.mesajlar.slice(bas)) s.append(ciz(m));
  const dahaEski = () => {
    if (!bas) return;
    const btn = el(`<button class="btn eski-mesajlar">Daha eski ${bas} mesajı göster</button>`);
    btn.onclick = () => {
      const kutu = $("#mesajlar");
      const onceYukseklik = kutu.scrollHeight;
      const yeniBas = Math.max(0, bas - PENCERE);
      const parca = document.createDocumentFragment();
      for (const m of oturum.mesajlar.slice(yeniBas, bas)) parca.append(ciz(m));
      btn.replaceWith(parca);
      bas = yeniBas;
      ikonlariYerlestir(s);
      kutu.scrollTop += kutu.scrollHeight - onceYukseklik; // okunan yer kaymasin
      dahaEski();
      s.querySelector(".eski-mesajlar")?.focus();
    };
    s.prepend(btn);
  };
  dahaEski();
  ikonlariYerlestir(s);
  sonaKaydir(true);
}

export function yeniSohbetEkrani({ girdiyiKoru = false } = {}) {
  durdur();
  durum.oturumId = null;
  oneriTemizle();
  siradakiler.length = 0;
  siraCiz();
  bekleyenEkler.splice(0).forEach((e) => { if (e.onizleme) URL.revokeObjectURL(e.onizleme); });
  ekleriCiz();
  mesajlariCiz(null);
  if (!girdiyiKoru) $("#girdi").value = ""; // acilista kullanicinin o ana dek yazdigi silinmesin
  boyutla();
  gonderDurumu();
  setTimeout(() => $("#girdi").focus(), 0);
}

let gonderKilit = false;
// ---- gonderme / akis ----
export async function gonder() {
  if (gonderKilit) return;
  gonderKilit = true;
  oneriTemizle();
  const girdi = $("#girdi");
  let oturumId = null;
  try {
    let metin;
    try {
      metin = await anahtarCoz(girdi.value.trim()); // anahtar kasaya, mesaja yalniz adi
    } catch (e) {
      bildir(`Anahtar kasaya kaydedilemedi, mesaj gönderilmedi: ${e.message}`, "hata");
      return;
    }
    if (komutMu(metin, (istem) => { gonderKilit = false; $("#girdi").value = istem; gonder(); })) { // yerel slash komut
      girdi.value = "";
      boyutla();
      return;
    }
    if (akisKontrol && girdi.value.trim()) { // Claude Code gibi: yanit surerken yazilan mesaj siraya girer
      siradakiler.push(girdi.value);
      girdi.value = "";
      boyutla();
      siraCiz();
      return;
    }
    if (akisKontrol || (!metin && !bekleyenEkler.length) || bekleyenEkler.some((e) => e.yukleniyor)) return;
    // Claude Code kisayollari (tek satir, eksiz): "!komut" kabukta calisir, "#not" hafizaya yazilir
    if (!bekleyenEkler.length && !metin.includes("\n")) {
      if (/^!\s*\S/.test(metin)) { girdi.value = ""; boyutla(); gonderDurumu(); kabukCalistir(metin.slice(1).trim()); return; }
      if (/^#\s*[^#\s]/.test(metin)) { girdi.value = ""; boyutla(); gonderDurumu(); hafizaNotu(metin.slice(1).trim()); return; }
    }
    if (duzenlenen) { // duzenlenen mesaj ve cevabi once kesilir, sonra yeni metin normal gonderilir
      const { m, oid } = duzenlenen;
      duzenlenen = null;
      if (oid === durum.oturumId) {
        try {
          await api(`/api/oturumlar/${oid}/geri-sar`, { method: "POST", govde: m.id ? { mesaj_id: m.id } : { run: m.run } });
          await geriCagri.oturumAc(oid, true);
        } catch (e) { bildir(e.message, "hata"); return; }
      }
    }
    const ekler = bekleyenEkler.splice(0);
    ekler.forEach((e) => { if (e.onizleme) URL.revokeObjectURL(e.onizleme); });
    girdi.value = "";
    boyutla();
    ekleriCiz();
    try {
      if (!durum.oturumId) {
        const o = await api("/api/oturumlar", { method: "POST" });
        durum.oturumId = o.id;
      }
    } catch (e) {
      bildir(e.message, "hata");
      return;
    }
    oturumId = durum.oturumId;
    // Claude Code gibi: proje aciksa (ve mod sohbet degilse) mesaj AJAN olarak calisir
    if (ajanModu() && !ekler.length) {
      ajanGonderiliyor = true;
      try {
        await ajanaGonder(oturumId, metin);
      } catch (e) {
        if (durum.oturumId === oturumId && !girdi.value) {
          girdi.value = metin;
          boyutla();
        }
        bildir(e.message, "hata");
      } finally {
        ajanGonderiliyor = false;
        gonderDurumu();
      }
      return;
    }
    var akisBasliyor = { metin, ekler };
  } finally {
    gonderKilit = false;
  }
  const { metin, ekler } = akisBasliyor;
  const s = sutun();
  const yanit = asistanMesaji();
  yanit.canliBaslat(durum.ayarlar?.model);
  let kullaniciCizildi = false;
  akisKontrol = new AbortController();
  calisanOturumId = oturumId;
  document.querySelector(`.oturum[data-id="${oturumId}"]`)?.classList.add("calisiyor");
  gonderDurumu();
  try {
    for await (const o of sseOku(`/api/oturumlar/${oturumId}/mesaj`, { metin, ekler: ekler.map((e) => e.id) }, akisKontrol.signal)) {
      if (durum.oturumId !== oturumId) continue; // kullanici baska sohbete gecti
      switch (o.tur) {
        case "kullanici_mesaji":
          s.append(kullaniciMesaji(o.mesaj), yanit.el);
          kullaniciCizildi = true;
          ikonlariYerlestir(s);
          yanit.durum("Hazırlanıyor…");
          geriCagri.baslikAyarla(o.baslik);
          geriCagri.oturumlarYenile();
          sonaKaydir(true);
          break;
        case "durum":
        case "ilerleme":
          if (!yanit.metin) yanit.durum(o.metin);
          break;
        case "dusunce":
          yanit.dusunceEkle(o.metin);
          sonaKaydir();
          break;
        case "parca":
          yanit.parcaEkle(o.metin);
          sonaKaydir();
          break;
        case "arac_cagrisi":
          yanit.aracCagrisi(o);
          ikonlariYerlestir(yanit.el);
          sonaKaydir();
          break;
        case "arac_sonucu":
          yanit.aracSonucu(o);
          break;
        case "uyari":
          yanit.uyari(o.metin);
          break;
        case "hata":
          yanit.hata(o.mesaj);
          break;
        case "bitti":
          yanit.bitir(o.mesaj.istatistik, o.mesaj.zaman, o.mesaj);
          if (durum.ayarlar?.bildirim_yanit) masaustuBildirimi("Kairo yanıtladı", (o.mesaj.metin || "").slice(0, 140));
          if (sesliModAcik() && (o.mesaj?.metin || "").trim()) yanit.el.querySelector(".sesli-oku")?.click();
          break;
      }
    }
  } catch (e) {
    if (!kullaniciCizildi) {
      s.append(kullaniciMesaji({ metin, ekler }), yanit.el);
      ikonlariYerlestir(s);
    }
    if (e.name === "AbortError") yanit.hata("Durduruldu.");
    else yanit.hata(e.message);
  } finally {
    clearInterval(yanit.sayac);
    if (yanit.el.querySelector(".mesaj-alt").hidden) yanit.bitir(null); // hata/durdurma
    akisKontrol = null;
    calisanOturumId = null;
    document.querySelectorAll(".oturum.calisiyor").forEach((x) => x.classList.remove("calisiyor"));
    gonderDurumu();
    geriCagri.oturumlarYenile();
    if (siradakiler.length && durum.oturumId === oturumId) { // sirada bekleyen ilk mesaj sonraki tur olarak gider
      $("#girdi").value = siradakiler.shift();
      siraCiz();
      gonder();
    } else if (siradakiler.length) {
      siradakiler.length = 0;
      siraCiz();
    } else sonrakiOneri();
  }
}

// ---- sonraki mesaj onerisi (Claude Code gibi soluk metin, Tab ile al) ----
const VARSAYILAN_YER = "Ne üzerinde çalışalım?";
function oneriTemizle() {
  const g = $("#girdi");
  delete g.dataset.oneri;
  g.placeholder = VARSAYILAN_YER;
  g.classList.remove("oneri-var");
}
let oneriSayac = 0;
export async function sonrakiOneri() {
  const kullanicilar = $$("#mesajlar .mesaj.kullanici .balon");
  const asistanlar = $$("#mesajlar .mesaj.asistan");
  const asistan = asistanlar[asistanlar.length - 1]?.innerText || "";
  if (!asistan.trim()) return;
  const no = ++oneriSayac;
  const oturum = durum.oturumId;
  try {
    const { oneri } = await api("/api/sonraki-oneri", { method: "POST", govde: {
      kullanici: (kullanicilar[kullanicilar.length - 1]?.innerText || "").slice(-4000),
      asistan: asistan.slice(-6000),
    } });
    const g = $("#girdi");
    // bu arada yeni tur, baska sohbet ya da yazilmaya baslanmis girdi: oneri gosterilmez
    if (!oneri || no !== oneriSayac || oturum !== durum.oturumId || g.value || akisVar()) return;
    g.dataset.oneri = oneri;
    g.placeholder = `${oneri}   (Tab)`;
    g.classList.add("oneri-var");
  } catch { /* oneri istege bagli */ }
}
document.addEventListener("ajan-tur-bitti", () => sonrakiOneri());

// ---- yanit surerken yazilan mesajlarin sirasi ----
const siradakiler = [];
function siraCiz() {
  let kap = $("#sira-listesi");
  if (!kap) {
    kap = el('<div id="sira-listesi" class="sira-listesi" aria-live="polite"></div>');
    $("#yazma").prepend(kap);
  }
  kap.innerHTML = "";
  siradakiler.forEach((m, i) => {
    const c = el(`<div class="sira-oge"><span class="soluk kucuk">Sırada</span><span class="sira-metin">${kacir(m)}</span>
      <button class="ikon-btn kucuk" title="Sıradan çıkar" aria-label="Sıradan çıkar">${ikon("x")}</button></div>`);
    c.querySelector("button").onclick = () => { siradakiler.splice(i, 1); siraCiz(); };
    kap.append(c);
  });
  kap.hidden = !siradakiler.length;
}

export function durdur() {
  akisKontrol?.abort();
}

// "!komut": kullanicinin KENDI komutu (Terminal paneliyle ayni uc). Model calistirmadigi icin onay
// sorulmaz; cikti modele kendiliginden gitmez, istenirse "Mesaja ekle" ile girdiye alinir.
async function kabukCalistir(komut) {
  const s = sutun();
  bosDurum(false);
  const kap = el(`<div class="mesaj asistan"><pre class="adim-cikti kabuk-cikti">çalışıyor…</pre>
    <div class="kabuk-alt soluk kucuk"><span class="kabuk-durum parilti">çalışıyor…</span>
    <button class="btn" data-durdur>Durdur</button><button class="btn" data-ekle hidden>Mesaja ekle</button></div></div>`);
  s.append(kullaniciMesaji({ metin: `!${komut}`, ekler: [] }), kap);
  ikonlariYerlestir(s);
  sonaKaydir(true);
  const cikti = kap.querySelector(".kabuk-cikti");
  const durumEl = kap.querySelector(".kabuk-durum");
  try {
    let is = await api("/api/terminal", { method: "POST", govde: { komut } });
    kap.querySelector("[data-durdur]").onclick = () => api(`/api/komutlar/${is.id}/durdur`, { method: "POST" }).catch((e) => bildir(e.message, "hata"));
    while (is.durum === "calisiyor") {
      await new Promise((r) => setTimeout(r, 600));
      if (!kap.isConnected) return; // baska sohbete gecildi; komut Arka plan islerinde gorunur
      is = await api(`/api/komutlar/${is.id}`);
      cikti.textContent = is.cikti || "çalışıyor…";
      sonaKaydir();
    }
    cikti.textContent = is.cikti || "(çıktı yok)";
    durumEl.classList.remove("parilti");
    durumEl.textContent = `${is.durum}${is.cikis_kodu == null ? "" : ` · çıkış ${is.cikis_kodu}`}${is.sure_sn == null ? "" : ` · ${sayi(is.sure_sn)} sn`}`;
    kap.querySelector("[data-durdur]").hidden = true;
    const ekle = kap.querySelector("[data-ekle]");
    ekle.hidden = false;
    ekle.onclick = () => {
      const g = $("#girdi");
      g.value = `${g.value}${g.value ? "\n" : ""}\`${komut}\` çıktısı (çıkış ${is.cikis_kodu}):\n\`\`\`\n${(is.cikti || "").slice(-6000)}\n\`\`\`\n`;
      boyutla();
      gonderDurumu();
      g.focus();
    };
  } catch (e) {
    cikti.textContent = "";
    durumEl.classList.remove("parilti");
    durumEl.textContent = "";
    kap.append(el(`<div class="hata-kutu">${kacir(e.message)}</div>`));
    kap.querySelector("[data-durdur]").hidden = true;
  }
}

// "#not": kalici hafizaya (acik projenin kapsaminda) not ekler; modele mesaj gitmez.
async function hafizaNotu(not) {
  try {
    await api("/api/hafiza", { method: "POST", govde: { metin: not, kapsam: projeDurumu.aktif?.id || "genel" } });
    bildir(`Hafızaya eklendi${projeDurumu.aktif ? ` (${projeDurumu.aktif.ad})` : ""}. /memory ile yönetebilirsin.`, "basari", 3000);
  } catch (e) {
    bildir(e.message, "hata");
    $("#girdi").value = `#${not}`; // yazilan kaybolmasin
    boyutla();
    gonderDurumu();
  }
}

let ajanGonderiliyor = false; // gorev baslarken liste yoklamasi ekrani bos sunucu kaydiyla ezmesin
export function akisVar() {
  return !!akisKontrol || ajanGonderiliyor;
}

// ---- yardimci ----
async function kopyala(metin) {
  try {
    await navigator.clipboard.writeText(metin || "");
    bildir("Kopyalandı", "basari", 1500);
  } catch {
    bildir("Kopyalanamadi", "hata");
  }
}

function kodKopyala(e) {
  const b = e.target.closest(".kod-kopyala");
  if (b) kopyala(b.closest("pre").querySelector("code").textContent);
}

export { modelAdi };

// ---- sohbet = ajan (Claude Code Desktop duzeni) ----
// shortcut: gorev-sohbet baglantisi tarayicida (localStorage) tutulur; baska cihazda gorunmez,
// sunucuda oturum kaydina tasimak sonraki adim.
const AJAN_ANAHTAR = "ajanRunlari";
function ajanKayitlari() {
  try { return JSON.parse(localStorage.getItem(AJAN_ANAHTAR) || "{}"); } catch { return {}; }
}
function ajanKaydet(oturumId, kayit, sunucuya = true) {
  const t = ajanKayitlari();
  if ((t[oturumId] ||= []).some((k) => k.run === kayit.run)) return;
  t[oturumId].push(kayit);
  try { localStorage.setItem(AJAN_ANAHTAR, JSON.stringify(t)); } catch { /* depolama kapali */ }
  if (sunucuya) api(`/api/oturumlar/${oturumId}/ajan-run`, { method: "POST", govde: kayit }).catch(() => {});
}
/** Sunucudaki kayitlar (kalici) ile tarayici onbellegini birlestirir; yalniz yerelde olanlar
 * sunucuya tasinir. Port her acilista degistigi icin tarayici deposu tek basina kayboluyordu. */
export function ajanKayitlariniBirlestir(oturum) {
  for (const k of oturum.ajan_runlari || []) ajanKaydet(oturum.id, k, false);
  const sunucu = new Set((oturum.ajan_runlari || []).map((k) => k.run));
  for (const k of ajanKayitlari()[oturum.id] || []) {
    if (!sunucu.has(k.run)) api(`/api/oturumlar/${oturum.id}/ajan-run`, { method: "POST", govde: k }).catch(() => {});
  }
}
function ajanModu() {
  // Proje acik olmasa da (kisisel klasorler) ajan calisir; yalniz 'sohbet' modu duz sohbettir
  const mod = projeDurumu.izin?.mod;
  return Boolean(mod) && mod !== "sohbet";
}
function ajanBlogu(kayit) {
  const kap = el(`<div class="mesaj asistan ajan-mesaj"><div class="gr-detay" aria-live="polite"><div class="parilti">Ajan başlıyor…</div></div></div>`);
  return { kap, detay: kap.querySelector(".gr-detay"), kayit };
}
function sohbetGoreviniIzle(detay, id, oturumId, ilkDurum) {
  const durumBildir = (runDurumu) => {
    if (oturumId !== durum.oturumId || !detay.isConnected) return;
    if (!BITMIS_RUN.has(runDurumu)) aktifGorev = { detay, id, oturumId };
    else if (aktifGorev?.id === id) aktifGorev = null;
    gonderDurumu();
  };
  if (ilkDurum) durumBildir(ilkDurum);
  sohbetteGorevGoster(detay, id, durumBildir);
}

const BITMIS_RUN = new Set(["iptal", "basarili", "dogrulanmadi", "basarisiz"]);

async function ajanaGonder(oturumId, metin) {
  const s = sutun();
  const balon = kullaniciMesaji({ rol: "kullanici", metin, ekler: [] });
  s.append(balon);
  bosDurum(false);
  const kayitlar = ajanKayitlari()[oturumId] || [];
  const son = kayitlar[kayitlar.length - 1];
  try {
    if (son) { // calisan gorev varsa yeni mesaj YONLENDIRME olur (Claude Code'da calisirken yazmak gibi)
      const r = await api(`/api/gorevler/${son.run}`);
      if (!BITMIS_RUN.has(r.durum)) {
        await api(`/api/gorevler/${son.run}/mesaj`, { method: "POST", govde: { metin } });
        // Claude Code gibi: mesajin calisan goreve sira ile verildigi balonda gorunur
        balon.append(el('<div class="sira-rozet soluk kucuk"><span class="rozet sari">sırada</span> Çalışan göreve iletildi; ajan sıradaki adımdan önce okuyup cevaplar.</div>'));
        sonaKaydir(true);
        return;
      }
    }
    const izole = !!document.getElementById("hap-izole")?.checked;
    // onceki: ayni sohbetin son gorevi -> ajan onceki turlarin ozetini gorur (konusma surekliligi)
    const r = await api("/api/gorevler", { method: "POST", govde: { hedef: metin, izole, onceki: son?.run || "", etkilesimli: true } });
    ajanKaydet(oturumId, { run: r.id, metin });
    if (!kayitlar.length) await api(`/api/oturumlar/${oturumId}`, { method: "PATCH", govde: { baslik: metin.slice(0, 60) } }).catch(() => {});
    document.dispatchEvent(new Event("oturumlar-degisti")); // baslik kaydedildikten SONRA
    const b = ajanBlogu({ run: r.id, metin });
    s.append(b.kap);
    sohbetGoreviniIzle(b.detay, r.id, oturumId, r.durum);
    sonaKaydir(true);
  } catch (e) {
    balon.remove();
    throw e;
  }
}

/** Oturum acilinca bu sohbete bagli ajan gorevlerini akisa ekler; sonuncusu canli izlenir. */
export function ajanBloklariniCiz(oturumId) {
  const kayitlar = ajanKayitlari()[oturumId] || [];
  if (!kayitlar.length) return;
  const s = $("#mesajlar .mesaj-sutun") || sutun();
  bosDurum(false);
  kayitlar.forEach((k, i) => {
    s.append(kullaniciMesaji({ rol: "kullanici", metin: k.metin, ekler: [], run: k.run }));
    const b = ajanBlogu(k);
    s.append(b.kap);
    if (i === kayitlar.length - 1) sohbetGoreviniIzle(b.detay, k.run, oturumId);
    // onceki turlar: sonuc markdown olarak (son tur gibi), hata duz metin
    else api(`/api/gorevler/${k.run}`).then((r) => {
      b.detay.innerHTML = r.sonuc?.ozet
        ? `<div class="ajan-sonuc ajan-rapor"><div class="md">${md(r.sonuc.ozet)}</div>${gorevRaporEylemleri()}</div>`
        : `<div class="uyari-kutu">${kacir(r.hata || r.durum)}</div>`;
      ikonlariYerlestir(b.detay);
      gorevRaporEylemleriniBagla(b.detay, r);
    }).catch(() => {});
  });
  ikonlariYerlestir(s);
  sonaKaydir(true);
}

export const ajanliOturum = (id) => Boolean(ajanKayitlari()[id]?.length);
/** Bu sohbete bagli ajan gorevleri ({run, metin}); /cost, /todos, /export icin. */
export const sohbetRunlari = (id) => ajanKayitlari()[id] || [];
