// Claude Code Desktop gibi sag paneller: Terminal, Degisiklikler (git diff), Tarayici.
// Her biri ust cubuktaki dugmeyle acilip kapanir; ayni anda birden fazlasi ustuste durabilir.
import { diffHtml } from "./inceleme.js";
import { kacir } from "./md.js";
import { $, $$, api, bildir } from "./ortak.js";

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
  $("#tr-cerceve").src = u;
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
  document.addEventListener("keydown", (e) => { if (e.ctrlKey && e.key === "`") { e.preventDefault(); dockAcKapa("terminal"); } });
  ciz(acikPaneller());
}
