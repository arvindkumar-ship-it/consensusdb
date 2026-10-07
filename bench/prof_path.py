import statistics as st, time, uuid
from distributed.config import GROUPS
from distributed.conn import post_json

H = "127.0.0.1"
def p50(f, n=60):
    lat = []
    for i in range(n):
        t = time.perf_counter(); f(i); lat.append((time.perf_counter() - t) * 1000)
    return round(st.median(lat), 2), round(max(lat), 2)

router = lambda path, body: post_json(H, 8000, path, body, 30)
node = lambda port, path, body: post_json(H, port, path, body, 30)
leader = next(p for p in GROUPS["g1"].values() if node(p, "/status", {})["state"] == "LEADER")
other = next(p for p in GROUPS["g1"].values() if p != leader)
# g1 ki table chahiye: naam badalte rahenge jab tak ring g1 na de
while True:
    t = "prof" + uuid.uuid4().hex[:6]
    if router("/sql", {"table": t, "sql": f"CREATE TABLE {t} (id INT PRIMARY KEY, name TEXT)"})["group"] == "g1":
        break
for i in range(20):
    router("/sql", {"table": t, "sql": f"INSERT INTO {t} VALUES ({i}, 'u{i}')"})
n = [1000]
def nid():
    n[0] += 1; return n[0]

print("1 node /status (keep-alive)   :", p50(lambda i: node(leader, "/status", {})))
print("2 leader /query direct        :", p50(lambda i: node(leader, "/query", {"sql": f"SELECT * FROM {t} WHERE id = {i % 20}"})))
print("3 router /query               :", p50(lambda i: router("/query", {"table": t, "sql": f"SELECT * FROM {t} WHERE id = {i % 20}"})))
print("4 leader /client INSERT direct:", p50(lambda i: (lambda k: node(leader, "/client", {"cmd": f"INSERT INTO {t} VALUES ({k}, 'x')"}))(nid())))
print("5 router /sql INSERT          :", p50(lambda i: (lambda k: router("/sql", {"table": t, "sql": f"INSERT INTO {t} VALUES ({k}, 'x')"}))(nid())))
print("6 follower /append (empty hb) :", p50(lambda i: node(other, "/status", {})))