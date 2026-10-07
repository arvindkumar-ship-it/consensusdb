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
        try:
            out = self.route(b)
        except OSError as e:
            out = {"error": f"upstream: {e}"}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def route(self, b):
        if self.path in ("/sql", "/query"):
            if "table" not in b or "sql" not in b:
                return {"error": 'body: {"table": "...", "sql": "..."}'}
            g = ring.get(b["table"])
            port = leader_port(g)
            if port is None:
                return {"group": g, "error": "no leader"}
            if self.path == "/sql":
                return {"group": g, "ok": call(port, "/client", {"cmd": b["sql"]})}
            return {"group": g, **call(port, "/query", {"sql": b["sql"]})}

        if "key" not in b:
            return {"error": "use /set /get /del (key) ya /sql /query (table, sql)"}
        g = ring.get(b["key"])
        port = leader_port(g)
        if port is None:
            return {"group": g, "error": "no leader"}
        if self.path == "/set":
            return {"group": g, "ok": call(port, "/client", {"cmd": f"SET {b['key']} {b['value']}"})}
        if self.path == "/del":
            return {"group": g, "ok": call(port, "/client", {"cmd": f"DEL {b['key']}"})}
        if self.path == "/get":
            return {"group": g, **call(port, "/get", b)}
        return {"error": "use /set /get /del /sql /query"}

    def log_message(self, *a):
        pass


ThreadingHTTPServer(("127.0.0.1", 8000), Router).serve_forever()
