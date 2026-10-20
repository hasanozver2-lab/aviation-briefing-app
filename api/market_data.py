"""Deterministic market data, taxonomy, and local SQLite event helpers."""

import csv
import io
import json
import math
import os
import re
import sqlite3
import statistics
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

try:
    from . import text_match
except ImportError:
    import text_match


BASE_DIR = Path(__file__).resolve().parent.parent
MARKET_CONFIG_PATH = BASE_DIR / "config" / "market_indicators.json"
TAXONOMY_CONFIG_PATH = BASE_DIR / "config" / "event_taxonomy.json"
MIGRATION_PATH = BASE_DIR / "migrations" / "002_market_data.sql"
DEFAULT_DATABASE_PATH = BASE_DIR / "data" / "pipeline.sqlite3"
EIA_SPOT_ENDPOINT = "https://api.eia.gov/v2/petroleum/pri/spt/data/"
FRED_OBSERVATIONS_ENDPOINT = "https://api.stlouisfed.org/fred/series/observations"
FRED_GRAPH_CSV_ENDPOINT = "https://fred.stlouisfed.org/graph/fredgraph.csv"
YAHOO_BRENT_ENDPOINT = "https://query1.finance.yahoo.com/v8/finance/chart/BZ=F"
FUEL_SERIES = ("brent_spot", "us_gulf_coast_jet_fuel")
GALLONS_PER_BARREL = 42
ECB_EXR_ENDPOINT = "https://data-api.ecb.europa.eu/service/data/EXR"
IATA_FUEL_MONITOR_URL = "https://www.iata.org/en/publications/economics/fuel-monitor/"
IATA_CACHE_PATH = BASE_DIR / "data" / "iata_fuel_cache.json"
FX_CURRENCIES = ("EUR", "GBP", "JPY", "CNY", "INR", "TRY", "BRL")
MISSING_FUEL_NOTE = "Brent ve ABD Körfez Kıyısı jet yakıtı göstergeleri bu yayında yok: EIA anahtarı tanımlı değil ve FRED'e ulaşılamadı."
FUEL_CONTEXT_TERMS = text_match.TermSet(["jet fuel", "yakıt*", "brent", "oil", "petrol*"], allow_plural=True)


def utc_now():
    return datetime.now(timezone.utc)


def database_path(path=None):
    configured_path = os.environ.get("MARKET_DB_PATH", "").strip()
    return Path(path or configured_path or DEFAULT_DATABASE_PATH)


def load_json_config(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_market_config():
    return load_json_config(MARKET_CONFIG_PATH)


def load_taxonomy_config():
    return load_json_config(TAXONOMY_CONFIG_PATH)


def migrate_market_database(path=None):
    target = database_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
    return target


def _json_request(url, headers=None, timeout=20):
    request = urllib.request.Request(url, headers=headers or {"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _text_request(url, headers=None, timeout=20):
    request = urllib.request.Request(url, headers=headers or {"Accept": "text/csv"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def eia_series_url(series_id, api_key, start_date, end_date):
    query = urllib.parse.urlencode({
        "api_key": api_key,
        "frequency": "daily",
        "data[0]": "value",
        "facets[series][]": series_id,
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "length": 5000,
    })
    return f"{EIA_SPOT_ENDPOINT}?{query}"


def fetch_eia_series(series_id, api_key, start_date, end_date):
    """Return EIA daily observations, preserving the supplied EIA series identifier."""
    if not api_key:
        raise RuntimeError("EIA_API_KEY is required to fetch EIA market data")
    payload = _json_request(eia_series_url(series_id, api_key, start_date, end_date))
    rows = payload.get("response", {}).get("data", [])
    observations = []
    for row in rows:
        try:
            observed_on = date.fromisoformat(str(row["period"]))
            value = float(row["value"])
        except (KeyError, TypeError, ValueError):
            continue
        observations.append((observed_on, value))
    return sorted(observations)


def _parse_fred_value(raw):
    """FRED marks missing days with '.'; those are skipped rather than stored."""
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def fetch_fred_series_with_key(series_id, api_key, start_date, end_date):
    query = urllib.parse.urlencode({
        "series_id": series_id, "api_key": api_key, "file_type": "json",
        "observation_start": start_date.isoformat(), "observation_end": end_date.isoformat(),
    })
    payload = _json_request(f"{FRED_OBSERVATIONS_ENDPOINT}?{query}")
    rows = [(row.get("date"), _parse_fred_value(row.get("value"))) for row in payload.get("observations", [])]
    return _fred_rows(rows)


def fetch_fred_series_keyless(series_id, start_date, end_date):
    query = urllib.parse.urlencode({"id": series_id, "cosd": start_date.isoformat(), "coed": end_date.isoformat()})
    reader = csv.reader(io.StringIO(_text_request(f"{FRED_GRAPH_CSV_ENDPOINT}?{query}")))
    next(reader, None)  # header
    return _fred_rows([(row[0], _parse_fred_value(row[1])) for row in reader if len(row) >= 2])


def _fred_rows(rows):
    observations = []
    for raw_date, value in rows:
        if value is None:
            continue
        try:
            observations.append((date.fromisoformat(str(raw_date)), value))
        except ValueError:
            continue
    return sorted(observations)


def fetch_fred_series(series_id, api_key, start_date, end_date):
    """FRED observations: the keyed API when a key is set, the keyless CSV otherwise or when the keyed call fails.

    Exceptions are never formatted with the request URL, so the key cannot reach a log through here.
    """
    if str(api_key or "").strip():
        try:
            return fetch_fred_series_with_key(series_id, api_key, start_date, end_date)
        except Exception:
            pass
    return fetch_fred_series_keyless(series_id, start_date, end_date)


def fetch_live_brent(timeout=8):
    """Fetch recent daily closing observations for Brent Crude Futures (BZ=F) from Yahoo Finance.

    Returns a list of (date, value) tuples sorted by date. On any network or parsing failure,
    returns an empty list so callers safely fall back to retrospective FRED/EIA data.
    """
    url = f"{YAHOO_BRENT_ENDPOINT}?range=1mo&interval=1d"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    try:
        payload = _json_request(url, headers=headers, timeout=timeout)
        result = payload.get("chart", {}).get("result", [])
        if not result:
            return []
        item = result[0]
        timestamps = item.get("timestamp", [])
        quotes = item.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        observations = []
        for ts, close in zip(timestamps, quotes):
            if close is None:
                continue
            obs_date = datetime.fromtimestamp(ts, tz=timezone.utc).date()
            observations.append((obs_date, round(float(close), 2)))
        return sorted(observations)
    except Exception:
        return []


def parse_iata_week_ending(raw_str):
    raw = str(raw_str).strip()
    for fmt in ("%d %b %Y", "%d %B %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})", raw)
    if m:
        day, month_str, year = m.groups()
        for fmt in ("%d %b %Y", "%d %B %Y"):
            try:
                return datetime.strptime(f"{day} {month_str} {year}", fmt).date().isoformat()
            except ValueError:
                pass
    return utc_now().date().isoformat()


def get_cached_iata_fuel_data():
    if not IATA_CACHE_PATH.exists():
        return None
    try:
        return json.loads(IATA_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_iata_fuel_data(data):
    try:
        IATA_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        IATA_CACHE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def fetch_iata_fuel_monitor(gemini_api_key="", timeout=10):
    """Fetch official weekly Jet Fuel Price and Crack Spread from IATA's Fuel Monitor page.

    Combines HTML headline parsing and multimodal table parsing (when Gemini key is available),
    caching successful results in data/iata_fuel_cache.json. Gracefully falls back to cache on any error.
    """
    cached = get_cached_iata_fuel_data()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    extracted = None
    try:
        req = urllib.request.Request(IATA_FUEL_MONITOR_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        headline_price = None
        headline_match = re.search(r"global average jet fuel price.*?to\s*\$?([0-9]+\.?[0-9]*)/bbl", html, re.I)
        if headline_match:
            try:
                headline_price = float(headline_match.group(1))
            except ValueError:
                pass

        img_match = re.search(r'src=["\']([^"\']*fuel_price_analysis[^"\']*)["\']', html, re.I)
        img_url = img_match.group(1) if img_match else ""
        if img_url and img_url.startswith("/"):
            img_url = "https://www.iata.org" + img_url

        if img_url and gemini_api_key:
            try:
                import base64
                img_req = urllib.request.Request(img_url, headers=headers)
                with urllib.request.urlopen(img_req, timeout=timeout) as img_resp:
                    img_bytes = img_resp.read()
                b64 = base64.b64encode(img_bytes).decode("utf-8")
                prompt = (
                    "Analyze this IATA Fuel Price Analysis table image. Return a JSON object with: "
                    "week_ending (string, e.g. '16 Oct 2026'), "
                    "jet_fuel_price_bbl (number, in $/bbl for global Jet fuel price), "
                    "brent_price_bbl (number, Oil Price Dated Brent in $/bbl), "
                    "crack_spread_bbl (number, Crack Spread in $/bbl), "
                    "weekly_change_pct (number, Crack spread prior week change %). "
                    "Only return valid JSON."
                )
                payload = {
                    "contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": b64}}]}],
                    "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"},
                }
                greq = urllib.request.Request(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_api_key}",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(greq, timeout=timeout) as gresp:
                    gres = json.loads(gresp.read().decode("utf-8"))
                    cand = gres.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    parsed = json.loads(cand)
                    if "crack_spread_bbl" in parsed:
                        as_of_iso = parse_iata_week_ending(parsed.get("week_ending", ""))
                        extracted = {
                            "as_of": as_of_iso,
                            "week_ending": parsed.get("week_ending", ""),
                            "jet_fuel_price_bbl": float(parsed.get("jet_fuel_price_bbl", 0)),
                            "brent_price_bbl": float(parsed.get("brent_price_bbl", 0)),
                            "crack_spread_bbl": float(parsed["crack_spread_bbl"]),
                            "weekly_pct": float(parsed.get("weekly_change_pct", 0)),
                            "source": "IATA / Platts Jet Fuel Price Monitor",
                            "updated_at": utc_now().isoformat(),
                        }
                        save_iata_fuel_data(extracted)
            except Exception:
                pass

        if not extracted and headline_price and cached:
            extracted = dict(cached)
            extracted["jet_fuel_price_bbl"] = headline_price

    except Exception:
        pass

    return extracted or cached


def ecb_fx_url(start_date, end_date):
    currencies = "+".join(("USD",) + FX_CURRENCIES[1:])
    key = f"D.{currencies}.EUR.SP00.A"
    query = urllib.parse.urlencode({
        "format": "csvdata",
        "startPeriod": start_date.isoformat(),
        "endPeriod": end_date.isoformat(),
    })
    return f"{ECB_EXR_ENDPOINT}/{key}?{query}"


def _row_value(row, *keys):
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return ""


def fetch_ecb_fx_series(start_date, end_date):
    """Return USD-cross observations calculated from ECB EUR reference rates."""
    csv_payload = _text_request(ecb_fx_url(start_date, end_date))
    euro_rates = {}
    for row in csv.DictReader(io.StringIO(csv_payload)):
        currency = str(_row_value(row, "CURRENCY", "currency")).upper()
        raw_period = str(_row_value(row, "TIME_PERIOD", "TIME PERIOD", "time_period"))
        raw_value = _row_value(row, "OBS_VALUE", "OBS VALUE", "obs_value")
        try:
            observed_on = date.fromisoformat(raw_period)
            rate_per_eur = float(raw_value)
        except ValueError:
            continue
        euro_rates.setdefault(observed_on, {})[currency] = rate_per_eur

    crosses = {f"fx_usd_{currency.lower()}": [] for currency in FX_CURRENCIES}
    for observed_on, rates in euro_rates.items():
        usd_per_eur = rates.get("USD")
        if not usd_per_eur:
            continue
        for currency in FX_CURRENCIES:
            series_id = f"fx_usd_{currency.lower()}"
            if currency == "EUR":
                crosses[series_id].append((observed_on, 1 / usd_per_eur))
                continue
            currency_per_eur = rates.get(currency)
            if currency_per_eur:
                crosses[series_id].append((observed_on, currency_per_eur / usd_per_eur))
    return {series_id: sorted(values) for series_id, values in crosses.items()}


def _fuel_source(series_config, provider):
    return provider_label(provider) if provider else series_config["source"]


def display_fx():
    return bool(load_market_config().get("market", {}).get("display_fx", False))


def is_fx_series(series_id):
    return str(series_id).startswith("fx_usd_")


def apply_display_settings(market):
    """Read-time view of a stored market panel: without display_fx, no fx_usd_* items and no fx events.

    Archives written before the switch (or with it on) still hold FX rows; they are hidden here, not rewritten.
    Also hides us_gulf_coast_jet_fuel from public display.
    Ensures jet_fuel_brent_crack_spread reflects the official IATA / Platts monitor.
    """
    if not isinstance(market, dict):
        return market
    visible = dict(market)
    show_fx = display_fx()
    iata_data = get_cached_iata_fuel_data()
    items = []
    for item in market.get("items", []):
        series_id = item.get("series_id")
        if series_id == "us_gulf_coast_jet_fuel":
            continue
        if not show_fx and is_fx_series(series_id):
            continue
        if series_id == "jet_fuel_brent_crack_spread" and iata_data and "crack_spread_bbl" in iata_data:
            item = dict(item)
            item["value"] = float(iata_data["crack_spread_bbl"])
            item["source"] = iata_data.get("source", "IATA / Platts Jet Fuel Price Monitor")
            item["name"] = "IATA Jet yakıtı - Brent marjı"
            if "as_of" in iata_data:
                item["as_of"] = iata_data["as_of"]
                try:
                    observed_on = date.fromisoformat(iata_data["as_of"])
                    age_days = (utc_now().date() - observed_on).days
                    item["carried_forward"] = age_days > 0
                    item["age_days"] = max(age_days, 0)
                except ValueError:
                    pass
            if "weekly_pct" in iata_data:
                item["changes"] = dict(item.get("changes") or {})
                item["changes"]["weekly_pct"] = float(iata_data["weekly_pct"])
                item["changes"]["daily_pct"] = 0.0
        items.append(item)
    visible["items"] = items
    if not show_fx:
        visible["events"] = [event for event in market.get("events", []) if event.get("event_type") != "fx_currency"]
    return visible


def provider_label(provider):
    return load_market_config()["providers"].get(provider, provider)


def market_series_definitions(provider_by_series=None):
    """provider_by_series ("eia" | "fred" per fuel series) sets the source label of what was actually fetched."""
    config = load_market_config()
    configured_series = config["series"]
    provider_by_series = provider_by_series or {}
    definitions = {
        "brent_spot": {
            "name": configured_series["brent_spot"]["name"],
            "unit": configured_series["brent_spot"]["unit"],
            "source": _fuel_source(configured_series["brent_spot"], provider_by_series.get("brent_spot")),
            "frequency": "daily",
        },
        "us_gulf_coast_jet_fuel": {
            "name": configured_series["us_gulf_coast_jet_fuel"]["name"],
            "unit": configured_series["us_gulf_coast_jet_fuel"]["unit"],
            "source": _fuel_source(configured_series["us_gulf_coast_jet_fuel"], provider_by_series.get("us_gulf_coast_jet_fuel")),
            "frequency": "daily",
        },
    }
    for currency in FX_CURRENCIES:
        definitions[f"fx_usd_{currency.lower()}"] = {
            "name": f"USD karşısında {currency}",
            "unit": f"{currency} per USD",
            "source": "European Central Bank",
            "frequency": "business_daily",
        }
    return definitions


def upsert_observations(path, observations_by_series, fetched_at=None, provider_by_series=None):
    target = migrate_market_database(path)
    definitions = market_series_definitions(provider_by_series)
    fetched_timestamp = (fetched_at or utc_now()).isoformat()
    with sqlite3.connect(target) as connection:
        for series_id, definition in definitions.items():
            connection.execute(
                """
                INSERT INTO market_series (series_id, name, unit, source, frequency)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(series_id) DO UPDATE SET
                    name = excluded.name, unit = excluded.unit, source = excluded.source,
                    frequency = excluded.frequency
                """,
                (series_id, definition["name"], definition["unit"], definition["source"], definition["frequency"]),
            )
        for series_id, observations in observations_by_series.items():
            for observed_on, value in observations:
                connection.execute(
                    """
                    INSERT INTO market_observations (series_id, date, value, fetched_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(series_id, date) DO UPDATE SET
                        value = excluded.value, fetched_at = excluded.fetched_at
                    """,
                    (series_id, observed_on.isoformat(), float(value), fetched_timestamp),
                )
    return target


def load_observations(path, series_id):
    target = database_path(path)
    if not target.exists():
        return []
    with sqlite3.connect(target) as connection:
        rows = connection.execute(
            "SELECT date, value FROM market_observations WHERE series_id = ? ORDER BY date",
            (series_id,),
        ).fetchall()
    return [(date.fromisoformat(row[0]), float(row[1])) for row in rows]


def _latest_on_or_before(observations, target_date):
    matches = [item for item in observations if item[0] <= target_date]
    return matches[-1] if matches else None


def _change_pct(current_value, prior_value):
    if prior_value in (None, 0):
        return None
    return ((current_value - prior_value) / prior_value) * 100


def calculate_series_indicators(observations):
    if not observations:
        return None
    latest_date, latest_value = observations[-1]
    values_52_weeks = [value for observed_on, value in observations if observed_on >= latest_date - timedelta(days=365)]
    low_52_weeks = min(values_52_weeks) if values_52_weeks else None
    high_52_weeks = max(values_52_weeks) if values_52_weeks else None
    range_position = None
    if high_52_weeks is not None and low_52_weeks is not None and high_52_weeks != low_52_weeks:
        range_position = ((latest_value - low_52_weeks) / (high_52_weeks - low_52_weeks)) * 100
    changes = {}
    for name, days in (("daily_pct", 1), ("weekly_pct", 7), ("monthly_pct", 30)):
        prior = _latest_on_or_before(observations, latest_date - timedelta(days=days))
        changes[name] = _change_pct(latest_value, prior[1] if prior else None)
    return {
        "as_of": latest_date.isoformat(),
        "value": latest_value,
        "changes": changes,
        "low_52_weeks": low_52_weeks,
        "high_52_weeks": high_52_weeks,
        "position_52_weeks_pct": range_position,
        "sparkline": [
            {"date": observed_on.isoformat(), "value": value}
            for observed_on, value in observations[-30:]
        ],
    }


def calculate_crack_spread(brent_observations, jet_fuel_observations, source_label="EIA"):
    spread_rows = calculate_crack_spread_rows(brent_observations, jet_fuel_observations)
    indicators = calculate_series_indicators(spread_rows)
    if not indicators:
        return None
    latest_date = date.fromisoformat(indicators["as_of"])
    last_90_days = [
        value for observed_on, value in spread_rows
        if observed_on >= latest_date - timedelta(days=90)
    ]
    mean_90_days = statistics.fmean(last_90_days) if last_90_days else None
    standard_deviation_90_days = statistics.pstdev(last_90_days) if len(last_90_days) > 1 else 0.0
    deviation = None
    if mean_90_days is not None and standard_deviation_90_days:
        deviation = (indicators["value"] - mean_90_days) / standard_deviation_90_days
    indicators.update({
        "name": "ABD Körfez Kıyısı jet yakıtı - Brent marjı",
        "unit": "USD/varil",
        "source": f"{source_label}; jet yakıtı USD/galon değeri {GALLONS_PER_BARREL} ile USD/varile çevrilmiştir.",
        "mean_90_days": mean_90_days,
        "standard_deviation_90_days": standard_deviation_90_days,
        "deviation_from_mean_standard_deviations": deviation,
    })
    return indicators


def _event_payload(indicator):
    return json.dumps(indicator, ensure_ascii=False, sort_keys=True)


def _upsert_event(connection, event_type, occurred_on, headline, source, payload, related_market_event_id=None):
    connection.execute(
        """
        INSERT INTO events (
            event_type, occurred_on, headline, source, payload_json,
            related_market_event_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_type, occurred_on, headline, source) DO UPDATE SET
            payload_json = excluded.payload_json,
            related_market_event_id = excluded.related_market_event_id
        """,
        (
            event_type,
            occurred_on,
            headline,
            source,
            _event_payload(payload),
            related_market_event_id,
            utc_now().isoformat(),
        ),
    )
    row = connection.execute(
        "SELECT id FROM events WHERE event_type = ? AND occurred_on = ? AND headline = ? AND source = ?",
        (event_type, occurred_on, headline, source),
    ).fetchone()
    return row[0]


def deterministic_market_comment(event_type):
    if event_type == "fuel_energy":
        return (
            "Yakıt maliyeti hareketi, özellikle uzun menzilli ve hedge oranı düşük taşıyıcılarda daha belirgin olabilir. "
            "Taşıyıcıların fiyatlama ve kapasite tepkileri ile Brent ve ABD Körfez Kıyısı jet yakıtı marjının yönü izlenmelidir. "
            "Bu değerlendirme yatırım tavsiyesi değildir."
        )
    return (
        "Kur hareketi, ABD doları cinsinden maliyet ve gelir dengesi farklı olan taşıyıcılarda etkili olabilir. "
        "Fiyatlama, kapasite ve hedge açıklamalarındaki değişim izlenmelidir. Bu değerlendirme yatırım tavsiyesi değildir."
    )


def _event_comment(event_type, api_key):
    """Allow an optional, number-free LLM note; fall back to an auditable template."""
    if not api_key:
        return deterministic_market_comment(event_type)
    prompt = (
        "Türkçe iki kısa cümle yaz. Rakam, yüzde, tarih, yatırım tavsiyesi veya al/sat dili kullanma. "
        "Uzun menzil, düşük maliyetli ve hedge oranı düşük taşıyıcıların olası etkisini; fiyatlama/kapasite tepkisini ve "
        "izlenecek sonraki sinyali anlat. Sadece şu olay türünü yorumla: " + event_type
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "text/plain"},
    }
    request = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
        comment = body["candidates"][0]["content"]["parts"][0]["text"].strip()
        if comment and not re.search(r"\d", comment):
            return comment
    except Exception:
        pass
    return deterministic_market_comment(event_type)


def list_threshold_breaches(path, fuel_source="EIA"):
    """Evaluate every stored observation date so historical threshold days are auditable."""
    target = database_path(path)
    thresholds = load_market_config()["thresholds"]
    definitions = market_series_definitions()
    breaches = []
    jet_fuel = load_observations(target, "us_gulf_coast_jet_fuel")
    for index, (observed_on, value) in enumerate(jet_fuel):
        prior = _latest_on_or_before(jet_fuel[:index], observed_on - timedelta(days=7))
        weekly_change = _change_pct(value, prior[1] if prior else None)
        if abs(weekly_change or 0) >= thresholds["jet_fuel_weekly_change_pct"]:
            breaches.append({
                "event_type": "fuel_energy",
                "as_of": observed_on.isoformat(),
                "headline": "ABD Körfez Kıyısı jet yakıtında haftalık eşik aşımı",
                "source": fuel_source,
                "payload": {
                    "series_id": "us_gulf_coast_jet_fuel",
                    "value": value,
                    "weekly_pct": weekly_change,
                    "unit": definitions["us_gulf_coast_jet_fuel"]["unit"],
                },
            })

    crack_rows = [
        (observed_on, value) for observed_on, value in calculate_crack_spread_rows(
            load_observations(target, "brent_spot"), jet_fuel
        )
    ]
    for index, (observed_on, value) in enumerate(crack_rows):
        window = [
            prior_value for prior_date, prior_value in crack_rows[:index]
            if prior_date >= observed_on - timedelta(days=90)
        ]
        if len(window) < 2:
            continue
        mean_value = statistics.fmean(window)
        standard_deviation = statistics.pstdev(window)
        deviation = (value - mean_value) / standard_deviation if standard_deviation else 0.0
        if deviation >= thresholds["crack_spread_standard_deviations"]:
            breaches.append({
                "event_type": "fuel_energy",
                "as_of": observed_on.isoformat(),
                "headline": "ABD Körfez Kıyısı jet yakıtı - Brent marjında 90 günlük eşik aşımı",
                "source": fuel_source,
                "payload": {
                    "series_id": "jet_fuel_brent_crack_spread",
                    "value": value,
                    "mean_90_days": mean_value,
                    "standard_deviation_90_days": standard_deviation,
                    "deviation_from_mean_standard_deviations": deviation,
                    "unit": "USD/varil",
                },
            })

    for series_id in (series for series in definitions if series.startswith("fx_usd_")):
        observations = load_observations(target, series_id)
        for index, (observed_on, value) in enumerate(observations):
            prior = _latest_on_or_before(observations[:index], observed_on - timedelta(days=1))
            daily_change = _change_pct(value, prior[1] if prior else None)
            if abs(daily_change or 0) < thresholds["fx_daily_change_pct"]:
                continue
            breaches.append({
                "event_type": "fx_currency",
                "as_of": observed_on.isoformat(),
                "headline": f"{definitions[series_id]['name']} günlük eşik aşımı",
                "source": "ECB",
                "payload": {
                    "series_id": series_id,
                    "value": value,
                    "daily_pct": daily_change,
                    "unit": definitions[series_id]["unit"],
                },
            })
    return breaches


def calculate_crack_spread_rows(brent_observations, jet_fuel_observations):
    brent_by_date = dict(brent_observations)
    return [
        (observed_on, jet_value * GALLONS_PER_BARREL - brent_by_date[observed_on])
        for observed_on, jet_value in jet_fuel_observations
        if observed_on in brent_by_date
    ]


def write_threshold_events(path, indicators, api_key="", fuel_source="EIA"):
    """Persist deterministic threshold events; only most-recent events receive a short comment."""
    target = migrate_market_database(path)
    latest_dates = {
        indicator["as_of"]
        for indicator in indicators.values()
        if isinstance(indicator, dict) and indicator.get("as_of")
    }
    published_events = []
    with sqlite3.connect(target) as connection:
        for breach in list_threshold_breaches(target, fuel_source):
            event_id = _upsert_event(
                connection,
                breach["event_type"],
                breach["as_of"],
                breach["headline"],
                breach["source"],
                breach["payload"],
            )
            if breach["as_of"] not in latest_dates:
                continue
            published_events.append({
                "id": event_id,
                "event_type": breach["event_type"],
                "headline": breach["headline"],
                "as_of": breach["as_of"],
                "comment": _event_comment(breach["event_type"], api_key),
            })
    return published_events


@lru_cache(maxsize=2)
def _compiled_taxonomy(config_mtime_ns):
    """Compile taxonomy terms once per config version; the mtime key picks up edits."""
    compiled = {}
    for event_type, rule in load_taxonomy_config()["event_types"].items():
        context_terms = rule.get("aviation_context_terms")
        compiled[event_type] = {
            "exclude_when_rule": rule.get("exclude_when_rule"),
            "weight": float(rule["weight"]),
            "terms": text_match.TermSet(rule.get("terms", []), allow_plural=True),
            "context": text_match.TermSet(context_terms, allow_plural=True) if context_terms else None,
        }
    return compiled


def _min_description_hits():
    return int(load_taxonomy_config().get("min_description_hits", 2))


def _taxonomy():
    return _compiled_taxonomy(TAXONOMY_CONFIG_PATH.stat().st_mtime_ns)


def _military_strike_applies(prepared_text):
    """True for a strike in a military context ("missile strike", "airstrike") that no labour context contradicts."""
    from . import story_lifecycle  # lazy, as in is_excluded_from_typing
    return story_lifecycle.military_strike_matches(prepared_text, story_lifecycle.load_relevance_config()["selection"])


def is_excluded_from_typing(title):
    """True for defence items and investment commentary: they must not pick up the guarded types.

    Reads the same lists the selection step uses (config/relevance.json), so the two cannot drift apart.
    """
    from . import story_lifecycle  # lazy: story_lifecycle's own imports must not depend on this module

    relevance = story_lifecycle.load_relevance_config()
    selection = relevance.get("selection", {})
    prepared = text_match.prepare(title)
    defence_terms = text_match.TermSet(selection.get("exclude_terms", []))
    keep_terms = text_match.TermSet(selection.get("keep_terms", []))
    is_defence = bool(selection.get("exclude_terms")) and defence_terms.any(prepared) and not keep_terms.any(prepared)
    commentary_patterns = (relevance.get("commentary") or {}).get("title_patterns", [])
    is_commentary = bool(commentary_patterns) and text_match.TermSet(commentary_patterns).any(prepared)
    return is_defence or is_commentary


def classify_event_type(text, description=""):
    """Primary event type from the title (text) and optional description.

    A type counts when a term is in the title, or at least min_description_hits distinct terms are
    in the description; one stray hit in a long description is usually boilerplate.
    """
    title = text_match.prepare(text)
    body = text_match.prepare(description)
    if not title.raw.strip() and not body.raw.strip():
        return None
    taxonomy = _taxonomy()
    minimum_body_hits = _min_description_hits()
    combined = text_match.prepare(f"{title.raw} {body.raw}")
    military_strike = _military_strike_applies(combined)
    guarded_types = set(load_taxonomy_config().get("typing_exclusions", {}).get("guarded_types", []))
    skip_guarded = bool(guarded_types) and is_excluded_from_typing(title.raw)
    ranked_matches = []
    for event_type, rule in taxonomy.items():
        if skip_guarded and event_type in guarded_types:
            continue
        if military_strike and rule.get("exclude_when_rule") == "military_strike":
            continue
        title_terms = {term for term, _ in rule["terms"].matches(title)}
        body_terms = {term for term, _ in rule["terms"].matches(body)}
        if not title_terms and len(body_terms) < minimum_body_hits:
            continue
        if rule["context"] is not None and not rule["context"].any(combined):
            continue
        ranked_matches.append((len(title_terms | body_terms), rule["weight"], event_type))
    if not ranked_matches:
        return None
    matched_types = {event_type for _, _, event_type in ranked_matches}
    # A headline about airline shares reacting to fuel is principally a capital
    # markets story, while its same-day fuel event is retained as the relation.
    if "capital_markets" in matched_types and "fuel_energy" in matched_types:
        return {"event_type": "capital_markets", "event_weight": taxonomy["capital_markets"]["weight"]}
    _, weight, event_type = max(ranked_matches)
    return {"event_type": event_type, "event_weight": weight}


def _article_date(article):
    timestamp = article.get("timestamp")
    if isinstance(timestamp, (int, float)):
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).date()
    return utc_now().date()


def record_article_events(path, articles):
    """Store classified news events locally and associate same-day fuel context."""
    target = migrate_market_database(path)
    recorded_articles = []
    with sqlite3.connect(target) as connection:
        for article in articles:
            classification = classify_event_type(article.get("title", ""), article.get("description", ""))
            if not classification:
                continue
            occurred_on = _article_date(article).isoformat()
            text = f"{article.get('title', '')} {article.get('description', '')}"
            related_market_event_id = None
            if classification["event_type"] != "fuel_energy" and FUEL_CONTEXT_TERMS.any(text):
                row = connection.execute(
                    "SELECT id FROM events WHERE event_type = 'fuel_energy' AND occurred_on = ? ORDER BY id DESC LIMIT 1",
                    (occurred_on,),
                ).fetchone()
                related_market_event_id = row[0] if row else None
            event_id = _upsert_event(
                connection,
                classification["event_type"],
                occurred_on,
                str(article.get("title") or "Aviation market update"),
                str(article.get("link") or article.get("source") or "source"),
                {"url": article.get("link", ""), "source": article.get("source", "")},
                related_market_event_id,
            )
            article["event_type"] = classification["event_type"]
            article["event_weight"] = classification["event_weight"]
            article["event_id"] = event_id
            article["related_market_event_id"] = related_market_event_id
            recorded_articles.append(article)
    return recorded_articles


def build_market_panel(path, provider_by_series=None):
    definitions = market_series_definitions(provider_by_series)
    jet_provider = (provider_by_series or {}).get("us_gulf_coast_jet_fuel")
    indicators = {
        series_id: calculate_series_indicators(load_observations(path, series_id))
        for series_id in definitions
    }
    crack_provider = (provider_by_series or {}).get("jet_fuel_brent_crack_spread")
    if crack_provider == "iata":
        iata_data = get_cached_iata_fuel_data()
        if iata_data and "crack_spread_bbl" in iata_data:
            observed_on = date.fromisoformat(iata_data.get("as_of", utc_now().date().isoformat()))
            crack_spread = {
                "as_of": observed_on.isoformat(),
                "value": float(iata_data["crack_spread_bbl"]),
                "changes": {
                    "daily_pct": 0.0,
                    "weekly_pct": float(iata_data.get("weekly_pct", 0.0)),
                    "monthly_pct": None,
                },
                "name": "IATA Jet yakıtı - Brent marjı",
                "unit": "USD/varil",
                "source": iata_data.get("source", "IATA / Platts Jet Fuel Price Monitor"),
                "low_52_weeks": None,
                "high_52_weeks": None,
                "position_52_weeks_pct": None,
                "sparkline": [
                    {"date": observed_on.isoformat(), "value": float(iata_data["crack_spread_bbl"])}
                ],
            }
        else:
            crack_spread = None
    else:
        crack_spread = calculate_crack_spread(
            load_observations(path, "brent_spot"),
            load_observations(path, "us_gulf_coast_jet_fuel"),
            source_label=_fuel_source({"source": "EIA"}, jet_provider) if jet_provider else "EIA",
        )
    if crack_spread:
        indicators["jet_fuel_brent_crack_spread"] = crack_spread
    items = []
    show_fx = display_fx()
    for series_id, indicator in indicators.items():
        if not indicator or (is_fx_series(series_id) and not show_fx):
            continue
        definition = definitions.get(series_id, {})
        item = dict(indicator)
        observed_on = date.fromisoformat(indicator["as_of"])
        age_days = (utc_now().date() - observed_on).days
        item.update({
            "series_id": series_id,
            "name": definition.get("name", indicator.get("name", series_id)),
            "unit": definition.get("unit", indicator.get("unit", "")),
            "source": definition.get("source", indicator.get("source", "")),
            # as_of is the real observation date (FRED/EIA publish with a lag); age_days says how stale that is today.
            "carried_forward": age_days > 0,
            "age_days": max(age_days, 0),
        })
        items.append(item)
    return {
        "status": "ok" if items else "unavailable",
        "items": items,
        "iata_monitor": {
            "name": "IATA Jet Fuel Price Monitor",
            "url": IATA_FUEL_MONITOR_URL,
            "access": "external_link_only",
        },
        "note": load_market_config()["iatanote"],
    }, indicators


def _fetch_fuel_series(fetch, series_key, config, today, start):
    """{series_id: observations} for both fuel series from one provider (all or nothing)."""
    return {series_id: fetch(config[series_id][series_key], start, today) for series_id in FUEL_SERIES}


def refresh_market_data(path=None, eia_api_key="", start_date=None, end_date=None, gemini_api_key="", fred_api_key="", live_brent=None, live_iata_crack=None):
    """Fetch, persist, calculate, and emit deterministic market signals for a pipeline run.

    Fuel series: EIA when EIA_API_KEY is set, with FRED as the fallback; FRED alone otherwise. A missing
    EIA key is recorded in panel["skipped"], never silently dropped. No provider failure stops the run.
    """
    target = migrate_market_database(path)
    today = end_date or utc_now().date()
    start = start_date or (today - timedelta(days=400))
    config = load_market_config()["series"]
    observations = {}
    errors = []
    skipped = []
    fuel_provider = None
    if str(eia_api_key or "").strip():
        try:
            observations.update(_fetch_fuel_series(lambda series, s, e: fetch_eia_series(series, eia_api_key, s, e), "eia_series", config, today, start))
            fuel_provider = "eia"
        except Exception as exc:
            errors.append(f"EIA: {type(exc).__name__}")
    else:
        skipped.append("EIA")
    if fuel_provider is None:
        try:
            observations.update(_fetch_fuel_series(lambda series, s, e: fetch_fred_series(series, fred_api_key, s, e), "fred_series", config, today, start))
            fuel_provider = "fred"
        except Exception as exc:
            errors.append(f"FRED: {type(exc).__name__}")
    try:
        observations.update(fetch_ecb_fx_series(start, today))
    except Exception as exc:
        errors.append(f"ECB: {type(exc).__name__}")
    provider_by_series = {series_id: fuel_provider for series_id in FUEL_SERIES} if fuel_provider else {}
    if observations:
        upsert_observations(target, observations, provider_by_series=provider_by_series)
    should_live_brent = (
        bool(live_brent)
        if live_brent is not None
        else (os.environ.get("ENABLE_LIVE_BRENT", "").strip().lower() in ("1", "true", "yes"))
    )
    if should_live_brent and (end_date is None or end_date >= utc_now().date()):
        try:
            live_brent_rows = fetch_live_brent()
            if live_brent_rows:
                provider_by_series["brent_spot"] = "ice"
                upsert_observations(target, {"brent_spot": live_brent_rows}, provider_by_series=provider_by_series)
        except Exception as exc:
            errors.append(f"LiveBrent: {type(exc).__name__}")
    should_iata_crack = (
        bool(live_iata_crack)
        if live_iata_crack is not None
        else (os.environ.get("ENABLE_IATA_CRACK", "").strip().lower() in ("1", "true", "yes"))
    )
    if should_iata_crack:
        try:
            iata_data = fetch_iata_fuel_monitor(gemini_api_key=gemini_api_key)
            if iata_data and "crack_spread_bbl" in iata_data:
                provider_by_series["jet_fuel_brent_crack_spread"] = "iata"
        except Exception as exc:
            errors.append(f"IATA: {type(exc).__name__}")
    panel, indicators = build_market_panel(target, provider_by_series)
    panel["errors"] = errors
    panel["skipped"] = skipped
    panel["fuel_provider"] = fuel_provider
    if not fuel_provider:
        panel["missing_data_note"] = MISSING_FUEL_NOTE
    has_gap = bool(errors) or not fuel_provider
    if has_gap and panel["status"] == "ok":
        panel["status"] = "partial"
    fuel_source = provider_label(fuel_provider) if fuel_provider else "EIA"
    events = write_threshold_events(target, indicators, gemini_api_key, fuel_source) if indicators else []
    panel["events"] = events if display_fx() else [event for event in events if event["event_type"] != "fx_currency"]
    return panel
