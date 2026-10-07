import http.client, os, socket, statistics as st, struct, subprocess, sys, time
PORT = 29210
srv = subprocess.Popen([sys.executable, "-m", "bench.prof_srv"], env=dict(os.environ, P=str(PORT)))
for _ in range(50):
    try:
        socket.create_connection(("127.0.0.1", PORT)).close(); break
    except OSError:
        time.sleep(0.1)

def p50(f, n=60):
    lat = []
    for _ in range(n):
        t = time.perf_counter(); f(); lat.append((time.perf_counter() - t) * 1000)
    return round(st.median(lat), 2), round(max(lat), 2)

def http_reused(t):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=t)
    def req():
        c.request("POST", "/", b"{}"); c.getresponse().read()
    req()
    return req

s = socket.create_connection(("127.0.0.1", PORT))            # blocking + OS-level recv timeout
s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVTIMEO, struct.pack("I", 2000))
REQ = b"POST / HTTP/1.1\r\nHost: x\r\nContent-Length: 2\r\n\r\n{}"
def raw():
    s.sendall(REQ); s.recv(4096)

print(sys.version.split()[0])
print("connect, timeout=None   :", p50(lambda: socket.create_connection(("127.0.0.1", PORT)).close()))
print("connect, timeout=2      :", p50(lambda: socket.create_connection(("127.0.0.1", PORT), timeout=2).close()))
print("http reused, None       :", p50(http_reused(None)))
print("http reused, timeout=2  :", p50(http_reused(2)))
print("raw reused, SO_RCVTIMEO :", p50(raw))
srv.terminate()