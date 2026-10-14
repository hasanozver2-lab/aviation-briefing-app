# ✈️ Aviation Briefing — Executive Mobile App (iOS PWA)

Bu proje, havacılık sektörü ve  yöneticileri için hazırlanmış; son 48 saatlik (Günlük) ve son 1 saatlik (Saatlik) doğrulanmış havacılık istihbaratını **iPhone ve mobil cihazlardan tek dokunuşla** takip etmenizi sağlayan yerel mobil web uygulamasıdır (PWA).

---

## 📱 iPhone'a Nasıl Yüklenir? (30 Saniye)

1. **Aynı Wi-Fi:** iPhone'unuzun bilgisayarınızla aynı Wi-Fi ağına bağlı olduğundan emin olun.
2. **Safari'yi Açın:** Safari adres çubuğuna sunucu adresinizi yazın:
   👉 **`http://172.20.10.4:8090`** (veya bilgisayarınızda **`http://localhost:8090`**)
3. **Ana Ekrana Ekle:** 
   - Safari'nin alt ortasındaki **Paylaş (Kare + Yukarı Ok `⎋`)** simgesine dokunun.
   - Aşağı kaydırıp **"Ana Ekrana Ekle" (Add to Home Screen)** seçeneğini seçin.
   - Sağ üstteki **"Ekle"**ye basın.
4. **Hazır!** Ana ekranınızda THY kırmızısı özel **Aviation Briefing** ikonu belirecektir. Üzerine dokunduğunuzda Safari çubuğu olmadan, tam ekran yerel bir iOS uygulaması gibi açılır.

---

## 🌟 Öne Çıkan Özellikler

### 1. İki Katmanlı Executive Mimari (Two-Layer Structure)
* **Layer 1 (Top Summary List):** Sayfanın en üstünde, iç çapa (anchor) bağlantılı tıklanabilir özet başlık listesi. Bir başlığa dokunduğunuzda sayfa yumuşak bir animasyonla alttaki ilgili haber kartına kayar.
* **Layer 2 (Detailed Story Blocks):** Her haber için özel tasarlanmış executive analiz kartı:
  * **Lead:** Kısa giriş paragrafı
  * **Detailed Analysis:** Strateji, kapasite, talep, gelir ve filo etkilerini içeren 4-6 madde
  * **Data Points:** Sayısal veriler (kapasite, bilet iptalleri, teslimatlar, marjlar)
  * **THY Impact Assessment:** Doğrudan Türk Hava Yolları perspektifinden stratejik değerlendirme
  * **Why it matters:** Tek cümlelik pazar/operasyonel risk özeti
  * **Original Source:** Doğrudan haber kaynağına giden gerçek bağlantı
  * **Back to top summary:** Anında üstteki özet listesine geri dönen navigasyon butonu

### 2. Canlı Mod Geçişi
* **Günlük (Daily / 48h):** Son 48 saatin kapsamlı sektör istihbaratı.
* **Saatlik (Hourly / 1h):** Son 1 saatin kritik flaş gelişmeleri veya izleme listesi (Watchlist).

### 3. Yapay Zeka Destekli Analiz
* `Q:\DEV\.env` dosyasındaki **Gemini 2.5 Flash** anahtarı ile Google News, Simple Flying, Reuters, FlightGlobal ve KAP havacılık akışlarını anında analiz eder ve prompt formatına dönüştürür.

### 4. Havayolu odaklı kaynak politikası
* Motor, genel medya ve ticari havacılık akışlarında havayolu/havacılık konusu olmayan başlıkları modele göndermeden eler.
* Her haberde kaynak türü görünür: `Mainstream`, `Aviation media`, `Airline IR`, `Official newsroom` veya `Official social`.
* Reuters, Financial Times ve Bloomberg gibi lisanslı kaynaklar için Vercel/yerel ortamda yetkili RSS/API URL'leri aşağıdaki değişkenlerle tanımlanır. İçeriğin tam metni kopyalanmaz; başlık, kısa açıklama ve doğrudan kaynak bağlantısı kullanılır.

```text
REUTERS_AVIATION_RSS_URL=https://...
FT_AVIATION_RSS_URL=https://...
BLOOMBERG_AVIATION_RSS_URL=https://...
```

Resmi havayolu yatırımcı ilişkileri, newsroom ve sosyal akışları toplu olarak eklemek için `AIRLINE_BRIEFING_SOURCES_JSON` kullanılır. RSS/Atom veya resmi API URL'leriyle kayıt eklenir; sayfa kazıma ve sosyal platformların kullanım şartlarını aşan otomatik scraping yapılmaz.

Yerleşik resmi kaynak seti Lufthansa, Delta, Turkish Airlines, Emirates, Qatar Airways ve Pegasus'a ek olarak American, United, Southwest, Air France, KLM, Air Canada, Ryanair, easyJet, Qantas, Singapore Airlines, ANA, Japan Airlines, Cathay Pacific, Air India, Etihad, IndiGo, JetBlue, Copa, LATAM ve Alaska akışlarını kapsar. RSS/Atom sağlayanlar doğrudan feed olarak; yalnızca newsroom/IR sayfası sağlayanlar tarih zorunlu HTML adaptörüyle okunur. Tarih doğrulanamazsa duyuru akışa alınmaz.

```json
[
  {
    "name": "Pegasus Investor Relations",
    "url": "https://example.com/feed-or-api",
    "source_type": "airline_ir",
    "airline": "Pegasus",
    "airline_code": "PGSUS",
    "fetch_mode": "rss",
    "date_required": true
  },
  {
    "name": "Lufthansa Group Newsroom",
    "url": "https://example.com/feed-or-api",
    "source_type": "airline_newsroom",
    "airline": "Lufthansa Group",
    "fetch_mode": "html",
    "html_link_class": "press__link",
    "html_href_contains": "/press-release/",
    "html_date_context_chars": 1800,
    "date_required": true,
    "resolve_detail_dates": true
  }
]
```

Pegasus Press Room için tarih kontrollü HTML adaptörü de aktiftir; yayın tarihi detay sayfasından doğrulanamayan duyurular akışa alınmaz. Bu kural özellikle saatlik radarın eski IR/duyurularla kirlenmesini önler.

IATA dizinindeki tüm üyeler için kaynak URL'leri tek seferde güvenilir biçimde keşfedilemediği için kayıtlar doğrulanmış feed/API URL'leriyle genişletilir. Böylece özel (halka açık olmayan) havayolları ve RSS yayınlamayan siteler için yanlış/uydurma kaynak gösterilmez.

### 5. Tek Tıkla Paylaş / E-Posta Kopyala
* Üst bardaki **"Paylaş"** butonuna basarak bülteni formatlı şekilde panoya kopyalayabilir veya iOS Paylaş menüsüyle WhatsApp, Mail ya da Telegram üzerinden ekibinize gönderebilirsiniz.

---

## 🚀 Başlatma

Terminalden veya `start_app.cmd` dosyasına çift tıklayarak başlatabilirsiniz:

```powershell
cd Q:\DEV\aviation-briefing-app
q:\DEV\.venv\Scripts\python.exe scripts\dev_server.py 8090
```
