import urllib.error
from pathlib import Path

from api import _engine

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "briefing-pipeline.yml"


def test_an_http_failure_is_logged_with_its_status_code():
    assert _engine.describe_fetch_error(urllib.error.HTTPError("u", 403, "Forbidden", {}, None)) == "HTTPError 403"
    assert _engine.describe_fetch_error(urllib.error.HTTPError("u", 404, "Not Found", {}, None)) == "HTTPError 404"


def test_other_failures_keep_their_type_name():
    assert _engine.describe_fetch_error(TimeoutError()) == "TimeoutError"
    assert _engine.describe_fetch_error(urllib.error.URLError(ConnectionResetError())) == "URLError (ConnectionResetError)"


def test_the_workflow_asks_more_than_once_an_hour_and_never_overlaps():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert 'cron: "7,22,37,52 * * * *"' in text
    assert "group: aerobrief-publish" in text and "cancel-in-progress: false" in text
