import xml.etree.ElementTree as ET
from api import _engine, story_lifecycle


def test_extract_entry_image_from_enclosure():
    xml = b"""<item>
        <title>Airbus A350 delivery</title>
        <link>https://example.com/a350</link>
        <enclosure url="https://example.com/images/a350.jpg" length="1024" type="image/jpeg" />
    </item>"""
    entry = ET.fromstring(xml)
    assert _engine.extract_entry_image(entry) == "https://example.com/images/a350.jpg"


def test_extract_entry_image_from_media_content():
    xml = b"""<item xmlns:media="http://search.yahoo.com/mrss/">
        <title>Boeing 777X test flight</title>
        <link>https://example.com/777x</link>
        <media:content url="https://example.com/images/777x.png" medium="image" />
    </item>"""
    entry = ET.fromstring(xml)
    assert _engine.extract_entry_image(entry) == "https://example.com/images/777x.png"


def test_extract_entry_image_from_html_description():
    xml = b"""<item>
        <title>Turkish Airlines fleet expansion</title>
        <link>https://example.com/thy</link>
        <description>&lt;p&gt;&lt;img src="https://example.com/thy-plane.webp" alt="THY" /&gt;Turkish Airlines adds new routes.&lt;/p&gt;</description>
    </item>"""
    entry = ET.fromstring(xml)
    assert _engine.extract_entry_image(entry) == "https://example.com/thy-plane.webp"


def test_extract_entry_image_ignores_audio_or_empty():
    xml = b"""<item>
        <title>Aviation podcast episode 12</title>
        <link>https://example.com/podcast</link>
        <enclosure url="https://example.com/audio.mp3" length="5000" type="audio/mpeg" />
    </item>"""
    entry = ET.fromstring(xml)
    assert _engine.extract_entry_image(entry) == ""


def test_extract_html_entries_extracts_img():
    source = {"url": "https://news.example.com", "category_hint": "European and other global airlines"}
    html = b"""<div>
        <a class="news-card" href="/article/123">
            <img src="/media/card.jpg" alt="Photo" />
            <h3>Major European Airline Earnings Record</h3>
        </a>
    </div>"""
    entries = _engine.extract_html_entries(html, source)
    assert len(entries) == 1
    assert entries[0]["image_url"] == "https://news.example.com/media/card.jpg"


def test_build_candidate_story_carries_image_url():
    article = {
        "title": "New Airport Hub Opens",
        "link": "https://example.com/hub",
        "image_url": "https://example.com/hub.jpg",
        "category_hint": "European and other global airlines",
    }
    story = _engine.build_candidate_story(article)
    assert story["image_url"] == "https://example.com/hub.jpg"


def test_enrich_stories_propagates_image_from_cluster_members():
    articles = [
        {
            "title": "Engine Manufacturer Recall",
            "link": "https://wire.com/recall-1",
            "source": "Wire A",
            "category_hint": "European and other global airlines",
            "image_url": "",
        },
        {
            "title": "Engine Manufacturer Recall",
            "link": "https://wire.com/recall-2",
            "source": "Wire B",
            "category_hint": "European and other global airlines",
            "image_url": "https://wire.com/engine.jpg",
        },
    ]
    candidates = [_engine.build_candidate_story(articles[0])]
    enriched = story_lifecycle.enrich_stories(candidates, articles)
    assert enriched[0]["image_url"] == "https://wire.com/engine.jpg"
