"""Fleet, Delivery & Engine Delays Watch (Filo, Teslimat & Motor Gecikmeleri Radarı).

Tracks OEM delivery targets (Airbus, Boeing, Embraer), engine inspection groundings
(Pratt & Whitney GTF PW1100G, CFM LEAP supply bottlenecks, Rolls-Royce Trent),
and Turkish / global airline fleet impacts (THY A321neo groundings, Pegasus deliveries).
"""

from datetime import datetime, timezone

FLEET_PROGRAMS = [
    {
        "id": "pw-gtf-groundings",
        "category": "ENGINE_GROUNDING",
        "category_tr": "Motor Güvenlik & Yere İndirme",
        "category_en": "Engine Grounding & Airworthiness",
        "title_tr": "Pratt & Whitney GTF (PW1100G) Toz Metal Kusuru & Yere İndirmeler",
        "title_en": "Pratt & Whitney GTF (PW1100G) Powder Metal Defect & Groundings",
        "severity": "CRITICAL",
        "severity_badge": "🔴 KRİTİK ETKİ",
        "affected_carriers": ["Türk Hava Yolları", "Wizz Air", "Lufthansa", "IndiGo", "Spirit Airlines"],
        "aircraft_models": ["Airbus A320neo", "Airbus A321neo"],
        "engine_model": "Pratt & Whitney PW1100G-JM / GTF",
        "current_status_tr": "Yüksek basınçlı türbin disklerindeki mikroskobik toz metal kirliliği nedeniyle küresel çapta yüzlerce A320neo/A321neo uçağı planlanmamış motor bakımına alındı. Ortalama motor revizyon süresi (TAT) 250-300 günü buluyor.",
        "current_status_en": "Contaminated powder metal in high-pressure turbine disks required accelerated inspections; hundreds of A320neo family jets grounded globally with MRO shop turnaround times reaching 250-300 days.",
        "thy_pegasus_impact_tr": "THY filosundaki yaklaşık 30-40 adet A320/A321neo uçağı yerde bekliyor; kapasite açığını kapatmak için ıslak kiralama (wet lease) ve mevcut A320ceo uçaklarının hizmet ömrünü uzatma yoluna gidildi. Pegasus filosu ağırlıklı CFM LEAP motorlu olduğu için doğrudan etkilenmedi.",
        "thy_pegasus_impact_en": "Turkish Airlines has 30-40 A321neo aircraft parked; capacity shortfall managed via wet leases and extending older A320ceo service lives. Pegasus remains largely unaffected due to CFM LEAP engine selection.",
        "timeline_horizon": "2026 yılı boyunca ve 2027 ilk yarısına kadar sürmesi bekleniyor.",
        "source_reference": "RTX Corporation / FAA Airworthiness Directives (AD 2024-0044) / THY KAP Açıklamaları",
    },
    {
        "id": "boeing-737max-faa-cap",
        "category": "DELIVERY_DELAY",
        "category_tr": "Üretim Tavanı & Teslimat Gecikmesi",
        "category_en": "Production Cap & Delivery Shortfall",
        "title_tr": "Boeing 737 MAX Üretim Kısıtı (FAA Aylık 38 Tavanı) & Tedarik Zinciri",
        "title_en": "Boeing 737 MAX FAA Monthly 38 Cap & Supply Chain Bottlecks",
        "severity": "HIGH",
        "severity_badge": "🟠 YÜKSEK GECİKME",
        "affected_carriers": ["Ryanair", "United Airlines", "Southwest Airlines", "SunExpress", "Flydubai"],
        "aircraft_models": ["Boeing 737 MAX 8", "737 MAX 9", "737 MAX 7 (Sertifikasyon)", "737 MAX 10 (Sertifikasyon)"],
        "engine_model": "CFM International LEAP-1B",
        "current_status_tr": "FAA'in kalite ve montaj denetimleri kapsamında Boeing 737 üretimini aylık 38 uçak tavanında tutması ve Spirit AeroSystems gövde teslimat gecikmeleri nedeniyle 2026 teslimat takvimleri 3-6 ay geriye ötelendi. MAX 7 ve MAX 10 sertifikasyonu gecikmeye devam ediyor.",
        "current_status_en": "FAA capped 737 production at 38/month pending quality audit milestones; Spirit AeroSystems fuselage supply constraints pushed airline delivery slots back by 3 to 6 months. MAX 7 and MAX 10 certification remains pending.",
        "thy_pegasus_impact_tr": "SunExpress ve THY teslimatları planlanan takvimin gerisinde seyrediyor; havayolları yoğun yaz ve sonbahar kapasite planlamalarını mevcut gövdelerle optimize ediyor.",
        "thy_pegasus_impact_en": "SunExpress and Turkish Airlines delivery streams experiencing slot postponements; carriers optimizing utilization on existing fleet assets.",
        "timeline_horizon": "Aylık 38 üretim tavanının 2026 sonuna kadar aşamalı olarak artırılması hedefleniyor.",
        "source_reference": "FAA Oversight Directives / Boeing Quarterly Deliveries / Airline Fleet Filings",
    },
    {
        "id": "airbus-a321xlr-entry",
        "category": "FLEET_EXPANSION",
        "category_tr": "Yeni Tip Teslimatı & Rota Genişlemesi",
        "category_en": "New Aircraft Delivery & Route Expansion",
        "title_tr": "Airbus A321XLR Ticari Teslimatları & Dar Gövde Uzun Menzil Devrimi",
        "title_en": "Airbus A321XLR Entry into Service & Long-Range Narrowbody Wave",
        "severity": "WATCH",
        "severity_badge": "🟢 OLUMLU GENİŞLEME",
        "affected_carriers": ["Iberia (İlk Müşteri)", "Aer Lingus", "Wizz Air", "United Airlines", "American Airlines"],
        "aircraft_models": ["Airbus A321XLR"],
        "engine_model": "CFM LEAP-1A / Pratt & Whitney GTF",
        "current_status_tr": "EASA tip sertifikasyonunu tamamlayan A321XLR, Iberia tarafından Madrid-Boston hattında ilk ticari uçuşlarına başladı. 4.700 deniz mili (8.700 km) menziliyle dar gövdede transatlantik ve kıtalararası uçuş maliyetlerini %30 düşürüyor.",
        "current_status_en": "Having achieved EASA certification, the A321XLR commenced transatlantic operations with launch customer Iberia. Its 4,700 nm range unlocks thin long-haul routes at 30% lower trip cost.",
        "thy_pegasus_impact_tr": "Orta Doğu, Afrika ve ikincil Avrupa şehirlerine doğrudan bağlantı potansiyeli nedeniyle bölge taşıyıcıları tarafından yakından izleniyor. THY ve Pegasus filo stratejilerinde uzun vadeli alternatif.",
        "thy_pegasus_impact_en": "Closely monitored by regional carriers for secondary point-to-point routes into Africa, Central Asia and Europe; potential long-term fit for Istanbul network.",
        "timeline_horizon": "2026-2027 boyunca küresel teslimatların hızlanması planlanıyor.",
        "source_reference": "EASA Type Certificate Data Sheet (TCDS) / Airbus Commercial Aircraft Updates",
    },
    {
        "id": "boeing-777x-entry-timeline",
        "category": "DELIVERY_DELAY",
        "category_tr": "Geniş Gövde Gecikmesi",
        "category_en": "Widebody Program Delay",
        "title_tr": "Boeing 777-9 (777X) Test Uçuşları & Hizmete Giriş Tarihi",
        "title_en": "Boeing 777-9 (777X) Flight Testing & Entry-into-Service Schedule",
        "severity": "HIGH",
        "severity_badge": "🟠 2026/2027 GECİKMESİ",
        "affected_carriers": ["Emirates", "Lufthansa", "Qatar Airways", "Singapore Airlines", "Cathay Pacific"],
        "aircraft_models": ["Boeing 777-9", "777-8F"],
        "engine_model": "GE Aerospace GE9X",
        "current_status_tr": "İtiş kolu bağlantı elemanındaki (thrust link) teknik arıza sonrası test uçuşları geçici olarak durdurulmuştu; Boeing ilk teslimat takvimini 2026 yılına (ve potansiyel olarak 2027'ye) revize etti. Başta Emirates ve Lufthansa olmak üzere amiral gemisi filoları A380 ve 777-300ER ömür uzatmak zorunda kaldı.",
        "current_status_en": "Structural component inspection on engine thrust links required test fleet pause; initial deliveries rescheduled to 2026/2027. Major customers Emirates and Lufthansa forced to extend legacy 777-300ER and A380 service lives.",
        "thy_pegasus_impact_tr": "THY'nin geniş gövde siparişlerinde Airbus A350-1000'e ağırlık vermesinde 777X gecikmeleri belirleyici stratejik etken oldu.",
        "thy_pegasus_impact_en": "Delays were a primary catalyst for Turkish Airlines' decision to anchor its high-capacity widebody order book on the Airbus A350-1000.",
        "timeline_horizon": "FAA tip sertifikasyonu ve ilk ticari teslimat 2026 sonu / 2027 hedefleniyor.",
        "source_reference": "Boeing Defense, Space & Security / Airline IR Filings / Emirates President Statements",
    },
    {
        "id": "cfm-leap-durability-tat",
        "category": "MAINTENANCE_BOTTLENECK",
        "category_tr": "MRO & Yedek Parça Darboğazı",
        "category_en": "MRO & Spare Engine Scarcity",
        "title_tr": "CFM LEAP-1A / 1B Yüksek Basınç Türbini Dayanıklılığı & MRO Bekleme Süreleri",
        "title_en": "CFM LEAP-1A / 1B Hot-Section Durability & Shop Visit Backlogs",
        "severity": "RESTRICTED",
        "severity_badge": "🟡 İZLEMEDE / MRO DARBOĞAZI",
        "affected_carriers": ["Pegasus Hava Yolları", "Ryanair", "American Airlines", "easyJet", "Flydubai"],
        "aircraft_models": ["Airbus A320neo", "Airbus A321neo", "Boeing 737 MAX"],
        "engine_model": "CFM International LEAP-1A / LEAP-1B",
        "current_status_tr": "Sıcak iklim, tozlu hava sahası ve yüksek iniş-kalkış döngüsü altında çalışan LEAP motorlarında türbin kanatçığı erozyonu nedeniyle planlanandan erken motor indirme yaşanıyor. Küresel MRO atölyelerinde yedek parça ve motor kıtlığı devam ediyor.",
        "current_status_en": "Harsh environment operations (heat, sand, high cycle utilization) causing premature hot-section turbine blade wear; global MRO shops experiencing parts constraints and extended turn-around times.",
        "thy_pegasus_impact_tr": "Pegasus'un filosunun belkemiğini oluşturan A321neo uçaklarında CFM LEAP-1A motorları kullanılıyor. Pegasus, proaktif motor rotasyonu ve yedek motor rezervasyonu ile uçak yerde kalma süresini (AOG) asgaride tutuyor.",
        "thy_pegasus_impact_en": "Pegasus relies heavily on CFM LEAP-1A on its A321neo fleet; carrier leverages proactive engine rotation and buffer lease pools to keep AOG rates minimal.",
        "timeline_horizon": "CFM'in güncellenmiş dayanıklı parça (durability kit) teslimatları 2026 boyunca yaygınlaşıyor.",
        "source_reference": "Safran / GE Aerospace Engine Technical Briefings / Aviation Week MRO Watch",
    },
]


def load_fleet_watch():
    """Return complete structured Fleet, Delivery and Engine Delays dataset."""
    programs = FLEET_PROGRAMS[:]
    
    # Counts
    grounding_count = sum(1 for p in programs if p["category"] == "ENGINE_GROUNDING")
    delivery_delay_count = sum(1 for p in programs if p["category"] == "DELIVERY_DELAY")
    critical_count = sum(1 for p in programs if p["severity"] in ("CRITICAL", "HIGH"))

    # Baseline audit and verification timestamp of the tracked fleet dataset
    dataset_verified_at = "2026-10-18T10:00:00+00:00"

    return {
        "status": "ok",
        "dataset_version": "2026.10-R1",
        "last_verified_at": dataset_verified_at,
        "updated_at": dataset_verified_at,
        "total_programs": len(programs),
        "grounding_count": grounding_count,
        "delivery_delay_count": delivery_delay_count,
        "critical_count": critical_count,
        "headline_tr": f"🚨 Filo & Motor Radarı: {grounding_count} Kritik Motor Sorunu · {delivery_delay_count} OEM Teslimat Gecikmesi",
        "headline_en": f"🚨 Fleet Watch: {grounding_count} Engine Grounding Issues · {delivery_delay_count} OEM Delivery Delays",
        "programs": programs,
    }
