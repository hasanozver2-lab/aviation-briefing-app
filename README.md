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

### 4. Tek Tıkla Paylaş / E-Posta Kopyala
* Üst bardaki **"Paylaş"** butonuna basarak bülteni formatlı şekilde panoya kopyalayabilir veya iOS Paylaş menüsüyle WhatsApp, Mail ya da Telegram üzerinden ekibinize gönderebilirsiniz.

---

## 🚀 Başlatma

Terminalden veya `start_app.cmd` dosyasına çift tıklayarak başlatabilirsiniz:

```powershell
cd Q:\DEV\aviation-briefing-app
q:\DEV\.venv\Scripts\python.exe scripts\dev_server.py 8090
```
