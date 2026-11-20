// Claude Code Desktop gibi sag paneller: Terminal, Degisiklikler (git diff), Tarayici.
// Her biri ust cubuktaki dugmeyle acilip kapanir; ayni anda birden fazlasi ustuste durabilir.
import { diffHtml } from "./inceleme.js";
import { kacir } from "./md.js";
import { kacir as _k, md } from "./md.js";
import { $, $$, api, bildir, sseOku } from "./ortak.js";
import { t } from "./i18n.js";

// ---- yan sohbet (Claude Desktop "Side chat"): ayri oturum, ana sohbete karismaz ----
let yanOturum = null;
let yanAkis = null;
async function yanGonder(metin) {
  const kap = $("#yan-mesajlar");
  kap.insertAdjacentHTML("beforeend", `<div class="yan-k">${_k(metin)}</div>`);
  const cevap = document.createElement("div");
  cevap.className = "yan-a md";
  cevap.textContent = "…";
  kap.append(cevap);
  let yazi = "";
  try {
    if (!yanOturum) yanOturum = (await api("/api/oturumlar", { method: "POST" })).id;
    yanAkis = new AbortController();
    for await (const o of sseOku(`/api/oturumlar/${yanOturum}/mesaj`, { metin, ekler: [] }, yanAkis.signal)) {
      if (o.tur === "parca") { yazi += o.metin; cevap.innerHTML = md(yazi); }
      else if (o.tur === "hata") cevap.textContent = o.mesaj;
      else if (o.tur === "durum" && !yazi) cevap.textContent = o.metin;
      kap.scrollTop = kap.scrollHeight;
    }
  } catch (e) { cevap.textContent = e.message; }
  yanAkis = null;
}

// ---- plan paneli: calisan (ya da son) ajan gorevinin plani ----
let planZaman = null;
async function planYenile() {
  clearTimeout(planZaman);
  if ($('[data-panel="plan"]').hidden) return;
  const g = $("#plan-govde");
  try {
    const { gorevler } = await api("/api/gorevler");
    const r0 = gorevler.find((x) => x.durum === "calisiyor") || gorevler[0];
    if (!r0) { g.innerHTML = '<div class="soluk">Henüz ajan görevi yok. Proje açıp bir görev verdiğinde planı burada görünür.</div>'; }
    else {
      const r = await api(`/api/gorevler/${r0.id}`);
      $("#pl-gorev").textContent = (r.hedef || "").slice(0, 60);
      const isaret = { tamam: "✓", suruyor: "▸", atlandi: "–", bekliyor: "○" };
      g.innerHTML = (r.plan || []).length
        ? `<ul class="plan-liste">${r.plan.map((p) => `<li class="plan-${kacir(p.durum)}">${isaret[p.durum] || "○"} ${kacir(p.baslik)}</li>`).join("")}</ul><div class="soluk kucuk">Durum: ${kacir(r.durum)}</div>`
        : `<div class="soluk">Bu görev henüz plan yazmadı (durum: ${kacir(r.durum)}).</div>`;
    }
  } catch (e) { g.innerHTML = `<div class="soluk">${kacir(e.message)}</div>`; }
  planZaman = setTimeout(planYenile, 3000);
}

const ACIK = "kairo.dock";
let tmIs = null; // calisan terminal isi
let tmZamanlayici = null;

function acikPaneller() {
  try { return JSON.parse(localStorage.getItem(ACIK) || "[]"); } catch { return []; }
}

function ciz(acik) {
  localStorage.setItem(ACIK, JSON.stringify(acik));
  $$(".dock-panel").forEach((p) => { p.hidden = !acik.includes(p.dataset.panel); });
  $("#dock").hidden = !acik.length;
  $$("[data-dock]").forEach((b) => b.classList.toggle("aktif", acik.includes(b.dataset.dock)));
}

export function dockAcKapa(ad, zorla = null) {
  let acik = acikPaneller();
  const ac = zorla ?? !acik.includes(ad);
  acik = acik.filter((x) => x !== ad);
  if (ac) acik.push(ad);
  ciz(acik);
  if (ac && ad === "degisiklik") degisiklikYenile();
  if (ac && ad === "terminal") setTimeout(() => $("#tm-girdi").focus(), 0);
  if (ac && ad === "yan") setTimeout(() => $("#yan-girdi").focus(), 0);
  if (ac && ad === "plan") planYenile();
}

// ---- terminal ----
function tmYaz(metin) {
  const c = $("#tm-cikti");
  c.textContent += metin;
  c.scrollTop = c.scrollHeight;
}

async function tmIzle() {
  clearTimeout(tmZamanlayici);
  if (!tmIs) return;
  try {
    const r = await api(`/api/komutlar/${tmIs.id}`);
    const yeni = r.cikti.slice(tmIs.okunan);
    tmIs.okunan = r.cikti.length;
    if (yeni) tmYaz(yeni.endsWith("\n") ? yeni : `${yeni}\n`);
    if (r.durum !== "calisiyor") {
      tmYaz(`[${r.durum}${r.cikis_kodu != null ? `, çıkış ${r.cikis_kodu}` : ""}]\n`);
      tmIs = null;
      $("#tm-durdur").hidden = true;
      return;
    }
  } catch (e) { tmYaz(`[hata] ${e.message}\n`); tmIs = null; $("#tm-durdur").hidden = true; return; }
  tmZamanlayici = setTimeout(tmIzle, 500);
}

async function tmGonder(komut) {
  if (tmIs) { // calisan komuta girdi
    try { await api(`/api/komutlar/${tmIs.id}/girdi`, { method: "POST", govde: { metin: komut } }); tmYaz(`${komut}\n`); } catch (e) { bildir(e.message, "hata"); }
    return;
  }
  tmYaz(`> ${komut}\n`);
  try {
    const r = await api("/api/terminal", { method: "POST", govde: { komut } });
    $("#tm-cwd").textContent = r.cwd;
    tmIs = { id: r.id, okunan: 0 };
    $("#tm-durdur").hidden = false;
    tmIzle();
  } catch (e) { tmYaz(`[hata] ${e.message}\n`); }
}

// ---- degisiklikler ----
export async function degisiklikYenile() {
  const g = $("#dg-govde");
  if (!g || $("#dock").hidden) return;
  try {
    const d = await api("/api/review/diff");
    g.innerHTML = d.diff?.trim()
      ? `<div class="diff">${diffHtml(d.diff)}</div>`
      : `<div class="soluk">${kacir(d.hata || "Değişiklik yok.")}</div>`;
  } catch (e) { g.innerHTML = `<div class="soluk">${kacir(e.message)}</div>`; }
}

// ---- tarayici ----
function trAc(adres) {
  let u = adres.trim();
  if (!u) return;
  if (!/^https?:\/\//i.test(u)) u = `http://${u}`;
  try {
    if (new URL(u).origin === location.origin) return bildir("Uygulamanın kendisi burada açılamaz.", "uyari");
  } catch { return bildir("Geçersiz adres.", "hata"); }
  $("#tr-adres").value = u;
  const host = new URL(u).hostname;
  const yerel = host === "localhost" || host.endsWith(".localhost") || /^127\./.test(host) || host === "[::1]";
  if (!yerel) disAc(u); // dis siteler iframe'e izin vermez (X-Frame-Options): ayri pencere
  else { $("#tr-cerceve").removeAttribute("srcdoc"); $("#tr-cerceve").src = u; } // srcdoc src'den once gelir
}

// Google/GitHub gibi siteler gomulu gosterimi yasaklar; Kairo icinden ayri tarayici penceresi acilir
async function disAc(u) {
  const f = $("#tr-cerceve");
  let acildi = false;
  try { acildi = !!(await window.pywebview?.api?.tarayici_ac(u)); } catch { /* masaustu kopru yok */ }
  if (!acildi) acildi = !!window.open(u, "_blank", "noopener");
  f.removeAttribute("src");
  f.srcdoc = `<body style="margin:0;display:grid;place-items:center;height:100vh;font:14px system-ui;color:#9a9a94;background:transparent;text-align:center;padding:24px">${kacir(acildi
    ? t("Bu site gömülü gösterime izin vermiyor; ayrı pencerede açıldı.")
    : t("Bu site gömülü gösterime izin vermiyor ve ayrı pencere açılamadı."))}</body>`;
}

export function dockKur() {
  $$("[data-dock]").forEach((b) => { b.onclick = () => dockAcKapa(b.dataset.dock); });
  $$(".dock-panel [data-kapat]").forEach((b) => { b.onclick = () => dockAcKapa(b.closest(".dock-panel").dataset.panel, false); });
  $("#tm-girdi").onkeydown = (e) => {
    if (e.key === "Enter" && e.target.value.trim()) { tmGonder(e.target.value); e.target.value = ""; }
  };
  $("#tm-temizle").onclick = () => { $("#tm-cikti").textContent = ""; };
  $("#tm-durdur").onclick = async () => { if (tmIs) try { await api(`/api/komutlar/${tmIs.id}/durdur`, { method: "POST" }); } catch (e) { bildir(e.message, "hata"); } };
  $("#dg-yenile").onclick = degisiklikYenile;
  $("#tr-adres").onkeydown = (e) => { if (e.key === "Enter") trAc(e.target.value); };
  $("#tr-yenile").onclick = () => { const f = $("#tr-cerceve"); if (f.src) f.src = f.src; };
  $("#tr-geri").onclick = () => { try { $("#tr-cerceve").contentWindow.history.back(); } catch { /* farkli origin */ } };
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key === "`") { e.preventDefault(); dockAcKapa("terminal"); }
    if (e.ctrlKey && e.key === ";") { e.preventDefault(); dockAcKapa("yan"); }
  });
  $("#yan-girdi").onkeydown = (e) => {
    if (e.key === "Enter" && e.target.value.trim() && !yanAkis) { yanGonder(e.target.value.trim()); e.target.value = ""; }
  };
  $("#yan-yeni").onclick = () => { yanAkis?.abort(); yanOturum = null; $("#yan-mesajlar").innerHTML = ""; };
  ciz(acikPaneller());
}
