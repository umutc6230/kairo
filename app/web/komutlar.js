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
  "/permissions": { aciklama: "Proje, mod ve izin kapsamı", calistir: () => projeAc() },
  "/diff": { aciklama: "Çalışma ağacı diff'i", calistir: () => diffGoster() },
  "/review": { aciklama: "Diff'i kod review'dan geçirir", calistir: () => reviewYap() },
  "/agents": { aciklama: "Ajan görevleri sayfası", calistir: () => git("gorevler") },
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

const HENUZ_YOK = ["/cost", "/resume", "/rewind", "/plugin", "/browser", "/loop", "/schedule", "/doctor"];

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
