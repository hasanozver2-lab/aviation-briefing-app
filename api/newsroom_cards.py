"""Read configured newsroom cards without borrowing a neighbouring card's date or title."""

import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "newsroom_cards.json"
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class CardParser(HTMLParser):
    def __init__(self, url, rule):
        super().__init__(convert_charrefs=True)
        self.url, self.rule = url, rule
        self.stack, self.items = [], []
        self.parts, self.link = {}, ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(attrs.get("class", "").split())
        if not self.stack:
            if self.rule["container_class"] not in classes:
                return
            self.parts, self.link = {"title": [], "date": []}, ""
        field = next((name for name in self.parts if self.rule[name + "_class"] in classes), "")
        if self.rule.get("link_class") in classes:
            field = "link"
        inherited = field or (self.stack[-1][1] if self.stack else "")
        if tag == "a" and inherited in {"title", "link"} and not self.link:
            self.link = urljoin(self.url, attrs.get("href", ""))
        if tag not in VOID_TAGS:
            self.stack.append((tag, inherited))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_data(self, text):
        if self.stack and self.stack[-1][1] in self.parts:
            self.parts[self.stack[-1][1]].append(text)

    def handle_endtag(self, tag):
        positions = [index for index, entry in enumerate(self.stack) if entry[0] == tag]
        if not positions:
            return
        del self.stack[positions[-1]:]
        if self.stack:
            return
        title = " ".join("".join(self.parts["title"]).split())
        stamp = " ".join("".join(self.parts["date"]).split())
        try:
            published = datetime.strptime(stamp, self.rule["date_format"]).replace(tzinfo=timezone.utc)
        except ValueError:
            return
        parsed = urlparse(self.link)
        if title and parsed.scheme in {"http", "https"} and parsed.hostname == urlparse(self.url).hostname:
            self.items.append((title, self.link, published))


def parse_cards(page, url):
    rules = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    host_rules = rules.get(urlparse(url).hostname)
    if not host_rules:
        return []
    host_rules = host_rules if isinstance(host_rules, list) else [host_rules]
    items = []
    for rule in host_rules:
        parser = CardParser(url, rule)
        parser.feed(page)
        items.extend(parser.items)
    return list(dict.fromkeys(items))
