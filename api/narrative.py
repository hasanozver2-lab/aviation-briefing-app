"""Narrative (LLM) step.

A story's narrative is generated once and stored with its story_id, so an unchanged story never
costs a call. Pending stories are sent in ONE batched request; 429/5xx answers are retried with
exponential backoff and, when that fails, the stories simply stay narrative_status="pending" and are
tried again on the next run. Scores, badges, ordering and the archive never depend on this step.
"""

import json
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
NARRATIVE_CONFIG_PATH = BASE_DIR / "config" / "narrative.json"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
NARRATIVE_DONE, NARRATIVE_PENDING = "done", "pending"
IMPACT_LABELS = {"Positive", "Negative", "Neutral", "Competitive Headwind"}
MAX_TEXT_LENGTH = 1200


class NarrativeUnavailable(RuntimeError):
    """The LLM could not be reached or kept answering with a retryable error."""


def load_narrative_config():
    return json.loads(NARRATIVE_CONFIG_PATH.read_text(encoding="utf-8"))


SYSTEM_PROMPT = """You write short, structured decision-support notes for aviation professionals worldwide (network planning, revenue management, sales, fleet, airports, leasing).
Rules:
- Use ONLY facts present in the provided items. Never invent figures, names, fleets or operators.
- Copy numbers exactly as written and keep comparative figures together (for example airport A versus airport B).
- Do not attribute anything to a carrier that the item does not name. The analysis is global; do not single out any one airline.
- Return pure JSON: {"stories": [ ... ]} with exactly one object per input item, using the item's story_id unchanged.
Each object has: story_id, headline (one concise factual headline), lead (one or two sentences), detailed_analysis (3 to 5 short bullet strings), data_points (array of concrete figures quoted from the item; empty when there are none), strategic_impact (one or two sentences on capacity, demand, revenue, cost, competition or operations), market_exposure (array of {carrier, impact, details} for named carriers, airports or manufacturers only; impact is one of Positive, Negative, Neutral, Competitive Headwind), why_it_matters (one consequence-focused sentence)."""


def build_request_items(stories, description_limit):
    return [
        {
            "story_id": story["story_id"],
            "title": story.get("original_source", {}).get("title") or story.get("headline", ""),
            "source": story.get("original_source", {}).get("source_name", ""),
            "published_at": story.get("published_at", ""),
            "event_type": story.get("event_type"),
            "description": str(story.get("source_description", ""))[:description_limit],
            "publishers": story.get("source_count", 1),
        }
        for story in stories
    ]


def _text(value):
    return str(value).strip()[:MAX_TEXT_LENGTH] if isinstance(value, (str, int, float)) else ""


def _text_list(value):
    return [_text(item) for item in value if isinstance(item, (str, int, float)) and _text(item)] if isinstance(value, list) else []


def _exposure(value):
    exposures = []
    for item in value if isinstance(value, list) else []:
        if isinstance(item, dict) and _text(item.get("carrier")):
            impact = _text(item.get("impact")) if _text(item.get("impact")) in IMPACT_LABELS else "Neutral"
            exposures.append({"carrier": _text(item["carrier"]), "impact": impact, "details": _text(item.get("details"))})
    return exposures


def parse_narratives(response, expected_ids):
    """{story_id: narrative fields}; unknown ids are dropped, items without a headline or lead ignored."""
    text = response["candidates"][0]["content"]["parts"][0]["text"]
    items = json.loads(text).get("stories", [])
    parsed = {}
    for item in items if isinstance(items, list) else []:
        story_id = item.get("story_id") if isinstance(item, dict) else None
        if story_id not in expected_ids or not _text(item.get("headline")) or not _text(item.get("lead")):
            continue
        parsed[story_id] = {
            "headline": _text(item["headline"]),
            "lead": _text(item["lead"]),
            "detailed_analysis": _text_list(item.get("detailed_analysis")),
            "data_points": _text_list(item.get("data_points")),
            "strategic_impact": _text(item.get("strategic_impact")),
            "market_exposure": _exposure(item.get("market_exposure")),
            "why_it_matters": _text(item.get("why_it_matters")),
        }
    return parsed


def post_to_gemini(items, api_key, config):
    """One HTTP request; raises urllib errors untouched so the caller can decide to retry."""
    payload = {
        "contents": [{"parts": [{"text": SYSTEM_PROMPT}, {"text": "ITEMS:\n" + json.dumps(items, ensure_ascii=False)}]}],
        "generationConfig": {"temperature": config["temperature"], "responseMimeType": "application/json"},
    }
    request = urllib.request.Request(
        GEMINI_URL.format(model=config["model"]),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    with urllib.request.urlopen(request, context=ssl.create_default_context(), timeout=config["request_timeout_seconds"]) as response:
        return json.loads(response.read().decode("utf-8"))


def retry_delay(attempt, retry_config, retry_after=None):
    """Exponential backoff (base x 2^(attempt-1)), never beyond max_delay; a server Retry-After wins if shorter."""
    delay = min(retry_config["max_delay_seconds"], retry_config["base_delay_seconds"] * 2 ** (attempt - 1))
    if retry_after is not None:
        delay = min(retry_config["max_delay_seconds"], max(delay, retry_after))
    return delay


def call_with_backoff(send, retry_config, sleep=time.sleep):
    """Run send(); retry 429/5xx and network errors with exponential backoff, a bounded number of times."""
    attempts = retry_config["max_attempts"]
    for attempt in range(1, attempts + 1):
        try:
            return send()
        except urllib.error.HTTPError as exc:
            if exc.code not in retry_config["retry_statuses"]:
                raise NarrativeUnavailable(f"HTTP {exc.code} (not retried)") from None
            reason, retry_after = f"HTTP {exc.code}", _retry_after(exc)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            reason, retry_after = type(exc).__name__, None
        if attempt == attempts:
            raise NarrativeUnavailable(f"{reason} after {attempts} attempts")
        sleep(retry_delay(attempt, retry_config, retry_after))


def _retry_after(error):
    value = error.headers.get("Retry-After") if getattr(error, "headers", None) else None
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def fill_pending(stories, api_key, description_limit, config=None, post=None, sleep=time.sleep, now=None):
    """Generate narratives for stories that have none (or whose facts changed). Returns a report.

    Never raises for LLM trouble: failed stories keep narrative_status="pending".
    """
    config = config or load_narrative_config()
    post = post or (lambda items: post_to_gemini(items, api_key, config))
    now_iso = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    pending = sorted((s for s in stories if s.get("narrative_status") != NARRATIVE_DONE), key=lambda s: (-float(s.get("relevance_score", 0)), s["story_id"]))
    report = {"calls": 0, "narrated": 0, "pending": len(pending), "error": ""}
    if not pending:
        return report
    if not api_key:
        report["error"] = "GEMINI_API_KEY is not configured"
        return report

    batch_size = config["max_stories_per_call"]
    for start in range(0, min(len(pending), batch_size * config["max_calls_per_run"]), batch_size):
        batch = pending[start:start + batch_size]
        report["calls"] += 1
        try:
            response = call_with_backoff(lambda: post(build_request_items(batch, description_limit)), config["retry"], sleep)
            parsed = parse_narratives(response, {story["story_id"] for story in batch})
        except NarrativeUnavailable as exc:
            report["error"] = str(exc)
            break          # do not hammer an API that is refusing us; the next run tries again
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            report["error"] = f"unreadable narrative response ({type(exc).__name__})"
            break
        for story in batch:
            fields = parsed.get(story["story_id"])
            if fields:
                story.update(fields)
                story["narrative_status"] = NARRATIVE_DONE
                story["narrative_generated_at"] = now_iso
                report["narrated"] += 1
    report["pending"] = sum(1 for s in stories if s.get("narrative_status") != NARRATIVE_DONE)
    return report
