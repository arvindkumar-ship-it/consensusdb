import http.client, socket, statistics as st, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

def p50(f, n=100):
    lat = []
    for i in range(n):
        t = time.perf_counter(); f(i); lat.append((time.perf_counter() - t) * 1000)
    return round(st.median(lat), 3), round(max(lat), 3)

srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(); port = srv.getsockname()[1]
def serve_c(c):
    c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    while True:
        d = c.recv(1024)
        if not d:
            break
        c.sendall(d)
def acceptor():
    while True:
        c, _ = srv.accept()
        threading.Thread(target=serve_c, args=(c,), daemon=True).start()
threading.Thread(target=acceptor, daemon=True).start()

print("A raw connect only     :", p50(lambda i: socket.create_connection(("127.0.0.1", port)).close()))
c = socket.create_connection(("127.0.0.1", port)); c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
print("B raw echo round trip  :", p50(lambda i: (c.sendall(b"x"), c.recv(10))))

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"; disable_nagle_algorithm = True; wbufsize = -1
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"{}")
    def log_message(self, *a): pass
hs = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=hs.serve_forever, daemon=True).start()
hc = http.client.HTTPConnection("127.0.0.1", hs.server_address[1])
def req(i):
    hc.request("POST", "/", b"{}"); hc.getresponse().read()
print("C trivial http.server  :", p50(req))