"""Router (port 8000) pe load daal ke latency/throughput naapna.

Chalao:   python -m bench.bench --tables 4 --rows 500 --threads 8
Agar mkdb ka SQL syntax alag hai to neeche DDL/INS/SEL templates badal do.
"""
import argparse
import json
import statistics
import threading
import time
import urllib.request

DDL = "CREATE TABLE {t} (id INT PRIMARY KEY, name TEXT)"
INS = "INSERT INTO {t} VALUES ({i}, 'user{i}')"
SEL = "SELECT * FROM {t} WHERE id = {i}"
SEL_SCAN = "SELECT * FROM {t} WHERE name = 'user{i}'"


def post(url, path, body):
    req = urllib.request.Request(url + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def pct(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(len(v) * p / 100))] if v else 0.0


def run_phase(name, jobs, threads, url):
    lat, errs, lock = [], [0], threading.Lock()
    it = iter(jobs)

    def worker():
        while True:
            with lock:
                job = next(it, None)
            if job is None:
                return
            path, body = job
            t0 = time.perf_counter()
            try:
                out = post(url, path, body)
                bad = "error" in out
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--tables", type=int, default=4)
    ap.add_argument("--rows", type=int, default=500)
    ap.add_argument("--threads", type=int, default=8)
    a = ap.parse_args()
    import random, string
    tag = "".join(random.choices(string.ascii_lowercase, k=5))
    tables = [f"bench{tag}{chr(97 + k)}" for k in range(a.tables)]
    for t in tables:
        post(a.url, "/sql", {"table": t, "sql": DDL.format(t=t)})
    ins = [("/sql", {"table": t, "sql": INS.format(t=t, i=i)}) for t in tables for i in range(a.rows)]
    sel = [("/query", {"table": t, "sql": SEL.format(t=t, i=i)}) for t in tables for i in range(a.rows)]
    scan = [("/query", {"table": t, "sql": SEL_SCAN.format(t=t, i=i)}) for t in tables for i in range(0, a.rows, 5)]
    out = [run_phase("insert (raft write)", ins, a.threads, a.url),
           run_phase("select by pk (point lookup)", sel, a.threads, a.url),
           run_phase("select by non-key (full scan)", scan, a.threads, a.url)]
    with open("bench_results.json", "w") as f:
        json.dump(out, f, indent=1)
    print("saved bench_results.json")


if __name__ == "__main__":
    main()

