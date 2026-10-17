# Kaynak kayıp analizi

Ölçüm: 2026-10-17. Kod değiştirilmedi; çözümler yalnızca önerilir. «main'de çalıştırıcıda hata veriyor muydu» sütunu, main'in (d245ee9) GitHub çalıştırıcısı günlüklerindeki 12 atlanan kaynaktan gelir.

## 1. Bu dala girmeden önce main'de aktif olan 36 kaynak

| Neden | Kaynak sayısı |
|---|--:|
| hâlâ aktif | 16 |
| 403 | 7 |
| zaman aşımı | 5 |
| besleme doğrulanamadı | 3 |
| robots.txt | 2 |
| başka | 2 |
| şart | 1 |

| Sınıf | Kaynak sayısı |
|---|--:|
| Kayıp yok | 16 |
| Önceden de kayıp (main'de de hata veriyordu) | 11 |
| Bilinçli kapanış | 3 |
| Gerçek kayıp (probe yanlış negatifi) | 2 |
| Gerçek kayıp (UA'ya duyarlı olabilir) | 2 |
| Gerçek kayıp olup olmadığı belirsiz | 1 |
| Önceden de kayıp | 1 |

| Kaynak | Şimdiki durum | Neden (kategori) | Kayıp sınıfı | main'de çalıştırıcıda hata veriyor muydu | Ayrıntı |
|---|---|---|---|---|---|
| HavaHaber | active | hâlâ aktif | Kayıp yok | hayır |  |
| Tolga Özbek Havacılık | active | hâlâ aktif | Kayıp yok | hayır |  |
| Yahoo Finance (THY & Pegasus) | excluded_policy | robots.txt | Bilinçli kapanış | hayır | feeds.finance.yahoo.com/robots.txt: `User-agent: * Disallow: /`. |
| Simple Flying | active | hâlâ aktif | Kayıp yok | hayır |  |
| FlightGlobal | disabled_blocked | 403 | Önceden de kayıp (main'de de hata veriyordu) | evet | HTTPError 403 on /rss |
| AeroTime | active | hâlâ aktif | Kayıp yok | hayır |  |
| Aviation24 | active | hâlâ aktif | Kayıp yok | hayır |  |
| AirDataNews | active | hâlâ aktif | Kayıp yok | hayır |  |
| Flightradar24 | active | hâlâ aktif | Kayıp yok | hayır |  |
| Yahoo Finance Aviation | excluded_policy | robots.txt | Bilinçli kapanış | hayır | feeds.finance.yahoo.com/robots.txt: `User-agent: * Disallow: /`. |
| Lufthansa Group Newsroom | active | hâlâ aktif | Kayıp yok | hayır |  |
| Delta News Hub | active | hâlâ aktif | Kayıp yok | hayır |  |
| Turkish Airlines Blog | disabled_blocked | 403 | Önceden de kayıp (main'de de hata veriyordu) | evet | HTTPError 403 on /en/feed/ |
| Emirates Newsroom | active | hâlâ aktif | Kayıp yok | hayır |  |
| Qatar Airways Official Tumblr | active | hâlâ aktif | Kayıp yok | hayır |  |
| Pegasus Press Room | no_extractable_feed | başka | Gerçek kayıp (probe yanlış negatifi) | hayır | HTML kazıyıcı hâlâ okuyor: son 30 günde 2 makale. Sonda eski HTML kaynaklarını yalnızca son 7 günde sonuç vermezse `no_extractable_feed` sayıyor; sayfa sakin olduğu için yanlış kapandı. |
| American Airlines Newsroom | disabled_blocked | 403 | Önceden de kayıp (main'de de hata veriyordu) | evet | HTTPError 403 |
| United Airlines Newsroom | disabled_blocked | zaman aşımı | Önceden de kayıp (main'de de hata veriyordu) | evet | TimeoutError on /en/us/newsroom |
| Southwest Newsroom | no_extractable_feed | besleme doğrulanamadı | Gerçek kayıp olup olmadığı belirsiz | hayır | Sayfa 200 dönüyor (66 KB) ama kazıyıcı 30 günde 0 makale çıkarıyor, RSS/site haritası yok. main'de de sessiz sıfır vermiş olabilir (hata günlüğünde yoktu, hikâyesi de arşivde yok). |
| Air France Press Releases | active | hâlâ aktif | Kayıp yok | hayır |  |
| KLM Newsroom | active | hâlâ aktif | Kayıp yok | hayır |  |
| Air Canada News Releases | excluded_policy | şart | Bilinçli kapanış | hayır | Şartlar otomatik erişimi açıkça yasaklıyor (kararla `excluded_policy`). |
| Ryanair Newsroom | active | hâlâ aktif | Kayıp yok | hayır |  |
| easyJet Media Centre | no_extractable_feed | başka | Gerçek kayıp (probe yanlış negatifi) | hayır | HTML kazıyıcı hâlâ okuyor: son 30 günde 3 makale. Aynı 7 günlük pencere sorunu. |
| Qantas Newsroom | disabled_blocked | zaman aşımı | Önceden de kayıp (main'de de hata veriyordu) | evet | TimeoutError on / |
| Singapore Airlines Newsroom | no_extractable_feed | besleme doğrulanamadı | Gerçek kayıp (UA'ya duyarlı olabilir) | hayır | Kayıtlı ve denenen tüm basın adresleri HTTP 404 (en_UK/au, us, sg varyantları). main'in çalıştırıcı günlüğünde hata listesinde yoktu, yani tarayıcı kimliğiyle 200 alınıyordu; yeni User-Agent ile 404. Yeni resmî adres bulunamadı; elle kontrol gerekir. |
| ANA Group Press Releases | no_extractable_feed | besleme doğrulanamadı | Önceden de kayıp | evet | main'de de hata veriyordu (zaman aşımı). Şimdi 200 dönüyor ama 12 KB'lık bir gövde (bot doğrulama sayfası gibi), kazıyıcı 0 makale çıkarıyor. |
| Japan Airlines Press Releases | disabled_blocked | 403 | Önceden de kayıp (main'de de hata veriyordu) | evet | HTTPError 403 on /en/ |
| Cathay Pacific Newsroom | active | hâlâ aktif | Kayıp yok | hayır |  |
| Air India Newsroom | disabled_blocked | zaman aşımı | Gerçek kayıp (UA'ya duyarlı olabilir) | hayır | main'in çalıştırıcı günlüğünde hata listesinde yoktu (okuyabiliyordu); şimdi çalıştırıcıdan ve bu bilgisayardan zaman aşımı. Aynı adres bu bilgisayardan 15 sn'de de yanıt vermedi. |
| Etihad Airways News | disabled_blocked | zaman aşımı | Önceden de kayıp (main'de de hata veriyordu) | evet | TimeoutError on /en/news |
| IndiGo Press Releases | disabled_blocked | zaman aşımı | Önceden de kayıp (main'de de hata veriyordu) | evet | TimeoutError on /press-releases.html |
| JetBlue Investor News | disabled_blocked | 403 | Önceden de kayıp (main'de de hata veriyordu) | evet | HTTPError 403 |
| Copa Holdings News Releases | disabled_blocked | 403 | Önceden de kayıp (main'de de hata veriyordu) | evet | HTTPError 403 on /press-releases |
| LATAM Investor Releases | disabled_blocked | 403 | Önceden de kayıp (main'de de hata veriyordu) | evet | HTTPError 403 |
| Alaska Airlines Newsroom | active | hâlâ aktif | Kayıp yok | hayır |  |

**Gerçek kayıp** = main'de okunabilen ve şimdi okunamayan, bilinçli kapatılmamış kaynak. **Bilinçli kapanış** = robots.txt ya da açık şart. **Önceden de kayıp** = main'in çalıştırıcıda da hata verdiği kaynak (bu dalda yeni bir kayıp değil).

## 2. Gerçek kayıpların kök nedeni ve meşru çözüm önerileri (uygulanmadı)

1. **Pegasus Press Room ve easyJet Media Centre — sondanın yanlış negatifi.** İkisinin HTML kazıyıcısı bu bilgisayardan hâlâ çalışıyor (30 günde 2 ve 3 makale). Sonda, eski HTML kaynaklarını yalnızca son 7 günde makale çıkarırsa «çalışıyor» sayıyor; sakin bir haftada kaynak `no_extractable_feed`e düşüyor. **Öneri:** eski HTML kaynaklarını doğrulama ölçütüyle aynı pencerede (son 90 gün, en az bir öğe) değerlendirmek; iki kaynak yeniden aktif olur. Yeni adres ya da başka besleme gerekmiyor.
2. **Singapore Airlines — adres taşınmış.** Kayıtlı adres ve beş makul varyant (`en_UK/au|us|sg/media-centre|corporate/newsroom`) HTTP 404; sayfada alternatif besleme yok. main çalıştırıcıda bu adresten hata almıyordu, yani eski sürümün tarayıcı kimliğiyle 200 alınıyordu. **Öneri:** yayıncının güncel basın odası adresini elle doğrulamak; otomatik keşfin bulabileceği meşru bir alternatif (aynı alan adında besleme/site haritası) çıkmadı.
3. **Air India — zaman aşımı.** main çalıştırıcıda hatasız okuyordu; şimdi hem çalıştırıcıdan hem bu bilgisayardan 15 sn'de yanıt yok. Tek başına User-Agent'a bağlanamayacak kadar sert bir engel; haftalık yeniden deneme zaten devrede. **Öneri:** bekleyip yeniden denemeye bırakmak.
4. **Southwest — kazıyıcı boş.** Sayfa 200, kazıyıcı 0 makale çıkarıyor, besleme/site haritası/JSON-LD yok (en yaygın RSS yolları 404). main'de de çalışmıyor olabilir. **Öneri:** kayıp saymadan `no_extractable_feed` olarak bırakmak.
5. **403 ve zaman aşımı veren 12 kaynak** main'de de hata veriyordu (FlightGlobal, THY Blog, American, United, Qantas, JAL, Etihad, IndiGo, JetBlue, Copa, LATAM, ANA): bu dalın kaybı değil. Aynı kaynaklar iki farklı User-Agent ile iki sondada aynı sonucu verdi; neden çalıştırıcının veri merkezi ağı. **Meşru çözüm yok** (engeli aşmak yasak); seçenekler ağ değişikliği (başka çalıştırıcı) ya da alternatif besleme aramak.

Ayrıca bulunan bir hata (bu raporun kapsamı dışında, düzeltme ayrı dalda): haftalık yeniden deneme Routes Online News'i «geçerli içerik» diye geri aldı ama aynı çalışmada okuma, kayıtlı adres için tüm öğelerin eksiksiz olmasını isteyen katı doğrulamaya takıldı ve kaynak yine bloklu göründü.

## 3. Kapsam boşluğu: bloklu havayollarının haberi diğer kaynaklardan geliyor mu?

Son 7 gün, 14 havayolu hedefi için; veri: aktif kaynaklardan toplanan 159 makale (bu bilgisayardan okundu), kümeleme sonrası hikâye sayısı. «Listeye giren»: skor ≥ 40 ve savunma/yatırım süzgecinden geçen.

| Havayolu | Hikâye (7 gün) | Listeye giren | Haberi getiren kaynaklar | En yüksek skorlu hikâye |
|---|--:|--:|---|---|
| American Airlines | 4 | 0 | AirDataNews, Simple Flying, Tolga Özbek Havacılık | 30.5 Why American Airlines' Longest-Ever Flight Needs Just 51 Business Clas |
| United Airlines | 1 | 0 | AeroTime | 30.5 United begins Starlink rollout on 737 MAX 8 fleet, starting with Guam- |
| JetBlue **HİÇ HABER YOK** | 0 | 0 | — | — |
| Japan Airlines | 1 | 1 | AirDataNews | 57.5 Japan Airlines orders up to 26 Embraer E190-E2 jets, following rival A |
| LATAM | 1 | 0 | Simple Flying | 30.5 8 Largest Airline Loyalty Programs In The World By Disclosed Member Co |
| Qantas | 1 | 1 | Emirates Newsroom | 61.5 Emirates celebrates 30 years of strong partnership with Australia |
| Air India | 1 | 1 | Aviation24 | 68.8 Air India Frankfurt–Delhi flight diverts to Jaipur after suspected acc |
| Etihad | 1 | 1 | Aviation24 | 51.5 Condor launches daily Berlin–Abu Dhabi flights with Etihad codeshare |
| IndiGo **HİÇ HABER YOK** | 0 | 0 | — | — |
| IAG (BA/IB/VY/EI) | 3 | 0 | Airbus Press Releases, HavaHaber, Simple Flying | 30.5 Why Does One Of The World's Biggest A380 Fleets Have Such A Small Netw |
| Air France-KLM | 4 | 1 | AirDataNews, Flightradar24, HavaHaber, KLM Newsroom | 70.5 Statement situation Middle East |
| Qatar Airways | 1 | 0 | HavaHaber | 30.5 Qatar Airways, 3 Boeing 787-9 için ilk kez JOLCO finansman modelini ku |
| Copa **HİÇ HABER YOK** | 0 | 0 | — | — |
| Turkish Airlines | 2 | 1 | AeroTime, HavaHaber, Tolga Özbek Havacılık | 73.5 THY ve CFM’den 600 motorluk dev anlaşma.. Murat Şeker’den ilk değerlen |

Hiç haberi çıkmayan havayolları: JetBlue, IndiGo, Copa. Bunların kendi haber odaları bloklu ve başka kaynak onları 7 günde hiç anmadı; kapsam boşluğu olarak işaretlendi.

