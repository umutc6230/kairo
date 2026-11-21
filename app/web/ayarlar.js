// AI Ayarlari, Hakkinda ve Arama pencereleri.
import { dikteDurumuYenile } from "./dikte.js";
import { modelSil } from "./modeller.js";
import { uzantiKomutlariniYukle, uzantiSekmesiKur } from "./uzantilar.js";
import { aracPaketleriCiz, baglayiciIceAktarCiz, EK_PANELLER, EK_SEKMELER, ekSekmeKur, githubBaglan } from "./ayarlar2.js";
import { ikon, ikonlariYerlestir } from "./ikonlar.js";
import { goreceliZaman, gorevDurumlari, oturumDurumu } from "./oturum_durumu.js";
import { kacir } from "./md.js";
import { $, $$, api, baglayiciDurumu, bildir, durum, ekAvatar, el, menuAc, modal, onayla, sayi, sor } from "./ortak.js";

let yenile = async () => {};
let modellerSayfasi = () => {};
export function ayarlarKur(cb, magaza) { yenile = cb; if (magaza) modellerSayfasi = magaza; }

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

function modelKartlari(arama) {
  const a = durum.ayarlar;
  const kucuk = arama.toLowerCase();
  return (durum.sunucu?.modeller || [])
    .filter((m) => (m.dosya_var || m.anahtar === a.model) && (!kucuk || `${m.ad} ${m.anahtar}`.toLowerCase().includes(kucuk)))
    .map((m) => `<label class="secenek-kart ${m.anahtar === a.model ? "secili" : ""} ${m.dosya_var ? "" : "pasif"}">
      <input type="radio" name="ayar-model" value="${m.anahtar}" ${m.anahtar === a.model ? "checked" : ""} ${m.dosya_var ? "" : "disabled"}>
      <div><div class="ust">${kacir(m.ad)}
        <span class="rozet">~${m.ram_gb} GB RAM</span>
        <span class="rozet yesil">ücretsiz (yerel)</span>
        <span class="rozet" title="Ayarlar > Yerel motor > Bağlam">context ${a.baglam_token}</span>
        <span class="rozet ${m.ses ? "yesil" : ""}">${m.ses ? "metin · resim · araç · ses" : "metin · resim · araç"}</span>
        ${m.dosya_var ? "" : '<span class="rozet kirmizi">dosya yok</span>'}
        ${m.dosya_var && !m.mmproj_var ? '<span class="rozet sari">görüntü modülü yok</span>' : ""}</div>
        <div class="alt">${kacir(m.aciklama)} · <code>${kacir(m.anahtar)}</code></div></div>
      ${m.dosya_var ? `<button type="button" class="ikon-btn ay-model-sil" data-sil="${kacir(m.anahtar)}" title="Bu bilgisayardan sil" aria-label="${kacir(m.ad)} modelini sil">${ikon("cop")}</button>` : ""}</label>`)
    .join("") || `<div class="ayar-not">Eşleşen model yok.</div>`;
}

export function ayarlarAc(sekme = "ai") {
  const a = durum.ayarlar;
  const s = durum.sunucu || {};
  const govde = el(`<div class="ayar-pencere">
    <div class="sekmeler" role="tablist" aria-label="Ayar bölümleri"><button class="sekme" data-sekme="ai">AI Ayarları</button><button class="sekme" data-sekme="hafiza">Hafıza</button><button class="sekme" data-sekme="mcp">Bağlayıcılar</button><button class="sekme" data-sekme="plugin">Plugin'ler</button><button class="sekme" data-sekme="uzanti">Uzantılar</button><button class="sekme" data-sekme="hooks">Hook'lar</button>${EK_SEKMELER}<button class="sekme" data-sekme="hakkinda">Hakkında</button></div>
    <div class="modal-govde" data-panel="ai">
      <nav class="ay-atla" aria-label="AI ayar bölümleri"><button type="button" data-atla="ay-b-model">Model</button><button type="button" data-atla="ay-b-dusunme">Düşünme</button><button type="button" data-atla="ay-b-yetki">Yetkiler</button><button type="button" data-atla="ay-b-cevap">Cevap</button><button type="button" data-atla="ay-b-yerel" data-yerel>Yerel motor</button></nav>
      <h3 class="ay-bolum" id="ay-b-model">Model</h3>
      <!-- 1) Ozet: su an hangi model calisiyor (Cursor/Open WebUI gibi once cevap) -->
      <div class="ay-aktif" id="ay-aktif" aria-live="polite"></div>
      <!-- 2) Saglayici: iki secenekli kisa anahtar (buyuk kartlar yerine) -->
      <div class="ay-sag-sec" role="radiogroup" aria-label="Sağlayıcı">
        <label class="ay-sag-hap"><input type="radio" name="ay-sag" value="yerel" ${a.saglayici === "yerel" ? "checked" : ""}><span>Bu bilgisayar</span><small>internetsiz · ücretsiz</small></label>
        <label class="ay-sag-hap"><input type="radio" name="ay-sag" value="openrouter" ${a.saglayici === "openrouter" ? "checked" : ""}><span>OpenRouter</span><small>bulut · yüzlerce model</small></label>
        <label class="ay-sag-hap"><input type="radio" name="ay-sag" value="ollama" ${a.saglayici === "ollama" ? "checked" : ""}><span>Ollama</span><small>yerel · ollama.com modelleri</small></label>
        <label class="ay-sag-hap"><input type="radio" name="ay-sag" value="uyumlu" ${a.saglayici === "uyumlu" ? "checked" : ""}><span>Diğer bulut</span><small>OpenAI · Gemini · Groq · …</small></label>
      </div>
      <div class="ayar-grup" id="ay-uy" ${a.saglayici === "uyumlu" ? "" : "hidden"}>
        <div class="satir"><label for="ay-uy-sid" class="ay-etiket">Sağlayıcı</label><select class="secim" id="ay-uy-sid" style="flex:1"></select></div>
        <div class="ay-anahtar-satir"><span class="ay-etiket">API anahtarı</span><span id="ay-uy-anahtar"></span>
          <span class="ay-sag-dugme"><button class="btn kucuk tehlike" id="ay-uy-sil">Sil</button></span></div>
        <div class="satir" id="ay-uy-adres-satir" hidden><input class="alan" id="ay-uy-adres" placeholder="Base URL (ör. http://127.0.0.1:1234/v1)" style="flex:1"></div>
        <div class="satir"><input class="alan" id="ay-uy-yeni" type="password" autocomplete="off" placeholder="Anahtarı yapıştır (değiştirmek için)" style="flex:1">
          <button class="btn ana" id="ay-uy-kaydet">Kaydet</button></div>
        <div class="ay-secici-ust"><input class="alan" id="ay-uy-ara" placeholder="Model ara…" style="flex:1">
          <button class="btn kucuk" id="ay-uy-yenile">Yenile</button><button class="btn kucuk ana" id="ay-uy-test">Dene</button></div>
        <div class="soluk kucuk" id="ay-uy-uyari"></div>
        <div id="ay-uy-modeller" class="ay-model-liste" role="listbox" aria-label="Sağlayıcı modelleri"></div>
        <div class="ayar-not" id="ay-uy-sonuc"></div>
        <div class="ayar-not">Anahtar bu bilgisayarda şifreli saklanır, arayüze geri gönderilmez. Düşünme seviyesi bu sağlayıcılara gönderilmez; modelin varsayılanı kullanılır.</div></div>
      <div class="ayar-grup" id="ay-ol" ${a.saglayici === "ollama" ? "" : "hidden"}>
        <div class="ay-anahtar-satir"><span class="ay-etiket">Ollama</span><span id="ay-ol-durum" class="soluk kucuk">Denetleniyor…</span>
          <span class="ay-sag-dugme"><button class="btn kucuk" id="ay-ol-magaza" title="ollama.com'da ara, indir, sil">Model mağazası</button></span></div>
        <div id="ay-ol-modeller" class="ay-model-liste" role="listbox" aria-label="Ollama modelleri"></div>
        <div class="ayar-not">Kairo, Ollama'yı kendi sunucusuyla çakışmasın diye ayrı portta başlatır (<code id="ay-ol-adres"></code>); modeller Ollama'nın kendi klasöründedir. Bağlam uzunluğu "Yerel motor" bölümündeki bağlam token değerinden alınır.</div></div>
      <div class="ayar-grup" id="ay-or" ${a.saglayici === "openrouter" ? "" : "hidden"}>
        <!-- 3) Anahtar: tek satir durum; degistirme alani yalniz istenince -->
        <div class="ay-anahtar-satir"><span class="ay-etiket">API anahtarı</span><span id="ay-or-anahtar"></span>
          <span class="ay-sag-dugme"><button class="btn kucuk" id="ay-or-degistir">Değiştir</button><button class="btn kucuk tehlike" id="ay-or-sil">Sil</button></span></div>
        <div class="satir" id="ay-or-anahtar-gir" hidden>
          <input class="alan" id="ay-or-yeni" type="password" autocomplete="off" placeholder="sk-or-... anahtarını yapıştır" style="flex:1">
          <button class="btn ana" id="ay-or-kaydet">Kaydet</button></div>
        <!-- 4) Model secici: ara + filtre cipleri + tek satirlik liste -->
        <details class="ay-secici" id="ay-or-secici">
          <summary><span>Model seç</span><span class="soluk kucuk" id="ay-or-uyari"></span></summary>
          <div class="ay-secici-ust">
            <input class="alan" id="ay-or-ara" placeholder="Model ara… (ör. deepseek, gemini, claude)" style="flex:1">
            <button class="btn kucuk" id="ay-or-yenile" title="Listeyi OpenRouter'dan yeniden al">Yenile</button></div>
          <div class="ay-filtre" role="group" aria-label="Filtreler">
            <label class="ay-cip"><input type="checkbox" id="ay-or-ucretsiz" checked> Ücretsiz</label>
            <label class="ay-cip"><input type="checkbox" data-filtre="araclar" checked> Araç kullanır</label>
            <label class="ay-cip"><input type="checkbox" data-filtre="goruntu"> Görsel okur</label>
            <label class="ay-cip"><input type="checkbox" data-filtre="dusunme"> Düşünür</label></div>
          <div id="ay-or-modeller" class="ay-model-liste" role="listbox" aria-label="OpenRouter modelleri"></div>
        </details>
        <span id="ay-or-test-sonuc" hidden></span><button id="ay-or-test" hidden></button></div>
      <div class="ayar-grup" data-yerel><label>Yerel model</label>
        <div class="satir"><input class="alan" id="ay-ara" placeholder="Model ara...">
        <label class="onay" title="Yerel modellerin hepsi ücretsizdir"><input type="checkbox" checked disabled> Yalnız ücretsiz</label>
        <button class="btn kucuk" id="ay-magaza" title="Hugging Face'te GGUF ara, bu PC'ye uygunluğunu gör, indir">Hugging Face'ten indir</button></div>
        <div id="ay-modeller" class="ayar-grup"></div></div>
      <div class="ayar-grup"><label for="ay-gorsel-saglayici">Görsel üretim</label>
        <div class="satir"><select class="secim" id="ay-gorsel-saglayici">
          ${[["otomatik", "Otomatik (Codex kuruluysa Codex, yoksa OpenRouter)"], ["codex", "Codex: ChatGPT aboneliği (Plus/Pro)"], ["openrouter", "OpenRouter: aşağıdaki model"]]
            .map(([d, ad]) => `<option value="${d}" ${(a.gorsel_saglayici || "otomatik") === d ? "selected" : ""}>${ad}</option>`).join("")}</select>
          <span class="soluk kucuk" id="ay-codex-durum"></span></div>
        <div class="satir" id="ay-gorsel-or"><input class="alan" id="ay-gorsel-model" list="ay-gorsel-liste" value="${kacir(a.gorsel_model || "")}" placeholder="Boş = görsel üretme kapalı" style="flex:1" maxlength="200">
          <label class="onay"><input type="checkbox" id="ay-gorsel-ucretsiz" checked> Yalnız ücretsiz</label>
          <button class="btn kucuk" id="ay-gorsel-yenile" title="Listeyi OpenRouter'dan yeniden al">Yenile</button></div>
        <datalist id="ay-gorsel-liste"></datalist>
        <div class="ayar-not" id="ay-gorsel-not">Sohbette "logo çiz", "görsel üret" gibi isteklerde ajan resim üretip projeye kaydeder. Codex abonelik kotanı kullanır (~1-2 dk); OpenRouter anahtar ve model ister.</div></div>
      <div class="ayar-grup"><label for="ay-video-model">Video üretim modeli (ücretli)</label>
        <div class="satir"><input class="alan" id="ay-video-model" list="ay-video-liste" value="${kacir(a.video_model || "")}" placeholder="Boş = video üretme kapalı" style="flex:1" maxlength="200">
          <button class="btn kucuk" id="ay-video-yenile" title="Listeyi OpenRouter'dan yeniden al">Yenile</button></div>
        <datalist id="ay-video-liste"></datalist>
        <div class="ayar-not" id="ay-video-not">Sohbette "video üret", "kısa klip" gibi isteklerde ajan bu modelle mp4 üretir. Her video OpenRouter bakiyenden ücret düşer; her seferinde onay sorulur.</div></div>
      <div class="ayar-grup" data-yerel><label>Test</label>
        <div class="satir"><button class="btn" id="ay-test"><span data-ikon="oynat"></span>Seçili modeli test et</button><span id="ay-test-sonuc" class="ayar-not">Uygulamanın kullandığı biçimde (JSON şema) kısa bir istek atar.</span></div></div>
      <div class="ayar-grup"><label>Yeni projeler için varsayılan modeller</label>
        <div class="satir"><input class="alan" id="ay-v-koord" list="ay-v-liste" value="${kacir(a.varsayilan_koordinator || "")}" placeholder="Koordinatör (boş: aktif model)" spellcheck="false"><input class="alan" id="ay-v-uyg" list="ay-v-liste" value="${kacir(a.varsayilan_uygulayici || "")}" placeholder="Uygulayıcı / thread (boş: aktif model)" spellcheck="false"></div>
        <datalist id="ay-v-liste"></datalist>
        <div class="ayar-not">Yeni açılan projeye bu modeller atanır: koordinatör planlar ve iş dağıtır, uygulayıcı thread'lerde kodu yazar. Proje ayrıntısından projeye özel değiştirilebilir.</div></div>
      <div class="ayar-grup"><label for="ay-gunluk-butce">Günlük bulut bütçe sınırı (USD, 0 = sınırsız)</label>
        <input class="alan" id="ay-gunluk-butce" type="number" min="0" max="1000" step="0.01" value="${a.gunluk_butce_usd ?? 0}" style="max-width:180px">
        <div class="ayar-not">Günlük bulut harcaması bu sınırı aştığında yeni sohbetler otomatik yerel modele yönlendirilir.</div></div>
      <h3 class="ay-bolum" id="ay-b-dusunme">Düşünme (effort)</h3>
      <div id="ay-dusunme-not" class="ayar-not"></div>
      <div id="ay-dusunme" class="ayar-grup secenek-sira"></div>
      <h3 class="ay-bolum" id="ay-b-yetki">Yetkiler</h3>
      <div class="ayar-not">Proje açık olmasa da model Claude Code gibi iş yapar. Okuma serbesttir; dosya yazma, komut, bağlayıcı (GitHub vb.) ve web, <b>Tam yetki</b> kapalıyken senin onayınla çalışır.</div>
      <div class="anahtar-satir tam-yetki"><div><div>Tam yetki <span class="rozet sari">onaysız</span></div><div class="ayar-not">Açıkken ajan dosya yazar, komut çalıştırır, bağlayıcıları (GitHub, MCP) ve web'i <b>sormadan</b> kullanır. Yine de sorulanlar: disk/sürücü silme, biçimlendirme, bilgisayarı kapatma, zorla git push gibi geri alınamaz komutlar ve gönderme, paylaşma, yayınlama, ödeme gibi dış etkili eylemler (onay kartında "Her zaman izin ver" dersen o tür bir daha sorulmaz). Gizli dosyalar (.env, ssh anahtarı) hiç okunmaz. Planla modu salt okunur kalır.</div></div>
        <label class="anahtar"><input type="checkbox" id="ay-tam-yetki" ${a.tam_yetki ? "checked" : ""}><span></span></label></div>
      <div class="anahtar-satir"><div><div>Sohbette araçlar</div><div class="ayar-not">Model dosyaları listeleyip okuyabilir ve arayabilir; yazma, silme ve komut Tam yetki kapalıyken onay ister. .env, ssh anahtarı, parola dosyaları hiç okunmaz.</div></div>
        <label class="anahtar"><input type="checkbox" id="ay-araclar" ${a.sohbet_araclari ? "checked" : ""}><span></span></label></div>
      <div class="anahtar-satir"><div><div>İnternet erişimi</div><div class="ayar-not">Açıkken model web'de arama yapabilir ve sayfa okuyabilir (<code>web_ara</code>, <code>web_getir</code>). Tam yetki kapalıyken her istek onay ister; yerel ağ adresleri okunmaz. Kurum politikası kapattıysa açılamaz.</div></div>
        <label class="anahtar"><input type="checkbox" id="ay-ag" ${a.ag_acik ? "checked" : ""}><span></span></label></div>
      <div class="anahtar-satir"><div><div>Sesli dikte bulutta</div><div class="ayar-not">Açıkken mikrofon kaydın aşağıdaki ayrı dikte modeline (OpenRouter, ses girişli) gönderilip yazıya dökülür; sohbette hangi model seçili olursa olsun çalışır. Kapalıyken ses bilgisayardan çıkmaz; dikte yalnız yerel Gemma 4 ile çalışır. Gönderimde sağlayıcıdan veri toplamaması istenir.</div></div>
        <label class="anahtar"><input type="checkbox" id="ay-dikte-bulut" ${a.dikte_bulut ? "checked" : ""}><span></span></label></div>
      <div class="anahtar-satir"><div><div>Dikte modeli</div><div class="ayar-not">OpenRouter model kimliği, ses girişi desteklemeli (ör. google/gemini-2.5-flash).</div></div>
        <input class="alan" id="ay-dikte-model" style="max-width:240px" value="${kacir(a.dikte_model || "")}"></div>
      <div class="anahtar-satir"><div><div>Tarayıcı kontrolü</div><div class="ayar-not">Ajan ayrı bir tarayıcı profiliyle (senin Chrome profilin, çerezlerin ve şifrelerin değil) sayfa açabilir, form doldurabilir, tıklayabilir, ekran görüntüsü alabilir. Dış sitelerde her tıklama ve yazma ayrıca onay ister. Acil durdurma: sohbette <code>/browser kapat</code>.</div></div>
        <label class="anahtar"><input type="checkbox" id="ay-tarayici" ${a.tarayici_acik ? "checked" : ""}><span></span></label></div>
      <div class="anahtar-satir"><div><div>Bilgisayar kullanımı (tüm programlar)</div><div class="ayar-not">Açıkken ajan bilgisayardaki tüm program pencerelerini görebilir, tıklayabilir ve yazabilir. Tam yetki kapalıyken her eylem onay ister. Yönetici onayı (UAC), kilit ekranı, Windows Güvenliği ve parola pencereleri hiçbir zaman kontrol edilmez. Acil durdurma: sohbette <code>/masaustu durdur</code>.</div></div>
        <label class="anahtar"><input type="checkbox" id="ay-masaustu-hepsi" ${(a.masaustu_izinli || []).includes("*") ? "checked" : ""}><span></span></label></div>
      <div class="ayar-grup" id="ay-masaustu-liste" ${(a.masaustu_izinli || []).includes("*") ? "hidden" : ""}><label>Ya da yalnız şu programlar</label>
        <input class="alan" id="ay-masaustu" placeholder="ör. notepad.exe, calc.exe (boş: kapalı)" value="${kacir((a.masaustu_izinli || []).filter((x) => x !== "*").join(", "))}"></div>
      <div class="ayar-grup"><label>Onay kuralları</label>
        <div class="ayar-not">Onay kartında "Her zaman izin ver" dediğin işlem türleri. Kaldırırsan o tür yeniden sorulur.</div>
        <div id="ay-kurallar" class="kaynak-liste"><span class="soluk kucuk">Yükleniyor…</span></div></div>
      <h3 class="ay-bolum" id="ay-b-cevap">Cevap</h3>
      <div class="ayar-grup"><label>Sistem istemi (isteğe bağlı)</label><textarea class="alan" id="ay-sistem" rows="3" placeholder="Örn: Her zaman Türkçe ve kısa cevap ver.">${kacir(a.sistem_istemi)}</textarea></div>
      <div class="satir"><div class="ayar-grup" style="flex:1"><label>Sıcaklık (${a.sicaklik})</label><input type="range" id="ay-sicaklik" min="0" max="1.5" step="0.1" value="${a.sicaklik}"></div>
        <div class="ayar-grup" style="flex:1"><label>En fazla cevap token</label><input class="alan" id="ay-max" type="number" min="16" max="8192" value="${a.max_tokens}"></div></div>
      <h3 class="ay-bolum" id="ay-b-yerel" data-yerel>Yerel motor (llama.cpp)</h3>
      <div class="ayar-grup" data-yerel><label>Model klasörü</label><input class="alan" id="ay-dizin" value="${kacir(a.llm_dizin)}">
        <div class="ayar-not">llama.cpp\\llama-server.exe ve models\\*.gguf bu klasörde olmalı. ${s.motor_var ? "✓ llama.cpp bulundu" : "✗ llama.cpp bulunamadı"}</div></div>
      <div class="ayar-grup" data-yerel><label>Bağlam boyutu</label>
        <select class="secim" id="ay-baglam"><option value="8192">8K token (en az RAM; yalnız kısa sohbet)</option><option value="16384">16K token (sohbet; ajan görevinde geçmiş kısa kalır)</option><option value="32768">32K token (ajan görevleri için önerilen; daha çok RAM)</option></select>
        <div class="ayar-not">Değişince model bir sonraki mesajda yeni bağlamla yeniden açılır. Talimat ve skill ayarları: Skill'ler ve talimatlar sayfası.</div></div>
      <div class="ayar-grup"><label>Bağlam profili</label>
        <select class="secim" id="ay-profil"><option value="otomatik">Otomatik (küçük yerel modelde hafif)</option><option value="tam">Tam: tüm araçlar, skill'ler, MCP</option><option value="hafif">Hafif: temel dosya/komut araçları, kısa talimat</option></select>
        <div class="ayar-not">Hafif profil düşük parametreli modeller içindir: skill listesi, MCP ve ek araçlar gönderilmez, Claude talimatları atlanır, proje talimatı kısaltılır. Otomatik: ~5 GB RAM ve altı yerel modelde hafif.</div></div>
      <div class="ayar-grup" data-yerel><label>Sunucu adresi</label><input class="alan" id="ay-adres" value="${kacir(a.adres)}"></div>
      <div class="anahtar-satir" data-yerel><div><div>Otomatik başlat</div><div class="ayar-not">Model kapalıysa ilk mesajda arka planda açılır; uygulama kapanınca kapanır.</div></div>
        <label class="anahtar"><input type="checkbox" id="ay-oto" ${a.otomatik_baslat ? "checked" : ""}><span></span></label></div>
      <div class="ayar-grup" id="ay-agecidi" data-yerel><label>Yerel sunucu (Ollama gibi): modelleri diğer uygulamalar kullansın</label>
        <div class="anahtar-satir"><div><div>Sunucuyu aç</div><div class="ayar-not">Studio açıkken buradaki modeller <b>Ollama uyumlu</b> ve <b>OpenAI uyumlu</b> adresten diğer uygulamalara sunulur. İstenen model kapalıysa Studio açar; ayrı bir Ollama gerekmez. Yalnız bu bilgisayardan erişilir.</div></div>
          <label class="anahtar"><input type="checkbox" id="ay-sunucu-acik" ${a.sunucu_acik ? "checked" : ""}><span></span></label></div>
        <div class="satir"><label class="soluk kucuk" for="ay-sunucu-port">Port</label><input class="alan" id="ay-sunucu-port" type="number" min="1024" max="65535" value="${a.sunucu_port}" style="max-width:140px">
          <span class="ayar-not">11434 = Ollama'nın portu (Ollama destekli uygulamalar ayar değiştirmeden bağlanır)</span></div>
        <div id="ay-sunucu-durum"></div>
      </div>
      <div class="ayar-grup" data-yerel><label>Sunucu</label><div class="satir">
        <button class="btn" id="ay-yukle"><span data-ikon="guc"></span>Modeli şimdi yükle</button>
        <button class="btn" id="ay-durdur"><span data-ikon="durdur"></span>Sunucuyu durdur</button>
        <button class="btn tehlike" id="ay-harici" ${s.sunucu_acik && !s.bizim_sunucu ? "" : "hidden"}>Dışarıdan açılmış sunucuyu kapat</button></div></div>
    </div>
    <div class="modal-govde" data-panel="hafiza" hidden>
      <div class="anahtar-satir"><div><div>Hafızayı kullan</div><div class="ayar-not">Kayıtlı notlar sohbete ve ajan görevlerine eklenir. Notlar doğrulanmamış bilgi sayılır, kanıt yerine geçmez. Sohbeti temizlemek hafızayı silmez.</div></div>
        <label class="anahtar"><input type="checkbox" id="hf-acik" ${a.hafiza_acik ? "checked" : ""}><span></span></label></div>
      <div class="anahtar-satir"><div><div>Otomatik öğrenme</div><div class="ayar-not">Ajan, işine yarayacak kalıcı proje bilgilerini kendisi not edebilir (düşük güvenle). Gizli bilgi içeren not hiçbir zaman kaydedilmez.</div></div>
        <label class="anahtar"><input type="checkbox" id="hf-ogrenme" ${a.otomatik_ogrenme ? "checked" : ""}><span></span></label></div>
      <div class="anahtar-satir"><div><div>Görev sonu otomatik inceleme</div><div class="ayar-not">Ajan dosya değiştirdiyse görev bitince değişiklikler model tarafından incelenir; ciddi bulgular sonraki görevlere ders olarak eklenir. Model çağrısı yapar.</div></div>
        <label class="anahtar"><input type="checkbox" id="hf-inceleme" ${a.otomatik_inceleme ? "checked" : ""}><span></span></label></div>
      <div class="satir"><input class="alan" id="hf-yeni" placeholder="Yeni not: ör. Testler pytest -q ile çalışır" style="flex:1" maxlength="1000">
        <button class="btn" id="hf-ekle">Ekle</button><button class="btn" id="hf-ice" title="Claude, ChatGPT ya da Grok'tan hafızanı taşı">İçe aktar</button><button class="btn" id="hf-disa">Dışa aktar</button></div>
      <div id="hf-liste" class="ayar-grup"></div>
      <div class="anahtar-satir"><div><div>Sır kasası</div><div class="ayar-not">Sohbete yapıştırdığın API anahtarları burada Windows şifrelemesiyle (DPAPI) saklanır. Modele yalnız adı gider; ajan komutlarında ortam değişkeni olarak hazırdır ve çıktıda maskelenir. Tüm oturumlarda geçerlidir.</div></div></div>
      <div id="sr-liste" class="ayar-grup"></div>
    </div>
    <div class="modal-govde ek-panel" data-panel="mcp" hidden>
      <div class="ek-panel-ust"><div><b class="ek-panel-baslik">Bağlayıcılar</b><div class="soluk kucuk">Modele yeni araçlar verir (takvim, veritabanı, GitHub…). İşaretlemediğin her araç çağrısı onay ister; anahtarlar modele gitmez.</div></div>
        <span class="ek-ozet" id="mc-ozet"></span></div>
      <div class="ek-bolum-baslik"><b>Senin bağlayıcıların</b></div>
      <div id="mc-liste" class="ek-liste"></div>
      <details class="ek-ekle"><summary><span data-ikon="arti"></span>Elle bağlayıcı ekle (komut ya da adres)</summary>
        <div class="satir"><input class="alan" id="mc-ad" placeholder="ad (ör. dosyalar)" style="max-width:150px" maxlength="32">
          <input class="alan" id="mc-komut" placeholder="Komut (ör. npx)" style="max-width:160px" maxlength="500">
          <input class="alan" id="mc-arg" placeholder="Argümanlar (boşlukla)" style="flex:1"></div>
        <div class="satir"><input class="alan" id="mc-url" placeholder="ya da uzak sunucu adresi: https://..." style="flex:1">
          <input class="alan" id="mc-baslik" type="password" placeholder="Authorization (ör. Bearer ...)" style="max-width:220px" autocomplete="off"></div>
        <div class="satir"><input class="alan" id="mc-ortam" type="password" placeholder="Ortam: ANAHTAR=deger, ANAHTAR2=deger" style="flex:1" autocomplete="off">
          <button class="btn ana" id="mc-ekle">Ekle</button></div></details>
      <div id="mc-ice"></div>
      <div id="mc-paket"></div>
    </div>
    <div class="modal-govde ek-panel" data-panel="uzanti" hidden>
      <div class="ek-panel-ust"><div><b class="ek-panel-baslik">Uzantılar</b><div class="soluk kucuk">Kairo'ya yeni komut, panel, olay dinleyici ya da araç ekler. Ayrı süreçte çalışır, yalnız ilan ettiği yetenekleri kullanır; araçları her çağrıda onay ister.</div></div></div>
      <div class="ek-bolum-baslik"><b>Kurulu uzantılar</b></div>
      <div id="uz-liste" class="ek-liste"></div>
      <details class="ek-ekle"><summary><span data-ikon="arti"></span>Uzantı ekle (klasörden, önce karantinada incelenir)</summary>
        <div class="satir"><input class="alan" id="uz-yol" placeholder="Uzantı klasörü (uzanti.json içeren)" style="flex:1">
          <button class="btn ana" id="uz-incele">Karantinaya al ve incele</button></div></details>
      <div id="uz-rapor"></div>
    </div>
    <div class="modal-govde ek-panel" data-panel="plugin" hidden>
      <div class="ek-panel-ust"><div><b class="ek-panel-baslik">Plugin'ler</b><div class="soluk kucuk">Skill, komut ve ajan paketleri. Önce karantinada incelenir; kurulum scriptleri hiç çalıştırılmaz. Her sürüm saklanır, geri alınabilir.</div></div>
        <span class="ek-ozet" id="pl-ozet"></span></div>
      <div class="ek-bolum-baslik"><b>Kurulu plugin'ler</b><span class="ek-sag"><button class="btn kucuk" id="pl-esitle" title="Claude Code'daki plugin'ler açılışta da otomatik içe aktarılır; hook ve MCP sen açana kadar kapalı kalır">Claude Code ile eşitle</button></span></div>
      <div id="pl-liste" class="ek-liste"></div>
      <details class="ek-ekle"><summary><span data-ikon="arti"></span>Plugin ekle (klasör, git, marketplace, Claude Code)</summary>
        <div class="satir"><input class="alan" id="pl-yol" placeholder="Plugin klasörü (plugin.json içeren)" style="flex:1">
          <button class="btn" id="pl-incele">Klasörü incele</button></div>
        <div class="satir"><input class="alan" id="pl-git" placeholder="Git adresi (https://github.com/..) ya da marketplace klasörü/adresi" style="flex:1">
          <button class="btn" id="pl-git-incele">Git'ten incele</button><button class="btn" id="pl-pazar">Marketplace aç</button></div>
        <div class="satir"><button class="btn" id="pl-cc">Claude Code'daki plugin'lerden seç</button></div>
        <div id="pl-secim"></div></details>
      <div id="pl-rapor"></div>
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
      <div class="satir"><button class="btn" id="ay-guncelleme-kontrol">Güncellemeleri denetle</button><span id="ay-guncelleme-sonuc" class="ayar-not"></span></div>
      <div class="ayar-not">Veri klasörü: ${kacir(durum.bilgi.veri_dizini)}</div>
    </div></div>`);
  const m = modal({ baslik: "Ayarlar", icerik: govde, genis: true });
  $(".modal", m.arka).classList.add("ayarlar"); // sol dikey sekme + sabit boy (app.css)
  const sekmeAc = (ad) => {
    $$(".sekme", govde).forEach((b) => {
      const secili = b.dataset.sekme === ad;
      b.classList.toggle("aktif", secili);
      b.setAttribute("role", "tab");
      b.setAttribute("aria-selected", String(secili));
    });
    $$("[data-panel]", govde).forEach((p) => { p.hidden = p.dataset.panel !== ad; p.scrollTop = 0; });
  };
  $$(".sekme", govde).forEach((b) => { b.onclick = () => sekmeAc(b.dataset.sekme); });
  sekmeAc(sekme);
  ekSekmeKur(govde, kaydet);

  // Ayar aramasi (openbot gibi): eslesmeyen satirlar ve sekmeler gizlenir, ilk eslesen sekme acilir
  const ara = el(`<input class="alan ayar-ara" type="search" placeholder="Ayarlarda ara…" aria-label="Ayarlarda ara">`);
  $(".sekmeler", govde).prepend(ara);
  const SATIR = ":scope > .anahtar-satir, :scope > .ayar-grup, :scope > .ay-bolum, :scope > .ayar-not, :scope > .satir, :scope > .satir-iki, :scope > .ay-sag-sec, :scope > .ay-aktif, :scope > .ek-bolum-baslik, :scope > .ek-liste, :scope > .ek-ekle";
  ara.oninput = () => {
    const q = ara.value.trim().toLocaleLowerCase("tr-TR");
    let ilk = null;
    $$("[data-panel]", govde).forEach((p) => {
      let var_ = false;
      p.querySelectorAll(SATIR).forEach((r) => {
        if (r.hidden) return;
        const uy = !q || r.textContent.toLocaleLowerCase("tr-TR").includes(q);
        r.classList.toggle("arama-gizli", !uy);
        if (uy && q && !r.classList.contains("ay-bolum")) var_ = true;
      });
      const b = $(`.sekme[data-sekme="${p.dataset.panel}"]`, govde);
      if (b) b.hidden = Boolean(q) && !var_;
      if (var_ && !ilk) ilk = p.dataset.panel;
    });
    if (ilk && $(`[data-panel="${ilk}"]`, govde).hidden) sekmeAc(ilk);
  };

  // ---- Hafıza ----
  const sirCiz = async () => {
    const kap = $("#sr-liste", govde);
    try {
      const { adlar } = await api("/api/sirlar");
      kap.innerHTML = adlar.map((ad) => `<div class="secenek-kart" data-sir="${kacir(ad)}"><div style="flex:1"><code>$${kacir(ad)}</code> <span class="soluk">••••••••</span></div><button class="btn tehlike">Sil</button></div>`).join("")
        || '<div class="ayar-not">Kayıtlı anahtar yok.</div>';
      $$("[data-sir]", kap).forEach((kart) => {
        $("button", kart).onclick = async () => {
          const ad = kart.dataset.sir;
          if (!(await onayla("Anahtarı sil", `${ad} kasadan kalıcı olarak silinsin mi? Ajan bundan sonra kullanamaz.`, { evet: "Sil", tehlike: true }))) return;
          try { await api(`/api/sirlar/${encodeURIComponent(ad)}`, { method: "DELETE" }); sirCiz(); } catch (err) { bildir(err.message, "hata"); }
        };
      });
    } catch (e) { kap.innerHTML = `<div class="ayar-not">${kacir(e.message)}</div>`; }
  };
  sirCiz();

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
  $("#hf-inceleme", govde).onchange = (e) => kaydet({ otomatik_inceleme: e.target.checked });
  $("#hf-ekle", govde).onclick = async () => {
    const g = $("#hf-yeni", govde);
    if (!g.value.trim()) return;
    try {
      await api("/api/hafiza", { method: "POST", govde: { metin: g.value.trim() } });
      g.value = "";
      hafizaCiz();
    } catch (err) { bildir(err.message, "hata"); }
  };
  $("#hf-ice", govde).onclick = () => {
    const alan = el(`<div><p class="ayar-not" style="margin-top:0">Diğer asistana (Claude, ChatGPT, Grok) "Hakkımda hatırladığın her şeyi madde madde yaz" de, cevabı buraya yapıştır. Her satır ayrı not olur; anahtar/parola içerenler ve zaten kayıtlı olanlar atlanır.</p>
      <textarea class="alan" rows="10" style="width:100%" maxlength="100000" aria-label="Aktarılacak hafıza metni"></textarea></div>`);
    const ta = $("textarea", alan);
    modal({
      baslik: "Hafızayı içe aktar",
      icerik: alan,
      genis: true,
      dugmeler: [
        { metin: "Vazgeç" },
        { metin: "Aktar", tur: "ana", eylem: async (kapat, b) => {
          if (!ta.value.trim()) return;
          b.disabled = true;
          try {
            const r = await api("/api/hafiza/ice-aktar", { method: "POST", govde: { metin: ta.value } });
            bildir(`${r.eklenen} not eklendi` + (r.atlanan ? `, ${r.atlanan} zaten vardı` : "")
              + (r.gizli ? `, ${r.gizli} gizli bilgi içerdiği için atlandı` : "")
              + (r.dolu ? ". Hafıza doldu, kalanlar eklenmedi." : ""), r.dolu ? "hata" : "basari");
            kapat();
            hafizaCiz();
          } catch (err) { bildir(err.message, "hata"); b.disabled = false; }
        } },
      ],
    });
    setTimeout(() => ta.focus(), 10);
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
  let mcpYenile = null;
  const mcpCiz = async () => {
    clearTimeout(mcpYenile);
    const kap = $("#mc-liste", govde);
    try {
      const { sunucular: hepsi } = await api("/api/mcp");
      const sunucular = hepsi.filter((s) => !s.ek); // plugin/Composio kendi yerinden yonetilir
      const SIRA = { giris: 0, hata: 1, baglaniyor: 2, bagli: 3, kapali: 4 };
      sunucular.sort((a, b) => SIRA[baglayiciDurumu(a).kod] - SIRA[baglayiciDurumu(b).kod]);
      const say = (k) => sunucular.filter((s) => baglayiciDurumu(s).kod === k).length;
      $("#mc-ozet", govde).innerHTML = [["bagli", "bağlı", "yesil"], ["giris", "giriş gerekli", "sari"], ["hata", "bağlanamadı", "kirmizi"], ["baglaniyor", "bağlanıyor", "mavi"]]
        .filter(([k]) => say(k)).map(([k, ad, sinif]) => `<span class="rozet ${sinif}">${say(k)} ${ad}</span>`).join("");
      kap.innerHTML = sunucular.map((s) => {
        const d = baglayiciDurumu(s);
        const ana = { giris: ["oauth", s.oauth?.bagli ? "Yeniden giriş" : "Giriş yap"], hata: ["test", "Yeniden dene"], bagli: ["test", "Araçlar"], kapali: ["ac", "Aç"], baglaniyor: ["", ""] }[d.kod];
        const kaynak = s.uzak ? new URL(s.url || "https://x").host : [s.komut, ...s.argumanlar].join(" ");
        return `<div class="ek-satir-sar" data-mc="${kacir(s.ad)}"><div class="ek-satir">
          ${ekAvatar(s.ad)}
          <div class="ek-govde"><div class="ek-ad">${kacir(s.ad)}${s.uzak ? ' <span class="rozet" title="Araç çağrılarında veri bu bilgisayardan çıkar">uzak</span>' : ""}</div>
            <div class="ek-alt soluk" title="${kacir(kaynak)}">${kacir(kaynak)}${Object.keys(s.ortam).length ? ` · ortam: ${kacir(Object.keys(s.ortam).join(", "))} (gizli)` : ""}</div></div>
          <span class="rozet ek-durum ${d.sinif}" title="${kacir(d.ipucu)}">${kacir(d.etiket)}</span>
          ${ana[0] ? `<button class="btn kucuk" data-is="${ana[0]}">${kacir(ana[1])}</button>` : ""}
          <button class="ikon-btn" data-ikon="daha" title="Seçenekler" data-menu></button></div>
          <div class="mc-araclar"></div></div>`;
      }).join("") || '<div class="soluk kucuk ek-bos">Henüz bağlayıcı yok. Aşağıdaki Dizin\'den ya da Claude\'dan içe aktararak ekleyebilirsin.</div>';
      ikonlariYerlestir(kap);
      if (sunucular.some((s) => baglayiciDurumu(s).kod === "baglaniyor") && kap.offsetParent) mcpYenile = setTimeout(mcpCiz, 3000);
      $$("[data-mc]", kap).forEach((kart) => {
        const ad = kart.dataset.mc;
        const s = sunucular.find((x) => x.ad === ad);
        const yap = async (is, b) => {
          try {
            if (is === "test") {
              const alan = $(".mc-araclar", kart);
              if (alan.innerHTML && b) { alan.innerHTML = ""; return; } // ikinci tiklama: araclari gizle
              if (b) b.disabled = true;
              const t = await api(`/api/mcp/${ad}/test`, { method: "POST" });
              alan.innerHTML = (t.araclar.length > 1 ? `<label class="onay mc-tumu"><input type="checkbox" data-tumu> Tümünü seç <span class="soluk kucuk">(${t.araclar.length} araç)</span></label>` : "")
                + `<div class="mc-arac-liste">${t.araclar.map((a) => `<label class="onay"><input type="checkbox" data-arac="${kacir(a)}" ${s.izinli_araclar.includes(a) ? "checked" : ""}> ${kacir(a)}</label>`).join("")}</div>`
                + (s.uzak ? '<div class="soluk kucuk">Uzak sunucu: her araç çağrısı onay ister (veri dışarı gider).</div>' : '<div class="soluk kucuk">İşaretli araçlar onaysız çalışır (yalnız okuma yapan araçları işaretle).</div>') + (t.kaynaklar?.length ? `<div class="soluk kucuk">Kaynaklar: ${kacir(t.kaynaklar.join(", "))}</div>` : "");
              const tumu = $("[data-tumu]", alan);
              const tumuGuncelle = () => {
                if (!tumu) return;
                const n = $$("[data-arac]:checked", alan).length;
                tumu.checked = n === t.araclar.length;
                tumu.indeterminate = n > 0 && n < t.araclar.length;
              };
              const kaydetIzinli = async () => {
                const izinli = $$("[data-arac]:checked", alan).map((x) => x.dataset.arac);
                try { await api(`/api/mcp/${ad}`, { method: "PUT", govde: { izinli_araclar: izinli } }); s.izinli_araclar = izinli; } catch (err) { bildir(err.message, "hata"); }
              };
              $$("[data-arac]", alan).forEach((c) => { c.onchange = () => { tumuGuncelle(); kaydetIzinli(); }; });
              if (tumu) {
                tumu.onchange = () => { $$("[data-arac]", alan).forEach((c) => { c.checked = tumu.checked; }); tumuGuncelle(); kaydetIzinli(); };
                tumuGuncelle();
              }
              if (b) b.disabled = false;
              return;
            }
            if (is === "oauth" && /githubcopilot\.com|github\.com/i.test(s.url || "")) {
              // GitHub MCP otomatik istemci kaydi (OAuth DCR) desteklemez: GitHub CLI girisiyle token baglanir
              await githubBaglan();
              mcpCiz();
              return;
            }
            if (is === "oauth") {
              await api(`/api/mcp/${ad}/oauth`, { method: "POST" });
              bildir("Tarayıcıda giriş sayfası açıldı. Giriş bitince durum kendiliğinden güncellenir.", "bilgi", 5000);
              return;
            }
            if (is === "sil") {
              if (!(await onayla("Bağlayıcıyı sil", `${ad} silinsin mi?`, { evet: "Sil", tehlike: true }))) return;
              await api(`/api/mcp/${ad}`, { method: "DELETE" });
            } else {
              await api(`/api/mcp/${ad}`, { method: "PUT", govde: { aktif: !s.aktif } });
            }
            mcpCiz();
          } catch (err) { if (b) b.disabled = false; bildir(err.message, "hata"); }
        };
        const anaB = $("[data-is]", kart);
        if (anaB) anaB.onclick = () => yap(anaB.dataset.is, anaB);
        $("[data-menu]", kart).onclick = (e) => menuAc(e.currentTarget, [
          { metin: "Bağlantıyı dene ve araçları göster", ikon: "oynat", eylem: () => yap("test") },
          ...(s.uzak ? [{ metin: s.oauth?.bagli ? "Yeniden giriş yap" : "Tarayıcıda giriş yap", ikon: "anahtar", eylem: () => yap("oauth") }] : []),
          { metin: s.aktif ? "Kapat" : "Aç", ikon: "guc", eylem: () => yap("ac") },
          "ayrac",
          { metin: "Sil", ikon: "cop", tehlike: true, eylem: () => yap("sil") },
        ], { sagaHizali: true });
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
  aracPaketleriCiz(govde, mcpCiz); // prepend: ice aktarmanin USTUNDE gorunur

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
      const acik = pluginler.filter((p) => p.acik).length;
      $("#pl-ozet", govde).innerHTML = pluginler.length ? `<span class="rozet yesil">${acik} açık</span>${pluginler.length - acik ? ` <span class="rozet">${pluginler.length - acik} kapalı</span>` : ""}` : "";
      kap.innerHTML = pluginler.map((p) => `<div class="ek-satir-sar" data-pl="${kacir(p.ad)}"><div class="ek-satir">
        ${ekAvatar(p.ad)}
        <div class="ek-govde"><div class="ek-ad">${kacir(p.ad)} <span class="soluk kucuk">v${kacir(p.aktif)}</span></div>
          <div class="ek-alt soluk" title="${kacir(p.aciklama)}">${kacir(p.aciklama || "")}</div></div>
        <span class="rozet ek-durum ${p.acik ? "yesil" : ""}">${p.acik ? "Açık" : "Kapalı"}</span>
        <button class="btn kucuk" data-is="detay">Ayrıntılar</button>
        <button class="ikon-btn" data-ikon="daha" title="Seçenekler" data-menu></button></div>
        <div class="pl-detay" hidden>${bilesenOzet(p.bilesenler)}
          ${p.bilesenler?.hook ? `<label class="onay kucuk"><input type="checkbox" data-bil="hooks" ${p.hooks_acik ? "checked" : ""}> Hook'ları çalıştır (${kacir(p.bilesenler.hook)})</label>` : ""}
          ${p.bilesenler?.mcp?.length ? `<label class="onay kucuk"><input type="checkbox" data-bil="mcp" ${p.mcp_acik ? "checked" : ""}> MCP sunucularını aç (${kacir(p.bilesenler.mcp.join(", "))})</label>` : ""}
          ${p.onceki ? `<div class="soluk kucuk">Önceki sürüm: v${kacir(p.onceki)}</div>` : ""}</div></div>`).join("")
        || '<div class="soluk kucuk ek-bos">Kurulu plugin yok. "Plugin ekle"den ya da "Claude Code ile eşitle" ile ekleyebilirsin.</div>';
      ikonlariYerlestir(kap);
      $$("[data-pl]", kap).forEach((kart) => {
        const ad = kart.dataset.pl;
        const p = pluginler.find((x) => x.ad === ad);
        $$("[data-bil]", kart).forEach((c) => {
          c.onchange = async () => {
            try { await api(`/api/pluginler/${ad}/bilesen`, { method: "PUT", govde: { tur: c.dataset.bil, acik: c.checked } }); bildir("Kaydedildi.", "basari", 1000); } catch (err) { bildir(err.message, "hata"); c.checked = !c.checked; }
          };
        });
        $('[data-is="detay"]', kart).onclick = () => { const d = $(".pl-detay", kart); d.hidden = !d.hidden; };
        const yap = async (is) => {
          try {
            if (is === "geri") await api(`/api/pluginler/${ad}/geri-al`, { method: "POST" });
            else if (is === "ac") await api(`/api/pluginler/${ad}/durum`, { method: "PUT", govde: { acik: !p.acik } });
            else {
              if (!(await onayla("Plugin'i kaldır", `${ad} ve tüm sürümleri silinsin mi?`, { evet: "Kaldır", tehlike: true }))) return;
              await api(`/api/pluginler/${ad}`, { method: "DELETE" });
            }
            pluginCiz();
          } catch (err) { bildir(err.message, "hata"); }
        };
        $("[data-menu]", kart).onclick = (e) => menuAc(e.currentTarget, [
          { metin: p.acik ? "Kapat" : "Aç", ikon: "guc", eylem: () => yap("ac") },
          ...(p.onceki ? [{ metin: `Önceki sürüme dön (v${p.onceki})`, ikon: "yenile", eylem: () => yap("geri") }] : []),
          "ayrac",
          { metin: "Kaldır", ikon: "cop", tehlike: true, eylem: () => yap("sil") },
        ], { sagaHizali: true });
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
    const kat = el(`<div><div class="ek-bolum-baslik"><b>Katalog</b><span class="soluk kucuk">kilitli sürüm ve hash</span></div>
      <div class="ek-izgara">${katalog.map((x) => `<div class="ek-kart">${ekAvatar(x.name)}<div class="ek-govde"><div class="ek-ad">${kacir(x.name)}</div><div class="ek-aciklama">${kacir(x.description || "")}</div><div class="ek-alt soluk">v${kacir(x.version)}</div></div><button class="btn kucuk" data-kat="${kacir(x.name)}">İncele</button></div>`).join("")}</div></div>`);
    $$("[data-kat]", kat).forEach((b) => { b.onclick = () => plIncele(() => api(`/api/pluginler/katalog/${b.dataset.kat}`, { method: "POST" })); });
    $("#pl-rapor", govde).after(kat);
  }).catch(() => {});
  pluginCiz();
  uzantiSekmesiKur(govde);

  const modelleriCiz = () => {
    $("#ay-modeller", govde).innerHTML = modelKartlari($("#ay-ara", govde).value);
    $$("input[name=ayar-model]", govde).forEach((r) => {
      r.onchange = async () => { await kaydet({ model: r.value }); modelleriCiz(); aktifCiz(); };
    });
    $$("[data-sil]", govde).forEach((b) => {
      b.onclick = async (e) => {
        e.preventDefault(); // label icinde: radyo secilmesin
        const m = (durum.sunucu?.modeller || []).find((x) => x.anahtar === b.dataset.sil);
        if (m && (await modelSil({ ...m, acik: durum.sunucu?.yuklenen_model === m.anahtar }))) { modelleriCiz(); aktifCiz(); }
      };
    });
  };
  $("#ay-magaza", govde).onclick = () => { m.kapat(); modellerSayfasi(); };
  for (const [id, alan] of [["#ay-v-koord", "varsayilan_koordinator"], ["#ay-v-uyg", "varsayilan_uygulayici"]]) {
    $(id, govde).onchange = (e) => kaydet({ [alan]: e.target.value.trim() });
  }
  (a.saglayici === "openrouter"
    ? api("/api/openrouter/modeller").then((v) => v.modeller.map((x) => x.id)).catch(() => [])
    : Promise.resolve((durum.sunucu?.modeller || []).map((x) => x.anahtar))
  ).then((idler) => { $("#ay-v-liste", govde).innerHTML = idler.map((id) => `<option value="${kacir(id)}"></option>`).join(""); });
  $("#ay-ara", govde).oninput = modelleriCiz;
  modelleriCiz();

  // ---- OpenRouter ----
  let orListe = [];
  let orAnahtarVar = false;
  const orAnahtarCiz = async () => {
    const d = await api("/api/openrouter/anahtar");
    orAnahtarVar = d.var;
    $("#ay-or-anahtar", govde).innerHTML = d.var
      ? `<code>${kacir(d.maskeli)}</code> <span class="rozet yesil">kayıtlı</span>`
      : '<span class="rozet kirmizi">yok</span> <a href="https://openrouter.ai/keys" target="_blank" rel="noopener" class="kucuk">anahtar al</a>';
    $("#ay-or-sil", govde).hidden = !d.var;
    $("#ay-or-degistir", govde).textContent = d.var ? "Değiştir" : "Ekle";
    $("#ay-or-anahtar-gir", govde).hidden = d.var; // anahtar yoksa giris alani hemen acik
    aktifCiz();
  };
  const ctx = (n) => (n >= 1e6 ? `${sayi(n / 1e6, n % 1e6 ? 1 : 0)}M` : `${Math.round(n / 1000)}K`);
  const fiyat = (m) => (m.ucretsiz ? "ücretsiz" : `$${m.giris_1m} / $${m.cikis_1m}`);
  const yetenekler = (m) => [m.araclar && "araç", m.goruntu && "görsel", m.dusunme && "düşünme"].filter(Boolean);
  const orModelleriCiz = () => {
    const kucuk = $("#ay-or-ara", govde).value.toLowerCase();
    const ucretsiz = $("#ay-or-ucretsiz", govde).checked;
    const filtre = $$("[data-filtre]:checked", govde).map((x) => x.dataset.filtre);
    const sec = durum.ayarlar.or_model;
    const liste = orListe.filter((m) => (!ucretsiz || m.ucretsiz) && filtre.every((f) => m[f])
      && (!kucuk || `${m.ad} ${m.id}`.toLowerCase().includes(kucuk)));
    // secili model filtreye takilsa da en ustte gorunur (ucretli secimken "Ucretsiz" gizliyordu)
    const secili = orListe.find((m) => m.id === sec);
    if (secili && !kucuk && !liste.includes(secili)) liste.unshift(secili);
    else if (secili && liste.includes(secili)) liste.sort((a, b) => (b === secili) - (a === secili));
    $("#ay-or-modeller", govde).innerHTML = liste.slice(0, 200).map((m) => `<button type="button" class="ay-model-satir ${m.id === sec ? "secili" : ""}" role="option" aria-selected="${m.id === sec}" data-id="${kacir(m.id)}" title="${kacir(m.id)}">
      <span class="ay-model-ad">${kacir(m.ad)}</span>
      <span class="ay-model-yet">${yetenekler(m).map((y) => `<span class="ay-yet">${y}</span>`).join("")}</span>
      <span class="ay-model-meta">${ctx(m.baglam)} · ${fiyat(m)}</span>${m.id === sec ? '<span class="ay-tik" aria-hidden="true">✓</span>' : ""}</button>`).join("")
      || '<div class="ayar-not">Eşleşen model yok; filtreleri gevşet.</div>';
    $("#ay-or-uyari", govde).textContent = `${liste.length} / ${orListe.length} model`;
    $$(".ay-model-satir", $("#ay-or-modeller", govde)).forEach((b) => {
      b.onclick = async () => {
        await kaydet({ or_model: b.dataset.id }, true);
        $("#ay-or-secici", govde).open = false;
        orModelleriCiz(); dusunmeCiz(); aktifCiz();
        bildir("Model seçildi", "basari", 1200);
      };
    });
  };
  // Ozet karti: kullanilan model + yetenekleri + Degistir / Dene
  function aktifCiz() {
    const k = $("#ay-aktif", govde);
    const or = durum.ayarlar.saglayici === "openrouter";
    const ol = durum.ayarlar.saglayici === "ollama";
    let ad, alt = [];
    if (ol) {
      const m = olListe.find((x) => x.ad === durum.ayarlar.ollama_model);
      ad = durum.ayarlar.ollama_model || "Model seçilmedi";
      alt = m ? [m.parametre, m.niceleme, `${sayi(m.boyut_gb)} GB`, ...olYetenek(m.yetenek)] : ["Ollama"];
      if (m?.yetenek && !m.yetenek.araclar) alt.push("⚠ araç kullanamaz: ajan işleri çalışmaz");
    } else if (durum.ayarlar.saglayici === "uyumlu") {
      ad = durum.ayarlar.uyumlu_model || "Model seçilmedi";
      alt = ["bulut · OpenAI uyumlu"];
    } else if (or) {
      const m = orListe.find((x) => x.id === durum.ayarlar.or_model);
      ad = m ? m.ad : durum.ayarlar.or_model || "Model seçilmedi";
      if (m) alt = [`${ctx(m.baglam)} bağlam`, fiyat(m), ...yetenekler(m)];
      if (!orAnahtarVar) alt.unshift("⚠ API anahtarı yok");
      if (m && !m.araclar) alt.push("⚠ araç kullanamaz: ajan işleri çalışmaz");
    } else {
      const m = (durum.sunucu?.modeller || []).find((x) => x.anahtar === durum.ayarlar.model);
      ad = m ? m.ad || m.anahtar : durum.ayarlar.model;
      alt = ["bu bilgisayarda", m && !m.dosya_var ? "⚠ dosya indirilmemiş" : "internetsiz"];
    }
    k.innerHTML = `<div class="ay-aktif-sol"><div class="soluk kucuk">Kullanılan model · ${ol ? "Ollama" : or ? "OpenRouter" : durum.ayarlar.saglayici === "uyumlu" ? "Diğer bulut" : "Bu bilgisayar"}</div>
      <div class="ay-aktif-ad">${kacir(ad)}</div><div class="ay-aktif-alt">${alt.filter(Boolean).map((x) => `<span class="${String(x).startsWith("⚠") ? "uyari-metin" : ""}">${kacir(x)}</span>`).join(" · ")}</div>
      <div id="ay-aktif-sonuc" class="ayar-not"></div></div>
      <div class="ay-aktif-sag"><button class="btn kucuk" id="ay-aktif-degistir">Değiştir</button><button class="btn kucuk ana" id="ay-aktif-dene"><span data-ikon="oynat"></span>Dene</button></div>`;
    ikonlariYerlestir(k);
    $("#ay-aktif-degistir", k).onclick = () => {
      const hedef = ol ? $("#ay-ol", govde) : durum.ayarlar.saglayici === "uyumlu" ? $("#ay-uy", govde) : or ? $("#ay-or-secici", govde) : $("#ay-modeller", govde);
      if (or) { hedef.open = true; setTimeout(() => $("#ay-or-ara", govde).focus(), 50); }
      hedef.scrollIntoView({ behavior: "smooth", block: "start" });
    };
    $("#ay-aktif-dene", k).onclick = () => (or ? $("#ay-or-test", govde) : durum.ayarlar.saglayici === "uyumlu" ? $("#ay-uy-test", govde) : $("#ay-test", govde)).click();
  }
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
    dusunmeCiz();
    aktifCiz();
    if (!durum.ayarlar.or_model) $("#ay-or-secici", govde).open = true; // secim yoksa acik gelsin
  };
  let orYuklendi = false;
  const orPanel = () => {
    const acik = durum.ayarlar.saglayici === "openrouter";
    const ol = durum.ayarlar.saglayici === "ollama";
    $("#ay-or", govde).hidden = !acik;
    $("#ay-ol", govde).hidden = !ol;
    const uy = durum.ayarlar.saglayici === "uyumlu";
    $("#ay-uy", govde).hidden = !uy;
    if (uy) uyPanelCiz();
    $$("[data-yerel]", govde).forEach((x) => { x.hidden = acik || ol || uy; });
    $("#ay-test", govde).closest(".ayar-grup").hidden = acik || uy; // Test: yerel + Ollama
    $("#ay-baglam", govde)?.closest(".ayar-grup")?.classList.remove("arama-gizli");
    if ($("#ay-baglam", govde)) $("#ay-baglam", govde).closest(".ayar-grup").hidden = acik; // Ollama da baglam_token kullanir
    if (ol) olPanelCiz();
    dusunmeCiz();
    aktifCiz();
    if (acik && !orYuklendi) { orYuklendi = true; orAnahtarCiz(); orListeYukle(); }
  };
  $$("input[name=ay-sag]", govde).forEach((r) => {
    r.onchange = async () => {
      await kaydet({ saglayici: r.value });
      orPanel();
    };
  });
  $("#ay-or-degistir", govde).onclick = () => {
    const g = $("#ay-or-anahtar-gir", govde);
    g.hidden = !g.hidden;
    if (!g.hidden) $("#ay-or-yeni", govde).focus();
  };
  $$("[data-filtre]", govde).forEach((x) => { x.onchange = orModelleriCiz; });
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
    const sonuc = $("#ay-aktif-sonuc", govde) || $("#ay-or-test-sonuc", govde);
    b.disabled = true;
    sonuc.innerHTML = '<span class="parilti">Deneniyor…</span>';
    try {
      const t = await api("/api/openrouter/test", { method: "POST", govde: {} });
      sonuc.innerHTML = `<span class="rozet yesil">başarılı</span> "${kacir(t.cevap)}" · ${sayi(t.sure_sn)} sn · maliyet $${t.maliyet_usd}${t.arac_cagrisi ? " · araç çağırdı" : ""}`;
    } catch (err) {
      sonuc.innerHTML = `<span class="rozet kirmizi">hata</span> ${kacir(err.message)}`;
    } finally { b.disabled = false; }
  };
  // ---- Diger bulut (OpenAI uyumlu) ----
  let uyDurum = [], uyListe = [];
  const uySid = () => $("#ay-uy-sid", govde).value;
  async function uyPanelCiz() {
    uyDurum = await api("/api/saglayicilar").catch(() => []);
    const sec = $("#ay-uy-sid", govde);
    const onceki = sec.value || (durum.ayarlar.uyumlu_model || "").split(":")[0] || "openai";
    sec.innerHTML = uyDurum.map((s) => `<option value="${kacir(s.id)}">${kacir(s.ad)}${s.anahtar.var ? " ✓" : ""}</option>`).join("");
    sec.value = onceki;
    uyAnahtarCiz();
    uyListeYukle();
  }
  function uyAnahtarCiz() {
    const s = uyDurum.find((x) => x.id === uySid());
    if (!s) return;
    const k = s.anahtar;
    $("#ay-uy-anahtar", govde).innerHTML = k.var
      ? `<code>${kacir(k.maskeli)}</code> <span class="rozet yesil">${k.kaynak === "ortam" ? `ortam değişkeni (${kacir(s.ortam)})` : "kayıtlı"}</span>`
      : s.anahtar_gerekli ? '<span class="rozet kirmizi">yok</span>' : '<span class="soluk kucuk">gerekmez</span>';
    $("#ay-uy-sil", govde).hidden = k.kaynak !== "kayitli";
    const adresli = ["ozel", "lmstudio"].includes(s.id);
    $("#ay-uy-adres-satir", govde).hidden = !adresli;
    $("#ay-uy-adres", govde).value = adresli ? s.adres : "";
  }
  async function uyListeYukle(yenile = false) {
    uyListe = [];
    $("#ay-uy-uyari", govde).innerHTML = '<span class="parilti">Model listesi alınıyor…</span>';
    try {
      const v = await api(`/api/saglayicilar/${uySid()}/modeller${yenile ? "?yenile=true" : ""}`);
      uyListe = v.modeller;
      $("#ay-uy-uyari", govde).textContent = v.uyari || `${uyListe.length} model · liste ${new Date(v.zaman * 1000).toLocaleString("tr-TR")}`;
    } catch (err) {
      $("#ay-uy-uyari", govde).innerHTML = `<span class="rozet kirmizi">hata</span> ${kacir(err.message)}`;
    }
    uyModelleriCiz();
  }
  function uyModelleriCiz() {
    const ara = $("#ay-uy-ara", govde).value.toLowerCase();
    const secili = durum.ayarlar.uyumlu_model;
    const liste = uyListe.filter((m) => !ara || `${m.ad} ${m.id}`.toLowerCase().includes(ara));
    const kutu = $("#ay-uy-modeller", govde);
    kutu.innerHTML = liste.slice(0, 200).map((m) => {
      const id = `${uySid()}:${m.id}`;
      return `<button type="button" class="ay-model-satir ${id === secili ? "secili" : ""}" role="option" aria-selected="${id === secili}" data-uy="${kacir(id)}">
        <span class="ay-model-ad">${kacir(m.ad)}</span><span class="ay-model-meta">${m.baglam ? `${ctx(m.baglam)} bağlam` : ""}</span>${id === secili ? '<span class="ay-tik" aria-hidden="true">✓</span>' : ""}</button>`;
    }).join("") || '<div class="ayar-not">Model yok; anahtarı kaydedip Yenile düğmesine bas.</div>';
    $$("[data-uy]", kutu).forEach((b) => {
      b.onclick = async () => { await kaydet({ uyumlu_model: b.dataset.uy }, true); uyModelleriCiz(); aktifCiz(); bildir("Model seçildi", "basari", 1200); };
    });
  }
  $("#ay-uy-sid", govde).onchange = () => { uyAnahtarCiz(); uyListeYukle(); };
  $("#ay-uy-ara", govde).oninput = uyModelleriCiz;
  $("#ay-uy-yenile", govde).onclick = () => uyListeYukle(true);
  $("#ay-uy-kaydet", govde).onclick = async () => {
    const g = $("#ay-uy-yeni", govde);
    try {
      uyDurum = await api(`/api/saglayicilar/${uySid()}`, { method: "PUT", govde: { anahtar: g.value, adres: $("#ay-uy-adres", govde).value } });
      g.value = "";
      bildir("Kaydedildi", "basari", 1500);
      uyAnahtarCiz(); uyListeYukle(true);
    } catch (err) { bildir(err.message, "hata"); }
  };
  $("#ay-uy-sil", govde).onclick = async () => {
    if (!(await onayla("Anahtarı sil", "Bu sağlayıcının API anahtarı bu bilgisayardan silinsin mi?", { evet: "Sil", tehlike: true }))) return;
    uyDurum = await api(`/api/saglayicilar/${uySid()}`, { method: "DELETE" });
    uyAnahtarCiz(); uyListeYukle();
  };
  $("#ay-uy-test", govde).onclick = async (e) => {
    const b = e.currentTarget, sonuc = $("#ay-uy-sonuc", govde);
    b.disabled = true;
    sonuc.innerHTML = '<span class="parilti">Deneniyor…</span>';
    try {
      const t = await api("/api/saglayicilar/test", { method: "POST", govde: {} });
      sonuc.innerHTML = `<span class="rozet yesil">başarılı</span> "${kacir(t.cevap)}" · ${sayi(t.sure_sn)} sn${t.token ? ` · ${t.token} token` : ""}${t.arac_cagrisi ? " · araç çağırdı" : ""}${t.finish_reason === "length" ? " · ⚠ çıktı sınıra takıldı" : ""}`;
    } catch (err) {
      sonuc.innerHTML = `<span class="rozet kirmizi">hata</span> ${kacir(err.message)}`;
    } finally { b.disabled = false; }
  };
  // ---- Ollama ----
  let olListe = [];
  const olYetenek = (y) => (y ? [y.araclar && "araç", y.goruntu && "görsel", y.dusunme && "düşünür", y.baglam && `${ctx(y.baglam)} bağlam`].filter(Boolean) : []);
  async function olPanelCiz() {
    $("#ay-ol-magaza", govde).onclick = () => { m.kapat(); modellerSayfasi("ollama"); };
    const d = await api("/api/ollama/durum").catch(() => ({}));
    $("#ay-ol-adres", govde).textContent = d.adres || "";
    const kutu = $("#ay-ol-modeller", govde);
    if (!d.kurulu && !d.calisiyor) {
      $("#ay-ol-durum", govde).innerHTML = '<span class="rozet kirmizi">kurulu değil</span> <a href="https://ollama.com/download" target="_blank" rel="noopener" class="kucuk">indir</a>';
      kutu.innerHTML = "";
      return;
    }
    $("#ay-ol-durum", govde).innerHTML = '<span class="parilti">Ollama başlatılıyor…</span>';
    try {
      olListe = (await api("/api/ollama/yuklu")).modeller;
      const s = await api("/api/ollama/durum");
      $("#ay-ol-durum", govde).innerHTML = `<span class="rozet yesil">çalışıyor</span> <span class="soluk kucuk">v${kacir(s.surum || "")} · ${olListe.length} model</span>`;
    } catch (err) {
      $("#ay-ol-durum", govde).innerHTML = `<span class="rozet kirmizi">hata</span> ${kacir(err.message)}`;
      return;
    }
    // yetenekler (arac/gorsel/dusunme) /api/show'dan; secim karti ve uyarilar bunlara dayanir
    await Promise.all(olListe.filter((x) => !x.yetenek).map(async (x) => {
      try {
        const dt = await api(`/api/ollama/detay?ad=${encodeURIComponent(x.ad)}`);
        x.yetenek = { araclar: dt.yetenekler.includes("tools"), goruntu: dt.yetenekler.includes("vision"), dusunme: dt.yetenekler.includes("thinking"), baglam: dt.baglam };
      } catch { /* detay alinamazsa rozet yok */ }
    }));
    kutu.innerHTML = olListe.length ? olListe.map((x) => `<button type="button" class="ay-model-satir ${x.ad === durum.ayarlar.ollama_model ? "secili" : ""}" role="option" data-ol="${kacir(x.ad)}" aria-selected="${x.ad === durum.ayarlar.ollama_model}">
        <span class="ay-model-ad">${kacir(x.ad)}</span><span class="soluk kucuk">${kacir([x.parametre, x.niceleme, `${sayi(x.boyut_gb)} GB`, ...olYetenek(x.yetenek)].filter(Boolean).join(" · "))}</span>
        ${x.acik ? '<span class="rozet yesil">açık</span>' : ""}</button>`).join("")
      : '<div class="ayar-not">Ollama\'da model yok. "Model mağazası"ndan indir.</div>';
    $$("[data-ol]", kutu).forEach((b) => {
      b.onclick = async () => { await kaydet({ ollama_model: b.dataset.ol }); olPanelCiz(); bildir("Model seçildi", "basari", 1200); };
    });
    dusunmeCiz();
    aktifCiz();
  }
  orPanel();

  // Bolum kisayollari: adres cubugu (#) degismez, yalniz panel kayar
  $$("[data-atla]", govde).forEach((b) => {
    b.onclick = () => $(`#${b.dataset.atla}`, govde)?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  function dusunmeCiz() {
    const kutu = $("#ay-dusunme", govde);
    if (!kutu) return;
    // Modelin yetenegine gore: desteklemiyorsa kapali ve kilitli; destekliyorsa secilebilir
    let destek = true;
    let not = "";
    if (durum.ayarlar.saglayici === "openrouter") {
      const m = orListe.find((x) => x.id === durum.ayarlar.or_model);
      if (!m) not = orListe.length ? "Seçili OpenRouter modeli listede yok; seviye yine gönderilir." : "Model listesi yükleniyor…";
      else if (!m.dusunme) { destek = false; not = `<b>${kacir(m.ad)}</b> düşünmeyi desteklemiyor; seviye kapalı ve değiştirilemez.`; }
      else not = `<b>${kacir(m.ad)}</b> düşünmeyi destekliyor. Dengeli = düşük efor, Derin = yüksek efor. Düşünmesi zorunlu modellerde "Kapalı" en düşük eforla çalışır.`;
    } else if (durum.ayarlar.saglayici === "ollama") {
      const y = olListe.find((x) => x.ad === durum.ayarlar.ollama_model)?.yetenek;
      if (y && !y.dusunme) { destek = false; not = "Seçili Ollama modeli düşünmeyi desteklemiyor; seviye kapalı."; }
      else not = "Ollama: Kapalı = düşünme yok, Dengeli = düşük efor, Derin = yüksek efor.";
    } else {
      not = "Yerel model: Dengeli en fazla 1024 düşünme token'ı, Derin sınırsız.";
    }
    $("#ay-dusunme-not", govde).innerHTML = not;
    const secili = destek ? durum.ayarlar.dusunme : "kapali";
    kutu.innerHTML = durum.bilgi.dusunme_secenekleri.map((d) => `<label class="secenek-kart ${d.deger === secili ? "secili" : ""} ${!destek && d.deger !== "kapali" ? "kilitli" : ""}">
      <input type="radio" name="ay-dus" value="${d.deger}" ${d.deger === secili ? "checked" : ""} ${!destek ? "disabled" : ""}>
      <div><div class="ust">${kacir(d.ad)} <span class="rozet">${kacir(d.sure)}</span></div><div class="alt">${kacir(d.aciklama)}</div></div></label>`).join("");
    $$("input[name=ay-dus]", govde).forEach((r) => { r.onchange = async () => { await kaydet({ dusunme: r.value }); dusunmeCiz(); }; });
  }
  dusunmeCiz();

  const alanKaydet = (sec, anahtar, donustur = (v) => v) => {
    $(sec, govde).onchange = (e) => kaydet({ [anahtar]: donustur(e.target.type === "checkbox" ? e.target.checked : e.target.value) });
  };
  alanKaydet("#ay-dizin", "llm_dizin");
  alanKaydet("#ay-adres", "adres");
  alanKaydet("#ay-oto", "otomatik_baslat");
  alanKaydet("#ay-araclar", "sohbet_araclari");
  alanKaydet("#ay-ag", "ag_acik");
  $("#ay-dikte-bulut", govde).onchange = async (e) => { await kaydet({ dikte_bulut: e.target.checked }); dikteDurumuYenile(); };
  $("#ay-dikte-model", govde).onchange = async (e) => { await kaydet({ dikte_model: e.target.value.trim() }); dikteDurumuYenile(); };
  // Tam yetki: acarken tek seferlik onay (openbot ilk acilis onayi gibi); kapatmak serbest
  $("#ay-tam-yetki", govde).onchange = async (e) => {
    const g = e.target;
    if (g.checked && !(await onayla(
      "Tam yetki açılsın mı?",
      "Ajan dosya yazma, komut çalıştırma, GitHub/MCP bağlayıcıları ve web işlemlerini sana sormadan yapacak. Yalnız disk silme, biçimlendirme, kapatma ve zorla push gibi geri alınamaz komutlar yine onay ister. Önemli dosyalarının yedeği olduğundan emin ol.",
      { evet: "Aç", tehlike: true },
    ))) { g.checked = false; return; }
    // Tam yetki web'i de acar (eski kurulumlarda kayitli ag_acik=false kalmis olabilir)
    await kaydet(g.checked ? { tam_yetki: true, ag_acik: true } : { tam_yetki: false });
    if (g.checked) $("#ay-ag", govde).checked = true;
    import("./proje.js").then((m) => m.projeYenile()).catch(() => {});
  };
  alanKaydet("#ay-tarayici", "tarayici_acik");
  const kurallarCiz = (liste) => {
    const k = $("#ay-kurallar", govde);
    if (!k) return;
    k.innerHTML = liste.length ? liste.map((x) => `<div class="satir"><span style="flex:1"><code>${kacir(x.arac)}</code> <span class="soluk kucuk">${kacir(x.yan_etki)}${x.anahtar.split("|")[2] ? ` · ${kacir(x.anahtar.split("|")[2])}` : ""}</span></span><button class="btn kucuk tehlike" data-kural="${kacir(x.id)}">Kaldır</button></div>`).join("") : '<span class="soluk kucuk">Kural yok.</span>';
    k.querySelectorAll("[data-kural]").forEach((b) => {
      b.onclick = async () => { try { kurallarCiz((await api(`/api/onay-kurallari/${b.dataset.kural}`, { method: "DELETE" })).kurallar); } catch (e) { bildir(e.message, "hata"); } };
    });
  };
  api("/api/onay-kurallari").then((r) => kurallarCiz(r.kurallar)).catch(() => kurallarCiz([]));
  alanKaydet("#ay-masaustu", "masaustu_izinli", (v) => v.split(",").map((x) => x.trim()).filter(Boolean));
  $("#ay-masaustu-hepsi", govde).onchange = async (e) => {
    const hepsi = e.target.checked;
    $("#ay-masaustu-liste", govde).hidden = hepsi;
    const liste = $("#ay-masaustu", govde).value.split(",").map((x) => x.trim()).filter(Boolean);
    await kaydet({ masaustu_izinli: hepsi ? ["*"] : liste });
  };
  const sunucuKaydet = async (degisiklik) => { await kaydet(degisiklik); sunucuDurumuCiz(govde); };
  $("#ay-sunucu-acik", govde).onchange = (e) => sunucuKaydet({ sunucu_acik: e.target.checked });
  $("#ay-sunucu-port", govde).onchange = (e) => sunucuKaydet({ sunucu_port: Number(e.target.value) });
  sunucuDurumuCiz(govde);
  $("#ay-baglam", govde).value = String(a.baglam_token);
  alanKaydet("#ay-baglam", "baglam_token", Number);
  $("#ay-profil", govde).value = a.baglam_profili || "otomatik";
  alanKaydet("#ay-profil", "baglam_profili");
  alanKaydet("#ay-sistem", "sistem_istemi");
  alanKaydet("#ay-gorsel-model", "gorsel_model", (v) => v.trim());
  const gorselSaglayiciCiz = () => { $("#ay-gorsel-or", govde).hidden = $("#ay-gorsel-saglayici", govde).value === "codex"; };
  $("#ay-gorsel-saglayici", govde).onchange = (e) => { gorselSaglayiciCiz(); kaydet({ gorsel_saglayici: e.target.value }); };
  gorselSaglayiciCiz();
  api("/api/ajanlar-saglayicilar").then((v) => {
    $("#ay-codex-durum", govde).textContent = v.kurulu.codex ? "Codex kurulu" : "Codex kurulu değil";
  }).catch(() => {});
  const gorselListe = async (yenile = false) => {
    try {
      const v = await api(`/api/openrouter/modeller?cikti=image${yenile ? "&yenile=true" : ""}`);
      const ucretsiz = $("#ay-gorsel-ucretsiz", govde).checked;
      $("#ay-gorsel-liste", govde).innerHTML = v.modeller.filter((m) => !ucretsiz || m.ucretsiz)
        .map((m) => `<option value="${kacir(m.id)}">${kacir(m.ad)}${m.ucretsiz ? " (ücretsiz)" : ""}</option>`).join("");
      if (v.uyari) $("#ay-gorsel-not", govde).textContent = v.uyari;
    } catch (err) { $("#ay-gorsel-not", govde).textContent = `Görsel model listesi alınamadı: ${err.message}`; }
  };
  $("#ay-gorsel-ucretsiz", govde).onchange = () => gorselListe();
  alanKaydet("#ay-video-model", "video_model", (v) => v.trim());
  const videoListe = async (yenile = false) => {
    try {
      const v = await api(`/api/openrouter/modeller?cikti=video${yenile ? "&yenile=true" : ""}`);
      $("#ay-video-liste", govde).innerHTML = v.modeller
        .map((m) => `<option value="${kacir(m.id)}">${kacir(m.ad)}</option>`).join("");
      if (v.uyari) $("#ay-video-not", govde).textContent = v.uyari;
    } catch (err) { $("#ay-video-not", govde).textContent = `Video model listesi alınamadı: ${err.message}`; }
  };
  $("#ay-video-yenile", govde).onclick = () => videoListe(true);
  videoListe();
  $("#ay-gorsel-yenile", govde).onclick = () => gorselListe(true);
  gorselListe();
  alanKaydet("#ay-sicaklik", "sicaklik", Number);
  alanKaydet("#ay-max", "max_tokens", Number);
  alanKaydet("#ay-gunluk-butce", "gunluk_butce_usd", (v) => Math.max(0, Number(v) || 0));
  $("#ay-sicaklik", govde).oninput = (e) => { e.target.previousElementSibling.textContent = `Sıcaklık (${e.target.value})`; };

  $("#ay-test", govde).onclick = async (e) => {
    const b = e.currentTarget;
    const sonuc = $("#ay-aktif-sonuc", govde) || $("#ay-test-sonuc", govde);
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
  const guncBtn = $("#ay-guncelleme-kontrol", govde);
  if (guncBtn) {
    guncBtn.onclick = async () => {
      const sonucEl = $("#ay-guncelleme-sonuc", govde);
      guncBtn.disabled = true;
      sonucEl.textContent = "Denetleniyor…";
      try {
        const g = await api("/api/guncelleme?zorla=true");
        if (g.yeni_var) {
          const link = g.adres && /^https:\/\//i.test(g.adres) ? g.adres : "https://github.com/umutc6230/kairo/releases";
          sonucEl.innerHTML = `<span class="rozet yesil">Yeni sürüm: v${kacir(g.son)}</span> <a href="${kacir(link)}" target="_blank" rel="noopener">GitHub Release sayfasını aç</a>`;
        } else {
          sonucEl.textContent = g.uyari || g.not || `Güncel sürümü kullanıyorsunuz (${g.mevcut}).`;
        }
      } catch (err) {
        sonucEl.textContent = err.message;
      } finally {
        guncBtn.disabled = false;
      }
    };
  }
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

// Ctrl+K oturum degistirici: bos aramada Calisiyor / Onay bekliyor / Son gruplari; ok tuslari + Enter
export function aramaAc(oturumAc, projeAdi = () => "", aktifId = "") {
  const kutu = el(`<div class="degistirici"><div class="arama-kutu">${ikon("ara")}<input placeholder="Sohbete geç ya da ara..." id="ar-girdi" aria-label="Sohbet ara"></div>
    <div id="ar-sonuc" role="listbox"></div><div class="degistirici-alt soluk kucuk"><span>↑↓ seç</span><span>Enter aç</span><span>Esc kapat</span></div></div>`);
  const m = modal({ baslik: "Sohbete geç", icerik: kutu });
  const girdi = $("#ar-girdi", kutu);
  let zaman;
  let secili = 0;
  const sec = (i) => {
    const s = [...kutu.querySelectorAll(".arama-sonuc")];
    if (!s.length) return;
    secili = (i + s.length) % s.length;
    s.forEach((x, j) => { x.classList.toggle("secili", j === secili); x.setAttribute("aria-selected", String(j === secili)); });
    s[secili].scrollIntoView({ block: "nearest" });
  };
  const satir = (o, d) => {
    const proje = o.alan ? projeAdi(o.alan) : "";
    const s = el(`<div class="arama-sonuc" role="option"><span class="ds-nokta ${d ? `ds-${d}` : ""}" aria-hidden="true"></span><span class="ds-ad">${kacir(o.baslik)}</span>
      ${proje ? `<span class="soluk kucuk ds-proje">${kacir(proje)}</span>` : ""}<span class="soluk kucuk ds-zaman">${o.id === aktifId ? "Şu an" : kacir(goreceliZaman(o.guncelleme))}</span></div>`);
    s.onclick = () => { m.kapat(); oturumAc(o.id); };
    return s;
  };
  const ara = async () => {
    const q = girdi.value.trim();
    const [liste, harita] = await Promise.all([api(`/api/oturumlar?q=${encodeURIComponent(q)}`).catch(() => []), gorevDurumlari()]);
    const kap = $("#ar-sonuc", kutu);
    kap.innerHTML = "";
    const gorunur = liste.filter((o) => o.mesaj_sayisi || o.ajan_sayisi || o.id === aktifId)
      .sort((a, b) => (b.guncelleme || "").localeCompare(a.guncelleme || ""));
    if (!gorunur.length) { kap.innerHTML = '<div class="ayar-not" style="padding:12px">Sonuç yok.</div>'; return; }
    const gruplar = q ? [["", gorunur.slice(0, 40)]] : (() => {
      const d = (o) => oturumDurumu(o, harita);
      return [["Çalışıyor", gorunur.filter((o) => d(o) === "calisiyor")], ["Onay bekliyor", gorunur.filter((o) => d(o) === "onay")],
        ["Son", gorunur.filter((o) => !["calisiyor", "onay"].includes(d(o))).slice(0, 15)]];
    })();
    for (const [ad, ogeler] of gruplar) {
      if (!ogeler.length) continue;
      if (ad) kap.append(el(`<div class="ds-grup soluk kucuk">${kacir(ad)}</div>`));
      ogeler.forEach((o) => kap.append(satir(o, oturumDurumu(o, harita))));
    }
    sec(0);
  };
  girdi.oninput = () => { clearTimeout(zaman); zaman = setTimeout(ara, 150); };
  girdi.onkeydown = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); sec(secili + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); sec(secili - 1); }
    else if (e.key === "Enter") { e.preventDefault(); kutu.querySelectorAll(".arama-sonuc")[secili]?.click(); }
  };
  ara();
  setTimeout(() => girdi.focus(), 10);
}
