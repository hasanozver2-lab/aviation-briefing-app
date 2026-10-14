"""
Aviation Briefing Engine
Havacılık haberlerini RSS kaynaklarından toplar, Gemini 2.5 Flash ile analiz eder
ve executive brifing JSON çıktısını üretir.
"""

import os
import sys
import re
import json
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

def get_rss_sources(max_hours=48):
    """Doğrudan yayıncı sitelerinin (Simple Flying, HavaHaber, FlightGlobal, AeroTime vb.) gerçek linkli RSS akışları."""
    return [
        # 1. Turkey / THY and Turkish aviation
        {
            "category_hint": "Turkey / THY and Turkish aviation",
            "name": "HavaHaber",
            "url": "https://havahaber.com/feed/"
        },
        {
            "category_hint": "Turkey / THY and Turkish aviation",
            "name": "Tolga Özbek Havacılık",
            "url": "https://tolgaozbek.com/feed/"
        },
        {
            "category_hint": "Turkey / THY and Turkish aviation",
            "name": "Yahoo Finance (THY & Pegasus)",
            "url": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=THYAO.IS,PGSUS.IS"
        },
        # 2. European and other global airlines
        {
            "category_hint": "European and other global airlines",
            "name": "Simple Flying",
            "url": "https://simpleflying.com/feed/"
        },
        {
            "category_hint": "European and other global airlines",
            "name": "FlightGlobal",
            "url": "https://www.flightglobal.com/rss"
        },
        {
            "category_hint": "European and other global airlines",
            "name": "AeroTime",
            "url": "https://www.aerotime.aero/feed"
        },
        {
            "category_hint": "European and other global airlines",
            "name": "Aviation24",
            "url": "https://www.aviation24.be/feed/"
        },
        # 3. Route news & Fleet
        {
            "category_hint": "Route news",
            "name": "AirDataNews",
            "url": "https://www.airdatanews.com/feed/"
        },
        {
            "category_hint": "Route news",
            "name": "Flightradar24",
            "url": "https://www.flightradar24.com/blog/feed/"
        },
        # 4. Other areas (Market & Industry)
        {
            "category_hint": "Other areas",
            "name": "Yahoo Finance Aviation",
            "url": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=LHA.DE,AF.PA,IAG.L,AAL,DAL,BA,AIR.PA"
        }
    ]

def clean_html(raw_html):
    """HTML etiketlerini temizler."""
    if not raw_html:
        return ""
    clean = re.sub(r'<.*?>', '', raw_html)
    return " ".join(clean.split()).strip()

def fetch_rss_items(max_hours=48):
    """Doğrudan yayıncı RSS kaynaklarından son haberleri çeker ve en yeniden eskiye sıralar."""
    articles = []
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
                root = ET.fromstring(content)
                
                channel = root.find("channel")
                if channel is None:
                    continue
                
                for item in channel.findall("item")[:10]:
                    title = item.findtext("title", "").strip()
                    link = item.findtext("link", "").strip()
                    description = clean_html(item.findtext("description", ""))
                    pub_date = item.findtext("pubDate", "")
                    
                    if not title or not link:
                        continue
                    
                    # Tarih filtreleme
                    pub_ts = time.time()
                    pub_str = ""
                    if pub_date:
                        try:
                            dt = parsedate_to_datetime(pub_date)
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            if dt < cutoff:
                                continue  # Eski haberi atla
                            pub_ts = dt.timestamp()
                            pub_str = dt.strftime("%d %b %H:%M")
                        except Exception:
                            pass
                    
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

Required Sections (Strict Order):
1. `Turkey / THY and Turkish aviation`
2. `European and other global airlines`
3. `Route news`
4. `Other areas`

Each Story Block Structure:
- `id`: unique slug e.g. "story-1", "story-2"
- `section`: One of the 4 exact section names above.
- `headline`: One concise, impactful executive headline.
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
            return normalize_generated_briefing(briefing, mode)
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


def text_list(value):
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def normalize_generated_briefing(briefing, mode):
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

        stories.append({
            "id": f"story-{index}",
            "section": section,
            "headline": str(raw_story.get("headline", "Untitled aviation update")),
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
                "url": safe_source_url(source.get("url")),
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
            "id": f"story-{index}",
            "section": section,
            "headline": str(article.get("title", "Untitled aviation update")),
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
