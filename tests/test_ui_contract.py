"""public/index.html is the only UI source (Vercel serves public/); these checks pin what the page reads from the API and how it behaves."""

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from api import story_lifecycle

PROJECT_DIR = Path(__file__).resolve().parents[1]
INDEX = "public/index.html"
IGNORED_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".playwright-cli", ".pytest_cache", "design_handoff"}
ALLOWED_EXTERNAL_HOSTS = {"fonts.googleapis.com", "fonts.gstatic.com"}
MIN_TEXT_CONTRAST = 4.5


def page(relative_path=INDEX):
    return (PROJECT_DIR / relative_path).read_text(encoding="utf-8")


def css_color(name, html):
    return re.search(rf"--{name}:\s*(#[0-9A-Fa-f]{{6}})", html).group(1)


def luminance(hex_color):
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(foreground, background):
    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_index_html_has_exactly_one_copy_and_it_is_in_public():
    # Vercel serves public/; a second copy elsewhere silently drifts (static/index.html did, for weeks).
    found = sorted(
        path.relative_to(PROJECT_DIR).as_posix() for path in PROJECT_DIR.rglob("index.html")
        if not IGNORED_DIRS & set(path.relative_to(PROJECT_DIR).parts)
    )
    assert found == [INDEX]


def test_the_page_reads_only_fields_the_api_really_returns():
    now = datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc)
    stamp = story_lifecycle.to_iso(now)
    story = {
        "story_id": "story-1", "id": "story-1", "headline": "H", "relevance_score": 70, "region_section": "Europe", "section": "Route news",
        "first_seen_at": stamp, "published_at_iso": stamp, "narrative_status": "done", "source_count": 2,
        "original_source": {"url": "https://example.com/a", "source_name": "Wire"}, "sources": [{"name": "Wire", "url": "https://example.com/a", "title": "t"}],
    }
    day = {"stories": [story]}
    story_lifecycle.present_stories(day, now)
    served = day["stories"][0]
    html = page()
    for field in ("badges", "level", "source_count", "sources", "narrative_status", "region_section", "story_id"):
        assert field in served, f"the API stopped returning {field}"
        assert re.search(rf"\b{field}\b", html), f"the page no longer reads {field}"
    for field in ("last_pipeline_run_at", "generated_at", "date_str", "time_str", "status", "age_days", "carried_forward"):
        assert re.search(rf"\b{field}\b", html), field
    assert "freshness" not in html, "the API has no freshness field; the age comes from last_pipeline_run_at"


def test_there_is_one_page_without_tabs_or_modes():
    html = page()
    for removed in ('role="tab"', "data-mode", "Live", "setMode", "hourly", "state.mode", "?mode=", "48h", "60 min"):
        assert removed not in html, f"{removed} belongs to the removed Daily/Live tabs"
    assert 'BRIEFING_URL = "/api/briefing"' in html, "the page asks for the default (daily, today) view and sends no mode"


def test_yesterdays_stories_come_from_the_api_and_sit_at_the_bottom_unbadged():
    html = page()
    assert 'carried_from === YESTERDAY' in html and "Yesterday ·" in html
    assert "!isYesterday(s) && !known.has" in html, "carried-over stories never raise the new-stories pill"


def test_labels_and_levels_come_from_the_server():
    html = page()
    assert "story.badges" in html and "story.level" in html
    for label in ("Breaking", "New", "Updated", "Critical", "Important", "Watch"):
        assert label in html
    for removed in ("isPriority", "Priority", "previousKeysByMode", "newKeys"):
        assert removed not in html, f"{removed} was the browser-side guess the server labels replace"
    assert re.search(r"counts.*breaking", html), "the counter reads 'N stories · N breaking'"


def test_regions_follow_the_server_and_the_old_turkey_section_is_gone():
    html = page()
    assert "Turkey / THY" not in html and "thy_impact_assessment" not in html
    assert "story.region_section ||" in html and "story.section" not in html


def test_the_top_block_and_the_region_groups():
    html = page()
    assert "Critical &amp; Important" in html and "function isTopLevel" in html
    assert 'TOP_LEVELS = ["critical", "important"]' in html


def test_clustered_stories_show_their_sources_and_pending_ones_a_plain_note():
    html = page()
    assert "${count} sources" in html and "sourcesOf(s)" in html and 'class="sources"' in html
    assert "Analysis pending" in html and 'story.narrative_status === "pending"' in html


def test_freshness_comes_from_the_pipeline_run_time_and_warns_after_three_hours():
    html = page()
    assert "STALE_AFTER_MINUTES = 180" in html
    assert "data.last_pipeline_run_at || data.generated_at" in html
    assert "Updated ${ageText(minutes)}" in html


def test_the_market_strip_names_what_is_missing_and_where_the_data_comes_from():
    html = page()
    assert "unavailable" in html.lower() and "Unavailable right now" in html
    assert "Sources:" in html and "EIA · ECB reference rates" not in html


def test_new_stories_are_added_without_a_reload():
    html = page()
    assert "POLL_INTERVAL_MS = 5 * 60 * 1000" in html
    assert "visibilitychange" in html and "function pollBriefing" in html
    assert 'id="new-pill"' in html, "a reader who has scrolled gets a button instead of a jump"


def test_the_page_stays_zoomable_and_calls_no_third_party_scripts():
    html = page()
    assert "user-scalable=no" not in html and "maximum-scale" not in html
    hosts = set(re.findall(r"https?://([^/\"' )]+)", html))
    assert hosts <= ALLOWED_EXTERNAL_HOSTS | {"www.w3.org"}, hosts
    assert "<script src" not in html


def test_the_page_updates_itself_when_a_new_version_is_deployed():
    """A home-screen app resumes with old page code; it must notice a new deployment and reload."""
    html = page()
    assert "function checkForNewVersion" in html and "location.reload()" in html
    assert 'cache: "no-store"' in html
    assert "!state.articleId) location.reload()" in html, "never reload under a reader with a story open"
    assert html.count("checkForNewVersion") >= 5


def test_there_is_no_manual_refresh_button_and_share_stays():
    html = page()
    assert "btn-refresh" not in html and ">Refresh<" not in html
    assert 'id="btn-share"' in html


def test_local_storage_is_only_touched_inside_try_blocks():
    html = page()
    uses = [line.strip() for line in html.splitlines() if "localStorage" in line]
    assert uses and all("try {" in line or line.startswith("// ") for line in uses), uses


def test_a_story_link_survives_page_load():
    html = page()
    assert "const initialHash" in html and "function openLinkedStory" in html
    assert "if (location.hash) history.replaceState" not in html, "the old code erased the story link on load"


def test_the_story_panel_manages_focus():
    html = page()
    for needle in ('role="dialog"', 'aria-modal="true"', "inert = true", "inert = false", "function focusArticleHeading", "function returnFocus", 'tabindex="-1"'):
        assert needle in html, needle


@pytest.mark.parametrize("color_name", ["faint", "muted", "body"])
def test_text_colours_meet_aa_contrast_on_both_paper_tones(color_name):
    html = page()
    for background in ("paper", "paper-2"):
        ratio = contrast(css_color(color_name, html), css_color(background, html))
        assert ratio >= MIN_TEXT_CONTRAST, f"--{color_name} on --{background} is {ratio:.2f}:1"


def test_the_market_strip_is_fuel_only_and_hides_when_empty():
    html = page()
    order = re.search(r"const MARKET_ORDER = (\[[^\]]*\])", html).group(1)
    assert "fx_usd" not in order and "brent_spot" in order and "jet_fuel_brent_crack_spread" in order
    assert "European Central Bank" not in html and "ECB" not in html
    assert 'if (!items.length) { $("market").hidden = true; return; }' in html


def test_headline_only_stories_say_so_and_the_new_source_types_have_labels():
    html = page()
    assert 's.basis === "headline_only"' in html and "Based on the publisher's headline and short summary only" in html
    for source_type in ("regulator", "exchange", "oem", "trade", "tech_vendor", "wire_headline"):
        assert f"{source_type}:" in html.split("const SOURCE_TYPES")[1].split("};")[0]
