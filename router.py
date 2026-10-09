import http.client
import json
import os
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from abtest.experiment import ExperimentManager
from distributed.config import GROUPS, SPARE
from distributed.rebalance import rebalance
from distributed.ring import Ring
from optimizer.service import OptimizerService
from workload.recorder import WorkloadRecorder

ring = Ring(list(GROUPS))
recorder = WorkloadRecorder()
optimizer = OptimizerService(recorder, group_of=lambda t: ring.get(t))
experiments = ExperimentManager()
rebalancing = False
METRICS = deque(maxlen=50000)     # (ts, path, group, ms, ok) -- UI ke /metrics ke liye
HERE = os.path.dirname(os.path.abspath(__file__))

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


def _lift(g, res):
    """Node ka SQL error top-level 'error' bane, taaki ok/applied sahi nikle."""
    if isinstance(res, dict) and "error" in res:
        return {"group": g, "error": res["error"]}
    return {"group": g, "ok": res}


def sql_write(table, sql):
    g = ring.get(table)
    out = to_leader(g, "/client", {"cmd": sql}, wrap=True)
    return out if "error" in out else _lift(g, out["ok"])


def timed_sql(path, b):
    """/sql ya /query: route karo, time naapo, workload log me daalo, A/B buckets me record karo."""
    g = ring.get(b["table"])
    t0 = time.perf_counter()
    out = sql_write(b["table"], b["sql"]) if path == "/sql" else to_leader(g, "/query", {"sql": b["sql"]})
    ms = (time.perf_counter() - t0) * 1000
    ok = "error" not in out
    buckets = experiments.assign(b["sql"])
    first = next(iter(buckets.values()), None)
    recorder.record(b["sql"], b["table"], ms, g, ok, "write" if path == "/sql" else "read", first)
    for name, bk in buckets.items():
        experiments.record(name, bk, ms, ok)
    return out


def add_group(name):
    """Naya group ring me jodo: data copy karo, phir ring badlo. Beech me writes band."""
    global ring, rebalancing
    if name in GROUPS or name not in SPARE:
        return {"error": f"{name} SPARE me nahi hai ya pehle se active hai"}
    rebalancing = True
    time.sleep(0.5)                                   # in-flight writes settle ho jaayein
    GROUPS[name] = SPARE[name]
    try:
        logs = {}
        for g in GROUPS:
            if g == name:
                continue
            p = leader_port(g)
            if p is None:
                raise OSError(f"{g} ka leader nahi mila")
            logs[g] = call(p, "/log")["cmds"]
        if leader_port(name) is None:
            raise OSError(f"{name} ke nodes chalu nahi hain")
        new = Ring(list(GROUPS))
        out = rebalance(logs, new, lambda g, c: call(leader_port(g), "/client", {"cmd": c}) is True)
        if "error" in out:
            raise OSError(out["error"])
        ring = new
        return out
    except (OSError, *NET_ERRS) as e:
        GROUPS.pop(name, None)
        with LEADER_LOCK:
            LEADER.pop(name, None)
        return {"error": str(e)}
    finally:
        rebalancing = False


def cluster():
    """Har node ka poora /status (state, term, log, commit, applied). Parallel, taaki dead nodes se slow na ho."""
    nodes = {}
    for grp, active in ((GROUPS, True), (SPARE, False)):
        for g, members in grp.items():
            if not active and g in GROUPS:
                continue
            for n, port in members.items():
                nodes[n] = (g, port, active)
    out = {}

    def probe(n, g, port, active):
        try:
            s = call(port, "/status", timeout=PROBE_TIMEOUT)
            out[n] = {"group": g, "port": port, "active": active, **s}
        except NET_ERRS:
            out[n] = {"group": g, "port": port, "active": active, "state": "DOWN"}

    ts = [threading.Thread(target=probe, args=(n, *v)) for n, v in nodes.items()]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    groups = {}
    for n in nodes:
        info = out[n]
        groups.setdefault(info["group"], {"active": info["active"], "nodes": {}})["nodes"][n] = \
            {k: v for k, v in info.items() if k not in ("group", "active")}
    return {"groups": groups, "leaders": dict(LEADER), "rebalancing": rebalancing, "ts": time.time()}


def metrics(window=60):
    now = time.time()
    rows = [m for m in list(METRICS) if m[0] >= now - window]
    lat = sorted(m[3] for m in rows)

    def pct(p):
        return round(lat[min(len(lat) - 1, int(round((len(lat) - 1) * p / 100)))], 2) if lat else None

    per_group, series = {}, [0] * window
    for ts, _p, g, _ms, ok in rows:
        if g:
            per_group[g] = per_group.get(g, 0) + 1
        series[min(window - 1, int(ts - (now - window)))] += 1
    return {"window_s": window, "ops": len(rows), "ops_per_sec": round(len(rows) / window, 1),
            "errors": sum(1 for m in rows if not m[4]), "p50_ms": pct(50), "p95_ms": pct(95),
            "per_group": per_group, "series": series}


def bench():
    p = os.path.join(HERE, "bench_results.json")
    if not os.path.exists(p):
        return {"error": "bench_results.json nahi mila"}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


DATA_PATHS = ("/set", "/get", "/del", "/mget", "/sql", "/query")


class Router(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"    # client (benchmark) ke liye keep-alive
    disable_nagle_algorithm = True   # Linux/Docker pe 40ms delayed-ACK stall se bachne ke liye
    wbufsize = -1                    # header+body ek hi segment me

    def _send(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/health":
            return self._send({"leaders": dict(LEADER), "groups": health()})
        if p == "/cluster":
            return self._send(cluster())
        if p == "/metrics":
            return self._send(metrics())
        if p == "/bench":
            return self._send(bench())
        if p == "/stats":
            return self._send(self.stats())
        self._send({"error": "GET /health /cluster /metrics /bench /stats ya POST /set /get /del /mget /sql /query"}, 404)

    @staticmethod
    def stats():
        tables = {t: {**d, "indexes": sorted(d["indexes"])} for t, d in recorder.schema.tables.items()}
        return {"entries": len(recorder.snapshot()), "tables": tables, "rebalancing": rebalancing,
                "ab_active": list(experiments.active)}

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            b = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._send({"error": "bad json"}, 400)
        t0 = time.perf_counter()
        try:
            out = self.route(b)
        except Exception as e:
            out = {"error": f"router: {e!r}"}
        p = urlparse(self.path).path
        if p in DATA_PATHS:
            ms = (time.perf_counter() - t0) * 1000
            METRICS.append((time.time(), p, out.get("group") if isinstance(out, dict) else None, ms,
                            not (isinstance(out, dict) and "error" in out)))
        self._send(out)

    def route(self, b):
        p = urlparse(self.path).path

        if rebalancing and p in ("/sql", "/set", "/del"):
            return {"error": "rebalance chal raha hai, thodi der baad try karo"}
        if p == "/rebalance/add":
            return add_group(b.get("group", ""))
        if p == "/optimize/run":
            return optimizer.generate()
        if p == "/optimize/apply":
            return optimizer.apply(b.get("id", ""), sql_write)
        if p == "/optimize/impact":
            return optimizer.impact(b.get("id", ""))
        if p == "/ab/start":
            if "name" not in b:
                return {"error": 'body: {"name", "treatment_pct"}'}
            experiments.start(b["name"], int(b.get("treatment_pct", 50)))
            return {"started": b["name"]}
        if p == "/ab/report":
            return experiments.report(b.get("name", ""))
        if p == "/ab/stop":
            experiments.stop(b.get("name", ""))
            return {"stopped": b.get("name")}

        if p in ("/sql", "/query"):
            if "table" not in b or "sql" not in b:
                return {"error": 'body: {"table": "...", "sql": "..."}'}
            return timed_sql(p, b)

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
    port = int(os.environ.get("ROUTER_PORT", "8000"))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Router)
    srv.daemon_threads = True
    print(f"router on http://127.0.0.1:{port}  (GET /health /cluster /metrics)")
    srv.serve_forever()