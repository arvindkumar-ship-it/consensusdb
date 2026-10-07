"""Load test. Router pe: python -m bench.bench   |   Poora comparison: python -m bench.compare"""
import argparse
import json
import random
import statistics
import string
import threading
import time
import urllib.request

DDL = "CREATE TABLE {t} (id INT PRIMARY KEY, name TEXT)"
INS = "INSERT INTO {t} VALUES ({i}, 'user{i}')"
SEL = "SELECT * FROM {t} WHERE id = {i}"
SEL_SCAN = "SELECT * FROM {t} WHERE name = 'user{i}'"


def router_send(url):
    def send(path, body):
        req = urllib.request.Request(url + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    return send


def pct(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(len(v) * p / 100))] if v else 0.0


def run_phase(name, jobs, threads, send):
    lat, errs, lock = [], [0], threading.Lock()
    it = iter(jobs)

    def worker():
        while True:
            with lock:
                job = next(it, None)
            if job is None:
                return
            t0 = time.perf_counter()
            try:
                out = send(*job)
                bad = "error" in out or out.get("ok") is False
            except Exception:
                bad = True
            ms = (time.perf_counter() - t0) * 1000
            with lock:
                lat.append(ms)
                errs[0] += bad

    t0 = time.perf_counter()
    ts = [threading.Thread(target=worker) for _ in range(threads)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    wall = time.perf_counter() - t0
    res = {"phase": name, "ops": len(lat), "errors": errs[0], "ops_per_sec": round(len(lat) / wall, 1),
           "p50_ms": round(pct(lat, 50), 2), "p95_ms": round(pct(lat, 95), 2), "p99_ms": round(pct(lat, 99), 2),
           "mean_ms": round(statistics.mean(lat), 2) if lat else 0}
    print(json.dumps(res))
    return res


def make_jobs(tables, rows):
    sql = lambda path, t, tpl, i=0: (path, {"table": t, "sql": tpl.format(t=t, i=i)})
    return {"ddl": [sql("/sql", t, DDL) for t in tables],
            "ins": [sql("/sql", t, INS, i) for t in tables for i in range(rows)],
            "sel": [sql("/query", t, SEL, i) for t in tables for i in range(rows)],
            "scan": [sql("/query", t, SEL_SCAN, i) for t in tables for i in range(0, rows, 5)]}


def new_tables(n):
    tag = "".join(random.choices(string.ascii_lowercase, k=5))
    return [f"bench{tag}{chr(97 + k)}" for k in range(n)]


def run_all(send, tables, rows, threads):
    j = make_jobs(tables, rows)
    run_phase("create", j["ddl"], 1, send)
    return [run_phase("insert (write)", j["ins"], threads, send),
            run_phase("select by pk", j["sel"], threads, send),
            run_phase("select by non-key (full scan)", j["scan"], threads, send)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--tables", type=int, default=4)
    ap.add_argument("--rows", type=int, default=500)
    ap.add_argument("--threads", type=int, default=8)
    a = ap.parse_args()
    out = run_all(router_send(a.url), new_tables(a.tables), a.rows, a.threads)
    json.dump(out, open("bench_results.json", "w"), indent=1)


if __name__ == "__main__":
    main()
