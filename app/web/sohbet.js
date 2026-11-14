// Sohbet gorunumu: mesajlar, dusunce blogu, yazma alani, ekler, akis ve durdurma.
import { sohbetteGorevGoster } from "./gorevler.js";
import { threadKarti } from "./superajan.js";
import { masaustuBildirimi } from "./ayarlar2.js";
import { girdiYardimKur, oneriTusu } from "./girdi.js";
import { komutListesi, komutMu } from "./komutlar.js";
import { projeDurumu } from "./proje.js";
import { ikon, ikonlariYerlestir } from "./ikonlar.js";
import { kacir, md } from "./md.js";
import {
  $, api, bildir, canliSayac, durum, el, istatistikCipleri, modal, modelAdi, modelProfil, onayla, sayi, sseOku,
} from "./ortak.js";

const bekleyenEkler = []; // {id?, ad, tur, onizleme, yukleniyor}
let akisKontrol = null; // AbortController
let geriCagri = { oturumlarYenile: async () => {}, baslikAyarla: () => {}, oturumAc: async () => {} };
let oneriKararlari = {}; // acik oturumun alt oturum onerisi kararlari: kaynak -> alt id | "reddedildi"

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
    if (karar) {
      sira.innerHTML = '<span class="rozet yesil">Açıldı</span><button class="btn kucuk">Alt oturuma git</button>';
      sira.querySelector("button").onclick = () => geriCagri.oturumAc(karar, true);
      return;
    }
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
  const girdi = $("#girdi");
  girdi.addEventListener("input", () => { boyutla(); gonderDurumu(); });
  girdi.addEventListener("keydown", (e) => {
    if (oneriTusu(e)) return; // "/" ve "@" onerileri acikken ok/Enter/Tab onlara gider
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); gonder(); }
  });
  girdiYardimKur(komutListesi);
  girdi.addEventListener("paste", (e) => {
    const dosyalar = [...(e.clipboardData?.files || [])];
    if (dosyalar.length) { e.preventDefault(); dosyalar.forEach(ekYukle); }
  });
  $("#btn-gonder").onclick = () => (akisKontrol ? durdur() : gonder());
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
}

function boyutla() {
  const g = $("#girdi");
  g.style.height = "auto";
  g.style.height = `${Math.min(g.scrollHeight, 260)}px`;
  g.style.overflowY = g.scrollHeight > 260 ? "auto" : "hidden";
}

function gonderDurumu() {
  const b = $("#btn-gonder");
  if (akisKontrol) {
    b.disabled = false;
    b.classList.add("durdur");
    b.innerHTML = ikon("durdur");
    b.title = "Durdur";
    return;
  }
  b.classList.remove("durdur");
  b.innerHTML = ikon("yukari");
  b.title = "Gonder (Enter)";
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
    c.querySelector("button").onclick = () => { bekleyenEkler.splice(i, 1); ekleriCiz(); };
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
    bekleyenEkler.splice(bekleyenEkler.indexOf(kayit), 1);
    bildir(e.message, "hata");
  }
  ekleriCiz();
}

// ---- mesaj cizimi ----
function sonaKaydir(zorla = false) {
  const m = $("#mesajlar");
  if (zorla || m.scrollHeight - m.scrollTop - m.clientHeight < 160) m.scrollTop = m.scrollHeight;
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

function kullaniciMesaji(m) {
  const ekler = (m.ekler || []).map((e) => e.tur === "resim"
    ? `<img src="/api/ekler/${e.id}" alt="${kacir(e.ad)}" data-buyut="${e.id}">`
    : `<span class="ek-cip"><span class="tur">${ikon(TUR_IKON[e.tur] || "dosya")}</span><span class="ad">${kacir(e.ad)}</span></span>`).join("");
  const d = el(`<div class="mesaj kullanici">
    ${ekler ? `<div class="mesaj-ekleri">${ekler}</div>` : ""}
    ${m.metin ? `<div class="balon">${kacir(m.metin)}</div>` : ""}
    <div class="mesaj-alt"><button class="ikon-btn" title="Kopyala" data-ikon="kopyala"></button></div></div>`);
  d.querySelector(".mesaj-alt .ikon-btn").onclick = () => kopyala(m.metin);
  d.querySelectorAll("[data-buyut]").forEach((img) => {
    img.onclick = () => modal({ baslik: img.alt, icerik: `<img class="resim-buyuk" src="${img.src}">`, genis: true });
  });
  return d;
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
    <div class="mesaj-alt" hidden><button class="ikon-btn" title="Kopyala" data-ikon="kopyala"></button><span class="istat istat-cipleri"></span></div>
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
      d.querySelector(".arac-adimlari").append(a);
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
      const ozet = a.querySelector(".ozet");
      const hataVar = o.durum === "hata" || (o.ozet || "").startsWith("hata");
      const sonucsuz = o.durum === "sonucsuz";
      ozet.classList.remove("parilti");
      ozet.classList.toggle("hata", hataVar);
      ozet.classList.toggle("sonucsuz", sonucsuz);
      const isaret = hataVar ? "✗" : sonucsuz ? "⦸" : "✓"; // basari ikonu yalniz gercek sonucta
      ozet.textContent = `${isaret} ${o.ozet}${o.truncated ? " · kısaltıldı" : ""}`;
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
    bitir(ist) {
      this.mod(null);
      const gecen = this.gecen();
      this.sayacDurdur = null;
      this.durum("");
      this.dusunceBitir(ist?.dusunce_sn);
      if (!ist && gecen != null) ist = { model: this.model, sure_sn: Math.round(gecen * 10) / 10, durduruldu: true };
      const alt = d.querySelector(".mesaj-alt");
      alt.hidden = false;
      alt.querySelector(".istat").innerHTML = istatistikCipleri(ist);
      alt.querySelector(".ikon-btn").onclick = () => kopyala(this.metin);
    },
  };
  return o;
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
  o.bitir({ ...m.istatistik, model: m.istatistik?.model || m.model });
  return o.el;
}

export function bosDurum(goster) {
  $("#bos-durum").hidden = !goster;
}

const PENCERE = 40;

export function mesajlariCiz(oturum) {
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
  mesajlariCiz(null);
  if (!girdiyiKoru) $("#girdi").value = ""; // acilista kullanicinin o ana dek yazdigi silinmesin
  boyutla();
  gonderDurumu();
  setTimeout(() => $("#girdi").focus(), 0);
}

// ---- gonderme / akis ----
export async function gonder() {
  const girdi = $("#girdi");
  const metin = girdi.value.trim();
  if (komutMu(metin, (istem) => { $("#girdi").value = istem; gonder(); })) { // yerel slash komut: modele mesaj olarak gitmez
    girdi.value = "";
    boyutla();
    return;
  }
  if (akisKontrol || (!metin && !bekleyenEkler.length) || bekleyenEkler.some((e) => e.yukleniyor)) return;
  // Claude Code kisayollari (tek satir, eksiz): "!komut" kabukta calisir, "#not" hafizaya yazilir
  if (!bekleyenEkler.length && !metin.includes("\n")) {
    if (/^!\s*\S/.test(metin)) { girdi.value = ""; boyutla(); gonderDurumu(); kabukCalistir(metin.slice(1).trim()); return; }
    if (/^#\s*[^#\s]/.test(metin)) { girdi.value = ""; boyutla(); gonderDurumu(); hafizaNotu(metin.slice(1).trim()); return; }
  }
  const ekler = bekleyenEkler.splice(0);
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
  const oturumId = durum.oturumId;
  // Claude Code gibi: proje aciksa (ve mod sohbet degilse) mesaj AJAN olarak calisir; adimlar,
  // onaylar ve diff bu sohbetin icinde gorunur. Ekli mesajlar normal sohbet yolundan gider.
  if (ajanModu() && !ekler.length) { await ajanaGonder(oturumId, metin); return; }
  const s = sutun();
  const yanit = asistanMesaji();
  yanit.canliBaslat(durum.ayarlar?.model);
  let kullaniciCizildi = false;
  akisKontrol = new AbortController();
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
          yanit.bitir(o.mesaj.istatistik);
          if (durum.ayarlar?.bildirim_yanit) masaustuBildirimi("Kairo yanıtladı", (o.mesaj.metin || "").slice(0, 140));
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
    gonderDurumu();
    geriCagri.oturumlarYenile();
  }
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

export function akisVar() {
  return !!akisKontrol;
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
const BITMIS_RUN = new Set(["iptal", "basarili", "dogrulanmadi", "basarisiz"]);

async function ajanaGonder(oturumId, metin) {
  const s = sutun();
  s.append(kullaniciMesaji({ rol: "kullanici", metin, ekler: [] }));
  bosDurum(false);
  const kayitlar = ajanKayitlari()[oturumId] || [];
  const son = kayitlar[kayitlar.length - 1];
  try {
    if (son) { // calisan gorev varsa yeni mesaj YONLENDIRME olur (Claude Code'da calisirken yazmak gibi)
      const r = await api(`/api/gorevler/${son.run}`);
      if (!BITMIS_RUN.has(r.durum)) {
        await api(`/api/gorevler/${son.run}/mesaj`, { method: "POST", govde: { metin } });
        bildir("Ajana iletildi; sonraki adımdan önce işlenir.", "basari", 1500);
        sonaKaydir(true);
        return;
      }
    }
    const izole = document.getElementById("hap-izole")?.getAttribute("aria-pressed") === "true";
    // onceki: ayni sohbetin son gorevi -> ajan onceki turlarin ozetini gorur (konusma surekliligi)
    const r = await api("/api/gorevler", { method: "POST", govde: { hedef: metin, izole, onceki: son?.run || "", etkilesimli: true } });
    ajanKaydet(oturumId, { run: r.id, metin });
    if (!kayitlar.length) await api(`/api/oturumlar/${oturumId}`, { method: "PATCH", govde: { baslik: metin.slice(0, 60) } }).catch(() => {});
    document.dispatchEvent(new Event("oturumlar-degisti")); // baslik kaydedildikten SONRA
    const b = ajanBlogu({ run: r.id, metin });
    s.append(b.kap);
    sohbetteGorevGoster(b.detay, r.id);
    sonaKaydir(true);
  } catch (e) {
    s.append(el(`<div class="mesaj asistan"><div class="uyari-kutu">${kacir(e.message)}</div></div>`));
  }
}

/** Oturum acilinca bu sohbete bagli ajan gorevlerini akisa ekler; sonuncusu canli izlenir. */
export function ajanBloklariniCiz(oturumId) {
  const kayitlar = ajanKayitlari()[oturumId] || [];
  if (!kayitlar.length) return;
  const s = $("#mesajlar .mesaj-sutun") || sutun();
  bosDurum(false);
  kayitlar.forEach((k, i) => {
    s.append(kullaniciMesaji({ rol: "kullanici", metin: k.metin, ekler: [] }));
    const b = ajanBlogu(k);
    s.append(b.kap);
    if (i === kayitlar.length - 1) sohbetteGorevGoster(b.detay, k.run);
    else api(`/api/gorevler/${k.run}`).then((r) => { b.detay.innerHTML = `<div class="soluk kucuk">Görev: ${kacir(r.durum)} · ${kacir(r.sonuc?.ozet || r.hata || "")}</div>`; }).catch(() => {});
  });
  ikonlariYerlestir(s);
  sonaKaydir(true);
}

export const ajanliOturum = (id) => Boolean(ajanKayitlari()[id]?.length);
/** Bu sohbete bagli ajan gorevleri ({run, metin}); /cost, /todos, /export icin. */
export const sohbetRunlari = (id) => ajanKayitlari()[id] || [];
