// AI Ayarlari, Hakkinda ve Arama pencereleri.
import { uzantiKomutlariniYukle, uzantiSekmesiKur } from "./uzantilar.js";
import { baglayiciIceAktarCiz, EK_PANELLER, EK_SEKMELER, ekSekmeKur } from "./ayarlar2.js";
import { ikon, ikonlariYerlestir } from "./ikonlar.js";
import { kacir } from "./md.js";
import { $, $$, api, bildir, durum, el, modal, onayla, sayi, sor } from "./ortak.js";

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
    <div class="sekmeler"><button class="sekme" data-sekme="ai">AI Ayarları</button><button class="sekme" data-sekme="hafiza">Hafıza</button><button class="sekme" data-sekme="mcp">Bağlayıcılar</button><button class="sekme" data-sekme="plugin">Plugin'ler</button><button class="sekme" data-sekme="uzanti">Uzantılar</button><button class="sekme" data-sekme="hooks">Hook'lar</button>${EK_SEKMELER}<button class="sekme" data-sekme="hakkinda">Hakkında</button></div>
    <div class="modal-govde" data-panel="ai">
      <div class="ayar-grup"><label>Sağlayıcı</label>
        <label class="secenek-kart ${a.saglayici !== "openrouter" ? "secili" : ""}"><input type="radio" name="ay-sag" value="yerel" ${a.saglayici !== "openrouter" ? "checked" : ""}><div><div class="ust">Yerel (llama.cpp) <span class="rozet yesil">internetsiz</span></div>
        <div class="alt">Modeller bu bilgisayarda çalışır, veri dışarı çıkmaz. API anahtarı gerekmez.</div></div></label>
        <label class="secenek-kart ${a.saglayici === "openrouter" ? "secili" : ""}"><input type="radio" name="ay-sag" value="openrouter" ${a.saglayici === "openrouter" ? "checked" : ""}><div><div class="ust">OpenRouter <span class="rozet sari">internet</span></div>
        <div class="alt">Uzak modeller (ücretsiz ve ücretli). Mesajlar ve ekler OpenRouter'a gönderilir. API anahtarı gerekir.</div></div></label></div>
      <div class="ayar-grup" id="ay-or" ${a.saglayici === "openrouter" ? "" : "hidden"}><label>OpenRouter</label>
        <div class="satir"><span id="ay-or-anahtar" class="ayar-not"></span>
          <input class="alan" id="ay-or-yeni" type="password" autocomplete="off" placeholder="sk-or-... anahtarı yapıştır" style="flex:1">
          <button class="btn" id="ay-or-kaydet">Kaydet</button><button class="btn tehlike" id="ay-or-sil">Sil</button></div>
        <div class="satir"><input class="alan" id="ay-or-ara" placeholder="OpenRouter modeli ara..." style="flex:1">
          <label class="onay"><input type="checkbox" id="ay-or-ucretsiz" checked> Yalnız ücretsiz</label>
          <button class="btn" id="ay-or-yenile">Yenile</button></div>
        <div id="ay-or-uyari" class="ayar-not"></div>
        <div id="ay-or-modeller" class="ayar-grup" style="max-height:320px;overflow:auto"></div>
        <div class="satir"><button class="btn" id="ay-or-test"><span data-ikon="oynat"></span>Seçili OpenRouter modelini test et</button><span id="ay-or-test-sonuc" class="ayar-not">Araç tanımlı kısa bir istek atar; süre ve maliyet gösterilir.</span></div></div>
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
      <div class="anahtar-satir"><div><div>İnternet erişimi</div><div class="ayar-not">Açıkken model web'de arama yapabilir ve sayfa okuyabilir (<code>web_ara</code>, <code>web_getir</code>). Her istek yine onay ister; yerel ağ adresleri okunmaz. Kurum politikası kapattıysa açılamaz.</div></div>
        <label class="anahtar"><input type="checkbox" id="ay-ag" ${a.ag_acik ? "checked" : ""}><span></span></label></div>
      <div class="anahtar-satir"><div><div>Tarayıcı kontrolü</div><div class="ayar-not">Proje açıkken ajan ayrı bir tarayıcı profiliyle (senin Chrome profilin, çerezlerin ve şifrelerin değil) sayfa açabilir, form doldurabilir, tıklayabilir, ekran görüntüsü alabilir. Dış sitelerde her tıklama ve yazma ayrıca onay ister. Acil durdurma: sohbette <code>/browser kapat</code>.</div></div>
        <label class="anahtar"><input type="checkbox" id="ay-tarayici" ${a.tarayici_acik ? "checked" : ""}><span></span></label></div>
      <div class="ayar-grup"><label>Masaüstü kontrolü: izinli programlar</label>
        <input class="alan" id="ay-masaustu" placeholder="ör. notepad.exe, calc.exe (boş: kapalı)" value="${kacir((a.masaustu_izinli || []).join(", "))}">
        <div class="ayar-not">Ajan yalnız bu programların pencerelerini görebilir; her tıklama ve yazma onay ister. Yönetici onayı (UAC) ve kilit ekranı kontrol edilemez. Acil durdurma: sohbette <code>/masaustu durdur</code>.</div></div>
      <div class="ayar-grup"><label>Sistem istemi (isteğe bağlı)</label><textarea class="alan" id="ay-sistem" rows="3" placeholder="Örn: Her zaman Türkçe ve kısa cevap ver.">${kacir(a.sistem_istemi)}</textarea></div>
      <div class="satir"><div class="ayar-grup" style="flex:1"><label>Sıcaklık (${a.sicaklik})</label><input type="range" id="ay-sicaklik" min="0" max="1.5" step="0.1" value="${a.sicaklik}"></div>
        <div class="ayar-grup" style="flex:1"><label>En fazla cevap token</label><input class="alan" id="ay-max" type="number" min="16" max="8192" value="${a.max_tokens}"></div></div>
      <div class="ayar-grup" id="ay-agecidi"><label>Yerel sunucu (Ollama gibi): modelleri diğer uygulamalar kullansın</label>
        <div class="anahtar-satir"><div><div>Sunucuyu aç</div><div class="ayar-not">Studio açıkken buradaki modeller <b>Ollama uyumlu</b> ve <b>OpenAI uyumlu</b> adresten diğer uygulamalara sunulur. İstenen model kapalıysa Studio açar; ayrı bir Ollama gerekmez. Yalnız bu bilgisayardan erişilir.</div></div>
          <label class="anahtar"><input type="checkbox" id="ay-sunucu-acik" ${a.sunucu_acik ? "checked" : ""}><span></span></label></div>
        <div class="satir"><label class="soluk kucuk" for="ay-sunucu-port">Port</label><input class="alan" id="ay-sunucu-port" type="number" min="1024" max="65535" value="${a.sunucu_port}" style="max-width:140px">
          <span class="ayar-not">11434 = Ollama'nın portu (Ollama destekli uygulamalar ayar değiştirmeden bağlanır)</span></div>
        <div id="ay-sunucu-durum"></div>
      </div>
      <div class="ayar-grup"><label>Sunucu</label><div class="satir">
        <button class="btn" id="ay-yukle"><span data-ikon="guc"></span>Modeli şimdi yükle</button>
        <button class="btn" id="ay-durdur"><span data-ikon="durdur"></span>Sunucuyu durdur</button>
        <button class="btn tehlike" id="ay-harici" ${s.sunucu_acik && !s.bizim_sunucu ? "" : "hidden"}>Dışarıdan açılmış sunucuyu kapat</button></div></div>
    </div>
    <div class="modal-govde" data-panel="hafiza" hidden>
      <div class="anahtar-satir"><div><div>Hafızayı kullan</div><div class="ayar-not">Kayıtlı notlar sohbete ve ajan görevlerine eklenir. Notlar doğrulanmamış bilgi sayılır, kanıt yerine geçmez. Sohbeti temizlemek hafızayı silmez.</div></div>
        <label class="anahtar"><input type="checkbox" id="hf-acik" ${a.hafiza_acik ? "checked" : ""}><span></span></label></div>
      <div class="anahtar-satir"><div><div>Otomatik öğrenme</div><div class="ayar-not">Ajan, işine yarayacak kalıcı proje bilgilerini kendisi not edebilir (düşük güvenle). Gizli bilgi içeren not hiçbir zaman kaydedilmez.</div></div>
        <label class="anahtar"><input type="checkbox" id="hf-ogrenme" ${a.otomatik_ogrenme ? "checked" : ""}><span></span></label></div>
      <div class="satir"><input class="alan" id="hf-yeni" placeholder="Yeni not: ör. Testler pytest -q ile çalışır" style="flex:1" maxlength="1000">
        <button class="btn" id="hf-ekle">Ekle</button><button class="btn" id="hf-disa">Dışa aktar</button></div>
      <div id="hf-liste" class="ayar-grup"></div>
    </div>
    <div class="modal-govde" data-panel="mcp" hidden>
      <div class="ayar-not">MCP sunucusu, modele yeni araçlar verir (ör. veritabanı, takvim). Sunucu bu bilgisayarda bir komut olarak çalışır. Araçları <code>mcp__sunucu__arac</code> adıyla görünür. İşaretlemediğin her araç çağrısı onay ister; ortam değişkenlerindeki anahtarlar yalnız burada saklanır, modele gitmez.</div>
      <div class="satir"><input class="alan" id="mc-ad" placeholder="ad (ör. dosyalar)" style="max-width:150px" maxlength="32">
        <input class="alan" id="mc-komut" placeholder="Komut (ör. npx)" style="max-width:160px" maxlength="500">
        <input class="alan" id="mc-arg" placeholder="Argümanlar (boşlukla)" style="flex:1"></div>
      <div class="satir"><input class="alan" id="mc-url" placeholder="ya da uzak sunucu adresi: https://..." style="flex:1">
        <input class="alan" id="mc-baslik" type="password" placeholder="Authorization (ör. Bearer ...)" style="max-width:220px" autocomplete="off"></div>
      <div class="satir"><input class="alan" id="mc-ortam" placeholder="Ortam: ANAHTAR=deger, ANAHTAR2=deger" style="flex:1" autocomplete="off">
        <button class="btn" id="mc-ekle">Ekle</button></div>
      <div id="mc-liste" class="ayar-grup"></div>
    </div>
    <div class="modal-govde" data-panel="uzanti" hidden>
      <div class="ayar-not">Uzantı, uygulamaya yeni <b>komut</b>, <b>panel</b>, <b>olay dinleyici</b> ya da <b>araç</b> ekler. Ayrı bir süreçte çalışır ve yalnız ilan ettiği yetenekleri kullanabilir; araçları her çağrıda onay ister. Kurulumdan önce karantinada incelenir.</div>
      <div class="satir"><input class="alan" id="uz-yol" placeholder="Uzantı klasörü (uzanti.json içeren)" style="flex:1">
        <button class="btn" id="uz-incele">Karantinaya al ve incele</button></div>
      <div id="uz-rapor"></div>
      <div id="uz-liste" class="ayar-grup"></div>
    </div>
    <div class="modal-govde" data-panel="plugin" hidden>
      <div class="ayar-not">Plugin, skill paketi getirir. Önce <b>karantinaya</b> alınır ve dosyaları incelenir; içindeki kurulum scriptleri hiçbir zaman çalıştırılmaz. Raporu okuyup sen onaylarsan kurulur. Her sürüm saklanır, önceki sürüme geri dönülebilir.</div>
      <div class="satir"><input class="alan" id="pl-yol" placeholder="Plugin klasörü (plugin.json içeren)" style="flex:1">
        <button class="btn" id="pl-incele">Karantinaya al ve incele</button></div>
      <div class="satir"><input class="alan" id="pl-git" placeholder="Git adresi (https://github.com/..) ya da marketplace klasörü/adresi" style="flex:1">
        <button class="btn" id="pl-git-incele">Git'ten incele</button><button class="btn" id="pl-pazar">Marketplace aç</button></div>
      <div class="satir"><button class="btn" id="pl-cc">Claude Code'dan içe aktar</button><button class="btn" id="pl-esitle">Şimdi eşitle</button><span class="soluk kucuk">Claude Code'daki plugin'ler açılışta otomatik içe aktarılır; hook ve MCP sen açana kadar kapalı kalır.</span></div>
      <div id="pl-secim"></div>
      <div id="pl-rapor"></div>
      <div id="pl-liste" class="ayar-grup"></div>
    </div>
    <div class="modal-govde" data-panel="hooks" hidden>
      <div class="ayar-not">Hook, bir olayda (ör. araç çalışmadan önce) bu bilgisayarda çalışan komuttur. Olay bilgisini JSON olarak stdin'den alır (sırlar maskeli). Çıkış kodu 2 işlemi <b>engeller</b>. <b>Güvenlik</b> hook'u hata verir ya da zaman aşımına uğrarsa da engeller; <b>bilgi</b> hook'u yalnız kaydedilir. Komut senin yetkilerinle çalışır.</div>
      <div class="satir"><input class="alan" id="hk-ad" placeholder="Ad" style="max-width:140px" maxlength="80">
        <select class="secim" id="hk-olay" aria-label="Olay"></select>
        <select class="secim" id="hk-tur" aria-label="Tür"><option value="bilgi">bilgi</option><option value="guvenlik">güvenlik</option></select>
        <input class="alan" id="hk-arac" placeholder="Araç (boş: hepsi)" style="max-width:150px" maxlength="80"></div>
      <div class="satir"><input class="alan" id="hk-komut" placeholder="Komut, ör. python C:\\hooks\\kontrol.py" style="flex:1" maxlength="2000">
        <input class="alan" id="hk-sure" type="number" min="1" max="120" value="10" style="max-width:80px" aria-label="Zaman aşımı (sn)">
        <button class="btn" id="hk-ekle">Ekle</button></div>
      <div id="hk-liste" class="ayar-grup"></div>
    </div>
    ${EK_PANELLER}
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
  ekSekmeKur(govde, kaydet);

  // ---- Hafıza ----
  const hafizaCiz = async () => {
    const kap = $("#hf-liste", govde);
    try {
      const { kayitlar } = await api("/api/hafiza");
      kap.innerHTML = kayitlar.map((k) => `<div class="secenek-kart ${k.aktif ? "" : "pasif"}" data-id="${kacir(k.id)}">
        <div style="flex:1"><div class="ust"><span class="hf-metin">${kacir(k.metin)}</span></div>
        <div class="alt"><span class="rozet">${kacir(k.kapsam)}</span> <span class="rozet">${kacir(k.kaynak)}</span> <span class="rozet">güven: ${kacir(k.guven)}</span> ${kacir(k.tarih.slice(0, 10))}${k.gecerlilik ? ` · ${kacir(k.gecerlilik)} tarihine kadar` : ""}</div></div>
        <button class="btn" data-is="duzelt">Düzelt</button><button class="btn" data-is="ac">${k.aktif ? "Kapat" : "Aç"}</button><button class="btn tehlike" data-is="sil">Sil</button></div>`).join("")
        || '<div class="ayar-not">Henüz not yok.</div>';
      $$("[data-id]", kap).forEach((kart) => {
        const id = kart.dataset.id;
        const kayit = kayitlar.find((k) => k.id === id);
        $$("[data-is]", kart).forEach((b) => {
          b.onclick = async () => {
            try {
              if (b.dataset.is === "sil") {
                if (!(await onayla("Notu sil", "Bu hafıza notu kalıcı olarak silinsin mi?", { evet: "Sil", tehlike: true }))) return;
                await api(`/api/hafiza/${id}`, { method: "DELETE" });
              } else if (b.dataset.is === "ac") {
                await api(`/api/hafiza/${id}`, { method: "PATCH", govde: { aktif: !kayit.aktif } });
              } else {
                const yeni = await sor("Notu düzelt", kayit.metin);
                if (!yeni || yeni === kayit.metin) return;
                await api(`/api/hafiza/${id}`, { method: "PATCH", govde: { metin: yeni } });
              }
              hafizaCiz();
            } catch (err) { bildir(err.message, "hata"); }
          };
        });
      });
    } catch (err) {
      kap.innerHTML = `<span class="rozet kirmizi">hata</span> ${kacir(err.message)}`;
    }
  };
  $("#hf-acik", govde).onchange = (e) => kaydet({ hafiza_acik: e.target.checked });
  $("#hf-ogrenme", govde).onchange = (e) => kaydet({ otomatik_ogrenme: e.target.checked });
  $("#hf-ekle", govde).onclick = async () => {
    const g = $("#hf-yeni", govde);
    if (!g.value.trim()) return;
    try {
      await api("/api/hafiza", { method: "POST", govde: { metin: g.value.trim() } });
      g.value = "";
      hafizaCiz();
    } catch (err) { bildir(err.message, "hata"); }
  };
  $("#hf-disa", govde).onclick = async () => {
    try {  // oturum basligi gerektigi icin duz <a download> kullanilamaz
      const veri = await api("/api/hafiza-disa-aktar");
      const url = URL.createObjectURL(new Blob([JSON.stringify(veri, null, 1)], { type: "application/json" }));
      const a = Object.assign(document.createElement("a"), { href: url, download: "hafiza.json" });
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) { bildir(err.message, "hata"); }
  };
  hafizaCiz();

  // ---- Hook'lar ----
  const hookCiz = async () => {
    const kap = $("#hk-liste", govde);
    try {
      const { hooks, olaylar } = await api("/api/hooks");
      const sec = $("#hk-olay", govde);
      if (!sec.options.length) sec.innerHTML = olaylar.map((o) => `<option>${kacir(o)}</option>`).join("");
      kap.innerHTML = hooks.map((h) => `<div class="secenek-kart ${h.aktif ? "" : "pasif"}" data-hk="${kacir(h.id)}">
        <div style="flex:1"><div class="ust"><b>${kacir(h.ad)}</b> <span class="rozet">${kacir(h.olay)}</span>
          <span class="rozet ${h.tur === "guvenlik" ? "kirmizi" : ""}">${kacir(h.tur)}</span>${h.arac ? ` <span class="rozet">${kacir(h.arac)}</span>` : ""}</div>
          <div class="alt"><code>${kacir(h.komut)}</code> · ${kacir(h.timeout)} sn</div><div class="alt hk-sonuc"></div></div>
        <button class="btn" data-is="test">Test et</button><button class="btn" data-is="ac">${h.aktif ? "Kapat" : "Aç"}</button><button class="btn tehlike" data-is="sil">Sil</button></div>`).join("")
        || '<div class="ayar-not">Henüz hook yok.</div>';
      $$("[data-hk]", kap).forEach((kart) => {
        const id = kart.dataset.hk;
        const h = hooks.find((x) => x.id === id);
        $$("[data-is]", kart).forEach((b) => {
          b.onclick = async () => {
            try {
              if (b.dataset.is === "test") {
                const t = await api(`/api/hooks/${id}/test`, { method: "POST" });
                $(".hk-sonuc", kart).textContent = `Test: ${t.durum}${t.mesaj ? " - " + t.mesaj : ""}`;
                return;
              }
              if (b.dataset.is === "sil") {
                if (!(await onayla("Hook'u sil", "Bu hook silinsin mi?", { evet: "Sil", tehlike: true }))) return;
                await api(`/api/hooks/${id}`, { method: "DELETE" });
              } else {
                await api(`/api/hooks/${id}`, { method: "PUT", govde: { aktif: !h.aktif } });
              }
              hookCiz();
            } catch (err) { bildir(err.message, "hata"); }
          };
        });
      });
    } catch (err) { kap.innerHTML = `<span class="rozet kirmizi">hata</span> ${kacir(err.message)}`; }
  };
  $("#hk-ekle", govde).onclick = async () => {
    const d = (id) => $(id, govde).value.trim();
    try {
      await api("/api/hooks", { method: "POST", govde: { ad: d("#hk-ad"), olay: d("#hk-olay"), tur: d("#hk-tur"), arac: d("#hk-arac"), komut: d("#hk-komut"), timeout: Number(d("#hk-sure")) || 10 } });
      $("#hk-komut", govde).value = "";
      $("#hk-ad", govde).value = "";
      hookCiz();
    } catch (err) { bildir(err.message, "hata"); }
  };
  hookCiz();

  // ---- MCP bağlayıcıları ----
  const mcpCiz = async () => {
    const kap = $("#mc-liste", govde);
    try {
      const { sunucular } = await api("/api/mcp");
      kap.innerHTML = sunucular.map((s) => `<div class="secenek-kart ${s.aktif ? "" : "pasif"}" data-mc="${kacir(s.ad)}">
        <div style="flex:1"><div class="ust"><b>${kacir(s.ad)}</b> ${s.uzak ? `<span class="rozet sari" title="Araç çağrılarında veri bu bilgisayardan çıkar">uzak</span> <code class="soluk">${kacir(s.url)}</code>` : `<code class="soluk">${kacir([s.komut, ...s.argumanlar].join(" "))}</code>`}</div>
          <div class="alt mc-araclar">${Object.keys(s.ortam).length ? `ortam: ${kacir(Object.keys(s.ortam).join(", "))} (gizli) · ` : ""}Araçları görmek için Bağlan.</div></div>
        <button class="btn" data-is="test">Bağlan</button><button class="btn" data-is="ac">${s.aktif ? "Kapat" : "Aç"}</button><button class="btn tehlike" data-is="sil">Sil</button></div>`).join("")
        || '<div class="ayar-not">Henüz bağlayıcı yok.</div>';
      $$("[data-mc]", kap).forEach((kart) => {
        const ad = kart.dataset.mc;
        const s = sunucular.find((x) => x.ad === ad);
        $$("[data-is]", kart).forEach((b) => {
          b.onclick = async () => {
            try {
              if (b.dataset.is === "test") {
                b.disabled = true;
                const t = await api(`/api/mcp/${ad}/test`, { method: "POST" });
                const alan = $(".mc-araclar", kart);
                alan.innerHTML = t.araclar.map((a) => `<label class="onay"><input type="checkbox" data-arac="${kacir(a)}" ${s.izinli_araclar.includes(a) ? "checked" : ""}> ${kacir(a)}</label>`).join(" ")
                  + (s.uzak ? '<div class="soluk kucuk">Uzak sunucu: her araç çağrısı onay ister (veri dışarı gider).</div>' : '<div class="soluk kucuk">İşaretli araçlar onaysız çalışır (yalnız okuma yapan araçları işaretle).</div>') + (t.kaynaklar?.length ? `<div class="soluk kucuk">Kaynaklar: ${kacir(t.kaynaklar.join(", "))}</div>` : "");
                $$("[data-arac]", alan).forEach((c) => {
                  c.onchange = async () => {
                    const izinli = $$("[data-arac]:checked", alan).map((x) => x.dataset.arac);
                    try { await api(`/api/mcp/${ad}`, { method: "PUT", govde: { izinli_araclar: izinli } }); s.izinli_araclar = izinli; } catch (err) { bildir(err.message, "hata"); }
                  };
                });
                b.disabled = false;
                return;
              }
              if (b.dataset.is === "sil") {
                if (!(await onayla("Bağlayıcıyı sil", `${ad} silinsin mi?`, { evet: "Sil", tehlike: true }))) return;
                await api(`/api/mcp/${ad}`, { method: "DELETE" });
              } else {
                await api(`/api/mcp/${ad}`, { method: "PUT", govde: { aktif: !s.aktif } });
              }
              mcpCiz();
            } catch (err) { b.disabled = false; bildir(err.message, "hata"); }
          };
        });
      });
    } catch (err) { kap.innerHTML = `<span class="rozet kirmizi">hata</span> ${kacir(err.message)}`; }
  };
  $("#mc-ekle", govde).onclick = async () => {
    const d = (id) => $(id, govde).value.trim();
    const ortam = Object.fromEntries(d("#mc-ortam").split(",").map((x) => x.trim()).filter((x) => x.includes("=")).map((x) => [x.slice(0, x.indexOf("=")).trim(), x.slice(x.indexOf("=") + 1).trim()]));
    try {
      await api("/api/mcp", { method: "POST", govde: { ad: d("#mc-ad"), komut: d("#mc-komut"), argumanlar: d("#mc-arg").split(/\s+/).filter(Boolean), url: d("#mc-url"), basliklar: d("#mc-baslik") ? { Authorization: d("#mc-baslik") } : {}, ortam } });
      ["#mc-ad", "#mc-komut", "#mc-arg", "#mc-ortam", "#mc-url", "#mc-baslik"].forEach((x) => { $(x, govde).value = ""; });
      mcpCiz();
    } catch (err) { bildir(err.message, "hata"); }
  };
  mcpCiz();
  baglayiciIceAktarCiz(govde, mcpCiz);

  // ---- Plugin'ler ----
  const bilesenOzet = (b) => {
    if (!b) return "";
    const parca = [b.skill && `${b.skill} skill`, b.komut?.length && `komut: ${b.komut.map((x) => "/" + x).join(" ")}`,
      b.ajan?.length && `ajan: ${b.ajan.join(", ")}`, b.hook && `${b.hook} hook`, b.mcp?.length && `MCP: ${b.mcp.join(", ")}`].filter(Boolean);
    return `<div class="soluk kucuk">${kacir(parca.join(" · "))}</div>${b.desteklenmeyen?.length ? `<div class="soluk kucuk">Desteklenmeyen: ${kacir(b.desteklenmeyen.join("; "))}</div>` : ""}`;
  };
  const pluginCiz = async () => {
    const kap = $("#pl-liste", govde);
    try {
      const { pluginler } = await api("/api/pluginler");
      kap.innerHTML = pluginler.map((p) => `<div class="secenek-kart ${p.acik ? "" : "pasif"}" data-pl="${kacir(p.ad)}">
        <div style="flex:1"><div class="ust"><b>${kacir(p.ad)}</b> <span class="rozet">v${kacir(p.aktif)}</span>${p.onceki ? ` <span class="soluk kucuk">önceki: v${kacir(p.onceki)}</span>` : ""}</div>
        <div class="alt">${kacir(p.aciklama)}</div>${bilesenOzet(p.bilesenler)}
        ${p.bilesenler?.hook ? `<label class="kucuk"><input type="checkbox" data-bil="hooks" ${p.hooks_acik ? "checked" : ""}> Hook'ları çalıştır (${p.bilesenler.hook})</label> ` : ""}${p.bilesenler?.mcp?.length ? `<label class="kucuk"><input type="checkbox" data-bil="mcp" ${p.mcp_acik ? "checked" : ""}> MCP sunucularını aç (${kacir(p.bilesenler.mcp.join(", "))})</label>` : ""}</div>
        ${p.onceki ? '<button class="btn" data-is="geri">Geri al</button>' : ""}<button class="btn" data-is="ac">${p.acik ? "Kapat" : "Aç"}</button><button class="btn tehlike" data-is="sil">Kaldır</button></div>`).join("")
        || '<div class="ayar-not">Kurulu plugin yok.</div>';
      $$("[data-pl]", kap).forEach((kart) => {
        const ad = kart.dataset.pl;
        const p = pluginler.find((x) => x.ad === ad);
        $$("[data-bil]", kart).forEach((c) => {
          c.onchange = async () => {
            try { await api(`/api/pluginler/${ad}/bilesen`, { method: "PUT", govde: { tur: c.dataset.bil, acik: c.checked } }); bildir("Kaydedildi.", "basari", 1000); } catch (err) { bildir(err.message, "hata"); c.checked = !c.checked; }
          };
        });
        $$("[data-is]", kart).forEach((b) => {
          b.onclick = async () => {
            try {
              if (b.dataset.is === "geri") await api(`/api/pluginler/${ad}/geri-al`, { method: "POST" });
              else if (b.dataset.is === "ac") await api(`/api/pluginler/${ad}/durum`, { method: "PUT", govde: { acik: !p.acik } });
              else {
                if (!(await onayla("Plugin'i kaldır", `${ad} ve tüm sürümleri silinsin mi?`, { evet: "Kaldır", tehlike: true }))) return;
                await api(`/api/pluginler/${ad}`, { method: "DELETE" });
              }
              pluginCiz();
            } catch (err) { bildir(err.message, "hata"); }
          };
        });
      });
    } catch (err) { kap.innerHTML = `<span class="rozet kirmizi">hata</span> ${kacir(err.message)}`; }
  };
  const plIncele = async (istek) => {
    const rapor = $("#pl-rapor", govde);
    try {
      const k = await istek();
      const r = k.rapor;
      rapor.innerHTML = `<div class="kart"><div class="kart-baslik"><b>${kacir(k.manifest.name)} v${kacir(k.manifest.version)}</b><span class="soluk kucuk">${kacir(r.dosya_sayisi)} dosya · ${kacir(Math.round(r.toplam_bayt / 1024))} KB</span></div>
        <div>${kacir(k.manifest.description)}</div>${bilesenOzet(k.bilesenler)}
        ${r.kurulum_scriptleri.length ? `<div class="uyari-kutu kucuk">Kurulum scriptleri (ÇALIŞTIRILMAYACAK): ${kacir(r.kurulum_scriptleri.join(", "))}</div>` : ""}
        ${r.riskler.length ? `<div class="uyari-kutu kucuk"><b>Dikkat:</b><ul>${r.riskler.map((x) => `<li><code>${kacir(x.dosya)}</code> ${kacir(x.neden)}</li>`).join("")}</ul></div>` : '<div class="soluk kucuk">Bilinen riskli desen bulunmadı (bu bir güvenlik garantisi değildir).</div>'}
        <details><summary class="kucuk">Dosyalar</summary><ul class="kucuk">${r.dosyalar.map((f) => `<li><code>${kacir(f.dosya)}</code> <span class="soluk">${kacir(f.sha256)}</span></li>`).join("")}</ul></details>
        <div class="dugme-sira"><button class="btn ana" id="pl-kur">İnceledim, kur</button></div></div>`;
      $("#pl-kur", rapor).onclick = async () => {
        try { await api("/api/pluginler/kur", { method: "POST", govde: { karantina: k.karantina } }); rapor.innerHTML = ""; bildir("Plugin kuruldu.", "basari", 1500); pluginCiz(); uzantiKomutlariniYukle(); } catch (err) { bildir(err.message, "hata"); }
      };
    } catch (err) { rapor.innerHTML = `<div class="uyari-kutu kucuk">${kacir(err.message)}</div>`; }
  };
  $("#pl-incele", govde).onclick = () => plIncele(() => api("/api/pluginler/karantina", { method: "POST", govde: { yol: $("#pl-yol", govde).value.trim() } }));
  const secimCiz = (baslik, ogeler, istek) => {
    const kap = $("#pl-secim", govde);
    kap.innerHTML = `<div class="ayar-grup"><b class="kucuk">${kacir(baslik)}</b>${ogeler.map((x, i) => `<div class="satir"><span style="flex:1">${kacir(x.ad)} <span class="soluk kucuk">${kacir(x.alt || "")}</span></span><button class="btn" data-sec="${i}" ${x.bos ? "disabled" : ""}>${x.bos ? "boş" : "İncele"}</button></div>`).join("") || '<div class="ayar-not">Bulunamadı.</div>'}</div>`;
    $$("[data-sec]", kap).forEach((b) => { b.onclick = () => plIncele(() => istek(ogeler[+b.dataset.sec])); });
  };
  $("#pl-cc", govde).onclick = async () => {
    try {
      const { pluginler } = await api("/api/pluginler/claude-code");
      secimCiz("Claude Code'da kurulu plugin'ler", pluginler.map((p) => ({ ...p, alt: `${p.surum} ${p.esitleme === "kuruldu" ? "· kurulu" : p.esitleme === "inceleme" ? "· onay bekliyor" : ""}` })), (p) => api("/api/pluginler/karantina", { method: "POST", govde: { yol: p.yol, ad: p.ad } }));
    } catch (err) { bildir(err.message, "hata"); }
  };
  $("#pl-esitle", govde).onclick = async () => {
    try {
      const o = await api("/api/pluginler/claude-code/esitle", { method: "POST" });
      bildir(`Kuruldu/güncellendi: ${o.kuruldu?.length || 0}, onay bekleyen: ${o.inceleme?.length || 0}${o.hata?.length ? `, hata: ${o.hata.length}` : ""}`, "basari", 2500);
      pluginCiz(); uzantiKomutlariniYukle();
    } catch (err) { bildir(err.message, "hata"); }
  };
  $("#pl-git-incele", govde).onclick = () => plIncele(() => api("/api/pluginler/git", { method: "POST", govde: { url: $("#pl-git", govde).value.trim() } }));
  $("#pl-pazar", govde).onclick = async () => {
    const kaynak = $("#pl-git", govde).value.trim();
    try {
      const m = await api("/api/pluginler/marketplace", { method: "POST", govde: { kaynak } });
      secimCiz(`Marketplace: ${m.ad}`, m.pluginler.map((p) => ({ ad: p.name, alt: p.description })), (p) => api("/api/pluginler/marketplace/kur", { method: "POST", govde: { kaynak, ad: p.ad } }));
    } catch (err) { bildir(err.message, "hata"); }
  };
  api("/api/pluginler/katalog").then(({ katalog }) => {
    if (!katalog.length) return;
    const kat = el(`<div class="ayar-grup"><b class="kucuk">Katalog (kilitli sürüm ve hash)</b>${katalog.map((x) => `<div class="satir"><span>${kacir(x.name)} v${kacir(x.version)}</span><button class="btn" data-kat="${kacir(x.name)}">İncele</button></div>`).join("")}</div>`);
    $$("[data-kat]", kat).forEach((b) => { b.onclick = () => plIncele(() => api(`/api/pluginler/katalog/${b.dataset.kat}`, { method: "POST" })); });
    $("#pl-liste", govde).before(kat);
  }).catch(() => {});
  pluginCiz();
  uzantiSekmesiKur(govde);

  const modelleriCiz = () => {
    $("#ay-modeller", govde).innerHTML = modelKartlari($("#ay-ara", govde).value, $("#ay-indirilen", govde).checked);
    $$("input[name=ay-model]", govde).forEach((r) => {
      r.onchange = async () => { await kaydet({ model: r.value }); modelleriCiz(); };
    });
  };
  $("#ay-ara", govde).oninput = modelleriCiz;
  $("#ay-indirilen", govde).onchange = modelleriCiz;
  modelleriCiz();

  // ---- OpenRouter ----
  let orListe = [];
  const orAnahtarCiz = async () => {
    const d = await api("/api/openrouter/anahtar");
    $("#ay-or-anahtar", govde).innerHTML = d.var ? `Anahtar: <code>${kacir(d.maskeli)}</code>` : '<span class="rozet kirmizi">anahtar yok</span>';
    $("#ay-or-sil", govde).hidden = !d.var;
  };
  const orModelleriCiz = () => {
    const kucuk = $("#ay-or-ara", govde).value.toLowerCase();
    const ucretsiz = $("#ay-or-ucretsiz", govde).checked;
    const sec = durum.ayarlar.or_model;
    const liste = orListe.filter((m) => (!ucretsiz || m.ucretsiz) && (!kucuk || `${m.ad} ${m.id}`.toLowerCase().includes(kucuk)));
    $("#ay-or-modeller", govde).innerHTML = liste.slice(0, 200).map((m) => `<label class="secenek-kart ${m.id === sec ? "secili" : ""}">
      <input type="radio" name="ay-or-model" value="${kacir(m.id)}" ${m.id === sec ? "checked" : ""}>
      <div><div class="ust">${kacir(m.ad)}
        ${m.ucretsiz ? '<span class="rozet yesil">ücretsiz</span>' : `<span class="rozet">$${m.giris_1m} / $${m.cikis_1m} (1M token)</span>`}
        <span class="rozet">context ${m.baglam.toLocaleString("tr-TR")}</span>
        <span class="rozet ${m.araclar ? "yesil" : "sari"}">${m.araclar ? "araç" : "araç yok"}</span>
        ${m.goruntu ? '<span class="rozet yesil">resim</span>' : ""}${m.json ? '<span class="rozet">JSON şema</span>' : ""}${m.dusunme ? '<span class="rozet">düşünme</span>' : ""}</div>
        <div class="alt"><code>${kacir(m.id)}</code>${m.araclar ? "" : " · sohbet araçları bu modelde çalışmaz"}</div></div></label>`).join("")
      || '<div class="ayar-not">Eşleşen model yok.</div>';
    $$("input[name=ay-or-model]", govde).forEach((r) => {
      r.onchange = async () => { await kaydet({ or_model: r.value }); orModelleriCiz(); };
    });
  };
  const orListeYukle = async (yenile = false) => {
    $("#ay-or-uyari", govde).innerHTML = '<span class="parilti">Model listesi alınıyor…</span>';
    try {
      const v = await api(`/api/openrouter/modeller${yenile ? "?yenile=true" : ""}`);
      orListe = v.modeller;
      $("#ay-or-uyari", govde).textContent = v.uyari || `${orListe.length} model · liste ${new Date(v.zaman * 1000).toLocaleString("tr-TR")}`;
    } catch (err) {
      $("#ay-or-uyari", govde).innerHTML = `<span class="rozet kirmizi">hata</span> ${kacir(err.message)}`;
    }
    orModelleriCiz();
  };
  let orYuklendi = false;
  const orPanel = () => {
    const acik = durum.ayarlar.saglayici === "openrouter";
    $("#ay-or", govde).hidden = !acik;
    if (acik && !orYuklendi) { orYuklendi = true; orAnahtarCiz(); orListeYukle(); }
  };
  $$("input[name=ay-sag]", govde).forEach((r) => {
    r.onchange = async () => {
      await kaydet({ saglayici: r.value });
      $$("input[name=ay-sag]", govde).forEach((x) => x.closest(".secenek-kart").classList.toggle("secili", x.checked));
      orPanel();
    };
  });
  $("#ay-or-kaydet", govde).onclick = async () => {
    const g = $("#ay-or-yeni", govde);
    try {
      await api("/api/openrouter/anahtar", { method: "PUT", govde: { anahtar: g.value } });
      g.value = "";
      bildir("Anahtar kaydedildi", "basari", 1500);
      orAnahtarCiz();
    } catch (err) { bildir(err.message, "hata"); }
  };
  $("#ay-or-sil", govde).onclick = async () => {
    if (!(await onayla("Anahtarı sil", "OpenRouter API anahtarı bu bilgisayardan silinsin mi?", { evet: "Sil", tehlike: true }))) return;
    await api("/api/openrouter/anahtar", { method: "DELETE" });
    orAnahtarCiz();
  };
  $("#ay-or-ara", govde).oninput = orModelleriCiz;
  $("#ay-or-ucretsiz", govde).onchange = orModelleriCiz;
  $("#ay-or-yenile", govde).onclick = () => orListeYukle(true);
  $("#ay-or-test", govde).onclick = async (e) => {
    const b = e.currentTarget;
    const sonuc = $("#ay-or-test-sonuc", govde);
    b.disabled = true;
    sonuc.innerHTML = '<span class="parilti">Deneniyor…</span>';
    try {
      const t = await api("/api/openrouter/test", { method: "POST", govde: {} });
      sonuc.innerHTML = `<span class="rozet yesil">başarılı</span> "${kacir(t.cevap)}" · ${sayi(t.sure_sn)} sn · maliyet $${t.maliyet_usd}${t.arac_cagrisi ? " · araç çağırdı" : ""}`;
    } catch (err) {
      sonuc.innerHTML = `<span class="rozet kirmizi">hata</span> ${kacir(err.message)}`;
    } finally { b.disabled = false; }
  };
  orPanel();

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
  alanKaydet("#ay-ag", "ag_acik");
  alanKaydet("#ay-tarayici", "tarayici_acik");
  alanKaydet("#ay-masaustu", "masaustu_izinli", (v) => v.split(",").map((x) => x.trim()).filter(Boolean));
  const sunucuKaydet = async (degisiklik) => { await kaydet(degisiklik); sunucuDurumuCiz(govde); };
  $("#ay-sunucu-acik", govde).onchange = (e) => sunucuKaydet({ sunucu_acik: e.target.checked });
  $("#ay-sunucu-port", govde).onchange = (e) => sunucuKaydet({ sunucu_port: Number(e.target.value) });
  sunucuDurumuCiz(govde);
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

async function sunucuDurumuCiz(govde) {
  const kap = $("#ay-sunucu-durum", govde);
  if (!kap) return;
  let s;
  try { s = await api("/api/sunucu"); } catch (e) { kap.innerHTML = `<div class="hata-kutu">${kacir(e.message)}</div>`; return; }
  const modeller = (durum.sunucu?.modeller || []).filter((m) => m.dosya_var).map((m) => m.anahtar);
  const kopya = (metin) => `<button class="btn kucuk kopya" data-metin="${kacir(metin)}">Kopyala</button>`;
  kap.innerHTML = s.acik
    ? `<div class="kart" style="padding:10px 12px;gap:8px">
        <div><span class="rozet yesil">açık</span> <span class="soluk kucuk">${s.istek_sayisi} istek karşılandı</span></div>
        <div class="satir"><span class="kucuk" style="min-width:150px">Ollama uyumlu adres</span><code>${kacir(s.ollama_adres)}</code>${kopya(s.ollama_adres)}</div>
        <div class="satir"><span class="kucuk" style="min-width:150px">OpenAI uyumlu adres</span><code>${kacir(s.openai_adres)}</code>${kopya(s.openai_adres)}</div>
        <div class="kucuk soluk">Model adları: ${modeller.map((m) => `<code>${kacir(m)}</code>`).join(" ")}</div>
        <div class="ayar-not"><b>Nasıl bağlanır?</b> GridMind: AI motoru → <i>Local model (Ollama)</i>. Ollama destekli diğer uygulamalar: ayar gerekmez. OpenAI/OpenRouter kullanan uygulamalar: temel adres = OpenAI uyumlu adres, API anahtarı herhangi bir metin, model = yukarıdaki adlardan biri. Pencereyi kapatınca sunucu da kapanır; arka planda çalıştırmak için portable klasördeki <code>Sunucu.bat</code>.</div>
        ${s.son_istekler.length ? `<div class="kucuk soluk">Son istekler: ${s.son_istekler.slice(0, 5).map((i) => `${kacir(i.zaman.slice(11, 19))} ${kacir(i.yol)} ${kacir(i.model || "")}`).join(" · ")}</div>` : ""}
      </div>`
    : `<div class="kart" style="padding:10px 12px"><span class="rozet ${s.hata ? "kirmizi" : ""}">${s.hata ? "açılamadı" : "kapalı"}</span>
        ${s.hata ? `<span class="kucuk"> ${kacir(s.hata)} Başka port seçin ya da o programı kapatıp </span><button class="btn kucuk" id="ay-sunucu-yeniden">Tekrar dene</button>` : ""}</div>`;
  kap.querySelectorAll(".kopya").forEach((b) => {
    b.onclick = async () => { await navigator.clipboard.writeText(b.dataset.metin); bildir("Kopyalandı", "basari", 1500); };
  });
  const yeniden = $("#ay-sunucu-yeniden", kap);
  if (yeniden) yeniden.onclick = async () => { await api("/api/sunucu/yeniden", { method: "POST" }).catch(() => {}); sunucuDurumuCiz(govde); };
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
