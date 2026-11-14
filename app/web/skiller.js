// Skill'ler ve talimatlar sayfasi (Claude Code mantigi: CLAUDE.md + skills).
import { ikonlariYerlestir } from "./ikonlar.js";
import { kacir } from "./md.js";
import { $, $$, api, bildir, durum, el, modal, onayla, sayi } from "./ortak.js";

const KAYNAK_AD = { claude: "Claude Code", brain: "Brain", uygulama: "Uygulama" };
let skiller = [];
let filtre = "hepsi";
let ayarYenile = async () => {};

export function skillerKur(cb) {
  ayarYenile = cb;
  $("#s-ara").oninput = listeCiz;
  $$("#s-filtre .ornek").forEach((b) => {
    b.onclick = () => {
      filtre = b.dataset.f;
      $$("#s-filtre .ornek").forEach((x) => x.classList.toggle("secili", x === b));
      listeCiz();
    };
  });
  $("#s-yeni").onclick = yeniSkill;
  $("#s-github").onclick = githubdanEkle;
  $("#t-kaydet").onclick = async () => {
    try {
      await api("/api/talimatlar", { method: "PUT", govde: { metin: $("#t-uygulama").value } });
      bildir("KAIRO.md kaydedildi", "basari");
      talimatlarYukle();
    } catch (e) { bildir(e.message, "hata"); }
  };
  $("#t-uygulama").oninput = () => { $("#t-uygulama-token").textContent = `~${sayi($("#t-uygulama").value.length / 3.3, 0)} token`; };
  const anahtar = (sec, ad) => {
    $(sec).onchange = async (e) => {
      await api("/api/ayarlar", { method: "PUT", govde: { [ad]: e.target.checked } }).catch((x) => bildir(x.message, "hata"));
      await ayarYenile();
      talimatlarYukle();
    };
  };
  anahtar("#t-claude-acik", "claude_talimatlari");
  anahtar("#t-uygulama-acik", "uygulama_talimati");
  anahtar("#s-acik", "skiller_acik");
  $("#t-baglam").onchange = async (e) => {
    try {
      await api("/api/ayarlar", { method: "PUT", govde: { baglam_token: Number(e.target.value) } });
      bildir("Bağlam değişti; model bir sonraki mesajda yeni ayarla açılır.", "basari");
      await ayarYenile();
      talimatlarYukle();
    } catch (x) { bildir(x.message, "hata"); }
  };
}

export async function skillSayfasiYukle() {
  await Promise.all([talimatlarYukle(), skillleriYukle()]);
}

async function talimatlarYukle() {
  let t;
  try { t = await api("/api/talimatlar"); } catch (e) { bildir(e.message, "hata"); return; }
  $("#t-claude-acik").checked = t.claude_acik;
  $("#t-uygulama-acik").checked = t.uygulama_acik;
  $("#s-acik").checked = durum.ayarlar.skiller_acik;
  $("#t-baglam").value = String(t.baglam_token);
  if (document.activeElement !== $("#t-uygulama")) $("#t-uygulama").value = t.uygulama;
  $("#t-uygulama").oninput();
  const toplam = t.claude.reduce((a, k) => a + k.token, 0);
  const kairoToplam = (t.kairo || []).reduce((a, k) => a + k.token, 0);
  $("#t-claude-ozet").textContent = t.claude.length ? `${t.claude.length} dosya · ~${sayi(toplam, 0)} token` : "eklenecek yeni dosya yok";
  // KAIRO.md'nin import ettikleri (kendisi ustteki kutuda); CLAUDE.md ayri ve istege bagli
  kaynaklariCiz($("#t-kairo-liste"), (t.kairo || []).slice(1));
  kaynaklariCiz($("#t-claude-liste"), t.claude);
  const oran = Math.round((((t.claude_acik ? toplam : 0) + (t.uygulama_acik ? kairoToplam : 0)) / t.baglam_token) * 100);
  $("#t-baglam-not").innerHTML = oran > 30
    ? `<span class="rozet sari">talimatlar bağlamın %${oran}'ini kullanıyor</span>`
    : `<span class="rozet">talimatlar bağlamın %${oran}'i</span>`;
}

function kaynaklariCiz(kap, liste) {
  kap.innerHTML = "";
  for (const k of liste) {
    const s = el(`<div class="kaynak-satir"><span data-ikon="dosya"></span><span class="ad">${kacir(k.yol.split(/[\\/]/).pop())}</span>
      <span class="soluk kucuk yol">${kacir(k.yol)}</span><span class="rozet">~${sayi(k.token, 0)} token</span>${k.kisaltildi ? '<span class="rozet sari">kısaltıldı</span>' : ""}
      <button class="btn kucuk">Göster</button></div>`);
    s.querySelector("button").onclick = () => modal({ baslik: k.yol, icerik: `<pre class="duz">${kacir(k.metin)}</pre>`, genis: true });
    kap.append(s);
  }
  ikonlariYerlestir(kap);
}

async function skillleriYukle() {
  try {
    const v = await api("/api/skiller");
    skiller = v.skiller;
    $("#s-kaynaklar").textContent = v.kaynaklar.map((k) => `${KAYNAK_AD[k.kaynak]}: ${k.yol}${k.var ? "" : " (yok)"}`).join("  ·  ");
  } catch (e) { bildir(e.message, "hata"); }
  listeCiz();
}

function listeCiz() {
  const aranan = $("#s-ara").value.toLowerCase();
  const liste = skiller.filter((s) => (filtre === "hepsi" || s.kaynak === filtre)
    && (!aranan || `${s.ad} ${s.aciklama}`.toLowerCase().includes(aranan)));
  $("#s-sayi").textContent = `${liste.length} / ${skiller.length} skill · ${skiller.filter((s) => s.acik).length} açık`;
  const kap = $("#s-liste");
  kap.innerHTML = liste.length ? "" : `<div class="bos-not soluk">Eşleşen skill yok.</div>`;
  for (const s of liste) {
    const r = el(`<div class="skill-satir ${s.acik ? "" : "kapali"}">
      <div class="skill-bilgi"><div class="ust"><b>${kacir(s.ad)}</b><span class="rozet ${s.kaynak === "uygulama" ? "yesil" : ""}">${KAYNAK_AD[s.kaynak]}</span></div>
      <div class="alt soluk">${kacir(s.aciklama)}</div></div>
      <div class="skill-eylem"><button class="ikon-btn" title="Önizle" data-ikon="dosya"></button>
      ${s.silinebilir ? '<button class="ikon-btn sil" title="Sil" data-ikon="cop"></button>' : ""}
      <label class="anahtar" title="Bu skill kullanılsın mı"><input type="checkbox" ${s.acik ? "checked" : ""}><span></span></label></div></div>`);
    r.querySelector('[title="Önizle"]').onclick = () => onizle(s.ad);
    r.querySelector(".sil")?.addEventListener("click", () => sil(s));
    r.querySelector("input").onchange = async (e) => {
      try {
        await api(`/api/skiller/${encodeURIComponent(s.ad)}/durum`, { method: "PUT", govde: { acik: e.target.checked } });
        s.acik = e.target.checked;
        r.classList.toggle("kapali", !s.acik);
        $("#s-sayi").textContent = `${liste.length} / ${skiller.length} skill · ${skiller.filter((x) => x.acik).length} açık`;
        await ayarYenile();
      } catch (x) { bildir(x.message, "hata"); }
    };
    kap.append(r);
  }
  ikonlariYerlestir(kap);
}

async function onizle(ad) {
  try {
    const s = await api(`/api/skiller/${encodeURIComponent(ad)}`);
    modal({ baslik: `${s.ad} · ${KAYNAK_AD[s.kaynak]}`, icerik: `<div class="ayar-not">${kacir(s.yol)}</div><pre class="duz">${kacir(s.icerik)}</pre>`, genis: true });
  } catch (e) { bildir(e.message, "hata"); }
}

async function sil(s) {
  if (!(await onayla("Skill'i sil", `"${s.ad}" uygulamadan silinecek.`, { evet: "Sil", tehlike: true }))) return;
  try {
    await api(`/api/skiller/${encodeURIComponent(s.ad)}`, { method: "DELETE" });
    bildir("Silindi", "basari");
    skillleriYukle();
  } catch (e) { bildir(e.message, "hata"); }
}

function yeniSkill() {
  const form = el(`<div class="ayar-grup" style="gap:10px">
    <div class="ayar-grup"><label>Ad (küçük harf, rakam, -)</label><input class="alan" id="ys-ad" placeholder="fatura-okuma"></div>
    <div class="ayar-grup"><label>Açıklama: model skill'i buna bakarak seçer; ne işe yaradığını ve tetikleyici kelimeleri yaz</label>
      <textarea class="alan" id="ys-aciklama" rows="3" placeholder="Fatura ve hakediş görsellerinden tutar, tarih, firma bilgisini çıkarır. Tetikleyiciler: fatura, hakediş, tutar..."></textarea></div>
    <div class="ayar-grup"><label>Talimat (SKILL.md gövdesi, markdown)</label>
      <textarea class="alan" id="ys-icerik" rows="10" placeholder="# Fatura okuma&#10;1. Önce resmi OCR'la...&#10;2. ..."></textarea></div>
    <div class="ayar-not">Skill, uygulamanın data\\skills klasörüne SKILL.md olarak kaydedilir. Claude Code ve brain skill'leri otomatik bulunur, buradan eklenmez.</div></div>`);
  modal({
    baslik: "Yeni skill",
    icerik: form,
    genis: true,
    dugmeler: [
      { metin: "Vazgeç" },
      {
        metin: "Kaydet",
        tur: "ana",
        eylem: async (kapat) => {
          try {
            await api("/api/skiller", { method: "POST", govde: { ad: $("#ys-ad", form).value, aciklama: $("#ys-aciklama", form).value, icerik: $("#ys-icerik", form).value } });
            bildir("Skill eklendi", "basari");
            kapat();
            skillleriYukle();
          } catch (e) { bildir(e.message, "hata"); }
        },
      },
    ],
  });
}

// ---- GitHub'dan skill: indir -> karantina -> kural taramasi + Claude Code denetimi -> onayla kur ----
// Hicbir dosya calistirilmaz. Denetlenmeyen ve "reddet" alan skill kurulamaz; "sartli" acik onay ister.
const KARAR = {
  denetlenmedi: ["Denetlenmedi", ""], temiz: ["Güvenli", "yesil"], sartli: ["Riskli: onay ister", "sari"], reddet: ["Reddedildi", "kirmizi"],
};
const ONEM = { yuksek: "kirmizi", orta: "sari" };

function skillKarti(s) {
  const [etiket, sinif] = KARAR[s.son] || [s.son, ""];
  const d = s.denetim;
  const kural = s.rapor.riskler.slice(0, 8).map((r) => `<li><code>${kacir(r.dosya)}</code> ${kacir(r.neden)}</li>`).join("");
  const bulgu = (d?.bulgular || []).map((b) => `<li><span class="rozet ${ONEM[b.onem] || ""}">${kacir(b.onem)}</span> <code>${kacir(b.dosya)}${b.satir ? `:${kacir(b.satir)}` : ""}</code> ${kacir(b.tur)}: ${kacir(b.aciklama)}</li>`).join("");
  const secilebilir = ["temiz", "sartli"].includes(s.son);
  // neden secilemiyor: kutuyu kapatmak yetmez, kullaniciya yazilir
  const engel = { denetlenmedi: "Önce Claude Code ile denetle", reddet: "Denetim reddetti; kurulamaz" }[s.son] || "";
  const KAYNAK = { claude: "Claude Code'da", brain: "Brain'de", uygulama: "Kairo'da" };
  return `<div class="ske-skill ${secilebilir ? "" : "pasif"}" data-ad="${kacir(s.ad)}">
    <div class="ske-ust"><label class="ske-sec" title="${kacir(engel)}"><input type="checkbox" data-sec ${secilebilir && !s.var ? "checked" : ""} ${secilebilir ? "" : "disabled"}> <b>${kacir(s.ad)}</b></label>
      <span class="rozet ${sinif}">${kacir(etiket)}</span>
      <span class="soluk kucuk">${kacir(s.rapor.dosya_sayisi)} dosya</span>
      ${s.son === "denetlenmedi" ? '<button class="btn kucuk" data-denetle>Claude Code ile denetle</button>' : ""}</div>
    ${engel && s.son !== "denetlenmedi" ? `<div class="kucuk vurgu">${kacir(engel)}</div>` : ""}
    ${s.var && secilebilir ? `<div class="ske-ad-sec kucuk"><span>Bu adda bir skill ${kacir(KAYNAK[s.var] || (s.var.startsWith("plugin:") ? `${s.var.slice(7)} plugin'inde` : ""))} zaten var; aynı adla kurulamaz. Farklı adla kur:</span>
      <input class="alan" data-yeni-ad value="${kacir(`${s.ad}-github`)}" maxlength="64" spellcheck="false" aria-label="Yeni skill adı"></div>` : ""}
    ${s.son === "sartli" ? '<label class="onay kucuk ske-riskli-kart"><input type="checkbox" data-riskli> Riskli bulguları okudum, yine de kurulsun.</label>' : ""}
    <div class="soluk kucuk">${kacir(s.aciklama || "")}${s.sorun ? ` <span class="rozet kirmizi">${kacir(s.sorun)}</span>` : ""}</div>
    ${d ? `<div class="ske-denetim"><b>Claude Code:</b> ${kacir(d.ozet)}${bulgu ? `<ul>${bulgu}</ul>` : ""}</div>` : ""}
    ${kural ? `<details class="ske-kural"><summary class="soluk kucuk">Kural taraması: ${kacir(s.rapor.riskler.length)} işaret</summary><ul>${kural}</ul></details>` : ""}
    ${s.rapor.kurulum_scriptleri.length ? `<div class="soluk kucuk">Kurulum scriptleri (çalıştırılmaz): ${kacir(s.rapor.kurulum_scriptleri.join(", "))}</div>` : ""}
  </div>`;
}

function githubdanEkle() {
  let kayit = null;
  const g = el(`<div class="ske">
    <p class="soluk kucuk">Bir GitHub deposunun ya da içindeki skill klasörünün adresini yapıştır. Kairo indirir, hiçbir dosyayı çalıştırmadan karantinaya alır, kural taraması yapar ve <b>Claude Code</b>'a yalnız okuma yetkisiyle güvenlik ve gizlilik denetimi yaptırır. Güvenli bulunan kurulur, riskli olan senin onayını ister, reddedilen kurulmaz.</p>
    <div class="satir"><input class="alan" id="ske-url" placeholder="https://github.com/sahip/depo/tree/main/skills/ornek" style="flex:1" spellcheck="false" aria-label="GitHub adresi">
    <button class="btn ana" id="ske-indir">İndir ve tara</button></div>
    <div id="ske-sonuc"></div></div>`);
  const sonuc = $("#ske-sonuc", g);
  const ciz = () => {
    sonuc.innerHTML = !kayit ? "" : `<div class="soluk kucuk ske-kaynak">Kaynak: <code>${kacir(kayit.url)}</code>${kayit.commit ? ` · commit <code>${kacir(kayit.commit.slice(0, 10))}</code>` : ""}</div>${kayit.skiller.map(skillKarti).join("")}`;
    // ad kutusuna yazinca ya da riskli onayi isaretlenince skill kendiliginden secilir
    $$("[data-yeni-ad], [data-riskli]", sonuc).forEach((x) => {
      x.addEventListener("input", () => { const c = $("[data-sec]", x.closest("[data-ad]")); if (c && !c.disabled) c.checked = true; });
    });
    $$("[data-denetle]", sonuc).forEach((b) => {
      b.onclick = async () => {
        const ad = b.closest("[data-ad]").dataset.ad;
        b.disabled = true;
        b.textContent = "Denetleniyor… (20-60 sn)";
        try {
          const s = await api(`/api/skill-ice/${kayit.id}/denetle`, { method: "POST", govde: { ad } });
          kayit.skiller = kayit.skiller.map((x) => (x.ad === ad ? s : x));
        } catch (e) { bildir(e.message, "hata", 7000); }
        ciz();
      };
    });
  };
  const sil = () => { if (kayit) api(`/api/skill-ice/${kayit.id}`, { method: "DELETE" }).catch(() => {}); };
  $("#ske-indir", g).onclick = async (e) => {
    const b = e.currentTarget;
    const url = $("#ske-url", g).value.trim();
    if (!url) return;
    b.disabled = true;
    b.textContent = "İndiriliyor…";
    try {
      sil();
      kayit = await api("/api/skill-ice", { method: "POST", govde: { url } });
    } catch (err) { kayit = null; bildir(err.message, "hata", 7000); }
    ciz();
    b.disabled = false;
    b.textContent = "İndir ve tara";
  };
  modal({ baslik: "GitHub'dan skill ekle", icerik: g, genis: true, kapaninca: sil, dugmeler: [
    { metin: "Kapat" },
    { metin: "Seçilenleri kur", tur: "ana", eylem: async (kapat, b) => {
      const kartlar = $$("[data-sec]:checked", sonuc).map((x) => x.closest("[data-ad]"));
      if (!kayit || !kartlar.length) { bildir("Kurmak için denetlenmiş bir skill seç.", "uyari"); return; }
      const riskliOnaysiz = kartlar.filter((k) => $("[data-riskli]", k) && !$("[data-riskli]", k).checked).map((k) => k.dataset.ad);
      if (riskliOnaysiz.length) { bildir(`Riskli: ${riskliOnaysiz.join(", ")}. Kurmak için kartındaki "okudum" kutusunu işaretle.`, "uyari", 6000); return; }
      const adlar = kartlar.map((k) => k.dataset.ad);
      const yeni_adlar = Object.fromEntries(kartlar.filter((k) => $("[data-yeni-ad]", k)).map((k) => [k.dataset.ad, $("[data-yeni-ad]", k).value.trim()]));
      b.disabled = true;
      try {
        const r = await api(`/api/skill-ice/${kayit.id}/kur`, { method: "POST", govde: { adlar, riskli_onay: kartlar.some((k) => $("[data-riskli]", k)?.checked), yeni_adlar } });
        bildir(`Kuruldu: ${r.kurulan.join(", ")}`, "basari", 4000);
        kapat();
        skillleriYukle();
      } catch (e) { bildir(e.message, "hata", 7000); b.disabled = false; }
    } },
  ] });
}
