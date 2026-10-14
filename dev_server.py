"""
Aviation Briefing Mobile Server
iPhone / PWA için hafif HTTP sunucusu ve REST API.
"""

import os
import sys
import json
import socket
import urllib.parse
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler

# Windows cp1254 encoding fix
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

# Engine'i içe aktar
sys.path.insert(0, str(BASE_DIR))
import engine

def get_local_ip():
    """Yerel ağ IP adresini tespit eder (telefondan bağlanabilmek için)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Harici bir hedefe bağlanarak aktif ağ adaptörünün IP'sini bul
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

class BriefingRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # Kök dizin isteği -> index.html
        if path in ("/", "/index.html"):
            index_path = STATIC_DIR / "index.html"
            if index_path.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(index_path.read_bytes())
                return

        # /static/... dosyaları
        if path.startswith("/static/"):
            file_name = path[len("/static/"):]
            target = STATIC_DIR / file_name
            if target.exists() and target.is_file():
                self.send_response(200)
                if target.suffix == ".html":
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                elif target.suffix == ".svg":
                    self.send_header("Content-Type", "image/svg+xml")
                elif target.suffix == ".json":
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                elif target.suffix == ".css":
                    self.send_header("Content-Type", "text/css")
                elif target.suffix == ".js":
                    self.send_header("Content-Type", "application/javascript")
                self.end_headers()
                self.wfile.write(target.read_bytes())
                return

        # API: Brifing verisini al
        if path == "/api/briefing":
            mode = query.get("mode", ["daily"])[0]
            force = query.get("refresh", ["false"])[0].lower() in ("true", "1")
            try:
                data = engine.get_briefing(mode=mode, force_refresh=force)
                self.send_json(data)
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)
            return

        # API: Sistem durumu
        if path == "/api/status":
            self.send_json({
                "status": "online",
                "local_ip": get_local_ip(),
                "time": engine.datetime.now().isoformat()
            })
            return

        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/api/refresh":
            mode = query.get("mode", ["daily"])[0]
            try:
                data = engine.get_briefing(mode=mode, force_refresh=True)
                self.send_json(data)
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)
            return

        self.send_response(404)
        self.end_headers()

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format, *args):
        # Konsolu temiz tutmak için sadece API isteklerini yaz
        if "api" in args[0]:
            sys.stdout.write(f"[{engine.datetime.now().strftime('%H:%M:%S')}] {args[0]}\n")
            sys.stdout.flush()

def run_server(port=8090):
    local_ip = get_local_ip()
    server_address = ('0.0.0.0', port)
    httpd = HTTPServer(server_address, BriefingRequestHandler)
    
    print("\n" + "="*60)
    print("✈️  AVIATION BRIEFING — iOS & MOBILE EXECUTIVE APP")
    print("="*60)
    print(f"📡 Bilgisayarınızdan erişmek için: http://localhost:{port}")
    print(f"📱 iPhone / Telefonunuzdan erişmek için: http://{local_ip}:{port}")
    print("="*60)
    print("💡 iPhone'da Nasıl Açılır?")
    print(f"   1. iPhone'unuzu bilgisayarla aynı Wi-Fi ağına bağlayın.")
    print(f"   2. Safari'yi açıp şu adrese gidin: http://{local_ip}:{port}")
    print(f"   3. Safari'nin altındaki 'Paylaş' (Kare + Yukarı Ok) butonuna basın.")
    print(f"   4. 'Ana Ekrana Ekle' (Add to Home Screen) seçeneğine dokunun.")
    print("="*60 + "\n")
    sys.stdout.flush()
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nSunucu kapatıldı.")

if __name__ == "__main__":
    port = 8090
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    run_server(port)
