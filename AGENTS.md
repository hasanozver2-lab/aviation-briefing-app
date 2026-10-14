# Aviation Briefing App (iOS PWA & Executive Mobile Cockpit)

Bu proje, Türk Hava Yolları (THY) ve havacılık sektörü yöneticileri için geliştirilmiş, son 48 saatlik (günlük) ve son 1 saatlik (saatlik) doğrulanmış havacılık istihbaratını iPhone ve mobil cihazlardan takip etmeyi sağlayan PWA (Progressive Web App) ve analiz servisidir.

## Proje Yapısı
- `engine.py`: Havacılık RSS kaynaklarını (Simple Flying, FlightGlobal, Reuters, Google News TR vb.) toplayan, `gemini-2.5-flash` ile prompt kurallarına göre analiz eden ve `briefing_cache.json` oluşturan motor.
- `server.py`: Python yerel HTTP sunucusu ve REST API (`/api/briefing`, `/api/refresh`). Yerel ağdaki iPhone'ların erişebilmesi için `0.0.0.0:8090` üzerinde çalışır ve terminalde QR kod basar.
- `static/`: Mobil arayüz dosyaları (PWA).
  - `index.html`: iPhone ve mobil odaklı, THY kurumsal renklerinde (`#C70A0C`, `#FFFFFF`, `#000000`) 2 katmanlı (Top Summary + Detay Kartları) executive arayüz.
  - `manifest.json`: iOS Safari "Ana Ekrana Ekle" PWA manifesti.
  - `icon.svg` / `icon-192.png`: THY temalı uygulama ikonu.

## Geliştirme Kuralları
- Stil ve renk paleti: THY Kırmızısı `#C70A0C`, Beyaz `#FFFFFF`, Siyah `#000000`.
- Katmanlı yapı:
  - Layer 1: Üstte tıklandığında habere kayan iç çapa (anchor) bağlantılı özet başlıklar.
  - Layer 2: Altta detaylı analiz kartları, `Data Points:`, `THY Impact Assessment:` ve `Back to top summary` navigasyonu.
- Python ortamı: `q:\DEV\.venv\Scripts\python.exe`
