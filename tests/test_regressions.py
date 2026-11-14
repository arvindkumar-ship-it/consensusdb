"""Paanch bugs ke regression tests: catch-up cost, slow follower, stale read, ambiguous write/dedup, shard map."""
import json
import os
import signal
import subprocess
import sys
import time
import http.client

from distributed.kv import KV
from distributed.raft_node import RaftNode
from distributed.states import Nodestate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Link:
    def __init__(self, me, other, cuts, delay=0.0, stats=None):
        self.me, self.other, self.cuts, self.delay, self.stats = me, other, cuts, delay, stats

    @property
    def alive(self):
        return self.other.alive and frozenset((self.me.node_id, self.other.node_id)) not in self.cuts

    def handle_append_entries(self, *a):
        if self.stats is not None:
            self.stats["rpcs"] += 1
            self.stats["entries"] += len(a[4])
        if self.delay:
            time.sleep(self.delay)
        return self.other.handle_append_entries(*a)

    def __getattr__(self, name):
        return getattr(self.other, name)


class Counter:
    def __init__(self):
        self.n = 0

    def apply(self, cmd):
        self.n += 1


def cluster(delays=None, stats=None, sm=KV):
    cuts, ids = set(), ["n0", "n1", "n2"]
    nodes = {i: RaftNode(i, [p for p in ids if p != i]) for i in ids}
    for me in nodes.values():
        me.sm = sm()
        me.connect_peers({p: Link(me, nodes[p], cuts, (delays or {}).get(p, 0.0), stats) for p in me.peer_ids})
    return nodes, cuts


def elect(nodes, who):
    """who ko leader banao (deterministic)."""
    nodes[who].start_election()
    assert nodes[who].state == Nodestate.LEADER
    nodes[who].replicate()
    return nodes[who]


def settle(nodes):
    for x in nodes.values():
        x.tick()
        x.apply_committed()


def test_catch_up_after_leader_change_is_not_quadratic():
    stats = {"rpcs": 0, "entries": 0}
    nodes, _ = cluster(stats=stats)
    old = elect(nodes, "n0")
    nodes["n2"].alive = False
    for i in range(2000):
        old.client_request(f"SET k{i} v")
    old.alive = False
    nodes["n2"].alive = True
    new = elect(nodes, "n1")
    stats["rpcs"] = stats["entries"] = 0
    new.replicate()
    assert len(nodes["n2"].log) == len(new.log)
    assert stats["rpcs"] <= 12 and stats["entries"] <= 2 * 2100     # pehle: 2001 RPC, 20 lakh entries


def test_slow_follower_does_not_slow_writes():
    nodes, _ = cluster(delays={"n2": 0.3})
    L = elect(nodes, "n0")
    L.wait_all = False
    t = time.perf_counter()
    idx = L.client_append("SET a 1")
    assert L.wait_commit(idx, 2.0)
    assert time.perf_counter() - t < 0.15                            # pehle: 300 ms
    time.sleep(0.4)                                                  # slow push khatam hone do


def test_partitioned_old_leader_refuses_reads():
    nodes, cuts = cluster()
    old = elect(nodes, "n0")
    old.client_request("SET x old")
    settle(nodes)
    assert old.read_barrier(0.5)
    cuts.update({frozenset(("n0", "n1")), frozenset(("n0", "n2"))})
    new = elect(nodes, "n1")
    new.client_request("SET x new")
    assert old.state == Nodestate.LEADER                             # use abhi pata nahi
    assert not old.read_barrier(0.2)                                 # par read nahi dega
    assert new.read_barrier(0.5) and new.sm.data["x"] == "new"


def test_uncommitted_write_is_unknown_then_commits_once():
    nodes, cuts = cluster(sm=Counter)
    L = elect(nodes, "n0")
    cuts.update({frozenset(("n0", "n1")), frozenset(("n0", "n2"))})
    idx = L.client_append("#r1 SET y 1")
    assert not L.wait_commit(idx, 0.1)                               # commit nahi: client ko 'unknown' milta hai
    cuts.clear()
    L.client_request("#r1 SET y 1")                                  # client ne same rid se retry kiya
    settle(nodes)
    settle(nodes)
    assert L.commit_index >= idx + 1
    assert [n.sm.n for n in nodes.values()] == [1, 1, 1]             # do entries, ek hi baar apply


def test_shardmap_survives_router_restart(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SHARDMAP", str(tmp_path / "shardmap.json"))
    sys.modules.pop("router", None)
    import router
    assert "g3" not in router.GROUPS
    router.GROUPS["g3"] = router.SPARE["g3"]
    router.save_shardmap(1)
    router.GROUPS.pop("g3")
    assert router.load_shardmap() == 1 and "g3" in router.GROUPS     # restart ke baad g3 wapas ring me
    router.GROUPS.pop("g3")
    sys.modules.pop("router", None)


def _post(port, path, body, timeout=5):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        c.request("POST", path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        return json.loads(c.getresponse().read())
    finally:
        c.close()


def test_real_cluster_kill_leader_and_follower_read(tmp_path):
    """Asli processes: follower read mana kare, leader kill -9 ke baad koi acked write na khoye."""
    env = dict(os.environ, PYTHONPATH=ROOT, ROUTER_PORT="8090")
    env.pop("USE_MKDB", None)
    names = {"g1n1": 8001, "g1n2": 8002, "g1n3": 8003, "g2n1": 8011, "g2n2": 8012, "g2n3": 8013}
    procs = {n: subprocess.Popen([sys.executable, os.path.join(ROOT, "run_node.py"), n], cwd=tmp_path, env=env)
             for n in names}
    procs["router"] = subprocess.Popen([sys.executable, os.path.join(ROOT, "router.py")], cwd=tmp_path, env=env)
    try:
        def put(k, v):
            try:
                return _post(8090, "/set", {"key": k, "value": v}).get("ok") is True
            except (OSError, ValueError):
                return False

        deadline = time.time() + 20
        while not (put("warm:a", "1") and put("warm:b", "1") and put("warm:c", "1") and put("warm:d", "1")):
            assert time.time() < deadline, "cluster ready nahi hua"
            time.sleep(0.3)
        st = {n: _post(p, "/status", {}) for n, p in names.items() if n.startswith("g1")}
        leader = next(n for n, s in st.items() if s["state"] == "LEADER")
        follower = next(n for n in st if n != leader)
        assert _post(names[follower], "/get", {"key": "warm:a"}) == {"error": "not_leader"}

        acked = [k for k in (f"k:{i}" for i in range(150)) if put(k, "x")]
        if os.name == "nt":
            procs[leader].kill()
        else:
            os.kill(procs[leader].pid, signal.SIGKILL)
        acked += [k for k in (f"j:{i}" for i in range(150)) if put(k, "x")]
        assert len(acked) >= 290
        lost = [k for k in acked if _post(8090, "/get", {"key": k}).get("value") != "x"]
        assert lost == []
    finally:
        for p in procs.values():
            p.kill()
        for p in procs.values():
            p.wait(5)
