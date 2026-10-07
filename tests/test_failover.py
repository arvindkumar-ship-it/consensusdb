from distributed.states import Nodestate

def run(n, k=30):
    for _ in range(k):
        for x in n.values():
            x.tick()

def leaders(n):
    return [x for x in n.values() if x.alive and x.state == Nodestate.LEADER]

def test_leader_elected(make_cluster):
    n = make_cluster()
    run(n)
    assert len(leaders(n)) == 1

def test_failover(make_cluster):
    n = make_cluster()
    run(n)
    old = leaders(n)[0]
    old.alive = False
    run(n)
    assert len(leaders(n)) == 1 and leaders(n)[0] is not old