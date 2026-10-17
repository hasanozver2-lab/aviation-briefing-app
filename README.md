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

### 3. Zamanlanmış yapay zekâ analizi
* Toplama ve Gemini analizi yalnızca GitHub Actions işi içinde çalışır. Vercel API hiçbir zaman kaynak toplamaz veya LLM çağrısı yapmaz; son tamamlanmış JSON snapshot'ını Vercel Blob'dan okur.
* İş başarısız olursa son başarılı snapshot korunur ve API `status: "stale"` döndürür. `last_pipeline_run_at`, son başarılı işin zamanını belirtir.

### 4. Havayolu odaklı kaynak politikası
* Motor, genel medya ve ticari havacılık akışlarında havayolu/havacılık konusu olmayan başlıkları modele göndermeden eler.
* Her haberde kaynak türü görünür: `Mainstream`, `Aviation media`, `Airline IR`, `Official newsroom` veya `Official social`.
* Reuters, Financial Times ve Bloomberg sicilde `paid`, tier 3 ve `active: false` olarak kayıtlıdır. Bu sürümde hiçbirinin ingest'i, küme sinyali, model girdisi veya arayüz bağlantısı açık değildir. Geçerli ticari lisans ve ayrıca onay olmadan etkinleştirilemezler.

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

### 4.1 Kaynak sicili, lisans ve performans ölçümü

Aktif kaynaklar `data/source_registry.sqlite3` içindeki SQLite sicilinde yönetilir. Şema ve idempotent migration dosyası [`migrations/001_source_registry.sql`](migrations/001_source_registry.sql) içindedir; güvenilirlik ağırlıkları yalnızca [`config/source_registry.json`](config/source_registry.json) üzerinden okunur.

| Tier | Kaynak türü | Başlangıç güvenilirlik ağırlığı |
| --- | --- | ---: |
| 1 | Resmî havayolu, havalimanı, üretici, regülatör, EUROCONTROL, ICAO, IATA | 1.0 |
| 2 | Sektör uzman yayını | 0.8 |
| 3 | Büyük haber ajansı / finans medyası | 0.7 |
| 4 | Yüksek hacimli genel veya bölgesel havacılık medyası | 0.4 |

Sicili ve bölge × tier raporunu yeniden üretmek için:

```powershell
q:\DEV\.venv\Scripts\python.exe scripts\source_registry_report.py
```

Onaysız adaylar [`config/source_candidates.json`](config/source_candidates.json) içinde her zaman `active: false` olarak tutulur. Erişim testini çalıştırmak adayları aktifleştirmez:

```powershell
q:\DEV\.venv\Scripts\python.exe scripts\test_source_candidates.py
```

Lisanslı bir kaynak ileride ayrıca onaylanırsa yalnızca başlık, yayın zamanı ve URL işlenebilir; gövde metni, özet veya snippet saklanmaz, Gemini'ye gönderilmez veya arayüzde yayınlanmaz.

`source_stats` günlük toplama sonuçlarından kaynak katkısı, kümelerdeki madde sayısı, briefing'e giren kümeler ve ilk-haberleyen ön ölçümünü tutar. İlk-haberleyen metriği kümeleme öncesi muhafazakâr başlık benzerliği ölçümüdür; pazar geneli için münhasır ilk yayın iddiası değildir ve skora girmez.

### 4.2 GitHub Actions + Vercel Blob pipeline'ı

`daily` iş her saat başında iki dakika sonra, `hourly` iş ise her 15 dakikada bir çalışır. İş; kaynakları toplar, yerel SQLite üzerinde etiketleme/değerlendirme yapar, tamamlanmış sonucu sabit Blob yollarına yazar:

```text
briefings/daily.json
briefings/hourly.json
briefings/daily-status.json
briefings/hourly-status.json
```

Vercel Blob Storage'da **public** store oluşturun. GitHub repository secrets'a `BLOB_READ_WRITE_TOKEN`, `BLOB_PUBLIC_BASE_URL`, `GEMINI_API_KEY` ve `EIA_API_KEY` ekleyin. Vercel Production environment'a yalnızca `BLOB_PUBLIC_BASE_URL` ekleyin. Yazma token'ı Vercel'e verilmez.

Yerel geliştirmede `MARKET_DB_PATH` ile SQLite dosyasını seçebilirsiniz; varsayılan `data/pipeline.sqlite3`'dir ve commit edilmez. Zamanlanmış iş her koşuda EIA/ECB'den yeterli geçmiş gözlemi yeniden yüklediği için GitHub runner'ındaki bu veritabanı Vercel tarafından okunmaz.

### 4.3 Piyasa ve Yakıt katmanı

* Brent yalnızca EIA `RBRTE` serisinden gelir; WTI `RWTC` kullanılmaz.
* Jet yakıtı serisi EIA `EER_EPJK_PF4_RGC_DPG`'dir ve her yerde **ABD Körfez Kıyısı jet yakıtı** olarak adlandırılır. Küresel jet yakıtı fiyatı olarak yorumlanmaz.
* Jet yakıtı USD/galon değeri 42 ile USD/varile çevrilerek Brent marjı hesaplanır. Günlük, haftalık, 30 günlük değişimler; 52 haftalık konum ve konfigürasyondaki eşik aşımları hesaplanır.
* ECB iş günü referans kurlarıyla USD karşısında EUR, GBP, JPY, CNY, INR, TRY ve BRL gösterilir. Hafta sonu/tatilde son geçerli gözlem tarihi açıkça gösterilir.
* IATA Jet Fuel Price Monitor verisi çekilmez, saklanmaz veya yeniden yayınlanmaz; yalnızca dış kaynak bağlantısı sunulur.

Şema [`migrations/002_market_data.sql`](migrations/002_market_data.sql), eşikler [`config/market_indicators.json`](config/market_indicators.json), taksonomi ve başlangıç ağırlıkları [`config/event_taxonomy.json`](config/event_taxonomy.json) içindedir.

Yeni taksonomi türleri: `fuel_energy` (0.90), `fx_currency` (0.50), `macro_demand` (0.75), `airline_financials` (0.85), `capital_markets` (0.45), `geopolitics_airspace` (0.95). `geopolitics_airspace`, yalnız jeopolitik terimle birlikte bir havacılık varlığı veya hava sahası terimi varsa atanır.

Birinci finansal kaynak adayları erişim raporu [`reports/financial_source_access.md`](reports/financial_source_access.md) içindedir. SEC EDGAR dışında tüm IR/KAP sayfaları adaptör ve kaynak-bazlı kullanım koşulu onayı beklediğinden pasiftir.

IATA dizinindeki tüm üyeler için kaynak URL'leri tek seferde güvenilir biçimde keşfedilemediği için kayıtlar doğrulanmış feed/API URL'leriyle genişletilir. Böylece özel (halka açık olmayan) havayolları ve RSS yayınlamayan siteler için yanlış/uydurma kaynak gösterilmez.

### 5. Tek Tıkla Paylaş / E-Posta Kopyala
* Üst bardaki **"Paylaş"** butonuna basarak bülteni formatlı şekilde panoya kopyalayabilir veya iOS Paylaş menüsüyle WhatsApp, Mail ya da Telegram üzerinden ekibinize gönderebilirsiniz.

---

## Yerel probe (kendi bilgisayarınızdan kaynak denemesi)
GitHub çalıştırıcısı bazı haber odalarından 403 ya da zaman aşımı alır; kendi ağınızdan açılanları görmek için `python scripts/probe_local.py` komutunu çalıştırın (Python 3.11 ya da üstü; ek paket gerekmez, yalnızca standart kütüphane kullanılır, `requirements.txt` bunu not eder; bu depoda kullanılan sürüm Python 3.12). Betik 95 kaynağın hepsini aynı kendini tanıtan User-Agent ve robots.txt kurallarıyla, alan adı başına sıralı dener; her kaynak için HTTP kodunu, süreyi ve son 90 gündeki öğe sayısını `reports/probe_local.json` dosyasına yazar ve çalıştırıcı sonucuyla (`reports/source_probe.json`) karşılaştıran bir özet basar: hangi kaynaklar yalnızca sizin ağınızdan açılıyor. Betik yalnızca okur; veri dalına, arşive, kaynak listesine ya da herhangi bir secret'a yazmaz.

## 🚀 Başlatma

Terminalden veya `start_app.cmd` dosyasına çift tıklayarak başlatabilirsiniz:

```powershell
cd Q:\DEV\aviation-briefing-app
q:\DEV\.venv\Scripts\python.exe scripts\dev_server.py 8090
```
