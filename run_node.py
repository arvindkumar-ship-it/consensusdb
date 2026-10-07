import sys
from distributed.config import GROUPS
from distributed.kv import KV
from distributed.raft_node import RaftNode
from distributed.rpc import RemotePeer, serve

me = sys.argv[1]                                  # e.g. g1n1
members = next(m for m in GROUPS.values() if me in m)
others = [p for p in members if p != me]
node = RaftNode(me, others)
node.sm = KV()
node.connect_peers({p: RemotePeer(f"http://127.0.0.1:{members[p]}") for p in others})
serve(node, members[me])