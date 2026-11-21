// Superajan: is emirleri (dsh-superagent tasarimi). Ilke: az insan dikkati. Panel once insan
// bekleyenleri ve onlarin TEK dogrudan eylemini gosterir; calisan/siradakiler tek satir, bitenler katli.
// Arka uc: /api/superajan. Bir is emrinin canli adimlari gorevler.js ile ayni gorunumde acilir.
import { sohbetteGorevGoster } from "./gorevler.js";
import { kacir, md } from "./md.js";
import { ikonlariYerlestir } from "./ikonlar.js";
import { $, $$, api, bildir, el, menuAc, modal, onayla } from "./ortak.js";

const ASAMA = {
  onay_bekliyor: ["GitHub'dan geldi · onay bekliyor", "sari"],
  insan_bekliyor: ["Senden yanıt bekliyor", "sari"], inceleme: ["İncelemeye hazır", "yesil"],
  taslak: ["Doğrulanmadı (taslak)", "sari"], basarisiz: ["Başarısız", "kirmizi"],
  calisiyor: ["Çalışıyor", "mavi"], sirada: ["Sırada", ""], yapilacak_yok: ["Yapılacak iş yok", ""],
  bitti: ["Bitti", ""], durduruldu: ["Durduruldu", ""],
};
const ONCE = ["onay_bekliyor", "insan_bekliyor", "inceleme", "taslak", "basarisiz"];
let acikDetay = "";

function satir(x) {
  const [etiket, sinif] = ASAMA[x.asama] || [x.asama, ""];
  const pr = x.pr_url ? "" : '<button class="btn kucuk" data-teslim title="Dalı gönderir, PR açar, ilgili issue\'ya yorum yazar">PR aç</button>';
  const eylem = {
    onay_bekliyor: '<button class="btn kucuk ana" data-baslat>Başlat</button><button class="btn kucuk" data-ac>Ayrıntı</button>',
    insan_bekliyor: '<button class="btn kucuk ana" data-ac>Yanıtla</button>',
    inceleme: `<button class="btn kucuk ana" data-birlestir>Ana dala birleştir</button>${pr}<button class="btn kucuk" data-ac>İncele</button>`,
    taslak: '<button class="btn kucuk" data-ac>İncele</button><button class="btn kucuk" data-tekrar>Tamamlat</button>',
    basarisiz: '<button class="btn kucuk" data-tekrar>Tekrar dene</button><button class="btn kucuk" data-ac>Ayrıntı</button>',
    calisiyor: '<button class="btn kucuk" data-ac>İzle</button>',
  }[x.asama] || "";
  const kapali = ["bitti", "durduruldu", "yapilacak_yok"].includes(x.asama);
  return `<div class="ek-satir-sar is-satir" data-is="${kacir(x.id)}"><div class="ek-satir">
    <div class="ek-govde"><div class="ek-ad">${kacir(x.baslik)}</div>
      <div class="ek-alt soluk">${kacir(x.proje_kok.split(/[\\/]/).pop())}${x.dal ? ` · dal <code>${kacir(x.dal)}</code>` : ""}${x.bekleme ? ` · ${kacir(x.bekleme)}` : ""}${(x.konular || []).length ? ` · ${kacir(x.konular.join(", "))}` : ""}${x.pr_url && /^https:\/\/github\.com\//.test(x.pr_url) ? ` · <a href="${kacir(x.pr_url)}" target="_blank" rel="noopener">PR</a>` : ""}</div></div>
    <span class="rozet ek-durum ${sinif}">${kacir(etiket)}</span>${eylem}
    <button class="ikon-btn" data-ikon="daha" title="Seçenekler" data-menu ${kapali && !x.runlar.length ? "hidden" : ""}></button></div>
    <div class="is-detay" ${acikDetay === x.id ? "" : "hidden"}></div></div>`;
}

export async function isEmirleriCiz() {
  const kap = $("#aj-isler-liste");
  if (!kap) return;
  let v;
  try { v = await api("/api/superajan"); } catch (e) { kap.innerHTML = `<div class="soluk kucuk">${kacir(e.message)}</div>`; return; }
  $("#aj-isler-sayi").textContent = v.insan_bekliyor ? `${v.insan_bekliyor} seni bekliyor` : "";
  $("#aj-isler-sayi").className = v.insan_bekliyor ? "rozet sari" : "";
  const once = v.isler.filter((x) => ONCE.includes(x.asama));
  const suren = v.isler.filter((x) => ["calisiyor", "sirada"].includes(x.asama));
  const biten = v.isler.filter((x) => !ONCE.includes(x.asama) && !["calisiyor", "sirada"].includes(x.asama));
  kap.innerHTML = `${once.length || suren.length ? `<div class="ek-liste">${[...once, ...suren].map(satir).join("")}</div>`
    : '<div class="soluk kucuk ek-bos">Açık iş emri yok. "Yeni iş emri" ile bir işi ayrı bir dalda ajana yaptırabilirsin; bitince incelersin, istersen ana dala birleştirirsin.</div>'}
    ${biten.length ? `<details class="ek-ekle"><summary>Bitenler <span class="soluk kucuk">${biten.length}</span></summary><div class="ek-liste">${biten.map(satir).join("")}</div></details>` : ""}`;
  ikonlariBagla(kap, v.isler);
}

function ikonlariBagla(kap, isler) {
  ikonlariYerlestir(kap);
  $$("[data-is]", kap).forEach((k) => {
    const x = isler.find((i) => i.id === k.dataset.is);
    const istek = async (yol, govde) => {
      try { await api(`/api/superajan/isler/${x.id}/${yol}`, { method: "POST", govde }); await isEmirleriCiz(); } catch (e) { bildir(e.message, "hata", 7000); }
    };
    $("[data-ac]", k)?.addEventListener("click", () => detayAcKapa(k, x));
    $("[data-tekrar]", k)?.addEventListener("click", () => istek("tekrar"));
    $("[data-baslat]", k)?.addEventListener("click", () => istek("baslat"));
    $("[data-teslim]", k)?.addEventListener("click", async () => {
      if (!(await onayla("PR aç", `"${x.baslik}" işinin dalı (${x.dal}) GitHub'a gönderilsin, PR açılsın${(x.konular || []).length ? " ve ilgili issue'ya yorum yazılsın" : ""} mı?`, { evet: "Gönder ve PR aç" }))) return;
      try {
        const s = await api(`/api/superajan/isler/${x.id}/teslim`, { method: "POST", govde: {} });
        bildir(`PR açıldı: ${s.pr_url}`, "basari", 7000);
      } catch (e) { bildir(e.message, "hata", 9000); }
      isEmirleriCiz();
    });
    $("[data-birlestir]", k)?.addEventListener("click", async () => {
      if (!(await onayla("Ana dala birleştir", `"${x.baslik}" işinin dalı (${x.dal}) ana dala birleştirilsin mi? Senin commit edilmemiş değişikliğin varsa birleştirme yapılmaz; çakışma olursa geri alınır.`, { evet: "Birleştir" }))) return;
      try {
        const s = await api(`/api/superajan/isler/${x.id}/birlestir`, { method: "POST", govde: {} });
        const m = { birlestirildi: "Ana dala birleştirildi.", degisiklik_yok: "Birleştirilecek değişiklik yok.", kullanici_degisikligi_var: s.not, catisma: `Çakışma: ${(s.catisan || []).join(", ")}. ${s.not || ""}` }[s.durum] || s.durum;
        bildir(m, s.durum === "birlestirildi" ? "basari" : "uyari", 7000);
      } catch (e) { bildir(e.message, "hata", 7000); }
      isEmirleriCiz();
    });
    $("[data-menu]", k)?.addEventListener("click", (e) => {
      const acik = x.durum === "acik";
      menuAc(e.currentTarget, [
        ...(acik ? [{ metin: "Takip mesajı gönder", ikon: "kalem", eylem: () => takipSor(x) }] : []),
        ...(acik && x.asama !== "durduruldu" ? [{ metin: "Durdur (kalıcı)", ikon: "durdur", eylem: () => istek("durdur") }] : []),
        ...(acik && x.dal ? [{ metin: "Değişiklikleri at", ikon: "cop", tehlike: true, eylem: async () => {
          if (await onayla("Değişiklikleri at", "Bu işin ayrı daldaki tüm değişiklikleri silinsin mi? Ana dala dokunulmaz.", { evet: "At", tehlike: true })) istek("at");
        } }] : []),
        ...(!acik || !x.runlar.length ? [{ metin: "Listeden kaldır", ikon: "cop", eylem: async () => {
          try { await api(`/api/superajan/isler/${x.id}`, { method: "DELETE" }); isEmirleriCiz(); } catch (er) { bildir(er.message, "hata"); }
        } }] : []),
      ], { sagaHizali: true });
    });
  });
}

function detayAcKapa(k, x) {
  const d = $(".is-detay", k);
  if (!d.hidden) { d.hidden = true; acikDetay = ""; return; }
  acikDetay = x.id;
  d.hidden = false;
  d.innerHTML = `<div class="soluk kucuk">${md(x.gorev)}</div>${x.ozet ? `<div class="is-ozet md">${md(x.ozet)}</div>` : ""}<div class="is-canli"></div>`;
  if (x.run) sohbetteGorevGoster($(".is-canli", d), x.run);
}

function takipSor(x) {
  const g = el(`<div><p class="soluk kucuk">Çalışıyorsa yönlendirme olarak iletilir; bittiyse aynı dalda yeni bir atama başlar.</p><textarea class="alan" id="is-takip" rows="4" style="width:100%" placeholder="ör. Testleri de ekle"></textarea></div>`);
  modal({ baslik: `Takip: ${x.baslik}`, icerik: g, dugmeler: [{ metin: "İptal" }, { metin: "Gönder", tur: "ana", eylem: async (kapat) => {
    const metin = $("#is-takip", g).value.trim();
    if (!metin) return;
    try { await api(`/api/superajan/isler/${x.id}/mesaj`, { method: "POST", govde: { metin } }); kapat(); isEmirleriCiz(); } catch (e) { bildir(e.message, "hata", 7000); }
  } }] });
}

export function yeniIsEmri(onDoldur = {}) {
  const g = el(`<div class="ske">
    <p class="soluk kucuk">İş, açık projenin <b>ayrı bir git dalında</b> ajana yaptırılır; ana daldaki kod değişmez. Bitince incelersin, istersen tek tıkla ana dala birleştirirsin. Ajan gerekirse sana tek bir soru sorar.</p>
    <label class="proje-alan">Başlık (isteğe bağlı)<input class="alan" id="is-baslik" maxlength="120" placeholder="ör. Giriş ekranına şifre göster düğmesi"></label>
    <label class="proje-alan">Ne yapılsın?<textarea class="alan" id="is-gorev" rows="6" placeholder="İşi, ilgili dosyaları ve bitti ölçütünü yaz."></textarea></label></div>`);
  $("#is-gorev", g).value = onDoldur.gorev || "";
  $("#is-baslik", g).value = onDoldur.baslik || "";
  modal({ baslik: "Yeni iş emri", icerik: g, genis: true, dugmeler: [{ metin: "İptal" }, { metin: "Başlat", tur: "ana", eylem: async (kapat, b) => {
    const govde = { gorev: $("#is-gorev", g).value.trim(), baslik: $("#is-baslik", g).value.trim(), kaynak: onDoldur.kaynak || "elle" };
    if (!govde.gorev) { bildir("Ne yapılacağını yaz.", "uyari"); return; }
    b.disabled = true;
    try {
      await api("/api/superajan/isler", { method: "POST", govde });
    } catch (e) {
      b.disabled = false;
      if (!String(e.message).includes("GIT_YOK")) { bildir(e.message, "hata", 7000); return; }
      if (!(await onayla("Git deposu oluşturulsun mu?", "İş emri ayrı bir dalda çalışır; bunun için proje klasörü bir git deposu olmalı. Kairo bu klasörde git deposu açıp mevcut dosyalarla ilk commit'i atsın mı? (.gitignore'a uyulur; dosyaların silinmez ya da değişmez.)", { evet: "Oluştur ve başlat" }))) return;
      try {
        await api("/api/superajan/git-baslat", { method: "POST", govde: {} });
        await api("/api/superajan/isler", { method: "POST", govde });
      } catch (e2) { bildir(e2.message, "hata", 7000); return; }
    }
    bildir("İş emri başlatıldı.", "basari", 2500);
    kapat();
    isEmirleriCiz();
  } }] });
}

// Sohbetteki thread karti (Claude "proje sohbeti" gibi): is_emri_baslat / is_emirleri_durum sonucu.
// Kart DOM'da kaldikca 4 sn'de bir guncellenir; satira tiklayinca canli adimlar + yonlendirme acilir.
export function threadKarti(ids, kap) {
  const kart = el('<div class="thread-kart"><div class="soluk kucuk thread-ust">Thread\'ler</div><div class="thread-liste"></div></div>');
  kap.append(kart);
  const acik = new Set();
  const ciz = async () => {
    if (!kart.isConnected) return;
    let v;
    try { v = await api("/api/superajan"); } catch { return setTimeout(ciz, 8000); }
    const isler = v.isler.filter((x) => ids.includes(x.id));
    const liste = $(".thread-liste", kart);
    for (const x of isler) {
      const [etiket, sinif] = ASAMA[x.asama] || [x.asama, ""];
      let s = $(`[data-th="${x.id}"]`, liste);
      if (!s) {
        s = el(`<div class="thread-satir" data-th="${kacir(x.id)}"><button class="thread-bas"><span class="thread-nokta"></span><span class="thread-ad"></span><span class="rozet"></span></button><div class="thread-soru" hidden></div><div class="thread-detay" hidden></div></div>`);
        $(".thread-bas", s).onclick = () => threadAcKapa(s, x, acik);
        liste.append(s);
      }
      $(".thread-ad", s).textContent = x.baslik;
      $(".thread-nokta", s).className = `thread-nokta ${sinif}${x.asama === "calisiyor" ? " parilti" : ""}`;
      const r = $(".rozet", s);
      r.className = `rozet ${sinif}`;
      r.textContent = etiket;
      s.dataset.run = x.run;
      soruCiz(s, x, acik);
      // onay istedi (soru degil): kart kendiliginden acilir, onay canli gorunumden verilir
      if (x.asama === "insan_bekliyor" && !x.soru?.metin && !acik.has(x.id)) threadAcKapa(s, x, acik);
      else if (acik.has(x.id) && s.dataset.cizilenRun !== x.run) threadDetay(s, x);
    }
    if (isler.some((x) => !["bitti", "durduruldu", "yapilacak_yok"].includes(x.asama))) setTimeout(ciz, 4000);
  };
  ciz();
  return kart;
}

function threadAcKapa(s, x, acik) {
  const d = $(".thread-detay", s);
  if (!d.hidden) { d.hidden = true; acik.delete(x.id); return; }
  acik.add(x.id);
  d.hidden = false;
  threadDetay(s, x);
}

function threadDetay(s, x) {
  const d = $(".thread-detay", s);
  s.dataset.cizilenRun = x.run;
  d.innerHTML = `${x.ozet ? `<div class="is-ozet md">${md(x.ozet)}</div>` : ""}<div class="is-canli"></div>
    <div class="thread-yonlendir"><input class="alan" placeholder="Bu thread'i yönlendir… (/btw soru, /fork talimat)" aria-label="Bu thread'i yönlendir"><button class="btn kucuk">Gönder</button></div>`;
  if (x.run) sohbetteGorevGoster($(".is-canli", d), x.run);
  const girdi = $("input", d);
  const gonder = async () => {
    const metin = girdi.value.trim();
    if (!metin) return;
    const [, komut, arg = ""] = metin.match(/^\/(btw|fork)(?:\s+|$)([\s\S]*)$/) || [];
    if (komut === "btw") { // yan soru: thread'i bozmadan ana sohbete gider
      if (!arg.trim()) return bildir("/btw sonrasına soru yaz.", "uyari", 4000);
      const ana = $("#girdi");
      if (!ana || !$("#btn-gonder")) return;
      ana.value = `(${x.baslik} thread'i hakkında) ${arg.trim()}`;
      ana.dispatchEvent(new Event("input", { bubbles: true }));
      girdi.value = "";
      return $("#btn-gonder").click();
    }
    if (komut === "fork") { // ayni isten yeni thread (ayri dal)
      if (!arg.trim()) return bildir("/fork sonrasına talimat yaz.", "uyari", 4000);
      try {
        const y = await api("/api/superajan/isler", { method: "POST", govde: { baslik: `${x.baslik} (fork)`.slice(0, 120), gorev: `${x.gorev}

EK TALIMAT: ${arg}`.slice(0, 8000), proje_kok: x.proje_kok, kaynak: "sohbet" } });
        threadKarti([y.id], s.closest(".thread-kart").parentElement);
        girdi.value = "";
      } catch (e) { bildir(e.message, "hata", 7000); }
      return;
    }
    try { await api(`/api/superajan/isler/${x.id}/mesaj`, { method: "POST", govde: { metin } }); girdi.value = ""; bildir("Thread'e iletildi.", "basari", 2500); } catch (e) { bildir(e.message, "hata", 7000); }
  };
  $(".thread-yonlendir button", d).onclick = gonder;
  girdi.onkeydown = (e) => { if (e.key === "Enter") gonder(); };
}

// GitHub kaynagi (D3-D5): /kairo ile baslayan issue/yorum is emri acar; gozle modunda "Baslat" bekler
export async function githubAyarAc() {
  let a;
  try { a = await api("/api/superajan/github"); } catch (e) { return bildir(e.message, "hata"); }
  const g = el(`<div>
    <p class="soluk kucuk">Depodaki bir issue ya da yorum ilk satırda <code>/kairo</code> ile başlarsa ve yazan izinli listedeyse Kairo bunu iş emrine çevirir (60 sn'de bir yoklanır). Ayrı GitHub hesabı gerekmez; gh girişin kullanılır.${a.gh ? "" : " <b>GitHub CLI (gh) kurulu değil.</b>"}</p>
    <label class="anahtar-satir"><span>Açık</span><span class="anahtar"><input type="checkbox" id="gh-aktif" ${a.aktif ? "checked" : ""}><span></span></span></label>
    <label class="proje-alan">Depo (sahip/ad)<input class="alan" id="gh-depo" placeholder="umutc6230/proje" value="${kacir(a.depo)}"></label>
    <label class="proje-alan">Yerel klasör (boş: açık proje)<input class="alan" id="gh-kok" value="${kacir(a.proje_kok)}"></label>
    <label class="proje-alan">İzinli GitHub kullanıcıları (virgülle; boş: kendi hesabın)<input class="alan" id="gh-izinli" value="${kacir(a.izinli.join(", "))}"></label>
    <label class="proje-alan">Mod<select class="secim" id="gh-mod">
      <option value="gozle" ${a.mod === "gozle" ? "selected" : ""}>Gözle: iş emri açılır, sen "Başlat" dersin; GitHub'a yalnız "PR aç" ile yazılır</option>
      <option value="yap" ${a.mod === "yap" ? "selected" : ""}>Yap: hemen başlar; doğrulanmış iş otomatik PR olur</option></select></label>
  </div>`);
  modal({ baslik: "GitHub'dan iş emri", icerik: g, dugmeler: [
    { metin: "Kapat" },
    { metin: "Şimdi yokla", eylem: async () => {
      try { const s = await api("/api/superajan/yokla", { method: "POST", govde: {} }); bildir(s.durum === "kapali" ? "Kaynak kapalı." : `${s.acilan} yeni iş emri, ${s.takip} takip.`, "bilgi", 5000); isEmirleriCiz(); } catch (e) { bildir(e.message, "hata", 8000); }
    } },
    { metin: "Kaydet", tur: "ana", eylem: async (kapat) => {
      const govde = { aktif: $("#gh-aktif", g).checked, depo: $("#gh-depo", g).value.trim(), proje_kok: $("#gh-kok", g).value.trim(),
        izinli: $("#gh-izinli", g).value.split(",").map((x) => x.trim()).filter(Boolean), mod: $("#gh-mod", g).value };
      try { await api("/api/superajan/github", { method: "PUT", govde }); bildir("Kaydedildi.", "basari", 2500); kapat(); } catch (e) { bildir(e.message, "hata", 8000); }
    } },
  ] });
}

// T3: thread'in sorusu proje sohbetinde secenekli kart (ilk secenek onerilen); cevap thread'e gider
function soruCiz(s, x, acik) {
  const k = $(".thread-soru", s);
  const soru = x.soru?.metin ? x.soru : null;
  const anahtar = soru ? `${x.run}|${soru.metin}` : "";
  if (k.dataset.anahtar === anahtar) return; // ayni soru: yeniden cizip secimi bozma
  k.dataset.anahtar = anahtar;
  k.hidden = !soru;
  if (!soru) { k.innerHTML = ""; return; }
  k.innerHTML = `<div class="soru-metin md">${md(soru.metin)}</div><div class="dugme-sira"></div>`;
  const sira = $(".dugme-sira", k);
  const gonder = async (metin, btn) => {
    sira.querySelectorAll("button").forEach((b) => { b.disabled = true; });
    try {
      await api(`/api/superajan/isler/${x.id}/mesaj`, { method: "POST", govde: { metin } });
      k.innerHTML = `<span class="soluk kucuk">Cevaplandı: ${kacir(metin)}</span>`;
    } catch (e) { bildir(e.message, "hata", 7000); sira.querySelectorAll("button").forEach((b) => { b.disabled = false; }); btn?.focus(); }
  };
  (soru.secenekler || []).forEach((sec, i) => {
    const b = el(`<button class="btn kucuk ${i === 0 ? "ana" : ""}">${String.fromCharCode(65 + i)}. ${kacir(sec)}${i === 0 ? ' <span class="soluk">(önerilen)</span>' : ""}</button>`);
    b.onclick = () => gonder(sec, b);
    sira.append(b);
  });
  const ac = el('<button class="btn kucuk">Thread\'i aç</button>');
  ac.onclick = () => { if ($(".thread-detay", s).hidden) threadAcKapa(s, x, acik); };
  sira.append(ac);
}
