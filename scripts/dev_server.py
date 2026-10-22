"""
Aviation Briefing Mobile Server
iPhone / PWA için hafif HTTP sunucusu ve REST API.
"""

import os
import sys
import json
import socket
import ipaddress
import mimetypes
import urllib.parse
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

# Windows cp1254 encoding fix
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = BASE_DIR / "public"

# Engine'i içe aktar
API_DIR = BASE_DIR / "api"
sys.path.insert(0, str(API_DIR))
import _engine as engine
import briefing_store
briefing_store.read_json = briefing_store.read_for_update


def resolve_public_file(file_name):
    """Resolve a URL path only when it remains inside the public directory."""
    decoded_name = urllib.parse.unquote(file_name)
    requested_path = Path(decoded_name)
    if requested_path.is_absolute():
        return None

    public_root = PUBLIC_DIR.resolve()
    candidate = (public_root / requested_path).resolve()
    try:
        candidate.relative_to(public_root)
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate


def is_refresh_authorized(client_ip, authorization_header):
    """Allow local maintenance or callers holding the refresh secret."""
    try:
        ip = ipaddress.ip_address(client_ip)
        if ip.is_loopback or (isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped and ip.ipv4_mapped.is_loopback):
            return True
    except ValueError:
        return False

    refresh_secret = os.environ.get("REFRESH_SECRET") or engine.ENV.get("REFRESH_SECRET")
    if not refresh_secret:
        return False
    return authorization_header == f"Bearer {refresh_secret}"

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
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

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

        # Kök dizin isteği -> index.html
        if path in ("/", "/index.html"):
            index_path = PUBLIC_DIR / "index.html"
            if index_path.exists():
                content = index_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0")
                self.end_headers()
                self.wfile.write(content)
                return

        # /static/... veya genel statik dosyalar (manifest, favicon, ikonlar)
        clean_path = path.lstrip("/")
        if clean_path and not clean_path.startswith("api/"):
            sub_path = clean_path[len("static/"):] if clean_path.startswith("static/") else clean_path
            target = resolve_public_file(sub_path)
            if target and target.is_file():
                content = target.read_bytes()
                self.send_response(200)
                content_type, _ = mimetypes.guess_type(target.name)
                self.send_header("Content-Type", content_type or "application/octet-stream")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(content)
                return

        # API: Brifing verisini al
        if path == "/api/briefing":
            mode = query.get("mode", ["daily"])[0]
            try:
                try:
                    data = engine.get_ready_briefing(mode=mode, date=query.get("date", [None])[0], include_low=engine.wants_low(query))
                except engine.BriefingNotFound:
                    data = engine.get_briefing(mode=mode, force_refresh=False, date=query.get("date", [None])[0], include_low=engine.wants_low(query))
                self.send_json(data)
            except engine.BriefingNotFound as e:
                self.send_json({"error": str(e)}, status=404)
            except ValueError as e:
                self.send_json({"error": str(e)}, status=400)
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

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/api/refresh":
            mode = query.get("mode", ["daily"])[0]
            authorization = self.headers.get("Authorization", "")
            if not is_refresh_authorized(self.client_address[0], authorization):
                self.send_json({"error": "Refresh is not authorized"}, status=401)
                return
            try:
                data = engine.get_briefing(mode=mode, force_refresh=True)
                self.send_json(data)
            except ValueError as e:
                self.send_json({"error": str(e)}, status=400)
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)
            return

        self.send_response(404)
        self.end_headers()

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(body)
            self.wfile.flush()
        except (ConnectionResetError, BrokenPipeError):
            pass
        self.close_connection = True

    def log_message(self, format, *args):
        # Konsolu temiz tutmak için sadece API isteklerini yaz
        # args[0] is the request line for access logs but an int status code for log_error, hence the str().
        message = str(args[0]) if args else ""
        if "api" in message:
            sys.stdout.write(f"[{engine.datetime.now().strftime('%H:%M:%S')}] {message}\n")
            sys.stdout.flush()

def run_server(port=8090):
    local_ip = get_local_ip()
    server_address = ('0.0.0.0', port)
    httpd = ThreadingHTTPServer(server_address, BriefingRequestHandler)
    
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
