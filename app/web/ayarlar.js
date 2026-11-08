// AI Ayarlari, Hakkinda ve Arama pencereleri.
import { ikon, ikonlariYerlestir } from "./ikonlar.js";
import { kacir } from "./md.js";
import { $, $$, api, bildir, durum, el, modal, onayla, sayi } from "./ortak.js";

let yenile = async () => {};
export function ayarlarKur(cb) { yenile = cb; }

async function kaydet(degisiklik, sessiz = false) {
  try {
    durum.ayarlar = await api("/api/ayarlar", { method: "PUT", govde: degisiklik });
    if (!sessiz) bildir("Kaydedildi", "basari", 1500);
    await yenile();
  } catch (e) {
    bildir(e.message, "hata");
  }
}
export { kaydet as ayarKaydet };

function modelKartlari(arama, yalnizIndirilen) {
  const a = durum.ayarlar;
  const kucuk = arama.toLowerCase();
  return (durum.sunucu?.modeller || [])
    .filter((m) => (!kucuk || `${m.ad} ${m.anahtar}`.toLowerCase().includes(kucuk)) && (!yalnizIndirilen || m.dosya_var))
    .map((m) => `<label class="secenek-kart ${m.anahtar === a.model ? "secili" : ""} ${m.dosya_var ? "" : "pasif"}">
      <input type="radio" name="ayar-model" value="${m.anahtar}" ${m.anahtar === a.model ? "checked" : ""} ${m.dosya_var ? "" : "disabled"}>
      <div><div class="ust">${kacir(m.ad)}
        <span class="rozet">~${m.ram_gb} GB RAM</span>
        <span class="rozet yesil">ücretsiz (yerel)</span>
        <span class="rozet">context 8192</span>
        <span class="rozet ${m.ses ? "yesil" : ""}">${m.ses ? "metin · resim · araç · ses" : "metin · resim · araç"}</span>
        ${m.dosya_var ? "" : '<span class="rozet kirmizi">dosya yok</span>'}
        ${m.dosya_var && !m.mmproj_var ? '<span class="rozet sari">görüntü modülü yok</span>' : ""}</div>
        <div class="alt">${kacir(m.aciklama)} · <code>${kacir(m.anahtar)}</code></div></div></label>`)
    .join("") || `<div class="ayar-not">Eşleşen model yok.</div>`;
}

export function ayarlarAc(sekme = "ai") {
  const a = durum.ayarlar;
  const s = durum.sunucu || {};
  const govde = el(`<div>
    <div class="sekmeler"><button class="sekme" data-sekme="ai">AI Ayarları</button><button class="sekme" data-sekme="hakkinda">Hakkında</button></div>
    <div class="modal-govde" data-panel="ai">
      <div class="ayar-grup"><label>Sağlayıcı</label>
        <div class="secenek-kart secili"><input type="radio" checked><div><div class="ust">Yerel (llama.cpp) <span class="rozet yesil">internetsiz</span></div>
        <div class="alt">Modeller bu bilgisayarda çalışır, veri dışarı çıkmaz. Bu sağlayıcı API anahtarı gerektirmez.</div></div></div></div>
      <div class="ayar-grup"><label>Model</label>
        <div class="satir"><input class="alan" id="ay-ara" placeholder="Model ara..."><label class="onay"><input type="checkbox" id="ay-indirilen"> Yalnız indirilenler</label>
        <label class="onay" title="Yerel modellerin hepsi ücretsizdir"><input type="checkbox" checked disabled> Yalnız ücretsiz</label></div>
        <div id="ay-modeller" class="ayar-grup"></div></div>
      <div class="ayar-grup"><label>Düşünme seviyesi</label><div id="ay-dusunme" class="ayar-grup"></div></div>
      <div class="ayar-grup"><label>Test</label>
        <div class="satir"><button class="btn" id="ay-test"><span data-ikon="oynat"></span>Seçili modeli test et</button><span id="ay-test-sonuc" class="ayar-not">Uygulamanın kullandığı biçimde (JSON şema) kısa bir istek atar.</span></div></div>
      <div class="ayar-grup"><label>Model klasörü</label><input class="alan" id="ay-dizin" value="${kacir(a.llm_dizin)}">
        <div class="ayar-not">llama.cpp\\llama-server.exe ve models\\*.gguf bu klasörde olmalı. ${s.motor_var ? "✓ llama.cpp bulundu" : "✗ llama.cpp bulunamadı"}</div></div>
      <div class="ayar-grup"><label>Bağlam boyutu</label>
        <select class="secim" id="ay-baglam"><option value="8192">8K token (en az RAM)</option><option value="16384">16K token (önerilen; talimatlar ~3K yer)</option><option value="32768">32K token (daha çok RAM)</option></select>
        <div class="ayar-not">Değişince model bir sonraki mesajda yeni bağlamla yeniden açılır. Talimat ve skill ayarları: Skill'ler ve talimatlar sayfası.</div></div>
      <div class="ayar-grup"><label>Sunucu adresi</label><input class="alan" id="ay-adres" value="${kacir(a.adres)}"></div>
      <div class="anahtar-satir"><div><div>Otomatik başlat</div><div class="ayar-not">Model kapalıysa ilk mesajda arka planda açılır; uygulama kapanınca kapanır.</div></div>
        <label class="anahtar"><input type="checkbox" id="ay-oto" ${a.otomatik_baslat ? "checked" : ""}><span></span></label></div>
      <div class="anahtar-satir"><div><div>Sohbette araçlar</div><div class="ayar-not">Model gerektiğinde bu bilgisayardaki dosya ve klasörleri <b>yalnız okuyabilir</b> (listeleme, okuma, arama), hesap yapabilir, saati öğrenebilir. Silme/yazma aracı yoktur; .env, ssh anahtarı, parola dosyaları okunmaz.</div></div>
        <label class="anahtar"><input type="checkbox" id="ay-araclar" ${a.sohbet_araclari ? "checked" : ""}><span></span></label></div>
      <div class="ayar-grup"><label>Sistem istemi (isteğe bağlı)</label><textarea class="alan" id="ay-sistem" rows="3" placeholder="Örn: Her zaman Türkçe ve kısa cevap ver.">${kacir(a.sistem_istemi)}</textarea></div>
      <div class="satir"><div class="ayar-grup" style="flex:1"><label>Sıcaklık (${a.sicaklik})</label><input type="range" id="ay-sicaklik" min="0" max="1.5" step="0.1" value="${a.sicaklik}"></div>
        <div class="ayar-grup" style="flex:1"><label>En fazla cevap token</label><input class="alan" id="ay-max" type="number" min="16" max="8192" value="${a.max_tokens}"></div></div>
      <div class="ayar-grup"><label>Sunucu</label><div class="satir">
        <button class="btn" id="ay-yukle"><span data-ikon="guc"></span>Modeli şimdi yükle</button>
        <button class="btn" id="ay-durdur"><span data-ikon="durdur"></span>Sunucuyu durdur</button>
        <button class="btn tehlike" id="ay-harici" ${s.sunucu_acik && !s.bizim_sunucu ? "" : "hidden"}>Dışarıdan açılmış sunucuyu kapat</button></div></div>
    </div>
    <div class="modal-govde" data-panel="hakkinda" hidden>
      <div class="hakkinda-logo">${ikon("logo")}</div>
      <div><b style="font-size:18px">${kacir(durum.bilgi.urun)}</b> <span class="soluk">sürüm ${kacir(durum.bilgi.surum)}</span></div>
      <p class="soluk" style="margin:0">Bilgisayarındaki sansürsüz yerel modelleri sohbet, OCR, araç çağırma ve karşılaştırma testleriyle denemek için.</p>
      <div>Ürün sahibi: <b>${kacir(durum.bilgi.urun_sahibi)}</b></div>
      <div class="satir"><a href="${durum.bilgi.x}" target="_blank" rel="noopener">X: @umutc6230</a><a href="${durum.bilgi.github}" target="_blank" rel="noopener">GitHub: umutc6230</a></div>
      <div class="ayar-not">Veri klasörü: ${kacir(durum.bilgi.veri_dizini)}</div>
    </div></div>`);
  const m = modal({ baslik: "Ayarlar", icerik: govde, genis: true });
  m.govde.style.padding = "0";
  const sekmeAc = (ad) => {
    $$(".sekme", govde).forEach((b) => b.classList.toggle("aktif", b.dataset.sekme === ad));
    $$("[data-panel]", govde).forEach((p) => { p.hidden = p.dataset.panel !== ad; });
  };
  $$(".sekme", govde).forEach((b) => { b.onclick = () => sekmeAc(b.dataset.sekme); });
  sekmeAc(sekme);

  const modelleriCiz = () => {
    $("#ay-modeller", govde).innerHTML = modelKartlari($("#ay-ara", govde).value, $("#ay-indirilen", govde).checked);
    $$("input[name=ay-model]", govde).forEach((r) => {
      r.onchange = async () => { await kaydet({ model: r.value }); modelleriCiz(); };
    });
  };
  $("#ay-ara", govde).oninput = modelleriCiz;
  $("#ay-indirilen", govde).onchange = modelleriCiz;
  modelleriCiz();

  const dusunmeCiz = () => {
    $("#ay-dusunme", govde).innerHTML = durum.bilgi.dusunme_secenekleri.map((d) => `<label class="secenek-kart ${d.deger === durum.ayarlar.dusunme ? "secili" : ""}">
      <input type="radio" name="ay-dus" value="${d.deger}" ${d.deger === durum.ayarlar.dusunme ? "checked" : ""}>
      <div><div class="ust">${kacir(d.ad)} <span class="rozet">${kacir(d.sure)}</span></div><div class="alt">${kacir(d.aciklama)}</div></div></label>`).join("");
    $$("input[name=ay-dus]", govde).forEach((r) => { r.onchange = async () => { await kaydet({ dusunme: r.value }); dusunmeCiz(); }; });
  };
  dusunmeCiz();

  const alanKaydet = (sec, anahtar, donustur = (v) => v) => {
    $(sec, govde).onchange = (e) => kaydet({ [anahtar]: donustur(e.target.type === "checkbox" ? e.target.checked : e.target.value) });
  };
  alanKaydet("#ay-dizin", "llm_dizin");
  alanKaydet("#ay-adres", "adres");
  alanKaydet("#ay-oto", "otomatik_baslat");
  alanKaydet("#ay-araclar", "sohbet_araclari");
  $("#ay-baglam", govde).value = String(a.baglam_token);
  alanKaydet("#ay-baglam", "baglam_token", Number);
  alanKaydet("#ay-sistem", "sistem_istemi");
  alanKaydet("#ay-sicaklik", "sicaklik", Number);
  alanKaydet("#ay-max", "max_tokens", Number);
  $("#ay-sicaklik", govde).oninput = (e) => { e.target.previousElementSibling.textContent = `Sıcaklık (${e.target.value})`; };

  $("#ay-test", govde).onclick = async (e) => {
    const b = e.currentTarget;
    const sonuc = $("#ay-test-sonuc", govde);
    b.disabled = true;
    sonuc.innerHTML = '<span class="parilti">Model hazırlanıyor ve deneniyor…</span>';
    try {
      const t = await api("/api/ayarlar/test", { method: "POST", govde: {} });
      sonuc.innerHTML = `<span class="rozet ${t.basarili ? "yesil" : "kirmizi"}">${t.basarili ? "başarılı" : "beklenmeyen cevap"}</span>
        ${kacir(JSON.stringify(t.sonuc))} · ${sayi(t.sure_sn)} sn · ${t.uretim_tok_sn ? `${sayi(t.uretim_tok_sn)} tok/sn · ` : ""}maliyet ${kacir(t.maliyet)}`;
    } catch (err) {
      sonuc.innerHTML = `<span class="rozet kirmizi">hata</span> ${kacir(err.message)}`;
    } finally {
      b.disabled = false;
      yenile();
    }
  };
  $("#ay-yukle", govde).onclick = () => modelYukle();
  $("#ay-durdur", govde).onclick = () => sunucuDurdur(false);
  $("#ay-harici", govde).onclick = () => sunucuDurdur(true);
  ikonlariYerlestir(govde);
}

export async function modelYukle(model) {
  bildir("Model yükleniyor… (30-60 sn sürebilir)", "bilgi", 3000);
  try {
    const r = await api("/api/model/hazirla", { method: "POST", govde: { model: model || null } });
    bildir(`Model hazır${r.yukleme_sn ? ` (${sayi(r.yukleme_sn)} sn)` : ""}`, "basari");
  } catch (e) {
    bildir(e.message, "hata", 8000);
  }
  yenile();
}

export async function sunucuDurdur(harici) {
  if (harici && !(await onayla("Sunucuyu kapat", "Dışarıdan (bat dosyasıyla) açılmış llama-server kapatılacak. Devam edilsin mi?", { evet: "Kapat", tehlike: true }))) return;
  try {
    await api("/api/model/durdur", { method: "POST", govde: { harici } });
    bildir("Sunucu durduruldu", "basari");
  } catch (e) {
    bildir(e.message, "hata");
  }
  yenile();
}

export function aramaAc(oturumAc) {
  const kutu = el(`<div><div class="arama-kutu">${ikon("ara")}<input placeholder="Sohbetlerde ara..." id="ar-girdi"></div><div id="ar-sonuc" style="padding-top:8px"></div></div>`);
  const m = modal({ baslik: "Ara", icerik: kutu });
  const girdi = $("#ar-girdi", kutu);
  let zaman;
  const ara = async () => {
    const liste = await api(`/api/oturumlar?q=${encodeURIComponent(girdi.value)}`).catch(() => []);
    const kap = $("#ar-sonuc", kutu);
    kap.innerHTML = liste.length ? "" : `<div class="ayar-not" style="padding:12px">Sonuç yok.</div>`;
    liste.slice(0, 40).forEach((o) => {
      const s = el(`<div class="arama-sonuc"><span>${kacir(o.baslik)}</span><span class="soluk kucuk">${kacir(o.guncelleme.slice(0, 16).replace("T", " "))}</span></div>`);
      s.onclick = () => { m.kapat(); oturumAc(o.id); };
      kap.append(s);
    });
  };
  girdi.oninput = () => { clearTimeout(zaman); zaman = setTimeout(ara, 150); };
  girdi.onkeydown = (e) => { if (e.key === "Enter") $("#ar-sonuc .arama-sonuc", kutu)?.click(); };
  ara();
  setTimeout(() => girdi.focus(), 10);
}
