"""Vercel serverless function for on-demand AI story analysis."""

from http.server import BaseHTTPRequestHandler
import json
import sys
import urllib.parse
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(API_DIR))
try:
    import _engine as engine
except ImportError:
    from . import _engine as engine


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            req_data = json.loads(body.decode("utf-8")) if body else {}
        except json.JSONDecodeError:
            req_data = {}

        story_id = req_data.get("story_id") or query.get("story_id", [None])[0]
        headline = req_data.get("headline") or query.get("headline", [None])[0]
        story_payload = req_data.get("story")

        if not story_id and not headline and not story_payload:
            self.send_json({"error": "story_id, headline, or story payload is required"}, status=400)
            return

        try:
            result = engine.analyze_single_story(story_id=story_id, headline=headline, story_payload=story_payload)
            self.send_json(result)
        except engine.BriefingNotFound as exc:
            self.send_json({"error": str(exc)}, status=404)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=400)
        except RuntimeError as exc:
            self.send_json({"error": str(exc)}, status=503)
        except Exception as exc:
            self.send_json({"error": f"AI analysis failed: {str(exc)}"}, status=500)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        story_id = query.get("story_id", [None])[0]
        headline = query.get("headline", [None])[0]
        if not story_id and not headline:
            self.send_json({"error": "story_id or headline query parameter is required"}, status=400)
            return
        try:
            result = engine.analyze_single_story(story_id=story_id, headline=headline)
            self.send_json(result)
        except engine.BriefingNotFound as exc:
            self.send_json({"error": str(exc)}, status=404)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=400)
        except RuntimeError as exc:
            self.send_json({"error": str(exc)}, status=503)
        except Exception as exc:
            self.send_json({"error": f"AI analysis failed: {str(exc)}"}, status=500)

    def send_json(self, data, status=200, cache_control="no-store"):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
