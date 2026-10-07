import socket
import threading
import time

from distributed import conn
from distributed.kv import KV
from distributed.raft_node import RaftNode
from distributed.rpc import serve


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def test_connection_is_reused_and_survives_server_close(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)                       # serve() data/ yahin likhega
    port = free_port()
    node = RaftNode("ka1", [])
    node.sm = KV()
    threading.Thread(target=serve, args=(node, port), daemon=True).start()
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.05)
    assert conn.post_json("127.0.0.1", port, "/status", {}, 2)["id"] == "ka1"
    c1 = conn._tls.conns[("127.0.0.1", port)]
    for _ in range(20):
        assert conn.post_json("127.0.0.1", port, "/status", {}, 2)["id"] == "ka1"
    assert conn._tls.conns[("127.0.0.1", port)] is c1                  # same connection, naya nahi bana
    c1.sock.shutdown(socket.SHUT_RDWR)                                   # stale conn jaisa haal
    assert conn.post_json("127.0.0.1", port, "/status", {}, 2)["id"] == "ka1"   # ek retry se theek
