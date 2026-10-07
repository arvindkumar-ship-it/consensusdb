import threading, time
from distributed.config import GROUPS
from distributed.conn import post_json
from bench.bench import make_jobs, new_tables, router_send, run_all

H = "127.0.0.1"
port = next(iter(GROUPS["g1"].values()))


def status_tput(th, n=400):
    def w():
        for _ in range(n // th):
            post_json(H, port, "/status", {}, 30)
    ts = [threading.Thread(target=w) for _ in range(th)]
    t0 = time.perf_counter()
    [t.start() for t in ts]
    [t.join() for t in ts]
    return round(n / (time.perf_counter() - t0), 1)


send = router_send("http://127.0.0.1:8000")
print("threads | node /status ops/s | router insert ops/s (p50) | router select-pk ops/s (p50)")
for th in (1, 2, 4, 8):
    r = run_all(send, new_tables(2), 200, th)
    print(th, "|", status_tput(th), "|", r[0]["ops_per_sec"], f"({r[0]['p50_ms']})", "|",
          r[1]["ops_per_sec"], f"({r[1]['p50_ms']})")