import json
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from distributed.config import GROUPS
from distributed.ring import Ring

ring = Ring(list(GROUPS))


def call(port, path, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", json.dumps(body or {}).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3) as r:
        return json.loads(r.read())


def leader_port(group):
    for port in GROUPS[group].values():
        try:
            if call(port, "/status")["state"] == "LEADER":
                return port
        except OSError:
            pass
    return None


class Router(BaseHTTPRequestHandler):
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        g = ring.get(b["key"])
        port = leader_port(g)
        if port is None:
            out = {"group": g, "error": "no leader"}
        elif self.path == "/set":
            out = {"group": g, "ok": call(port, "/client", {"cmd": f"SET {b['key']} {b['value']}"})}
        elif self.path == "/del":
            out = {"group": g, "ok": call(port, "/client", {"cmd": f"DEL {b['key']}"})}
        elif self.path == "/get":
            out = {"group": g, **call(port, "/get", b)}
        else:
            out = {"error": "use /set /get /del"}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


ThreadingHTTPServer(("127.0.0.1", 8000), Router).serve_forever()