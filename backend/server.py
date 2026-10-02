import json
import mimetypes
import os
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from domain import handle, snapshot

ROOT = Path(__file__).resolve().parents[1]
MAX_BODY = 2_000_000


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def reply(self, code, value):
        data = json.dumps(value, allow_nan=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self.reply(200, {"status": "ok"})
        if path == "/api/state":
            return self.reply(200, snapshot())
        if path.startswith("/api/"):
            return self.reply(404, {"error": "Unknown endpoint"})
        base = (ROOT / "frontend/dist").resolve()
        target = (base / path.lstrip("/")).resolve()
        if not target.is_relative_to(base):
            return self.reply(403, {"error": "Invalid path"})
        if not target.is_file():
            if Path(path).suffix:
                return self.reply(404, {"error": "Asset not found"})
            target = base / "index.html"
        if not target.exists():
            return self.reply(
                503,
                {
                    "error": "Build the frontend first: cd frontend && npm ci && npm run build"
                },
            )
        data = target.read_bytes()
        self.send_response(200)
        self.send_header(
            "Content-Type",
            mimetypes.guess_type(str(target))[0] or "application/octet-stream",
        )
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        start = time.monotonic()
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > MAX_BODY:
                return self.reply(413, {"error": "Request exceeds 2 MB"})
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("Expected a JSON object")
            result = handle(urlparse(self.path).path, body)
            self.reply(200, result)
        except (ValueError, KeyError, TypeError) as error:
            self.reply(400, {"error": str(error)})
        except Exception:
            traceback.print_exc()
            self.reply(500, {"error": "Request failed; inspect server logs"})
        finally:
            print(
                json.dumps(
                    {
                        "method": "POST",
                        "path": self.path,
                        "duration_ms": round((time.monotonic() - start) * 1000, 2),
                    }
                ),
                flush=True,
            )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8314"))
    print(f"Listening on http://localhost:{port}", flush=True)
    ThreadingHTTPServer(
        (os.environ.get("HOST", "127.0.0.1"), port), Handler
    ).serve_forever()
