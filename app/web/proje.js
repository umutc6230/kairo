// Proje (calisma alani) ve izin kapsami arayuzu. Native dialog YOK: in-app modal.
import { ikonlariYerlestir } from "./ikonlar.js";
import { kacir } from "./md.js";
import { $, api, bildir, durum, el, modal, onayla } from "./ortak.js";

const MOD_TR = {
  sohbet: { ad: "Sohbet", aciklama: "Dosya yazma ve komut yok; yalnız okuma ve sohbet." },
  planla: { ad: "Planla", aciklama: "Salt okunur: inceler, plan önerir, hiçbir değişiklik uygulamaz." },
  onayli: { ad: "Onaylı uygulama", aciklama: "Her yan etkili adım için sizden onay ister." },
  otomatik: { ad: "Politika kapsamında otomatik", aciklama: "Onay istemeden uygular; yine de kök dışına, gizli dosyalara ve dış ağa dokunamaz." },
};
const GUVEN_TR = {
  guvenilir: { ad: "Güvenilir", aciklama: "Projenin kendi AGENTS.md/CLAUDE.md talimatı okunur." },
  sinirli: { ad: "Sınırlı", aciklama: "Proje talimatı okunmaz; araçlar kök içinde çalışır." },
  guvenilmeyen: { ad: "Güvenilmeyen", aciklama: "Yalnız okuma; proje talimatı okunmaz." },
};

export const projeDurumu = { etkin: null, aktif: null, izin: null };

export async function projeYenile() {
  try {
    const [p, izin] = await Promise.all([api("/api/projeler"), api("/api/izinler")]);
    projeDurumu.etkin = p.etkin;
    projeDurumu.aktif = p.aktif;
    projeDurumu.liste = p.alanlar;
    projeDurumu.izin = izin;
  } catch {
    return;
  }
  hapiCiz();
}

function hapiCiz() {
  const hap = $("#proje-hapi");
  if (!hap) return;
  const e = projeDurumu.etkin;
  const izin = projeDurumu.izin || {};
  hap.hidden = false;
  $("#proje-metni").textContent = e ? e.ad : "Proje yok";
  const mod = MOD_TR[izin.mod]?.ad || izin.mod || "";
  $("#proje-mod").textContent = mod;
  hap.classList.toggle("salt-okunur", !!izin.salt_okunur);
  hap.title = `${e?.ad || ""} · ${mod}\nYetkili klasörler:\n${(izin.kokler || []).join("\n")}`;
}

function satir(etiket, deger) {
  return `<div class="izin-satiri"><span class="soluk">${kacir(etiket)}</span><span>${kacir(deger)}</span></div>`;
}

export function projeAc() {
  const govde = el('<div class="proje-modal"></div>');

  const ciz = () => {
    const e = projeDurumu.etkin || {};
    const izin = projeDurumu.izin || {};
    const aktif = projeDurumu.aktif;
    govde.innerHTML = `
      <div class="kutu">
        <div class="kutu-baslik">Etkin kapsam</div>
        ${satir("Çalışma alanı", e.ad || "-")}
        ${satir("Mod", MOD_TR[izin.mod]?.ad || izin.mod || "-")}
        ${satir("Güven", GUVEN_TR[izin.guven]?.ad || izin.guven || "-")}
        ${satir("Değişiklik", izin.salt_okunur ? "Uygulanmaz (salt okunur)" : "Politika kapsamında")}
        ${satir("Proje talimatı", izin.talimat_okunur ? "Okunur" : "Okunmaz")}
        ${satir("Dış ağ", izin.ag_izinli ? "Onayla" : "Kapalı")}
        <div class="izin-satiri"><span class="soluk">Yetkili klasörler</span><span></span></div>
        <ul class="kok-liste">${(izin.kokler || []).map((k) => `<li><code>${kacir(k)}</code></li>`).join("") || "<li class='soluk'>yok</li>"}</ul>
        ${izin.mod_tavani_uygulandi ? `<div class="uyari-kutu kucuk">Yönetilen politika modu <b>${kacir(izin.mod)}</b> ile sınırlıyor.</div>` : ""}
        <div class="uyari-kutu kucuk">İzolasyon: <b>${izin.izolasyon === "yok" ? "yok" : "konteyner (ağ kapalı)"}</b> · Otomatik modda komut: <b>${kacir(izin.otomatik_komut || "onay ister")}</b><br>${kacir(izin.izolasyon_notu || "")}</div>
        <label class="proje-alan">Komutlar nerede çalışsın
          <select class="alan" id="izolasyon-sec">
            <option value="yok" ${izin.izolasyon_secimi !== "konteyner" ? "selected" : ""}>Bu bilgisayarda (izolasyon yok, otomatik modda da onay ister)</option>
            <option value="konteyner" ${izin.izolasyon_secimi === "konteyner" ? "selected" : ""}>Konteynerde (Podman/Docker: ağ kapalı, yalnız proje klasörü)</option>
          </select>
        </label>
        ${izin.izolasyon_secimi === "konteyner" && !izin.izolasyon_kullanilabilir ? '<div class="uyari-kutu kucuk">Konteyner şu an kullanılamıyor; komutlar çalıştırılmaz (izolasyonsuz çalışmaya sessizce dönülmez).</div>' : ""}
      </div>

      <div class="kutu">
        <div class="kutu-baslik">Proje aç</div>
        <label class="proje-alan">Klasör yolu
          <input class="alan" id="proje-yol" type="text" placeholder="C:\\Users\\umuti\\Projects\\ornek" spellcheck="false">
        </label>
        <label class="proje-alan">Güven
          <select class="alan" id="proje-guven">${Object.entries(GUVEN_TR).map(([k, v]) => `<option value="${k}" ${k === "sinirli" ? "selected" : ""}>${kacir(v.ad)} - ${kacir(v.aciklama)}</option>`).join("")}</select>
        </label>
        <button class="btn ana" id="btn-proje-ac">Aç</button>
      </div>

      ${aktif ? `<div class="kutu">
        <div class="kutu-baslik">Aktif proje: ${kacir(aktif.ad)}</div>
        <label class="proje-alan">Mod
          <select class="alan" id="proje-mod-sec">${Object.entries(MOD_TR).map(([k, v]) => `<option value="${k}" ${aktif.mod === k ? "selected" : ""}>${kacir(v.ad)} - ${kacir(v.aciklama)}</option>`).join("")}</select>
        </label>
        <label class="proje-alan">Güven
          <select class="alan" id="proje-guven-sec">${Object.entries(GUVEN_TR).map(([k, v]) => `<option value="${k}" ${aktif.guven === k ? "selected" : ""}>${kacir(v.ad)}</option>`).join("")}</select>
        </label>
        <label class="proje-alan">Ek klasör yetkilendir (kök dışı)
          <input class="alan" id="proje-ek" type="text" placeholder="C:\\...\\baska-klasor" spellcheck="false">
        </label>
        <div class="dugme-sira">
          <button class="btn" id="btn-ek-ekle">Ek klasör ekle</button>
          <button class="btn" id="btn-kok-ekle">İkinci kök ekle</button>
          <button class="btn tehlike" id="btn-proje-kapat">Projeyi kapat</button>
        </div>
      </div>` : ""}

      ${(projeDurumu.liste || []).length ? `<div class="kutu">
        <div class="kutu-baslik">Son projeler</div>
        <ul class="kok-liste">${projeDurumu.liste.map((a) => `<li><button class="bag" data-ac="${kacir(a.kokler[0] || "")}">${kacir(a.ad)}</button> <code class="soluk">${kacir(a.kokler[0] || "")}</code></li>`).join("")}</ul>
      </div>` : ""}`;
    ikonlariYerlestir(govde);
    baglantilariKur();
  };

  const yenile = async () => {
    await projeYenile();
    ciz();
  };

  const sarmala = async (is_) => {
    try {
      await is_();
      await yenile();
    } catch (e) {
      bildir(e.message, "hata");
    }
  };

  function baglantilariKur() {
    $("#izolasyon-sec", govde).onchange = (ev) =>
      sarmala(async () => {
        await api("/api/ayarlar", { method: "PUT", govde: { izolasyon: ev.target.value } });
        bildir("İzolasyon ayarı kaydedildi.");
      });
    $("#btn-proje-ac", govde).onclick = () =>
      sarmala(async () => {
        const yol = $("#proje-yol", govde).value.trim();
        if (!yol) throw new Error("Klasör yolu girin.");
        await api("/api/projeler", { method: "POST", govde: { yol, guven: $("#proje-guven", govde).value } });
        bildir("Proje açıldı.");
      });
    const aktif = projeDurumu.aktif;
    if (!aktif) return;
    $("#proje-mod-sec", govde).onchange = (e) =>
      sarmala(() => api(`/api/projeler/${aktif.id}/mod`, { method: "PUT", govde: { mod: e.target.value } }));
    $("#proje-guven-sec", govde).onchange = (e) =>
      sarmala(() => api(`/api/projeler/${aktif.id}/guven`, { method: "PUT", govde: { guven: e.target.value } }));
    $("#btn-ek-ekle", govde).onclick = () =>
      sarmala(async () => {
        const yol = $("#proje-ek", govde).value.trim();
        if (!yol) throw new Error("Klasör yolu girin.");
        await api(`/api/projeler/${aktif.id}/klasor`, { method: "POST", govde: { yol } });
        bildir("Klasör yetkilendirildi.");
      });
    $("#btn-kok-ekle", govde).onclick = () =>
      sarmala(async () => {
        const yol = $("#proje-ek", govde).value.trim();
        if (!yol) throw new Error("Klasör yolu girin.");
        await api(`/api/projeler/${aktif.id}/kok`, { method: "POST", govde: { yol } });
        bildir("Kök eklendi.");
      });
    $("#btn-proje-kapat", govde).onclick = async () => {
      if (!(await onayla("Projeyi kapat", "Araçlar kişisel klasörlerle sınırlı kapsama döner."))) return;
      sarmala(() => api("/api/projeler/kapat", { method: "POST" }));
    };
    for (const b of govde.querySelectorAll("[data-ac]")) {
      b.onclick = () => sarmala(() => api("/api/projeler", { method: "POST", govde: { yol: b.dataset.ac } }));
    }
  }

  ciz();
  modal({ baslik: "Proje ve izinler", icerik: govde, genis: true, dugmeler: [{ metin: "Kapat" }] });
  yenile();
}

export function projeKur() {
  const hap = $("#proje-hapi");
  if (hap) hap.onclick = projeAc;
  projeYenile();
  durum.proje = projeDurumu;
}
