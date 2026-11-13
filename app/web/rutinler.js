// Rutinler (Claude Desktop 'Routines'): zamanlanmis ajan gorevleri, sablonlar, simdi calistir.
// Arka uc: /api/zamanlamalar (yalniz uygulama acikken calisir).
import { kacir } from "./md.js";
import { $, $$, api, bildir, onayla } from "./ortak.js";

const SABLONLAR = [
  { ad: "Günlük kod incelemesi", hedef: "Son 24 saatteki commit'leri incele; riskli değişiklikleri, eksik testleri ve takip edilmesi gerekenleri özetle.", tur: "gunluk", saat: "09:00" },
  { ad: "Bağımlılık kontrolü", hedef: "Eski paketleri, güvenlik yamalarını ve kırıcı değişiklikleri tara; rapor yaz, değişiklik yapma.", tur: "gunluk", saat: "10:00", gunler: [0] },
  { ad: "Kararsız test takibi", hedef: "Test paketini çalıştır; ara sıra geçip kalan testleri bul ve raporla.", tur: "gunluk", saat: "18:00", gunler: [0, 2, 4] },
  { ad: "Sürüm notu taslağı", hedef: "Son etiketten bu yana yapılan değişikliklerden kullanıcıya dönük sürüm notu taslağı yaz.", tur: "gunluk", saat: "17:00", gunler: [4] },
  { ad: "Sistem sağlık kontrolü", hedef: "Projenin testlerini, lint'ini ve derlemesini çalıştır; hataları özetle.", tur: "aralik", aralik_dk: 360 },
  { ad: "TODO taraması", hedef: "Koddaki TODO/FIXME notlarını listele ve önceliklendir.", tur: "gunluk", saat: "08:30", gunler: [0] },
];
const GUN = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"];

function zamanMetni(z) {
  if (z.tur === "bir_kez") return "Bir kez";
  if (z.tur === "aralik") return `Her ${z.aralik_dk >= 60 ? `${z.aralik_dk / 60} saatte` : `${z.aralik_dk} dakikada`} bir`;
  const g = z.gunler || [0, 1, 2, 3, 4, 5, 6];
  const gunler = g.length === 7 ? "Her gün" : g.join() === "0,1,2,3,4" ? "Hafta içi" : g.map((i) => GUN[i]).join(", ");
  return `${gunler} ${z.saat}`;
}

function formAc(on = {}) {
  const kap = $("#rt-form");
  kap.hidden = false;
  kap.innerHTML = `<div class="kart">
    <label class="proje-alan">Ad<input class="alan" id="rt-ad" maxlength="80" value="${kacir(on.ad || "")}" placeholder="gunluk-kod-incelemesi"></label>
    <label class="proje-alan">Talimat<textarea class="alan" id="rt-hedef" rows="3" maxlength="4000" placeholder="Ajanın her çalışmada yapacağı iş">${kacir(on.hedef || "")}</textarea></label>
    <div class="ornekler" id="rt-zaman">${["Şimdi, bir kez", "Elle", "Saatlik", "Günlük", "Hafta içi", "Haftalık"].map((x) => `<button class="ornek" data-z="${x}">${x}</button>`).join("")}</div>
    <div class="satir"><label class="soluk kucuk" for="rt-saat">Saat</label><input class="alan" id="rt-saat" type="time" value="${on.saat || "09:00"}" style="max-width:120px"></div>
    <div class="soluk kucuk">Ne yapsın?</div>
    <div class="ornekler" id="rt-davranis"><button class="ornek" data-d="yap">Benim için yapsın</button><button class="ornek" data-d="bildir">Yalnız bana bildirsin</button></div>
    <label class="proje-alan">Ne zamana kadar? <span class="soluk kucuk">(boş: ben durdurana kadar)</span><input class="alan" id="rt-bitis" maxlength="500" value="${kacir(on.bitis_kosulu || "")}" placeholder="ör. tüm testler geçene kadar / v2 yayınlanana kadar"></label>
    <div class="soluk kucuk">Rutin açık projede çalışır ve yalnız uygulama açıkken tetiklenir. Onay gerektiren adımda durur.</div>
    <div class="dugme-sira"><button class="btn" id="rt-iptal">İptal</button><button class="btn ana" id="rt-kaydet">Oluştur</button></div></div>`;
  let secim = on.tur === "aralik" ? "Saatlik" : on.gunler?.length === 1 ? "Haftalık" : on.gunler?.join() === "0,1,2,3,4" ? "Hafta içi" : "Günlük";
  const isaretle = () => $$("#rt-zaman .ornek").forEach((b) => b.classList.toggle("secili", b.dataset.z === secim));
  $$("#rt-zaman .ornek").forEach((b) => { b.onclick = () => { secim = b.dataset.z; isaretle(); }; });
  isaretle();
  let davranis = on.davranis || "yap";
  const dIsaretle = () => $$("#rt-davranis .ornek").forEach((b) => b.classList.toggle("secili", b.dataset.d === davranis));
  $$("#rt-davranis .ornek").forEach((b) => { b.onclick = () => { davranis = b.dataset.d; dIsaretle(); }; });
  dIsaretle();
  $("#rt-iptal").onclick = () => { kap.hidden = true; };
  $("#rt-kaydet").onclick = async () => {
    const veri = { ad: $("#rt-ad").value.trim(), hedef: $("#rt-hedef").value.trim(), saat: $("#rt-saat").value || "09:00" };
    if (!veri.ad || !veri.hedef) return bildir("Ad ve talimat gerekli.", "uyari");
    Object.assign(veri, { davranis, bitis_kosulu: $("#rt-bitis").value.trim() });
    if (secim === "Şimdi, bir kez") veri.tur = "bir_kez";
    else if (secim === "Saatlik") Object.assign(veri, { tur: "aralik", aralik_dk: on.aralik_dk || 60 });
    else Object.assign(veri, { tur: "gunluk", gunler: { "Günlük": [0, 1, 2, 3, 4, 5, 6], "Hafta içi": [0, 1, 2, 3, 4], "Haftalık": on.gunler?.length === 1 ? on.gunler : [0] }[secim] || [0, 1, 2, 3, 4, 5, 6] });
    if (secim === "Elle") veri.aktif = false;
    try { await api("/api/zamanlamalar", { method: "POST", govde: veri }); kap.hidden = true; bildir("Rutin oluşturuldu.", "basari", 1500); rutinleriYukle(); } catch (e) { bildir(e.message, "hata"); }
  };
}

export async function rutinleriYukle() {
  const kap = $("#rt-liste");
  try {
    const { zamanlamalar, gecmis } = await api("/api/zamanlamalar");
    kap.innerHTML = zamanlamalar.map((z) => {
      const son = [...gecmis].reverse().find((g) => g.zamanlama === z.id);
      return `<div class="secenek-kart ${z.aktif ? "" : "pasif"}" data-rt="${z.id}"><div style="flex:1">
        <div class="ust"><b>${kacir(z.ad)}</b> <span class="soluk kucuk">${kacir(z.aktif ? zamanMetni(z) : "Elle")}</span></div>
        <div class="alt">${kacir(z.hedef.slice(0, 160))}</div>
        <div class="soluk kucuk">${z.davranis === "bildir" ? "Yalnız bildirir" : "Yapar"} · ${z.tamamlandi ? `Hedefe ulaştı (${kacir(z.tamamlandi.slice(0, 10))})` : z.bitis_kosulu ? `${kacir(z.bitis_kosulu)} olana kadar` : "Durdurana kadar"}</div>${son ? `<div class="soluk kucuk">Son: ${kacir(son.durum || "")}</div>` : ""}</div>
        <button class="btn" data-is="calistir">Şimdi çalıştır</button><button class="btn" data-is="ac">${z.aktif ? "Duraklat" : "Etkinleştir"}</button><button class="btn tehlike" data-is="sil">Sil</button></div>`;
    }).join("") || '<div class="ayar-not">Henüz rutin yok. Aşağıdaki şablonlardan başlayabilirsin.</div>';
    $$("[data-rt]", kap).forEach((k) => {
      const z = zamanlamalar.find((x) => x.id === k.dataset.rt);
      $$("[data-is]", k).forEach((b) => {
        b.onclick = async () => {
          try {
            if (b.dataset.is === "calistir") { await api(`/api/zamanlamalar/${z.id}/calistir`, { method: "POST" }); bildir("Rutin başlatıldı; Görevler'de izleyebilirsin.", "basari", 2000); }
            else if (b.dataset.is === "ac") await api(`/api/zamanlamalar/${z.id}`, { method: "PATCH", govde: { aktif: !z.aktif } });
            else if (await onayla("Rutini sil", `"${z.ad}" silinsin mi?`, { evet: "Sil", tehlike: true })) await api(`/api/zamanlamalar/${z.id}`, { method: "DELETE" });
            rutinleriYukle();
          } catch (e) { bildir(e.message, "hata"); }
        };
      });
    });
  } catch (e) { kap.innerHTML = `<div class="ayar-not">${kacir(e.message)}</div>`; }
}

export function rutinlerKur() {
  $("#rt-yeni").onclick = () => formAc();
  $("#rt-sablonlar").innerHTML = SABLONLAR.map((s, i) => `<button class="secenek-kart" data-sb="${i}" style="text-align:left"><div><div class="ust"><b>${kacir(s.ad)}</b></div>
    <div class="alt">${kacir(s.hedef)}</div><div class="soluk kucuk">${kacir(zamanMetni(s))}</div></div></button>`).join("");
  $$("[data-sb]").forEach((b) => { b.onclick = () => formAc(SABLONLAR[+b.dataset.sb]); });
}
