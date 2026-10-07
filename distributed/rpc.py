import json, os, threading, time, urllib.request
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from .conn import post_json
from .raft_node import LogEntry


class RemotePeer:
    def __init__(self, url):
        self.url = url
        u = urlparse(url)
        self.host, self.port = u.hostname, u.port

    def _post(self, path, body):
        return post_json(self.host, self.port, path, body, 0.5)

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


# ---- persistence: data/<id>.log (JSON lines, append-only) + data/<id>.meta.json (term, voted_for) ----
_DIR = "data"
_st = {}    # node_id -> {"n": persisted entries, "last": log[n] object, "meta": (term, voted_for), "f": append handle}


def _paths(node):
    b = f"{_DIR}/{node.node_id}"
    return b + ".log", b + ".meta.json", b + ".json"      # teesra: purana single-file format


def _replace(src, dst):
    for _ in range(50):               # Windows pe file locked ho to retry
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            time.sleep(0.01)
    os.replace(src, dst)


def _write_atomic(path, data):
    with open(path + ".tmp", "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    _replace(path + ".tmp", path)


def _line(e):
    return (json.dumps([e.term, e.command]) + "\n").encode()


def _rewrite(node):
    """Poora log dobara likho (pehli baar, truncate ke baad, ya bad file ke baad)."""
    logp = _paths(node)[0]
    os.makedirs(_DIR, exist_ok=True)
    old = _st.get(node.node_id)
    if old and old["f"]:
        old["f"].close()              # Windows pe open handle ke upar replace nahi hota
    _write_atomic(logp, b"".join(_line(e) for e in node.log[1:]))
    st = _st[node.node_id] = {"n": len(node.log) - 1,
                              "last": node.log[-1] if len(node.log) > 1 else None,
                              "meta": old["meta"] if old else None,
                              "f": open(logp, "ab")}
    return st


def _persist_meta(node, st):
    meta = (node.current_term, node.voted_for)
    if st["meta"] != meta:
        _write_atomic(_paths(node)[1],
                      json.dumps({"term": meta[0], "voted_for": meta[1]}).encode())
        st["meta"] = meta


def persist(node):
    st = _st.get(node.node_id)
    n = len(node.log) - 1
    # last persisted entry abhi bhi wahi object hai => beech mein truncate nahi hua
    intact = st is not None and (st["n"] == 0 or (n >= st["n"] and node.log[st["n"]] is st["last"]))
    if not intact:
        st = _rewrite(node)
    elif n > st["n"]:
        if st["f"] is None:
            st["f"] = open(_paths(node)[0], "ab")
        st["f"].write(b"".join(_line(e) for e in node.log[st["n"] + 1:]))
        st["f"].flush()
        os.fsync(st["f"].fileno())
        st["n"], st["last"] = n, node.log[n]
    _persist_meta(node, st)


def save(node):
    _rewrite(node)
    _persist_meta(node, _st[node.node_id])


def load(node):
    logp, metap, old = _paths(node)
    _st.pop(node.node_id, None)
    if not os.path.exists(logp) and not os.path.exists(metap):
        try:
            with open(old) as f:      # purana format: migrate, naye format mein pehle persist pe likhega
                d = json.load(f)
        except FileNotFoundError:
            return
        node.current_term, node.voted_for = d["term"], d["voted_for"]
        node.log = [LogEntry(**e) for e in d["log"]]
        return
    meta = None
    try:
        with open(metap) as f:
            d = json.load(f)
        node.current_term, node.voted_for = d["term"], d["voted_for"]
        meta = (d["term"], d["voted_for"])
    except (FileNotFoundError, ValueError, KeyError):
        pass
    ents, bad = [], False
    try:
        with open(logp, "rb") as f:
            for raw in f:
                try:
                    if not raw.endswith(b"\n"):
                        raise ValueError("torn line")
                    t, c = json.loads(raw)
                    ents.append(LogEntry(t, c))
                except (ValueError, TypeError):
                    bad = True        # crash mein adhoori likhi last line: chhod do
                    break
    except FileNotFoundError:
        pass
    node.log = [node.log[0]] + ents
    if not bad:
        _st[node.node_id] = {"n": len(ents), "last": ents[-1] if ents else None, "meta": meta, "f": None}
    # bad ho to _st khaali: agla persist file saaf karke dobara likhega


def done(node):
    persist(node)                     # pehle disk, phir state machine
    node.apply_committed()


def serve(node, port):
    load(node)
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"       # keep-alive
        disable_nagle_algorithm = True
        wbufsize = -1                      # header+body ek hi segment me

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
                        idx = len(node.log) - 1
                        done(node)
                        err = node.apply_errors.pop(idx, None) if ok else None
                        if err:
                            out = {"error": err}
                    elif self.path == "/query":
                        try:
                            out = {"result": node.sm.query(body["sql"])}
                        except Exception as e:      # SqlError ya KV mode (query nahi hai)
                            out = {"error": str(e)}
                    elif self.path == "/log":
                        out = {"cmds": [e.command for e in node.log[1:node.commit_index + 1] if e.command != "NOOP"]}
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