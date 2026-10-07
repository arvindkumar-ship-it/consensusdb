import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from optimizer import features, rules
from workload import hotkeys
from workload.recorder import WorkloadRecorder


def rec(r, sql, n=1, ms=1.0):
    for _ in range(n):
        r.record(sql, None, ms)


def test_lookups_basic_and_quotes():
    e = {"kind": "select", "table": "users", "ok": True,
         "sql": "SELECT * FROM users WHERE email = 'o''x@b.c' AND age = 5 AND age2 > 3"}
    assert hotkeys.lookups(e) == [("users", "email", "o'x@b.c"), ("users", "age", "5")]


def test_lookups_skips_insert_failed_and_foreign_alias():
    assert hotkeys.lookups({"kind": "insert", "table": "t", "sql": "INSERT INTO t VALUES (1)"}) == []
    assert hotkeys.lookups({"kind": "select", "table": "t", "ok": False, "sql": "SELECT * FROM t WHERE id = 1"}) == []
    e = {"kind": "select", "table": "users", "ok": True,
         "sql": "SELECT * FROM users u JOIN orders o ON u.id = o.uid WHERE o.id = 7 AND users.id = 3"}
    assert hotkeys.lookups(e) == [("users", "id", "3")]


def test_detect_finds_hot_and_ignores_uniform():
    r = WorkloadRecorder(persist=False)
    rec(r, "SELECT * FROM t WHERE id = 42", 60)
    for i in range(40):
        rec(r, f"SELECT * FROM t WHERE id = {1000 + i}")
    for i in range(100):
        rec(r, f"SELECT * FROM u WHERE id = {i}")          # uniform: koi hot nahi
    hot = hotkeys.detect(r.snapshot())
    assert len(hot) == 1
    h = hot[0]
    assert (h["table"], h["column"], h["value"], h["count"]) == ("t", "id", "42", 60)
    assert h["share_pct"] == 60.0 and h["distinct_values"] == 41


def test_detect_thresholds():
    r = WorkloadRecorder(persist=False)
    rec(r, "SELECT * FROM t WHERE id = 1", 5)
    assert hotkeys.detect(r.snapshot()) == []                # min_count=20 se kam
    assert hotkeys.detect(r.snapshot(), min_count=5)[0]["value"] == "1"


def test_features_and_rules_note():
    r = WorkloadRecorder(persist=False)
    r.schema.observe("CREATE TABLE t (id INT PRIMARY KEY, name TEXT)")
    rec(r, "SELECT * FROM t WHERE id = 9", 50)
    f = features.extract(r.snapshot(), r.schema)
    assert f["hot_keys"][0]["value"] == "9"
    out = rules.suggest(f)
    assert any("Hot key" in n and "t.id = 9" in n for n in out["notes"])


def test_no_hot_keys_key_is_empty_list():
    r = WorkloadRecorder(persist=False)
    rec(r, "INSERT INTO t VALUES (1)")
    assert features.extract(r.snapshot(), r.schema)["hot_keys"] == []