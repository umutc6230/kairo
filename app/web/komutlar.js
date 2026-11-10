// Slash komut kaydi (A6.3). Komutlar YEREL calisir, modele mesaj olarak gitmez.
// Servisi hazir olmayan komut sahte cevap vermez: "henuz yok" der.
import { ayarlarAc } from "./ayarlar.js";
import { diffGoster, reviewYap } from "./inceleme.js";
import { kacir } from "./md.js";
import { api, bildir, durum, modal } from "./ortak.js";
import { projeAc } from "./proje.js";

const git = (hedef) => document.querySelector(`[data-git="${hedef}"]`)?.click();

function bilgiPenceresi(baslik, satirlar) {
  const html = satirlar.map(([k, v]) => `<div class="izin-satiri"><span class="soluk">${kacir(k)}</span><span>${kacir(v)}</span></div>`).join("");
  modal({ baslik, icerik: html, dugmeler: [{ metin: "Kapat" }] });
}

export const KOMUTLAR = {
  "/help": { aciklama: "Komutları listeler", calistir: () => yardim() },
  "/status": {
    aciklama: "Model, sağlayıcı, izin ve izolasyon durumu",
    calistir: async () => {
      const [y, i] = await Promise.all([api("/api/model/yetenek"), api("/api/izinler")]);
      bilgiPenceresi("Durum", [
        ["Model", `${y.model} (${y.saglayici})`], ["Bağlam", y.baglam], ["Araç desteği", y.araclar ? "var" : "yok"],
        ["Mod", i.mod], ["Güven", i.guven], ["İzolasyon", i.izolasyon], ["Otomatik komut", i.otomatik_komut],
      ]);
    },
  },
  "/context": {
    aciklama: "Model yeteneği ve bağlam boyutu",
    calistir: async () => {
      const y = await api("/api/model/yetenek");
      bilgiPenceresi("Bağlam", Object.entries(y).map(([k, v]) => [k, String(v)]));
    },
  },
  "/model": { aciklama: "Model ve sağlayıcı seçimi", calistir: () => ayarlarAc("ai") },
  "/config": { aciklama: "Ayarlar", calistir: () => ayarlarAc("ai") },
  "/effort": { aciklama: "Düşünme seviyesi (Ayarlar)", calistir: () => ayarlarAc("ai") },
  "/memory": { aciklama: "Hafıza notları", calistir: () => ayarlarAc("hafiza") },
  "/hooks": { aciklama: "Hook'lar", calistir: () => ayarlarAc("hooks") },
  "/mcp": { aciklama: "MCP bağlayıcıları", calistir: () => ayarlarAc("mcp") },
  "/plugin": { aciklama: "Plugin'ler", calistir: () => ayarlarAc("plugin") },
  "/permissions": { aciklama: "Proje, mod ve izin kapsamı", calistir: () => projeAc() },
  "/diff": { aciklama: "Çalışma ağacı diff'i", calistir: () => diffGoster() },
  "/review": { aciklama: "Diff'i kod review'dan geçirir (/review derin: güvenlik + doğruluk geçişleri)", calistir: (arg) => reviewYap(arg === "derin") },
  "/agents": { aciklama: "Ajan görevleri sayfası", calistir: () => git("gorevler") },
  "/browser": {
    aciklama: "Tarayıcı durumu; /browser kapat: acil durdurma",
    calistir: async (arg) => {
      if (arg === "kapat") { await api("/api/tarayici/kapat", { method: "POST" }); bildir("Tarayıcı kapatıldı.", "basari", 2000); return; }
      const d = await api("/api/tarayici");
      bilgiPenceresi("Tarayıcı", [["Durum", d.acik ? "açık" : "kapalı"], ["Playwright", d.playwright ? "kurulu" : "yok (pip install playwright)"], ["Ayar", durum.ayarlar?.tarayici_acik ? "açık" : "kapalı (Ayarlar > AI Ayarları)"]]);
    },
  },
  "/akis": { aciklama: "İş akışları: listele, JSON ile başlat, onaydan sonra devam", calistir: () => akisPenceresi() },
  "/goal": {
    aciklama: "/goal <hedef>: ajan görevi başlatır",
    calistir: async (arg) => {
      if (!arg) { bildir("Kullanım: /goal <hedef>", "uyari"); return; }
      await api("/api/gorevler", { method: "POST", govde: { hedef: arg } });
      git("gorevler");
      bildir("Görev başlatıldı.", "basari", 1500);
    },
  },
  "/clear": {
    aciklama: "Bu sohbetin mesajlarını siler (hafızaya dokunmaz)",
    calistir: async () => {
      if (!durum.oturumId) return;
      await api(`/api/oturumlar/${durum.oturumId}/temizle`, { method: "POST" });
      document.querySelector(`.oturum[data-id="${durum.oturumId}"]`)?.click();
    },
  },
  "/compact": { aciklama: "Ajan görevlerinde bağlam dolunca otomatik özetlenir", calistir: () => bildir("Özetleme ajan görevlerinde otomatik; sohbet için henüz elle özet yok.", "bilgi") },
};

const HENUZ_YOK = ["/cost", "/resume", "/rewind", "/loop", "/schedule", "/doctor"];

// Is akislari (A8.6): adimlar yalniz "ajan" ya da "komut"; kod calistirma yok.
const AKIS_ORNEK = JSON.stringify({ ad: "duzelt ve test et", adimlar: [
  { id: "duzelt", tur: "ajan", hedef: "testleri gecirecek duzeltmeyi yap" },
  { id: "test", tur: "komut", komut: "python -m pytest -q", bagimli: ["duzelt"], tekrar: 1 },
] }, null, 1);
const AKIS_TR = { bekliyor: "bekliyor", calisiyor: "çalışıyor", onay_bekliyor: "onay bekliyor", basarili: "başarılı", basarisiz: "başarısız", atlandi: "atlandı" };

function akisPenceresi() {
  const kap = document.createElement("div");
  kap.className = "diff-modal";
  const ciz = async () => {
    let liste = [];
    try { liste = (await api("/api/akislar")).akislar; } catch (e) { bildir(e.message, "hata"); }
    kap.innerHTML = `<div class="ayar-not">Adım türleri: <code>ajan</code> (hedef) ve <code>komut</code>. <code>bagimli</code>, <code>kosul</code> ({adim, durum}) ve <code>tekrar</code> (en fazla 3) kullanılabilir. Komutlar izin kurallarından geçer; onay isteyen komutta akış durur.</div>
      <textarea class="alan" rows="9" aria-label="Akış tanımı (JSON)">${kacir(AKIS_ORNEK)}</textarea>
      <div class="dugme-sira"><button class="btn ana" data-baslat>Başlat</button><button class="btn" data-yenile>Yenile</button></div>
      ${liste.map((a) => `<div class="kart"><div class="kart-baslik"><b>${kacir(a.ad)}</b><span class="rozet">${kacir(AKIS_TR[a.durum] || a.durum)}</span></div>
        <ul class="plan-liste">${a.adimlar.map((x) => `<li>${kacir(x.id)} <code>${kacir(x.tur)}</code> <span class="soluk kucuk">${kacir(AKIS_TR[x.durum] || x.durum)}${x.deneme > 1 ? ` · ${kacir(x.deneme)} deneme` : ""}${x.sonuc ? ` · ${kacir(x.sonuc.slice(0, 120))}` : ""}</span></li>`).join("")}</ul>
        ${a.durum === "onay_bekliyor" ? `<button class="btn" data-devam="${kacir(a.id)}">Onayladım, devam et</button>` : ""}</div>`).join("") || '<div class="soluk">Henüz akış yok.</div>'}`;
    kap.querySelector("[data-baslat]").onclick = async () => {
      let veri;
      try { veri = JSON.parse(kap.querySelector("textarea").value); } catch { bildir("Geçersiz JSON.", "hata"); return; }
      try { await api("/api/akislar", { method: "POST", govde: veri }); bildir("Akış başladı.", "basari", 1500); setTimeout(ciz, 800); } catch (e) { bildir(e.message, "hata"); }
    };
    kap.querySelector("[data-yenile]").onclick = ciz;
    kap.querySelectorAll("[data-devam]").forEach((b) => {
      b.onclick = async () => { try { await api(`/api/akislar/${b.dataset.devam}/devam`, { method: "POST" }); setTimeout(ciz, 800); } catch (e) { bildir(e.message, "hata"); } };
    });
  };
  modal({ baslik: "İş akışları", icerik: kap, genis: true, dugmeler: [{ metin: "Kapat" }] });
  ciz();
}

function yardim() {
  const satirlar = Object.entries(KOMUTLAR).map(([k, v]) => [k, v.aciklama]);
  satirlar.push(["Henüz yok", HENUZ_YOK.join(" ")]);
  bilgiPenceresi("Komutlar", satirlar);
}

/** Metin bir komutsa calistirir ve true doner; degilse false (normal mesaj). */
export function komutMu(metin) {
  if (!metin.startsWith("/")) return false;
  const [ad, ...kalan] = metin.split(/\s+/);
  const k = KOMUTLAR[ad.toLowerCase()];
  if (k) {
    Promise.resolve(k.calistir(kalan.join(" ").trim())).catch((e) => bildir(e.message, "hata"));
    return true;
  }
  if (HENUZ_YOK.includes(ad.toLowerCase())) {
    bildir(`${ad} henüz yok (ilgili servis sonraki aşamalarda).`, "uyari");
    return true;
  }
  return false; // bilinmeyen /... normal mesaj gider (or. yol)
}
