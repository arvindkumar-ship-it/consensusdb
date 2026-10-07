import pytest
from distributed.raft_node import RaftNode
@pytest.fixture
def make_cluster():
    def build(n=3):
        ids = [f"n{i}" for i in range(1,n+1)]
        nodes = {i: RaftNode(i,[p for p in ids if p != i]) for i in ids}
        for node in nodes.values():
            node.connect_peers(nodes)
        return nodes
    return build