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
```bat
pip install -r requirements.txt
baslat.bat              :: pencere
python -m app --tarayici  :: varsayılan tarayıcıda
python -m app --version
```
Veri (sohbetler, ekler, ayarlar): kaynaktan çalışırken `data\`, kurulu exe'de
`%LOCALAPPDATA%\YerelAIStudio\`. `YAS_VERI_DIZINI` ortam değişkeniyle değiştirilebilir.

## Geliştirme
```bat
pip install -r requirements-dev.txt
ruff format . && ruff check .
pytest --cov
paketleme\derle.bat     :: temiz venv'de PyInstaller -> dist\YerelAIStudio\YerelAIStudio.exe
```
Model istemcisi `app/services/yerel_llm.py`, brain skill'i `yerel-llm-deepseek`'in kopyasıdır.

## Lisans / not
Sansürsüz modeller içerik filtresi uygulamaz; kullanıcıya dönük kullanımda sorumluluk kullanıcıdadır.
