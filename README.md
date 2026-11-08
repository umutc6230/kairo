# Yerel AI Studio

Bilgisayarındaki **yerel ve sansürsüz** dil modellerini (llama.cpp) sohbet, OCR, araç çağırma ve
karşılaştırma testleriyle denemek için masaüstü uygulaması. Arayüz düzeni koyu temalı, solda sohbet
listesi, ortada sohbet ve altta mesaj kutusu olan bir masaüstü sohbet uygulaması gibidir.

**Ürün sahibi: Umut Çelik** · [X](https://x.com/umutc6230) · [GitHub](https://github.com/umutc6230)

## Özellikler
- **Sohbet:** akan cevap, **Durdur**, cevabın üstünde canlı akan ve sonra katlanan **düşünce bloğu**,
  düşünme seviyesi (Kapalı / Dengeli / Derin), sohbet geçmişi, arama, yeniden adlandırma, silme.
- **Dosya ekleme:** resim (OCR / görsel soru), PDF (seçilebilir yazı varsa doğrudan, taranmışsa sayfa
  sayfa OCR), ses (wav/mp3, yalnız Gemma 4), metin dosyaları. Sürükle-bırak ve yapıştırma.
- **Karşılaştır:** aynı soru seçilen modellere sırayla; cevaplar, yükleme süresi, token/sn yan yana.
- **OCR testi:** resim/PDF + beklenen metin -> doğruluk yüzdesi, Türkçe harf sayısı, isteğe bağlı JSON.
- **Araç testi:** demo araçlar (kur, hesap, hava, saat, birim çevirme); her çağrı ve sonucu canlı.
- **Test paketi:** mantık, araç çağırma, JSON, Türkçe OCR, sansürsüzlük; model başına puan tablosu.
- **AI Ayarları:** model seçimi (RAM ihtiyacı, yetenekler, dosya durumu), düşünme seviyesi, sistem
  istemi, sıcaklık, model klasörü, otomatik başlatma, "Test" butonu (süre, sonuç, maliyet: 0).
- Bellek uyarısı: boş RAM modelin ihtiyacından azsa mesaj kutusunun üstünde uyarı.
- **Sohbette araçlar (salt okunur):** model masaüstünü ve klasörleri listeleyebilir, metin dosyası
  okuyabilir, dosya arayabilir; hesap/saat/birim çevirme. Silme/yazma aracı yoktur; `.env`, ssh
  anahtarı, parola ve tarayıcı profil dosyaları okunmaz. Her araç adımı cevapta açılır satır olarak görünür.
- **Sohbet devamı:** önceki mesajlardaki resim, PDF/metin yazısı ve ses de modele gider (bağlam
  bütçesine sığmayan en eski ekler için uyarı).
- **Skill'ler ve talimatlar (Claude Code mantığı):** `~/.claude/CLAUDE.md` ve `@import`'ları (örn.
  brain `BRAIN-POLICY.md`) her sohbete talimat olarak eklenir; uygulamanın kendi `AGENTS.md`'si
  düzenlenebilir. `~/.claude/skills` ve `~/Documents/brain/skills` otomatik bulunur; model uygun
  skill'i `skill_kullan` ile yükler, çok güçlü eşleşen skill otomatik yüklenir. Uygulamaya özel
  skill eklenip silinebilir; her skill açılıp kapatılabilir. Skill'ler yalnız okunur.
- **Modeller (Hugging Face mağazası):** GGUF modelleri ara; her sonuçta bu bilgisayarın RAM ve
  diskine göre "✓ Çalışır / ⚠ Zorlanır / ✗ Çalışmaz" göstergesi. İndirme arka planda, kaldığı
  yerden devam eder, SHA256 ile doğrulanır; indirilen model listeye eklenir. Yüklü modeller silinebilir.
- **Yerel sunucu (Ollama gibi):** Studio açıkken modeller diğer uygulamalara sunulur.
  Ollama uyumlu `http://127.0.0.1:11434` (`/api/tags`, `/api/show`, `/api/chat`, `/api/generate`) ve
  OpenAI uyumlu `http://127.0.0.1:11434/v1` (`/v1/models`, `/v1/chat/completions`). İstenen model
  kapalıysa Studio açar/değiştirir. Ollama destekli uygulamalar (GridMind: AI motoru → *Local model
  (Ollama)*) ayar değiştirmeden bağlanır; OpenAI/OpenRouter kullananlar yalnız adresi değiştirir.
  Pencere olmadan arka planda: `Sunucu.bat`, kapatmak: `Sunucu-Durdur.bat`.
- **Claude Code yerel modelle:** sunucu Anthropic uyumlu uçları da verir (`/v1/messages`,
  `/v1/messages/count_tokens`), yani Claude Code bulut ve API anahtarı olmadan yerel modelle çalışır.
  Portable klasörde `Claude-Yerel.bat [model]` (çalışılacak klasörde açın). TermFlow Agent IDE:
  Ayarlar > AI Providers > **Add Local Models**. Claude Code'un `adaptive` düşünme isteği yerel
  modelde kapalı tutulur. Not: dahili GPU'da ilk tur (~5K token) birkaç dakika sürer; küçük model
  basit dosya işlerinde iyi, uzun ajan görevlerinde zorlanır.
- **Bağlam boyutu:** 8K / 16K / 32K (talimatlar ~3K token yer; 16K önerilir).

## Gereksinimler
- Windows 10/11 (WebView2 hazır gelir), Python 3.12 (kaynaktan çalıştırmak için).
- Model klasörü (varsayılan `C:\Users\umuti\Projects\llm`):
  `llama.cpp\llama-server.exe` (Vulkan) + `models\*.gguf`. Desteklenen modeller:
  - `deepseek-heretic`: DeepSeek-V4-Pro Qwen3.5 9B heretic (i1-Q4_K_M, ~6.2 GB)
  - `gemma4-12b-heretic`: Gemma 4 12B heretic QAT Q4_0 (~7.8 GB, ses girişi var)
  - `gemma4-e4b-heretic`: Gemma 4 E4B ultra-uncensored heretic (i1-Q4_K_M, ~5.9 GB, ses girişi var)
- Dahili GPU'lu bilgisayarda model sistem RAM'ini kullanır: modelin boyutundan ~1-2 GB fazla boş RAM
  gerekir. Oyun/tarayıcı açıkken resim işleme "bellek yetmedi" hatası verebilir.

## Çalıştırma
**Portable (önerilen):** `Baslat.bat` ya da `YerelAIStudio.exe`. Kurulum ve yönetici izni gerekmez;
klasör istenen yere kopyalanır. Ayarlar, sohbetler ve ekler klasörün içindeki `data\` altında durur;
registry, AppData ya da başlangıç girdisi yazılmaz. Kaldırmak için klasörü silmek yeterli.

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
Yalnız Windows'ta çalışır (llama-server.exe ve WebView2 Windows'a özel).

## Geliştirme
```bat
pip install -r requirements-dev.txt
ruff format . && ruff check .
pytest --cov
paketleme\derle.bat     :: temiz venv'de PyInstaller -> dist\YerelAIStudio\ (portable klasör)
```
Model istemcisi `app/services/yerel_llm.py`, brain skill'i `yerel-llm-deepseek`'in kopyasıdır.

## Lisans / not
Sansürsüz modeller içerik filtresi uygulamaz; kullanıcıya dönük kullanımda sorumluluk kullanıcıdadır.
