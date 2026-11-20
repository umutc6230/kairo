// Claude Desktop gibi: cevaptaki GitHub PR linki ikonlu cipe doner, cevabin altina PR karti eklenir
import { $, api } from "./ortak.js";
import { kacir } from "./md.js";
import { ikon } from "./ikonlar.js";

const PR = /^https:\/\/github\.com\/([\w.-]+\/[\w.-]+)\/pull\/(\d+)\/?$/;
const onbellek = new Map(); // url -> Promise<pr|null>; akista ayni PR tekrar tekrar sorulmasin
const getir = (url) => {
  if (!onbellek.has(url)) {
    onbellek.set(url, api(`/api/github/pr?url=${encodeURIComponent(url)}`).then((p) => (p?.number ? p : null)).catch(() => null));
  }
  return onbellek.get(url);
};

const DURUM = { OPEN: ["Open", "acik"], MERGED: ["Merged", "birlesti"], CLOSED: ["Closed", "kapali"] };

export function goreli(iso) {
  const sn = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (sn < 60) return "az önce";
  if (sn < 3600) return `${Math.floor(sn / 60)} dk önce`;
  if (sn < 86400) return `${Math.floor(sn / 3600)} sa önce`;
  return `${Math.floor(sn / 86400)} gün önce`;
}

function kart(p, repo) {
  const [ad, sinif] = p.isDraft ? ["Draft", "taslak"] : DURUM[p.state] || [p.state, ""];
  return `<a class="pr-kart" href="${kacir(p.url)}" target="_blank" rel="noopener" data-pr-kart="${kacir(p.url)}">
    <span class="pr-kart-ikon">${ikon("dal")}</span>
    <span class="pr-kart-ust"><span class="pr-durum ${sinif}">${ikon("dal")}${kacir(ad)}</span><span class="soluk">${kacir(repo)} #${Number(p.number)}${p.author?.login ? ` · ${kacir(p.author.login)}` : ""}${p.createdAt ? ` · ${goreli(p.createdAt)}` : ""}</span></span>
    <span class="pr-kart-alt"><b>${kacir(p.title)}</b><span class="pr-sayilar"><span class="pr-dosya">${Number(p.changedFiles)} dosya</span><span class="pr-fark"><span class="arti">+${Number(p.additions)}</span> <span class="eksi">−${Number(p.deletions)}</span></span></span></span>
  </a>`;
}

async function isle(a) {
  const m = PR.exec(a.getAttribute("href") || "");
  if (!m || a.dataset.pr) return;
  a.dataset.pr = "1";
  const url = a.href.replace(/\/$/, "");
  const p = await getir(url);
  if (!p || !a.isConnected || !PR.test(p.url)) return;
  const repo = m[1];
  a.classList.add("pr-cip");
  a.innerHTML = `${ikon("dal")}<span>${kacir(repo)}#${Number(p.number)} · ${kacir(p.title)}</span>`;
  a.title = p.title;
  const md = a.closest(".md");
  if (!md || md.parentElement.querySelector(`[data-pr-kart="${CSS.escape(p.url)}"]`)) return;
  md.insertAdjacentHTML("afterend", kart(p, repo));
}

let bekleyen = 0;
export function prKartlariKur() {
  const kap = $("#mesajlar");
  const tara = () => { bekleyen = 0; kap.querySelectorAll('.md a[href^="https://github.com/"]:not([data-pr])').forEach(isle); };
  new MutationObserver(() => { if (!bekleyen) bekleyen = setTimeout(tara, 150); }).observe(kap, { childList: true, subtree: true });
}
