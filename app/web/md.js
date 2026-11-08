// Kucuk ve guvenli markdown -> HTML. Once HTML kacirilir; yalniz bilinen bicimler etiketlenir.
export function kacir(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function satirIci(s) {
  const kodlar = [];
  s = s.replace(/`([^`\n]+)`/g, (_, k) => { kodlar.push(k); return `\u0000${kodlar.length - 1}\u0000`; });
  s = kacir(s);
  s = s.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_\n]+)__/g, "<strong>$1</strong>")
    .replace(/(^|[^*\w])\*([^*\n]+)\*(?!\w)/g, "$1<em>$2</em>")
    .replace(/~~([^~\n]+)~~/g, "<del>$1</del>")
    .replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>');
  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${kacir(kodlar[+i])}</code>`);
}

function tabloMu(satirlar, i) {
  return /^\s*\|.*\|\s*$/.test(satirlar[i] || "") && /^\s*\|?\s*:?-{2,}/.test(satirlar[i + 1] || "");
}

function hucreler(satir) {
  return satir.trim().replace(/^\||\|$/g, "").split("|").map((h) => h.trim());
}

export function md(metin) {
  const satirlar = String(metin ?? "").replace(/\r\n/g, "\n").split("\n");
  const cikti = [];
  let i = 0;
  let paragraf = [];
  const paragrafBitir = () => {
    if (paragraf.length) cikti.push(`<p>${paragraf.map(satirIci).join("<br>")}</p>`);
    paragraf = [];
  };
  while (i < satirlar.length) {
    const s = satirlar[i];
    const kod = s.match(/^\s*```\s*([\w+-]*)/);
    if (kod) {
      paragrafBitir();
      const govde = [];
      i++;
      while (i < satirlar.length && !/^\s*```/.test(satirlar[i])) govde.push(satirlar[i++]);
      i++;
      const dil = kacir(kod[1] || "metin");
      cikti.push(`<pre><div class="kod-ust"><span>${dil}</span><button class="ikon-btn kod-kopyala" title="Kopyala" data-ikon="kopyala"></button></div><code>${kacir(govde.join("\n"))}</code></pre>`);
      continue;
    }
    if (tabloMu(satirlar, i)) {
      paragrafBitir();
      const bas = hucreler(s);
      i += 2;
      const govde = [];
      while (i < satirlar.length && /^\s*\|.*\|\s*$/.test(satirlar[i])) govde.push(hucreler(satirlar[i++]));
      cikti.push(`<table><thead><tr>${bas.map((h) => `<th>${satirIci(h)}</th>`).join("")}</tr></thead><tbody>${govde.map((r) => `<tr>${r.map((h) => `<td>${satirIci(h)}</td>`).join("")}</tr>`).join("")}</tbody></table>`);
      continue;
    }
    const baslik = s.match(/^(#{1,4})\s+(.*)$/);
    if (baslik) { paragrafBitir(); cikti.push(`<h${baslik[1].length}>${satirIci(baslik[2])}</h${baslik[1].length}>`); i++; continue; }
    if (/^\s*([-*_])\s*\1\s*\1[\s\-*_]*$/.test(s)) { paragrafBitir(); cikti.push("<hr>"); i++; continue; }
    if (/^\s*>\s?/.test(s)) {
      paragrafBitir();
      const alinti = [];
      while (i < satirlar.length && /^\s*>\s?/.test(satirlar[i])) alinti.push(satirlar[i++].replace(/^\s*>\s?/, ""));
      cikti.push(`<blockquote>${md(alinti.join("\n"))}</blockquote>`);
      continue;
    }
    const liste = s.match(/^\s*([-*+]|\d+[.)])\s+(.*)$/);
    if (liste) {
      paragrafBitir();
      const sirali = /\d/.test(liste[1]);
      const ogeler = [];
      while (i < satirlar.length) {
        const m = satirlar[i].match(/^\s*([-*+]|\d+[.)])\s+(.*)$/);
        if (m) { ogeler.push(m[2]); i++; }
        else if (/^\s{2,}\S/.test(satirlar[i]) && ogeler.length) { ogeler[ogeler.length - 1] += " " + satirlar[i].trim(); i++; }
        else break;
      }
      const etiket = sirali ? "ol" : "ul";
      cikti.push(`<${etiket}>${ogeler.map((o) => `<li>${satirIci(o)}</li>`).join("")}</${etiket}>`);
      continue;
    }
    if (!s.trim()) { paragrafBitir(); i++; continue; }
    paragraf.push(s);
    i++;
  }
  paragrafBitir();
  return cikti.join("");
}
