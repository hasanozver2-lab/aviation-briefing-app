"""Airspace & Conflict Zones Radar (EASA CZIB / Conflict Zone Bulletins).

Tracks active conflict zone information bulletins, affected FIRs (Flight Information Regions),
and military/geopolitical airspace closures relevant to civil airlines (THY, Pegasus, global carriers).
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

FEED_URL = "https://www.easa.europa.eu/en/domains/air-operations/czibs/feed.xml"
CZIB_PORTAL_URL = "https://www.easa.europa.eu/en/domains/air-operations/czibs"

KNOWN_FIR_REGIONS = {
    "iran": {
        "fir": "OIIX (Tehran)",
        "country_tr": "İran",
        "risk_level": "DO_NOT_OPERATE",
        "risk_badge": "🔴 UÇUŞA KAPALI",
        "risk_badge_en": "🔴 DO NOT OPERATE",
        "restriction_tr": "FIR Tehran (OIIX) tüm irtifalar ve uçuş seviyeleri.",
        "restriction_en": "FIR Tehran (OIIX), all altitudes and flight levels.",
        "summary_tr": "Askeri çatışma ve hava savunma füzesi riski nedeniyle sivil uçuşlara kapalıdır.",
        "summary_en": "High risk of military confrontation and air defence system misidentification.",
    },
    "lebanon": {
        "fir": "OLBB (Beirut)",
        "country_tr": "Lübnan",
        "risk_level": "DO_NOT_OPERATE",
        "risk_badge": "🔴 YÜKSEK RİSK",
        "risk_badge_en": "🔴 HIGH RISK",
        "restriction_tr": "FIR Beirut (OLBB) tüm irtifalar; Beyrut iniş/kalkış risk değerlendirmesi.",
        "restriction_en": "FIR Beirut (OLBB), all altitudes; heightened risk during approach.",
        "summary_tr": "İsrail ve Lübnan arasındaki hava saldırıları ve füze trafiği nedeniyle uçuşlar kısıtlıdır.",
        "summary_en": "Airstrikes and cross-border missile activity pose high risk to civil flights.",
    },
    "israel": {
        "fir": "LLLL (Tel Aviv)",
        "country_tr": "İsrail",
        "risk_level": "HIGH_RISK",
        "risk_badge": "🟠 ASKERİ RİSK",
        "risk_badge_en": "🟠 MILITARY RISK",
        "restriction_tr": "FIR Tel Aviv (LLLL) füze/İHA tehdidi ve sıkı rota kontrolü.",
        "restriction_en": "FIR Tel Aviv (LLLL) active rocket/drone interception zone.",
        "summary_tr": "Hava savunma sistemleri devrede; rotalar ve operasyonlar anlık NOTAM'lara tabidir.",
        "summary_en": "Air defence systems active; commercial operations subject to rapid NOTAM closures.",
    },
    "iraq": {
        "fir": "ORBB (Baghdad)",
        "country_tr": "Irak",
        "risk_level": "RESTRICTED",
        "risk_badge": "🟠 İRTİFA KISITI",
        "risk_badge_en": "🟠 ALTITUDE LIMIT",
        "restriction_tr": "FIR Baghdad (ORBB) FL320 altı yasak; sadece yüksek transit koridoru.",
        "restriction_en": "FIR Baghdad (ORBB) prohibited below FL320; transit corridor only.",
        "summary_tr": "Bölgesel füze/İHA geçiş rotası; FL320 altı operasyonlar tavsiye edilmemektedir.",
        "summary_en": "Transit corridor for regional drone/missile activity; avoid below FL320.",
    },
    "persian gulf": {
        "fir": "OMAE / OOMM / OBBB",
        "country_tr": "Basra Körfezi & Umman Denizi",
        "risk_level": "CAUTION",
        "risk_badge": "🟡 DİKKAT / GPS UYARISI",
        "risk_badge_en": "🟡 CAUTION / GPS ALERT",
        "restriction_tr": "Hürmüz Boğazı ve Basra Körfezi hava koridorları; yoğun GPS karıştırma.",
        "restriction_en": "Strait of Hormuz and Persian Gulf corridors; severe GPS/GNSS spoofing.",
        "summary_tr": "Bölgede yoğun elektronik harp (GPS spoofing/jamming) ve askeri teyakkuz bulunmaktadır.",
        "summary_en": "Widespread GNSS spoofing and jamming; heightened regional military readiness.",
    },
    "saudi arabia": {
        "fir": "OEJD (Jeddah)",
        "country_tr": "Suudi Arabistan",
        "risk_level": "CAUTION",
        "risk_badge": "🟡 DİKKAT / GÜNEY SINIRI",
        "risk_badge_en": "🟡 CAUTION / SOUTHERN BORDER",
        "restriction_tr": "Yemen sınırı ve Kızıldeniz FIR hattında dikkatli seyir.",
        "restriction_en": "Vigilance along Yemen border and southern Red Sea airway segments.",
        "summary_tr": "Yemen kaynaklı İHA/füze tehditleri nedeniyle güney koridorlarında teyakkuz tavsiye edilir.",
        "summary_en": "Heightened vigilance advised for southern border airways and Red Sea routes.",
    },
    "jordan": {
        "fir": "OJAC (Amman)",
        "country_tr": "Ürdün",
        "risk_level": "CAUTION",
        "risk_badge": "🟡 TEYAKKUZ",
        "risk_badge_en": "🟡 VIGILANCE",
        "restriction_tr": "FIR Amman (OJAC) doğu ve güney sınır rotaları.",
        "restriction_en": "FIR Amman (OJAC) eastern and southern boundary segments.",
        "summary_tr": "Bölgesel füze engelleme tatbikatları ve anlık hava sahası geçici kapanma riski.",
        "summary_en": "Risk of rapid airspace closure during regional missile interception events.",
    },
    "ukraine": {
        "fir": "UKBV / UKDV / UKLV / UKOV / UKFV",
        "country_tr": "Ukrayna",
        "risk_level": "DO_NOT_OPERATE",
        "risk_badge": "🔴 UÇUŞA KAPALI",
        "risk_badge_en": "🔴 DO NOT OPERATE",
        "restriction_tr": "Ukrayna tüm hava sahası sivil uçuşlara tamamen kapalıdır.",
        "restriction_en": "All Ukrainian airspace strictly closed to civil aviation.",
        "summary_tr": "Aktif askeri çatışma ve yoğun hava savunma sistemleri nedeniyle tamamen kapalıdır.",
        "summary_en": "Active war zone with anti-aircraft warfare systems deployed.",
    },
    "russian federation": {
        "fir": "URRV (Rostov) / UUWV (Moscow güneyi)",
        "country_tr": "Rusya (Güney Sınırı)",
        "risk_level": "DO_NOT_OPERATE",
        "risk_badge": "🔴 UÇUŞA KAPALI",
        "risk_badge_en": "🔴 DO NOT OPERATE",
        "restriction_tr": "Ukrayna sınırına 100 NM mesafe ve Rostov FIR batısı.",
        "restriction_en": "Within 100 NM of Ukrainian border and western Rostov FIR.",
        "summary_tr": "İHA saldırıları ve askeri operasyonlar nedeniyle sınır FIR'ları sivil uçuşa kapalıdır.",
        "summary_en": "Border airspace closed due to drone operations and military conflict.",
    },
    "yemen": {
        "fir": "OYSC (Sana'a)",
        "country_tr": "Yemen & Kızıldeniz",
        "risk_level": "DO_NOT_OPERATE",
        "risk_badge": "🔴 UÇUŞA KAPALI",
        "risk_badge_en": "🔴 DO NOT OPERATE",
        "restriction_tr": "FIR Sana'a (OYSC) tüm irtifalar ve güney Kızıldeniz sahası.",
        "restriction_en": "FIR Sana'a (OYSC), all altitudes and southern Red Sea airspace.",
        "summary_tr": "Askeri operasyonlar ve gemilere yönelik balistik füze saldırıları riski.",
        "summary_en": "Armed conflict and anti-ship missile activity pose severe risk.",
    },
    "syria": {
        "fir": "OSTT (Damascus)",
        "country_tr": "Suriye",
        "risk_level": "DO_NOT_OPERATE",
        "risk_badge": "🔴 UÇUŞA KAPALI",
        "risk_badge_en": "🔴 DO NOT OPERATE",
        "restriction_tr": "FIR Damascus (OSTT) tüm irtifalar.",
        "restriction_en": "FIR Damascus (OSTT), all altitudes.",
        "summary_tr": "Süregelen askeri harekatlar ve hava saldırıları nedeniyle sivil uçuşa kapalıdır.",
        "summary_en": "High risk of military conflict and air defence activity.",
    },
    "sudan": {
        "fir": "HSSS (Khartoum)",
        "country_tr": "Sudan",
        "risk_level": "DO_NOT_OPERATE",
        "risk_badge": "🔴 UÇUŞA KAPALI",
        "risk_badge_en": "🔴 DO NOT OPERATE",
        "restriction_tr": "FIR Khartoum (HSSS) tüm irtifalar.",
        "restriction_en": "FIR Khartoum (HSSS), all altitudes.",
        "summary_tr": "İç çatışma ve havalimanlarının silahlı güçler kontrolünde olması riski.",
        "summary_en": "Civil conflict and active fighting around international airports.",
    },
    "libya": {
        "fir": "HLLL (Tripoli)",
        "country_tr": "Libya",
        "risk_level": "DO_NOT_OPERATE",
        "risk_badge": "🔴 UÇUŞA KAPALI",
        "risk_badge_en": "🔴 DO NOT OPERATE",
        "restriction_tr": "FIR Tripoli (HLLL) tüm irtifalar.",
        "restriction_en": "FIR Tripoli (HLLL), all altitudes.",
        "summary_tr": "Silahlı çatışmalar ve hava savunma silahları riski nedeniyle operasyon önerilmez.",
        "summary_en": "Threat from anti-aircraft weaponry and armed militias.",
    },
    "somalia": {
        "fir": "HCSM (Mogadishu)",
        "country_tr": "Somali",
        "risk_level": "RESTRICTED",
        "risk_badge": "🟠 FL260 ALTI YASAK",
        "risk_badge_en": "🟠 BELOW FL260 PROHIBITED",
        "restriction_tr": "FIR Mogadishu (HCSM) FL260 altı riskli.",
        "restriction_en": "FIR Mogadishu (HCSM) do not operate below FL260.",
        "summary_tr": "MANPADS ve hafif uçaksavar silahları riski nedeniyle FL260 üzerinde transit önerilir.",
        "summary_en": "Risk of MANPADS weaponry; maintain cruising level above FL260.",
    },
}


def parse_czib_feed(xml_text):
    """Parse EASA CZIB RSS feed into normalized advisory items."""
    if not xml_text or not xml_text.strip():
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items = []
    channel = root.find("channel")
    if channel is None:
        return []
    for item in channel.findall("item"):
        title = (item.find("title").text if item.find("title") is not None else "").strip()
        link = (item.find("link").text if item.find("link") is not None else "").strip()
        pub_date = (item.find("pubDate").text if item.find("pubDate") is not None else "").strip()
        if not title:
            continue
        items.append({"title": title, "link": link, "pub_date": pub_date})
    return items


def match_known_region(title):
    """Match advisory title to known FIR / region configuration."""
    clean_title = title.lower()
    for key, data in KNOWN_FIR_REGIONS.items():
        if key in clean_title:
            return key, data
    return None, None


def extract_bulletin_code(url):
    """Extract CZIB-YYYY-NN-Rx identifier from link URL."""
    if not url:
        return ""
    m = re.search(r"(czib-\d{4}-\d{2}-?r?\d*|\d{4}-\d{2}-?r?\d*)", url, re.IGNORECASE)
    return m.group(1).upper() if m else ""


def build_zone_record(feed_item):
    """Build a rich zone record from a feed item and known FIR metadata."""
    title = feed_item.get("title", "")
    link = feed_item.get("link", CZIB_PORTAL_URL)
    pub_date = feed_item.get("pub_date", "")
    key, meta = match_known_region(title)
    if not meta:
        meta = {
            "fir": "Regional FIR",
            "country_tr": title.replace("Airspace of", "").strip(),
            "risk_level": "WARNING",
            "risk_badge": "🟠 UYARI / CZIB",
            "risk_badge_en": "🟠 WARNING / CZIB",
            "restriction_tr": "EASA CZIB bültenine göre kısıtlı hava sahası.",
            "restriction_en": "Restricted airspace per active EASA bulletin.",
            "summary_tr": "Bölgesel güvenlik riski nedeniyle EASA operasyonel bülteni yürürlüktedir.",
            "summary_en": "Active EASA operational conflict zone advisory in effect.",
        }
    return {
        "title": title,
        "country": meta.get("country_tr", title),
        "fir": meta.get("fir", "FIR"),
        "risk_level": meta.get("risk_level", "WARNING"),
        "risk_badge": meta.get("risk_badge", "🟠 UYARI"),
        "risk_badge_en": meta.get("risk_badge_en", "🟠 WARNING"),
        "restriction_tr": meta.get("restriction_tr", ""),
        "restriction_en": meta.get("restriction_en", ""),
        "summary_tr": meta.get("summary_tr", ""),
        "summary_en": meta.get("summary_en", ""),
        "bulletin_code": extract_bulletin_code(link),
        "published_date": pub_date,
        "link": link or CZIB_PORTAL_URL,
    }


def fetch_czib_feed(timeout=6, opener=None):
    """Fetch raw XML from EASA CZIB feed or return None on failure."""
    _opener = opener or urllib.request.urlopen
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }
    req = urllib.request.Request(FEED_URL, headers=headers)
    try:
        with _opener(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None


def get_fallback_zones():
    """Return default high-risk zones if remote feed is unreachable."""
    zones = []
    # Primary critical zones that all airlines monitor
    critical_keys = ["iran", "lebanon", "israel", "iraq", "persian gulf", "ukraine", "russian federation", "yemen", "syria", "sudan"]
    for key in critical_keys:
        meta = KNOWN_FIR_REGIONS[key]
        zones.append({
            "title": f"Airspace of {meta['country_tr']}",
            "country": meta["country_tr"],
            "fir": meta["fir"],
            "risk_level": meta["risk_level"],
            "risk_badge": meta["risk_badge"],
            "risk_badge_en": meta["risk_badge_en"],
            "restriction_tr": meta["restriction_tr"],
            "restriction_en": meta["restriction_en"],
            "summary_tr": meta["summary_tr"],
            "summary_en": meta["summary_en"],
            "bulletin_code": "EASA CZIB",
            "published_date": "Active 2026",
            "link": CZIB_PORTAL_URL,
        })
    return zones


def load_radar(xml_text=None, opener=None, timeout=6, now=None):
    """Return the complete Airspace & Conflict Zone Radar data structure."""
    raw_xml = xml_text if xml_text is not None else fetch_czib_feed(timeout=timeout, opener=opener)
    feed_items = parse_czib_feed(raw_xml) if raw_xml else []
    
    if feed_items:
        seen_keys = set()
        zones = []
        for item in feed_items:
            key, _ = match_known_region(item.get("title", ""))
            dedup_key = key or item.get("title", "").lower()
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            zones.append(build_zone_record(item))
    else:
        zones = get_fallback_zones()

    # Sort so DO_NOT_OPERATE comes first, then HIGH_RISK, RESTRICTED, CAUTION
    priority = {"DO_NOT_OPERATE": 0, "HIGH_RISK": 1, "RESTRICTED": 2, "WARNING": 3, "CAUTION": 4}
    zones.sort(key=lambda z: priority.get(z.get("risk_level"), 9))

    do_not_operate_count = sum(1 for z in zones if z.get("risk_level") == "DO_NOT_OPERATE")
    restricted_count = sum(1 for z in zones if z.get("risk_level") in ("HIGH_RISK", "RESTRICTED", "WARNING"))
    caution_count = sum(1 for z in zones if z.get("risk_level") == "CAUTION")

    updated_time = now if isinstance(now, datetime) else datetime.now(timezone.utc)
    if updated_time.tzinfo is None:
        updated_time = updated_time.replace(tzinfo=timezone.utc)

    return {
        "status": "ok",
        "updated_at": updated_time.isoformat(timespec="seconds"),
        "source": "EASA Conflict Zone Information Bulletins (CZIB)",
        "source_url": CZIB_PORTAL_URL,
        "total_active_zones": len(zones),
        "do_not_operate_count": do_not_operate_count,
        "restricted_count": restricted_count,
        "caution_count": caution_count,
        "headline_alert_tr": f"🚨 {do_not_operate_count} Hava Sahası Sivil Uçuşa Kapalı / Yüksek Riskli",
        "headline_alert_en": f"🚨 {do_not_operate_count} Airspaces Under Do-Not-Operate / High Risk Advisory",
        "zones": zones,
    }
