# Tip atanmamış haberler (event_type = None)

Veri: iki gerçek makale anlık görüntüsü (birleşik, tekilleştirilmiş) — 117 makale → 103 hikâye. Mevcut taksonomi (`config/event_taxonomy.json`) ile yeniden sınıflandırıldı. Örneklem tohumu: 20261016 (aynı veri → aynı 40 haber).

## Sayılar

| Kapsam | Hikâye | Tipsiz | Oran |
|---|---:|---:|---:|
| Tüm hikâyeler | 103 | 80 | 77.7% |
| Arşive girenler (skor ≥ 35) | 27 | 8 | 29.6% |
| Ana listede (skor ≥ 40) | 20 | 2 | 10.0% |

Makale düzeyinde: 86 / 117 makale tipsiz (73.5%).

Tip dağılımı (hikâye): tipsiz: 80, route_network_change: 5, geopolitics_airspace: 4, operations_disruption: 4, fleet_orders: 3, safety_incident: 3, airline_financials: 2, community_csr: 1, capital_markets: 1.

Not: tipsiz bir hikâye otomatik olarak düşük skorlu değildir — tip ağırlığı yoksa varsayılan `event_type_default` kullanılır; kaynak güvenilirliği ve varlık önemi yine skoru taşır.

## Rastgele 40 tipsiz hikâye (skora göre sıralı)

| # | Skor | Kaynak | Başlık |
|--:|--:|---|---|
| 1 | 43.5 | Emirates Newsroom | Emirates brings global travel rehearsal programme to Colombia |
| 2 | 36.5 | FlightGlobal | How ‘generational’ move for TAP brings something different to Lufthansa |
| 3 | 36.5 | Flightradar24 | The Airbus A350 joins the KLM fleet |
| 4 | 36.5 | FlightGlobal | Condor chief outlines ‘bleisure’ transformation and blasts European airline regulations |
| 5 | 30.5 | HavaHaber | Qatar Airways, 3 Boeing 787-9 için ilk kez JOLCO finansman modelini kullandı |
| 6 | 30.5 | FlightGlobal | Abra targets Rio growth as consolidated network takes shape |
| 7 | 30.5 | Simple Flying | Simple Flying Podcast Episode 307: Southwest Airlines' New Loyalty Program, Lufthansa Adds Extra Fuel On Frank |
| 8 | 30.5 | FlightGlobal | SAS targets ‘spread and depth’ through long-haul expansion |
| 9 | 30.5 | AeroTime | Lufthansa tells jets to carry extra fuel as Frankfurt, Zurich face supply crunch |
| 10 | 30.5 | Tolga Özbek Havacılık | İstanbul Havalimanı, 41. haftada Avrupa’da liderliğini sürdürüyor |
| 11 | 30.5 | Tolga Özbek Havacılık | Koli bandı ile paketlenen yolcuya 20 yıl hapis istemi |
| 12 | 30.5 | AirDataNews | Lufthansa could transfer eight Airbus A350 jets to TAP after 2030 |
| 13 | 30.5 | HavaHaber | Delta Air Lines uçağında türbülans paniği: İki kabin memuru yaralandı |
| 14 | 30.5 | Flightradar24 | AvTalk Episode 391: A critical path faces its greatest challenge yet |
| 15 | 24.5 | HavaHaber | Sabiha Gökçen Havalimanı 9 ayda 38 milyon yolcuya yaklaştı |
| 16 | 23.5 | Air Canada News Releases | Aeroplan Members Get Rewarded for Coveted Dining Reservations and Experiences via Expanded DINR Partnership |
| 17 | 18.5 | Aviation24 | LOT parent plans dedicated cargo airline under new growth strategy |
| 18 | 18.5 | Aviation24 | airBaltic aircraft lands safely at Brussels Airport following technical emergency |
| 19 | 18.5 | HavaHaber | Polonya havacılığında dijital dönüşüm: PGL, yer hizmetlerini yeniden yapılandırıyor |
| 20 | 16.5 | FlightGlobal | ReFuelEU sustainable aviation fuel mandate here to stay: European Commission |
| 21 | 16.5 | FlightGlobal | Airbus Helicopters details test plan to prove Racer is more than just a sprinter |
| 22 | 16.5 | FlightGlobal | Bombardier deepens US presence with new training centre amid Trump threats |
| 23 | 16.5 | Flightradar24 | The intricate sky art of Benjamin McDaniel and N1810R |
| 24 | 15.0 | Yahoo Finance Aviation | GA Telesis Strengthens Next Generation Aircraft Aftermarket Dominance with First Boeing 737 MAX 8 Disassembly  |
| 25 | 10.5 | AirDataNews | Airbus moves closer to decisions on larger A350 and A220 jets |
| 26 | 10.5 | Aviation24 | EUROCONTROL’s Maastricht centre more than halves summer air traffic delays |
| 27 | 10.5 | Simple Flying | How Do The Thunderbirds Fly So Close Together Without Colliding? |
| 28 | 10.5 | AeroTime | Boeing CEO among industry bosses to convene for certification reform talks |
| 29 | 10.5 | AirDataNews | Airbus links German and Swedish air defense systems during NATO live-fire exercise |
| 30 | 10.5 | AeroTime | Ukrainian drone attacks cause chaos at multiple Russian airports overnight |
| 31 | 10.5 | AirDataNews | Boeing prepares to close F/A-18 Super Hornet production after four decades |
| 32 | 10.5 | AirDataNews | Boeing 737 MAX 8 faces early teardown despite record demand for new aircraft |
| 33 | 10.5 | AeroTime | Saab rolls out Sweden’s first GlobalEye as NATO prepares to follow |
| 34 | 10.5 | AirDataNews | ATR delivers new ATR 72-600 to Cape Verde’s CVsky |
| 35 | 10.5 | Aviation24 | Snowbirds bid farewell to CT-114 Tutor with final Moose Jaw performance |
| 36 | 10.5 | AeroTime | France tests how Rafale fighters can keep flying from civilian airports |
| 37 | 10.5 | AirDataNews | COMAC C919 reaches 8.4 million passengers but deliveries remain slow in 2026 |
| 38 | 10.5 | HavaHaber | Türkiye, Avrupa’nın en yoğun 6. hava sahası oldu: Günlük 3 bin 837 uçuş |
| 39 | 10.5 | AirDataNews | Israel signs deal for 12 Boeing AH-64E Apache attack helicopters |
| 40 | 4.5 | Yahoo Finance Aviation | Boeing Price Target Slashed To $235 By RBC – Firm Says Lingering Defense Budget Uncertainty Will Remain A Head |

## Yeni tip önerileri (EKLENMEDİ — karar sizin)

Her öneri için kanıt: tipsiz hikâyelerin kaç tanesi (başlık + açıklama) ilgili anahtar sözcüklerden birini içeriyor. Sözcük listeleri kaba bir ölçüdür; örtüşme olur (bir haber birden çok öneriye girebilir), gerçek kural yazılırsa başlık-isabeti/≥2 açıklama-isabeti kuralı ve gürültü testi gerekir.

| Öneri | Tipsiz hikâye | Oran | Skor ≥ 35 | Örnek başlıklar |
|---|--:|--:|--:|---|
| workforce_hr (pilot/crew hiring, strikes, training, labour deals) | 13 | 16.2% | 2 | Condor chief outlines ‘bleisure’ transformation and blasts E; Emirates turns to Manila for first pilot recruitment drive i |
| product_service (cabin, lounge, wifi, loyalty, menu, seat, upgrade) | 6 | 7.5% | 1 | SpaceX Expands Footprint With United Airlines Days After AAL; Simple Flying Podcast Episode 307: Southwest Airlines' New L |
| fleet_delivery_retirement (delivery, retire, lease, return, conversion) | 14 | 17.5% | 4 | US Navy receives first C-130J for conversion into E-130J nuc; Volga-Dnepr carrier Atran restores operations with 737 freig |
| partnership_mna (codeshare, alliance, stake, acquisition, MoU, JV) | 8 | 10.0% | 2 | Embraer signs E-Jet support agreement with TAP regional oper; Aeroplan Members Get Rewarded for Coveted Dining Reservation |
| airport_infrastructure (terminal, runway, expansion, slots, capacity) | 10 | 12.5% | 0 | SAS targets ‘spread and depth’ through long-haul expansion; TSA Suddenly Halts Major Airport Access Expansion Across The |
| sustainability_tech (SAF, hydrogen, eVTOL, emissions, electric) | 1 | 1.2% | 0 | ReFuelEU sustainable aviation fuel mandate here to stay: Eur |
| regulation_policy (tax, rules, passenger rights, EASA/FAA, certification) | 10 | 12.5% | 2 | Condor chief outlines ‘bleisure’ transformation and blasts E; EU plans to fast-track antitrust approval of SpaceX rival |
| accessibility_csr (autism, wheelchair, charity, community) | 1 | 1.2% | 1 |  |

Başlığında en az bir öneri sözcüğü geçen tipsiz hikâye: 26 / 80 (32.5%). Kalanlar genel haber/piyasa/ürün tanıtımı gibi tek bir tipe oturmayanlar.

## Öneri notları

- **product_service** ve **partnership_mna** en geniş kapsayanlar; ikisi de yüksek gürültü riski taşıyor ('app', 'partner', 'agreement' gibi sözcükler tek başına yetmez — başlıkta isabet veya ≥2 açıklama isabeti gerekir).
- **workforce_hr**: pilot alımı, grev, atama haberleri; örnek: Emirates pilot alımı. Skor için ayrı bir `event_weight` istenir.
- **fleet_delivery_retirement**, mevcut `fleet_orders` ile örtüşür; ya onu genişletmek ya ayrı tip yapmak karar konusu.
- **accessibility_csr**, mevcut `community_csr` tipine (Delta topluluk haberi) eklenebilir — yeni tip gerekmeyebilir (Emirates otizm prova programı bu tipe girmiyor çünkü anahtar sözcükler eksik).
- **sustainability_tech** ve **regulation_policy** bu örneklemde küçük; veri çoğalınca yeniden bakılmalı.
