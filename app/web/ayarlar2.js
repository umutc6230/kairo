// Claude Desktop ayar karsiliklari: Gorunum, Bildirimler, Masaustu, Kod sekmeleri;
// baglayici ice aktarma + dizin; gorunumun uygulanmasi ve bildirim gonderme.
import { kacir } from "./md.js";
import { $, $$, api, bildir, durum, onayla, sor } from "./ortak.js";

const sec = (ad, secenekler) => `<select class="secim" data-ayar="${ad}">${secenekler.map(([v, e]) => `<option value="${v}">${e}</option>`).join("")}</select>`;
const satir = (baslik, aciklama, kontrol) => `<div class="ayar-satir"><div><div>${baslik}</div>${aciklama ? `<div class="soluk kucuk">${aciklama}</div>` : ""}</div><div>${kontrol}</div></div>`;
const anahtar = (ad) => `<label class="anahtar"><input type="checkbox" data-ayar="${ad}"><span></span></label>`;

export const EK_SEKMELER = `<button class="sekme" data-sekme="gorunum">Görünüm</button><button class="sekme" data-sekme="bildirim">Bildirimler</button><button class="sekme" data-sekme="masaustu">Masaüstü</button><button class="sekme" data-sekme="kod">Kod</button>`;

export const EK_PANELLER = `
<div class="modal-govde" data-panel="gorunum" hidden>
  ${satir("Tema", "Sistem, Windows'un açık/koyu ayarını izler.", sec("tema", [["sistem", "Sistem"], ["acik", "Açık"], ["koyu", "Koyu"]]))}
  ${satir("Yazı boyutu", "", sec("yazi_boyutu", [["kucuk", "Küçük"], ["orta", "Orta"], ["buyuk", "Büyük"]]))}
  ${satir("Sohbet genişliği", "", sec("sohbet_genisligi", [["dar", "Dar"], ["genis", "Geniş"]]))}
  ${satir("Hareket", "Azalt seçilirse animasyonlar kapanır.", sec("hareket", [["sistem", "Sistem"], ["azalt", "Azalt"]]))}
</div>
<div class="modal-govde" data-panel="bildirim" hidden>
  <div class="ayar-not">Bildirimler Windows bildirim merkezine gider; yalnız Kairo penceresi arkadayken gösterilir.</div>
  ${satir("Yanıt bitince", "Uzun işler için kullanışlı.", anahtar("bildirim_yanit"))}
  ${satir("Onay beklerken", "Ajan bir komut ya da dosya değişikliği için onay istediğinde.", anahtar("bildirim_onay"))}
  ${satir("Rutinler", "Zamanlanmış görev bittiğinde ya da çalışamadığında.", anahtar("bildirim_zamanlama"))}
  <div class="satir"><button class="btn" id="bd-test">Deneme bildirimi gönder</button></div>
</div>
<div class="modal-govde" data-panel="masaustu" hidden>
  ${satir("Sürüm", "", `<span id="ms-surum" class="soluk"></span>`)}
  ${satir("Oturum açılınca başlat", "Windows Başlangıç klasörüne kısayol koyar; kapatınca silinir.", anahtar("baslangicta_ac"))}
  ${satir("Sistem tepsisi", "Kapat düğmesi Kairo'yu tepsiye küçültür; rutinler çalışmaya devam eder. Yeniden başlatınca geçerli olur.", anahtar("sistem_tepsisi"))}
  ${satir("Hızlı açma kısayolu", "Kairo'yu her yerden öne getirir. Ör. Ctrl+Alt+Space (boş: kapalı).", `<input class="alan" data-ayar="hizli_kisayol" style="max-width:170px">`)}
  ${satir("Dikte kısayolu", "Sohbette mikrofonu açar/kapatır.", `<input class="alan" data-ayar="dikte_kisayolu" style="max-width:170px">`)}
  <div class="ayar-not" id="ms-hata" hidden></div>
  <h4 style="margin:12px 0 4px">Depolama</h4>
  <div id="ms-depo" class="ayar-grup"></div>
  <div class="satir"><button class="btn" id="ms-klasor">Veri klasörünü aç</button></div>
</div>
<div class="modal-govde" data-panel="kod" hidden>
  ${satir("Sohbet ayrıntısı", "Yeni mesajlarda ne kadar ayrıntı görünür.", sec("ayrinti", [["normal", "Normal"], ["dusunme", "Düşünme"], ["ayrintili", "Ayrıntılı"]]))}
  ${satir("Çıktı stili", "Modelin cevaplarını nasıl yapılandıracağı.", sec("cikti_stili", [["varsayilan", "Varsayılan"], ["aciklayici", "Açıklayıcı"], ["ogretici", "Öğretici"], ["kisa", "Kısa"]]))}
  ${satir("Branch öneki", "Ajanın izole çalışmada açtığı dalların başına eklenir.", `<input class="alan" data-ayar="branch_oneki" style="max-width:170px">`)}
  ${satir("Boştaki sohbetleri arşivle", "Bu kadar gün dokunulmayan sohbetler listede Arşiv'e iner (silinmez). 0: hiç.", `<input class="alan" type="number" min="0" max="365" data-ayar="arsiv_gun" style="max-width:90px">`)}
  ${satir("Bilgisayarı uyanık tut", "Kairo açıkken uyku moduna geçmez (rutinler çalışabilsin).", `<label class="anahtar"><input type="checkbox" id="kd-uyanik"><span></span></label>`)}
</div>`;

export function ekSekmeKur(govde, kaydet) {
  const a = durum.ayarlar;
  $$("[data-ayar]", govde).forEach((e) => {
    const ad = e.dataset.ayar;
    if (e.type === "checkbox") e.checked = !!a[ad]; else e.value = a[ad] ?? "";
    e.onchange = async () => {
      const deger = e.type === "checkbox" ? e.checked : e.type === "number" ? Number(e.value) : e.value.trim();
      await kaydet({ [ad]: deger }, true);
      gorunumUygula(durum.ayarlar);
      if (ad === "baslangicta_ac" || ad === "hizli_kisayol") masaustuYenile(govde);
    };
  });
  $("#bd-test", govde).onclick = () => masaustuBildirimi("Kairo", "Bildirimler çalışıyor.", true);
  $("#ms-klasor", govde).onclick = () => api("/api/masaustu/klasor-ac", { method: "POST" }).catch((e) => bildir(e.message, "hata"));
  $("#ms-surum", govde).textContent = durum.bilgi?.surum || "";
  api("/api/uyanik").then((r) => { $("#kd-uyanik", govde).checked = r.acik; }).catch(() => {});
  $("#kd-uyanik", govde).onchange = (e) => api("/api/uyanik", { method: "PUT", govde: { acik: e.target.checked } }).catch((x) => bildir(x.message, "hata"));
  masaustuYenile(govde);
}

async function masaustuYenile(govde) {
  try {
    const m = await api("/api/masaustu");
    const b = $('[data-ayar="baslangicta_ac"]', govde);
    if (b) b.checked = m.baslangicta_ac;
    const h = $("#ms-hata", govde);
    h.hidden = !m.kisayol_hata; h.textContent = m.kisayol_hata;
    const mb = (x) => (x / 1048576).toFixed(1);
    const toplam = m.depolama.reduce((t, x) => t + x.bayt, 0);
    $("#ms-depo", govde).innerHTML = `<div class="soluk kucuk">Toplam ${mb(toplam)} MB · ${kacir(m.veri_dizini)}</div>` +
      m.depolama.filter((x) => x.bayt > 0).slice(0, 10).map((x) => `<div class="satir"><span style="flex:1">${kacir(x.ad)}</span><span class="soluk">${mb(x.bayt)} MB</span></div>`).join("");
  } catch { /* sessiz */ }
}

// ---- gorunum ----
export function gorunumUygula(a) {
  if (!a) return;
  const k = document.documentElement;
  const koyuSistem = window.matchMedia("(prefers-color-scheme: dark)").matches;
  k.dataset.tema = a.tema === "sistem" ? (koyuSistem ? "koyu" : "acik") : a.tema || "koyu";
  k.dataset.yazi = a.yazi_boyutu || "orta";
  k.dataset.genislik = a.sohbet_genisligi || "dar";
  k.dataset.hareket = a.hareket || "sistem";
  k.dataset.ayrinti = a.ayrinti || "normal";
}
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => gorunumUygula(durum.ayarlar));

// ---- bildirim: pencere arkadayken Windows bildirimi, onundeyse hicbir sey ----
export function masaustuBildirimi(baslik, metin, zorla = false) {
  if (!zorla && document.hasFocus() && !document.hidden) return;
  api("/api/bildirim", { method: "POST", govde: { baslik, metin } })
    .then((r) => { if (!r.gonderildi) bildir(`${baslik}: ${metin}`, "bilgi", 4000); })
    .catch(() => {});
}

// ---- kisayol eslestirme (uygulama ici) ----
export function kisayolEslesir(e, metin) {
  if (!metin) return false;
  const p = metin.toLowerCase().split("+").map((x) => x.trim());
  const tus = p[p.length - 1];
  return e.ctrlKey === p.includes("ctrl") && e.altKey === p.includes("alt") && e.shiftKey === p.includes("shift")
    && e.key.toLowerCase() === (tus === "space" ? " " : tus);
}

// ---- arac paketleri (REA, Craft Anything): surumu/ozeti sabit, veri klasorune kurulur ----
export async function aracPaketleriCiz(govde, yenile) {
  const kap = document.createElement("div");
  kap.className = "ayar-grup";
  kap.id = "arac-paketleri";
  $('[data-panel="mcp"]', govde).prepend(kap);
  const ciz = async () => {
    let paketler;
    try { ({ paketler } = await api("/api/arac-paketleri")); } catch (e) { kap.innerHTML = `<div class="hata-kutu">${kacir(e.message)}</div>`; return; }
    kap.innerHTML = `<b class="kucuk">Araç paketleri</b>
      <div class="ayar-not">Hazır araç setleri. Sürümü ve özeti sabittir; uygulamanın veri klasörüne kurulur, sistemde başka bir şeyi değiştirmez. Araçlar geçitle sunulur (ara → şema → çağır), her çağrı yine izin ister.</div>
      <div class="rutin-sablon">${paketler.map((p) => `<div class="secenek-kart" data-paket="${kacir(p.ad)}"><div style="flex:1">
        <div class="ust"><b>${kacir(p.baslik)}</b> <span class="soluk kucuk">v${kacir(p.surum)} · ~${kacir(p.boyut_mb)} MB · ${kacir(p.lisans)}</span></div>
        <div class="alt">${kacir(p.aciklama)}</div>
        ${p.engel ? `<div class="alt vurgu">${kacir(p.engel)}</div>` : ""}</div>
        ${p.mesgul ? '<span class="rozet sari">kuruluyor…</span>' : p.kurulu
          ? `<span class="rozet yesil">kurulu</span><button class="btn" data-kaldir="${kacir(p.ad)}">Kaldır</button>`
          : `<button class="btn ana" data-kur="${kacir(p.ad)}" ${p.engel ? "disabled" : ""}>Kur</button>`}</div>`).join("")}</div>`;
    $$("[data-kur]", kap).forEach((b) => {
      b.onclick = async () => {
        const p = paketler.find((x) => x.ad === b.dataset.kur);
        const metin = `${p.baslik} v${p.surum} indirilecek (~${p.boyut_mb} MB).\nKaynak: ${p.kaynak}${p.uyari ? `\n\n${p.uyari}` : ""}`;
        if (!(await onayla("Araç paketini kur", metin, { evet: "İndir ve kur" }))) return;
        b.disabled = true;
        b.textContent = "Kuruluyor…";
        try {
          await api(`/api/arac-paketleri/${p.ad}/kur`, { method: "POST" });
          bildir(`${p.baslik} kuruldu; bağlayıcı eklendi.`, "basari", 4000);
        } catch (e) { bildir(e.message, "hata", 8000); }
        ciz(); yenile();
      };
    });
    $$("[data-kaldir]", kap).forEach((b) => {
      b.onclick = async () => {
        const p = paketler.find((x) => x.ad === b.dataset.kaldir);
        if (!(await onayla("Araç paketini kaldır", `${p.baslik} dosyaları, bağlayıcısı ve skill'i silinecek.`, { evet: "Kaldır", tehlike: true }))) return;
        try { await api(`/api/arac-paketleri/${p.ad}`, { method: "DELETE" }); bildir(`${p.baslik} kaldırıldı.`, "basari", 3000); } catch (e) { bildir(e.message, "hata", 8000); }
        ciz(); yenile();
      };
    });
  };
  ciz();
}

// ---- baglayici ice aktarma + dizin ----
export async function baglayiciIceAktarCiz(govde, yenile) {
  const kap = document.createElement("div");
  kap.className = "ayar-grup";
  $('[data-panel="mcp"]', govde).prepend(kap);
  const ciz = async () => {
    try {
      const { bulunan, dizin } = await api("/api/mcp/ice-aktar");
      kap.innerHTML = `<b class="kucuk">Claude Code ve Claude Desktop'taki bağlayıcılar</b>
        ${bulunan.map((b) => `<div class="satir"><span style="flex:1">${kacir(b.baslik)} <span class="soluk kucuk">${kacir(b.kaynak)} · ${kacir(b.veri.komut || b.veri.url)}</span></span>${b.var ? '<span class="rozet yesil">ekli</span>' : `<button class="btn" data-ice="${kacir(b.anahtar)}">İçe aktar</button>`}</div>`).join("") || '<div class="soluk kucuk">Bulunamadı.</div>'}
        ${bulunan.some((b) => !b.var) ? '<div class="satir"><button class="btn" id="mc-hepsi">Hepsini içe aktar</button></div>' : ""}
        <b class="kucuk" style="margin-top:8px">Dizin</b>
        <div class="rutin-sablon">${dizin.map((d, i) => `<div class="secenek-kart"><div style="flex:1"><div class="ust"><b>${kacir(d.baslik)}</b></div><div class="alt">${kacir(d.aciklama)}</div></div>${d.var ? '<span class="rozet yesil">ekli</span>' : `<button class="btn" data-dz="${i}">Ekle</button>`}</div>`).join("")}</div>`;
      const aktar = async (anahtarlar) => {
        const r = await api("/api/mcp/ice-aktar", { method: "POST", govde: { anahtarlar } });
        bildir(`Eklendi: ${r.eklenen.length}${r.hatalar.length ? `, hata: ${r.hatalar.join("; ")}` : ""}`, r.hatalar.length ? "uyari" : "basari", 3000);
        ciz(); yenile();
      };
      $$("[data-ice]", kap).forEach((b) => { b.onclick = () => aktar([b.dataset.ice]).catch((e) => bildir(e.message, "hata")); });
      const h = $("#mc-hepsi", kap);
      if (h) h.onclick = () => aktar(bulunan.filter((b) => !b.var).map((b) => b.anahtar)).catch((e) => bildir(e.message, "hata"));
      $$("[data-dz]", kap).forEach((b) => {
        b.onclick = async () => {
          const d = dizin[+b.dataset.dz];
          const veri = { ad: d.ad };
          if (d.url) veri.url = d.url;
          else {
            veri.komut = d.komut;
            veri.argumanlar = [];
            for (const a of d.argumanlar) {
              if (a === "{klasor}") {
                const k = await sor("Klasör yolu", "");
                if (!k) return;
                veri.argumanlar.push(k.trim());
              } else veri.argumanlar.push(a);
            }
          }
          if (d.baslik_iste) {
            const t = await sor(d.baslik_iste, "");
            if (!t) return;
            veri.basliklar = { Authorization: `Bearer ${t.trim()}` };
          }
          try {
            await api("/api/mcp", { method: "POST", govde: veri });
            if (d.oauth) { await api(`/api/mcp/${d.ad}/oauth`, { method: "POST" }); bildir(`${d.baslik} eklendi; tarayıcıda giriş yap.`, "bilgi", 5000); }
            else bildir(`${d.baslik} eklendi.`, "basari", 1500);
            ciz(); yenile();
          } catch (e) { bildir(e.message, "hata"); }
        };
      });
    } catch (e) { kap.innerHTML = `<div class="soluk kucuk">${kacir(e.message)}</div>`; }
  };
  ciz();
}
