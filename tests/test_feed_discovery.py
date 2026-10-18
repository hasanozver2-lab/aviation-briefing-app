from datetime import datetime, timedelta, timezone

import pytest

from api import feed_discovery as fd
from api import newsroom_cards

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
RECENT = (NOW - timedelta(days=2)).strftime("%a, %d %b %Y %H:%M:%S +0000")
OLD = (NOW - timedelta(days=200)).strftime("%a, %d %b %Y %H:%M:%S +0000")
ISO_RECENT = (NOW - timedelta(days=1)).isoformat()


def rss(items):
    body = "".join(f"<item><title>{t}</title><link>{l}</link>{f'<pubDate>{d}</pubDate>' if d else ''}<description>short summary</description></item>" for t, l, d in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{body}</channel></rss>'.encode()


GOOD_RSS = rss([("Airline opens new route to Tokyo", "https://pub.example/a1", RECENT), ("Fleet order announced", "https://pub.example/a2", RECENT)])


class Site:
    """A fake network: {url: (status, body)}; records every request with its headers."""

    def __init__(self, pages):
        self.pages = pages
        self.log = []

    def __call__(self, url, headers, timeout):
        self.log.append((url, dict(headers)))
        status, body = self.pages.get(url, (404, b""))
        return fd.Response(status, body if isinstance(body, bytes) else body.encode(), {"ETag": '"abc"'} if status == 200 else {}, url, 0.01,
                           "" if status == 200 else f"HTTPError {status}")

    @property
    def urls(self):
        return [url for url, _ in self.log]


def fetcher_for(site, **kwargs):
    return fd.PoliteFetcher(fetch=site, sleep=lambda seconds: None, **kwargs)


def run(site, urls=("https://pub.example/",), **kwargs):
    return fd.discover(fetcher_for(site), list(urls), now=NOW, **kwargs)


HOME_WITH_ALTERNATE = '<html><head><link rel="alternate" type="application/rss+xml" href="/custom/news.xml"></head><body></body></html>'


def test_a_link_rel_alternate_feed_is_found_and_verified():
    site = Site({"https://pub.example/": (200, HOME_WITH_ALTERNATE), "https://pub.example/custom/news.xml": (200, GOOD_RSS)})
    result = run(site)
    assert (result.status, result.method, result.feed_url, result.item_count_90d) == (fd.STATUS_FOUND, "rss", "https://pub.example/custom/news.xml", 2)


def test_known_paths_are_tried_when_the_page_advertises_nothing():
    site = Site({"https://pub.example/": (200, "<html></html>"), "https://pub.example/rss.xml": (200, GOOD_RSS)})
    assert run(site).feed_url == "https://pub.example/rss.xml"


def test_an_atom_feed_is_read():
    atom = (f'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Regulator publishes safety notice</title><link href="https://pub.example/n1"/>'
            f'<updated>{ISO_RECENT}</updated><summary>s</summary></entry></feed>').encode()
    site = Site({"https://pub.example/": (200, "<html></html>"), "https://pub.example/atom.xml": (200, atom)})
    result = run(site)
    assert result.method == "atom" and result.items[0].link == "https://pub.example/n1"


def test_every_item_needs_a_title_a_link_and_a_date():
    undated = rss([("Has a date", "https://pub.example/a", RECENT), ("No date here", "https://pub.example/b", None)])
    site = Site({"https://pub.example/": (200, "<html></html>"), "https://pub.example/feed": (200, undated)})
    result = run(site)
    assert result.status == fd.STATUS_NO_FEED
    ok, _, reason = fd.validate_items(fd.parse_feed(undated)[1], NOW)
    assert not ok and "lack title, link or date" in reason


def test_a_feed_with_nothing_in_the_last_90_days_is_not_verified():
    stale = rss([("Old news", "https://pub.example/o", OLD)])
    ok, recent, reason = fd.validate_items(fd.parse_feed(stale)[1], NOW)
    assert not ok and recent == 0 and "90 days" in reason
    site = Site({"https://pub.example/": (200, "<html></html>"), "https://pub.example/feed": (200, stale)})
    assert run(site).status == fd.STATUS_NO_FEED


def test_invalid_xml_and_non_feeds_are_not_verified():
    site = Site({"https://pub.example/": (200, "<html></html>"), "https://pub.example/feed": (200, b"<rss><channel><item>")})
    assert run(site).status == fd.STATUS_NO_FEED


def test_a_dtd_with_entities_is_refused():
    bomb = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa">]><rss><channel><item><title>&a;</title></item></channel></rss>'
    with pytest.raises(ValueError):
        fd.parse_feed(bomb)


# --- politeness ---------------------------------------------------------------------------------------------------------

def test_robots_txt_is_obeyed_and_a_disallowed_page_is_never_requested():
    site = Site({"https://pub.example/robots.txt": (200, "User-agent: *\nDisallow: /newsroom"), "https://pub.example/newsroom/": (200, HOME_WITH_ALTERNATE)})
    result = run(site, urls=("https://pub.example/newsroom/",))
    assert result.status == fd.STATUS_ROBOTS and "/newsroom/" in result.reason
    assert "https://pub.example/newsroom/" not in site.urls


def test_a_disallowed_guess_does_not_exclude_a_source_whose_page_advertises_an_allowed_feed():
    site = Site({"https://pub.example/robots.txt": (200, "User-agent: *\nDisallow: /feed"), "https://pub.example/": (200, HOME_WITH_ALTERNATE),
                 "https://pub.example/custom/news.xml": (200, GOOD_RSS)})
    result = run(site)
    assert result.status == fd.STATUS_FOUND and "https://pub.example/feed" not in site.urls


def test_robots_that_forbids_the_advertised_feed_excludes_the_source():
    site = Site({"https://pub.example/robots.txt": (200, "User-agent: *\nDisallow: /custom"), "https://pub.example/": (200, HOME_WITH_ALTERNATE)})
    result = run(site)
    assert result.status == fd.STATUS_ROBOTS and "https://pub.example/custom/news.xml" not in site.urls


def test_a_403_is_reported_as_blocked_with_the_code():
    site = Site({"https://pub.example/": (403, b"")})
    result = run(site)
    assert result.status == fd.STATUS_BLOCKED and "403" in result.reason


def test_a_timeout_is_reported_as_blocked():
    def slow(url, headers, timeout):
        return fd.Response(0, b"", {}, url, 3.0, "TimeoutError")
    result = fd.discover(fd.PoliteFetcher(fetch=slow, sleep=lambda s: None), ["https://pub.example/"], now=NOW)
    assert result.status == fd.STATUS_BLOCKED and "TimeoutError" in result.reason


def test_the_user_agent_identifies_the_project_and_no_cookie_or_login_headers_are_sent():
    site = Site({"https://pub.example/": (200, HOME_WITH_ALTERNATE), "https://pub.example/custom/news.xml": (200, GOOD_RSS)})
    run(site)
    expected = "Mozilla/5.0 (compatible; aviation-briefing-app/1.0; +https://github.com/hasanozver2-lab/aviation-briefing-app)"
    assert fd.USER_AGENT == expected
    for _, headers in site.log:
        assert headers["User-Agent"] == expected
        assert not {"Cookie", "Authorization", "Referer"} & set(headers)
    assert "@" not in expected, "no e-mail address in the User-Agent"
    assert fd.ROBOTS_TOKEN in expected and "github.com/hasanozver2-lab/aviation-briefing-app" in expected, "it names the project and links to it"
    assert not any(browser in expected for browser in ("Chrome", "Safari", "Firefox", "AppleWebKit", "Gecko", "Windows", "Macintosh")), "it never imitates a browser"


def test_conditional_headers_are_sent_when_validators_are_known():
    site = Site({"https://pub.example/feed": (200, GOOD_RSS)})
    fetcher = fetcher_for(site, validators={"https://pub.example/feed": {"etag": '"abc"', "last_modified": "Fri, 16 Oct 2026 10:00:00 GMT"}})
    fetcher.get("https://pub.example/feed", conditional=True)
    headers = site.log[-1][1]
    assert headers["If-None-Match"] == '"abc"' and headers["If-Modified-Since"] == "Fri, 16 Oct 2026 10:00:00 GMT"


def test_requests_to_one_host_are_spaced_out():
    site, pauses = Site({"https://pub.example/a": (200, b""), "https://pub.example/b": (200, b"")}), []
    fetcher = fd.PoliteFetcher(fetch=site, gap_seconds=1.0, sleep=pauses.append)
    fetcher.get("https://pub.example/a")
    fetcher.get("https://pub.example/b")
    assert len(pauses) >= 1 and all(0 < pause <= 1.0 for pause in pauses)


def test_a_discovery_never_exceeds_its_request_budget():
    site = Site({"https://pub.example/": (200, "<html></html>")})
    fetcher = fetcher_for(site)
    fd.discover(fetcher, ["https://pub.example/"], now=NOW, max_requests=5)
    assert fetcher.requests <= 6          # budget plus the robots.txt read


def test_article_pages_listed_in_a_feed_are_never_requested():
    site = Site({"https://pub.example/": (200, HOME_WITH_ALTERNATE), "https://pub.example/custom/news.xml": (200, GOOD_RSS)})
    result = run(site)
    assert result.status == fd.STATUS_FOUND
    assert not any(url.startswith("https://pub.example/a") for url in site.urls)


# --- the other methods --------------------------------------------------------------------------------------------------

NEWS_SITEMAP = (f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="{fd.NEWS_SITEMAP_NS}"><url><loc>https://pub.example/n1</loc>'
                f'<news:news><news:publication_date>{ISO_RECENT}</news:publication_date><news:title>Airline signs engine deal</news:title></news:news></url></urlset>').encode()
PLAIN_SITEMAP = f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://pub.example/n1</loc><lastmod>{ISO_RECENT}</lastmod></url></urlset>'.encode()


def test_a_news_sitemap_with_titles_is_accepted():
    site = Site({"https://pub.example/": (200, "<html></html>"), "https://pub.example/news-sitemap.xml": (200, NEWS_SITEMAP)})
    result = run(site)
    assert result.method == "sitemap" and result.items[0].title == "Airline signs engine deal"


def test_a_plain_sitemap_has_no_titles_and_is_not_accepted():
    site = Site({"https://pub.example/": (200, "<html></html>"), "https://pub.example/sitemap.xml": (200, PLAIN_SITEMAP)})
    assert run(site).status == fd.STATUS_NO_FEED


def test_a_sitemap_index_is_followed_one_level():
    index = b'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://pub.example/sm-news.xml</loc></sitemap></sitemapindex>'
    site = Site({"https://pub.example/": (200, "<html></html>"), "https://pub.example/sitemap.xml": (200, index), "https://pub.example/sm-news.xml": (200, NEWS_SITEMAP)})
    assert run(site).method == "sitemap"


JSONLD_PAGE = ('<html><script type="application/ld+json">{"@context":"https://schema.org","@type":"ItemList","itemListElement":['
               f'{{"@type":"NewsArticle","headline":"Regulator fines carrier over delays","url":"https://pub.example/x","datePublished":"{ISO_RECENT}"}}]}}</script></html>')


def test_json_ld_news_articles_are_used_when_there_is_no_feed():
    site = Site({"https://pub.example/": (200, JSONLD_PAGE)})
    result = run(site)
    assert result.method == "jsonld" and result.items[0].title == "Regulator fines carrier over delays"


def test_a_configured_public_q4_newsroom_api_is_read_without_fetching_articles():
    api_url = "https://pub.example/feed/PressRelease.svc/GetPressReleaseList?LanguageId=1"
    body = b'{"GetPressReleaseListResult":[{"Headline":"Airline adds Tokyo route","LinkToDetailPage":"/news/route","PressReleaseDate":"10/16/2026 09:00:00","ShortDescription":"Daily service"}]}'
    site = Site({api_url: (200, body)})
    result = run(site, urls=(api_url,))
    assert result.method == fd.METHOD_JSON_API
    assert result.items[0].link == "https://pub.example/news/route"
    assert result.items[0].summary == "Daily service"
    assert site.urls == ["https://pub.example/robots.txt", api_url]


def test_configured_newsroom_cards_can_keep_title_date_and_link_in_separate_fields(monkeypatch, tmp_path):
    config = tmp_path / "cards.json"
    config.write_text('{"pub.example":{"container_class":"news-card","title_class":"headline","date_class":"date","link_class":"footer","date_format":"%d %B %Y"}}', encoding="utf-8")
    monkeypatch.setattr(newsroom_cards, "CONFIG_PATH", config)
    page = '<div class="news-card"><div class="date">16 October 2026</div><div class="headline"><h3>Airline adds Tokyo route</h3></div><div class="footer"><a href="/news/route">Learn more</a></div></div>'
    items = fd.parse_dated_links(page, "https://pub.example/newsroom")
    assert [(item.title, item.link) for item in items] == [("Airline adds Tokyo route", "https://pub.example/news/route")]


DATED_PAGE = f'<html><body><article><time datetime="{ISO_RECENT}">today</time><a href="/news/1">Carrier announces winter schedule changes</a></article></body></html>'


def test_dated_links_are_the_last_resort():
    site = Site({"https://pub.example/": (200, DATED_PAGE)})
    result = run(site)
    assert result.method == "html" and result.items[0].link == "https://pub.example/news/1"


def test_a_page_without_any_extractable_news_gets_no_scraper():
    site = Site({"https://pub.example/": (200, "<html><body><a href='/x'>A very long link text that is not dated at all</a></body></html>")})
    result = run(site)
    assert result.status == fd.STATUS_NO_FEED and "no feed" in result.reason


def test_the_preferred_url_is_tried_first_and_the_second_url_is_a_fallback():
    site = Site({"https://pub.example/airlines": (200, "<html></html>"), "https://pub.example/": (200, HOME_WITH_ALTERNATE), "https://pub.example/custom/news.xml": (200, GOOD_RSS)})
    result = run(site, urls=("https://pub.example/airlines", "https://pub.example/"))
    assert result.status == fd.STATUS_FOUND
    assert site.urls.index("https://pub.example/airlines") < site.urls.index("https://pub.example/")


# --- robots.txt wildcards (the standard library parser ignores them) -------------------------------------------------------

def rules(*lines):
    return fd.RobotsRules(lines)


@pytest.mark.parametrize("lines, url, allowed", [
    (["User-agent: *", "Disallow: */feed"], "https://s.example/feed", False),                    # PROS
    (["User-agent: *", "Disallow: */feed"], "https://s.example/blog/feed", False),
    (["User-agent: *", "Disallow: */feed"], "https://s.example/news", True),
    (["User-agent: *", "Disallow: /*.rss"], "https://s.example/hub/aviation.rss", False),         # AP
    (["User-agent: *", "Disallow: /*.rss"], "https://s.example/hub/aviation", True),
    (["User-agent: *", "Disallow: */feed*"], "https://s.example/en/feed.xml", False),             # Pegasus
    (["User-agent: *", "Disallow: /"], "https://s.example/anything", False),                      # WSJ, AvHerald, Yahoo feeds
    (["User-agent: *", "Disallow:"], "https://s.example/anything", True),
    (["User-agent: *", "Disallow: /*?"], "https://s.example/page?x=1", False),                    # Air France
    (["User-agent: *", "Disallow: /*?"], "https://s.example/page", True),
    (["User-agent: *", "Disallow: /news$"], "https://s.example/news", False),
    (["User-agent: *", "Disallow: /news$"], "https://s.example/news/today", True),
])
def test_robots_wildcards(lines, url, allowed):
    assert rules(*lines).can_fetch(fd.ROBOTS_TOKEN, url) is allowed


def test_the_longest_matching_rule_wins_and_allow_wins_a_tie():
    r = rules("User-agent: *", "Disallow: /news", "Allow: /news/public")
    assert r.can_fetch(fd.ROBOTS_TOKEN, "https://s.example/news/public/a") and not r.can_fetch(fd.ROBOTS_TOKEN, "https://s.example/news/private")
    assert rules("User-agent: *", "Disallow: /a", "Allow: /a").can_fetch(fd.ROBOTS_TOKEN, "https://s.example/a")


def test_a_group_naming_this_bot_beats_the_generic_group():
    r = rules("User-agent: *", "Disallow: /", "", "User-agent: aviation-briefing-app", "Disallow: /private")
    assert r.can_fetch(fd.ROBOTS_TOKEN, "https://s.example/news") and not r.can_fetch(fd.ROBOTS_TOKEN, "https://s.example/private/x")
    assert not r.can_fetch("someotherbot", "https://s.example/news")


def test_other_bots_groups_do_not_apply_to_us():
    assert rules("User-agent: GPTBot", "Disallow: /").can_fetch(fd.ROBOTS_TOKEN, "https://s.example/feed")


def test_consecutive_user_agent_lines_share_one_group():
    r = rules("User-agent: gptbot", "User-agent: *", "Disallow: /x")
    assert not r.can_fetch(fd.ROBOTS_TOKEN, "https://s.example/x")


def test_the_fetcher_uses_the_wildcard_rules():
    site = Site({"https://pub.example/robots.txt": (200, "User-agent: *\nDisallow: */feed"), "https://pub.example/": (200, "<html></html>")})
    fetcher = fetcher_for(site)
    assert not fetcher.allowed("https://pub.example/feed") and fetcher.allowed("https://pub.example/news")


def test_an_invalid_or_relative_candidate_never_crashes_a_discovery():
    robots = "User-agent: *\nDisallow: /nothing\nSitemap: /relative-sitemap.xml\n"
    site = Site({"https://pub.example/robots.txt": (200, robots), "https://pub.example/": (200, "<html></html>"), "https://pub.example/relative-sitemap.xml": (200, NEWS_SITEMAP)})
    result = run(site)
    assert result.status == fd.STATUS_FOUND and result.method == "sitemap"
    assert fd.urllib_fetch("://broken", {}, 1).error == "InvalidURL"
    assert fetcher_for(site).allowed("not a url") is True
