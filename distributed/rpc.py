import json, os, threading, time, urllib.request
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .raft_node import LogEntry


class RemotePeer:
    def __init__(self, url):
        self.url = url

    def _post(self, path, body):
        req = urllib.request.Request(self.url + path, json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=0.5) as r:
            return json.loads(r.read())

    @property
    def alive(self):
        try:
            return self._post("/ping", {})["alive"]
        except OSError:
            return False

    def handle_request_vote(self, *args):
        return tuple(self._post("/vote", {"args": args}))

    def handle_append_entries(self, term, lid, prev_idx, prev_term, entries, commit):
        args = [term, lid, prev_idx, prev_term, [asdict(e) for e in entries], commit]
        return tuple(self._post("/append", {"args": args}))


def save(node):
    path = f"data/{node.node_id}.json"
    os.makedirs("data", exist_ok=True)
    d = {"term": node.current_term, "voted_for": node.voted_for,
         "log": [asdict(e) for e in node.log]}
    with open(path + ".tmp", "w") as f:
        json.dump(d, f)
        f.flush()
        os.fsync(f.fileno())
    for _ in range(50):               # Windows pe file locked ho to retry
        try:
            os.replace(path + ".tmp", path)
            return
        except PermissionError:
            time.sleep(0.01)
    os.replace(path + ".tmp", path)


def load(node):
    try:
        with open(f"data/{node.node_id}.json") as f:
            d = json.load(f)
    except FileNotFoundError:
        return
    node.current_term, node.voted_for = d["term"], d["voted_for"]
    node.log = [LogEntry(**e) for e in d["log"]]


_last = {}                            # node_id -> last saved fingerprint


def done(node):
    # sirf tab fsync jab persistent state (term, voted_for, log) badli ho
    key = (node.current_term, node.voted_for, len(node.log),
           node.log[-1].term, node.log[-1].command)
    if _last.get(node.node_id) != key:
        save(node)
        _last[node.node_id] = key
    node.apply_committed()            # pehle disk, phir state machine


def serve(node, port):
    load(node)
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/ping":
                out = {"alive": node.alive}
            else:
                with lock:
                    if self.path == "/vote":
                        out = node.handle_request_vote(*body["args"])
                        done(node)
                    elif self.path == "/append":
                        a = body["args"]
                        a[4] = [LogEntry(**e) for e in a[4]]
                        out = node.handle_append_entries(*a)
                        done(node)
                    elif self.path == "/client":
                        ok = node.client_request(body["cmd"])
                        out = ok and node.commit_index == len(node.log) - 1  # True = commit bhi hua
                        done(node)
                    elif self.path == "/query":
                        try:
                            out = {"result": node.sm.query(body["sql"])}
                        except Exception as e:      # SqlError ya KV mode (query nahi hai)
                            out = {"error": str(e)}
                    elif self.path == "/get":
                        out = {"value": node.sm.data.get(body["key"])}
                    else:
                        out = {"id": node.node_id, "state": node.state.name,
                               "term": node.current_term, "log": len(node.log) - 1,
                               "commit": node.commit_index, "applied": node.last_applied}
            data = json.dumps(out).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    def ticker():
        while True:
            time.sleep(0.1)
            with lock:
                try:
                    node.tick()
                    done(node)
                except OSError:
                    pass

    threading.Thread(target=ticker, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
