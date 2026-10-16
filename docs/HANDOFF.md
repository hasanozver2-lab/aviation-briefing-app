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

`data/*.sqlite3` git'te takipli değil; pipeline her çalışmada SQLite'ı CSV'den yeniden kurar (`_engine.run_pipeline`). `briefing_cache_*.json` **geçici olarak takipli kalıyor**: 2026-10-16 itibarıyla canlı site Blob'dan değil bu dosyalardan servis ediliyor (hiç Blob yayını yapılmadı). İlk başarılı Blob yayınından sonra takipten çıkarılacak (ayrı commit, önce onay).
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

## Yayın hattı (2026-10-16'dan beri: git dalı, Blob değil)
- Zamanlama: `.github/workflows/briefing-pipeline.yml`, **saatte bir** (`2 * * * *`), tek iş; tek çalıştırma toplar, puanlar, bugünün arşivine birleştirir (`daily`/`hourly` aynı arşivin görünümüdür) ve **tek commit** ile `briefing-data` dalına yazar (günde ≤ 24 commit). `main`'e hiçbir zaman commit atılmaz. İzin: yalnızca `contents: write`.
- Yazma: `scripts/run_pipeline.py` → `api/briefing_store.py` → `api/github_store.py`. Git plumbing (geçici index, `commit-tree`, tek ref push) kullanır; çalışma ağacına dokunmaz. Dosyalar: `briefings/YYYY-MM-DD.json` (Europe/Istanbul günü), `briefings/latest.json` (= bugünün dosyasının kopyası), `briefings/status.json`. Eski `daily.json`/`hourly.json`/`*-status.json` artık yazılmaz.
- Okuma: `/api/briefing` `latest.json`'ı (veya `?date=YYYY-MM-DD` ile o günün dosyasını) `raw.githubusercontent.com/<repo>/briefing-data/briefings/` altından okur (repo herkese açık olmalı; raw önbelleği ≈ 5 dk). Okuma başarısızsa commit'li `briefing_cache_*.json`'a düşer ve `status: "stale"` döner. Geçersiz tarih 400, arşivi olmayan gün 404.
- Depo seçimi: `BRIEFING_STORE=github|blob` (varsayılan `github`). Blob kodu (`api/blob_store.py`) duruyor; `blob` için `BLOB_READ_WRITE_TOKEN` ve `BLOB_PUBLIC_BASE_URL` gerekir. Okuma konumu `BRIEFING_DATA_REPO` / `BRIEFING_DATA_BRANCH` ile değiştirilebilir (Vercel'de `VERCEL_GIT_REPO_OWNER/SLUG` da kullanılır).
- Vercel: `vercel.json → git.deploymentEnabled["briefing-data"] = false`; veri dalı kendi `vercel.json`'unu da taşır (her commit'te yazılır), böylece push'lar yayın başlatmaz.
- Secrets: `GEMINI_API_KEY` (zorunlu), `EIA_API_KEY` (**isteğe bağlı**: yoksa Brent/jet yakıtı atlanır, ECB kurları sürer, panelde not görünür ve panel `partial` olur).
- Yerel deneme: `python scripts/run_pipeline.py --mode all --out-dir <klasör>` (yayınlamaz).
- Veri dalı büyür (~100 KB × 24/gün). Gerekirse dal periyodik olarak tek commit'e indirilebilir (orphan + force push); şimdilik yapılmadı.

## Haber yaşam döngüsü, arşiv ve etiketler (`api/story_lifecycle.py`)
Tamamı deterministik ve kural tabanlı; LLM yalnızca anlatı üretir, etiket/skor/sıralama üretmez.
- **Kimlik:** `story_id` = kanonik kaynak URL'sinin (utm/fbclid, sondaki `/`, fragment atılmış) SHA-1'inin ilk 12 hanesi (`story-<12 hane>`). Aynı haber her çalışmada ve günde aynı kimliği alır.
- **Zaman damgaları:** `first_seen_at` (bir kez yazılır, asla değişmez; dün görülen haber bugün yeniden gelirse dünkü değeri taşır), `last_updated_at` (yalnızca *önemli* değişimde ilerler), `published_at_iso` (makalenin yayın zamanı).
- **Eşleştirme:** aynı `story_id`, ortak kaynak URL'si veya başlık benzerliği ≥ `title_match_threshold` (0,6) → aynı haber. Aynı olayı anlatan farklı yayıncılar tek haberde `sources[]` altında toplanır.
- **Önemli değişim ("updated"):** skor `updated.min_score_change` kadar değişti veya yeni kaynak eklendi. Bu durumda içerik yenilenir; değilse haber **olduğu gibi** bırakılır (LLM metni her saat değişse de dosya değişmez).
- **Skor (`config/relevance.json`):** `active_version` = **v2 (geçici, sahibi onaylayana kadar sabitlenmedi)**; v1 aynen duruyor. 0–100 ağırlıklı toplam: event_type 45, kaynak güvenilirliği 15, varlık öne çıkışı 20, resmî kaynak 4, yayıncı sayısı 16 (v1: 35/20/25/10/10). Bileşenler `score_components` alanında. `selection`: skor ≥ 45 olan en fazla 12 haber arşive girer (geçici).
- **event_type kuralı:** bir tür, teriminin başlıkta geçmesiyle veya açıklamada en az 2 farklı terim geçmesiyle geçerli olur (tek terim, uzun açıklamadaki tanıtım metninden gelen yanlış eşleşmeyi önler: Delta haberi "personal guidance" yüzünden `airline_financials` sınıflanmıştı). Yeni türler: `safety_incident`, `operations_disruption`, `fleet_orders`, `community_csr` (ağırlık 0,05).
- **Anlatı (LLM) adımı (`api/narrative.py`, `config/narrative.json`):** deterministik seçimden sonra, anlatısı olmayan (`narrative_status: "pending"`) haberler için **tek toplu çağrı** (≤ 8 haber/çağrı, çalışma başına ≤ 2 çağrı). Anlatı `story_id` ile arşivde saklanır; değişmeyen haber için bir daha çağrı yapılmaz, önemli değişimde eski metin korunarak `pending` olur ve yeniden üretilir. 429/5xx'te 2, 4, 8 sn üstel geri çekilmeyle en fazla 4 deneme, sonra bırakılır (ilk başarısız partiden sonra o çalışmada yeni çağrı yapılmaz). Başarısız olursa skor, rozet, sıralama ve arşiv yine yayınlanır; iş kırmızı bitmez; sonraki saatte yeniden denenir. Piyasa olay yorumları artık şablondur (LLM çağrısı yok).
- **`status.json`:** `stale` yalnızca veri toplama gerçekten başarısız olduğunda (hiç makale toplanamadı) yazılır ve iş kırmızı biter. LLM sorunu `narrative_pending` / `narrative_error` olarak kaydedilir.
- **Etiketler (`config/badges.json`):** `new` (first_seen ≤ 6 s), `updated` (last_updated > first_seen ve ≤ 6 s), `breaking` (first_seen ≤ 3 s, skor ≥ `critical_score` 60 **ve** event_type `allowed_event_types` içinde: geopolitics_airspace, safety_incident, fuel_energy, airline_financials, operations_disruption). `new`/`breaking` için ayrıca yayın zamanı ≤ `max_publication_age_hours` (24) olmalı. **Etiketler API her yanıtladığında saklı zaman damgalarından yeniden hesaplanır**, süre dolunca pipeline çalışmasa da kalkar. Dosyadaki `badges` yalnızca yazım anının bilgisidir.
- **Sıralama:** breaking önce, sonra skor, sonra en yeni; her API yanıtında yeniden uygulanır.
- **Arşiv:** saatlik çalışma bugünün dosyasına birleştirir; **hiçbir haber silinmez**, geçmiş günler değişmez. Gün Europe/Istanbul gece yarısında döner (sistemde tz veritabanı yoksa sabit +03:00).
- **Commit yok kuralı:** içerik parmak izi (çalışma saatleri, rozetler, sıralama, piyasa yorumları hariç) değişmediyse gün dosyası ve `latest.json` yazılmaz; `status.json` yalnızca durum/hata değişince yazılır. Hiçbir şey değişmediyse commit atılmaz.
- **API:** `mode=daily` (varsayılan) bugünün tüm haberleri; `mode=hourly` bugünün son `hourly_view_window_hours` (2) saatte görülen/güncellenen haberleri; `date=YYYY-MM-DD` o günün arşivi. Her haberde `badges`.

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
- **Filo rakamlarının kaynağı Wikipedia (CC BY-SA).** Tier hesabı için yeterli; ancak varlık sayfalarında filo rakamı gösterilecekse kaynak gösterimi (atıf) ve lisans uyumu (CC BY-SA, türev veri paylaşımı koşulu) ayrıca ele alınmalı; `verification_source` sütunu atıf için başlangıç noktası.
- **ECB isteği ara sıra `HTTPError` veriyor** (2026-10-16 yerel çalıştırmada bir kez; hemen sonra sorunsuz). Actions'ta geçici DB her çalışmada boş olduğundan, tek başarısız istek o saatin kur panelini boş bırakır; basit bir yeniden deneme eklenebilir.
- **Canlı yayın hattı doğrulanmadı.** 2026-10-16: GitHub'da "Publish aviation briefings" için hiç çalışma kaydı yok ve canlı `/api/briefing` 14 Ekim tarihli commit'li önbelleği döndürüyor (`status`/`market` alanları yok). Secrets, ilk çalışma ve Blob okuma adresi (`BLOB_PUBLIC_BASE_URL`) doğrulanmalı.
- **Aynı depodan üç Vercel projesi yayın alıyor:** `aviation-briefing-app-drvd` (canlı site), `aviation-briefing-app-5w38` ve `aviation-briefing-app`. Amaçları belirsiz; kullanılmayanlar silinmeden önce sahibine sorulacak.
- **Veri dalında eski dosyalar duruyor:** `briefings/daily.json`, `hourly.json`, `*-status.json` artık güncellenmiyor; okunmuyor, silinebilir.
- **Aynı olay çok haber olarak görünüyor.** Başlık benzerliği (Jaccard ≥ 0,6) diller arası veya yeniden yazılmış başlıkları birleştirmiyor (THY–CFM 4, ACG siparişi 5, Lufthansa A350-1000 5 ayrı haber); yayıncı sayısı bu yüzden hep 1 ve `corroboration` bileşeni çalışmıyor. Ortak varlık + event_type + sayı ile kümeleme önerilir. Ayrıntı: `reports/relevance_calibration_v2.md`.
- **Finans yorumu ve askerî havacılık üst sırada.** Yahoo "stock" yazıları `airline_financials`/`breaking` olabiliyor; F-35/F-16/füze haberleri `geopolitics_airspace` olarak 42–49 puan alıyor. Kural önerileri kalibrasyon raporunda.
- **Eski veri dalı dosyaları:** `briefings/daily.json`, `hourly.json`, `*-status.json` canlı doğrulama bitene kadar duruyor; sonra silinmesi için sahibine sorulacak.
- **Eski tek çağrılı yol:** `_engine.run_pipeline(mode)` / `generate_briefing_with_gemini` yalnızca yerel bakım için duruyor, zamanlanmış hat `collect_run` + `narrative` kullanıyor; kaldırılabilir.
- **Seed rakamları kısmen doğrulanmış tahmin.** Doğrulama turu `reports/entity_seed_review.md` üzerinden.
