"""Vercel function for the public briefing endpoint."""

from http.server import BaseHTTPRequestHandler
import hmac
import json
import os
import sys
import urllib.parse
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(API_DIR))
import _engine as engine


def refresh_is_authorized(authorization_header):
    secret = os.environ.get("CRON_SECRET", "")
    if not secret:
        return False
    return hmac.compare_digest(authorization_header, f"Bearer {secret}")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        mode = query.get("mode", ["daily"])[0]
        force_refresh = (
            query.get("refresh", ["false"])[0].lower() in ("true", "1")
            or parsed.path.endswith("/refresh")
        )
        if force_refresh and not refresh_is_authorized(self.headers.get("Authorization", "")):
            self.send_json({"error": "Refresh is not authorized"}, 401)
            return

        try:
            data = engine.get_briefing(mode=mode, force_refresh=force_refresh)
            cache_control = "no-store" if force_refresh else "public, s-maxage=600, stale-while-revalidate=1800"
            self.send_json(data, cache_control=cache_control)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, 400)
        except Exception:
            self.send_json({"error": "Briefing generation failed"}, 500)

    def do_POST(self):
        self.do_GET()

    def send_json(self, data, status=200, cache_control="no-store"):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
