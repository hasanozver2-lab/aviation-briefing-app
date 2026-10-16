"""URL helpers shared by the engine and the story lifecycle."""

import urllib.parse


TRACKING_PARAMETERS = {"fbclid", "gclid"}


def canonicalize_url(value):
    """Lower-cased scheme/host, no fragment, no trailing slash, no utm_* / click-id parameters."""
    parsed = urllib.parse.urlsplit(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(key, val) for key, val in query if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMETERS]
    normalized_query = urllib.parse.urlencode(query)
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/") or "/", normalized_query, ""))
