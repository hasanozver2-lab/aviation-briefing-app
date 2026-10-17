# Dağıtım servisi beslemeleri (feature/wire-feeds)

Ölçüm: 2026-10-17, GitHub çalıştırıcısı (run 39020170313, temsilci `Mozilla/5.0 (compatible; aviation-briefing-app/1.0; …)`), bu bilgisayardan ikinci ölçümle karşılaştırıldı. Ağırlık ve eşik değiştirilmedi; SEC EDGAR'a dokunulmadı.

## 1. Keşif
Adresler elle yazılmadı. PR Newswire'ın kendi RSS sayfasından (`/rss/`) okundu: sayfa 14 sektör beslemesini listeliyor. Hepsi geçerli XML, her öğede başlık+bağlantı+tarih, 20 öğe. Şirket bazlı besleme belgelenmiş bir yolla bulunamadı (şirket haber odası sayfalarında besleme bağlantısı yok; GlobeNewswire ve Business Wire'ın şirket beslemeleri hesapla üretilen opak adresler). Bu yüzden kapsam şirketleri tek tek değil, ilgili sektör beslemesi + havacılık süzgeci ile yakalanıyor.

| Kaynak | Çalıştırıcıdan | Bu bilgisayardan | Öğe (7 gün) | Süzgeçten geçen | Listeye giren | Durum |
|---|---|---|--:|--:|--:|---|
| PR Newswire Travel Sector | zaman aşımı (30 sn, 11 istek) | 200, rss | 20 (çalıştırıcı: 0) | 0 | 0 | disabled_blocked (haftalık yeniden deneme) |
| PR Newswire Heavy Industry Sector | 200, rss | 200, rss | 20 | 0 | 0 | active |
| GlobeNewswire Transportation Feed | 403 (robots.txt dahil) | 403 | 0 | 0 | 0 | disabled_blocked |
| Business Wire Feeds | zaman aşımı / bağlantı sıfırlama | zaman aşımı | 0 | 0 | 0 | disabled_blocked |
| KAP THYAO / PGSUS | — (istek atılmadı) | — | 0 | 0 | 0 | no_public_feed |

Besleme penceresi kısa: Travel 15 saat, Heavy Industry 9,7 saat (son 20 öğe). Şirket adı eşleşmesi (AA, UAL, DAL, LUV, JetBlue, Alaska, Air Canada, LATAM, Copa, Boeing, Airbus, GE Aerospace, RTX, Embraer, Spirit Aero) ve havacılık anahtar kelimesi bu 14 beslemenin hiçbirinde çıkmadı. Bu yüzden **kümelemeye giren yeni kaynak öğesi örneği gösterilemiyor** (0 öğe süzgeçten geçti); uydurma örnek eklenmedi. Beslemeler yalnızca bir kuruluş duyuru yaptığı saatlerde değer üretir; asıl kazanç, büyük bir havayolu/OEM duyurusu geldiği anda.

## 2. KAP
Belgelenmiş açık RSS/API ve okunabilir şartlar sayfası bulunamadı; liste betikle üretiliyor, robots.txt hata veriyor. Şartlar yasakladığı için değil, açık bir besleme olmadığı için `no_public_feed` (language=tr, istek atılmadı, `no_retry`). Genel `KAP Public Disclosure` satırı önceden vardı (kendi `no_extractable_feed` durumu değişmedi).

## 3. Şartlar
PR Newswire: yalnızca kişisel ticari olmayan kullanım, kazıma/yeniden yayın/robot yasağı → `commercial_use_risk=high`; kaynak kapatılmadı. Yalnızca kurumun kendi herkese açık RSS kanalları okunuyor, mod `feed_only`: başlık, bağlantı, zaman, ≤300 karakter özet; metin yeniden yayınlanmıyor. GlobeNewswire ve Business Wire şartları 403 verdiği için okunamadı (`read:false`, risk `high` varsayıldı). Hiçbir engel aşılmadı.

## 4. Yatırımcı duyuruları ve taksonomi
Mevcut türler: bilanço/beklenti/temettü → `airline_financials` (0,85); geri alım → `capital_markets` (0,45); sipariş/teslimat → `fleet_orders` (0,7). **Tür bulamayan:** borç ihracı/tahvil (ör. «prices $500 million senior notes») → tür yok.
**Öneri (eklenmedi):** `investor_disclosure` türü, yalnızca borç/finansman ve diğer yatırımcı bildirimleri için; önerilen ağırlık 0,45 (`capital_markets` ile aynı, çünkü ikisi de bilanço dışı sermaye işlemi). Onaylanana kadar tür atanmıyor (şu anki yakın tür `capital_markets` ağırlığı kullanılabilir). `config/event_taxonomy.json` değişmedi.

## 5. Eklenenler
`config/source_expansion.json` grup G (6 satır, `catalog_key` ile aynı alan adında ayrı satırlar), `config/source_terms_review.json`, `config/source_status_overrides.json` (KAP), `api/source_catalog.py` (`catalog_key`), `tests/test_wire_feeds.py`. Süzgeç: `aviation_filter=true`.
