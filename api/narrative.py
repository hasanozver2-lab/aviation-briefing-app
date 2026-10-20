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
import re
from pathlib import Path

try:
    from . import language
except ImportError:
    import language


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
- Every item has target_language: "en" (English) or "tr" (Turkish). Write headline, lead, detailed_analysis, data_points, strategic_impact, the details of market_exposure and why_it_matters in that language, whatever language the source item is in.
- Numbers, dates, names, aircraft types, airport and airline codes come from the item and are never changed, converted, rounded or re-spelled by the translation. market_exposure impact stays one of the English labels listed below.
- For "tr", write natural Turkish as an aviation professional would (havayolu, uçuş, hat, filo, sefer, yolcu); avoid word-for-word English calques. Established industry terms may stay as they are (ASK, RPK, doluluk oranı, yield, slot, codeshare, MRO, SAF).
- An item with basis "headline_only" comes from a press headline feed: only its title and a short summary exist. Write only what they state, in your own words. Do not add any number, date, percentage, count, price, ranking or other figure that is not literally in the title or summary, and never estimate one. data_points holds only figures that appear literally in the title or summary, otherwise [].
- CRITICAL FOCUS ON DATA & METRICS ANALYSIS:
  * If the item contains concrete numbers, figures, percentages, financial amounts, dates, aircraft orders, or passenger/seat capacities:
    - Extract each exact figure into `data_points` (e.g. ['42,060 yeni uçak', '+%2.7 haftalık düşüş', '$1.3 milyar']).
    - In `detailed_analysis`, write bullets that STRICTLY analyze and contextualize those specific data points (explaining what each number means for the airline or industry, comparisons, capacity or cost implications).
  * If the item contains NO concrete figures or metrics:
    - `data_points` MUST be empty `[]`.
    - `detailed_analysis` MUST be empty `[]` or at most 1 concise bullet stating the confirmed action (never invent filler speculation).
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
            "target_language": language.story_language(story),
            "basis": story.get("basis", ""),
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
    """One HTTP request; falls back across configured models on HTTP 429 before raising for retry."""
    payload = {
        "contents": [{"parts": [{"text": SYSTEM_PROMPT}, {"text": "ITEMS:\n" + json.dumps(items, ensure_ascii=False)}]}],
        "generationConfig": {"temperature": config["temperature"], "responseMimeType": "application/json"},
    }
    fallbacks = config.get("fallback_models") or ["gemini-3-flash-preview", "gemini-2.5-pro"]
    models = [config["model"]] + [m for m in fallbacks if m != config["model"]]
    last_error = None
    for model_name in models:
        request = urllib.request.Request(
            GEMINI_URL.format(model=model_name),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        )
        try:
            with urllib.request.urlopen(request, context=ssl.create_default_context(), timeout=config["request_timeout_seconds"]) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in {404, 429, 500, 503}:
                continue
            raise
    raise last_error


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


BASIS_HEADLINE_ONLY = "headline_only"
NUMBER_PATTERN = re.compile(r"\d+(?:[.,]\d+)*")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _digits(token):
    return re.sub(r"[.,]", "", token)


def grounded_numbers(source_text):
    """Every number written in the source, with separators removed (1,200 and 1.200 and 1200 are the same figure)."""
    return {_digits(token) for token in NUMBER_PATTERN.findall(str(source_text))}


def has_ungrounded_number(text, known):
    return any(_digits(token) not in known for token in NUMBER_PATTERN.findall(str(text)))


def _keep_grounded_sentences(text, known):
    kept = [sentence for sentence in SENTENCE_SPLIT.split(str(text).strip()) if sentence and not has_ungrounded_number(sentence, known)]
    return " ".join(kept)


def sanitize_headline_only(fields, source_text):
    """Remove every figure the model was not given. Returns (fields, number_of_removed_pieces).

    A headline-only narrative rests on a title and a short summary; a number that is in neither is invented, so the
    sentence, bullet, data point or exposure detail that carries it is dropped (the headline falls back to the title).
    """
    known = grounded_numbers(source_text)
    removed = 0
    clean = dict(fields)
    for key in ("lead", "why_it_matters", "strategic_impact"):
        kept = _keep_grounded_sentences(clean.get(key, ""), known)
        removed += kept != clean.get(key, "")
        clean[key] = kept
    for key in ("detailed_analysis", "data_points"):
        kept = [item for item in clean.get(key, []) if not has_ungrounded_number(item, known)]
        removed += len(clean.get(key, [])) - len(kept)
        clean[key] = kept
    exposures = []
    for exposure in clean.get("market_exposure", []):
        if has_ungrounded_number(exposure.get("details", ""), known):
            removed += 1
            exposure = {**exposure, "details": ""}
        exposures.append(exposure)
    clean["market_exposure"] = exposures
    return clean, removed


def needs_language_rewrite(story):
    """A finished narrative whose language differs from the story's target language."""
    return story.get("narrative_status") == NARRATIVE_DONE and (story.get("narrative_language") or "en") != language.story_language(story)


def fill_pending(stories, api_key, description_limit, config=None, post=None, sleep=time.sleep, now=None):
    """Generate narratives for stories that have none (or whose facts changed). Returns a report.

    Never raises for LLM trouble: failed stories keep narrative_status="pending".
    """
    config = config or load_narrative_config()
    post = post or (lambda items: post_to_gemini(items, api_key, config))
    now_iso = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    # Stories without a narrative come first; then those whose stored narrative is in the wrong language (narratives written
    # before languages existed are English). A mismatched story keeps showing its old narrative until the new one arrives.
    pending = sorted(
        (s for s in stories if s.get("narrative_status") != NARRATIVE_DONE or needs_language_rewrite(s)),
        key=lambda s: (s.get("narrative_status") == NARRATIVE_DONE, -float(s.get("relevance_score", 0)), s["story_id"]),
    )
    report = {"calls": 0, "narrated": 0, "rewritten": 0, "pending": sum(1 for s in pending if s.get("narrative_status") != NARRATIVE_DONE), "error": ""}
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
            if fields and story.get("basis") == BASIS_HEADLINE_ONLY:
                title = (story.get("original_source") or {}).get("title") or story.get("headline", "")
                fields, removed = sanitize_headline_only(fields, f"{title} {story.get('source_description', '')}")
                report["numbers_removed"] = report.get("numbers_removed", 0) + removed
                fields["lead"] = fields["lead"] or title
                if has_ungrounded_number(fields["headline"], grounded_numbers(title)):
                    fields["headline"] = title
                    report["numbers_removed"] += 1
            if fields:
                was_rewrite = story.get("narrative_status") == NARRATIVE_DONE
                story.update(fields)
                story["narrative_status"] = NARRATIVE_DONE
                story["narrative_generated_at"] = now_iso
                story["narrative_language"] = language.story_language(story)
                if story.get("basis") == BASIS_HEADLINE_ONLY:
                    story["source_description"] = ""      # the publisher's summary is used once and not kept
                report["rewritten" if was_rewrite else "narrated"] += 1
    report["pending"] = sum(1 for s in stories if s.get("narrative_status") != NARRATIVE_DONE)
    return report
