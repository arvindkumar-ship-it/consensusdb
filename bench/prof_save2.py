import os, statistics as st, time
from types import SimpleNamespace
from distributed.raft_node import LogEntry
from distributed.rpc import save


def mk(n):
    log = [LogEntry(0, "NOOP")] + [
        LogEntry(1, f"INSERT INTO benchabcde VALUES ({i}, 'name{i}', 'xxxxxxxxxxxxxxxxxxxx')")
        for i in range(n)]
    return SimpleNamespace(node_id="prof_tmp", current_term=1, voted_for=None, log=log)


for n in (0, 500, 2000, 10000, 50000):
    node, lat = mk(n), []
    for _ in range(15):
        t = time.perf_counter()
        save(node)
        lat.append((time.perf_counter() - t) * 1000)
    print(n, "entries | save p50 ms:", round(st.median(lat), 2),
          "| file KB:", os.path.getsize("data/prof_tmp.json") // 1024)
os.remove("data/prof_tmp.json")