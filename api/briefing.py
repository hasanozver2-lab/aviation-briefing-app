"""Vercel function for the public briefing endpoint."""

from http.server import BaseHTTPRequestHandler
import json
import sys
import urllib.parse
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(API_DIR))
import _engine as engine


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        mode = query.get("mode", ["daily"])[0]
        if query.get("refresh", ["false"])[0].lower() in ("true", "1") or parsed.path.endswith("/refresh"):
            self.send_json({"error": "Briefing refreshes run in GitHub Actions."}, 405)
            return

        try:
            data = engine.get_ready_briefing(mode=mode, date=query.get("date", [None])[0], include_low=engine.wants_low(query))
            self.send_json(data, cache_control="public, s-maxage=60, stale-while-revalidate=300")
        except engine.BriefingNotFound as exc:
            self.send_json({"error": str(exc)}, 404)
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
