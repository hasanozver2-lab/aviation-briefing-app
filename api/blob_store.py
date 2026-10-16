"""Small Vercel Blob adapter used by the GitHub Actions briefing pipeline."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request


BLOB_API_URL = "https://blob.vercel-storage.com"
BRIEFING_PREFIX = "briefings"


def _env_value(name):
    return os.environ.get(name, "").strip()


def public_base_url():
    return _env_value("BLOB_PUBLIC_BASE_URL").rstrip("/")


def _safe_path(pathname):
    normalized = str(pathname or "").strip().lstrip("/")
    if not normalized or ".." in normalized.split("/"):
        raise ValueError("invalid blob pathname")
    return normalized


def public_url(pathname):
    base_url = public_base_url()
    if not base_url:
        return ""
    return f"{base_url}/{urllib.parse.quote(_safe_path(pathname), safe='/')}"


def briefing_path(mode):
    if mode not in {"daily", "hourly"}:
        raise ValueError("mode must be either 'daily' or 'hourly'")
    return f"{BRIEFING_PREFIX}/{mode}.json"


def pipeline_status_path(mode):
    if mode not in {"daily", "hourly"}:
        raise ValueError("mode must be either 'daily' or 'hourly'")
    return f"{BRIEFING_PREFIX}/{mode}-status.json"


def get_public_json(pathname, timeout=8):
    """Read a public Blob object. The deployed API needs no write token."""
    url = public_url(pathname)
    if not url:
        return None
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def put_public_json(pathname, payload, timeout=20):
    """Overwrite a stable public Blob pathname from the scheduled job."""
    token = _env_value("BLOB_READ_WRITE_TOKEN")
    if not token:
        raise RuntimeError("BLOB_READ_WRITE_TOKEN is required to publish a briefing")

    encoded_path = urllib.parse.quote(_safe_path(pathname), safe="/")
    request = urllib.request.Request(
        f"{BLOB_API_URL}/{encoded_path}",
        data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
            "x-content-type": "application/json; charset=utf-8",
            "x-api-version": "7",
            "x-add-random-suffix": "0",
            "x-allow-overwrite": "1",
            "x-cache-control-max-age": "60",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read().decode("utf-8") or "{}")
    return result
