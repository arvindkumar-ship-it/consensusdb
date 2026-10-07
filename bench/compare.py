"""Teen numbers: (1) akela mkdb vs Raft cluster, (2) index lagne se pehle/baad full scan.
Pehle cluster + router chalu karo (USE_MKDB=1). Chalao: python -m bench.compare --rows 1000

Index-effect ka tareeka: warmup (cold connections + optimizer threshold) -> before (median of rounds)
-> index apply -> after (median of rounds). Router ke raaste network hop (~4-5 ms) latency pe haavi
rehta hai; hop-free asar dekhne ke liye: python -m bench.index_direct"""
import argparse
import json
import threading

from bench.bench import make_jobs, new_tables, router_send, run_all, run_phase


def direct_send(port=29100):
    from distributed.mkdb_sm import MkdbSM
    sm, lock = MkdbSM("bench_direct", port), threading.Lock()

    def send(path, body):
        with lock:                                  # ek hi socket hai
            try:
                sm.execute(body["sql"])
                return {}
            except Exception as e:
                return {"error": str(e)}
    return send, sm.close


def median_run(runs):
    """ops_per_sec ke hisaab se beech wala run (outlier/cold run se bachne ke liye)."""
    by_speed = sorted(runs, key=lambda r: r["ops_per_sec"])
    mid = dict(by_speed[len(by_speed) // 2])
    mid["rounds"] = [r["ops_per_sec"] for r in runs]
    return mid


def measure(name, jobs, threads, send, rounds):
    return median_run([run_phase(f"{name} [{i + 1}/{rounds}]", jobs, threads, send) for i in range(rounds)])


def index_effect(send, tables, rows, threads, rounds=3):
    """Full scan chalao, optimizer ka index lagao, wahi scan dobara."""
    scan = make_jobs(tables, rows)["scan"] * 3      # chhote sample ka noise kam karne ke liye
    run_phase("scan warmup", scan, threads, send)   # cold connections + workload 30% threshold paar
    before = measure("scan, index se pehle", scan, threads, send, rounds)
    sugg = [s for s in send("/optimize/run", {})["suggestions"] if s["table"] in tables]
    done = [s for s in sugg if send("/optimize/apply", {"id": s["id"]}).get("applied")]
    applied = [s["ddl"] for s in done]
    assert applied, f"koi index apply nahi hua: {[s['table'] for s in sugg]}"
    run_phase("scan warmup (index ke baad)", scan, threads, send)
    after = measure("scan, index ke baad", scan, threads, send, rounds)
    impact = [send("/optimize/impact", {"id": s["id"]}) for s in done]
    return {"applied": applied, "before": before, "after": after, "impact": impact,
            "speedup_ops_per_sec": round(after["ops_per_sec"] / before["ops_per_sec"], 2) if before["ops_per_sec"] else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--rows", type=int, default=1000)
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--rounds", type=int, default=3)
    a = ap.parse_args()
    send, close = direct_send()
    try:
        single = run_all(send, new_tables(2), a.rows, 1)      # mkdb ek socket pe serial hai
    finally:
        close()
    tables = new_tables(2)
    cluster = router_send(a.url)
    out = {"single_mkdb": single, "raft_cluster": run_all(cluster, tables, a.rows, a.threads),
           "index_effect": index_effect(cluster, tables, a.rows, a.threads, a.rounds)}
    json.dump(out, open("bench_results.json", "w"), indent=1)
    print("saved bench_results.json")


if __name__ == "__main__":
    main()