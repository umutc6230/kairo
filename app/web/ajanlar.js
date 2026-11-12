// Kalici ajanlar (openbot "AI teammates" tasarimindan): her ajanin adi, avatari, talimati,
// klasoru, modeli, hafizasi ve FIFO kuyrugu vardir. Ajanlar birbirine is verebilir.
// Arka uc: /api/ajanlar. Calisan isin adimlari gorevler.js ile canli gosterilir.
import { sohbetteGorevGoster } from "./gorevler.js";
import { kacir, md } from "./md.js";
import { $, $$, api, bildir, onayla } from "./ortak.js";

let secili = null;
let yenileZamanlayici = null;
let sonCanliRun = "";
const DURUM = { bosta: ["boşta", ""], calisiyor: ["çalışıyor", "yesil"], duraklatildi: ["duraklatıldı", "sari"] };
const AVATARLAR = ["🤖", "🦉", "🧠", "🛠️", "🔎", "✍️", "📊", "🧪", "🕵️", "🎨", "📦", "⚙️"];

function kimdenMetni(k) {
  if (!k || k === "kullanici") return "Sen";
  if (k.startsWith("ajan:")) return "Ajan";
  if (k.startsWith("telegram:")) return "Telegram";
  if (k.startsWith("webhook:")) return "Webhook";
  return k;
}

async function listeCiz() {
  const kap = $("#aj-liste");
  if (!kap) return;
  let ajanlar = [];
  try { ({ ajanlar } = await api("/api/ajanlar")); } catch (e) { kap.innerHTML = `<div class="uyari-kutu">${kacir(e.message)}</div>`; return; }
  if (!ajanlar.length) {
    kap.innerHTML = '<div class="soluk kucuk" style="padding:8px">Henüz ajan yok. "Yeni ajan" ile ilk çalışma arkadaşını oluştur.</div>';
    $("#aj-detay").innerHTML = '<div class="bos-durum-ic soluk">Kalıcı ajanlar kendi klasöründe, kendi talimatıyla çalışır, önceki işlerini hatırlar ve birbirine iş verebilir.</div>';
    return;
  }
  if (!secili || !ajanlar.some((a) => a.id === secili)) secili = ajanlar[0].id;
  kap.innerHTML = ajanlar.map((a) => {
    const [d, renk] = DURUM[a.durum] || [a.durum, ""];
    return `<button class="aj-kart ${a.id === secili ? "secili" : ""}" data-aj="${kacir(a.id)}">
      <span class="aj-avatar">${kacir(a.avatar)}</span>
      <span class="aj-bilgi"><b>${kacir(a.ad)}</b><span class="soluk kucuk">${kacir(a.aciklama || a.model || "aktif model")}</span></span>
      <span class="rozet ${renk}">${kacir(d)}${a.kuyruk_sayisi ? ` · ${a.kuyruk_sayisi} sırada` : ""}</span></button>`;
  }).join("");
  $$("[data-aj]", kap).forEach((b) => { b.onclick = () => { secili = b.dataset.aj; sonCanliRun = ""; listeCiz(); }; });
  detayCiz();
}

async function detayCiz() {
  const kap = $("#aj-detay");
  if (!kap || !secili) return;
  let a;
  try { a = await api(`/api/ajanlar/${secili}`); } catch { return; }
  const yeniIskelet = kap.dataset.aj !== a.id;
  if (yeniIskelet) {
    kap.dataset.aj = a.id;
    kap.innerHTML = `<div class="aj-ust"><span class="aj-avatar buyuk">${kacir(a.avatar)}</span>
        <div style="flex:1"><h2 style="margin:0">${kacir(a.ad)}</h2><div class="soluk kucuk">Klasör: <code>${kacir(a.klasor_yolu)}</code> · Model: ${kacir(a.model || "uygulamanın aktif modeli")}</div></div>
        <button class="btn" id="aj-duzenle">Düzenle</button>
        <button class="btn" id="aj-durdur"></button>
        <button class="btn tehlike" id="aj-sil">Sil</button></div>
      <div id="aj-konusma" class="aj-konusma"></div>
      <div id="aj-canli" class="mesaj asistan ajan-mesaj"><div class="gr-detay"></div></div>
      <div id="aj-kuyruk"></div>
      <div class="satir aj-yaz"><textarea class="alan" id="aj-metin" rows="2" placeholder="${kacir(a.ad)} ajanına bir iş ya da soru yaz… (Enter gönderir, Shift+Enter yeni satır)" style="flex:1"></textarea>
        <button class="btn ana" id="aj-gonder">Gönder</button></div>`;
    $("#aj-duzenle").onclick = () => formAc(a);
    $("#aj-sil").onclick = async () => {
      if (!(await onayla("Ajanı sil", `${a.ad} silinsin mi? Konuşması ve kuyruğu silinir; klasöründeki dosyalar SİLİNMEZ.`, { evet: "Sil", tehlike: true }))) return;
      await api(`/api/ajanlar/${a.id}`, { method: "DELETE" });
      secili = null; listeCiz();
    };
    const gonder = async () => {
      const g = $("#aj-metin");
      const metin = g.value.trim();
      if (!metin) return;
      g.value = "";
      try { await api(`/api/ajanlar/${a.id}/mesaj`, { method: "POST", govde: { metin } }); } catch (e) { bildir(e.message, "hata"); g.value = metin; }
      listeCiz();
    };
    $("#aj-gonder").onclick = gonder;
    $("#aj-metin").onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); gonder(); } };
  }
  const durdur = $("#aj-durdur");
  durdur.textContent = a.duraklatildi ? "Devam ettir" : "Duraklat";
  durdur.onclick = async () => { await api(`/api/ajanlar/${a.id}`, { method: "PUT", govde: { duraklatildi: !a.duraklatildi } }); listeCiz(); };

  $("#aj-konusma").innerHTML = (a.konusma || []).slice(-60).map((m) => {
    if (m.rol === "gelen") return `<div class="aj-msj gelen"><div class="soluk kucuk">${kacir(kimdenMetni(m.kimden))} · ${kacir(m.zaman.slice(11, 16))}</div>${md(m.metin)}</div>`;
    if (m.rol === "cevap") return `<div class="aj-msj cevap"><div class="soluk kucuk">${kacir(a.avatar)} ${kacir(a.ad)} · ${kacir(m.durum)} · ${kacir(m.zaman.slice(11, 16))}</div><div class="md">${md(m.metin)}</div></div>`;
    return `<div class="aj-msj bilgi soluk kucuk">${kacir(m.metin)}</div>`;
  }).join("") || '<div class="soluk kucuk">Henüz konuşma yok.</div>';

  const canli = $("#aj-canli");
  const run = a.aktif_run && a.aktif_run !== "baslatiliyor" ? a.aktif_run : "";
  canli.hidden = !run;
  if (run && run !== sonCanliRun) { sonCanliRun = run; sohbetteGorevGoster(canli.querySelector(".gr-detay"), run); }
  $("#aj-kuyruk").innerHTML = (a.kuyruk || []).length
    ? `<div class="soluk kucuk">Sırada bekleyen ${a.kuyruk.length} iş:</div>${a.kuyruk.map((k) => `<div class="aj-sira"><span>${kacir(k.metin.slice(0, 140))}</span><button class="btn kucuk" data-kuyruk-sil="${kacir(k.id)}">Kaldır</button></div>`).join("")}`
    : "";
  $$("[data-kuyruk-sil]", $("#aj-kuyruk")).forEach((b) => {
    b.onclick = async () => { await api(`/api/ajanlar/${a.id}/kuyruk/${b.dataset.kuyrukSil}`, { method: "DELETE" }); detayCiz(); };
  });
}

function formAc(on = null) {
  const kap = $("#aj-form");
  kap.hidden = false;
  const a = on || { ad: "", avatar: "🤖", aciklama: "", talimat: "", klasor: "", model: "" };
  kap.innerHTML = `<div class="kart">
    <div class="satir"><div class="aj-avatar-sec">${AVATARLAR.map((x) => `<button class="ornek ${x === a.avatar ? "secili" : ""}" data-av="${x}">${x}</button>`).join("")}</div></div>
    <label class="proje-alan">Ad<input class="alan" id="aj-f-ad" maxlength="40" value="${kacir(a.ad)}" placeholder="ör. Araştırmacı"></label>
    <label class="proje-alan">Kısa açıklama (diğer ajanlar bunu görür)<input class="alan" id="aj-f-aciklama" maxlength="300" value="${kacir(a.aciklama)}" placeholder="ör. Web'de araştırma yapar, kaynaklı rapor yazar"></label>
    <label class="proje-alan">Talimatlar<textarea class="alan" id="aj-f-talimat" rows="6" maxlength="20000" placeholder="Bu ajanın rolü, kuralları, çıktı biçimi…">${kacir(a.talimat)}</textarea></label>
    <label class="proje-alan">Çalışma klasörü (boş: Kairo veri klasöründe kendi klasörü)<input class="alan" id="aj-f-klasor" value="${kacir(a.klasor)}" placeholder="C:\\Users\\...\\proje"></label>
    <label class="proje-alan">Model (boş: uygulamanın aktif modeli; ör. deepseek/deepseek-v4.1-flash)<input class="alan" id="aj-f-model" value="${kacir(a.model)}"></label>
    <div class="satir"><button class="btn ana" id="aj-f-kaydet">${on ? "Kaydet" : "Oluştur"}</button><button class="btn" id="aj-f-vazgec">Vazgeç</button></div></div>`;
  let avatar = a.avatar;
  $$("[data-av]", kap).forEach((b) => { b.onclick = () => { avatar = b.dataset.av; $$("[data-av]", kap).forEach((x) => x.classList.toggle("secili", x === b)); }; });
  $("#aj-f-vazgec").onclick = () => { kap.hidden = true; kap.innerHTML = ""; };
  $("#aj-f-kaydet").onclick = async () => {
    const govde = { ad: $("#aj-f-ad").value.trim(), avatar, aciklama: $("#aj-f-aciklama").value.trim(),
      talimat: $("#aj-f-talimat").value, klasor: $("#aj-f-klasor").value.trim(), model: $("#aj-f-model").value.trim() };
    try {
      const r = on ? await api(`/api/ajanlar/${on.id}`, { method: "PUT", govde }) : await api("/api/ajanlar", { method: "POST", govde });
      secili = r.id;
      kap.hidden = true; kap.innerHTML = "";
      $("#aj-detay").dataset.aj = "";
      bildir(on ? "Ajan güncellendi" : `${r.ad} oluşturuldu`, "basari", 1500);
      listeCiz();
    } catch (e) { bildir(e.message, "hata"); }
  };
}

async function telegramCiz() {
  const kap = $("#aj-tg");
  if (!kap) return;
  let t;
  try { t = await api("/api/telegram"); } catch { return; }
  let ajanlar = [];
  try { ({ ajanlar } = await api("/api/ajanlar")); } catch { /* bos */ }
  kap.innerHTML = `<div class="ayar-not">1) Telegram'da <b>@BotFather</b> ile bir bot oluştur, verdiği token'ı buraya yapıştır. 2) Bota telefondan bir mesaj at: izinli değilse sana sohbet kimliğini yazar. 3) O kimliği aşağıya ekle. <b>Yalnız izinli sohbetler</b> ajanlara ulaşır; tam yetki açıksa ajan bilgisayarında iş yapabilir, kimliği kimseyle paylaşma.</div>
    <div class="satir"><span class="ayar-not">${t.token_var ? `Token: <code>${kacir(t.token)}</code>${t.bot ? ` · @${kacir(t.bot)}` : ""}` : '<span class="rozet kirmizi">token yok</span>'}</span>
      <input class="alan" id="tg-token" type="password" autocomplete="off" placeholder="123456:ABC... bot token" style="flex:1"><button class="btn" id="tg-kaydet">Kaydet</button></div>
    <label class="proje-alan">İzinli sohbet kimlikleri (virgülle)<input class="alan" id="tg-izinli" value="${kacir((t.izinli || []).join(", "))}"></label>
    ${t.bekleyen_kimlikler?.length ? `<div class="ayar-not">Bota yazan izinsiz sohbetler: ${t.bekleyen_kimlikler.map((x) => `<button class="ornek" data-tg-ekle="${x}">${x} ekle</button>`).join(" ")}</div>` : ""}
    <label class="proje-alan">Varsayılan ajan<select class="secim" id="tg-ajan"><option value="">(ilk ajan)</option>${ajanlar.map((a) => `<option value="${kacir(a.id)}" ${a.id === t.ajan ? "selected" : ""}>${kacir(a.avatar)} ${kacir(a.ad)}</option>`).join("")}</select></label>
    <div class="anahtar-satir"><div><div>Telegram kanalı açık</div><div class="ayar-not">Komutlar: <code>/ajan Ad mesaj</code>, <code>/durum</code>, <code>/yardim</code>. ${t.calisiyor ? '<span class="rozet yesil">dinliyor</span>' : ""} ${t.son_hata ? `<span class="rozet kirmizi">${kacir(t.son_hata)}</span>` : ""}</div></div>
      <label class="anahtar"><input type="checkbox" id="tg-aktif" ${t.aktif ? "checked" : ""}><span></span></label></div>`;
  const kaydet = async (ek = {}) => {
    const izinli = $("#tg-izinli").value.split(",").map((x) => x.trim()).filter(Boolean);
    try { await api("/api/telegram", { method: "PUT", govde: { izinli, ajan: $("#tg-ajan").value, ...ek } }); bildir("Telegram ayarı kaydedildi", "basari", 1200); }
    catch (e) { bildir(e.message, "hata"); }
    telegramCiz();
  };
  $("#tg-kaydet").onclick = () => { const tk = $("#tg-token").value.trim(); kaydet(tk ? { token: tk } : {}); };
  $("#tg-ajan").onchange = () => kaydet();
  $("#tg-izinli").onchange = () => kaydet();
  $("#tg-aktif").onchange = (e) => kaydet({ aktif: e.target.checked });
  $$("[data-tg-ekle]", kap).forEach((b) => { b.onclick = () => { $("#tg-izinli").value = [$("#tg-izinli").value, b.dataset.tgEkle].filter(Boolean).join(", "); kaydet(); }; });
}

export function ajanlarKur() {
  const tg = $("#aj-telegram");
  if (tg) tg.ontoggle = () => { if (tg.open) telegramCiz(); };
  const yeni = $("#aj-yeni");
  if (yeni) yeni.onclick = () => formAc();
}

export function ajanlarYukle() {
  listeCiz();
  clearInterval(yenileZamanlayici);
  yenileZamanlayici = setInterval(() => {
    if ($("#g-ajanlar")?.hidden) { clearInterval(yenileZamanlayici); return; }
    listeCiz();
  }, 3000);
}
