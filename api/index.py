"""
Unified Vercel Entrypoint (api/index.py)
Serves both the Executive PWA Frontend and the REST API.
"""

from http.server import BaseHTTPRequestHandler
import json
import sys
import urllib.parse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = BASE_DIR / "public"
API_DIR = Path(__file__).resolve().parent

# _engine modülünü içe aktar
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

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. API İstekleri: On-demand AI Story Analysis
        if path in {"/api/analyze-story", "/api/analyze-story/", "/api/analyze_story", "/api/analyze_story/"}:
            story_id = query.get("story_id", [None])[0]
            headline = query.get("headline", [None])[0]
            if not story_id and not headline:
                self.send_json({"error": "story_id or headline query parameter is required"}, status=400)
                return
            try:
                result = engine.analyze_single_story(story_id=story_id, headline=headline)
                self.send_json(result)
            except engine.BriefingNotFound as e:
                self.send_json({"error": str(e)}, status=404)
            except ValueError as e:
                self.send_json({"error": str(e)}, status=400)
            except RuntimeError as e:
                self.send_json({"error": str(e)}, status=503)
            except Exception as e:
                self.send_json({"error": f"AI analysis failed: {str(e)}"}, status=500)
            return

        # 1b. API İstekleri: Briefing
        if path in {"/api", "/api/briefing", "/api/refresh"}:
            mode = query.get("mode", ["daily"])[0]
            if query.get("refresh", ["false"])[0].lower() in ("true", "1") or "refresh" in path:
                self.send_json({"error": "Briefing refreshes run in GitHub Actions."}, status=405)
                return
            try:
                data = engine.get_ready_briefing(mode=mode, date=query.get("date", [None])[0], include_low=engine.wants_low(query))
                self.send_json(data, cache_control="public, s-maxage=60, stale-while-revalidate=300")
            except engine.BriefingNotFound as e:
                self.send_json({"error": str(e)}, status=404)
            except ValueError as e:
                self.send_json({"error": str(e)}, status=400)
            except Exception as e:
                self.send_json({"error": "Briefing generation failed"}, status=500)
            return

        # 2. Statik Dosyalar (Manifest, Icon)
        if path.endswith("/manifest.json") or path == "/manifest.json":
            manifest_file = PUBLIC_DIR / "manifest.json"
            if not manifest_file.exists():
                manifest_file = BASE_DIR / "manifest.json"
            if manifest_file.exists():
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(manifest_file.read_bytes())
                return

        if path.endswith("/icon.svg") or path == "/icon.svg":
            icon_file = PUBLIC_DIR / "icon.svg"
            if not icon_file.exists():
                icon_file = BASE_DIR / "icon.svg"
            if icon_file.exists():
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml")
                self.end_headers()
                self.wfile.write(icon_file.read_bytes())
                return

        # 3. Ana Sayfa (HTML Arayüzü)
        index_file = PUBLIC_DIR / "index.html"
        if not index_file.exists():
            index_file = BASE_DIR / "index.html"

        if index_file.exists():
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(index_file.read_bytes())
            return

        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path in {"/api/analyze-story", "/api/analyze-story/", "/api/analyze_story", "/api/analyze_story/"}:
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
            return

        self.do_GET()

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
