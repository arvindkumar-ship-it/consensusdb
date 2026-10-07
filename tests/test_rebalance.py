from distributed.rebalance import cmds_for, moves, rebalance
from distributed.ring import Ring

OLD, NEW = Ring(["g1", "g2"]), Ring(["g1", "g2", "g3"])


def make_logs():
    logs = {"g1": [], "g2": []}
    for i in range(60):
        logs[OLD.get(f"k{i}")].append(f"SET k{i} v")
    for t in ("users", "orders", "items"):
        logs[OLD.get(t)] += [f"CREATE TABLE {t} (id INT)", f"INSERT INTO {t} VALUES (1)", f"CREATE INDEX i_{t} ON {t} (id)"]
    return logs


def test_keys_only_move_to_new_group():
    mv = moves(make_logs(), NEW)
    assert mv and all(dst == "g3" for _, dst in mv.values())
    assert len(mv) < 45                       # 63 me se kareeb 1/3, sab nahi


def test_copy_in_order_then_tombstone():
    logs, sent = make_logs(), []
    out = rebalance(logs, NEW, lambda g, c: sent.append((g, c)) or True)
    for name, (src, dst) in out["moved"].items():
        copies = [c for g, c in sent if g == dst and c in cmds_for(logs[src], name)]
        assert copies == cmds_for(logs[src], name)
        assert sent.index((src, f"MOVED {name}")) > sent.index((dst, copies[-1]))


def test_failure_aborts_without_tombstone():
    sent = []
    out = rebalance(make_logs(), NEW, lambda g, c: sent.append(c) or False)
    assert "error" in out and not any(c.startswith("MOVED") for c in sent)


def test_second_run_finds_nothing_to_move():
    logs = make_logs()
    logs["g3"] = []
    rebalance(logs, NEW, lambda g, c: logs[g].append(c) or True)   # logs me hi apply
    assert moves(logs, NEW) == {}
