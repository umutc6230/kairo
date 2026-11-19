// Yerel ses dikte (A5.7): mikrofon -> 16 kHz mono WAV -> /api/dikte (yerel Gemma 4) -> yazi alanı.
// Bulut konuşma tanıma (Web Speech API) KULLANILMAZ. Model sesi anlamıyorsa düğme devre dışı kalır
// ve nedenini söyler: sahte destek gösterilmez.
import { $, api, bildir } from "./ortak.js";

const ORNEK_HIZI = 16000;
let kayit = null; // { akis, baglam, islemci, parcalar, bas, sayac, zamanAsimi, maxSn }

function wavKodla(parcalar, hiz) {
  const uzunluk = parcalar.reduce((t, p) => t + p.length, 0);
  const tampon = new ArrayBuffer(44 + uzunluk * 2);
  const v = new DataView(tampon);
  const yaz = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  yaz(0, "RIFF"); v.setUint32(4, 36 + uzunluk * 2, true); yaz(8, "WAVE");
  yaz(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, hiz, true); v.setUint32(28, hiz * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  yaz(36, "data"); v.setUint32(40, uzunluk * 2, true);
  let o = 44;
  for (const p of parcalar) for (let i = 0; i < p.length; i++, o += 2) {
    const x = Math.max(-1, Math.min(1, p[i]));
    v.setInt16(o, x < 0 ? x * 0x8000 : x * 0x7fff, true);
  }
  return new Blob([tampon], { type: "audio/wav" });
}

function gosterge(metin) {
  const g = $("#dikte-durum");
  g.hidden = !metin;
  g.textContent = metin || "";
}

function dugmeDurumu(kayitta) {
  const b = $("#btn-dikte");
  b.classList.toggle("kayitta", kayitta);
  b.setAttribute("aria-pressed", String(kayitta));
  b.setAttribute("aria-label", kayitta ? "Kaydı bitir ve yazıya dök" : "Sesle yaz");
}

function temizle() {
  if (!kayit) return;
  clearInterval(kayit.sayac);
  clearTimeout(kayit.zamanAsimi);
  kayit.islemci.disconnect();
  kayit.akis.getTracks().forEach((t) => t.stop()); // mikrofon göstergesi tarayıcıda da kapanır
  kayit.baglam.close();
  document.removeEventListener("keydown", escIptal);
  kayit = null;
  dugmeDurumu(false);
}

function escIptal(e) {
  if (e.key === "Escape" && kayit) { e.stopPropagation(); temizle(); gosterge(""); bildir("Kayıt iptal edildi.", "bilgi", 1500); }
}

async function baslat() {
  let d;
  try { d = await api("/api/dikte/durum"); } catch (e) { bildir(e.message, "hata"); return; }
  if (!d.kullanilabilir) { durumuUygula(d); bildir(d.neden, "uyari"); return; }
  let akis;
  try {
    akis = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
  } catch {
    bildir("Mikrofon izni verilmedi ya da mikrofon bulunamadı.", "hata");
    return;
  }
  const baglam = new AudioContext({ sampleRate: ORNEK_HIZI });
  const kaynak = baglam.createMediaStreamSource(akis);
  const islemci = baglam.createScriptProcessor(4096, 1, 1);
  const parcalar = [];
  islemci.onaudioprocess = (e) => parcalar.push(new Float32Array(e.inputBuffer.getChannelData(0)));
  kaynak.connect(islemci);
  islemci.connect(baglam.destination);
  kayit = { akis, baglam, islemci, parcalar, bas: performance.now(), maxSn: d.max_sn || 30 };
  dugmeDurumu(true);
  const guncelle = () => {
    const sn = Math.floor((performance.now() - kayit.bas) / 1000);
    gosterge(`● Kaydediliyor ${sn} / ${kayit.maxSn} sn. Bitirmek için mikrofona tıklayın, iptal için Esc.`);
  };
  guncelle();
  kayit.sayac = setInterval(guncelle, 500);
  kayit.zamanAsimi = setTimeout(bitir, kayit.maxSn * 1000);
  document.addEventListener("keydown", escIptal, true);
}

async function bitir() {
  if (!kayit) return;
  const { parcalar, baglam } = kayit;
  const hiz = baglam.sampleRate;
  temizle();
  if (!parcalar.length) { gosterge(""); return; }
  gosterge("Yazıya dökülüyor… (yerel model)");
  const form = new FormData();
  form.append("ses", wavKodla(parcalar, hiz), "dikte.wav");
  try {
    const r = await api("/api/dikte", { method: "POST", form });
    const g = $("#girdi");
    const bas = g.selectionStart ?? g.value.length;
    const ek = (bas && !/\s$/.test(g.value.slice(0, bas)) ? " " : "") + r.metin;
    g.value = g.value.slice(0, bas) + ek + g.value.slice(g.selectionEnd ?? bas);
    g.dispatchEvent(new Event("input", { bubbles: true }));
    g.focus();
  } catch (e) {
    bildir(e.message, "hata");
  } finally {
    gosterge("");
  }
}

function durumuUygula(d) {
  const b = $("#btn-dikte");
  b.setAttribute("aria-disabled", String(!d.kullanilabilir));
  b.title = d.kullanilabilir ? `Sesle yaz (${d.bulut ? "bulutta: " + d.model : "yerel"}, en fazla 30 sn)` : `Sesle yazma kullanılamıyor: ${d.neden}`;
}

export async function dikteDurumuYenile() {
  try { durumuUygula(await api("/api/dikte/durum")); } catch { /* sunucu yoksa sessiz */ }
}

export function dikteKur() {
  const b = $("#btn-dikte");
  if (!navigator.mediaDevices?.getUserMedia || !window.AudioContext) {
    b.hidden = true; // tarayıcı mikrofon desteklemiyor: düğme gösterilmez
    return;
  }
  b.onclick = () => (kayit ? bitir() : baslat());
  dikteDurumuYenile();
}

export { wavKodla };
