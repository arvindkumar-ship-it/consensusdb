import os
import random
from distributed.raft_node import RaftNode
from distributed.states import Nodestate


class Link:
    """Peer ka proxy: cut hone par node 'alive' nahi dikhta (partition ka asar)."""
    def __init__(self, me, other, cuts):
        self.me, self.other, self.cuts = me, other, cuts

    @property
    def alive(self):
        return self.other.alive and frozenset((self.me.node_id, self.other.node_id)) not in self.cuts

    def __getattr__(self, name):
        return getattr(self.other, name)


def cluster(n, cuts):
    ids = [f"n{i}" for i in range(n)]
    nodes = {i: RaftNode(i, [p for p in ids if p != i]) for i in ids}
    for me in nodes.values():
        me.connect_peers({p: Link(me, nodes[p], cuts) for p in me.peer_ids})
    return nodes


def check(nodes, leaders, committed):
    for n in nodes.values():
        if n.state == Nodestate.LEADER:       # ek term me ek hi leader
            assert leaders.setdefault(n.current_term, n.node_id) == n.node_id
    for n in nodes.values():                  # committed entry kabhi badalti nahi
        for i in range(1, n.commit_index + 1):
            term = max(x.current_term for x in nodes.values() if x.commit_index >= i)
            assert committed.setdefault(i, (n.log[i], term))[0] == n.log[i]
    for n in nodes.values():                  # commit ke baad ke term ka leader wo entry rakhta hai
        if n.state == Nodestate.LEADER:
            for i, (e, term) in committed.items():
                if n.current_term > term:
                    assert i < len(n.log) and n.log[i] == e


def run(seed, size=5, steps=600):
    rnd, cuts, leaders, committed = random.Random(seed), set(), {}, {}
    random.seed(seed)                         # node ke election timeouts bhi repeatable
    nodes = cluster(size, cuts)
    for step in range(steps):
        r = rnd.random()
        n = rnd.choice(list(nodes.values()))
        if r < 0.05:
            n.alive = False
        elif r < 0.12:
            n.alive = True
        elif r < 0.17:
            cuts.add(frozenset(rnd.sample(list(nodes), 2)))
        elif r < 0.22:
            cuts.clear()
        elif r < 0.45:
            n.client_request(f"cmd{step}")
        for x in rnd.sample(list(nodes.values()), size):
            x.tick()
        check(nodes, leaders, committed)
    return len(committed)


def test_invariants_under_chaos():
    seeds = int(os.environ.get("CHAOS_SEEDS", 200))   # gehra run: CHAOS_SEEDS=3000 (Figure 8 jaise rare bug ke liye)
    assert sum(run(seed) for seed in range(seeds)) > 0   # kuch commit bhi hua, sirf safe-but-dead nahi
