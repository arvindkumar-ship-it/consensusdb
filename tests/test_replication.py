from distributed.states import Nodestate

def test_replicate(make_cluster):
    n = make_cluster()
    n["n1"].start_election()
    n["n1"].client_request("SET a 1")
    assert all(x.log[1].command == "SET a 1" for x in n.values())
    assert n["n1"].commit_index == 1

def test_stale_log_cannot_win(make_cluster):
    n = make_cluster()
    n["n1"].start_election()
    n["n1"].client_request("x")
    n["n1"].client_request("y")
    n["n3"].log = n["n3"].log[:1]
    n["n3"].start_election()
    assert n["n3"].state != Nodestate.LEADER

def test_majority_4_nodes(make_cluster):
    assert make_cluster(4)["n1"].majority() == 3