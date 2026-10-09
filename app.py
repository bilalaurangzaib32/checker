import json
import os
import sys
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict

from config import load_config, save_config
from monitor_engine import engine
from ssh_client import SSHMonitorClient
from discord_notifier import DiscordNotifier

HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "index.html")

class SentinelRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Clean logging
        sys.stderr.write(f"[{self.log_date_time_string()}] {format % args}\n")

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_content: str, status: int = 200):
        body = html_content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> Dict[str, Any]:
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                raw_data = self.rfile.read(content_length).decode("utf-8")
                return json.loads(raw_data)
        except Exception as e:
            print(f"Error parsing JSON body: {e}")
        return {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            if os.path.exists(HTML_PATH):
                with open(HTML_PATH, "r", encoding="utf-8") as f:
                    self._send_html(f.read())
            else:
                self._send_html("<h1>VPS Sentinel: index.html missing</h1>", 404)

        elif path == "/api/metrics":
            self._send_json(engine.get_snapshot())

        elif path == "/api/config":
            self._send_json(load_config())

        else:
            self._send_json({"error": "Endpoint not found"}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/refresh":
            engine.run_single_check()
            self._send_json(engine.get_snapshot())

        elif path == "/api/config":
            body = self._read_json_body()
            cfg = load_config()

            new_vps = body.get("vps", {})
            # Preserve existing sensitive fields if blank
            if not new_vps.get("password") and cfg.get("vps", {}).get("password"):
                new_vps["password"] = cfg["vps"]["password"]
            if not new_vps.get("private_key") and cfg.get("vps", {}).get("private_key"):
                new_vps["private_key"] = cfg["vps"]["private_key"]

            cfg["vps"] = new_vps
            cfg["discord"] = body.get("discord", cfg.get("discord", {}))
            cfg["thresholds"] = body.get("thresholds", cfg.get("thresholds", {}))

            save_config(cfg)
            self._send_json({"success": True, "message": "Configuration saved successfully."})

        elif path == "/api/test-ssh":
            body = self._read_json_body()
            client = SSHMonitorClient(
                host=body.get("host", ""),
                port=body.get("port", 22),
                username=body.get("username", "root"),
                password=body.get("password", ""),
                private_key_str=body.get("private_key", ""),
                timeout=8
            )
            res = client.test_connection()
            self._send_json(res)

        elif path == "/api/test-discord":
            body = self._read_json_body()
            notifier = DiscordNotifier(body.get("webhook_url", ""))
            res = notifier.send_test_message()
            self._send_json(res)

        elif path == "/api/send-report-now":
            res = engine.force_send_report()
            self._send_json(res)

        elif path == "/api/websites":
            body = self._read_json_body()
            cfg = load_config()
            sites = cfg.get("websites", [])
            name = body.get("name", "").strip()
            url = body.get("url", "").strip()
            if url:
                sites.append({"name": name or url, "url": url, "expected_status": 200})
                cfg["websites"] = sites
                save_config(cfg)
                self._send_json({"success": True, "message": "Website added successfully."})
            else:
                self._send_json({"success": False, "message": "URL is required."}, 400)

        else:
            self._send_json({"error": "Endpoint not found"}, 404)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/websites/"):
            try:
                idx = int(path.split("/")[-1])
                cfg = load_config()
                sites = cfg.get("websites", [])
                if 0 <= idx < len(sites):
                    sites.pop(idx)
                    cfg["websites"] = sites
                    save_config(cfg)
                    self._send_json({"success": True, "message": "Website removed."})
                    return
                else:
                    self._send_json({"success": False, "message": "Invalid index"}, 404)
                    return
            except Exception:
                pass
        self._send_json({"error": "Endpoint not found"}, 404)

def run_server(host: str = "0.0.0.0", port: int = 8000):
    # Start background monitoring thread
    engine.start()

    server = ThreadingHTTPServer((host, port), SentinelRequestHandler)
    print(f"======================================================")
    print(f"  VPS Sentinel Web Dashboard: http://{host}:{port}")
    print(f"  Background 24/7 Monitor: ACTIVE")
    print(f"======================================================")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping VPS Sentinel...")
    finally:
        engine.stop()
        server.server_close()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    run_server("0.0.0.0", port)
