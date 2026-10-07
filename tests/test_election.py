from distributed.raft_node import RaftNode
from distributed.states import Nodestate

def test_single_node(make_cluster):
    n = make_cluster(1)["n1"]
    n.start_election()
    assert n.state == Nodestate.LEADER
def test_one_vote_per_term(make_cluster):
    n3 = make_cluster()["n3"]
    assert n3.handle_request_vote(1,"n1",0,0)[1] == True
    assert n3.handle_request_vote(1,"n2",0,0)[1] == False

def test_step_down(make_cluster):
    n = make_cluster()
    n["n1"].start_election()
    n["n2"].start_election()
    assert n["n1"].state == Nodestate.FOLLOWER
    assert n["n1"].current_term == 2

