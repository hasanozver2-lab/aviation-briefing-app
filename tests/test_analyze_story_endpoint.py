"""Unit tests for on-demand AI story analysis endpoint and engine."""

import json
from unittest.mock import patch, MagicMock
from api import _engine as engine
from api import analyze_story


def test_analyze_single_story_with_payload():
    with patch("api.narrative.fill_pending") as mock_fill:
        def fake_fill(stories, api_key, limit):
            for s in stories:
                s["narrative_status"] = "done"
                s["why_it_matters"] = "Strategic takeaway for airline operations."
                s["detailed_analysis"] = ["Fact 1", "Fact 2"]
            return {"calls": 1, "narrated": 1, "rewritten": 0, "pending": 0, "error": ""}

        mock_fill.side_effect = fake_fill

        payload = {
            "headline": "Boeing and Airbus Sign Major Supply Chain Agreement",
            "lead": "The two aerospace manufacturers agreed on joint supplier standards.",
            "basis": "verified"
        }
        res = engine.analyze_single_story(story_id="test-story-abc", story_payload=payload)
        assert res["status"] == "ok"
        assert res["story"]["narrative_status"] == "done"
        assert res["story"]["why_it_matters"] == "Strategic takeaway for airline operations."
        assert res["story"]["story_id"] == "test-story-abc"


def test_analyze_single_story_match_in_snapshot():
    fake_snapshot = {
        "mode": "daily",
        "stories": [
            {
                "id": "story-12345",
                "story_id": "story-12345",
                "headline": "Lufthansa Expands Munich Hub Routes",
                "lead": "Lufthansa announced 10 new European routes.",
                "narrative_status": "pending"
            }
        ]
    }
    with patch.object(engine, "_read_local_briefing_cache", return_value=fake_snapshot), \
         patch.object(engine, "_write_local_briefing_cache"), \
         patch("api.narrative.fill_pending") as mock_fill:
        mock_fill.return_value = {"calls": 1, "narrated": 1, "rewritten": 0, "pending": 0, "error": ""}

        res = engine.analyze_single_story(story_id="story-12345")
        assert res["status"] == "ok"
        assert res["story"]["headline"] == "Lufthansa Expands Munich Hub Routes"


def test_analyze_story_options_handler():
    h = analyze_story.handler.__new__(analyze_story.handler)
    h.send_response = MagicMock()
    h.send_header = MagicMock()
    h.end_headers = MagicMock()

    h.do_OPTIONS()
    h.send_response.assert_called_once_with(204)
    headers = [call[0] for call in h.send_header.call_args_list]
    assert ("Access-Control-Allow-Origin", "*") in headers
