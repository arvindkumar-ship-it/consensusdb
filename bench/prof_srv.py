import http.client, socket, statistics as st, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(__import__("os").environ.get("P","29200"))

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"; disable_nagle_algorithm = True; wbufsize = -1
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"{}")
    def log_message(self, *a): pass

def p50(f, n=100):
    lat = []
    for _ in range(n):
        t = time.perf_counter(); f(); lat.append((time.perf_counter() - t) * 1000)
    return round(st.median(lat), 2), round(max(lat), 2)

if len(sys.argv) > 1 and sys.argv[1] == "client":
    c = http.client.HTTPConnection("127.0.0.1", PORT)
    def req():
        c.request("POST", "/", b"{}"); c.getresponse().read()
    print("connect only :", p50(lambda: socket.create_connection(("127.0.0.1", PORT)).close()))
    print("http reused  :", p50(req))
else:
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
