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


def unshorten_google_news_url(url, timeout=6, opener=None):
    """Resolve a news.google.com/rss/articles/... redirect link to its direct publisher article URL."""
    if not url or "news.google.com" not in str(url):
        return url
    import json
    import re
    import urllib.request
    _opener = opener or urllib.request.urlopen
    try:
        parsed_url = urllib.parse.urlparse(url)
        path_parts = parsed_url.path.strip("/").split("/")
        article_id = path_parts[-1] if path_parts else ""
        if not article_id:
            return url

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
        }
        rss_url = f"https://news.google.com/rss/articles/{article_id}"
        req = urllib.request.Request(rss_url, headers=headers)
        with _opener(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        sig_m = re.search(r'data-n-a-sg="([^"]+)"', html)
        ts_m = re.search(r'data-n-a-ts="([^"]+)"', html)
        if not sig_m or not ts_m:
            return url

        sig = sig_m.group(1)
        timestamp = ts_m.group(1)

        rpc_param = json.dumps([
            "garturlreq",
            [
                ["en-US", "US", ["FINANCE_TOP_INDICES", "WEB_TEST_1_0_0"], None, None, 1, 1, "US:en", None, None, None, None, None, None, None, 0, 5],
                "en-US", "US", True, [2, 4, 8], 1, True, "661099999", 0, 0, None, 0
            ],
            article_id,
            timestamp,
            sig
        ])
        body_payload = json.dumps([[["Fbv4je", rpc_param, None, "generic"]]])
        payload = urllib.parse.urlencode({"f.req": body_payload}).encode("utf-8")

        batch_headers = {
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "User-Agent": headers["User-Agent"],
            "Referer": "https://news.google.com/"
        }
        batchexecute_url = "https://news.google.com/_/DotsSplashUi/data/batchexecute?rpcids=Fbv4je"
        batch_req = urllib.request.Request(batchexecute_url, data=payload, headers=batch_headers)
        with _opener(batch_req, timeout=timeout) as response:
            resp_text = response.read().decode("utf-8", errors="replace")

        cleaned_text = resp_text.replace(")]}'", "").strip()
        json_data = json.loads(cleaned_text)
        inner_array_string = json_data[0][2]
        final_url = json.loads(inner_array_string)[1]
        if final_url and str(final_url).startswith("http"):
            return final_url
    except Exception:
        pass
    return url
