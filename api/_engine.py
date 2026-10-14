"""
Aviation Briefing Engine
Havacılık haberlerini RSS kaynaklarından toplar, Gemini 2.5 Flash ile analiz eder
ve executive brifing JSON çıktısını üretir.
"""

import os
import sys
import re
import json
import hashlib
import ssl
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
import xml.etree.ElementTree as ET

# Windows cp1254 encoding fix
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Konfigürasyon ve Yollar
BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent
ENV_FILE = ROOT_DIR / ".env"
VALID_MODES = {"daily", "hourly"}
SOURCE_POLICY_VERSION = "airline-only-v1"
SOURCE_TYPES = {
    "mainstream",
    "trade_media",
    "airline_ir",
    "airline_newsroom",
    "official_social",
}
SECTION_ORDER = [
    "Turkey / THY and Turkish aviation",
    "European and other global airlines",
    "Route news",
    "Other areas",
]


def validate_mode(mode):
    """Only accept modes backed by an isolated cache and prompt contract."""
    if mode not in VALID_MODES:
        raise ValueError("mode must be either 'daily' or 'hourly'")
    return mode


def utc_now():
    return datetime.now(timezone.utc)

def get_cache_path(filename):
    """Bulut/Serverless ortamlarinda /tmp dizinini, yerelde proje dizinini kullanir."""
    local_path = BASE_DIR / filename
    is_serverless = os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    if is_serverless:
        tmp_path = Path("/tmp") / filename
        if not tmp_path.exists() and local_path.exists():
            try:
                tmp_path.write_bytes(local_path.read_bytes())
            except OSError:
                pass
        return tmp_path
    return local_path

CACHE_FILE_DAILY = get_cache_path("briefing_cache_daily.json")
CACHE_FILE_HOURLY = get_cache_path("briefing_cache_hourly.json")

def load_env():
    """DEV kökündeki .env dosyasından anahtarları yükler."""
    env = {}
    if ENV_FILE.exists():
        try:
            for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
        except Exception:
            pass
    return env

ENV = load_env()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or ENV.get("GEMINI_API_KEY", "")

# Genel medya akışlarında yalnızca havayolu/havacılık bağlamı olan başlıkları
# kabul ederiz. Resmi havayolu kanalları ise kaynak doğrulaması sayesinde
# başlıkta "airline" kelimesi geçmese bile (ör. finansal sonuç duyurusu)
# kabul edilebilir.
AIRLINE_RELEVANCE_TERMS = (
    "airline", "airlines", "airways", "carrier", "aviation", "havayolu",
    "havacılık", "uçuş", "flight", "route", "rota", "fleet", "filo",
    "aircraft", "uçak", "passenger", "yolcu", "cargo", "kargo", "airport",
    "havalimanı", "airspace", "hava sahası", "runway", "pist", "slot",
    "capacity", "kapasite", "traffic", "load factor", "yield", "fare",
    "revenue", "earnings", "profit", "order", "delivery", "teslimat",
    "grounded", "maintenance", "bakım", "pilot", "crew", "strike", "grev",
    "schedule", "tarife", "codeshare", "alliance", "ittifak", "merger",
    "acquisition", "birleşme", "satın alma", "bankruptcy", "iflas", "faa",
    "easa", "iata", "icao", "jet fuel", "jet yakıt", "saf", "baggage",
    "bagaj", "delay", "gecikme", "cancellation", "iptal", "diversion",
    "safety", "emniyet", "security", "güvenlik", "a320", "a321", "a330",
    "a350", "a380", "737", "747", "767", "777", "787", "e190", "embraer",
    "airbus", "boeing",
)

TOPIC_TERMS = {
    "airline_operations": ("flight", "uçuş", "schedule", "tarife", "delay", "gecikme", "cancellation", "iptal", "crew", "pilot", "bakım", "maintenance"),
    "route_network": ("route", "rota", "destination", "uçuş ağı", "hub", "slot", "codeshare", "alliance", "ittifak"),
    "fleet": ("fleet", "filo", "aircraft", "uçak", "a320", "a321", "a330", "a350", "a380", "737", "747", "767", "777", "787", "e190", "airbus", "boeing", "embraer"),
    "orders_deliveries": ("order", "sipariş", "delivery", "teslimat", "backlog", "purchase", "satın"),
    "finance_investor": ("earnings", "revenue", "gelir", "profit", "kâr", "loss", "zarar", "investor", "yatırımcı", "results", "sonuç", "dividend", "temettü"),
    "regulation_safety": ("faa", "easa", "iata", "icao", "safety", "emniyet", "security", "güvenlik", "regulation", "düzenleme", "incident", "kaza"),
    "airports_airspace": ("airport", "havalimanı", "airspace", "hava sahası", "runway", "pist", "terminal", "atc", "air traffic"),
    "fuel_sustainability": ("jet fuel", "jet yakıt", "saf", "sustainable aviation", "sürdürülebilir", "emissions", "karbon"),
    "labor": ("pilot", "crew", "çalışan", "işçi", "union", "sendika", "strike", "grev", "job", "istihdam"),
    "partnerships_ma": ("partnership", "ortaklık", "codeshare", "alliance", "merger", "birleşme", "acquisition", "satın alma", "stake", "hisse"),
}


def _env_value(name):
    """Read a deployment variable, falling back to the shared local .env."""
    return os.environ.get(name) or ENV.get(name, "")


def _source_record(name, url, category_hint, source_type="trade_media", **metadata):
    return {
        "category_hint": category_hint,
        "name": name,
        "url": url.strip() if isinstance(url, str) else "",
        "source_type": source_type if source_type in SOURCE_TYPES else "trade_media",
        "official": source_type in {"airline_ir", "airline_newsroom", "official_social"},
        **metadata,
    }


def _configured_source_records():
    """Load licensed/API feeds without committing secrets or provider URLs."""
    records = []
    for env_name, display_name, source_type in (
        ("REUTERS_AVIATION_RSS_URL", "Reuters Aviation", "mainstream"),
        ("FT_AVIATION_RSS_URL", "Financial Times Aviation", "mainstream"),
        ("BLOOMBERG_AVIATION_RSS_URL", "Bloomberg Aviation", "mainstream"),
    ):
        url = _env_value(env_name)
        if url:
            records.append(_source_record(
                display_name,
                url,
                "European and other global airlines",
                source_type,
                license_required=True,
            ))

    # AIRLINE_BRIEFING_SOURCES_JSON; örnek biçim README'de açıklanmıştır.
    # Böylece yüzlerce resmi feed Vercel env üzerinden kod değişmeden eklenebilir.
    raw_registry = _env_value("AIRLINE_BRIEFING_SOURCES_JSON")
    if raw_registry:
        try:
            parsed_registry = json.loads(raw_registry)
        except (TypeError, json.JSONDecodeError) as exc:
            print(f"AIRLINE_BRIEFING_SOURCES_JSON okunamadı: {exc}")
            parsed_registry = []
        if isinstance(parsed_registry, list):
            for record in parsed_registry:
                if not isinstance(record, dict):
                    continue
                name = record.get("name")
                url = record.get("url")
                if not isinstance(name, str) or not isinstance(url, str) or not url.strip():
                    continue
                records.append(_source_record(
                    name,
                    url,
                    str(record.get("category_hint") or "European and other global airlines"),
                    str(record.get("source_type") or "airline_newsroom"),
                    airline=str(record.get("airline") or ""),
                    airline_code=str(record.get("airline_code") or ""),
                    official=True,
                    license_required=bool(record.get("license_required", False)),
                ))
    return records


def normalize_article_text(*values):
    return " ".join(str(value or "") for value in values).casefold()


def classify_topics(text):
    normalized = normalize_article_text(text)
    return [topic for topic, terms in TOPIC_TERMS.items() if any(term in normalized for term in terms)]


def is_airline_relevant(title, description="", source=None):
    """Reject generic/non-airline stories before they reach the model."""
    source = source if isinstance(source, dict) else {}
    normalized = normalize_article_text(title, description)
    if source.get("official") and source.get("source_type") in {"airline_ir", "airline_newsroom"}:
        return True
    return any(term in normalized for term in AIRLINE_RELEVANCE_TERMS)

def get_rss_sources(max_hours=48):
    """Return the built-in and deployment-configured airline source registry."""
    sources = [
        # 1. Turkey / THY and Turkish aviation
        _source_record("HavaHaber", "https://havahaber.com/feed/", "Turkey / THY and Turkish aviation"),
        _source_record("Tolga Özbek Havacılık", "https://tolgaozbek.com/feed/", "Turkey / THY and Turkish aviation"),
        _source_record("Yahoo Finance (THY & Pegasus)", "https://feeds.finance.yahoo.com/rss/2.0/headline?s=THYAO.IS,PGSUS.IS", "Turkey / THY and Turkish aviation", "mainstream"),
        # 2. European and other global airlines
        _source_record("Simple Flying", "https://simpleflying.com/feed/", "European and other global airlines"),
        _source_record("FlightGlobal", "https://www.flightglobal.com/rss", "European and other global airlines"),
        _source_record("AeroTime", "https://www.aerotime.aero/feed", "European and other global airlines"),
        _source_record("Aviation24", "https://www.aviation24.be/feed/", "European and other global airlines"),
        # 3. Route news & Fleet
        _source_record("AirDataNews", "https://www.airdatanews.com/feed/", "Route news"),
        _source_record("Flightradar24", "https://www.flightradar24.com/blog/feed/", "Route news"),
        # 4. Other areas (Market & Industry)
        _source_record("Yahoo Finance Aviation", "https://feeds.finance.yahoo.com/rss/2.0/headline?s=LHA.DE,AF.PA,IAG.L,AAL,DAL,BA,AIR.PA", "Other areas", "mainstream"),
    ]
    sources.extend(_configured_source_records())
    return [source for source in sources if source.get("url")]

def clean_html(raw_html):
    """HTML etiketlerini temizler."""
    if not raw_html:
        return ""
    clean = re.sub(r'<.*?>', '', raw_html)
    return " ".join(clean.split()).strip()


def _local_name(tag):
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(element, names):
    wanted = set(names)
    for child in list(element):
        if _local_name(child.tag) not in wanted:
            continue
        value = "".join(child.itertext()).strip()
        if value:
            return value
    return ""


def parse_feed_entries(content):
    """Parse both RSS 2.0 and Atom without an additional dependency."""
    root = ET.fromstring(content)
    root_name = _local_name(root.tag)
    if root_name == "rss":
        channel = next((child for child in list(root) if _local_name(child.tag) == "channel"), None)
        return [child for child in list(channel) if _local_name(child.tag) == "item"] if channel is not None else []
    if root_name == "feed":
        return [child for child in list(root) if _local_name(child.tag) == "entry"]
    return []


def entry_values(entry):
    title = _child_text(entry, {"title"})
    description = _child_text(entry, {"description", "summary", "content"})
    link = _child_text(entry, {"link"})
    if not link:
        for child in list(entry):
            if _local_name(child.tag) == "link" and child.attrib.get("href"):
                link = child.attrib["href"].strip()
                break
    pub_date = _child_text(entry, {"pubdate", "published", "updated", "date", "issued"})
    return title, link, clean_html(description), pub_date


def canonicalize_url(value):
    parsed = urllib.parse.urlsplit(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(key, val) for key, val in query if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}]
    normalized_query = urllib.parse.urlencode(query)
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/") or "/", normalized_query, ""))


def parse_published_datetime(value):
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def fetch_rss_items(max_hours=48):
    """Fetch recent airline-relevant entries from RSS/Atom source records."""
    articles = []
    seen_links = set()
    now = utc_now()
    cutoff = now - timedelta(hours=max_hours)
    
    ctx = ssl.create_default_context()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    sources = get_rss_sources(max_hours)

    for source in sources:
        try:
            req = urllib.request.Request(source["url"], headers=headers)
            with urllib.request.urlopen(req, context=ctx, timeout=12) as response:
                content = response.read()
                entries = parse_feed_entries(content)

                for item in entries[:20]:
                    title, link, description, pub_date = entry_values(item)
                    
                    if not title or not link:
                        continue

                    if not is_airline_relevant(title, description, source):
                        continue

                    canonical_link = canonicalize_url(link)
                    if not canonical_link or canonical_link in seen_links:
                        continue
                    seen_links.add(canonical_link)
                    
                    # Tarih filtreleme
                    pub_ts = time.time()
                    pub_str = ""
                    if pub_date:
                        dt = parse_published_datetime(pub_date)
                        if dt:
                            if dt < cutoff:
                                continue  # Eski haberi atla
                            pub_ts = dt.timestamp()
                            pub_str = dt.strftime("%d %b %H:%M")
                    
                    # Başlıktaki kaynak ismini ayır
                    source_name = source["name"]
                    if " - " in title:
                        parts = title.rsplit(" - ", 1)
                        title = parts[0].strip()
                        source_name = parts[1].strip()
                        
                    articles.append({
                        "title": title,
                        "link": link,
                        "description": description,
                        "source": source_name,
                        "category_hint": source["category_hint"],
                        "source_type": source.get("source_type", "trade_media"),
                        "official": bool(source.get("official", False)),
                        "airline": source.get("airline", ""),
                        "airline_code": source.get("airline_code", ""),
                        "license_required": bool(source.get("license_required", False)),
                        "topics": classify_topics(f"{title} {description}"),
                        "pub_date": pub_str,
                        "timestamp": pub_ts
                    })
        except Exception as e:
            print(f"[{source['name']}] RSS çekme hatası: {e}")
            
    # En taze haberler en üstte
    articles.sort(key=lambda a: a.get("timestamp", 0), reverse=True)
    return articles

def generate_briefing_with_gemini(articles, mode="daily"):
    """Gemini 2.5 Flash ile haberleri prompt kurallarına göre analiz eder."""
    mode = validate_mode(mode)
    if not GEMINI_API_KEY:
        print("Uyarı: GEMINI_API_KEY bulunamadı; yalnız kaynak özetleri gösterilecek.")
        return fallback_briefing(
            articles,
            mode,
            "AI analysis is unavailable because the API key is not configured.",
        )

    sample_articles = articles[:12]
    # Sadece başlık, kaynak, yayın saati ve kısa açıklamayı göndererek token ve süre tasarrufu sağla
    compact_articles = [
        {
            "title": a["title"],
            "source": a["source"],
            "source_type": a.get("source_type", "trade_media"),
            "official": bool(a.get("official", False)),
            "airline": a.get("airline", ""),
            "topics": a.get("topics", []),
            "published_at": a.get("pub_date", ""),
            "category_hint": a.get("category_hint", ""),
            "description": a["description"][:200] if a.get("description") else "",
            "link": a["link"]
        }
        for a in sample_articles
    ]
    if not compact_articles:
        return fallback_briefing([], mode)

    now = utc_now()
    today_str = now.strftime('%d %B %Y')

    prompt_mode_instructions = f"""
Mode: DAILY (Last 48 Hours)
- Today is {today_str}.
- STRONGLY prioritize the freshest breaking news published today and in the last 24-48 hours.
- Discard any outdated, historical or stale news items.
- Detailed Analysis: 4 to 6 short, punchy bullet points per story.
- Include data points, strategic implications, capacity / demand / revenue effects, competition effects, and operational outcomes whenever possible.
- Explicitly cover the effect on Turkish Airlines (THY) within analysis bullets where relevant.
""" if mode == "daily" else f"""
Mode: HOURLY (Last 1-2 Hours)
- Today is {today_str}.
- Shorter analysis: 2 to 3 short bullets under Detailed Analysis.
- Include only genuinely new, breaking developments from the current hourly window.
"""

    system_prompt = f"""
You are an expert aviation industry analyst creating an essential daily briefing for airline employees and aviation professionals (pilots, cabin managers, dispatchers, network planners, revenue managers, engineers, and aviation specialists).
Your task is to take the provided verified news items and compile an up-to-the-minute Aviation Intelligence Briefing adhering strictly to institutional analysis standards.
Today's date is {today_str}. All analysis must reflect the freshest verified information.
STRICT SCOPE: Include only airline, air transport, airport/airspace, aircraft fleet, route network, airline finance/investor, airline labor, safety/regulation, fuel/sustainability, or airline partnership/M&A developments. Exclude unrelated general business, politics, defense, space, technology, or tourism stories even when they come from a mainstream source. Preserve the supplied official/mainstream source metadata and never invent an original source.

Required Sections (Strict Order):
1. `Turkey / THY and Turkish aviation`
2. `European and other global airlines`
3. `Route news`
4. `Other areas`

Each Story Block Structure:
- `id`: unique slug e.g. "story-1", "story-2"
- `section`: One of the 4 exact section names above.
- `headline`: One concise, impactful executive headline.
- `published_at`: Publication timestamp from the supplied source item.
- `lead`: 1 short executive lead paragraph.
- `detailed_analysis`: Array of strings (4-6 bullets for daily, 2-3 for hourly). Include strategy, capacity, demand, revenue, fleet, competition.
- `data_points`: Array of strings with concrete numerical data (e.g. capacity, frequency, revenue, passengers, ASK, RPK, load factor, delivery count). Leave EMPTY array if no concrete numerical data exists in the story.
- `strategic_impact`: High-level executive strategic and commercial assessment (revenue, operational costs, network implications, capacity shifts, or fleet modernization).
- `market_exposure`: Array of objects detailing affected carriers or key market stakeholders with their impact tag, e.g.:
  [
    {{"carrier": "Turkish Airlines (THY)", "impact": "Positive", "details": "Benefits from enhanced hub connectivity and transfer traffic."}},
    {{"carrier": "European Legacy Carriers", "impact": "Competitive Headwind", "details": "Increased transfer pressure on long-haul routes."}}
  ]
- `thy_impact_assessment`: Assessment from Turkish Airlines' (THY) perspective (impact on revenue, cost, competition, route network, fleet, demand, operations, or brand). State honestly if direct impact is weak.
- `why_it_matters`: Single consequence-focused sentence discussing impact only through market impact, security risk, financial impact, or operational change.
- `original_source`: {{"title": "Article Title", "source_name": "publisher name", "url": "direct real url"}}
- `related_news`: Array of strings (optional, can be empty).
(Do NOT include any numerical risk score).

{prompt_mode_instructions}

Return pure JSON matching this schema:
{{
  "mode": "{mode}",
  "date_str": "{now.strftime('%d %B %Y')}",
  "time_str": "{now.strftime('%H:%M UTC')}",
  "heading": "{'Aviation Briefing | ' + now.strftime('%d %B %Y') if mode == 'daily' else 'Aviation Update | ' + now.strftime('%d %B %Y %H:%M UTC')}",
  "intro_sentence": "{'Below is a summary of the most important verified aviation developments from the last 48 hours.' if mode == 'daily' else 'Below is a summary of the most important newly verified or strongly supported aviation developments for the current hourly window.'}",
  "stories": [
    ...
  ]
}}
Ensure stories are grouped by the 4 required sections in order. Select 6 to 10 of the most strategic stories.
"""

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": system_prompt},
                    {"text": "RAW NEWS ARTICLES TO ANALYZE:\n" + json.dumps(compact_articles, ensure_ascii=False, indent=2)}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json"
        }
    }

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY,
        }
    )
    
    ctx = ssl.create_default_context()

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data["candidates"][0]["content"]["parts"][0]["text"]
            briefing = json.loads(content)
            article_metadata = {
                canonicalize_url(article.get("link")): article
                for article in articles
                if canonicalize_url(article.get("link"))
            }
            normalized = normalize_generated_briefing(briefing, mode, article_metadata)
            if not normalized["stories"] and articles:
                return fallback_briefing(
                    articles,
                    mode,
                    "AI output did not reference the approved source items; source headlines are shown instead.",
                )
            return normalized
    except Exception as e:
        print(f"Gemini API hatası ({e}); yalnız kaynak özetleri gösterilecek.")
        return fallback_briefing(
            articles,
            mode,
            "AI analysis could not be generated; source summaries are shown instead.",
        )

def safe_source_url(value):
    if not isinstance(value, str):
        return ""
    parsed = urllib.parse.urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return value.strip()


def stable_story_id(source_url, headline, fallback_index):
    """Keep the same story addressable across daily and hourly briefings."""
    identity = str(source_url or headline or f"story-{fallback_index}").strip().lower()
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]
    return f"story-{digest}"


def text_list(value):
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def normalize_generated_briefing(briefing, mode, article_metadata=None):
    """Keep model output within the public JSON contract."""
    if not isinstance(briefing, dict) or not isinstance(briefing.get("stories"), list):
        raise ValueError("Gemini returned an invalid briefing payload")

    stories = []
    for index, raw_story in enumerate(briefing["stories"][:10], start=1):
        if not isinstance(raw_story, dict):
            continue
        source = raw_story.get("original_source")
        source = source if isinstance(source, dict) else {}
        section = raw_story.get("section")
        if section not in SECTION_ORDER:
            section = "Other areas"

        exposure = []
        raw_exposures = raw_story.get("market_exposure", [])
        if isinstance(raw_exposures, list):
            for raw_exposure in raw_exposures:
                if not isinstance(raw_exposure, dict):
                    continue
                exposure.append({
                    "carrier": str(raw_exposure.get("carrier", "Stakeholder")),
                    "impact": str(raw_exposure.get("impact", "Neutral")),
                    "details": str(raw_exposure.get("details", "")),
                })

        source_url = safe_source_url(source.get("url"))
        source_article = (article_metadata or {}).get(canonicalize_url(source_url), {})
        if article_metadata is not None and (not source_url or not source_article):
            # Model output must point to an item we actually fetched; this
            # prevents unrelated/hallucinated stories from entering the feed.
            continue
        normalized_source_type = source_article.get("source_type") or source.get("source_type") or "trade_media"
        if normalized_source_type not in SOURCE_TYPES:
            normalized_source_type = "trade_media"
        stories.append({
            "id": stable_story_id(source.get("url"), raw_story.get("headline"), index),
            "section": section,
            "headline": str(raw_story.get("headline", "Untitled aviation update")),
            "published_at": str(raw_story.get("published_at", "")),
            "lead": str(raw_story.get("lead", "")),
            "detailed_analysis": text_list(raw_story.get("detailed_analysis")),
            "data_points": text_list(raw_story.get("data_points")),
            "strategic_impact": str(raw_story.get("strategic_impact", "")),
            "market_exposure": exposure,
            "thy_impact_assessment": str(raw_story.get("thy_impact_assessment", "")),
            "why_it_matters": str(raw_story.get("why_it_matters", "")),
            "original_source": {
                "title": str(source.get("title", "Read full article")),
                "source_name": str(source.get("source_name", "")),
                "url": source_url,
                "source_type": normalized_source_type,
                "official": bool(source_article.get("official", source.get("official", False))),
                "airline": str(source_article.get("airline", source.get("airline", ""))),
                "topics": source_article.get("topics", source.get("topics", [])),
                "license_required": bool(source_article.get("license_required", source.get("license_required", False))),
            },
            "related_news": text_list(raw_story.get("related_news")),
        })

    return build_briefing_payload(mode, stories, status="ok")


def build_briefing_payload(mode, stories, status, warning=""):
    now = utc_now()
    date_str = now.strftime("%d %B %Y")
    time_str = now.strftime("%H:%M UTC")
    is_verified_daily = status == "ok" and mode == "daily"
    intro_sentence = (
        "Below is a summary of the most important verified aviation developments from the last 48 hours."
        if is_verified_daily
        else "Below is the latest available aviation source feed."
    )
    return {
        "mode": mode,
        "source_policy": SOURCE_POLICY_VERSION,
        "date_str": date_str,
        "time_str": time_str,
        "heading": f"Aviation Briefing | {date_str}" if mode == "daily" else f"Aviation Update | {date_str} {time_str}",
        "intro_sentence": intro_sentence,
        "stories": stories,
        "status": status,
        "warning": warning,
        "generated_at": now.isoformat(),
    }


def fallback_briefing(articles, mode="daily", warning="AI analysis is unavailable."):
    """Return only real source material when AI analysis cannot be produced."""
    mode = validate_mode(mode)
    stories = []
    for index, article in enumerate(articles[:10], start=1):
        if not isinstance(article, dict):
            continue
        section = article.get("category_hint")
        if section not in SECTION_ORDER:
            section = "Other areas"
        stories.append({
            "id": stable_story_id(article.get("link"), article.get("title"), index),
            "section": section,
            "headline": str(article.get("title", "Untitled aviation update")),
            "published_at": str(article.get("pub_date", "")),
            "lead": str(article.get("description", "")),
            "detailed_analysis": [],
            "data_points": [],
            "strategic_impact": "",
            "market_exposure": [],
            "thy_impact_assessment": "",
            "why_it_matters": "",
            "original_source": {
                "title": str(article.get("title", "Read full article")),
                "source_name": str(article.get("source", "")),
                "url": safe_source_url(article.get("link")),
                "source_type": article.get("source_type", "trade_media"),
                "official": bool(article.get("official", False)),
                "airline": str(article.get("airline", "")),
                "topics": article.get("topics", []),
                "license_required": bool(article.get("license_required", False)),
            },
            "related_news": [],
        })
    status = "degraded" if stories else "unavailable"
    return build_briefing_payload(mode, stories, status=status, warning=warning)

def get_briefing(mode="daily", force_refresh=False):
    """Önbellekteki brifingi döndürür veya yenisini üretir."""
    mode = validate_mode(mode)
    cache_path = CACHE_FILE_HOURLY if mode == "hourly" else CACHE_FILE_DAILY
    
    if not force_refresh and cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                gen_time = datetime.fromisoformat(data.get("generated_at", "2000-01-01T00:00:00"))
                if gen_time.tzinfo is None:
                    gen_time = gen_time.astimezone()
                max_age = timedelta(minutes=10 if mode == "hourly" else 30)
                cache_is_valid = (
                    data.get("mode") == mode
                    and data.get("status") in {"ok", "degraded", "unavailable"}
                    and data.get("source_policy") == SOURCE_POLICY_VERSION
                )
                cache_age = utc_now() - gen_time.astimezone(timezone.utc)
                if cache_is_valid and cache_age < max_age:
                    return data
        except Exception as e:
            print(f"Önbellek okuma hatası ({cache_path.name}): {e}")

    print(f"Havacılık haberleri toplanıyor (Mod: {mode})...")
    articles = fetch_rss_items(max_hours=48 if mode == "daily" else 2)
    print(f"{len(articles)} haber maddesi toplandı. Analiz ediliyor...")
    briefing = generate_briefing_with_gemini(articles, mode=mode)
    
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(briefing, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Önbellek yazma hatası: {e}")
        
    return briefing

if __name__ == "__main__":
    print("Aviation Briefing Engine test ediliyor...")
    res = get_briefing(mode="daily", force_refresh=True)
    print(f"Başarılı! {len(res['stories'])} haber oluşturuldu.")
    print("Başlık:", res["heading"])
    for s in res["stories"]:
        print(f" - [{s['section']}] {s['headline']}")
