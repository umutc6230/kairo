// Ortak durum ve yardimcilar: API, SSE akisi, bildirim, modal, menu. Native dialog YOK.
import { ikon, ikonlariYerlestir } from "./ikonlar.js";
import { kacir } from "./md.js";

export const durum = {
  bilgi: null, // /api/bilgi
  sunucu: null, // /api/durum
  ayarlar: null, // /api/ayarlar
  oturumId: null,
  oturumlar: [],
  gorunum: "sohbet",
};

// Skill'den gelen ASCII metinlerin arayuzde gorunen Turkce karsiliklari.
const DUSUNME_TR = {
  kapali: { ad: "Kapalı (hızlı)", kisa: "Kapalı", aciklama: "Cevap hemen gelir. OCR, özet, çeviri, veri çıkarma için yeterli.", sure: "birkaç saniye" },
  dengeli: { ad: "Dengeli", kisa: "Dengeli", aciklama: "Kısa düşünür (en fazla 1024 token). Hesap ve mantık sorularında daha doğru.", sure: "~30 sn - 3 dk" },
  derin: { ad: "Derin (en iyi sonuç)", kisa: "Derin", aciklama: "Sınırsız düşünür. Zor problem, karar ve analiz için; bekleme uzun olabilir.", sure: "~1 - 10 dk" },
};
const MODEL_TR = {
  "deepseek-heretic": "Varsayılan. Metin, OCR, araç çağırma, JSON.",
  "gemma4-12b-heretic": "En güçlü. Metin, OCR, araç, ses. ~9-10 GB boş RAM ister.",
  "gemma4-e4b-heretic": "Hafif. Metin, OCR, araç, ses.",
};

/** /api/bilgi ve /api/durum metinlerini Turkcelestirir (anahtar/deger ayni kalir). */
export function turkcelestir(bilgi, sunucu) {
  if (bilgi) bilgi.dusunme_secenekleri = bilgi.dusunme_secenekleri.map((d) => ({ ...d, ...(DUSUNME_TR[d.deger] || {}) }));
  if (sunucu) for (const m of sunucu.modeller || []) m.aciklama = MODEL_TR[m.anahtar] || m.aciklama;
}

export const $ = (s, kok = document) => kok.querySelector(s);
export const $$ = (s, kok = document) => [...kok.querySelectorAll(s)];

export function el(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  const e = t.content.firstElementChild;
  ikonlariYerlestir(e);
  return e;
}

/** Oturum anahtari: sunucu index.html'e gomer. Baska origin bu sayfayi okuyamaz (A1.9). */
const OTURUM_ANAHTARI = document.querySelector('meta[name="yas-oturum"]')?.content || "";
export const oturumBasligi = () => (OTURUM_ANAHTARI ? { "X-YAS-Oturum": OTURUM_ANAHTARI } : {});

export async function api(yol, { method = "GET", govde, form } = {}) {
  const secenek = { method, headers: { ...oturumBasligi() } };
  if (form) secenek.body = form;
  else if (govde !== undefined) {
    secenek.headers["Content-Type"] = "application/json";
    secenek.body = JSON.stringify(govde);
  }
  let r;
  try {
    r = await fetch(yol, secenek);
  } catch {
    throw new Error("Uygulama sunucusuna ulasilamadi.");
  }
  const veri = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(veri.hata || hataMetni(veri) || `Hata (${r.status})`);
  return veri;
}

/** <img data-ek="id">: img etiketi oturum basligini gonderemez (403), resmi fetch+blob ile yukle. */
export function ekResimleriYukle(kok) {
  kok.querySelectorAll("img[data-ek]").forEach(async (img) => {
    const r = await fetch(`/api/ekler/${img.dataset.ek}`, { headers: oturumBasligi() }).catch(() => null);
    if (r?.ok) img.src = URL.createObjectURL(await r.blob());
  });
}

function hataMetni(veri) {
  if (Array.isArray(veri.detail)) return veri.detail.map((d) => d.msg).join("; ");
  return typeof veri.detail === "string" ? veri.detail : "";
}

/** POST/GET + text/event-stream: her "data: {...}" olayini verir. signal ile durdurulur. */
export async function* sseOku(yol, govde, signal) {
  const getMi = govde === undefined;
  const r = await fetch(yol, {
    method: getMi ? "GET" : "POST",
    headers: getMi ? { ...oturumBasligi() } : { "Content-Type": "application/json", ...oturumBasligi() },
    body: getMi ? undefined : JSON.stringify(govde),
    signal,
  });
  if (!r.ok) {
    const veri = await r.json().catch(() => ({}));
    throw new Error(veri.hata || hataMetni(veri) || `Hata (${r.status})`);
  }
  const okuyucu = r.body.getReader();
  const cozucu = new TextDecoder();
  let tampon = "";
  for (;;) {
    const { value, done } = await okuyucu.read();
    if (done) break;
    tampon += cozucu.decode(value, { stream: true });
    let i;
    while ((i = tampon.indexOf("\n\n")) >= 0) {
      const blok = tampon.slice(0, i);
      tampon = tampon.slice(i + 2);
      const satir = blok.split("\n").find((s) => s.startsWith("data: "));
      if (satir) yield JSON.parse(satir.slice(6));
    }
  }
}

export function bildir(metin, tur = "bilgi", sureMs = 4500) {
  const ikonAdi = { hata: "uyari", uyari: "uyari", basari: "tik", bilgi: "bilgi" }[tur] || "bilgi";
  const b = el(`<div class="bildirim ${tur}">${ikon(ikonAdi)}<div>${kacir(metin)}</div></div>`);
  $("#bildirimler").append(b);
  setTimeout(() => b.remove(), sureMs);
}

let modalSayac = 0;
const ODAKLANABILIR = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), iframe, [tabindex]:not([tabindex="-1"])';

export function modal({ baslik, icerik, dugmeler = [], genis = false, kapaninca }) {
  const baslikId = `modal-baslik-${++modalSayac}`;
  const onceki = document.activeElement; // kapaninca odak buraya doner
  const arka = el(`<div class="modal-arka"><div class="modal ${genis ? "genis" : ""}" role="dialog" aria-modal="true" aria-labelledby="${baslikId}">
    <header><span id="${baslikId}">${kacir(baslik)}</span><button class="ikon-btn" data-ikon="x" title="Kapat" aria-label="Kapat"></button></header>
    <div class="modal-govde"></div><footer hidden></footer></div></div>`);
  const govde = $(".modal-govde", arka);
  if (typeof icerik === "string") govde.innerHTML = icerik;
  else if (icerik) govde.append(icerik);
  ikonlariYerlestir(govde);
  const ayak = $("footer", arka);
  const kapat = () => {
    arka.remove();
    document.removeEventListener("keydown", tus);
    kapaninca?.();
    if (onceki && document.contains(onceki)) onceki.focus?.();
  };
  for (const d of dugmeler) {
    const b = el(`<button class="btn ${d.tur || ""}">${kacir(d.metin)}</button>`);
    b.onclick = () => d.eylem?.(kapat, b) ?? kapat();
    ayak.append(b);
    ayak.hidden = false;
  }
  const tus = (e) => {
    // ust uste modallarda yalniz en ustteki tusa tepki verir
    if (document.querySelector("#modal-kok > .modal-arka:last-child") !== arka) return;
    if (e.key === "Escape") { kapat(); return; }
    if (e.key !== "Tab") return;
    const odak = [...arka.querySelectorAll(ODAKLANABILIR)].filter((x) => x.offsetParent !== null || x.tagName === "IFRAME");
    if (!odak.length) return;
    const ilk = odak[0];
    const son = odak[odak.length - 1];
    if (e.shiftKey && document.activeElement === ilk) { e.preventDefault(); son.focus(); }
    else if (!e.shiftKey && document.activeElement === son) { e.preventDefault(); ilk.focus(); }
    else if (!arka.contains(document.activeElement)) { e.preventDefault(); ilk.focus(); }
  };
  document.addEventListener("keydown", tus);
  $("header .ikon-btn", arka).onclick = kapat;
  arka.addEventListener("mousedown", (e) => { if (e.target === arka) kapat(); });
  $("#modal-kok").append(arka);
  // odagi pencereye tasi: once govdedeki ilk alan, yoksa ilk dugme, yoksa kapat dugmesi
  setTimeout(() => {
    if (arka.contains(document.activeElement)) return;
    const hedef = govde.querySelector("input, textarea, select") || ayak.querySelector("button") || $("header .ikon-btn", arka);
    hedef?.focus();
  }, 0);
  return { kapat, govde, arka };
}

export function onayla(baslik, metin, { evet = "Evet", tehlike = false } = {}) {
  return new Promise((coz) => {
    let sonuc = false;
    modal({
      baslik,
      icerik: `<p style="margin:0">${kacir(metin)}</p>`,
      dugmeler: [
        { metin: "Vazgeç" },
        { metin: evet, tur: tehlike ? "tehlike" : "ana", eylem: (k) => { sonuc = true; k(); } },
      ],
      kapaninca: () => coz(sonuc),
    });
  });
}

export function sor(baslik, varsayilan = "") {
  return new Promise((coz) => {
    let sonuc = null;
    const girdi = el(`<input class="alan" value="${kacir(varsayilan)}">`);
    const tamam = (k) => { sonuc = girdi.value; k(); };
    const m = modal({
      baslik,
      icerik: girdi,
      dugmeler: [{ metin: "Vazgeç" }, { metin: "Kaydet", tur: "ana", eylem: tamam }],
      kapaninca: () => coz(sonuc),
    });
    girdi.onkeydown = (e) => { if (e.key === "Enter") tamam(m.kapat); };
    setTimeout(() => { girdi.focus(); girdi.select(); }, 10);
  });
}

let acikMenu = null;
let acikCapa = null;
let disTiklama = null; // acik menunun "disariya tiklayinca kapat" dinleyicisi
let disTus = null;
export function menuKapat() {
  acikMenu?.remove();
  acikMenu = null;
  acikCapa = null;
  // Dinleyici menuyle birlikte kaldirilir. Eskiden { once: true } ile kalip, menu ogeden secilerek
  // kapandiginda (stopPropagation) askida kaliyor; sonraki acilis tiklamasi yeni menuyu aninda
  // kapatiyordu ("bir kez aciliyor, sonra acilmiyor").
  if (disTiklama) document.removeEventListener("click", disTiklama);
  if (disTus) document.removeEventListener("keydown", disTus, true);
  disTiklama = null;
  disTus = null;
}

/** ogeler: {metin, ikon, sag, secili, tehlike, eylem} | "ayrac" | {baslik} */
export function menuAc(capa, ogeler, { yukari = false, sagaHizali = false } = {}) {
  if (acikMenu && acikCapa === capa) { menuKapat(); return; } // ayni dugme: ac/kapa
  menuKapat();
  const m = el(`<div class="menu"></div>`);
  for (const o of ogeler) {
    if (o === "ayrac") { m.append(el(`<div class="menu-ayrac"></div>`)); continue; }
    if (o.baslik) { m.append(el(`<div class="menu-baslik">${kacir(o.baslik)}</div>`)); continue; }
    const b = el(`<button class="menu-oge ${o.secili ? "secili" : ""} ${o.tehlike ? "tehlike" : ""}" ${o.pasif ? "disabled" : ""}>
      ${o.ikon ? `<span data-ikon="${o.ikon}"></span>` : ""}${o.aciklama ? `<span class="menu-metin"><span>${kacir(o.metin)}</span><small>${kacir(o.aciklama)}</small></span>` : `<span>${kacir(o.metin)}</span>`}
      ${o.sag ? `<span class="sag">${kacir(o.sag)}</span>` : ""}${o.secili ? `<span class="tik sag" data-ikon="tik"></span>` : ""}</button>`);
    b.onclick = (e) => { e.stopPropagation(); menuKapat(); o.eylem?.(); };
    m.append(b);
  }
  document.body.append(m);
  const r = capa.getBoundingClientRect();
  const mr = m.getBoundingClientRect();
  let sol = sagaHizali ? r.right - mr.width : r.left;
  sol = Math.max(8, Math.min(sol, innerWidth - mr.width - 8));
  const ust = yukari ? r.top - mr.height - 6 : r.bottom + 6;
  m.style.left = `${sol}px`;
  m.style.top = `${Math.max(8, Math.min(ust, innerHeight - mr.height - 8))}px`;
  acikMenu = m;
  acikCapa = capa;
  // acilis tiklamasi bitince kur; o arada menu kapandiysa (ya da yenisi acildiysa) kurma
  setTimeout(() => {
    if (acikMenu !== m) return;
    disTiklama = (e) => { if (!m.contains(e.target)) menuKapat(); };
    disTus = (e) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); menuKapat(); } };
    document.addEventListener("click", disTiklama);
    document.addEventListener("keydown", disTus, true);
  }, 0);
}

export function modelProfil(anahtar) {
  return durum.sunucu?.modeller?.find((m) => m.anahtar === anahtar);
}

export function modelAdi(anahtar) {
  return modelProfil(anahtar)?.ad || anahtar || "";
}

export function sayi(n, basamak = 1) {
  return n == null ? "-" : Number(n).toLocaleString("tr-TR", { maximumFractionDigits: basamak });
}

export function istatistikMetni(i) {
  if (!i) return "";
  const p = [modelAdi(i.model)];
  if (i.dusunme && i.dusunme !== "kapali") p.push(`düşünme: ${i.dusunme}`);
  if (i.sure_sn != null) p.push(`${sayi(i.sure_sn)} sn`);
  if (i.uretim_tok_sn) p.push(`${sayi(i.uretim_tok_sn)} tok/sn`);
  if (i.token) p.push(`${i.token} token`);
  if (i.yukleme_sn) p.push(`yükleme ${sayi(i.yukleme_sn)} sn`);
  return p.join(" · ");
}

function cip(etiket, deger, aciklama) {
  return `<span class="istat-cip" title="${kacir(aciklama)}">${kacir(etiket)} <b>${kacir(deger)}</b></span>`;
}

/** Cevabin sure bilgileri (etiketli cipler). i: sunucu istatistigi; eksik alanlar atlanir. */
export function istatistikCipleri(i) {
  if (!i) return "";
  const c = [];
  if (i.model) c.push(`<span class="istat-model">${kacir(modelAdi(i.model))}</span>`);
  if (i.sure_sn != null) c.push(cip("Toplam", `${sayi(i.sure_sn)} sn`, "İsteği gönderdiğinden cevabın bitmesine kadar geçen süre"));
  if (i.ilk_token_sn != null) c.push(cip("İlk yanıt", `${sayi(i.ilk_token_sn)} sn`, "Cevabın ilk kelimesi gelene kadar bekleme (girdi işleme + düşünme)"));
  if (i.dusunce_sn) c.push(cip("Düşünme", `${sayi(i.dusunce_sn)} sn`, `Düşünme seviyesi: ${i.dusunme || ""}`));
  if (i.yukleme_sn) c.push(cip("Model yükleme", `${sayi(i.yukleme_sn)} sn`, "Model bu istek için yeniden açıldı"));
  if (i.uretim_tok_sn) c.push(cip("Hız", `${sayi(i.uretim_tok_sn)} token/sn`, "Cevap üretme hızı"));
  if (i.token) c.push(cip("Cevap", `${i.token} token`, "Üretilen token sayısı"));
  if (i.prompt_token) c.push(cip("Girdi", `${sayi(i.prompt_token, 0)} token${i.prompt_tok_sn ? ` · ${sayi(i.prompt_tok_sn)}/sn` : ""}`, "Bu istekte işlenen girdi (önbellekteki kısım hariç) ve işleme hızı"));
  if (i.durduruldu) c.push(`<span class="istat-cip">durduruldu</span>`);
  return c.join("");
}

/** hedef ogeye her yarim saniyede "N sn" yazar; durdurma fonksiyonu dondurur. */
export function canliSayac(hedef, onEk = "") {
  const bas = performance.now();
  const yaz = () => { hedef.textContent = `${onEk}${Math.round((performance.now() - bas) / 1000)} sn`; };
  yaz();
  const id = setInterval(yaz, 500);
  return () => { clearInterval(id); return (performance.now() - bas) / 1000; };
}

/** Model secim cipleri (karsilastir, OCR, paket sayfalari). */
export function modelCipleri(kap, { coklu = true, ad = "m" } = {}) {
  const modeller = durum.sunucu?.modeller || [];
  const onceki = new Set($$("input:checked", kap).map((i) => i.value));
  kap.innerHTML = "";
  for (const m of modeller) {
    const secili = onceki.size ? onceki.has(m.anahtar) : m.dosya_var && (coklu || m.anahtar === durum.ayarlar?.model);
    const c = el(`<label class="model-cip ${m.dosya_var ? "" : "yok"}" title="${kacir(m.aciklama)}">
      <input type="${coklu ? "checkbox" : "radio"}" name="${ad}" value="${m.anahtar}" ${secili && m.dosya_var ? "checked" : ""} ${m.dosya_var ? "" : "disabled"}>
      <span>${kacir(m.ad)}</span><span class="soluk">${m.dosya_var ? `~${m.ram_gb} GB` : "indirilmedi"}</span></label>`);
    kap.append(c);
  }
}

export function seciliModeller(kap) {
  return $$("input:checked", kap).map((i) => i.value);
}

// Bagliyici (MCP) durumu: Eklentiler, sag panel ve Ayarlar ayni etiketi gosterir.
// s.baglanti sunucudan gelir (bagli/baglaniyor/hata/kapali); OAuth girisi eksikse once o soylenir.
export function baglayiciDurumu(s) {
  const b = s.baglanti || {};
  if (s.aktif === false || b.durum === "kapali") return { kod: "kapali", etiket: "Kapalı", sinif: "", ipucu: "Kapalı: ajan bu bağlayıcıyı kullanmaz." };
  const yetki = b.durum === "hata" && /401|403|kimlik|yetki|giri[sş]|unauthor/i.test(b.hata || "");
  if ((s.oauth && s.oauth.bagli === false) || yetki) return { kod: "giris", etiket: "Giriş gerekli", sinif: "sari", ipucu: b.hata || "Hesabınla giriş yapılmadı." };
  if (b.durum === "bagli") return { kod: "bagli", etiket: b.arac ? `Bağlı · ${b.arac} araç` : "Bağlı", sinif: "yesil", ipucu: "Bağlantı çalışıyor; ajan araçlarını kullanabilir." };
  if (b.durum === "hata") return { kod: "hata", etiket: "Bağlanamadı", sinif: "kirmizi", ipucu: b.hata || "Bağlantı kurulamadı." };
  return { kod: "baglaniyor", etiket: "Bağlanıyor…", sinif: "mavi", ipucu: "Sunucu başlatılıyor; birkaç saniye içinde durumu güncellenir." };
}

// Eklentiler ve Ayarlar listelerinde ayni logo/harf rozeti
const AVATAR_RENK = ["#d97757", "#2bb6a8", "#6a8fd8", "#c7a14a", "#a36ad8", "#d86a8f", "#5aa86a"];
export function ekAvatar(ad, logo) {
  if (logo) return `<img class="ek-logo" src="${kacir(logo)}" alt="" loading="lazy" referrerpolicy="no-referrer">`;
  const r = AVATAR_RENK[[...(ad || "?")].reduce((t, c) => t + c.charCodeAt(0), 0) % AVATAR_RENK.length];
  return `<span class="ek-logo harf" style="background:${r}">${kacir(((ad || "?")[0] || "?").toUpperCase())}</span>`;
}
