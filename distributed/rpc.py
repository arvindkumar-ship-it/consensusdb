import json, threading, time, urllib.request
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .raft_node import LogEntry


class RemotePeer:
    """Dusre process ke node ka proxy; methods RaftNode wale hi hain."""
    def __init__(self, url):
        self.url = url

    def _post(self, path, body):
        req = urllib.request.Request(self.url + path, json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=0.3) as r:
            return json.loads(r.read())

    @property
    def alive(self):
        try:
            return self._post("/ping", {})["alive"]
        except OSError:               # connection refused / timeout = node down
            return False

    def handle_request_vote(self, *args):
        return tuple(self._post("/vote", {"args": args}))

    def handle_append_entries(self, term, lid, prev_idx, prev_term, entries, commit):
        args = [term, lid, prev_idx, prev_term, [asdict(e) for e in entries], commit]
        return tuple(self._post("/append", {"args": args}))


def serve(node, port):
    lock = threading.Lock()           # tick thread aur HTTP threads ek saath node na chhedein

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/ping":      # lock-free, warna busy node dead dikhega
                out = {"alive": node.alive}
            else:
                with lock:
                    if self.path == "/vote":
                        out = node.handle_request_vote(*body["args"])
                    elif self.path == "/append":
                        a = body["args"]
                        a[4] = [LogEntry(**e) for e in a[4]]
                        out = node.handle_append_entries(*a)
                    elif self.path == "/client":
                        out = node.client_request(body["cmd"])
                    else:
                        out = {"id": node.node_id, "state": node.state.name,
                               "term": node.current_term, "log": len(node.log) - 1,
                               "commit": node.commit_index}
            data = json.dumps(out).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):    # console spam band
            pass

    def ticker():
        while True:
            time.sleep(0.1)           # 1 tick = 100ms, timeout = 0.5-1s
            with lock:
                try:
                    node.tick()
                except OSError:       # RPC beech mein fail hua, agla tick retry karega
                    pass

    threading.Thread(target=ticker, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()