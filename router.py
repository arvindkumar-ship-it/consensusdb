import json
import os
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from distributed.conn import post_json
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


def call(port, path, body=None):
    return post_json("127.0.0.1", port, path, body or {}, 3)


def leader_port(group):
    for port in GROUPS[group].values():
        try:
            if call(port, "/status")["state"] == "LEADER":
                return port
        except OSError:
            pass
    return None


def add_group(name):
    """Naya group ring me jodo: data copy karo, phir ring badlo. Beech me writes band."""
    global ring, rebalancing
    if name in GROUPS or name not in SPARE:
        return {"error": f"{name} SPARE me nahi hai ya pehle se active hai"}
    rebalancing = True
    time.sleep(0.5)                                   # in-flight writes settle ho jaayein
    GROUPS[name] = SPARE[name]
    try:
        logs = {g: call(leader_port(g), "/log")["cmds"] for g in GROUPS if g != name}
        if leader_port(name) is None:
            raise OSError(f"{name} ke nodes chalu nahi hain")
        new = Ring(list(GROUPS))
        out = rebalance(logs, new, lambda g, c: call(leader_port(g), "/client", {"cmd": c}) is True)
        if "error" in out:
            raise OSError(out["error"])
        ring = new
        return out
    except OSError as e:
        del GROUPS[name]
        return {"error": str(e)}
    finally:
        rebalancing = False


def _lift(g, res):
    """Node ka SQL error top-level 'error' bane, taaki ok/applied sahi nikle."""
    if isinstance(res, dict) and "error" in res:
        return {"group": g, "error": res["error"]}
    return {"group": g, "ok": res}


def sql_write(table, sql):
    g = ring.get(table)
    port = leader_port(g)
    if port is None:
        return {"group": g, "error": "no leader"}
    return _lift(g, call(port, "/client", {"cmd": sql}))


def timed_sql(path, b):
    """/sql ya /query: route karo, time naapo, workload log me daalo, A/B buckets me record karo."""
    g = ring.get(b["table"])
    port = leader_port(g)
    if port is None:
        return {"group": g, "error": "no leader"}
    t0 = time.perf_counter()
    if path == "/sql":
        out = _lift(g, call(port, "/client", {"cmd": b["sql"]}))
    else:
        out = {"group": g, **call(port, "/query", {"sql": b["sql"]})}
    ms = (time.perf_counter() - t0) * 1000
    ok = "error" not in out
    buckets = experiments.assign(b["sql"])
    first = next(iter(buckets.values()), None)
    recorder.record(b["sql"], b["table"], ms, g, ok, "write" if path == "/sql" else "read", first)
    for name, bk in buckets.items():
        experiments.record(name, bk, ms, ok)
    return out


class Router(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    disable_nagle_algorithm = True
    wbufsize = -1

    def _send(self, out):
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        try:
            out = self.route(urlparse(self.path).path, b)
        except OSError as e:
            out = {"error": f"upstream: {e}"}
        self._send(out)

    def do_GET(self):
        try:
            out = self.route(urlparse(self.path).path, {})
        except OSError as e:
            out = {"error": f"upstream: {e}"}
        self._send(out)

    def route(self, path, b):
        if rebalancing and path in ("/sql", "/set", "/del"):
            return {"error": "rebalance chal raha hai, thodi der baad try karo"}
        if path == "/rebalance/add":
            return add_group(b.get("group", ""))
        # ---- workload / optimizer / A-B (naye) ----
        if path == "/stats":
            return {"entries": len(recorder.snapshot()), "tables": recorder.schema.tables and {
                t: {**d, "indexes": sorted(d["indexes"])} for t, d in recorder.schema.tables.items()}}
        if path == "/optimize/run":
            return optimizer.generate()
        if path == "/optimize/apply":
            return optimizer.apply(b.get("id", ""), sql_write)
        if path == "/optimize/impact":
            return optimizer.impact(b.get("id", ""))
        if path == "/ab/start":
            experiments.start(b["name"], int(b.get("treatment_pct", 50)))
            return {"started": b["name"]}
        if path == "/ab/report":
            return experiments.report(b.get("name", ""))
        if path == "/ab/stop":
            experiments.stop(b.get("name", ""))
            return {"stopped": b.get("name")}

        # ---- purane routes (same behaviour) ----
        if path in ("/sql", "/query"):
            if "table" not in b or "sql" not in b:
                return {"error": 'body: {"table": "...", "sql": "..."}'}
            return timed_sql(path, b)
        if "key" not in b:
            return {"error": "use /set /get /del (key) ya /sql /query (table, sql)"}
        g = ring.get(b["key"])
        port = leader_port(g)
        if port is None:
            return {"group": g, "error": "no leader"}
        if path == "/set":
            return {"group": g, "ok": call(port, "/client", {"cmd": f"SET {b['key']} {b['value']}"})}
        if path == "/del":
            return {"group": g, "ok": call(port, "/client", {"cmd": f"DEL {b['key']}"})}
        if path == "/get":
            return {"group": g, **call(port, "/get", b)}
        return {"error": "use /set /get /del /sql /query"}

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("ROUTER_PORT", "8000"))), Router).serve_forever()
