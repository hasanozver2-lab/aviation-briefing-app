# Taksonomi v2 — önce/sonra

Veri: aynı 117 makale, 103 hikâye (`reports/unclassified_sample.md` ile aynı set). Önce = main (`2708eb9`), sonra = bu dal. Ağırlıklar ve terimler geçici; onayınız bekleniyor.

## Tipsiz oranı

| | Önce | Sonra |
|---|--:|--:|
| Makale | 86 / 117 (73.5%) | 76 / 117 (65.0%) |
| Hikâye (hepsi) | 80 / 103 (77.7%) | 70 / 103 (68.0%) |
| Hikâye (skor ≥ 35, arşive girer) | 8 / 27 (29.6%) | 6 / 33 (18.2%) |
| Hikâye (skor ≥ 40, listede) | 2 / 20 (10.0%) | 1 / 22 (4.5%) |

## Tür dağılımı (hikâye)

| Tür | Önce | Sonra |
|---|--:|--:|
| tipsiz | 80 | 70 |
| fleet_orders | 3 | 6 |
| route_network_change | 5 | 5 |
| operations_disruption | 4 | 4 |
| geopolitics_airspace | 4 | 4 |
| safety_incident | 3 | 3 |
| regulation_policy | 0 | 3 |
| community_csr | 1 | 2 |
| airline_financials | 2 | 2 |
| partnerships_mna | 0 | 1 |
| workforce_hr | 0 | 1 |
| sustainability_saf | 0 | 1 |
| capital_markets | 1 | 1 |

## Skor histogramı (hikâye sayısı)

| Aralık | Önce | Sonra |
|---|--:|--:|
| 0–25 | 58 | 51 |
| 25–35 | 18 | 19 |
| 35–40 | 7 | 11 |
| 40–45 | 4 | 4 |
| 45–60 | 11 | 13 |
| 60–+ | 5 | 5 |

## Kademe sayıları

| Kademe | Önce | Sonra |
|---|--:|--:|
| critical | 5 | 5 |
| important | 11 | 13 |
| watch | 4 | 4 |
| low | 7 | 11 |
| below | 76 | 70 |

## Tür veya kademesi değişen hikâyeler (10)

`↑` kademe yükseldi, `↓` düştü, `=` aynı. Gürültü sütunu elle değerlendirme için boş bırakılmadı: aşağıdaki işaretler benim okumam.

| Başlık | Tür önce → sonra | Skor | Kademe |
|---|---|--:|---|
| Condor chief outlines ‘bleisure’ transformation and blasts European airline regu | - → regulation_policy | 36.5 → 59.0 | low → important ↑ |
| Aeroplan Members Get Rewarded for Coveted Dining Reservations and Experiences vi | - → partnerships_mna | 23.5 → 48.2 | below → important ↑ |
| Emirates brings global travel rehearsal programme to Colombia | - → community_csr | 43.5 → 41.2 | watch → watch = |
| Emirates turns to Manila for first pilot recruitment drive in the Philippines | - → workforce_hr | 30.5 → 39.5 | below → low ↑ |
| ATR delivers new ATR 72-600 to Cape Verde’s CVsky | - → fleet_orders | 10.5 → 37.5 | below → low ↑ |
| MKE’den 3 adet daha elektrikli zırhlı personel taşıyıcı teslimatı | - → fleet_orders | 10.5 → 37.5 | below → low ↑ |
| EU plans to fast-track antitrust approval of SpaceX rival | - → regulation_policy | 15.0 → 37.5 | below → low ↑ |
| COMAC C919 reaches 8.4 million passengers but deliveries remain slow in 2026 | - → fleet_orders | 10.5 → 37.5 | below → low ↑ |
| Boeing CEO among industry bosses to convene for certification reform talks | - → regulation_policy | 10.5 → 33.0 | below → below = |
| ReFuelEU sustainable aviation fuel mandate here to stay: European Commission | - → sustainability_saf | 16.5 → 32.2 | below → below = |

Kademe yükselen: 7, düşen: 0, kademesi aynı kalıp yalnız türü değişen: 3.

## Yeni gürültü girdi mi? (elle okuma, 10 değişimin hepsi)

| Hikâye | Değerlendirme |
|---|---|
| Condor/regülasyon (36.5 → 59.0) | Gerçek: havayolu CEO'su AB düzenlemesini eleştiriyor. Ama sıçrama büyük (düşük → Önemli); `regulation_policy` 0,6 ağırlığının etkisi. |
| Aeroplan yemek rezervasyonu (23.5 → 48.2) | **Gürültü.** Sadakat programı pazarlaması "partnership" kelimesiyle `partnerships_mna` oldu ve Önemli'ye çıktı. |
| MKE zırhlı personel taşıyıcı teslimatı (10.5 → 37.5) | **Gürültü.** Savunma haberi `fleet_orders` ("teslimat"). Savunma dışlama listesi Türkçe "zırhlı" içermediği için yakalanmadı. |
| EU/SpaceX rakibi antitröst (15.0 → 37.5) | Sınırda: havacılık değil uydu. `regulation_policy` "antitrust" ile aldı; arşiv bandında kaldı. |
| ATR 72-600 teslimatı, COMAC C919 (10.5 → 37.5) | Gerçek: filo teslimatı. Arşiv bandında, listeye çıkmıyor. |
| Emirates pilot alımı (30.5 → 39.5) | Gerçek. Eşiğin 0,5 puan altında, arşiv bandı. |
| Emirates provası (43.5 → 41.2) | Tür doğru (erişilebilirlik) ama `community_csr` ağırlığı (0,05) varsayılandan (0,1) düşük olduğu için skor düştü; İzle'de kaldı. Mevcut tasarımın yan etkisi. |
| Boeing CEO sertifikasyon, ReFuelEU SAF | Gerçek, ama skor hâlâ eşiğin altında (33.0 / 32.2). |

Sonuç: 10 değişimin 2'si açık gürültü (Aeroplan, MKE), 1'i sınırda; ikisi de listeye değil Önemli/arşiv bandına etki ediyor — Aeroplan Önemli'ye çıkıyor, bu ciddi. Düzeltme önerileri (UYGULANMADI, karar sizin): `partnerships_mna` için "partnership" tek başına yetmesin, "airline|carrier" bağlamı iste (`aviation_context_terms` mekanizması hazır); savunma dışlama listesine "zırhlı", "armored", "attack helicopter", "Apache" ekle.
Tipsiz oran 77,7% → 68,0% (listede 10,0% → 4,5%). Tipsizlerin kalanı ağırlıkla savunma, hisse ve genel haber; yeni terim eklemek bunları yakalamak için değil gürültü riskini artırır.
