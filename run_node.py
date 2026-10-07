import os
import sys
from distributed.config import GROUPS
from distributed.kv import KV
from distributed.raft_node import RaftNode
from distributed.rpc import RemotePeer, serve

me = sys.argv[1]                                  # e.g. g1n1
members = next((m for m in GROUPS.values() if me in m), None)
if members is None:
    valid = sorted(n for g in GROUPS.values() for n in g)
    raise SystemExit(f"unknown node '{me}'. valid: {valid}")
others = [p for p in members if p != me]
node = RaftNode(me, others)

if os.environ.get("USE_MKDB") == "1":
    from distributed.mkdb_sm import MkdbSM
    node.sm = MkdbSM(me, members[me] + int(os.environ.get("MKDB_PORT_OFFSET", "20000")))      # g2n1: 8011 -> mkdb_server on 9011
else:
    node.sm = KV()

node.connect_peers({p: RemotePeer(f"http://127.0.0.1:{members[p]}") for p in others})
serve(node, members[me])
