"""Polite discovery and reading of publishers' PUBLIC feeds.

Rules this module enforces for every source:
* one self-identifying User-Agent (a "Mozilla/5.0 (compatible; ...)" product token that names this project and links to it; it does not
  imitate any browser), no cookies, no login, no proxy, no paywall workaround;
* robots.txt is read once per host and obeyed (a disallowed path is never requested);
* requests to one host are sequential with a pause between them; a discovery takes at most
  MAX_REQUESTS_PER_DISCOVERY requests; different hosts may run in parallel (the caller groups by host);
* only headline, link, publication time and the short feed summary are read - article pages are never fetched.

A feed counts as verified only when it is valid XML (or a sitemap / JSON-LD / dated-link list) with at least one item,
a title, a link and a date on every item, and at least one item from the last 90 days.
"""

import html as html_lib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

try:
    from .newsroom_cards import parse_cards
except ImportError:
    from newsroom_cards import parse_cards

USER_AGENT = "Mozilla/5.0 (compatible; aviation-briefing-app/1.0; +https://github.com/hasanozver2-lab/aviation-briefing-app)"
ROBOTS_TOKEN = "aviation-briefing-app"      # the product token robots.txt groups are matched against
MAX_REQUESTS_PER_DISCOVERY = 14
SAME_HOST_GAP_SECONDS = 1.0
VALID_WINDOW_DAYS = 90
MAX_BODY_BYTES = 3_000_000
KNOWN_FEED_PATHS = ("/feed", "/feed/", "/rss", "/rss.xml", "/atom.xml")
SITEMAP_PATHS = ("/news-sitemap.xml", "/sitemap.xml")
METHOD_RSS, METHOD_ATOM, METHOD_SITEMAP, METHOD_JSONLD, METHOD_HTML, METHOD_JSON_API = "rss", "atom", "sitemap", "jsonld", "html", "json_api"
NEWS_SITEMAP_NS = "http://www.google.com/schemas/sitemap-news/0.9"

STATUS_FOUND = "found"
STATUS_NO_FEED = "no_extractable_feed"
STATUS_BLOCKED = "disabled_blocked"
STATUS_ROBOTS = "excluded_policy"


@dataclass
class Response:
    status: int = 0
    body: bytes = b""
    headers: dict = field(default_factory=dict)
    final_url: str = ""
    seconds: float = 0.0
    error: str = ""


@dataclass
class Item:
    title: str
    link: str
    published: datetime = None
    summary: str = ""


@dataclass
class DiscoveryResult:
    status: str
    feed_url: str = ""
    method: str = ""
    item_count_90d: int = 0
    items: list = field(default_factory=list)
    http_code: int = 0
    seconds: float = 0.0
    requests: int = 0
    reason: str = ""


def utc_now():
    return datetime.now(timezone.utc)


def urllib_fetch(url, headers, timeout):
    """The default transport: plain urllib with the project's headers only (no cookie jar, no proxy configuration of ours)."""
    started = time.monotonic()
    if urllib.parse.urlparse(url).scheme not in ("http", "https") or not urllib.parse.urlparse(url).netloc:
        return Response(0, b"", {}, url, 0.0, "InvalidURL")
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as reply:
            body = reply.read(MAX_BODY_BYTES)
            return Response(reply.status, body, dict(reply.headers), reply.geturl(), time.monotonic() - started)
    except urllib.error.HTTPError as exc:
        return Response(exc.code, b"", dict(exc.headers or {}), url, time.monotonic() - started, f"HTTPError {exc.code}")
    except Exception as exc:  # timeouts, resets, DNS: the name is what the report needs
        return Response(0, b"", {}, url, time.monotonic() - started, type(exc).__name__)


class RobotsRules:
    """robots.txt per RFC 9309: user-agent groups, Allow/Disallow with * and $ wildcards, the longest matching rule wins
    (Allow wins a tie). The standard library parser ignores wildcards, so "Disallow: */feed" would never match there."""

    def __init__(self, lines=()):
        self.groups = []                       # [(set of lower-case agent tokens, [(allow, pattern)])]
        agents, rules, in_rules = set(), [], False
        for raw in lines:
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            field, value = (part.strip() for part in line.split(":", 1))
            field = field.lower()
            if field == "user-agent":
                if in_rules:
                    self.groups.append((agents, rules))
                    agents, rules, in_rules = set(), [], False
                agents.add(value.lower())
            elif field in ("allow", "disallow"):
                in_rules = True
                if value:
                    rules.append((field == "allow", value))
        if agents:
            self.groups.append((agents, rules))

    def rules_for(self, token):
        token = token.lower()
        specific = [rules for agents, rules in self.groups if any(agent and agent in token for agent in agents if agent != "*")]
        generic = [rules for agents, rules in self.groups if "*" in agents]
        return [rule for group in (specific or generic) for rule in group]

    @staticmethod
    def _matches(pattern, target):
        regex = "".join(".*" if char == "*" else re.escape(char) for char in pattern.rstrip("$"))
        return re.match(regex + ("$" if pattern.endswith("$") else ""), target) is not None

    def can_fetch(self, token, url):
        parsed = urllib.parse.urlparse(url)
        target = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
        best = None                            # (pattern length, allow)
        for allow, pattern in self.rules_for(token):
            if self._matches(pattern, target):
                candidate = (len(pattern), allow)
                if best is None or candidate[0] > best[0] or (candidate[0] == best[0] and allow):
                    best = candidate
        return True if best is None else best[1]


class PoliteFetcher:
    """Sequential, throttled, robots-aware reader for ONE host at a time (callers run hosts in parallel, never one host twice)."""

    def __init__(self, fetch=urllib_fetch, timeout=10, gap_seconds=SAME_HOST_GAP_SECONDS, sleep=time.sleep, validators=None):
        self.fetch, self.timeout, self.gap, self.sleep = fetch, timeout, gap_seconds, sleep
        self.validators = validators if validators is not None else {}     # url -> {"etag", "last_modified"} kept in memory for the run
        self.requests = 0
        self._last_request_at = {}
        self._robots = {}

    def headers(self, url, conditional=True):
        headers = {"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/html;q=0.8, */*;q=0.5"}
        known = self.validators.get(url) if conditional else None
        if known:
            if known.get("etag"):
                headers["If-None-Match"] = known["etag"]
            if known.get("last_modified"):
                headers["If-Modified-Since"] = known["last_modified"]
        return headers

    def get(self, url, conditional=False):
        host = urllib.parse.urlparse(url).hostname or ""
        wait = self.gap - (time.monotonic() - self._last_request_at.get(host, -1e9))
        if wait > 0:
            self.sleep(wait)
        self._last_request_at[host] = time.monotonic()
        self.requests += 1
        response = self.fetch(url, self.headers(url, conditional), self.timeout)
        self._last_request_at[host] = time.monotonic()
        if response.status == 200:
            self.validators[url] = {"etag": response.headers.get("ETag", ""), "last_modified": response.headers.get("Last-Modified", "")}
        return response

    def robots_for(self, url):
        parsed = urllib.parse.urlparse(url)
        if not (parsed.scheme in ("http", "https") and parsed.netloc):
            return RobotsRules(), [], "invalid url"
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots:
            response = self.get(f"{origin}/robots.txt")
            sitemaps = []
            if response.status == 200:
                lines = response.body.decode("utf-8", errors="replace").splitlines()
                sitemaps = [urllib.parse.urljoin(origin + "/", line.split(":", 1)[1].strip()) for line in lines if line.lower().startswith("sitemap:")]
                self._robots[origin] = (RobotsRules(lines), sitemaps, "read")
            else:
                # 4xx: no restrictions (RFC 9309); unreachable: nothing to obey, noted in the report
                self._robots[origin] = (RobotsRules(), sitemaps, f"robots.txt {response.status or response.error}")
        return self._robots[origin]

    def allowed(self, url):
        parser, _, _ = self.robots_for(url)
        return parser.can_fetch(ROBOTS_TOKEN, url)

    def robots_note(self, url):
        return self.robots_for(url)[2]

    def sitemaps(self, url):
        return self.robots_for(url)[1]


# ------------------------------------------------------------------------------------------------ parsing

def parse_datetime(value):
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError, OverflowError):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _local(tag):
    return tag.rsplit("}", 1)[-1].lower()


def _text(element, names):
    for child in element:
        if _local(child.tag) in names:
            value = "".join(child.itertext()).strip()
            if value:
                return value
    return ""


def _link(entry):
    link = _text(entry, {"link"})
    if link:
        return link
    for child in entry:
        if _local(child.tag) == "link" and child.attrib.get("href") and child.attrib.get("rel", "alternate") == "alternate":
            return child.attrib["href"].strip()
    return ""


def clean_text(value):
    return " ".join(html_lib.unescape(re.sub(r"<.*?>", " ", value or "")).split())


def safe_xml_root(content):
    """Parse feed XML; documents declaring entities are refused (entity-expansion attacks)."""
    if b"<!ENTITY" in content[:5000].upper() or b"<!DOCTYPE" in content[:200].upper() and b"[" in content[:2000]:
        raise ValueError("DTD with entities refused")
    return ET.fromstring(content)


def parse_feed(content):
    """(method, items) for RSS 2.0, RSS 1.0 (RDF) and Atom; raises ValueError for anything else."""
    root = safe_xml_root(content)
    name = _local(root.tag)
    if name == "rss":
        channel = next((child for child in root if _local(child.tag) == "channel"), None)
        entries = [child for child in (channel if channel is not None else []) if _local(child.tag) == "item"]
        method = METHOD_RSS
    elif name == "feed":
        entries, method = [child for child in root if _local(child.tag) == "entry"], METHOD_ATOM
    elif name == "rdf":
        entries, method = [child for child in root if _local(child.tag) == "item"], METHOD_RSS
    else:
        raise ValueError(f"not a feed: <{name}>")
    items = [Item(clean_text(_text(entry, {"title"})), _link(entry), parse_datetime(_text(entry, {"pubdate", "published", "updated", "date", "issued"})),
                  clean_text(_text(entry, {"description", "summary", "content"}))) for entry in entries]
    return method, items


def parse_sitemap(content):
    """('index', [sitemap urls]) or ('urlset', [Item]). A plain sitemap has no titles, so only news sitemaps yield usable items."""
    root = safe_xml_root(content)
    if _local(root.tag) == "sitemapindex":
        return "index", [_text(child, {"loc"}) for child in root if _local(child.tag) == "sitemap"]
    items = []
    for url in (child for child in root if _local(child.tag) == "url"):
        news = next((child for child in url if _local(child.tag) == "news"), None)
        title = clean_text(_text(news, {"title"})) if news is not None else ""
        published = parse_datetime(_text(news, {"publication_date"}) if news is not None else "") or parse_datetime(_text(url, {"lastmod"}))
        items.append(Item(title, _text(url, {"loc"}), published))
    return "urlset", items


JSONLD_PATTERN = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)
ARTICLE_TYPES = {"newsarticle", "article", "blogposting", "reportage", "analysisnewsarticle"}


def _walk_jsonld(node, out):
    if isinstance(node, list):
        for child in node:
            _walk_jsonld(child, out)
    elif isinstance(node, dict):
        kinds = node.get("@type")
        kinds = [kinds] if isinstance(kinds, str) else (kinds or [])
        if any(str(kind).lower() in ARTICLE_TYPES for kind in kinds):
            out.append(Item(clean_text(node.get("headline") or node.get("name") or ""), str(node.get("url") or (node.get("mainEntityOfPage") if isinstance(node.get("mainEntityOfPage"), str) else "") or ""),
                            parse_datetime(node.get("datePublished") or node.get("dateCreated"))))
        for key in ("itemListElement", "@graph", "item", "mainEntity", "hasPart"):
            if key in node:
                _walk_jsonld(node[key], out)


def parse_jsonld(page):
    items = []
    for block in JSONLD_PATTERN.findall(page):
        try:
            _walk_jsonld(json.loads(html_lib.unescape(block.strip())), items)
        except ValueError:
            continue
    return items


def parse_public_json_api(content, base_url):
    """Read explicitly configured publisher APIs that expose public newsroom metadata."""
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return []
    rows = payload.get("GetPressReleaseListResult") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        stamp = row.get("PressReleaseDate") or ""
        try:
            published = datetime.strptime(stamp, "%m/%d/%Y %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            published = parse_datetime(stamp)
        items.append(Item(
            clean_text(row.get("Headline") or ""),
            urllib.parse.urljoin(base_url, row.get("LinkToDetailPage") or row.get("LinkToUrl") or ""),
            published,
            clean_text(row.get("ShortDescription") or row.get("ShortBody") or ""),
        ))
    return items


ANCHOR_PATTERN = re.compile(r"<a\b([^>]*)>(.*?)</a\s*>", re.IGNORECASE | re.DOTALL)
TIME_PATTERN = re.compile(r'<time\b[^>]*datetime=["\']([^"\']+)["\']', re.IGNORECASE)
MIN_LINK_TEXT = 20


def parse_dated_links(page, base_url):
    """Anchors with a readable title that sit next to a <time datetime> element (a dated list of news links)."""
    cards = parse_cards(page, base_url)
    if cards:
        return [Item(title, link, published) for title, link, published in cards]
    items = []
    for match in ANCHOR_PATTERN.finditer(page):
        href = re.search(r'href=["\']([^"\']+)["\']', match.group(1))
        title = clean_text(match.group(2))
        if not href or len(title) < MIN_LINK_TEXT or href.group(1).startswith(("#", "mailto:", "javascript:")):
            continue
        window = page[max(0, match.start() - 400): match.end() + 400]
        stamp = TIME_PATTERN.search(window)
        if stamp:
            items.append(Item(title, urllib.parse.urljoin(base_url, href.group(1)), parse_datetime(stamp.group(1))))
    return items


ALTERNATE_PATTERN = re.compile(r"<link\b[^>]*>", re.IGNORECASE)


def alternate_feed_links(page, base_url):
    """link rel=alternate type=application/rss+xml|atom+xml targets, in page order."""
    found = []
    for tag in ALTERNATE_PATTERN.findall(page):
        if re.search(r'rel=["\']alternate["\']', tag, re.IGNORECASE) and re.search(r'type=["\']application/(rss|atom)\+xml["\']', tag, re.IGNORECASE):
            href = re.search(r'href=["\']([^"\']+)["\']', tag)
            if href:
                found.append(urllib.parse.urljoin(base_url, html_lib.unescape(href.group(1))))
    return list(dict.fromkeys(found))


RSS_PAGE_HINT = re.compile(r'href=["\']([^"\']*(?:rss|feeds?)(?:[/.\-_][^"\']*)?)["\']', re.IGNORECASE)


def official_rss_page_links(page, base_url):
    """Links to the publisher's own RSS/feeds page (not the feeds themselves), e.g. /rss-subscription."""
    links = [urllib.parse.urljoin(base_url, html_lib.unescape(href)) for href in RSS_PAGE_HINT.findall(page)]
    return list(dict.fromkeys(link for link in links if not link.lower().endswith((".png", ".jpg", ".svg", ".css", ".js"))))[:2]


# ------------------------------------------------------------------------------------------------ validation

def validate_items(items, now=None, window_days=VALID_WINDOW_DAYS):
    """(is_valid, item_count_in_window, reason). Every item needs title, link and date; one item must be recent."""
    now = now or utc_now()
    if not items:
        return False, 0, "no items"
    incomplete = [item for item in items if not (item.title and item.link and item.published)]
    if incomplete:
        return False, 0, f"{len(incomplete)} of {len(items)} items lack title, link or date"
    recent = sum(1 for item in items if now - item.published <= timedelta(days=window_days))
    return (recent >= 1), recent, "" if recent else f"no item in the last {window_days} days"


# ------------------------------------------------------------------------------------------------ discovery

def classify_body(body, url):
    """Read a fetched body as a feed, news sitemap, JSON-LD list or dated links. Returns (method, items)."""
    head = body[:600].lstrip().lower()
    if head.startswith((b"{", b"[")):
        json_items = parse_public_json_api(body, url)
        if json_items:
            return METHOD_JSON_API, json_items
    try:
        if b"<rss" in head or b"<feed" in head or b"<rdf:rdf" in head or (head.startswith(b"<?xml") and b"<urlset" not in body[:3000] and b"<sitemapindex" not in body[:3000]):
            return parse_feed(body)
        if b"<urlset" in body[:3000] or b"<sitemapindex" in body[:3000]:
            kind, items = parse_sitemap(body)
            return (METHOD_SITEMAP, items) if kind == "urlset" else ("sitemap_index", items)
    except (ET.ParseError, ValueError):
        return None, []
    page = body.decode("utf-8", errors="replace")
    jsonld = parse_jsonld(page)
    if jsonld:
        return METHOD_JSONLD, jsonld
    return METHOD_HTML, parse_dated_links(page, url)


def items_from_url(fetcher, url):
    """Fetch one candidate address and read it. Returns (method, items, response); method is None when it is unreadable."""
    response = fetcher.get(url)
    if response.status != 200:
        return None, [], response
    method, items = classify_body(response.body, response.final_url or url)
    return method, items, response


FEED_METHODS = (METHOD_RSS, METHOD_ATOM, METHOD_SITEMAP)
DIRECT_STRUCTURED_METHODS = FEED_METHODS + (METHOD_JSON_API,)


FEED_ONLY_METHODS = (METHOD_RSS, METHOD_ATOM)      # press/data sources: only the publisher's own public RSS/Atom feed, never a sitemap or page scrape


def discover(fetcher, urls, now=None, max_requests=MAX_REQUESTS_PER_DISCOVERY, explicit_feed_url=None, allowed_methods=None):
    """Find a verified public feed for a publisher. `urls` are the page addresses to start from; the order is the preference.

    Result precedence: a verified feed wins; otherwise "blocked" if the site refused us (401/403/429/timeout) on the way;
    otherwise "excluded_policy" if robots.txt forbade every page we were asked to read or a feed the page itself advertises;
    otherwise "no_extractable_feed".
    """
    now = now or utc_now()
    started = fetcher.requests
    method_ok = lambda method: allowed_methods is None or method in allowed_methods
    state = {"blocked": None, "robots": None, "last": Response()}
    path_of = lambda url: urllib.parse.urlparse(url).path or "/"

    def spent():
        return fetcher.requests - started

    def found(outcome):
        outcome.requests = spent()
        return outcome

    def robots_reason(url):
        return f"robots.txt disallows {path_of(url)} for {ROBOTS_TOKEN}"

    def try_candidate(url, advertised):
        """Read one candidate as a feed/sitemap. Only candidates the publisher itself points to count as a robots exclusion."""
        if spent() >= max_requests:
            return None
        if not fetcher.allowed(url):
            if advertised:
                state["robots"] = state["robots"] or robots_reason(url)
            return None
        method, items, response = items_from_url(fetcher, url)
        state["last"] = response
        if method == "sitemap_index":
            method = None
            for child in items[:2]:
                if spent() >= max_requests or not fetcher.allowed(child):
                    break
                child_method, child_items, response = items_from_url(fetcher, child)
                if child_method == METHOD_SITEMAP:
                    method, items = child_method, child_items
                    break
        if method is None or not method_ok(method):
            return None
        ok, recent, _ = validate_items(items, now)
        return found(DiscoveryResult(STATUS_FOUND, url, method, recent, items, response.status, response.seconds)) if ok else None

    pages = list(dict.fromkeys(urls))
    pages_html, advertised, guessed = {}, [explicit_feed_url] if explicit_feed_url else [], []
    disallowed_pages = 0
    for page_url in pages:
        origin = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(page_url))
        guessed += [origin + path for path in KNOWN_FEED_PATHS]
        if not fetcher.allowed(page_url):
            disallowed_pages += 1
            state["robots"] = state["robots"] or robots_reason(page_url)
            continue
        if spent() >= max_requests:
            break
        response = fetcher.get(page_url)
        state["last"] = response
        if response.status in (401, 403, 429) or (response.status == 0 and response.error):
            state["blocked"] = DiscoveryResult(STATUS_BLOCKED, http_code=response.status, seconds=response.seconds,
                                               reason=f"{response.error or response.status} on {path_of(page_url)}")
        elif response.status == 200:
            method, items = classify_body(response.body, response.final_url or page_url)
            if method in DIRECT_STRUCTURED_METHODS:          # the address itself is a feed/API (e.g. SEC Atom or a public newsroom API)
                ok, recent, _ = validate_items(items, now)
                if ok and method_ok(method):
                    return found(DiscoveryResult(STATUS_FOUND, page_url, method, recent, items, response.status, response.seconds))
                continue
            pages_html[page_url] = response.body.decode("utf-8", errors="replace")
            advertised += alternate_feed_links(pages_html[page_url], response.final_url or page_url)
    all_pages_disallowed = bool(pages) and disallowed_pages == len(pages)
    seen = set()
    for url, is_advertised in [(u, True) for u in advertised] + [(u, False) for u in guessed]:
        if url in seen or all_pages_disallowed or urllib.parse.urlparse(url).scheme not in ("http", "https"):
            continue
        seen.add(url)
        outcome = try_candidate(url, is_advertised)
        if outcome:
            return outcome
    for page_url, page in pages_html.items():
        for rss_page in official_rss_page_links(page, page_url):
            if rss_page in seen or spent() >= max_requests or not fetcher.allowed(rss_page):
                continue
            seen.add(rss_page)
            rss_response = fetcher.get(rss_page)
            if rss_response.status == 200:
                for feed_url in alternate_feed_links(rss_response.body.decode("utf-8", errors="replace"), rss_page)[:3]:
                    outcome = try_candidate(feed_url, True)
                    if outcome:
                        return outcome
    first = pages[0] if pages and not all_pages_disallowed else ""
    sitemap_urls = []
    if first:
        origin = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(first))
        sitemap_urls = fetcher.sitemaps(first)[:2] + [origin + path for path in SITEMAP_PATHS]
    for url in dict.fromkeys(sitemap_urls):
        if url in seen:
            continue
        seen.add(url)
        outcome = try_candidate(url, False)
        if outcome:
            return outcome
    for page_url, page in pages_html.items():
        for method, items in ((METHOD_JSONLD, parse_jsonld(page)), (METHOD_HTML, parse_dated_links(page, page_url))):
            ok, recent, _ = validate_items(items, now)
            if ok and method_ok(method):
                return found(DiscoveryResult(STATUS_FOUND, page_url, method, recent, items, 200, state["last"].seconds))
    if state["blocked"] and not pages_html:
        return found(state["blocked"])
    if state["robots"]:
        return found(DiscoveryResult(STATUS_ROBOTS, reason=state["robots"], http_code=state["last"].status))
    return found(DiscoveryResult(STATUS_NO_FEED, http_code=state["last"].status, seconds=state["last"].seconds,
                                 reason="no feed, news sitemap, JSON-LD or dated links found"))
