# Taksonomi v2 — önce/sonra

Veri: aynı 117 makale, 103 hikâye (`reports/unclassified_sample.md` ile aynı set). Önce = main (`2708eb9`), sonra = bu dal, partnership bağlamı ve savunma listesi sıkılaştırılmış hâli. Ağırlıklar ve terimler geçici; onayınız bekleniyor.

## Tipsiz oranı

| | Önce | Sonra |
|---|--:|--:|
| Makale | 86 / 117 (73.5%) | 78 / 117 (66.7%) |
| Hikâye (hepsi) | 80 / 103 (77.7%) | 72 / 103 (69.9%) |
| Hikâye (skor ≥ 35, arşive girer) | 8 / 27 (29.6%) | 6 / 31 (19.4%) |
| Hikâye (skor ≥ 40, listede) | 2 / 20 (10.0%) | 1 / 21 (4.8%) |

## Tür dağılımı (hikâye)

| Tür | Önce | Sonra |
|---|--:|--:|
| tipsiz | 80 | 72 |
| route_network_change | 5 | 5 |
| fleet_orders | 3 | 5 |
| operations_disruption | 4 | 4 |
| geopolitics_airspace | 4 | 4 |
| safety_incident | 3 | 3 |
| regulation_policy | 0 | 3 |
| community_csr | 1 | 2 |
| airline_financials | 2 | 2 |
| capital_markets | 1 | 1 |
| workforce_hr | 0 | 1 |
| sustainability_saf | 0 | 1 |

## Skor histogramı (hikâye sayısı)

| Aralık | Önce | Sonra |
|---|--:|--:|
| 0–25 | 58 | 53 |
| 25–35 | 18 | 19 |
| 35–40 | 7 | 10 |
| 40–45 | 4 | 4 |
| 45–60 | 11 | 12 |
| 60–+ | 5 | 5 |

## Kademe sayıları

| Kademe | Önce | Sonra |
|---|--:|--:|
| critical | 5 | 5 |
| important | 11 | 12 |
| watch | 4 | 4 |
| low | 7 | 10 |
| below | 76 | 72 |

## Tür veya kademesi değişen hikâyeler (8)

`↑` kademe yükseldi, `↓` düştü, `=` aynı. Gürültü sütunu elle değerlendirme için boş bırakılmadı: aşağıdaki işaretler benim okumam.

| Başlık | Tür önce → sonra | Skor | Kademe |
|---|---|--:|---|
| Condor chief outlines ‘bleisure’ transformation and blasts European airline regu | - → regulation_policy | 36.5 → 59.0 | low → important ↑ |
| Emirates brings global travel rehearsal programme to Colombia | - → community_csr | 43.5 → 41.2 | watch → watch = |
| Emirates turns to Manila for first pilot recruitment drive in the Philippines | - → workforce_hr | 30.5 → 39.5 | below → low ↑ |
| ATR delivers new ATR 72-600 to Cape Verde’s CVsky | - → fleet_orders | 10.5 → 37.5 | below → low ↑ |
| EU plans to fast-track antitrust approval of SpaceX rival | - → regulation_policy | 15.0 → 37.5 | below → low ↑ |
| COMAC C919 reaches 8.4 million passengers but deliveries remain slow in 2026 | - → fleet_orders | 10.5 → 37.5 | below → low ↑ |
| Boeing CEO among industry bosses to convene for certification reform talks | - → regulation_policy | 10.5 → 33.0 | below → below = |
| ReFuelEU sustainable aviation fuel mandate here to stay: European Commission | - → sustainability_saf | 16.5 → 32.2 | below → below = |

Kademe yükselen: 5, düşen: 0, kademesi aynı kalıp yalnız türü değişen: 3.

## Gürültü değerlendirmesi (düzeltme sonrası)

Önceki sürümde 10 hikâyenin türü/kademesi değişmişti, 2'si açık gürültüydü. Düzeltmeler:
- `partnerships_mna` artık başlıkta/açıklamada bir havacılık sözcüğü ister (`aviation_context_terms`: airline, carrier, aircraft, airport, flight, fleet, havayolu…). Aeroplan–DINR sadakat haberi (açıklaması boş, başlığında havacılık sözcüğü yok) artık tür almıyor ve Önemli'ye çıkmıyor.
- Savunma dışlama listesine eklendi: zırhlı*, armored/armoured (vehicle*), attack helicopter*, Apache, AH-64*, howitzer*, artillery, personnel carrier*, personel taşıyıcı*, battle tank*, frigate*, warship*, submarine*, SİHA*, kamikaze drone*. MKE zırhlı araç teslimatı artık tür almıyor. ("tank*" bilerek eklenmedi: yakıt tankı.)

Sonuç: değişen hikâye 10 → 8, kademe yükselen 7 → 5. Kalan 8'in hepsi gerçek haber (Condor/regülasyon, Emirates, ATR, COMAC, Boeing sertifikasyon, ReFuelEU) ya da sınırda tek vaka (AB/SpaceX rakibi antitröst, arşiv bandında).
Dikkat: bu örneklemde `partnerships_mna` artık hiç hikâye yakalamıyor; doğru pozitiflerini görmek için daha fazla veri gerekiyor.
Tipsiz oran (hikâye): 77,7% → 69,9%.
