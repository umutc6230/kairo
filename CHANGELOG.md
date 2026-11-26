# Changelog

Kairo icin onemli degisiklikler. En yeni en ustte. Tweet'e girmemis kayitlar "Yayinlanmamis" altinda birikir.

## Yayinlanmamis
- Sabit/uygulayıcı modelli görevlerde bağlam penceresi aktif model yerine görevin kendi modeline göre hesaplanır; CLI izin köprüsü Codex ve Antigravity CLI sağlayıcılarını da kapsayacak şekilde genişletildi.

## 2026-11-26 (tweet: 2026-11-26)
- VS Code köprüsü uçtan uca bağlandı: Kairo etkin port ve oturum bilgisini `data/baglanti.json` ile paylaşır, eklenti otomatik bağlanır ve seçili kod sohbet kutusunda bağlam çipi olarak görünür.
- Gizli proje ve günlük bütçe yönlendirmesi artık ajan görevlerini (abonelik CLI dahil) ve sohbet maliyetlerini kapsar; yerel yedek olarak Ollama ve LM Studio desteklenir.
- Claude Code izin köprüsü (`PreToolUse` hook ve arayüz onay kartı) ile güvenilir projede otomatik geliştirici komut izni eklendi.
- Diğer bulut sağlayıcılarında SSRF/loopback koruması, destekleyen modellere `reasoning_effort` ve kart komutu boş klasör koruması eklendi.
- Ollama modellerinde önbellek boşken bağlamın 8192 token'a kırpılması düzeltildi; küçük bağlamla açılmış Ollama sunucularında Türkçe çözüm yönlendirmesi ve ayar değişiminde süreç yenileme eklendi.
- Mini arayüz kart köprüsüne onaylı `yenile` desteği (`window.kairo.yenile`) eklendi; kartlar modeli kullanıcı onayıyla yeni istemle tekrar çağırabilir.
- Hafif VS Code bağlantısı eklendi: `/api/editor/baglam` uçları ve sıfır bağımlılıklı `integrations/vscode/` eklentisi (`Ctrl+Alt+K`).
- Kayıtlı ve parametreli iş akışı şablonları (`/api/akis-sablonlari` ve `/akis <şablon_id>`) eklendi; yerleşik `pr-incele-test`, `hata-avcisi` ve `surum-hazirla` şablonlarıyla gelir.
- Uygulama içi sürüm kontrolü (`/api/guncelleme`, durum çubuğu bildirimi ve Ayarlar > Hakkında denetimi) eklendi.
- Kum dışı `git`/`worktree` çağrılarında `core.pager`, `core.sshCommand`, `protocol.file.allow` ve `diff.external` sertleştirmesi, Proje penceresinde tek tıkla Windows Kum Havuzu anahtarı eklendi.
- Proje kodunda AST/regex ve BM25 ile hızlı sınıf, fonksiyon ve metod araması yapan `proje_sembol_ara` aracı eklendi.
- Sağ panel ve `/maliyet` komutuyla günlük/7 günlük/30 günlük harcama, önbellek ve yerel kullanım tasarrufunu gösteren analitik panosu eklendi.
- Yazma kutusuna tek tıkla eller serbest "Sesli sohbet modu" (dikte -> otomatik gönder -> cevabı sesli oku) eklendi.
- Oturumlar arası koordinasyon panosu `koordinasyon.json` dosyasında kalıcı hale getirildi; çoklu süreçlerde dosya kilitleri ve mesajlar korunur.
- Gizli proje ve günlük bulut bütçe sınırı (`gunluk_butce_usd`) eklendi; koşul oluştuğunda sohbet istekleri otomatik yerel modele yönlendirilir.
- Çalışan ajan görevlerinde sohbet akışı 1.5 sn yoklama yerine artımlı SSE (`mod=artimli`) ile güncellenir.
- Telegram kanalına `/onaylar`, `/onayla <id>`, `/reddet <id>` komutları ve onay gerektiğinde otomatik bildirim eklendi.
- Uzak web arayüzünde oturum yenileme, mobil uyumluluk, tema/kontrast ve İngilizce çeviri eksikleri (1903 anahtar) tamamlandı.
- Güvenlik ve izin kontrolleri sertleştirildi: Telegram, MCP ve webhook sırları DPAPI ile şifrelendi; dosya/yol kapsamı, SSRF ve API geçidi korumaları güçlendirildi.
- Sağlayıcı akış hataları (OpenRouter, Ollama, yerel LLM), ajan döngü/özetleme korumaları ve arka uç hata yönetimi düzeltildi.
- Arayüzde kopyala/durdur kontrolleri, kısayol yönetimi, dikte/eklenti/görev görünümleri ve açık tema okunabilirliği iyileştirildi.
- Alt ajan profilleri model, düşünme seviyesi, skill, MCP ve izin kapsamı ile ayrı çalışma dalı tanımlayabilir.
- Kapanan çalışma dalının sonucu sohbet kartında görünür ve gönderilemeyen mesaj taslağa geri gelir.
- İki model ayarlı görevlerde koordinatör planlar ve inceler, uygulama işleri ayrı modele devredilir.
- Ayrıntılı raporlar için Markdown dosyası hazırlanır ve tamamlanan yanıtın altında Kopyala ve Paylaş bulunur.
- Sohbette aktif işlem, karakter ve Plan step öneki olmadan tek satırda gösterilir.
- Sohbet kartındaki Pause, Continue ve Cancel düğmeleri kaldırıldı. Bitmemiş görevler yazma kutusundan durdurulabilir.
- Sohbette çalışan görev aktif işlemi gösterir ve yazma kutusundan durdurulur.
- Görevleri durduran toplam token sınırı kaldırıldı.
- Plan yalnız sohbet kartında gösterilir.
- Worktree görevleri plan öncesinde uygun skill'i seçip görev kartında gösterir.
- Görev kartı ve adımlarında kullanılan model görünür.
- Sohbette İzleyici uyarıları bilgi ikonuyla gösterilir.
- İngilizce arayüzde ajan izin menüsünün tüm mod adları ve açıklamaları çevrildi.
- Proje yok ve Kişisel klasörler grubundaki sohbetler menüden silinebilir.
- Proje dışı dosya işlemleri varsayılan olarak Windows kullanıcı klasöründen başlar.
- Sohbet durduruldugunda tamamlanan arac sonuclari gecmiste korunur.

## 2026-11-19 (tweet: 2026-11-19)
- Docker'siz Windows kum havuzu (AppContainer): ajan yalniz proje icine yazar, ag kapali
- Mesajda metin secince menu: yan sohbet baslat, alintiyla yanitla, kopyala
- Mesaj altinda dallan, sabitle, yeniden dene, duzenle; solda mesaj gezinme seridi
- Yazma kutusunda baglam halkasi ve dokum penceresi
- Exe'de metin secme/kopyalama, acilista son sohbet acilir, masaustu araci (comtypes) duzeldi
- Bulut model ile ses dikte (varsayilan kapali), GitHub Action (action.yml)

## 2026-11-18
- Prompt onbellegi, gorev basina maliyet, konusmayi geri sarma
- Alt klasor talimatlari, notebook okuma/duzenleme, GitHub issue/PR araclari
- TS SDK ve OpenTelemetry
- Olcum: 30 gorevde Kairo + DeepSeek V4.1 Flash 90/90 $0.46, Claude Code + Opus 90/90 $10.00
