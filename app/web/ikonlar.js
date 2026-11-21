// Cizgi ikonlar (24x24, stroke). data-ikon="ad" olan ogelere ikonlariYerlestir() ile basilir.
const P = {
  panel: '<rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M9 4v16"/>',
  sol: '<path d="m15 18-6-6 6-6"/>',
  sag: '<path d="m9 18 6-6-6-6"/>',
  asagi: '<path d="m6 9 6 6 6-6"/>',
  eksi: '<path d="M5 12h14"/>',
  kare: '<rect x="5" y="5" width="14" height="14" rx="1.5"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  arti: '<path d="M12 5v14M5 12h14"/>',
  dal: '<circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="7" r="2"/><path d="M6 7v10M18 9c0 5-6 4-11.5 8"/>',
  mikrofon: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v5M8 22h8"/>',
  ara: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  sutun: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16M15 4v16"/>',
  tara: '<path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M7 9h10M7 12h10M7 15h6"/>',
  anahtar: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.8-3.8a6 6 0 0 1-7.9 7.9l-6.9 6.9a2.1 2.1 0 0 1-3-3l6.9-6.9a6 6 0 0 1 7.9-7.9l-3.8 3.8z"/>',
  sise: '<path d="M10 2v7.3L4.6 19a2 2 0 0 0 1.8 3h11.2a2 2 0 0 0 1.8-3L14 9.3V2M8.5 2h7M7 16h10"/>',
  disli: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  klasor: '<path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.7-.9l-.8-1.2A2 2 0 0 0 7.9 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z"/>',
  ekran: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
  yukari: '<path d="M12 19V5M5 12l7-7 7 7"/>',
  durdur: '<rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor"/>',
  kopyala: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  tik: '<path d="M20 6 9 17l-5-5"/>',
  daha: '<circle cx="5" cy="12" r="1.2" fill="currentColor"/><circle cx="12" cy="12" r="1.2" fill="currentColor"/><circle cx="19" cy="12" r="1.2" fill="currentColor"/>',
  kalem: '<path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  cop: '<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
  beyin: '<path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/><path d="M12 5v13"/>',
  uyari: '<path d="m21.7 18-8-14a2 2 0 0 0-3.4 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3z"/><path d="M12 9v4M12 17h.01"/>',
  pr: '<circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="M6 8.5v7M18 15.5V9a3 3 0 0 0-3-3h-4"/><path d="m13 3.5-2.5 2.5 2.5 2.5"/>',
  terminal: '<path d="M4 17l6-5-6-5M12 19h8"/>',
  diff: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M12 7v6M9 10h6M9 17h6"/>',
  dunya: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  // Her ise ayri ikon: ayni simge farkli islerde kullanilmaz
  panelSag: '<rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M15 4v16"/>',
  yanSohbet: '<path d="M21 15a2 2 0 0 1-2 2H8l-4 4V6a2 2 0 0 1 2-2h13a2 2 0 0 1 2 2z"/><path d="M8 9h8M8 13h5"/>',
  plan: '<path d="M9 6h11M9 12h11M9 18h11"/><path d="m3 6 1.5 1.5L7 5M3 12l1.5 1.5L7 11M3 18l1.5 1.5L7 17"/>',
  gorevler: '<rect x="3" y="4" width="6" height="16" rx="1.5"/><rect x="10.5" y="4" width="6" height="10" rx="1.5"/><path d="M19.5 4v7"/>',
  arkaPlan: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 15l3-3-3-3M12 15h4"/><circle cx="19" cy="5" r="2.5"/>',
  kahve: '<path d="M4 9h13v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5z"/><path d="M17 11h1.5a2.5 2.5 0 0 1 0 5H17M8 3v3M12 3v3"/>',
  eklenti: '<path d="M14 4a2 2 0 1 0-4 0v2H6a1 1 0 0 0-1 1v4h2a2 2 0 1 1 0 4H5v4a1 1 0 0 0 1 1h4v-2a2 2 0 1 1 4 0v2h4a1 1 0 0 0 1-1v-4h-2a2 2 0 1 1 0-4h2V7a1 1 0 0 0-1-1h-4z"/>',
  uzak: '<path d="M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0"/><circle cx="12" cy="19.5" r="1"/><path d="M2 9a14.5 14.5 0 0 1 20 0"/>',
  liste: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  saat: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  dosya: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
  resim: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/>',
  hoparlor: '<path d="M11 5 6 9H2v6h4l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14"/>',
  muzik: '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
  yenile: '<path d="M21 12a9 9 0 1 1-2.6-6.4L21 8M21 3v5h-5"/>',
  raptiye: '<path d="M9 4h6l-1 6 4 4H6l4-4zM12 14v7"/>',
  oynat: '<path d="m6 4 14 8-14 8z" fill="currentColor"/>',
  sihir: '<path d="m12 3 1.9 5.8L20 10l-5 3.6L16.6 20 12 16.4 7.4 20 9 13.6 4 10l6.1-1.2z"/>',
  bilgi: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
  guc: '<path d="M12 2v10M18.4 6.6a9 9 0 1 1-12.8 0"/>',
  dis: '<path d="M7 7h10v10M7 17 17 7"/>',
  paylas: '<path d="M4 12v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7"/><path d="m16 6-4-4-4 4M12 2v13"/>', // kutudan yukari ok (yaygin Paylas)
  model: '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/>',
  analitik: '<path d="M4 20V14M10 20V8M16 20V4M21 20H3"/>',
};

// Kairo karakteri: kucuk piksel baykus (turkuaz).
const LOGO = `<svg class="baykus" viewBox="0 0 13 10" shape-rendering="crispEdges" fill="#2bb6a8">
<g class="bk-govde"><rect x="2" y="0" width="1" height="1"/><rect x="10" y="0" width="1" height="1"/>
<rect x="2" y="1" width="9" height="8"/>
<g class="bk-goz"><rect x="3" y="2" width="3" height="3" fill="#f4f1e8"/><rect x="7" y="2" width="3" height="3" fill="#f4f1e8"/>
<rect class="bk-bebek" x="4" y="3" width="1" height="1" fill="#1f1f1e"/><rect class="bk-bebek" x="8" y="3" width="1" height="1" fill="#1f1f1e"/></g>
<rect x="6" y="5" width="1" height="1" fill="#f2b134"/></g>
<rect class="bk-kanat bk-sol" x="1" y="4" width="1" height="3"/><rect class="bk-kanat bk-sag" x="11" y="4" width="1" height="3"/>
<rect class="bk-ayak bk-a1" x="4" y="9" width="2" height="1" fill="#f2b134"/><rect class="bk-ayak bk-a2" x="7" y="9" width="2" height="1" fill="#f2b134"/></svg>`;

export function ikon(ad) {
  if (ad === "logo") return LOGO;
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${P[ad] || ""}</svg>`;
}

export function ikonlariYerlestir(kok = document) {
  kok.querySelectorAll("[data-ikon]").forEach((el) => {
    if (el.dataset.ikonTamam) return;
    el.insertAdjacentHTML("afterbegin", ikon(el.dataset.ikon));
    el.dataset.ikonTamam = "1";
  });
}
