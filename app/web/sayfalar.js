// Test sayfalari: Karsilastir, OCR testi, Arac testi, Test paketi.
import { ikon, ikonlariYerlestir } from "./ikonlar.js";
import { kacir, md } from "./md.js";
import {
  $, api, bildir, durum, el, istatistikMetni, modelAdi, modelCipleri, sayi, seciliModeller, sseOku,
} from "./ortak.js";

let isKontrol = null; // ayni anda tek test

function isBaslat(dugme) {
  if (isKontrol) { isKontrol.abort(); return null; }
  isKontrol = new AbortController();
  const eski = dugme.innerHTML;
  dugme.innerHTML = `${ikon("durdur")}Durdur`;
  return () => { isKontrol = null; dugme.innerHTML = eski; };
}

export function sayfaModelleriniYenile() {
  modelCipleri($("#k-modeller"));
  modelCipleri($("#o-modeller"));
  modelCipleri($("#p-modeller"));
}

function rozet(tur, metin) {
  return `<span class="rozet ${tur}">${kacir(metin)}</span>`;
}

function hataMesaji(e) {
  return e.name === "AbortError" ? "Durduruldu." : e.message;
}

// ---------------- KARSILASTIR ----------------
function karsilastirKur() {
  const sec = $("#k-dusunme");
  for (const s of durum.bilgi.dusunme_secenekleri) sec.append(new Option(`Düşünme: ${s.ad}`, s.deger));
  $("#k-baslat").onclick = karsilastir;
}

async function karsilastir() {
  const modeller = seciliModeller($("#k-modeller"));
  const istem = $("#k-istem").value.trim();
  if (!istem || !modeller.length) { bildir("Soru yaz ve en az bir model sec.", "hata"); return; }
  const bitir = isBaslat($("#k-baslat"));
  if (!bitir) return;
  const kap = $("#k-sonuclar");
  kap.innerHTML = "";
  const kartlar = {};
  for (const m of modeller) {
    const k = el(`<div class="sonuc-kart"><header><span>${kacir(modelAdi(m))}</span>${rozet("", "sırada")}</header>
      <div class="icerik"><div class="dusunce" hidden><button class="dusunce-baslik"><span data-ikon="beyin"></span><span class="dusunce-etiket">Düşünce</span><span class="ok" data-ikon="sag"></span></button><div class="dusunce-icerik"></div></div><div class="md"></div></div><footer></footer></div>`);
    k.querySelector(".dusunce-baslik").onclick = () => k.querySelector(".dusunce").classList.toggle("acik");
    kartlar[m] = { el: k, metin: "", dusunce: "" };
    kap.append(k);
  }
  const rozetAyarla = (m, tur, metin) => { kartlar[m].el.querySelector("header .rozet").outerHTML = rozet(tur, metin); };
  try {
    for await (const o of sseOku("/api/karsilastir", { istem, modeller, dusunme: $("#k-dusunme").value }, isKontrol.signal)) {
      const k = kartlar[o.model];
      if (o.tur === "model_basladi") {
        rozetAyarla(o.model, "sari", "yükleniyor");
        if (o.uyari) k.el.querySelector(".icerik").prepend(el(`<div class="uyari-kutu">${kacir(o.uyari)}</div>`));
      } else if (o.tur === "durum") {
        rozetAyarla(o.model, "sari", o.metin.replace("...", "").toLowerCase());
      } else if (o.tur === "dusunce") {
        k.dusunce += o.metin;
        const d = k.el.querySelector(".dusunce");
        d.hidden = false;
        d.classList.add("acik");
        d.querySelector(".dusunce-icerik").textContent = k.dusunce;
      } else if (o.tur === "parca") {
        k.el.querySelector(".dusunce").classList.remove("acik");
        k.metin += o.metin;
        k.el.querySelector(".md").innerHTML = md(k.metin);
      } else if (o.tur === "model_bitti") {
        rozetAyarla(o.model, "yesil", "bitti");
        const i = o.istatistik || {};
        k.el.querySelector("footer").innerHTML = [
          o.yukleme_sn ? `yükleme ${sayi(o.yukleme_sn)} sn` : "zaten açıktı",
          `yanıt ${sayi(i.sure_sn)} sn`,
          i.ilk_token_sn != null ? `ilk token ${sayi(i.ilk_token_sn)} sn` : "",
          i.uretim_tok_sn ? `${sayi(i.uretim_tok_sn)} tok/sn` : "",
          i.token ? `${i.token} token` : "",
        ].filter(Boolean).map((x) => `<span>${x}</span>`).join("");
      } else if (o.tur === "model_hata") {
        rozetAyarla(o.model, "kirmizi", "hata");
        k.el.querySelector(".icerik").append(el(`<div class="hata-kutu">${kacir(o.mesaj)}</div>`));
      } else if (o.tur === "hata") {
        bildir(o.mesaj, "hata");
      }
    }
  } catch (e) {
    bildir(hataMesaji(e), e.name === "AbortError" ? "bilgi" : "hata");
  } finally {
    ikonlariYerlestir(kap);
    bitir();
  }
}

// ---------------- OCR ----------------
let ocrEk = null;

function ocrKur() {
  const birak = $("#o-birak");
  birak.onclick = () => $("#o-dosya").click();
  $("#o-dosya").onchange = (e) => { if (e.target.files[0]) ocrDosya(e.target.files[0]); e.target.value = ""; };
  birak.addEventListener("dragover", (e) => { e.preventDefault(); birak.classList.add("surukle"); });
  birak.addEventListener("dragleave", () => birak.classList.remove("surukle"));
  birak.addEventListener("drop", (e) => {
    e.preventDefault();
    birak.classList.remove("surukle");
    if (e.dataTransfer.files[0]) ocrDosya(e.dataTransfer.files[0]);
  });
  $("#o-ornek").onclick = async () => {
    try {
      const ek = await api("/api/ekler/ornek-belge", { method: "POST" });
      ocrEkAyarla(ek);
      $("#o-beklenen").value = ek.beklenen;
    } catch (e) { bildir(e.message, "hata"); }
  };
  $("#o-baslat").onclick = ocrCalistir;
}

async function ocrDosya(dosya) {
  const form = new FormData();
  form.append("dosya", dosya);
  try {
    ocrEkAyarla(await api("/api/ekler", { method: "POST", form }));
  } catch (e) { bildir(e.message, "hata"); }
}

function ocrEkAyarla(ek) {
  if (!["resim", "pdf"].includes(ek.tur)) { bildir("OCR icin resim ya da PDF sec.", "hata"); return; }
  ocrEk = ek;
  const on = $("#o-onizleme");
  on.innerHTML = ek.tur === "resim"
    ? `<img src="/api/ekler/${ek.id}" alt=""><span class="kucuk">${kacir(ek.ad)}</span>`
    : `<span class="buyuk-ikon" data-ikon="dosya"></span><span>${kacir(ek.ad)}</span><span class="kucuk soluk">PDF · ${sayi(ek.boyut / 1024, 0)} KB</span>`;
  ikonlariYerlestir(on);
  $("#o-baslat").disabled = false;
}

async function ocrCalistir() {
  const modeller = seciliModeller($("#o-modeller"));
  if (!ocrEk || !modeller.length) { bildir("Belge ve en az bir model sec.", "hata"); return; }
  const bitir = isBaslat($("#o-baslat"));
  if (!bitir) return;
  const kap = $("#o-sonuclar");
  kap.innerHTML = "";
  const kartlar = {};
  for (const m of modeller) {
    const k = el(`<div class="sonuc-kart"><header><span>${kacir(modelAdi(m))}</span>${rozet("", "sırada")}</header>
      <div class="icerik"><div class="olcum-satiri"></div></div></div>`);
    kartlar[m] = k;
    kap.append(k);
  }
  const rozetAyarla = (m, tur, metin) => { kartlar[m].querySelector("header .rozet").outerHTML = rozet(tur, metin); };
  const istek = {
    ek_id: ocrEk.id,
    modeller,
    beklenen: $("#o-beklenen").value,
    talimat: $("#o-talimat").value,
    json_cikar: $("#o-json").checked,
    metin_katmani: $("#o-katman").checked,
  };
  try {
    for await (const o of sseOku("/api/ocr", istek, isKontrol.signal)) {
      const k = kartlar[o.model];
      if (o.tur === "model_basladi") {
        rozetAyarla(o.model, "sari", "yükleniyor");
        if (o.uyari) k.querySelector(".icerik").prepend(el(`<div class="uyari-kutu">${kacir(o.uyari)}</div>`));
      } else if (o.tur === "durum" || o.tur === "ilerleme") {
        rozetAyarla(o.model, "sari", o.metin.replace("...", "").toLowerCase());
      } else if (o.tur === "model_bitti") {
        rozetAyarla(o.model, "yesil", "bitti");
        const olc = [
          `<span class="rozet">${sayi(o.sure_sn)} sn</span>`,
          o.yukleme_sn ? `<span class="rozet">yükleme ${sayi(o.yukleme_sn)} sn</span>` : "",
          o.benzerlik != null ? rozet(o.benzerlik >= 95 ? "yesil" : o.benzerlik >= 80 ? "sari" : "kirmizi", `doğruluk %${sayi(o.benzerlik)}`) : "",
          `<span class="rozet">Türkçe harf: ${o.turkce_harf}</span>`,
          o.uretim_tok_sn ? `<span class="rozet">${sayi(o.uretim_tok_sn)} tok/sn</span>` : "",
        ].join("");
        const ic = k.querySelector(".icerik");
        ic.querySelector(".olcum-satiri").innerHTML = olc;
        ic.append(el(`<pre class="duz">${kacir(o.metin || "(boş)")}</pre>`));
        if (o.json) {
          const satirlar = (o.json.alanlar || []).map((a) => `<tr><td>${kacir(a.ad)}</td><td>${kacir(a.deger)}</td></tr>`).join("");
          ic.append(el(`<table class="tablo"><thead><tr><th>Alan</th><th>Değer</th></tr></thead><tbody>${satirlar}</tbody></table>`));
        }
      } else if (o.tur === "model_hata") {
        rozetAyarla(o.model, "kirmizi", "hata");
        k.querySelector(".icerik").append(el(`<div class="hata-kutu">${kacir(o.mesaj)}</div>`));
      } else if (o.tur === "hata") {
        bildir(o.mesaj, "hata");
      }
    }
  } catch (e) {
    bildir(hataMesaji(e), e.name === "AbortError" ? "bilgi" : "hata");
  } finally {
    bitir();
  }
}

// ---------------- ARAC ----------------
async function aracKur() {
  $("#a-baslat").onclick = aracCalistir;
  $("#a-istem").onkeydown = (e) => { if (e.key === "Enter") aracCalistir(); };
  try {
    const v = await api("/api/araclar");
    $("#a-araclar").innerHTML = v.araclar.map((a) => `<span class="arac-cip" title="${kacir(a.function.description)}" data-ikon="anahtar">${kacir(a.function.name)}</span>`).join("");
    $("#a-ornekler").innerHTML = "";
    for (const ornek of v.ornekler) {
      const b = el(`<button class="ornek">${kacir(ornek)}</button>`);
      b.onclick = () => { $("#a-istem").value = ornek; };
      $("#a-ornekler").append(b);
    }
    ikonlariYerlestir($("#a-araclar"));
  } catch (e) { bildir(e.message, "hata"); }
}

async function aracCalistir() {
  const istem = $("#a-istem").value.trim();
  if (!istem) { bildir("Bir istek yaz.", "hata"); return; }
  const bitir = isBaslat($("#a-baslat"));
  if (!bitir) return;
  const akis = $("#a-akis");
  akis.innerHTML = "";
  const adim = (sinif, ust, govde) => {
    const a = el(`<div class="adim ${sinif}"><div class="ust">${ust}</div>${govde}</div>`);
    akis.append(a);
    return a;
  };
  let durumAdim = null;
  try {
    for await (const o of sseOku("/api/arac-testi", { istem }, isKontrol.signal)) {
      if (o.tur === "model_basladi") {
        adim("", `Model: <b>${kacir(modelAdi(o.model))}</b>`, o.uyari ? `<div class="uyari-kutu">${kacir(o.uyari)}</div>` : "");
      } else if (o.tur === "durum") {
        if (!durumAdim) durumAdim = adim("", "", `<span class="parilti"></span>`);
        durumAdim.querySelector(".parilti").textContent = o.metin;
      } else if (o.tur === "arac_cagrisi") {
        durumAdim?.remove();
        durumAdim = null;
        const arg = typeof o.argumanlar === "string" ? o.argumanlar : JSON.stringify(o.argumanlar);
        adim("cagri", "Araç çağrısı", `<code class="cagri">${kacir(o.ad)}(${kacir(arg)})</code>`);
      } else if (o.tur === "arac_sonucu") {
        adim("sonuc", `Sonuç · ${o.sure_ms} ms`, `<pre class="duz">${kacir(JSON.stringify(o.sonuc, null, 1))}</pre>`);
      } else if (o.tur === "model_bitti") {
        durumAdim?.remove();
        durumAdim = null;
        adim("son", `Cevap · ${o.tur_sayisi} tur · ${o.cagri_sayisi} araç çağrısı · ${sayi(o.sure_sn)} sn${o.yukleme_sn ? ` · yükleme ${sayi(o.yukleme_sn)} sn` : ""}`, `<div class="md">${md(o.cevap)}</div>`);
      } else if (o.tur === "model_hata" || o.tur === "hata") {
        durumAdim?.remove();
        durumAdim = null;
        adim("hata", "Hata", `<div class="hata-kutu">${kacir(o.mesaj)}</div>`);
      }
    }
  } catch (e) {
    adim("hata", "Hata", `<div class="hata-kutu">${kacir(hataMesaji(e))}</div>`);
  } finally {
    durumAdim?.remove();
    bitir();
  }
}

// ---------------- TEST PAKETI ----------------
const TESTLER = [
  ["mantik", "Mantık (dengeli düşünme)"],
  ["arac", "Araç çağırma"],
  ["json", "JSON çıktı"],
  ["ocr", "Türkçe OCR"],
  ["sansursuz", "Sansürsüz (reddetmedi)"],
];

function paketKur() {
  $("#p-baslat").onclick = paketCalistir;
}

function tabloCiz(modeller, sonuclar) {
  const bas = `<tr><th>Test</th>${modeller.map((m) => `<th>${kacir(modelAdi(m))}</th>`).join("")}</tr>`;
  const satirlar = TESTLER.map(([k, ad]) => `<tr><td>${ad}</td>${modeller.map((m) => {
    const s = sonuclar[m]?.[k];
    if (!s) return `<td class="soluk">${sonuclar[m]?._hata ? "-" : "…"}</td>`;
    const ek = s.hata ? s.hata : s.benzerlik != null ? `%${sayi(s.benzerlik)}` : "";
    return `<td class="${s.basarili ? "ok" : "yok"}">${s.basarili ? "✓" : "✗"} ${sayi(s.sure_sn)} sn<span class="soluk">${kacir(ek)}</span></td>`;
  }).join("")}</tr>`).join("");
  const puan = `<tr><th>Puan</th>${modeller.map((m) => {
    const r = sonuclar[m];
    if (r?._hata) return `<td class="yok">hata<span class="soluk">${kacir(r._hata)}</span></td>`;
    return `<td>${r?._puan != null ? `<b>${r._puan}/${TESTLER.length}</b>${r._yukleme ? `<span class="soluk">yükleme ${sayi(r._yukleme)} sn</span>` : ""}` : "…"}</td>`;
  }).join("")}</tr>`;
  $("#p-tablo").innerHTML = `<table class="tablo"><thead>${bas}</thead><tbody>${satirlar}${puan}</tbody></table>`;
}

async function paketCalistir() {
  const modeller = seciliModeller($("#p-modeller"));
  if (!modeller.length) { bildir("En az bir model sec.", "hata"); return; }
  const bitir = isBaslat($("#p-baslat"));
  if (!bitir) return;
  const sonuclar = {};
  const gunluk = $("#p-gunluk");
  gunluk.textContent = "";
  const yaz = (s) => { gunluk.textContent += `${new Date().toLocaleTimeString("tr-TR")}  ${s}\n`; gunluk.scrollTop = gunluk.scrollHeight; };
  tabloCiz(modeller, sonuclar);
  try {
    for await (const o of sseOku("/api/test-paketi", { modeller }, isKontrol.signal)) {
      if (o.tur === "model_basladi") { sonuclar[o.model] = {}; yaz(`${o.model}: başladı${o.uyari ? ` (UYARI: ${o.uyari})` : ""}`); }
      else if (o.tur === "durum") yaz(`${o.model}: ${o.metin}`);
      else if (o.tur === "test_sonucu") { sonuclar[o.model][o.test] = o; yaz(`${o.model}: ${o.test} -> ${o.basarili ? "BAŞARILI" : "BAŞARISIZ"} (${sayi(o.sure_sn)} sn)`); }
      else if (o.tur === "model_bitti") { Object.assign(sonuclar[o.model], { _puan: o.puan, _yukleme: o.yukleme_sn }); yaz(`${o.model}: puan ${o.puan}/${o.toplam}`); }
      else if (o.tur === "model_hata") { sonuclar[o.model] = { ...(sonuclar[o.model] || {}), _hata: o.mesaj }; yaz(`${o.model}: HATA ${o.mesaj}`); }
      else if (o.tur === "hata") bildir(o.mesaj, "hata");
      tabloCiz(modeller, sonuclar);
    }
  } catch (e) {
    yaz(hataMesaji(e));
  } finally {
    bitir();
  }
}

export function sayfalarKur() {
  karsilastirKur();
  ocrKur();
  aracKur();
  paketKur();
  sayfaModelleriniYenile();
}

export { istatistikMetni };
