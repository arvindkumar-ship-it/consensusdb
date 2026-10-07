import json, socket, statistics as st, time, urllib.request
from distributed.config import GROUPS

port = next(iter(next(iter(GROUPS.values())).values()))

def p50(f, n=100):
    lat = []
    for _ in range(n):
        t = time.perf_counter(); f(); lat.append((time.perf_counter() - t) * 1000)
    return round(st.median(lat), 2), round(max(lat), 2)

def status():
    req = urllib.request.Request(f"http://127.0.0.1:{port}/status", b"{}", {"Content-Type": "application/json"})
    json.loads(urllib.request.urlopen(req, timeout=3).read())

def connect():
    socket.create_connection(("127.0.0.1", port), timeout=3).close()

print("tcp connect only  p50/max ms:", p50(connect))
print("full /status call p50/max ms:", p50(status))