"""Teen numbers: (1) akela mkdb vs Raft cluster, (2) index lagne se pehle/baad full scan.
Pehle cluster + router chalu karo (USE_MKDB=1). Chalao: python -m bench.compare --rows 200"""
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


def index_effect(send, tables, rows, threads):
    """Full scan chalao, optimizer ka index lagao, wahi scan dobara."""
    scan = make_jobs(tables, rows)["scan"]
    before = run_phase("scan, index se pehle", scan, threads, send)
    sugg = [s for s in send("/optimize/run", {})["suggestions"] if s["table"] in tables]
    applied = [s["ddl"] for s in sugg if send("/optimize/apply", {"id": s["id"]}).get("applied")]
    after = run_phase("scan, index ke baad", scan, threads, send)
    return {"applied": applied, "before": before, "after": after}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--rows", type=int, default=200)
    ap.add_argument("--threads", type=int, default=8)
    a = ap.parse_args()
    send, close = direct_send()
    try:
        single = run_all(send, new_tables(2), a.rows, 1)      # mkdb ek socket pe serial hai
    finally:
        close()
    tables = new_tables(2)
    cluster = router_send(a.url)
    out = {"single_mkdb": single, "raft_cluster": run_all(cluster, tables, a.rows, a.threads),
           "index_effect": index_effect(cluster, tables, a.rows, a.threads)}
    json.dump(out, open("bench_results.json", "w"), indent=1)
    print("saved bench_results.json")


if __name__ == "__main__":
    main()
