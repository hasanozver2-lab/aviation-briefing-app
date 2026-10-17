# Kaynak genişletme raporu

Çalıştırıcı sondası: 2026-10-17T07:26:23+00:00 (Linux-6.17.0-1022-azure-x86_64-with-glibc2.39, Python 3.12.15), süre 253.7 sn. User-Agent: `aviation-briefing-app (github.com/hasanozver2-lab/aviation-briefing-app)`. Ham çıktı: `reports/source_probe.json`; doğrulanan besleme adresleri: `config/feeds_discovered.json`; şart incelemesi: `config/source_terms_review.json`.

## Özet

- Katalogda 95 kaynak var; durumlar: active 28, disabled_blocked 32, excluded_policy 9, no_extractable_feed 19, no_public_feed 7.
- Tek User-Agent (kişisel e-posta yok, tarayıcı kimliği yok), robots.txt (joker karakter destekli), alan adı başına sıralı çekim ve koşullu istek uygulanıyor; makale sayfası çekilmiyor.
- `feed_only` kaynaklarda yalnızca yayıncının halka açık RSS/Atom beslemesi kullanılır (site haritası, JSON-LD ve sayfa kazıma yok). Besleme özeti yalnızca modele bir kez verilir, arşive yazılmaz, API'de dönmez; anlatıdan, başlıkta ve özette olmayan her sayı silinir.
- Sondanın getirdiği değişiklik büyük: tarayıcı kimliğini bırakıp dürüst User-Agent'a geçince daha önce okunan birkaç resmî haber odası da 403/zaman aşımı vermeye başladı (Air Canada, Qantas, Japan Airlines, JetBlue, LATAM, Copa, FlightGlobal, Turkish Airlines Blog ve diğerleri). Bunlar `disabled_blocked` olarak, HTTP koduyla ve sebebiyle listede duruyor.
- SEC EDGAR: altı şirketin hepsi 403 veriyor. SEC adil erişim politikası User-Agent içinde iletişim e-postası istiyor; proje kuralı kişisel e-posta yasakladığı için bu kaynaklar kapalı. Çözüm kararı kullanıcıda (örneğin proje için ayrılmış, kişisel olmayan bir adres).

## Kaynak başına sonuç

| Kaynak | source_type | status | yöntem | çalıştırıcı HTTP | 7 g öğe | havacılık filtresi | ≥ min_score 40 | listeye giren | dil | commercial_use_risk | basis |
|---|---|---|---|--:|--:|--:|--:|--:|---|---|---|
| HavaHaber | trade | active | rss | 200 | 50 | 25 | 10 | 8 | tr | medium | — |
| Tolga Özbek Havacılık | trade | active | rss | 200 | 10 | 10 | 1 | 1 | tr | medium | — |
| Yahoo Finance (THY & Pegasus) | wire_headline | excluded_policy | — | — | 0 | 0 | 0 | 0 | en | high | — |
| Simple Flying | trade | active | rss | 200 | 10 | 10 | 0 | 0 | en | high | headline_only |
| FlightGlobal | trade | disabled_blocked | — | 403 | 0 | 0 | 0 | 0 | en | medium | headline_only |
| AeroTime | trade | active | rss | 200 | 67 | 25 | 7 | 5 | en | high | headline_only |
| Aviation24 | trade | active | rss | 200 | 10 | 10 | 3 | 3 | en | medium | — |
| AirDataNews | trade | active | rss | 200 | 25 | 25 | 5 | 4 | en | medium | — |
| Flightradar24 | trade | active | rss | 200 | 4 | 4 | 0 | 0 | en | medium | — |
| Yahoo Finance Aviation | wire_headline | excluded_policy | — | — | 0 | 0 | 0 | 0 | en | high | — |
| Reuters Aviation | wire_headline | excluded_policy | — | — | 0 | 0 | 0 | 0 | en | medium | headline_only |
| Financial Times Aviation | wire_headline | disabled_blocked | — | 403 | 0 | 0 | 0 | 0 | en | medium | headline_only |
| Bloomberg Aviation | wire_headline | excluded_policy | — | 403 | 0 | 0 | 0 | 0 | en | high | headline_only |
| Lufthansa Group Newsroom | airline_ir | active | legacy_scraper | 403 | 2 | 2 | 2 | 2 | en | medium | — |
| Delta News Hub | airline_ir | active | rss | 200 | 5 | 5 | 5 | 5 | en | high | — |
| Turkish Airlines Blog | airline_ir | disabled_blocked | — | 403 | 0 | 0 | 0 | 0 | en | medium | — |
| Emirates Newsroom | airline_ir | active | legacy_scraper | 404 | 4 | 4 | 2 | 2 | en | high | — |
| Qatar Airways Official Tumblr | airline_ir | active | legacy_scraper | 404 | 0 | 0 | 0 | 0 | en | medium | — |
| Pegasus Press Room | airline_ir | no_extractable_feed | — | 404 | 0 | 0 | 0 | 0 | en | medium | — |
| American Airlines Newsroom | airline_ir | disabled_blocked | — | 404 | 0 | 0 | 0 | 0 | en | medium | — |
| United Airlines Newsroom | airline_ir | disabled_blocked | — | — | 0 | 0 | 0 | 0 | en | medium | — |
| Southwest Newsroom | airline_ir | no_extractable_feed | — | 200 | 0 | 0 | 0 | 0 | en | medium | — |
| Air France Press Releases | airline_ir | active | rss | 200 | 0 | 0 | 0 | 0 | en | medium | — |
| KLM Newsroom | airline_ir | active | rss | 200 | 1 | 1 | 1 | 1 | en | medium | — |
| Air Canada News Releases | airline_ir | disabled_blocked | — | 403 | 0 | 0 | 0 | 0 | en | high | — |
| Ryanair Newsroom | airline_ir | active | html | 200 | 4 | 4 | 3 | 3 | en | high | — |
| easyJet Media Centre | airline_ir | no_extractable_feed | — | 403 | 0 | 0 | 0 | 0 | en | medium | — |
| Qantas Newsroom | airline_ir | disabled_blocked | — | — | 0 | 0 | 0 | 0 | en | medium | — |
| Singapore Airlines Newsroom | airline_ir | no_extractable_feed | — | 404 | 0 | 0 | 0 | 0 | en | medium | — |
| ANA Group Press Releases | airline_ir | no_extractable_feed | — | 404 | 0 | 0 | 0 | 0 | en | high | — |
| Japan Airlines Press Releases | airline_ir | disabled_blocked | — | 403 | 0 | 0 | 0 | 0 | en | medium | — |
| Cathay Pacific Newsroom | airline_ir | active | rss | 200 | 3 | 3 | 0 | 0 | en | medium | — |
| Air India Newsroom | airline_ir | disabled_blocked | — | — | 0 | 0 | 0 | 0 | en | medium | — |
| Etihad Airways News | airline_ir | disabled_blocked | — | — | 0 | 0 | 0 | 0 | en | medium | — |
| IndiGo Press Releases | airline_ir | disabled_blocked | — | — | 0 | 0 | 0 | 0 | en | medium | — |
| JetBlue Investor News | airline_ir | disabled_blocked | — | 404 | 0 | 0 | 0 | 0 | en | high | — |
| Copa Holdings News Releases | airline_ir | disabled_blocked | — | 403 | 0 | 0 | 0 | 0 | en | medium | — |
| LATAM Investor Releases | airline_ir | disabled_blocked | — | 404 | 0 | 0 | 0 | 0 | en | medium | — |
| Alaska Airlines Newsroom | airline_ir | active | rss | 200 | 5 | 5 | 5 | 5 | en | high | — |
| IAG Newsroom | airline_ir | disabled_blocked | — | 403 | 0 | 0 | 0 | 0 | en | medium | — |
| Air France-KLM Newsroom | airline_ir | disabled_blocked | — | 403 | 0 | 0 | 0 | 0 | en | medium | — |
| Qatar Airways Press Releases | airline_ir | disabled_blocked | — | 403 | 0 | 0 | 0 | 0 | en | medium | — |
| LATAM Airlines Press Room | airline_ir | disabled_blocked | — | 403 | 0 | 0 | 0 | 0 | en | medium | — |
| ICAO Newsroom | regulator | no_extractable_feed | — | 200 | 0 | 0 | 0 | 0 | en | high | — |
| IATA Press Room | regulator | no_extractable_feed | — | 404 | 0 | 0 | 0 | 0 | en | high | — |
| FAA Newsroom | regulator | active | rss | 200 | 5 | 5 | 0 | 0 | en | low | — |
| EASA News | regulator | active | rss | 200 | 3 | 3 | 2 | 2 | en | medium | — |
| Eurocontrol News | regulator | no_extractable_feed | — | 200 | 0 | 0 | 0 | 0 | en | medium | — |
| CAAC News | regulator | no_extractable_feed | — | 404 | 0 | 0 | 0 | 0 | en | medium | — |
| DGCA India | regulator | no_extractable_feed | — | 404 | 0 | 0 | 0 | 0 | en | low | — |
| ANAC Brazil | regulator | active | atom | 200 | 2 | 2 | 0 | 0 | en | medium | — |
| NTSB News | regulator | no_extractable_feed | — | 200 | 0 | 0 | 0 | 0 | en | low | — |
| AAIB UK | regulator | active | atom | 200 | 0 | 0 | 0 | 0 | en | low | — |
| BEA News | regulator | active | html | 200 | 5 | 5 | 4 | 4 | en | high | — |
| SHGM News | regulator | no_extractable_feed | — | 200 | 0 | 0 | 0 | 0 | tr | medium | — |
| SEC EDGAR 8-K American Airlines Group | exchange | disabled_blocked | — | 403 | 0 | 0 | 0 | 0 | en | low | — |
| SEC EDGAR 8-K United Airlines Holdings | exchange | disabled_blocked | — | 403 | 0 | 0 | 0 | 0 | en | low | — |
| SEC EDGAR 8-K Delta Air Lines | exchange | disabled_blocked | — | 403 | 0 | 0 | 0 | 0 | en | low | — |
| SEC EDGAR 8-K Southwest Airlines | exchange | disabled_blocked | — | 403 | 0 | 0 | 0 | 0 | en | low | — |
| SEC EDGAR 8-K JetBlue Airways | exchange | disabled_blocked | — | 403 | 0 | 0 | 0 | 0 | en | low | — |
| SEC EDGAR 8-K Alaska Air Group | exchange | disabled_blocked | — | 403 | 0 | 0 | 0 | 0 | en | low | — |
| LSE RNS | exchange | excluded_policy | — | 200 | 0 | 0 | 0 | 0 | en | high | — |
| HKEX News | exchange | excluded_policy | — | 404 | 0 | 0 | 0 | 0 | en | high | — |
| KAP Public Disclosure | exchange | no_extractable_feed | — | 404 | 0 | 0 | 0 | 0 | en | medium | — |
| The New York Times | wire_headline | disabled_blocked | — | 403 | 0 | 0 | 0 | 0 | en | medium | headline_only |
| The Washington Post | wire_headline | disabled_blocked | — | — | 0 | 0 | 0 | 0 | en | medium | headline_only |
| The Wall Street Journal | wire_headline | excluded_policy | — | — | 0 | 0 | 0 | 0 | en | high | headline_only |
| Associated Press Aviation | wire_headline | excluded_policy | — | 403 | 0 | 0 | 0 | 0 | en | high | headline_only |
| CNBC Airlines | wire_headline | no_public_feed | — | 404 | 0 | 0 | 0 | 0 | en | medium | headline_only |
| The Economist | wire_headline | disabled_blocked | — | 403 | 0 | 0 | 0 | 0 | en | medium | headline_only |
| Nikkei Asia | wire_headline | no_public_feed | — | 404 | 0 | 0 | 0 | 0 | en | high | headline_only |
| The Air Current | trade | active | rss | 200 | 3 | 3 | 2 | 2 | en | high | headline_only |
| Aviation Week | trade | no_public_feed | — | 404 | 0 | 0 | 0 | 0 | en | medium | headline_only |
| ch-aviation | trade | no_public_feed | — | 404 | 0 | 0 | 0 | 0 | en | high | headline_only |
| CAPA Centre for Aviation | trade | no_public_feed | — | 404 | 0 | 0 | 0 | 0 | en | medium | headline_only |
| Cirium Thought Cloud | trade | no_public_feed | — | 200 | 0 | 0 | 0 | 0 | en | medium | headline_only |
| OAG Blog | trade | no_public_feed | — | 404 | 0 | 0 | 0 | 0 | en | high | headline_only |
| Routes Online News | trade | disabled_blocked | — | 403 | 0 | 0 | 0 | 0 | en | medium | headline_only |
| AvHerald | trade | excluded_policy | — | — | 0 | 0 | 0 | 0 | en | high | headline_only |
| PhocusWire | trade | disabled_blocked | — | 403 | 0 | 0 | 0 | 0 | en | medium | headline_only |
| China Travel News | trade | disabled_blocked | — | — | 0 | 0 | 0 | 0 | en | medium | headline_only |
| PROS News | tech_vendor | no_extractable_feed | — | 200 | 0 | 0 | 0 | 0 | en | high | — |
| Amadeus Newsroom | tech_vendor | no_extractable_feed | — | 200 | 0 | 0 | 0 | 0 | en | high | — |
| Sabre Insights | tech_vendor | no_extractable_feed | — | 200 | 0 | 0 | 0 | 0 | en | medium | — |
| Accelya News | tech_vendor | active | rss | 200 | 2 | 1 | 0 | 0 | en | medium | — |
| T2RL News | tech_vendor | no_extractable_feed | — | 200 | 0 | 0 | 0 | 0 | en | medium | — |
| Airbus Press Releases | oem | active | rss | 200 | 1 | 1 | 0 | 0 | en | high | — |
| Boeing News Releases | oem | no_extractable_feed | — | 404 | 0 | 0 | 0 | 0 | en | high | — |
| Embraer News | oem | no_extractable_feed | — | 200 | 0 | 0 | 0 | 0 | en | high | — |
| GE Aerospace News | oem | active | rss | 200 | 0 | 0 | 0 | 0 | en | high | — |
| RTX News | oem | disabled_blocked | — | 403 | 0 | 0 | 0 | 0 | en | medium | — |
| Rolls-Royce Press Releases | oem | active | rss | 200 | 3 | 0 | 0 | 0 | en | medium | — |
| Safran News | oem | disabled_blocked | — | 403 | 0 | 0 | 0 | 0 | en | medium | — |
| Bombardier News | oem | active | rss | 200 | 2 | 2 | 1 | 1 | en | high | — |
| Textron Aviation Newsroom | oem | active | html | 200 | 1 | 1 | 1 | 1 | en | high | — |

`7 g öğe`: son 7 günde besleme/sayfadan gelen öğe. `havacılık filtresi`: sıkı havacılık filtresinden (genel beslemelerde) geçen. `≥ min_score 40`: öğenin hikâyesinin skoru 40 ve üstü. `listeye giren`: bu hikâyelerden savunma ve yatırım yorumu süzgecinden de geçenler. Skorlama DEĞİŞTİRİLMEDİ; ağırlıklar ve eşikler aynen duruyor.

## Aktif kaynak sayısı önce / sonra

| | Önce (main) | Sonra (bu dal) |
|---|--:|--:|
| Katalogda aktif | 36 | 28 |
| Hatasız okunan (tek geçiş, bu bilgisayar) | kaydedilmedi | 28 |

Önceki sürüm kaynak başına sonuç tutmuyordu; bu yüzden "önce" için yalnızca katalog sayısı var. Katalogdaki 36 aktif kaynağın 12'si GitHub çalıştırıcısında her çalışmada atlanıyordu (önceki rapor).

## Günlük hikâye sayısı önce / sonra

Measured on 2026-10-17 from one laptop and one moment with the same driver (one collection pass, no per-run cap, 48 h window): main before this branch vs this branch. Not the production archive; the runner sees a different network.

| Kademe | Önce | Sonra |
|---|--:|--:|
| Critical | 3 | 7 |
| Important | 10 | 10 |
| Watch | 3 | 5 |
| Toplam (listede) | 16 | 22 |
| Makale / aday hikâye | 107 / 95 | 93 / 85 |

## tech_vendor gürültüsü

Aktif tech_vendor: Accelya News. 7 günde 2 öğe, 1 tanesi havacılık filtresinden geçti, 0 tanesi min_score üstüne çıktı, 0 tanesi listeye girdi. Önerilen güvenilirlik: keep tier 4 (weight 0.4), the lowest existing tier; no vendor item reached the list in the window, so no further reduction is proposed. PROS, Amadeus, Sabre ve T2RL'de halka açık besleme bulunamadı (PROS ayrıca robots.txt ile `*/feed` yolunu yasaklıyor).

## Çalışma süresi ve Gemini

- Toplama geçişi (tüm kaynaklar, bu bilgisayar): 18.8 sn (önce 22.1 sn).
- Tam çalışma (toplama + anlatı + yayın hazırlığı, kuru çalıştırma, gerçek Gemini): 67 sn; **Gemini çağrısı 2** (çalışma başına üst sınır 2, çağrı başına 8 hikâye; 12 hikâye anlatıldı).
- Sonda iş akışı (95 kaynak, GitHub çalıştırıcısı): 253.7 sn; zaman sınırı 30 dk.

## Kümeleme doğrulaması

Aynı olayın farklı kaynak türlerinden kopyalarının tek hikâyede birleştiği gerçek örnekler:

| Hikâye | Türler | Birleşen kaynaklar | Kaynak |
|---|---|---|---|
| `story-1c2ce9b5a516` New Airbus A350-1000 to Begin Scheduled Service to Tokyo | airline_ir, trade | Lufthansa Group Newsroom, AirDataNews, AeroTime, Aviation24 | live archive 2026-10-17 |
| `story-50868a65320a` Air Canada Expands Canada-U.S. Connectivity for Summer 2027 | airline_ir, trade, wire_headline | Air Canada News Releases, AeroTime, Yahoo Finance Aviation | live archive 2026-10-17 |
| `story-1ff366f2a122` Turkish Airlines and CFM sign MOU for more than 600 LEAP-1B engines | trade, wire_headline | AeroTime, HavaHaber, Tolga Özbek Havacılık, Yahoo Finance (THY & Pegasus) | live archive 2026-10-17 |
| `story-1c2ce9b5a516` Lufthansa selects Tokyo as first destination for Airbus A350-1000 | airline_ir, trade | Lufthansa Group Newsroom, AeroTime, AirDataNews | runner probe 2026-10-17 (7-day window) |

Düzenleyici + basın: none in the data: FAA, EASA, ANAC, AAIB and BEA items appeared in the 7-day window but no press item about the same event was published, so no regulator story merged with press.

Birleşmeyen örnekler (kural genişletilmedi):

- same order, two stories: «AeroTime: Airbus secures order for 75 A320neo family aircraft from ACG» ↔ «AirDataNews: Airbus wins order for 75 A320neo Family jets» (ortak sözcükler: a320neo, airbus, family, order)
- same roll-out, separate story: «AeroTime: Saab rolls out Sweden's first GlobalEye as NATO prepares to follow» ↔ «Aviation24 / AirDataNews: Saab unveils Sweden's first GlobalEye surveillance aircraft» (ortak sözcükler: first, globaleye, saab, sweden)
- same strike, separate story: «AeroTime: Ukraine says Neptune missile strike hit six Russian bombers» ↔ «AirDataNews: Ukraine claims six Russian Su-34 bombers damaged» (ortak sözcükler: bombers, missile, neptune, russian, strike, ukraine)

Kümeleme kuralı değişikliği: none: the clustering rules were not widened.

## Ücretli katman öncesi hukuki değerlendirme gerektiren kaynaklar

`commercial_use_risk = high` veya `medium` olan kaynaklar. Risk kaynağı pasif yapmaz, yalnızca kayda geçer. **Okundu** sütunu: şart sayfası bu çalışmada gerçekten okundu mu? Hayır ise bulgu doğrulanmamıştır (sayfa erişilemedi, arama özeti ya da bellek) ve bir insan tarafından kontrol edilmelidir.

### Yüksek risk (şartlar ticari kullanımı, yeniden dağıtımı veya otomatik erişimi kısıtlıyor) — 32 kaynak

| Kaynak | status | Okundu | Şartın kısa özeti | Bağlantı |
|---|---|---|---|---|
| Yahoo Finance (THY & Pegasus) | excluded_policy | evet | 2(e): "may not access or reuse the Services... for any commercial purpose"; 2(d)(ix) bars automated collection w/o permission; 2(o) RSS: "only permitted to display the content that is provided in the feed", credit+link. | https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html |
| Simple Flying | active | evet | Valnet terms: licence is "personal, non-commercial use only"; bans to "scrape, automatically download, data-mine, extract" content. RSS clause: use feed unmodified; Valnet may require you to stop. | https://www.valnetinc.com/en/terms-of-use |
| AeroTime | active | evet | Forbids 'use any software or other automated means to access and gather information in the Site without express written permission'; may not 'copy, reproduce, republish... distribute' content; only personal non-commercial use. | https://www.aerotime.aero/terms-of-use |
| Yahoo Finance Aviation | excluded_policy | evet | s.2(e): 'may not access or reuse the Services... for any commercial purpose'; s.2(d)(9) bans collecting data 'using any automated means'; RSS (s.2(o)): only 'display the content provided in the feed, without modification'. | https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html |
| Bloomberg Aviation | excluded_policy | evet | 'solely for your own noncommercial use'; no copying/redistribution; may not use any 'scraper,' 'robot,' 'bot,' 'spider' ... to access, acquire, copy, or monitor the Service. | https://www.bloomberg.com/notices/tos/ |
| Delta News Hub | active | evet | Delta.com terms: access only for "personal use for non-commercial purposes"; bars "crawler, indexer, robot, spider, scraper" and "reproduce, reuse, republish" w/o written permission. RSS not mentioned; news.delta.com own terms 404. | https://www.delta.com/us/en/legal/terms-of-use |
| Emirates Newsroom | active | evet | 'You agree to use the Website only for personal, noncommercial use.' RSS/reuse not addressed; only the visible part of terms was read. | https://www.emirates.com/us/english/information/terms-and-conditions/ |
| Air Canada News Releases | disabled_blocked | evet | 'Use of the Website for any other purpose, including any commercial use or purpose, is expressly prohibited.' Bans 'automated scripts, robots, crawls, screen scrapers'; no re-dissemination of content. RSS not addressed. | https://www.aircanada.com/ca/en/aco/home/legal/terms-of-use.html |
| Ryanair Newsroom | active | evet | Content may be used 'only as strictly required for permitted personal, non-commercial purposes'; 'screen scraping' via automated systems to extract data for commercial purposes 'is strictly prohibited'. | https://www.ryanair.com/gb/en/corporate/terms-of-use |
| ANA Group Press Releases | no_extractable_feed | evet | 'Downloading, printing or otherwise reproducing the ANA Website is permitted only for private use'; 'may not reproduce, alter... distribute' Content without permission; no copying/quoting on other sites. | https://www.ana.co.jp/en/jp/guide/terms/website/ |
| JetBlue Investor News | disabled_blocked | evet | Site use "only for personal, non-commercial use"; may not "republish, distribute" content; robots/spiders/page-scrapers need prior written consent (8.1.5). Digital Assets excepted. | https://ir.jetblue.com/terms-of-use/default.aspx |
| Alaska Airlines Newsroom | active | evet | Multimedia Usage Agreement (applies to media downloads): "truthful current editorial and truthful current news reporting purposes only"; commercial use not allowed. Silent on RSS; general site terms not read. | https://news.alaskaair.com/multimedia-usage-agreement/ |
| ICAO Newsroom | no_extractable_feed | evet | Materials for "personal, non-commercial use, without any right to resell or redistribute"; no derivative works. Copyright notice: no use/reproduction/transmission without written permission. Scraping not mentioned. | https://www.icao.int/terms-and-conditions |
| IATA Press Room | no_extractable_feed | evet | Content 'for your personal use only... not intended for commercial exploitation unless expressly agreed in writing'; 'wholesale reproduction... not permitted'; no use on other websites without consent. Offers RSS /api/rss/pressrelease. | https://www.iata.org/en/terms/ |
| BEA News | active | evet | Non-commercial reuse allowed with source/date; 'Les informations ne peuvent etre utilisees a des fins commerciales ou promotionnelles' without a licence; a product/service offered to third parties counts as commercial. | https://www.bea.aero/en/legal-notice/ |
| LSE RNS | excluded_policy | evet | LSEG website terms (lseg.com; londonstockexchange.com terms not located): no copying for "commercial gain"; bars "any bot, script, automation software" and bulk download; no AI tools. [Judgement: this bars automated collection of the site, so the source is excluded; the page read was lseg.com, not londonstockexchange.com.] | https://www.lseg.com/en/policies/website-disclaimer |
| HKEX News | excluded_policy | evet | Personal use only; no distributing/copying without written permission; no 'systematic retrieval to create collections, compilations, databases'; no 'programmatic, scripted or other mechanical means' access (site-wide). | https://www.hkex.com.hk/Global/Exchange/Terms-of-Use?sc_lang=en |
| The Wall Street Journal | excluded_policy | evet | 'you may not access or use the Content, including ... any Content made available through one of our RSS feeds, in any commercial product or service, without our express written consent.' Also bans scraping/AI agents. | https://www.dowjones.com/terms-of-use/ |
| Associated Press Aviation | excluded_policy | hayır | Terms page returned 403 (not read). From memory, not re-read: AP prohibits scraping and commercial reuse without licence; AP content is licensed. robots.txt blocks /*.rss and /api/v2/feed/. | — |
| Nikkei Asia | no_public_feed | evet | RSS terms: feeds 'solely for ... individuals to view headlines ... within newsreaders for their personal, noncommercial use. Republication, copying or redistribution by any means is expressly prohibited.' Main ToS returned 403. | https://info.asia.nikkei.com/rss |
| The Air Current | active | evet | Bans 'systematic or automated data collection... scraping, data mining'; no reproduce/exploit 'for a commercial purpose, including media monitoring services for redistribution'; RSS only in an RSS reader. | https://theaircurrent.com/terms-of-service/ |
| ch-aviation | no_public_feed | evet | Must not "use any part of the materials on our site for commercial purposes" without licence; no re-selling or making materials available on networks. Scraping not mentioned; footer links an RSS feed. | https://www.ch-aviation.com/terms |
| OAG Blog | no_public_feed | evet | 6.3: "personal, non-commercial use only, unless you obtain a license for commercial purposes"; 7.1 bars bots/crawlers/scrapers "without our explicit written consent"; 6.4 bans republishing; 7.2 bans genAI training. RSS not mentioned. | https://www.oag.com/terms-of-use |
| AvHerald | excluded_policy | evet | Footer: 'all rights reserved, reproduction, redistribution and AI learning/use prohibited.' No terms page found. | https://avherald.com/ |
| PROS News | no_extractable_feed | hayır | Terms of Use PDF was unreadable (compressed). robots.txt explicitly blocks feed URLs for all agents ("Disallow: */feed"); legal page refers to MSA/AUP for contractual use. | https://s28006.pcdn.co/wp-content/uploads/2020/07/Terms-of-Use.pdf |
| Amadeus Newsroom | no_extractable_feed | evet | 'You must not use the Site in any way for your own commercial gain'; license 'for your personal, non-commercial purposes and for no other purpose'; no copying beyond personal use. Page dated Oct 2018; silent on scraping. | https://amadeus.com/en/policies/terms-of-use |
| Airbus Press Releases | active | evet | Users shall not '(i) modify, reproduce, represent, adapt and/or translate all or any part of the Site and/or related content; (ii) extract all or any part of the Site and/or its content'. Other rights excluded. | https://www.airbus.com/en/terms-of-use |
| Boeing News Releases | no_extractable_feed | evet | 'limited license to make personal use only'; excludes 'any resale or commercial use'; no 'data mining, robots, or similar data gathering'; materials only for 'personal, non-commercial, and informational use'. | https://www.boeing.com/terms-of-submission-and-privacy-policy/site-terms |
| Embraer News | no_extractable_feed | evet | Sec 2: site content owned by provider; "express prohibition to copy, reproduce, download or make any other type of use thereof", "for commercial purposes or not". No mention of scraping or RSS. | https://www.embraer.com/terms-of-use/en/ |
| GE Aerospace News | active | evet | Material only for "personal and non-commercial use"; other use incl. "distribution, transmission, publication" prohibited; use for competitive purposes banned. Scraping not named. | https://www.geaerospace.com/terms |
| Bombardier News | active | evet | Site "may be used by you only for personal, non-commercial purposes"; materials may not be "redistributed, broadcast, published, copied" without prior written consent. Scraping not mentioned. | https://bombardier.com/en/terms-of-use |
| Textron Aviation Newsroom | active | evet | 'Any resale or commercial use of this Site or its contents ... any use of data mining, robots, or similar data gathering and extraction rules ... is prohibited'; redistribution for commercial purposes prohibited. | https://txtav.com/en/terms-of-use |

### Orta risk (belirsiz ya da okunamadı) — 53 kaynak

| Kaynak | status | Okundu | Şartın kısa özeti | Bağlantı |
|---|---|---|---|---|
| HavaHaber | active | evet | No terms page found; Kunye and footer carry only 'Telif Hakki 2026, Tum Haklari Saklidir' (all rights reserved). Silent on feeds/reuse. | https://havahaber.com/kunye/ |
| Tolga Özbek Havacılık | active | evet | No terms page found; footer only says 'Tüm Hakları Saklıdır' (all rights reserved). Silent on feeds/reuse. (Feed URL itself returned 406 to a plain script UA.) | https://tolgaozbek.com/ |
| FlightGlobal | disabled_blocked | evet | Footer links only ProMedia general T&Cs (no website-content, RSS or scraping clauses found). No RSS terms. robots.txt has 'Content-signal: ai-train=no'. | https://www.promedia.co.uk/general-terms-conditions/ |
| Aviation24 | active | hayır | Only a copyright/attribution page (seen via search snippet; direct fetch 403): asks to credit and link when quoting articles. No formal ToS or feed/commercial clause found. | https://www.aviation24.be/copyright-information/ |
| AirDataNews | active | hayır | No terms-of-use page found (footer has only a Privacy Policy; /terms-of-use is 404). Silent about feeds and reuse. | — |
| Flightradar24 | active | hayır | Terms not retrievable (403 on /terms-and-conditions). Search excerpt only (not read): web service limited to human browser, personal non-commercial use; API for commercial. Blog feed not addressed. | — |
| Reuters Aviation | excluded_policy | hayır | terms not retrievable (fetch tool refused reuters.com). Reuters is known to restrict reuse/scraping, but not re-read; from memory, not re-read, likely high. Needs manual check/licence. | — |
| Financial Times Aviation | disabled_blocked | hayır | Terms not retrievable (WebFetch blocked, help.ft.com terms 404 via curl). robots.txt says all use is subject to T&C and bans AI/ML use. Likely restrictive (from memory, not re-read). | — |
| Lufthansa Group Newsroom | active | hayır | Terms not retrievable (lufthansagroup.com legal notice/disclaimer returned 403). Newsroom page openly lists 'Newsroom RSS feed' and 'RSS-Feed Press releases', suggesting intended syndication, but no reuse terms were read. | — |
| Turkish Airlines Blog | disabled_blocked | hayır | Terms not retrievable (403 / timeout on legal notice). | — |
| Qatar Airways Official Tumblr | active | evet | Tumblr ToS bans scraping and access 'other than through our currently available, published interfaces' (RSS is a published interface). Content is user/brand-owned; no brand-specific terms. | https://www.tumblr.com/policy/en/terms-of-service |
| Pegasus Press Room | no_extractable_feed | evet | No terms-of-use or press-room usage terms found on the press-room page (only "© 2026, All Rights Reserved" and privacy). No RSS/syndication statement. | — |
| American Airlines Newsroom | disabled_blocked | hayır | Terms not retrievable (aa.com legal pages 403 / JS-rendered, no text readable). | — |
| United Airlines Newsroom | disabled_blocked | hayır | terms not retrievable (united.com unreachable/timeout; newsroom.united.com robots unreachable). Related United sites (search excerpt, not read) say personal/noncommercial. | — |
| Southwest Newsroom | no_extractable_feed | hayır | Terms not retrievable: swamedia.com is JS-rendered, no legal page located. Corporate press-release newsroom, no stated reuse licence read. | — |
| Air France Press Releases | active | hayır | RSS page lists press-release feed with no reuse/copyright terms in the part read (first 100k chars of 323k); legal notice URL guess returned 403. Generic copyright only. | https://corporate.airfrance.com/en/rss-subscription |
| KLM Newsroom | active | hayır | Newsroom footer has no terms/legal link; it openly promotes an RSS feed (nieuws.klm.com/rss-feed/). klm.com terms timed out. Silent on feed reuse. | — |
| easyJet Media Centre | no_extractable_feed | hayır | terms not retrievable (mediacentre.easyjet.com and robots.txt returned 403). | — |
| Qantas Newsroom | disabled_blocked | hayır | Terms not retrievable (timeouts/connection reset). | — |
| Singapore Airlines Newsroom | no_extractable_feed | hayır | terms not retrievable (guessed URLs 404; conditions-of-use page returned only scripts). Search excerpt only, not read: personal non-commercial copy only; no explicit scraping clause seen. | — |
| Japan Airlines Press Releases | disabled_blocked | hayır | terms not retrievable (press.jal.co.jp and robots.txt returned 403). | — |
| Cathay Pacific Newsroom | active | hayır | Newsroom page has no terms/copyright link or reuse wording (only privacy policy); /terms is 404. Silent about feeds. | — |
| Air India Newsroom | disabled_blocked | hayır | terms not retrievable (site unreachable/Cloudflare challenge). From search excerpt, not re-read: terms reportedly bar robot/spider/scraper access without written permission. | — |
| Etihad Airways News | disabled_blocked | hayır | Terms not retrievable (etihad.com timed out / connection reset on every fetch). | — |
| IndiGo Press Releases | disabled_blocked | hayır | terms not retrievable (goindigo.in terms and robots.txt fetches timed out). | — |
| Copa Holdings News Releases | disabled_blocked | hayır | terms not retrievable (ir.copaair.com returned 403 Access Denied, incl. robots.txt). | — |
| LATAM Investor Releases | disabled_blocked | hayır | Terms not retrievable (ir.latam.com pages returned 403 / 404 for terms and disclaimer URLs). | — |
| IAG Newsroom | disabled_blocked | hayır | No legal notice found (/en/legal-notice 404; footer links not located). Silent about feeds and reuse. | — |
| Air France-KLM Newsroom | disabled_blocked | hayır | terms not retrievable (legal-notes page 403 Cloudflare). Search excerpt, not read: all reproduction rights reserved; copying site requires prior written authorization. | — |
| Qatar Airways Press Releases | disabled_blocked | hayır | Terms not retrievable (qatarairways.com timed out on robots.txt and legal pages). | — |
| LATAM Airlines Press Room | disabled_blocked | hayır | terms not retrievable (latamairlines.com robots.txt 403; terms not fetched). | — |
| EASA News | active | hayır | terms not retrievable (guessed legal-notice URLs returned 404). EU agency; reuse policy likely permissive but from memory, not re-read, so unconfirmed. | — |
| Eurocontrol News | no_extractable_feed | evet | Disclaimers and privacy/website-terms pages read: no wording on reuse, commercial use or scraping; only "(c) EUROCONTROL". Silent about feeds. | https://www.eurocontrol.int/info/disclaimers |
| CAAC News | no_extractable_feed | hayır | No terms page found/read; /en/ redirects to /English/. No copyright statement retrieved. | — |
| ANAC Brazil | active | hayır | terms not retrievable (gov.br/anac page returned only a captcha challenge; no licence text read). Government material, likely open, but unconfirmed. | — |
| SHGM News | no_extractable_feed | hayır | No terms-of-use, copyright or content-use statement found on web.shgm.gov.tr homepage; only a privacy PDF link and an RSS link (/tr/kurumsal/4000-rss). Government site, unconfirmed. | — |
| KAP Public Disclosure | no_extractable_feed | hayır | Terms not retrievable (guessed terms URLs 404; robots.txt returned non-standard error). Public company disclosure platform; reuse terms unknown. | — |
| The New York Times | disabled_blocked | hayır | terms not retrievable (fetch tool refused nytimes.com). From memory, not re-read: NYT terms limit use to personal non-commercial and bar automated access; likely high, verify manually. | — |
| The Washington Post | disabled_blocked | hayır | Terms not retrievable (403 / Cloudflare challenge). Likely restrictive (from memory, not re-read). | — |
| CNBC Airlines | no_public_feed | hayır | terms not retrievable (cnbc.com terms and robots.txt returned 403). From memory, not re-read: NBCUniversal terms are non-commercial/no-scraping; likely high, verify. | — |
| The Economist | disabled_blocked | hayır | Terms not retrievable (WebFetch blocked, curl 403 Cloudflare). Likely restrictive (from memory, not re-read). | — |
| Aviation Week | no_public_feed | hayır | terms not retrievable (guessed Informa/AviationWeek terms URLs returned 404). Paywalled Informa publication; likely restrictive but unread. | — |
| CAPA Centre for Aviation | no_public_feed | evet | Page read is the paid-customer licence contract (no copying/reselling Licensed Products; no AI use). Public-site terms (Informa) not read. RSS offered at rss.centreforaviation.com. | https://centreforaviation.com/about/terms-and-conditions |
| Cirium Thought Cloud | no_public_feed | hayır | Terms not retrievable: site returns a bot-protection (Incapsula) challenge page; terms URL guesses empty/404. | — |
| Routes Online News | disabled_blocked | hayır | Terms not retrievable (403 on terms pages and homepage). | — |
| PhocusWire | disabled_blocked | hayır | Terms not retrievable (403 on site and terms URLs). | — |
| China Travel News | disabled_blocked | hayır | terms not retrievable (site TLS certificate expired; robots and homepage failed). | — |
| Sabre Insights | no_extractable_feed | hayır | Terms not retrievable: site served a bot-challenge stub page; terms URLs returned empty/404. | — |
| Accelya News | active | hayır | terms not retrievable (terms-of-use redirected to w3.accelya.com which returned 404; robots redirected, not read). | — |
| T2RL News | no_extractable_feed | evet | Terms read: only informational-use/liability wording ("for informational purposes only"); no wording on reuse, commercial use or scraping. | https://www.t2rl.com/terms-conditions/ |
| RTX News | disabled_blocked | evet | May not 'reproduce or publicly display, perform or distribute or otherwise use the site and its contents for any public or commercial purpose', but RSS offered openly (/rss-feeds/news); conflict unresolved. | https://www.rtx.com/terms-of-use |
| Rolls-Royce Press Releases | active | evet | Only generic copyright: pages 'may not be reproduced in whole or part without the prior written authorisation'. No explicit commercial-use or automated-access clause, none about feeds. | https://www.rolls-royce.com/site-services/legal-information.aspx |
| Safran News | disabled_blocked | hayır | terms not retrievable (legal-notice URLs returned 403). | — |

