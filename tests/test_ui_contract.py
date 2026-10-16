"""The three index.html copies are one UI; these checks pin the single-screen behaviour."""

import re
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[1]
COPIES = ("index.html", "public/index.html", "static/index.html")
ALLOWED_EXTERNAL_HOSTS = {"fonts.googleapis.com", "fonts.gstatic.com"}


def page(relative_path="public/index.html"):
    return (PROJECT_DIR / relative_path).read_text(encoding="utf-8")


def test_the_three_copies_are_identical():
    assert len({page(path) for path in COPIES}) == 1


@pytest.mark.parametrize("path", COPIES)
def test_there_is_one_screen_without_a_live_radar_tab(path):
    html = page(path)
    assert "Live radar" not in html and 'data-mode="hourly"' not in html and "setMode" not in html
    assert 'class="today"' in html
    assert "/api/briefing?mode=${encodeURIComponent(mode)}" in html and 'state = { mode: "daily"' in html


@pytest.mark.parametrize("path", COPIES)
def test_new_stories_are_added_without_a_reload(path):
    html = page(path)
    assert "POLL_INTERVAL_MS = 5 * 60 * 1000" in html
    assert "visibilitychange" in html and "function pollBriefing" in html
    assert 'id="new-pill"' in html, "a reader who has scrolled gets a button instead of a jump"


@pytest.mark.parametrize("path", COPIES)
def test_labels_come_from_the_server_badges(path):
    html = page(path)
    assert "story.badges" in html
    for label in ("Breaking", "New", "Updated"):
        assert f">{label}</span>" in html


@pytest.mark.parametrize("path", COPIES)
def test_the_page_stays_zoomable_and_calls_no_third_party_scripts(path):
    html = page(path)
    assert "user-scalable=no" not in html and "maximum-scale" not in html
    hosts = set(re.findall(r"https?://([^/\"' )]+)", html))
    assert hosts <= ALLOWED_EXTERNAL_HOSTS | {"www.w3.org"}, hosts
    assert "<script src" not in html


@pytest.mark.parametrize("path", COPIES)
def test_the_page_updates_itself_when_a_new_version_is_deployed(path):
    """A home-screen app resumes with old page code; it must notice a new deployment and reload."""
    html = page(path)
    assert "function checkForNewVersion" in html and "location.reload()" in html
    assert 'cache: "no-store"' in html
    assert "!state.articleId) location.reload()" in html, "never reload under a reader with a story open"
    assert html.count("checkForNewVersion()") >= 3          # on load, on returning to the app, after closing a story


@pytest.mark.parametrize("path", COPIES)
def test_there_is_no_manual_refresh_button(path):
    html = page(path)
    assert "btn-refresh" not in html and ">Refresh<" not in html
    assert 'id="btn-share"' in html          # the Share button stays
