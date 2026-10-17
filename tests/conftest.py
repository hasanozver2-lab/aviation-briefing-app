import pytest

from api import source_retry


@pytest.fixture(autouse=True)
def no_live_weekly_retry(request, monkeypatch):
    """run_pipeline.run() retries blocked sources over the network once a week; tests must never do that.
    The retry's own tests (test_source_retry.py) use the real function with an injected transport."""
    if request.module.__name__.endswith("test_source_retry"):
        return
    monkeypatch.setattr(source_retry, "retry_blocked", lambda *args, **kwargs: {})
