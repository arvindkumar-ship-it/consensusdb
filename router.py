import http.client
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from distributed.config import GROUPS
from distributed.ring import Ring

ring = Ring(list(GROUPS))

LEADER = {}                      # group -> port (cache)
LEADER_LOCK = threading.Lock()
TLS = threading.local()          # per-thread pooled connections: port -> HTTPConnection
PROBE_TIMEOUT = 0.5              # /status probe
CALL_TIMEOUT = 3.0               # real request
CONNECT_TIMEOUT = 0.3            # Windows pe closed port connect ~2s leta hai, isliye cap
LEADER_WAIT = 3.0                # election chal rahi ho to itna wait

NET_ERRS = (OSError, http.client.HTTPException, ValueError)


def _conn(port, timeout):
    pool = getattr(TLS, "pool", None)
    if pool is None:
        pool = TLS.pool = {}
    c = pool.get(port)
    if c is None:
        c = pool[port] = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    c.timeout = timeout
    return c


def _drop(port):
    pool = getattr(TLS, "pool", {})
    c = pool.pop(port, None)
    if c:
        try:
            c.close()
        except Exception:
            pass


def call(port, path, body=None, timeout=CALL_TIMEOUT):
    """Node ko POST. Response kuch bhi ho sakta hai (dict, bool, ...), as-is return."""
    data = json.dumps(body or {}).encode()
    hdr = {"Content-Type": "application/json", "Content-Length": str(len(data))}
    for attempt in (0, 1):
        c = _conn(port, timeout)
        try:
            if c.sock is None:
                # naya connection: chhota connect timeout (dead node jaldi pakda jaye)
                c.timeout = min(timeout, CONNECT_TIMEOUT)
                c.connect()
                c.sock.settimeout(timeout)
            else:
                # reused connection: is call ka timeout lagao (probe 0.5 / call 3.0)
                c.sock.settimeout(timeout)
            c.request("POST", path, data, hdr)
            r = c.getresponse()
            raw = r.read()
            if r.status >= 400:
                raise OSError(f"{port}{path} -> HTTP {r.status}")
            return json.loads(raw)
        except NET_ERRS as e:
            _drop(port)
            # fresh retry sirf stale keep-alive pe; refused/timeout pe turant fail (dead node)
            stale = isinstance(e, (ConnectionResetError, BrokenPipeError,
                                   http.client.RemoteDisconnected))
            if attempt == 1 or not stale:
                raise


def _find_leader(group):
    for port in GROUPS[group].values():
        try:
            s = call(port, "/status", timeout=PROBE_TIMEOUT)
            if isinstance(s, dict) and s.get("state") == "LEADER":
                return port
        except NET_ERRS:
            pass
    return None


def leader_port(group, refresh=False):
    if not refresh:
        with LEADER_LOCK:
            p = LEADER.get(group)
        if p is not None:
            return p
    deadline = time.time() + LEADER_WAIT
    while True:
        p = _find_leader(group)
        if p is not None:
            with LEADER_LOCK:
                LEADER[group] = p
            return p
        if time.time() >= deadline:
            with LEADER_LOCK:
                LEADER.pop(group, None)
            return None
        time.sleep(0.1)


def _pack(group, res, wrap):
    """wrap=True ya res dict nahi -> {"group", "ok": res}; warna dict spread."""
    if wrap or not isinstance(res, dict):
        return {"group": group, "ok": res}
    return {"group": group, **res}


def to_leader(group, path, body, wrap=False):
    """Cached leader pe try; fail ho to leader dobara dhoond ke ek baar retry."""
    port = leader_port(group)
    if port is None:
        return {"group": group, "error": "no leader"}
    try:
        return _pack(group, call(port, path, body), wrap)
    except NET_ERRS:
        port = leader_port(group, refresh=True)
        if port is None:
            return {"group": group, "error": "no leader"}
        try:
            return _pack(group, call(port, path, body), wrap)
        except NET_ERRS as e:
            with LEADER_LOCK:
                LEADER.pop(group, None)
            return {"group": group, "error": f"upstream: {e}"}


def health():
    out = {}
    for g, nodes in GROUPS.items():
        info = {}
        for name, port in nodes.items():
            try:
                s = call(port, "/status", timeout=PROBE_TIMEOUT)
                info[name] = {"state": s.get("state"), "term": s.get("term")}
            except NET_ERRS:
                info[name] = {"state": "DOWN"}
        out[g] = info
    return out


class Router(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"    # client (benchmark) ke liye keep-alive
    disable_nagle_algorithm = True   # Linux/Docker pe 40ms delayed-ACK stall se bachne ke liye
    wbufsize = -1                    # header+body ek hi segment me

    def _send(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            return self._send({"leaders": dict(LEADER), "groups": health()})
        self._send({"error": "GET /health ya POST /set /get /del /mget /sql /query"}, 404)

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            b = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._send({"error": "bad json"}, 400)
        try:
            out = self.route(b)
        except Exception as e:
            out = {"error": f"router: {e!r}"}
        self._send(out)

    def route(self, b):
        p = self.path

        if p in ("/sql", "/query"):
            if "table" not in b or "sql" not in b:
                return {"error": 'body: {"table": "...", "sql": "..."}'}
            g = ring.get(b["table"])
            if p == "/sql":
                return to_leader(g, "/client", {"cmd": b["sql"]}, wrap=True)
            return to_leader(g, "/query", {"sql": b["sql"]})

        if p == "/mget":
            keys = b.get("keys")
            if not isinstance(keys, list):
                return {"error": 'body: {"keys": [...]}'}
            by_group = {}
            for k in keys:
                by_group.setdefault(ring.get(k), []).append(k)
            res = {}
            lock = threading.Lock()

            def fetch(g, ks):
                for k in ks:
                    r = to_leader(g, "/get", {"key": k})
                    with lock:
                        res[k] = r

            ts = [threading.Thread(target=fetch, args=(g, ks)) for g, ks in by_group.items()]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
            return {"results": {k: res[k] for k in keys}}

        if p in ("/set", "/get", "/del"):
            if "key" not in b:
                return {"error": 'body me "key" chahiye'}
            g = ring.get(b["key"])
            if p == "/set":
                if "value" not in b:
                    return {"error": 'body me "value" chahiye'}
                return to_leader(g, "/client", {"cmd": f"SET {b['key']} {b['value']}"}, wrap=True)
            if p == "/del":
                return to_leader(g, "/client", {"cmd": f"DEL {b['key']}"}, wrap=True)
            return to_leader(g, "/get", b)

        return {"error": "use /set /get /del /mget (key/keys) ya /sql /query (table, sql)"}

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer.request_queue_size = 128   # default 5: 16+ clients ek saath connect hon to RST
    srv = ThreadingHTTPServer(("127.0.0.1", 8000), Router)
    srv.daemon_threads = True
    print("router on http://127.0.0.1:8000  (GET /health)")
    srv.serve_forever()