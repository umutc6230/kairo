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
  $("#t-kaydet").onclick = async () => {
    try {
      await api("/api/talimatlar", { method: "PUT", govde: { metin: $("#t-uygulama").value } });
      bildir("Uygulama talimatı kaydedildi", "basari");
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
  $("#t-claude-ozet").textContent = t.claude.length ? `${t.claude.length} dosya · ~${sayi(toplam, 0)} token` : "bulunamadı (~/.claude/CLAUDE.md yok)";
  const kap = $("#t-claude-liste");
  kap.innerHTML = "";
  for (const k of t.claude) {
    const s = el(`<div class="kaynak-satir"><span data-ikon="dosya"></span><span class="ad">${kacir(k.yol.split(/[\\/]/).pop())}</span>
      <span class="soluk kucuk yol">${kacir(k.yol)}</span><span class="rozet">~${sayi(k.token, 0)} token</span>${k.kisaltildi ? '<span class="rozet sari">kısaltıldı</span>' : ""}
      <button class="btn kucuk">Göster</button></div>`);
    s.querySelector("button").onclick = () => modal({ baslik: k.yol, icerik: `<pre class="duz">${kacir(k.metin)}</pre>`, genis: true });
    kap.append(s);
  }
  const baglam = t.baglam_token;
  const oran = Math.round(((t.claude_acik ? toplam : 0) / baglam) * 100);
  $("#t-baglam-not").innerHTML = oran > 30
    ? `<span class="rozet sari">talimatlar bağlamın %${oran}'ini kullanıyor</span>`
    : `<span class="rozet">talimatlar bağlamın %${oran}'i</span>`;
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
