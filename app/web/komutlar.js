// Slash komut kaydi (A6.3). Komutlar YEREL calisir, modele mesaj olarak gitmez.
// Kayitli her komut gercek is yapar; bilinmeyen /... normal mesaj olarak gider.
import { ayarlarAc } from "./ayarlar.js";
import { diffAc } from "./gorevler.js";
import { diffGoster, reviewYap } from "./inceleme.js";
import { kacir } from "./md.js";
import { $, $$, api, bildir, durum, el, modal, oturumBasligi, sayi } from "./ortak.js";
import { projeAc, projeDurumu, projeYenile } from "./proje.js";
import { maliyetPanosuAc } from "./sagpanel.js";
import { ozelKomutListesi, pluginKomutuMu, uzantiKomutlariniYukle, uzantiKomutuMu } from "./uzantilar.js";

// Bu sohbete bagli ajan gorevleri (sohbet.js ile ayni localStorage kaydi; dongusel import yok)
function sohbetRunlari() {
  try { return JSON.parse(localStorage.getItem("ajanRunlari") || "{}")[durum.oturumId] || []; } catch { return []; }
}
const oturumaGit = (id) => document.querySelector(`.oturum[data-id="${id}"]`)?.click();

const INIT_ISTEMI = `Bu kod tabanını incele ve proje kökünde CLAUDE.md dosyasını oluştur (varsa oku ve eksiklerini tamamla).
Dosya, bu projede çalışacak bir yapay zeka ajanına yol gösterecek. Yalnız koddan ve yapılandırma dosyalarından DOĞRULADIĞIN bilgileri yaz:
- Projenin amacı ve kullanılan teknolojiler (tek paragraf)
- Kurulum, çalıştırma, test, lint ve derleme komutları (gerçekten var olanlar)
- Klasör yapısı ve önemli dosyalar; mimarinin ana hatları
- Kod stili ve bu projeye özgü kurallar (README, AGENTS.md, .cursorrules gibi dosyalar varsa onlardan)
Genel geçer öğütler yazma; kısa ve somut tut. Bitirmeden önce dosyayı geri okuyup doğrula.`;

let sayfayaGit = (hedef) => document.querySelector(`[data-git="${hedef}"]`)?.click();
export function komutlarKur({ git } = {}) {
  if (git) sayfayaGit = git;
}

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
  "/uzanti": { aciklama: "Uzantılar (Mods)", calistir: () => ayarlarAc("uzanti") },
  "/permissions": { aciklama: "Proje, mod ve izin kapsamı", calistir: () => projeAc() },
  "/diff": { aciklama: "Çalışma ağacı diff'i", calistir: () => diffGoster() },
  "/review": { aciklama: "Diff'i kod review'dan geçirir (/review derin: güvenlik + doğruluk geçişleri)", calistir: (arg) => reviewYap(arg === "derin") },
  "/security-review": { aciklama: "Diff'i güvenlik + doğruluk odaklı ayrı geçişlerle inceler", calistir: () => reviewYap(true) },
  "/init": {
    aciklama: "Kod tabanını inceleyip CLAUDE.md oluşturur (proje açık olmalı)",
    calistir: (arg, gonder) => {
      if (!projeDurumu.aktif || !gonder) return bildir("/init için önce bir proje aç.", "uyari");
      return gonder(arg ? `${INIT_ISTEMI}\n\nEk istek: ${arg}` : INIT_ISTEMI);
    },
  },
  "/add-dir": {
    aciklama: "/add-dir <klasör>: açık projeye ek klasör yetkisi verir",
    calistir: async (arg) => {
      if (!projeDurumu.aktif) return bildir("Önce bir proje aç.", "uyari");
      if (!arg) return bildir("Kullanım: /add-dir <klasör yolu>", "uyari");
      await api(`/api/projeler/${projeDurumu.aktif.id}/klasor`, { method: "POST", govde: { yol: arg } });
      await projeYenile();
      return bildir("Klasör yetkisi eklendi.", "basari", 2000);
    },
  },
  "/cost": { aciklama: "Bu sohbetin kullanımı: token, model çağrısı, süre", calistir: () => maliyet() },
  "/usage": { aciklama: "/cost ile aynı", calistir: () => maliyet() },
  "/maliyet": { aciklama: "Maliyet ve tasarruf panosu: günlük/haftalık harcama ve model dökümü", calistir: () => maliyetPanosuAc() },
  "/resume": { aciklama: "/resume [arama]: önceki bir sohbete dön", calistir: (arg) => devamEt(arg) },
  "/rewind": { aciklama: "Checkpoint'ler: ajanın dosya değişikliklerini geri al", calistir: () => geriSar() },
  "/todos": { aciklama: "Bu sohbetteki ajanın güncel planı", calistir: () => yapilacaklar() },
  "/bashes": {
    aciklama: "Arka plan komutları",
    calistir: async () => {
      const { isler } = await api("/api/komutlar");
      bilgiPenceresi("Arka plan komutları", isler.length ? isler.map((i) => [`${i.id} ${i.komut.slice(0, 70)}`, `${i.durum}${i.cikis_kodu == null ? "" : ` · çıkış ${i.cikis_kodu}`}`]) : [["Yok", "Çalışan ya da biten komut yok"]]);
    },
  },
  "/rename": {
    aciklama: "/rename <ad>: bu sohbeti yeniden adlandırır",
    calistir: async (arg) => {
      if (!durum.oturumId || !arg) return bildir("Kullanım: /rename <yeni ad> (açık bir sohbette)", "uyari");
      const o = await api(`/api/oturumlar/${durum.oturumId}`, { method: "PATCH", govde: { baslik: arg } });
      $("#sayfa-basligi").textContent = o.baslik;
      document.dispatchEvent(new Event("oturumlar-degisti"));
      return undefined;
    },
  },
  "/export": { aciklama: "Sohbeti Markdown dosyası olarak indirir (ajan görevleriyle birlikte)", calistir: () => disaAktar() },
  "/output-style": { aciklama: "Çıktı stili ve ayrıntı düzeyi (Ayarlar > Kod)", calistir: () => ayarlarAc("kod") },
  "/agents": { aciklama: "Ajan görevleri sayfası", calistir: () => sayfayaGit("gorevler") },
  "/browser": {
    aciklama: "Tarayıcı durumu; /browser kapat: acil durdurma",
    calistir: async (arg) => {
      if (arg === "kapat") { await api("/api/tarayici/kapat", { method: "POST" }); bildir("Tarayıcı kapatıldı.", "basari", 2000); return; }
      const d = await api("/api/tarayici");
      bilgiPenceresi("Tarayıcı", [["Durum", d.acik ? "açık" : "kapalı"], ["Playwright", d.playwright ? "kurulu" : "yok (pip install playwright)"], ["Ayar", durum.ayarlar?.tarayici_acik ? "açık" : "kapalı (Ayarlar > AI Ayarları)"]]);
    },
  },
  "/masaustu": {
    aciklama: "/masaustu durdur | devam: masaüstü kontrolünü acil durdurur ya da açar",
    calistir: async (arg) => {
      const islem = arg === "devam" ? "devam" : "durdur";
      await api(`/api/masaustu/${islem}`, { method: "POST" });
      bildir(islem === "durdur" ? "Masaüstü kontrolü durduruldu." : "Masaüstü kontrolü açıldı.", "basari", 2000);
    },
  },
  "/doctor": {
    aciklama: "Kurulum tanısı (llama.cpp, modeller, git, rg, Playwright...)",
    calistir: async () => {
      const { kontroller } = await api("/api/doctor");
      const isaret = { tamam: "✓", uyari: "!", hata: "✗", bilgi: "·" };
      bilgiPenceresi("Tanı", kontroller.map((c) => [`${isaret[c.durum] || ""} ${c.ad}`, `${c.ayrinti}${c.oneri ? ` - ${c.oneri}` : ""}`]));
    },
  },
  "/schedule": {
    aciklama: "Zamanlanmış görev: /schedule 60 <hedef> | /schedule 09:00 <hedef> | /schedule sil <id> (yalnız uygulama açıkken çalışır)",
    calistir: async (arg = "") => {
      const [ilk, ...kalan] = arg.trim().split(/\s+/);
      if (ilk === "sil" && kalan[0]) {
        await api(`/api/zamanlamalar/${encodeURIComponent(kalan[0])}`, { method: "DELETE" });
        return bildir("Zamanlama silindi.", "basari");
      }
      if (ilk && kalan.length) {
        const gunluk = /^\d{1,2}:\d{2}$/.test(ilk);
        if (!gunluk && !/^\d+$/.test(ilk)) return bildir("Biçim: /schedule <dakika|SS:DD> <hedef>", "hata");
        const hedef = kalan.join(" ");
        const veri = gunluk
          ? { ad: hedef.slice(0, 60), hedef, tur: "gunluk", saat: ilk.padStart(5, "0") }
          : { ad: hedef.slice(0, 60), hedef, tur: "aralik", aralik_dk: Number(ilk) };
        const z = await api("/api/zamanlamalar", { method: "POST", govde: veri });
        return bildir(`Zamanlandı (${z.id}). Uygulama kapalıyken çalışmaz.`, "basari");
      }
      const { zamanlamalar, gecmis } = await api("/api/zamanlamalar");
      const satirlar = zamanlamalar.map((z) => [`${z.id} ${z.aktif ? "" : "(kapalı) "}${z.ad}`,
        z.tur === "gunluk" ? `her gün ${z.saat} ${z.saat_dilimi}` : `her ${z.aralik_dk} dk`]);
      gecmis.slice(-8).reverse().forEach((t) => satirlar.push([`  ${t.plan.slice(0, 16).replace("T", " ")} UTC`, t.durum]));
      bilgiPenceresi("Zamanlamalar (yalnız uygulama açıkken)", satirlar.length ? satirlar : [["Yok", "/schedule 60 testleri çalıştır"]]);
    },
  },
  "/uzak": {
    aciklama: "Telefondan erişim, Tailscale üzerinden (varsayılan kapalı): /uzak | /uzak ac | /uzak kapat | /uzak kod [tam|izleyici|operator|onaylayici] | /uzak iptal <cihaz>",
    calistir: async (arg = "") => {
      const [islem, deger] = arg.trim().split(/\s+/);
      if (islem === "ac") { await api("/api/uzak/ac", { method: "POST" }); bildir("Uzak erişim açık (yalnız TLS).", "basari"); }
      else if (islem === "kapat") { await api("/api/uzak/kapat", { method: "POST" }); return bildir("Uzak erişim kapatıldı.", "basari"); }
      else if (islem === "kod") {
        const k = await api("/api/uzak/kod", { method: "POST", govde: { rol: deger || "tam" } });
        const d = await api("/api/uzak");
        return bilgiPenceresi("Eşleşme kodu (5 dk, tek kullanımlık)", [["Kod", `${k.kod.slice(0, 4)}-${k.kod.slice(4)}`], ["Rol", k.rol],
          ["Adres", d.adresler.join("  ") || "-"], ["Sertifika parmak izi", d.parmak_izi], ["Durum", d.acik ? "açık" : "KAPALI: önce /uzak ac"]]);
      } else if (islem === "iptal" && deger) { await api(`/api/uzak/cihaz/${encodeURIComponent(deger)}`, { method: "DELETE" }); return bildir("Cihaz eşleşmesi iptal edildi.", "basari"); }
      const d = await api("/api/uzak");
      const satirlar = [["Durum", d.acik ? "açık" : "kapalı"], ["Ağ", d.ag === "tailscale" ? (d.tailscale_yok ? "Tailscale bağlı değil" : "yalnız Tailscale") : "yerel ağ"], ["Adres", d.adresler.join("  ") || "-"], ["Parmak izi", d.parmak_izi]];
      d.cihazlar.forEach((c) => satirlar.push([`${c.id} ${c.ad}`, `${c.rol}${c.iptal ? " (iptal)" : ""}`]));
      bilgiPenceresi("Uzak erişim", satirlar);
    },
  },
  "/akis": { aciklama: "İş akışları: /akis [şablon_id anahtar=değer] — listele, şablon veya JSON ile başlat", calistir: (arg) => (arg ? akisSablonHizli(arg) : akisPenceresi()) },
  "/goal": {
    aciklama: "/goal <hedef>: ajan görevi başlatır",
    calistir: async (arg) => {
      if (!arg) { bildir("Kullanım: /goal <hedef>", "uyari"); return; }
      await api("/api/gorevler", { method: "POST", govde: { hedef: arg } });
      sayfayaGit("gorevler");
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
  "/compact": {
    aciklama: "Sohbetin eski mesajlarını özetleyip bağlamı boşaltır (ajan görevleri kendiliğinden özetler)",
    calistir: async () => {
      if (!durum.oturumId) return bildir("Özetlenecek açık sohbet yok.", "uyari");
      if (sohbetRunlari().length) return bildir("Ajan sohbetinde bağlam dolunca kendiliğinden özetlenir; önceki turlar sonraki göreve özet olarak taşınır.", "bilgi");
      bildir("Sohbet özetleniyor…", "bilgi", 2500);
      const r = await api(`/api/oturumlar/${durum.oturumId}/ozetle`, { method: "POST" });
      oturumaGit(durum.oturumId);
      return bildir(`${r.ozetlenen} mesaj özetlendi.`, "basari", 2500);
    },
  },
  "/loop": {
    aciklama: "/loop <dakika> <hedef>: görevi aralıkla yineler (= /schedule; yalnız uygulama açıkken). /loop: listele",
    calistir: (arg = "") => {
      const ilk = arg.trim().split(/\s+/)[0];
      if (ilk && ilk !== "sil" && !/^\d+$/.test(ilk)) return bildir("Biçim: /loop <dakika> <hedef> | /loop sil <id>", "hata");
      return KOMUTLAR["/schedule"].calistir(arg);
    },
  },
};

async function maliyet() {
  const kayitlar = sohbetRunlari();
  const runlar = (await Promise.all(kayitlar.map((k) => api(`/api/gorevler/${k.run}`).catch(() => null)))).filter(Boolean);
  const satirlar = [];
  let token = 0;
  let cagri = 0;
  let sure = 0;
  for (const r of runlar) {
    token += r.kullanim.token; cagri += r.kullanim.model_cagrisi; sure += r.kullanim.sure_sn;
    satirlar.push([`${r.hedef.slice(0, 60)}`, `${sayi(r.kullanim.token, 0)} token · ${r.kullanim.model_cagrisi} çağrı · ${r.kullanim.adim} adım · ${sayi(r.kullanim.sure_sn, 0)} sn`]);
  }
  if (durum.oturumId) {
    const o = await api(`/api/oturumlar/${durum.oturumId}`).catch(() => null);
    const cevaplar = (o?.mesajlar || []).filter((m) => m.rol === "asistan" && m.istatistik);
    if (cevaplar.length) {
      const t = cevaplar.reduce((a, m) => a + (m.istatistik.token || 0) + (m.istatistik.prompt_token || 0), 0);
      const sn = cevaplar.reduce((a, m) => a + (m.istatistik.sure_sn || 0), 0);
      token += t; cagri += cevaplar.length; sure += sn;
      satirlar.push(["Sohbet mesajları", `${sayi(t, 0)} token · ${cevaplar.length} cevap · ${sayi(sn, 0)} sn`]);
    }
  }
  satirlar.unshift(["Toplam", `${sayi(token, 0)} token · ${cagri} model çağrısı · ${sayi(sure, 0)} sn`]);
  satirlar.push(["Not", "Ajan token'ları tahminidir. Yerel model ücretsizdir; OpenRouter ücreti sağlayıcı panelinde görünür."]);
  bilgiPenceresi("Kullanım", satirlar);
}

async function devamEt(arama = "") {
  const liste = await api(`/api/oturumlar${arama ? `?q=${encodeURIComponent(arama)}` : ""}`);
  const kap = el(`<div class="komut-liste">${liste.slice(0, 40).map((o) => `<button class="btn" data-oturum="${kacir(o.id)}"><span>${kacir(o.baslik)}</span>
    <span class="soluk kucuk">${kacir((o.guncelleme || "").replace("T", " ").slice(0, 16))} · ${kacir(o.mesaj_sayisi)} mesaj</span></button>`).join("") || '<div class="soluk">Sohbet bulunamadı.</div>'}</div>`);
  const m = modal({ baslik: "Sohbete devam et", icerik: kap, dugmeler: [{ metin: "Kapat" }] });
  $$("[data-oturum]", kap).forEach((b) => {
    b.onclick = () => {
      m.kapat();
      if (!document.querySelector(`.oturum[data-id="${b.dataset.oturum}"]`)) return bildir("Sohbet kenar çubuğunda görünmüyor; aramayı temizleyip tekrar dene.", "uyari");
      return oturumaGit(b.dataset.oturum);
    };
  });
}

async function geriSar() {
  const { checkpointler } = await api("/api/checkpointler");
  const kap = el(`<div class="komut-liste"><div class="ayar-not">Her satır ajanın yaptığı bir dosya değişikliğidir. Açınca farkı görür, tamamını ya da seçtiğin blokları geri alabilirsin. Sonradan elle değiştirdiğin dosyalara dokunulmaz.</div>
    ${checkpointler.map((c) => `<button class="btn" data-cp="${kacir(c.id)}"><span>${kacir((c.aciklama || c.id).slice(0, 90))}</span>
      <span class="soluk kucuk">${kacir((c.zaman || "").replace("T", " ").slice(0, 16))} · ${kacir((c.dosyalar || []).length)} dosya${c.geri_alindi ? " · geri alındı" : ""}</span></button>`).join("") || '<div class="soluk">Henüz checkpoint yok.</div>'}</div>`);
  modal({ baslik: "Geri sar (checkpoint'ler)", icerik: kap, genis: true, dugmeler: [{ metin: "Kapat" }] });
  $$("[data-cp]", kap).forEach((b) => { b.onclick = () => diffAc(b.dataset.cp); });
}

async function yapilacaklar() {
  const son = sohbetRunlari().at(-1);
  if (!son) return bildir("Bu sohbette ajan görevi yok.", "uyari");
  const r = await api(`/api/gorevler/${son.run}`);
  const isaret = { tamam: "✓", suruyor: "▸", atlandi: "–", bekliyor: "·" };
  return bilgiPenceresi("Plan", (r.plan || []).length ? r.plan.map((p) => [`${isaret[p.durum] || "·"} ${p.baslik}`, p.kanit || p.durum]) : [["Plan yok", "Ajan henüz plan yazmadı"]]);
}

async function disaAktar() {
  if (!durum.oturumId) return bildir("Dışa aktarılacak açık sohbet yok.", "uyari");
  const r = await fetch(`/api/oturumlar/${durum.oturumId}/disa-aktar?bicim=md`, { headers: oturumBasligi() });
  if (!r.ok) throw new Error(`Dışa aktarılamadı (${r.status})`);
  let metin = await r.text();
  const runlar = (await Promise.all(sohbetRunlari().map((k) => api(`/api/gorevler/${k.run}`).catch(() => null)))).filter(Boolean);
  for (const g of runlar) {
    metin += `\n## kullanici\n${g.hedef}\n\n## ajan (${g.durum})\n${g.sonuc?.ozet || g.hata || ""}\n`;
    const adimlar = g.adimlar.filter((a) => a.arac !== "plan_guncelle").map((a) => `- ${a.no}. ${a.arac} ${a.dosya || a.argumanlar?.komut || a.argumanlar?.yol || ""} (${a.durum})`);
    if (adimlar.length) metin += `\n${adimlar.join("\n")}\n`;
  }
  const url = URL.createObjectURL(new Blob([metin], { type: "text/markdown" }));
  Object.assign(document.createElement("a"), { href: url, download: `sohbet-${durum.oturumId}.md` }).click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
  return bildir("Sohbet indirildi.", "basari", 1500);
}

/** "/" onerileri: yerlesik + uzanti + ozel/plugin komutlari. */
export function komutListesi() {
  const yerlesik = Object.entries(KOMUTLAR).map(([ad, k]) => ({ ad, aciklama: k.aciklama }));
  const ozel = ozelKomutListesi().map((k) => ({
    ad: `/${k.komut}`,
    aciklama: `${k.aciklama || ""}${k.ipucu ? ` ${k.ipucu}` : ""} (${k.plugin ? `plugin: ${k.plugin}` : k.kaynak === "proje" ? "proje komutu" : "kullanıcı komutu"})`.trim(),
  }));
  return [...yerlesik, ...ozel.filter((o) => !KOMUTLAR[o.ad])];
}

// Is akislari (A8.6): adimlar yalniz "ajan" ya da "komut"; kod calistirma yok.
const AKIS_ORNEK = JSON.stringify({ ad: "duzelt ve test et", adimlar: [
  { id: "duzelt", tur: "ajan", hedef: "testleri gecirecek duzeltmeyi yap" },
  { id: "test", tur: "komut", komut: "python -m pytest -q", bagimli: ["duzelt"], tekrar: 1 },
] }, null, 1);
const AKIS_TR = { bekliyor: "bekliyor", calisiyor: "çalışıyor", onay_bekliyor: "onay bekliyor", basarili: "başarılı", basarisiz: "başarısız", atlandi: "atlandı" };

async function akisSablonHizli(arg) {
  const metin = arg.trim();
  const bosluk = metin.search(/\s/);
  const sid = bosluk < 0 ? metin : metin.slice(0, bosluk);
  const kalan = bosluk < 0 ? "" : metin.slice(bosluk + 1).trim();
  const parametreler = {};
  if (kalan) {
    const ciftler = [...kalan.matchAll(/([a-zA-Z0-9_-]+)=("[^"]*"|'[^']*'|\S+)/g)];
    if (ciftler.length) {
      for (const m of ciftler) {
        let val = m[2];
        if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
          val = val.slice(1, -1);
        }
        parametreler[m[1]] = val;
      }
    } else {
      try {
        const { sablonlar } = await api("/api/akis-sablonlari");
        const s = sablonlar.find((x) => x.id === sid);
        if (s?.parametreler?.length) parametreler[s.parametreler[0]] = kalan;
      } catch { /* sunucu dogrulamasi bildirir */ }
    }
  }
  try {
    await api(`/api/akis-sablonlari/${encodeURIComponent(sid)}/calistir`, { method: "POST", govde: { parametreler } });
    bildir(`Şablon başlatıldı: ${sid}`, "basari", 2000);
  } catch (e) {
    bildir(e.message, "hata");
  }
}

function akisPenceresi() {
  const kap = document.createElement("div");
  kap.className = "diff-modal";
  const ciz = async () => {
    let liste = [];
    let sablonlar = [];
    try {
      const [ak, sb] = await Promise.all([api("/api/akislar"), api("/api/akis-sablonlari")]);
      liste = ak.akislar || [];
      sablonlar = sb.sablonlar || [];
    } catch (e) { bildir(e.message, "hata"); }
    kap.innerHTML = `<div class="ayar-not">Adım türleri: <code>ajan</code> (hedef) ve <code>komut</code>. <code>bagimli</code>, <code>kosul</code> ({adim, durum}) ve <code>tekrar</code> (en fazla 3) kullanılabilir. Komutlar izin kurallarından geçer; onay isteyen komutta akış durur.</div>
      <div class="kart-baslik"><b>Hazır ve kayıtlı şablonlar</b></div>
      ${sablonlar.map((s) => `<div class="kart" data-sablon="${kacir(s.id)}">
        <div class="kart-baslik"><b>${kacir(s.ad)}</b><code>${kacir(s.id)}</code>${s.yerlesik ? '<span class="rozet">yerleşik</span>' : ""}</div>
        ${s.aciklama ? `<div class="soluk kucuk">${kacir(s.aciklama)}</div>` : ""}
        <div class="satir" style="flex-wrap:wrap;gap:6px;margin-top:6px">
          ${(s.parametreler || []).map((p) => `<input class="alan" style="max-width:190px" data-sablon-param="${kacir(p)}" value="${kacir(s.varsayilanlar?.[p] || "")}" placeholder="${kacir(p)}">`).join("")}
          <button class="btn ana" data-sablon-calistir="${kacir(s.id)}">Şablonu çalıştır</button>
          ${!s.yerlesik ? `<button class="btn tehlike" data-sablon-sil="${kacir(s.id)}">Sil</button>` : ""}
        </div>
      </div>`).join("") || '<div class="soluk">Henüz şablon yok.</div>'}
      <textarea class="alan" rows="8" aria-label="Akış tanımı (JSON)">${kacir(AKIS_ORNEK)}</textarea>
      <div class="dugme-sira"><button class="btn ana" data-baslat>Başlat</button><button class="btn" data-sablon-kaydet>Şablon olarak kaydet</button><button class="btn" data-yenile>Yenile</button></div>
      ${liste.map((a) => `<div class="kart"><div class="kart-baslik"><b>${kacir(a.ad)}</b><span class="rozet">${kacir(AKIS_TR[a.durum] || a.durum)}</span></div>
        <ul class="plan-liste">${a.adimlar.map((x) => `<li>${kacir(x.id)} <code>${kacir(x.tur)}</code> <span class="soluk kucuk">${kacir(AKIS_TR[x.durum] || x.durum)}${x.deneme > 1 ? ` · ${kacir(x.deneme)} deneme` : ""}${x.sonuc ? ` · ${kacir(x.sonuc.slice(0, 120))}` : ""}</span></li>`).join("")}</ul>
        ${a.durum === "onay_bekliyor" ? `<button class="btn" data-devam="${kacir(a.id)}">Onayladım, devam et</button>` : ""}</div>`).join("") || '<div class="soluk">Henüz akış yok.</div>'}`;
    kap.querySelector("[data-baslat]").onclick = async () => {
      let veri;
      try { veri = JSON.parse(kap.querySelector("textarea").value); } catch { bildir("Geçersiz JSON.", "hata"); return; }
      try { await api("/api/akislar", { method: "POST", govde: veri }); bildir("Akış başladı.", "basari", 1500); setTimeout(ciz, 800); } catch (e) { bildir(e.message, "hata"); }
    };
    kap.querySelector("[data-sablon-kaydet]").onclick = async () => {
      let veri;
      try { veri = JSON.parse(kap.querySelector("textarea").value); } catch { bildir("Geçersiz JSON.", "hata"); return; }
      const sid = veri.id || String(veri.ad || "sablon").toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || `sablon-${Date.now().toString(36)}`;
      const bulunanParam = new Set(veri.parametreler || []);
      for (const a of veri.adimlar || []) {
        for (const metin of [a.hedef || "", a.komut || ""]) {
          for (const m of metin.matchAll(/\{\{([a-zA-Z0-9_-]{1,40})\}\}/g)) bulunanParam.add(m[1]);
        }
      }
      try {
        await api("/api/akis-sablonlari", { method: "POST", govde: { ...veri, id: sid, parametreler: [...bulunanParam] } });
        bildir(`Şablon kaydedildi: ${sid}`, "basari", 2000);
        ciz();
      } catch (e) { bildir(e.message, "hata"); }
    };
    kap.querySelectorAll("[data-sablon-calistir]").forEach((b) => {
      b.onclick = async () => {
        const kart = b.closest("[data-sablon]");
        const parametreler = {};
        kart.querySelectorAll("[data-sablon-param]").forEach((inp) => { parametreler[inp.dataset.sablonParam] = inp.value; });
        try {
          await api(`/api/akis-sablonlari/${encodeURIComponent(b.dataset.sablonCalistir)}/calistir`, { method: "POST", govde: { parametreler } });
          bildir("Şablon akışı başladı.", "basari", 1500);
          setTimeout(ciz, 800);
        } catch (e) { bildir(e.message, "hata"); }
      };
    });
    kap.querySelectorAll("[data-sablon-sil]").forEach((b) => {
      b.onclick = async () => {
        try {
          await api(`/api/akis-sablonlari/${encodeURIComponent(b.dataset.sablonSil)}`, { method: "DELETE" });
          bildir("Şablon silindi.", "basari", 1500);
          ciz();
        } catch (e) { bildir(e.message, "hata"); }
      };
    });
    kap.querySelector("[data-yenile]").onclick = ciz;
    kap.querySelectorAll("[data-devam]").forEach((b) => {
      b.onclick = async () => { try { await api(`/api/akislar/${b.dataset.devam}/devam`, { method: "POST" }); setTimeout(ciz, 800); } catch (e) { bildir(e.message, "hata"); } };
    });
  };
  modal({ baslik: "İş akışları", icerik: kap, genis: true, dugmeler: [{ metin: "Kapat" }] });
  ciz();
}

function yardim() {
  const satirlar = komutListesi().map((k) => [k.ad, k.aciklama]);
  satirlar.push(["Kısayollar", "@ dosya adı tamamlar · !komut kabukta çalıştırır · #not hafızaya ekler"]);
  bilgiPenceresi("Komutlar", satirlar);
}

/** Metin bir komutsa calistirir ve true doner; degilse false (normal mesaj). */
export function komutMu(metin, mesajGonder = null) {
  if (!metin.startsWith("/")) return false;
  const [ad, ...kalan] = metin.split(/\s+/);
  const k = KOMUTLAR[ad.toLowerCase()];
  if (k) {
    // async sarmal: senkron firlatilan hata da bildirim olur
    (async () => k.calistir(kalan.join(" ").trim(), mesajGonder))().catch((e) => bildir(e.message, "hata"));
    return true;
  }
  if (uzantiKomutuMu(ad, kalan.join(" ").trim())) return true; // kurulu uzanti komutu
  if (mesajGonder && pluginKomutuMu(ad, kalan.join(" ").trim(), mesajGonder)) return true; // Claude Code plugin komutu
  return false; // bilinmeyen /... normal mesaj gider (or. yol)
}

uzantiKomutlariniYukle();
