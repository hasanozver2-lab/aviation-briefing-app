# AeroBrief — HANDOFF

Son güncelleme: 2026-10-16 (Adım 1: kalıcı kimlikli varlık katmanı + seed)

## Doğruluk kaynakları (git'te metin dosyaları)
| Dosya | İçerik | SQLite'a nasıl girer |
| --- | --- | --- |
| `config/sources.csv` | 39 kaynak (36 aktif, 3 ücretli pasif) | `source_registry.sync_sources_from_csv()` → `data/source_registry.sqlite3` |
| `config/entities/groups.csv` | gruplar (Lufthansa Group, IAG, Air France-KLM ...) | `entities.sync_entities()` → `data/pipeline.sqlite3` |
| `config/entities/carriers.csv` | taşıyıcı markalar (`parent_entity_id` → grup) | aynı |
| `config/entities/airports.csv` | havalimanları | aynı |
| `config/entities/aircraft_types.csv` | uçak tipleri (aile + varyant) | aynı |
| `config/entities/entity_history.csv` | eski/geçici kod ve isimler (valid_from/valid_to) | aynı; isimler eşlemeye de katılır |
| `config/entities/match_exclusions.json` | alias'ın sayılmaması gereken ifadeler (United Arab Emirates, Pegasus spyware) | okunur |
| `config/entity_tiers.json` | filo ağırlıkları, tier eşikleri | okunur |
| `config/sections.json` | bölüm kuralları, ülke→bölge | okunur |
| `config/event_taxonomy.json` | event_type terimleri | okunur |
| `config/pipeline.json` | `llm_description_max_chars` (800) | okunur |

`data/*.sqlite3` ve `briefing_cache*.json` git'te takipli değil; pipeline her çalışmada SQLite'ı CSV'den yeniden kurar (`_engine.run_pipeline`).
Ücretli bir kaynak CSV'de `active=1` olamaz (yükleme hata verir).

## Kalıcı kimlik kuralları (değiştirilemez)
- Her varlığın ilk CSV sütunu `entity_id` (`carrier:000123`, `group:`, `airport:`, `aircraft:`); ikinci sütun kalıcı `slug`. Anlamsızdır; IATA/ICAO kodları ve isimler öznitelik, birincil anahtar değil.
- Bir kimlik atandıktan sonra asla yeniden numaralandırılmaz, silinmez, başka varlığa verilmez. `tests/test_entity_seed.py::test_entity_ids_are_never_renumbered_or_removed` bunu HEAD'deki CSV ile karşılaştırır (ilk commit'ten itibaren etkin).
- Kod/isim değişimi `entity_history.csv`'ye yazılır (ör. IST kodu 2019-04-06'da Atatürk'ten yeni havalimanına geçti); varlık satırı güncel değeri taşır. `parent_entity_id` yalnızca güncel ana grubu gösterir (Hawaiian → Alaska Air Group 2024, Asiana → Korean Air Group 2024 gibi geçmiş bağlar tutulmuyor).
- Tier türetilir (`config/entity_tiers.json`): taşıyıcı = ağırlıklı filo (geniş gövde ×2, dar gövde ×1, bölgesel jet/turboprop ×0,5; eşikler 200/100/50), marka bazında. Grup = **yolcu/mixed** markalarının toplamı, eşikler iki kat (≥400 / 200–399 / 100–199 / <100). `capacity_purchase=1` (SkyWest, Republic, Envoy, PSA, Endeavor, Horizon, Jazz) olan sözleşmeli bölgeselin tier'ı en fazla 2 olabilir (daha düşük tier'ı yükseltmez). `operator_type=cargo` satırları yolcu tier'ından çıkar: `tier` boş, `cargo_tier` aynı formülle hesaplanır, bölgesel besleme ×0,25; kargo markaları grup toplamına girmez. Havalimanı = yıllık yolcu (50/25/10 M). CSV'deki `metric_approx`, `tier`, `cargo_tier` yüklemede doğrulanır; ham rakam değişince `python -m scripts.recompute_entity_tiers` çalıştırılır.
- `tier_override` + `override_reason`: elle düzeltme. Neden boşken override girilirse yükleme hata verir; override etkin tier'ı belirler (kargo satırında `cargo_tier`'ı). `is_hub`: tier 1–2 bir yolcu taşıyıcısının birincil merkezi VEYA tier 1–2 havalimanı; tier 1–2 havalimanı `is_hub=1` olmak zorunda (yükleme doğrular, recompute düzeltir).
- `needs_verification=1`: rakamdan emin değilim ya da ±%15 (havalimanı ±%10) hata tier'ı değiştirir. Tüm rakamlar yaklaşıktır. 2026-10-16'da, ağırlıklı değeri bir tier eşiğine ±%15 yakın olan 45 taşıyıcıdan 41'i kamuya açık kaynakla doğrulandı (`verification_source`, `verified_at`; çoğunlukla Wikipedia filo tabloları, havayolunun kendi sayfası yalnızca Alaska için ve Republic'in sonuç duyurusu); 4'ü (Eurowings, AJet, Wizz Air, Sun Country) kaynaklar çeliştiği için doğrulanamadı ve işaretli kaldı. Diğer işaretli satırlara dokunulmadı. Tam liste: `reports/entity_seed_review.md`.
- `operator_type` (passenger|cargo|mixed) şimdilik yalnızca saklanır; skorlamada kullanımı sonraki adımda karara bağlanacak.

## Eşleme kuralları (api/text_match.py, api/entities.py)
- Tam kelime eşleşmesi; `'`/`’` sonrası ek (THY'nin, Delta's) tolere edilir. Kesme işaretsiz Türkçe ek (Lufthansanın) eşleşmez.
- Türkçe büyük/küçük harf: İ→i, I→ı; eşleme için ı→i ve aksan sökümü (`fold`), böylece HAVALİMANI/HAVALIMANI/havalimanı aynıdır.
- Taxonomy ve alias terimlerinde sonda `*` = kelime-öneki (Türkçe ekler için). Büyük harfli ≤4 harfli terimler (SAF, ASK, SAS, ANA) büyük/küçük harfe duyarlıdır; config'deki harf büyüklüğü bu yüzden anlamlıdır.
- Kısa kodlar: 2 harfli IATA taşıyıcı kodları yalnızca `BA117`, `BA flights`, `BA's` kalıplarında; havalimanı kodları yalnızca `(IST)`, `IST-AMS`, `IST airport`, `IST 1.530` kalıplarında. Parantez içi taşıyıcı kodu bilinçli olarak YOK (`(BA)` Boeing hisse kodu).
- Daha uzun bir alias, içindeki kısa alias'ı gölgeler ("Air France-KLM" içindeki "Air France"/"KLM", "Lufthansa Cargo" içindeki "Lufthansa"); grup adı markalarını da gölgeler. Baştaki `=` alias'ı büyük/küçük harfe duyarlı yapar (`=SWISS`).
- Bölüm: `config/sections.json → rule_order` sırasıyla (event_type → düzenleyici → taşıyıcı/grup bölgesi → havalimanı bölgesi → üretici/tedarik) tetiklenen her kural bölüm üretir; ilki `region_section` (tek birincil), kalanlar `secondary_tags`. Hiçbiri tutmazsa `Other`. Türkiye = Europe, Mısır = Africa, İsrail/Ürdün = Middle East & Gulf.
- Çıktı JSON'da yeni alanlar: `event_type`, `entities` (groups/carriers/airports/aircraft, her biri `entity_id` ile), `region_section`, `secondary_tags`. Eski `section` (4 bölüm) arayüz için aynen duruyor; arayüz henüz yeni alanları kullanmıyor.

## Bilinen teknik borç (onaylı, şimdi yapılmayacak)
1. **Üç kopya `index.html`.** Kök ve `public/` aynı, `static/index.html` eski (1654 satır). Vercel `public/` servis ediyor. Tek kopyaya indirilecek.
2. **`AGENTS.md` güncel değil.** THY merceği, THY kırmızısı ve `THY Impact Assessment` anlatıyor; kapsam kararı (küresel, THY'ye özel mercek yok) yansıtılmamış.
3. **Tarih ayrıştırma yıl sorunu.** `_engine.parse_published_datetime` yılsız biçimlerde ("%d %B", "%d %b") yılı şimdiki yıl alır; yıl dönümünde geçmiş haber ileri tarihli olabilir.

4. **Geçmiş grup bağları yok.** `parent_entity_id` yalnızca güncel ana grubu gösterir. Hawaiian → Alaska Air Group (2024) ve Asiana → Korean Air Group (2024) gibi tarihli üyelik değişiklikleri tutulmuyor; gerekirse `entity_history`'ye `parent` türünde kayıt veya ayrı üyelik tablosu eklenecek.

## Gözlemler (onay bekliyor, kendiliğinden yapılmadı)
- **Actions'ta SQLite geçicidir.** `source_stats` ve `events` runner'da kaybolur; etiketleme/değerlendirme yerelde yapılacağı için kalıcı depolama kararı gerekecek.
- **"share" terimi `capital_markets`'a "market share"i de çeker.** Skor katmanında ele alınmalı.
- **"gelir" terimi** (Türkçe: gelir=revenue) fiil olarak da geçer ("uçak gelir"). Şimdilik tam biçimleri listeli; "gelirken" eşleşmez.
- **THY–CFM tipi haber birincil `Europe`, ikincil `Manufacturers & Supply Chain` etiketi alır** (taşıyıcı kuralı üretici kuralından önce). Sıra `rule_order` ile değişir.
- **`articles[:12]` kesmesi** zamana göre; Adım 2'de skora göre seçime dönüşecek.
- **`thy_impact_assessment` / THY merceği** prompt, şema ve arayüzde duruyor (`market_read` geçişi Adım 3).
- **`index.html` hâlâ `user-scalable=no`** (erişilebilirlik).
- **Spirit Airlines filosu 0.** Doğrulama kaynağı (Wikipedia) 2026-05-02'de faaliyetin durduğunu yazıyor; tek kaynak, `needs_verification=1` bırakıldı. Gerçekse satır tier 4'e düşmüş olur.
- **Seed rakamları kısmen doğrulanmış tahmin.** Doğrulama turu `reports/entity_seed_review.md` üzerinden.
