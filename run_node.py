import sys
from distributed.raft_node import RaftNode
from distributed.rpc import RemotePeer, serve

PORTS = {"n1": 8001, "n2": 8002, "n3": 8003}
me = sys.argv[1]
others = [p for p in PORTS if p != me]
node = RaftNode(me, others)
node.connect_peers({p: RemotePeer(f"http://127.0.0.1:{PORTS[p]}") for p in others})
serve(node, PORTS[me])