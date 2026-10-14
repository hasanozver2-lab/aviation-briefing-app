"""
Vercel Serverless Function Handler (/api/briefing)
7/24 Bulutta calisan REST API ve Cron tetikleyici.
"""

from http.server import BaseHTTPRequestHandler
import json
import os
import sys
import urllib.parse
from pathlib import Path

# Engine'i dahil et
API_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(API_DIR))
try:
    import _engine as engine
except ImportError:
    from . import _engine as engine

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)

        mode = query.get("mode", ["daily"])[0]
        force = query.get("refresh", ["false"])[0].lower() in ("true", "1")

        try:
            data = engine.get_briefing(mode=mode, force_refresh=force)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "public, s-maxage=1800, stale-while-revalidate=3600")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8"))

    def do_POST(self):
        self.do_GET()
