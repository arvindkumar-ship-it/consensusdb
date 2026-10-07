import time, statistics as st
from distributed.raft_node import RaftNode, LogEntry
from distributed.rpc import save

n = RaftNode("prof", [])
n.log += [LogEntry(1, f"INSERT INTO t VALUES ({i}, 'user{i}')") for i in range(400)]
lat = []
for _ in range(50):
    t = time.perf_counter(); save(n); lat.append((time.perf_counter() - t) * 1000)
print("save() 400 entries p50 ms:", round(st.median(lat), 2), "max:", round(max(lat), 2))