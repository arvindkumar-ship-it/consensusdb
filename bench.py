"""
ConsensusDB benchmark (router ke through, stdlib only).

Pehle start_all.ps1 chala, router ready hone de, phir:
    python bench.py                     # n=2000, threads=1,4,8
    python bench.py --n 5000 --threads 1 4 16
"""
import argparse
import http.client
import json
import statistics
import threading
import time
import uuid

HOST, PORT = "127.0.0.1", 8000


class Client:
    def __init__(self):
        self.c = http.client.HTTPConnection(HOST, PORT, timeout=10)

    def post(self, path, body):
        data = json.dumps(body).encode()
        for attempt in (0, 1):
            try:
                self.c.request("POST", path, data, {"Content-Type": "application/json"})
                return json.loads(self.c.getresponse().read())
            except (OSError, http.client.HTTPException, ValueError):
                self.c.close()
                self.c = http.client.HTTPConnection(HOST, PORT, timeout=10)
                if attempt == 1:
                    raise


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p / 100))]


def run(workers, jobs):
    """jobs: list of (path, body, check_fn). workers threads me split karke chalao."""
    lat, errs, groups = [], [0], {}
    lock = threading.Lock()
    chunks = [jobs[i::workers] for i in range(workers)]

    def work(chunk):
        cl = Client()
        loc_lat, loc_err, loc_g = [], 0, {}
        for path, body, ok in chunk:
            t = time.perf_counter()
            try:
                r = cl.post(path, body)
                good = "error" not in r and ok(r)
            except Exception:
                r, good = {}, False
            loc_lat.append((time.perf_counter() - t) * 1000)
            if good:
                g = r.get("group")
                loc_g[g] = loc_g.get(g, 0) + 1
            else:
                loc_err += 1
        with lock:
            lat.extend(loc_lat)
            errs[0] += loc_err
            for g, c in loc_g.items():
                groups[g] = groups.get(g, 0) + c

    t0 = time.perf_counter()
    ts = [threading.Thread(target=work, args=(c,)) for c in chunks]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    wall = time.perf_counter() - t0
    return lat, errs[0], groups, wall


def report(name, workers, lat, errs, groups, wall):
    n = len(lat)
    print(f"{name:<6} thr={workers:<3} ops={n:<6} err={errs:<4} "
          f"tput={n / wall:8.1f}/s  p50={pct(lat, 50):7.2f}  p95={pct(lat, 95):7.2f}  "
          f"p99={pct(lat, 99):7.2f}  avg={statistics.mean(lat):7.2f} ms  groups={dict(sorted(groups.items(), key=lambda x: str(x[0])))}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--threads", type=int, nargs="+", default=[1, 4, 8])
    a = ap.parse_args()

    # router zinda + leaders ready?
    cl = Client()
    for _ in range(50):
        try:
            r = cl.post("/set", {"key": "bench:warm", "value": "1"})
            if "error" not in r:
                break
        except Exception:
            pass
        time.sleep(0.2)
    else:
        raise SystemExit("router/leader ready nahi. start_all.ps1 chala ke dekh, GET /health check kar")

    for w in a.threads:
        run_id = uuid.uuid4().hex[:6]
        keys = [f"bench:{run_id}:{i}" for i in range(a.n)]

        sets = [("/set", {"key": k, "value": f"v{i}"}, lambda r: True) for i, k in enumerate(keys)]
        res = run(w, sets)
        report("SET", w, *res)

        gets = [("/get", {"key": k}, (lambda i: lambda r: f'"v{i}"' in json.dumps(r))(i))
                for i, k in enumerate(keys)]
        res = run(w, gets)
        report("GET", w, *res)

        mixed = []
        for i, k in enumerate(keys):
            if i % 5 == 0:
                mixed.append(("/set", {"key": k, "value": f"v{i}"}, lambda r: True))
            else:
                mixed.append(("/get", {"key": k}, lambda r: True))
        res = run(w, mixed)
        report("MIXED", w, *res)
        print()

    print("SET = Raft commit tak ka latency (majority ack), GET = leader read.")
    print("groups={..} se dekh ring load kitna even baant raha hai.")


if __name__ == "__main__":
    main()