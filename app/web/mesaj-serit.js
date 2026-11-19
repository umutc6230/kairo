// Sohbetin solunda her kullanici mesaji icin bir cizgi; tikla -> o mesaja kay, aktif olan vurgulu.
const kap = document.getElementById("mesajlar");
const serit = document.createElement("nav");
serit.className = "mesaj-serit";
serit.setAttribute("aria-label", "Mesajlar arasında gezin");
kap.parentElement.append(serit);

const mesajlar = () => [...kap.querySelectorAll(".mesaj.kullanici")];

function aktifiIsaretle() {
  const ust = kap.getBoundingClientRect().top + 40;
  let aktif = 0;
  mesajlar().forEach((m, i) => { if (m.getBoundingClientRect().top <= ust) aktif = i; });
  [...serit.children].forEach((c, i) => c.classList.toggle("aktif", i === aktif));
}

function ciz() {
  const liste = mesajlar();
  serit.hidden = liste.length < 2;
  serit.replaceChildren(...liste.map((m) => {
    const b = document.createElement("button");
    const metin = m.textContent.trim().replace(/\s+/g, " ").slice(0, 80);
    b.title = metin;
    b.setAttribute("aria-label", metin);
    b.onclick = () => m.scrollIntoView({ behavior: "smooth", block: "start" });
    return b;
  }));
  aktifiIsaretle();
}

let bekleyen = 0;
new MutationObserver(() => { clearTimeout(bekleyen); bekleyen = setTimeout(ciz, 100); })
  .observe(kap, { childList: true, subtree: true });
kap.addEventListener("scroll", aktifiIsaretle, { passive: true });
ciz();
