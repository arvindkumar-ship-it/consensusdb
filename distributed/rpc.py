import http.client, json, os, threading, time, urllib.request
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from .conn import post_json
from .raft_node import LogEntry


class RemotePeer:
    """
    alive = cached flag, request path me network call nahi.
    Background thread har 0.2s peer ko ping karta hai; kisi call me OSError aaye to
    turant down mark. Pehle har replicate/tick pe dead peer ko ping hota tha
    (timeout ~0.5s x retry) aur wo node ka global lock pakde rehta tha.
    """
    PING_EVERY = 0.2
    PING_TIMEOUT = 0.3     # Windows pe closed port ~2s leta hai; timeout isse cap karta hai

    def __init__(self, url):
        self.url = url
        u = urlparse(url)
        self.host, self.port = u.hostname, u.port
        self._alive = True            # optimistic; watcher jaldi sahi kar deta hai
        threading.Thread(target=self._watch, daemon=True).start()

    def _ping(self):
        # apna alag connection: post_json ke shared state se koi takrav nahi
        c = http.client.HTTPConnection(self.host, self.port, timeout=self.PING_TIMEOUT)
        try:
            c.request("POST", "/ping", b"{}",
                      {"Content-Type": "application/json", "Content-Length": "2"})
            return bool(json.loads(c.getresponse().read())["alive"])
        finally:
            c.close()

    def _watch(self):
        while True:
            try:
                self._alive = self._ping()
            except Exception:
                self._alive = False
            time.sleep(self.PING_EVERY)

    def _post(self, path, body):
        try:
            out = post_json(self.host, self.port, path, body, 0.5)
        except OSError:
            self._alive = False       # isi call me fail hua to agle calls skip honge
            raise
        self._alive = True
        return out

    @property
    def alive(self):
        return self._alive

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
    pending, plock = [], threading.Lock()

    def flush(batch):
        """Lock pakde hue: batch ki saari entries append -> ek replicate -> ek fsync (done)."""
        try:
            for s in batch:
                s["idx"] = node.client_append(s["cmd"])
            if any(s["idx"] is not None for s in batch):
                node.replicate()
                done(node)
            for s in batch:
                if s["idx"] is None:
                    s["out"] = False                      # leader nahi
                else:
                    err = node.apply_errors.pop(s["idx"], None)
                    s["out"] = {"error": err} if err else node.commit_index >= s["idx"]  # True = commit hua
        except Exception as e:
            for s in batch:
                if s["out"] is None:
                    s["out"] = {"error": f"flush: {e!r}"}
        finally:
            for s in batch:
                s["done"] = True

    def submit(cmd):
        """Group commit: jo thread lock pehle le, wo pending sabki entries ek saath chalata hai."""
        slot = {"cmd": cmd, "idx": None, "out": None, "done": False}
        with plock:
            pending.append(slot)
        with lock:
            if not slot["done"]:
                with plock:
                    batch = pending[:]
                    del pending[:]
                flush(batch)
        return slot["out"]

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"       # keep-alive
        disable_nagle_algorithm = True
        wbufsize = -1                      # header+body ek hi segment me

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/ping":
                out = {"alive": node.alive}
            elif self.path == "/client":
                out = submit(body["cmd"])
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
    ThreadingHTTPServer.request_queue_size = 128
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()