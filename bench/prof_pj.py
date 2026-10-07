import http.client, statistics as st, time
from distributed.config import GROUPS
from distributed import conn

H = "127.0.0.1"
port = next(iter(GROUPS["g1"].values()))
key = (H, port)

lat, ids = [], []
for i in range(20):
    t = time.perf_counter()
    conn.post_json(H, port, "/status", {}, 30)
    lat.append((time.perf_counter() - t) * 1000)
    c = conn._tls.conns.get(key)
    ids.append(id(c.sock) if c is not None and c.sock else None)

print("port", port)
print("per-call ms :", [round(x, 2) for x in lat])
print("p50 ms      :", round(st.median(lat), 2))
print("distinct sockets:", len(set(ids)), "of", len(ids))

c = http.client.HTTPConnection(H, port, timeout=30)
c.request("POST", "/status", b"{}", {"Content-Type": "application/json"})
r = c.getresponse()
print("http version:", r.version, "| Connection hdr:", r.getheader("Connection"),
      "| Content-Length:", r.getheader("Content-Length"), "| will_close:", r.will_close)
r.read()
c.close()

cl = []
for i in range(10):
    c = http.client.HTTPConnection(H, port, timeout=30)
    t = time.perf_counter()
    c.connect()
    cl.append((time.perf_counter() - t) * 1000)
    c.close()
print("fresh HTTPConnection.connect p50 ms:", round(st.median(cl), 2))