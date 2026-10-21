"""Aviation Earnings & Traffic Calendar (Bilanço & Trafik Takvimi).

Tracks scheduled quarterly financial disclosures (1Q, 2Q, 3Q/9M, 4Q/FY) and monthly traffic/passenger
reports for Turkish carriers (THY, Pegasus), European airline groups (Lufthansa, IAG, Air France-KLM, Ryanair),
US majors (Delta, United), aircraft manufacturers (Airbus, Boeing), and industry bodies (DHMİ, IATA).
"""

from datetime import date, datetime, timedelta, timezone

SCHEDULED_EVENTS = [
    # --- October / November 2026 Earnings & Traffic Schedule ---
    {
        "id": "lha-q3-2026",
        "entity": "Lufthansa Group",
        "ticker": "LHA.DE",
        "country": "Almanya",
        "event_type": "financial_results",
        "title_tr": "Lufthansa Group 3Ç 2026 Finansal Sonuçları",
        "title_en": "Lufthansa Group Q3 2026 Financial Results",
        "period": "3Ç 2026 (9M)",
        "date": "2026-10-29",
        "official_url": "https://investor-relations.lufthansagroup.com",
        "watchpoints_tr": "Birim gelirler (RASK), City Airlines maliyetleri, Lufthansa Technik kârlılığı ve Boeing 787/777X teslimat gecikmelerinin tazminat etkisi.",
        "watchpoints_en": "Unit revenue (RASK), City Airlines expansion costs, Lufthansa Technik profitability, and Boeing delivery delay compensation.",
    },
    {
        "id": "airbus-q3-2026",
        "entity": "Airbus SE",
        "ticker": "AIR.PA",
        "country": "Fransa / Avrupa",
        "event_type": "financial_results",
        "title_tr": "Airbus 3Ç / 9 Aylık Finansal Sonuçları & Teslimat Güncellemesi",
        "title_en": "Airbus Q3 2026 Results & Commercial Delivery Guidance",
        "period": "3Ç 2026 (9M)",
        "date": "2026-10-30",
        "official_url": "https://www.airbus.com/en/investors",
        "watchpoints_tr": "2026 yılı 770 ticari uçak teslimat hedefi, A321XLR ilk teslimat hacmi ve Pratt & Whitney motor tedarik darboğazı.",
        "watchpoints_en": "Commercial aircraft delivery target, A321XLR delivery ramp-up, and PW1100G engine supplier constraints.",
    },
    {
        "id": "thyao-q3-2026",
        "entity": "Türk Hava Yolları",
        "ticker": "THYAO",
        "country": "Türkiye",
        "event_type": "financial_results",
        "title_tr": "Türk Hava Yolları (THY) 3Ç 2026 Bilanço & 9 Aylık Finansallar",
        "title_en": "Turkish Airlines (THY) Q3 / 9M 2026 Financial Results",
        "period": "3Ç 2026 (9M)",
        "date": "2026-11-03",
        "official_url": "https://investor.turkishairlines.com",
        "watchpoints_tr": "EBITDAR marjı, kargo (Turkish Cargo) gelir büyümesi, jet yakıtı crack spread etkisi ve AJet'in bağımsız operasyonel maliyet ayrışması.",
        "watchpoints_en": "EBITDAR margin, Turkish Cargo yield trends, jet fuel crack spread exposure, and AJet standalone cost performance.",
    },
    {
        "id": "ryanair-h1-2026",
        "entity": "Ryanair Holdings",
        "ticker": "RYA.L",
        "country": "İrlanda",
        "event_type": "financial_results",
        "title_tr": "Ryanair 1Y / 2Ç 2026 Finansal Sonuçları (Yarıyıl)",
        "title_en": "Ryanair H1 2026 Financial Results",
        "period": "1Y / 2Ç 2026",
        "date": "2026-11-04",
        "official_url": "https://investor.ryanair.com",
        "watchpoints_tr": "Ortalama bilet fiyatı (fare yields) baskısı, yolcu başı yan gelir (ancillary revenue) ve Boeing 737 MAX teslimat eksiklikleri.",
        "watchpoints_en": "Average fare yield trends, ancillary revenue per passenger, and Boeing 737 MAX delivery shortfall impact.",
    },
    {
        "id": "pgsus-q3-2026",
        "entity": "Pegasus Hava Yolları",
        "ticker": "PGSUS",
        "country": "Türkiye",
        "event_type": "financial_results",
        "title_tr": "Pegasus Hava Yolları 3Ç 2026 Bilanço & 9 Aylık Finansallar",
        "title_en": "Pegasus Airlines Q3 / 9M 2026 Financial Results",
        "period": "3Ç 2026 (9M)",
        "date": "2026-11-05",
        "official_url": "https://www.pegasusyatirimciiliskileri.com",
        "watchpoints_tr": "Dış hat misafir doluluk oranı, CASK (koltuk-km başı maliyet), yan gelir payı ve SAW (Sabiha Gökçen) 2. pist kapasite çarpanı.",
        "watchpoints_en": "International load factor, ex-fuel CASK discipline, ancillary revenue per guest, and SAW runway 2 throughput.",
    },
    {
        "id": "airfrance-klm-q3-2026",
        "entity": "Air France-KLM",
        "ticker": "AF.PA",
        "country": "Fransa / Hollanda",
        "event_type": "financial_results",
        "title_tr": "Air France-KLM 3Ç 2026 Finansal Sonuçları",
        "title_en": "Air France-KLM Q3 2026 Financial Results",
        "period": "3Ç 2026 (9M)",
        "date": "2026-11-06",
        "official_url": "https://www.airfranceklm.com/en/investors",
        "watchpoints_tr": "KLM operasyonel marj iyileşmesi, Schiphol havalimanı kapasite tavanı ve Paris Olimpiyatları sonrası sonbahar talep eğilimleri.",
        "watchpoints_en": "KLM operating margin recovery, Schiphol flight cap headwinds, and autumn transatlantic forward bookings.",
    },
    {
        "id": "iag-q3-2026",
        "entity": "International Airlines Group (IAG)",
        "ticker": "IAG.MC",
        "country": "İngiltere / İspanya",
        "event_type": "financial_results",
        "title_tr": "IAG (British Airways & Iberia) 3Ç 2026 Finansalları",
        "title_en": "IAG Q3 2026 Financial Results",
        "period": "3Ç 2026 (9M)",
        "date": "2026-11-07",
        "official_url": "https://www.iairgroup.com/en/investors-and-shareholders",
        "watchpoints_tr": "Kuzey Atlantik (British Airways) kârlılığı, Latin Amerika (Iberia) gücü ve hissedar temettü / hisse geri alım programı.",
        "watchpoints_en": "Transatlantic premium cabin yields (BA), Latin America strength (Iberia), and shareholder distribution outlook.",
    },
    {
        "id": "thy-oct-traffic-2026",
        "entity": "Türk Hava Yolları",
        "ticker": "THYAO",
        "country": "Türkiye",
        "event_type": "traffic_report",
        "title_tr": "THY Ekim 2026 Trafik & Yolcu Taşıma Sonuçları",
        "title_en": "Turkish Airlines October 2026 Traffic & Capacity Figures",
        "period": "Ekim 2026",
        "date": "2026-11-10",
        "official_url": "https://investor.turkishairlines.com",
        "watchpoints_tr": "Toplam yolcu sayısı, dıştan dışa transfer (transit) yolcu oranı ve taşınan kargo-posta hacmi (ton).",
        "watchpoints_en": "Total passengers carried, international-to-international transfer ratio, and cargo tonnage growth.",
    },
    {
        "id": "pgsus-oct-traffic-2026",
        "entity": "Pegasus Hava Yolları",
        "ticker": "PGSUS",
        "country": "Türkiye",
        "event_type": "traffic_report",
        "title_tr": "Pegasus Ekim 2026 Trafik & Doluluk Verileri",
        "title_en": "Pegasus Airlines October 2026 Traffic & Load Factor Report",
        "period": "Ekim 2026",
        "date": "2026-11-11",
        "official_url": "https://www.pegasusyatirimciiliskileri.com",
        "watchpoints_tr": "Dış hat ve iç hat yolcu dağılımı, koltuk doluluk oranı ve filo büyüklüğü (A321neo teslimatları).",
        "watchpoints_en": "International vs domestic volume split, passenger load factor, and A321neo fleet expansion.",
    },
    {
        "id": "dhmi-oct-traffic-2026",
        "entity": "DHMİ Genel Müdürlüğü",
        "ticker": "DHMİ",
        "country": "Türkiye",
        "event_type": "traffic_report",
        "title_tr": "DHMİ Türkiye Geneli Havalimanları Ekim 2026 Yolcu İstatistikleri",
        "title_en": "DHMI Turkish Airports October 2026 Traffic Statistics",
        "period": "Ekim 2026",
        "date": "2026-11-12",
        "official_url": "https://www.dhmi.gov.tr",
        "watchpoints_tr": "İstanbul Havalimanı (İGA), Antalya ve Sabiha Gökçen yolcu sayıları, turizm merkezleri dış hat trafiği.",
        "watchpoints_en": "Istanbul Airport (IGA), Antalya and SAW passenger volumes; Mediterranean tourist gateway trends.",
    },
    {
        "id": "iata-global-traffic-2026",
        "entity": "IATA (International Air Transport Association)",
        "ticker": "IATA",
        "country": "Küresel",
        "event_type": "traffic_report",
        "title_tr": "IATA Küresel Yolcu & Hava Kargo Piyasa Analizi",
        "title_en": "IATA Global Passenger & Air Cargo Market Report",
        "period": "Eylül / 3Ç 2026",
        "date": "2026-11-15",
        "official_url": "https://www.iata.org",
        "watchpoints_tr": "Küresel RPK (ücretli yolcu km) büyümesi, Asya-Pasifik toparlanması ve hava kargo CTK talep trendi.",
        "watchpoints_en": "Global RPK growth, Asia-Pacific recovery velocity, and air cargo CTK cargo demand trajectory.",
    },
]


def classify_event_status(target_date, today, has_verified_document=False):
    """Determine event status, days difference, and human badge."""
    delta_days = (target_date - today).days
    if delta_days < 0:
        if has_verified_document:
            return "REPORTED", delta_days, "Açıklandı (Doğrulandı)", "Reported (Verified)"
        return "REPORTED", delta_days, "Açıklandı (Teyit Bekleniyor)", "Reported (Pending Filing)"
    elif delta_days == 0:
        return "TODAY", 0, "BUGÜN AÇIKLANIYOR", "TODAY"
    elif delta_days <= 3:
        return "THIS_WEEK", delta_days, f"🚨 {delta_days} Gün Kaldı", f"🚨 In {delta_days} Days"
    elif delta_days <= 7:
        return "THIS_WEEK", delta_days, f"Bu Hafta ({delta_days} gün)", f"This Week ({delta_days}d)"
    else:
        return "UPCOMING", delta_days, f"{delta_days} gün kaldı", f"In {delta_days} days"


def load_calendar(now=None):
    """Return structured, sorted earnings & traffic release calendar relative to current date."""
    if now is None:
        today = datetime.now(timezone.utc).date()
    elif isinstance(now, datetime):
        today = now.date()
    elif isinstance(now, date):
        today = now
    else:
        today = datetime.now(timezone.utc).date()

    items = []
    for ev in SCHEDULED_EVENTS:
        ev_date = datetime.strptime(ev["date"], "%Y-%m-%d").date()
        has_doc = bool(ev.get("document_url"))
        status_code, days_diff, badge_tr, badge_en = classify_event_status(ev_date, today, has_verified_document=has_doc)
        pub_status = "CONFIRMED_REPORTED" if (days_diff < 0 and has_doc) else ("PENDING_CONFIRMATION" if days_diff < 0 else "SCHEDULED")
        pub_status_tr = "Yayımlandı & Doğrulandı" if (days_diff < 0 and has_doc) else ("Teyit Bekleniyor" if days_diff < 0 else "Planlandı")
        pub_status_en = "Published & Verified" if (days_diff < 0 and has_doc) else ("Pending Confirmation" if days_diff < 0 else "Scheduled")
        items.append({
            "id": ev["id"],
            "entity": ev["entity"],
            "ticker": ev["ticker"],
            "country": ev["country"],
            "event_type": ev["event_type"],
            "event_type_tr": "Bilanço & Finansal Sonuçlar" if ev["event_type"] == "financial_results" else "Aylık Trafik Verisi",
            "event_type_en": "Financial Results" if ev["event_type"] == "financial_results" else "Monthly Traffic Report",
            "title_tr": ev["title_tr"],
            "title_en": ev["title_en"],
            "period": ev["period"],
            "date": ev["date"],
            "status": status_code,
            "days_diff": days_diff,
            "badge_tr": badge_tr,
            "badge_en": badge_en,
            "publication_status": pub_status,
            "publication_status_tr": pub_status_tr,
            "publication_status_en": pub_status_en,
            "verification_date": ev.get("verification_date", "2026-10-18"),
            "document_url": ev.get("document_url", ev.get("official_url", "")),
            "official_url": ev.get("official_url", ""),
            "watchpoints_tr": ev.get("watchpoints_tr", ""),
            "watchpoints_en": ev.get("watchpoints_en", ""),
        })

    # Sort: future events first (ascending by days_diff), then reported events
    upcoming = sorted([it for it in items if it["days_diff"] >= 0], key=lambda x: x["days_diff"])
    past = sorted([it for it in items if it["days_diff"] < 0], key=lambda x: x["days_diff"], reverse=True)
    all_events = upcoming + past

    financial_count = sum(1 for it in upcoming if it["event_type"] == "financial_results")
    traffic_count = sum(1 for it in upcoming if it["event_type"] == "traffic_report")

    # Key highlight summary
    next_event = upcoming[0] if upcoming else None
    highlight_tr = f"En yakın açıklama: {next_event['entity']} {next_event['period']} ({next_event['badge_tr']})" if next_event else "Aktif takvim"
    highlight_en = f"Next release: {next_event['entity']} {next_event['period']} ({next_event['badge_en']})" if next_event else "Active schedule"

    return {
        "status": "ok",
        "as_of": today.isoformat(),
        "total_events": len(all_events),
        "upcoming_count": len(upcoming),
        "financial_count": financial_count,
        "traffic_count": traffic_count,
        "highlight_tr": highlight_tr,
        "highlight_en": highlight_en,
        "events": all_events,
    }
