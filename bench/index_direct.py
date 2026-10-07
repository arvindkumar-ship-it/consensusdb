import time, statistics as st
from distributed.mkdb_sm import MkdbSM

N, Q = 20000, 200
sm = MkdbSM("idx_direct", 29101)
sm.execute("CREATE TABLE t (id INT PRIMARY KEY, name TEXT)")
t0 = time.time()
for i in range(N):
    sm.execute(f"INSERT INTO t VALUES ({i}, 'user{i}')")
print(f"insert {N} rows: {time.time()-t0:.1f}s")

def scan():
    lat = []
    for i in range(0, N, N // Q):
        t = time.perf_counter()
        sm.execute(f"SELECT * FROM t WHERE name = 'user{i}'")
        lat.append((time.perf_counter() - t) * 1000)
    return round(st.median(lat), 3), round(max(lat), 3)

print("p50/max ms, no index :", scan(), scan())
try:
    sm.execute("CREATE INDEX idx_t_name ON t (name)")
    print("CREATE INDEX: ok")
except Exception as e:
    print("CREATE INDEX FAILED:", e)
print("p50/max ms, index    :", scan(), scan())
sm.close()