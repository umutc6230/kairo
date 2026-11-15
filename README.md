# Kairo

Windows için **masaüstü yapay zeka ajanı**. Bilgisayarındaki yerel ve sansürsüz modellerle (llama.cpp)
ya da OpenRouter üzerindeki bulut modelleriyle çalışır: sohbet eder, proje klasöründe kod yazar,
komut çalıştırır, web'de araştırır, tarayıcıyı ve masaüstü programlarını kullanır. Arayüz Claude
Desktop düzenindedir; skill, plugin, hook ve MCP tarafında Claude Code ile uyumludur.

**Ürün sahibi: Umut Çelik** · [X](https://x.com/umutc6230) · [GitHub](https://github.com/umutc6230)

Python 3.12 + FastAPI + pywebview, arayüz vanilla JS. Portable: kurulum ve yönetici izni gerekmez.

## Özellikler

### Modeller ve sağlayıcılar
- **Yerel (llama.cpp, Vulkan):** GGUF modeller; RAM ihtiyacı, yetenek ve dosya durumu etiketleri,
  bağlam boyutu 8K / 16K / 32K, boş RAM yetmezse uyarı.
- **OpenRouter:** anahtar ekle / doğrula / sil (maskeli, yalnız arka uçta), canlı model listesi
  (24 saat önbellek, Yenile), arama, "yalnız ücretsiz" filtresi, fiyat / bağlam / araç / görsel
  rozetleri, gerçek istek biçimiyle Test (süre, token, maliyet).
- **Model mağazası (Hugging Face):** GGUF ara; bu bilgisayarın RAM ve diskine göre
  "Çalışır / Zorlanır / Çalışmaz" göstergesi. İndirme kaldığı yerden devam eder, SHA256 ile doğrulanır.
- **Yerel sunucu (Ollama gibi):** Kairo açıkken modeller diğer uygulamalara sunulur. Ollama uyumlu
  `http://127.0.0.1:11434` (`/api/tags`, `/api/show`, `/api/chat`, `/api/generate`) ve OpenAI uyumlu
  `/v1` (`/v1/models`, `/v1/chat/completions`). Pencere olmadan: `Sunucu.bat` / `Sunucu-Durdur.bat`.
- **Claude Code yerel modelle:** sunucu Anthropic uyumlu uçları da verir (`/v1/messages`,
  `/v1/messages/count_tokens`); `Claude-Yerel.bat [model]` ile Claude Code bulut ve anahtar olmadan çalışır.

### Sohbet
- Akan cevap, **Durdur**, cevabın üstünde canlı akan ve sonra katlanan düşünce bloğu, düşünme
  seviyesi (Kapalı / Dengeli / Derin), geçmiş, arama, yeniden adlandırma, çatallama, dışa aktarma.
- **Dosya ekleme:** resim (OCR / görsel soru), PDF (metin katmanı ya da sayfa sayfa OCR), ses
  (wav/mp3, Gemma 4), metin dosyaları. Sürükle-bırak ve yapıştırma. Önceki eklerde bağlam bütçesi.
- **Sohbet planı** ve **araç grupları:** ardışık araç adımları katlanır satırlarda toplanır
  ("4 okuma yapıldı"), her adım açılıp incelenebilir.
- **Slash komutları:** `/compact`, `/cost`, `/todos`, `/export`, `/rewind`, `/resume`, `/rename`,
  `/init`, `/loop`, `/add-dir`, `/bashes`, `/usage`, `/output-style`, `/diff`, `/review`,
  `/security-review`; `.claude/commands` altındaki özel komutlar. `/` ve `@`
  tamamlama, `!komut` ve `#not` kısayolları.
- **Yan sohbet paneli** (Ctrl+;), **sesle dikte** (yerel Gemma 4), **hafıza** (kaynaklı, düzenlenebilir,
  içe / dışa aktarma), boş ekranda proaktif öneriler.

### Ajan
- **Proje / çalışma alanı:** klasör seç, son projeler, çok köklü çalışma alanı.
- **İzin modları:** Planla / Onaylı / Otomatik ve **Tam yetki**. Onay kapsamı tek sefer, sohbet
  ya da her zaman; tam yetkide bile riskli eylemler (ödeme, silme, gönderme, yayınlama, disk
  biçimlendirme, `git push --force`) sorulur. Hassas dosyalar (`.env`, ssh anahtarı, parola) okunmaz.
- **Araçlar:** dosya oku / listele / ara, yama ve yazma (hash + atomik yazım + checkpoint), terminal
  (arka plan işleri, durdur), git durum / diff / dal / commit, LSP tanım / referans / tanı.
- **Geri alma:** dosya ve hunk bazlı checkpoint; `reset --hard` kullanılmaz.
- **Kalıcı görev döngüsü:** adım / süre / token bütçesi, duraklat / devam / iptal, çalışırken
  yönlendirme, çökme sonrası kurtarma, kanıtsız "başarılı" yok. Canlı adım akışı ve terminal çıktısı.
- **Alt ajanlar ve iş emirleri:** uzak sağlayıcıda paralel alt ajan, izole `git worktree` dalları,
  takım panosu, tipli iş akışları.
- **Kod incelemesi:** `git diff` üzerinden kanıtlı bulgular (önem, dosya:satır, doğrulama önerisi).
- **İzolasyon (isteğe bağlı):** komutlar Podman / Docker konteynerinde, ağ kapalı.

### Kalıcı ajanlar ve otomasyon
- **Ajanlar:** ad, talimat, klasör, model ve hafızası olan kalıcı ajanlar; iş kuyruğu, ajanlar arası
  mesaj, konuşma kaydı.
- **CLI ajanları:** Claude Code, Codex ve Antigravity CLI'ları ajan sağlayıcısı olarak sürülür.
- **Rutinler:** zamanlanmış görevler (şablonlar, bir kez / tekrar, bitiş koşulu, yap ya da bildir).
- **Telegram ve webhook:** izinli sohbetten ajana iş verme; webhook olayı ajanın kuyruğuna düşer.
- **Etkinlik (denetim) penceresi**, Windows bildirimleri, bilgisayarı uyanık tutma.

### Web, tarayıcı ve masaüstü
- **Web araması ve sayfa okuma** (DuckDuckGo; Exa ve Parallel bağlayıcıları).
- **Tarayıcı kontrolü:** izole profil, erişilebilirlik ağacı, ekran görüntüsü.
- **Bilgisayar kullanımı:** Windows UI Automation ile programları kullanma; eylemden önce pencere
  ve eleman vurgusu. Güvenlik pencereleri (UAC, oturum açma) kontrol edilmez.
- **Görsel ve video üretimi:** `gorsel_uret` (OpenRouter ya da Codex CLI), `video_uret`
  (OpenRouter, ücretli, onaylı).

### Skill, plugin ve MCP
- **Talimatlar:** `~/.claude/CLAUDE.md` ve `@import`'ları ile proje `KAIRO.md` / `AGENTS.md` her sohbete eklenir.
- **Skill'ler:** `~/.claude/skills` otomatik bulunur, uygun skill modelle seçilir; ajan kendi
  skill'ini kaydedip sürümleyebilir (`skill_kaydet`). Yerleşik belge skill'leri: `docx`, `pdf`.
- **Claude Code plugin uyumu:** `.claude-plugin/plugin.json`, skills, commands, agents, `hooks.json`,
  `.mcp.json`, marketplace ve git kaynağı; kurulu Claude Code plugin'lerini içe aktarma.
- **Hook'lar:** sürümlü olaylar; güvenlik hook'u başarısızsa işlem engellenir.
- **MCP:** stdio ve streamable HTTP, OAuth girişi (keşif + dinamik kayıt + PKCE), 25 resmi uzak
  sunuculuk dizin, Claude Code / Claude Desktop ayarlarından içe aktarma, GitHub bağlantısı (`gh`).
- **Araçları ihtiyaca göre yükleme:** MCP şemaları ertelenir, model `arac_bul` ile bulduğunu yükler
  (ölçüm: 128 araçlı kurulumda mesaj başı ~51K token -> ~17K).
- **Araç paketleri:** REA, Craft Anything, agent-desktop; sürümü ve özeti sabit, veri klasörüne kurulur.
- **Uzantılar:** ayrı süreçte çalışan, sandbox panelli uzantı sistemi.

### Arayüz
- Üst çubukta **Terminal** (Ctrl+`), **Değişiklikler** (git diff) ve **Tarayıcı** panelleri; sağ
  panelde ortam, bağlam yüzdesi, bağlayıcılar, thread'ler ve dosya ağacı; alt durum çubuğu.
- Koyu / açık / sistem teması, yazı boyutu, sohbet genişliği, azaltılmış hareket desteği,
  klavye ve ekran okuyucu erişilebilirliği.
- Sistem tepsisi, genel hızlı açma kısayolu, başlangıçta açma (isteğe bağlı).

### Model test araçları
- **Karşılaştır:** aynı soru seçilen modellere; cevap, yükleme süresi, token/sn yan yana.
- **OCR testi**, **Araç testi** ve **Test paketi** (mantık, araç çağırma, JSON, Türkçe OCR, sansürsüzlük).

## Gereksinimler
- Windows 10/11 (WebView2 hazır gelir), Python 3.12 (kaynaktan çalıştırmak için).
- Yalnız OpenRouter kullanılacaksa model dosyası gerekmez; bir OpenRouter anahtarı yeter.
- Yerel model için model klasörü: `llama.cpp\llama-server.exe` (Vulkan) + `models\*.gguf`. Hazır profiller:
  - `deepseek-heretic`: DeepSeek-V4-Pro Qwen3.5 9B heretic (i1-Q4_K_M, ~6.2 GB)
  - `gemma4-12b-heretic`: Gemma 4 12B heretic QAT Q4_0 (~7.8 GB, ses girişi var)
  - `gemma4-e4b-heretic`: Gemma 4 E4B ultra-uncensored heretic (i1-Q4_K_M, ~5.9 GB, ses girişi var)
- Dahili GPU'lu bilgisayarda model sistem RAM'ini kullanır: modelin boyutundan ~1-2 GB fazla boş RAM gerekir.
- İsteğe bağlı: Git, `gh`, Node.js (bazı araç paketleri), Podman / Docker (izolasyon),
  Claude Code / Codex CLI (CLI ajanları).

## Çalıştırma
**Portable (önerilen):** `Baslat.bat` ya da `Kairo.exe`. Klasör istenen yere kopyalanır. Ayarlar,
sohbetler ve ekler klasörün içindeki `data\` altında durur; registry ya da AppData yazılmaz
(başlangıçta açma seçilirse yalnız bir kısayol). Kaldırmak için klasörü silmek yeterli.

Model klasörü şu sırayla aranır: `YEREL_LLM_DIZIN` ortam değişkeni, uygulama klasörünün içindeki ya
da yanındaki `llm`, kullanıcı klasöründeki `Projects\llm`. Bulunamazsa Ayarlar > Model klasörü.

**Kaynaktan:**
```bat
pip install -r requirements.txt
baslat.bat                 :: pencere
python -m app --tarayici   :: varsayılan tarayıcıda
python -m app --version
```
Kaynaktan çalışırken veri `data\` (proje kökü). `YAS_VERI_DIZINI` ortam değişkeniyle değiştirilebilir.
Yalnız Windows'ta çalışır (llama-server.exe, WebView2 ve UI Automation Windows'a özel).

## Geliştirme
```bat
pip install -r requirements-dev.txt
ruff format . && ruff check .
pytest --cov
paketleme\derle.bat     :: temiz venv'de PyInstaller -> dist\Kairo\ (portable klasör)
```
Yaklaşık 800 test; model çağrıları sahte sunucuyla, ağa çıkmadan çalışır.

## Güvenlik notları
- Sunucu yalnız `127.0.0.1`'e bağlanır; Host / Origin kontrolü ve oturum anahtarı vardır. Dışarıya açmayın.
- API anahtarları yalnız arka uçta, `data\` altında tutulur; arayüze ve loglara maskeli gider.
- **Tam yetki** modu ajanın dosya yazmasına, komut çalıştırmasına ve programları kullanmasına onaysız
  izin verir. Yalnız güvendiğiniz işlerde açın.
- Sansürsüz modeller içerik filtresi uygulamaz; kullanım sorumluluğu kullanıcıdadır.

## Üçüncü taraf
Tasarım fikirleri ve yerleşik skill'ler için `NOTICE-openbot.md`, `NOTICE-dsh-superagent.md` ve
`app/skills/NOTICE.txt` dosyalarına bakın.
