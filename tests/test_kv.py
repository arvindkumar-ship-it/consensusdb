from distributed.kv import KV

def test_apply(make_cluster):
    n = make_cluster()
    for x in n.values():
        x.sm = KV()
    n["n1"].start_election()
    n["n1"].client_request("SET a 1")
    n["n1"].replicate()               # followers ko commit index pahunchao
    for x in n.values():
        x.apply_committed()
    assert all(x.sm.data == {"a": "1"} for x in n.values())