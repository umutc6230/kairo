// Sohbet mini haritasi (Paradev gibi): mesaj alaninin solunda her kullanici mesaji icin bir cizgi.
// Tikla -> o mesaja kaydir; gorunen mesajin cizgisi vurgulu. Kisa sohbette (<3 mesaj) gizli.
import { $ } from "./ortak.js";

let serit = null;
// mesajin kaydirma alanindaki konumu (offsetTop konumlandirilmis ataya gore olcer, guvenilmez)
const konum = (kap, m) => m.getBoundingClientRect().top - kap.getBoundingClientRect().top + kap.scrollTop;
let zamanlayici = 0;

function ciz() {
  const kap = $("#mesajlar");
  if (!kap || !serit) return;
  const mesajlar = [...kap.querySelectorAll(".mesaj.kullanici")];
  serit.hidden = mesajlar.length < 3 || kap.scrollHeight <= kap.clientHeight * 1.2;
  if (serit.hidden) return;
  serit.innerHTML = "";
  const toplam = Math.max(1, kap.scrollHeight);
  for (const m of mesajlar) {
    const b = document.createElement("button");
    b.className = "mm-cizgi";
    b.style.top = `${(100 * konum(kap, m)) / toplam}%`;
    const metin = (m.querySelector(".balon")?.textContent || "").trim().slice(0, 80);
    b.title = metin;
    b.setAttribute("aria-label", `Mesaja git: ${metin}`);
    b.onclick = () => m.scrollIntoView({ behavior: "smooth", block: "start" });
    b._mesaj = m;
    serit.append(b);
  }
  vurgula();
}

function vurgula() {
  const kap = $("#mesajlar");
  if (!kap || !serit || serit.hidden) return;
  const ust = kap.scrollTop + 40;
  let aktif = null;
  for (const b of serit.children) if (konum(kap, b._mesaj) <= ust) aktif = b;
  aktif ||= serit.firstElementChild;
  for (const b of serit.children) b.classList.toggle("aktif", b === aktif);
}

const yeniden = () => { clearTimeout(zamanlayici); zamanlayici = setTimeout(ciz, 250); };

export function miniHaritaKur() {
  const kap = $("#mesajlar");
  if (!kap || serit) return;
  serit = document.createElement("nav");
  serit.className = "mini-harita";
  serit.setAttribute("aria-label", "Sohbet mini haritası");
  serit.hidden = true;
  kap.parentElement.append(serit);
  kap.addEventListener("scroll", () => requestAnimationFrame(vurgula), { passive: true });
  new MutationObserver(yeniden).observe(kap, { childList: true, subtree: true });
  new ResizeObserver(yeniden).observe(kap);
}
