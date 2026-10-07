import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from optimizer import cost, features, validator
from optimizer.llm_client import LLMError, parse_json_reply
from optimizer.optimizer import Optimizer
from optimizer.service import OptimizerService
from workload.recorder import WorkloadRecorder


def make_workload(n=60):
    r = WorkloadRecorder(persist=False)
    r.record("CREATE TABLE users (id INT, email TEXT, age INT)", "users", 1)
    r.record("CREATE TABLE orders (id INT, user_id INT)", "orders", 1)
    for i in range(1000):
        r.schema.observe(f"INSERT INTO users VALUES ({i}, 'e{i}', 20)")
    for i in range(n):
        r.record(f"SELECT * FROM users WHERE email = 'e{i}'", "users", 40 + i % 5)
    for i in range(10):
        r.record(f"SELECT * FROM users WHERE id = {i}", "users", 1)
    r.record("SELECT * FROM users u JOIN orders o ON u.id = o.user_id", "users", 9)
    return r


class FakeLLM:
    available = True

    def __init__(self, reply):
        self.reply = reply

    def complete(self, prompt):
        assert "Workload summary" in prompt
        return self.reply


def test_features_shape():
    r = make_workload()
    f = features.extract(r.snapshot(), r.schema, group_of=lambda t: "g1" if t == "users" else "g2")
    u = f["tables"]["users"]
    assert u["row_count"] == 1000 and u["full_scan_pct"] > 80 and u["where_columns"]["email"] == 60
    assert f["frequent_joins"][0]["cross_shard"] is True
    assert f["slow_queries"][0]["latency_ms"] >= 40


def test_percentile():
    assert features.percentile([1, 2, 3, 4, 5], 50) == 3
    assert features.percentile([], 95) == 0.0


def test_rules_fallback_suggests_email_index():
    r = make_workload()
    out = Optimizer(r, group_of=lambda t: "g1" if t == "users" else "g2", client=FakeLLM("garbage no json")).run()
    assert out["source"] == "rules" and "JSON" in out["llm_error"]
    s = out["suggestions"][0]
    assert s["table"] == "users" and s["columns"] == ["email"] and s["ddl"].startswith("CREATE INDEX idx_users_email")
    assert any("alag shard" in n for n in out["notes"])


def test_llm_suggestions_validated_and_bad_ones_rejected():
    r = make_workload()
    reply = "Sure!\n```json\n" + json.dumps({"indexes": [
        {"table": "users", "columns": ["email"], "type": "btree", "reason": "x"},
        {"table": "users", "columns": ["id"], "type": "btree", "reason": "pk already"},
        {"table": "users", "columns": ["nope"], "type": "btree", "reason": "ghost column"},
        {"table": "users; DROP TABLE users", "columns": ["email"], "type": "btree", "reason": "injection"},
        {"table": "users", "columns": ["age"], "type": "gin", "reason": "bad type"}],
        "notes": ["hi"]}) + "\n```"
    out = Optimizer(r, client=FakeLLM(reply)).run()
    assert out["source"] == "llm"
    assert [s["columns"] for s in out["suggestions"]] == [["email"]]
    assert len(out["rejected"]) == 4
    assert out["suggestions"][0]["cost"]["est_speedup_x"] > 1


def test_parse_json_reply_errors():
    assert parse_json_reply('text {"a": {"b": 1}} tail') == {"a": {"b": 1}}
    with pytest.raises(LLMError):
        parse_json_reply("no json here")
    with pytest.raises(LLMError):
        parse_json_reply('{"a": ')


def test_cost_model_calibrates_and_penalizes_writes():
    tf = {"row_count": 10000, "avg_latency_ms": 20.0, "full_scan_pct": 90, "write_pct": 50.0}
    assert cost.calibrate_io_cost(tf) == pytest.approx(0.002)
    e = cost.estimate({}, tf)
    assert e["est_after_ms"] < e["est_before_ms"] and e["est_write_slowdown_pct"] == 7.5


def test_service_apply_and_impact():
    r = make_workload()
    svc = OptimizerService(r, client=FakeLLM("nothing"))
    gen = svc.generate()
    sid = gen["suggestions"][0]["id"]
    calls = []
    res = svc.apply(sid, lambda t, ddl: calls.append((t, ddl)) or {"ok": "OK"})
    assert res["applied"] and calls[0][0] == "users" and "email" in r.schema.indexed("users")
    assert svc.apply("nope", lambda *a: {})["error"]
    assert svc.impact(sid)["significant"] is None  # after-data nahi hai abhi
    for i in range(40):  # index ke baad queries tez
        r.record(f"SELECT * FROM users WHERE email = 'e{i}'", "users", 2.0 + (i % 3) * 0.1)
    imp = svc.impact(sid)
    assert imp["significant"] is True and imp["improvement_pct"] > 80


def test_service_apply_failure_not_marked():
    r = make_workload()
    svc = OptimizerService(r, client=FakeLLM("x"))
    sid = svc.generate()["suggestions"][0]["id"]
    res = svc.apply(sid, lambda t, d: {"error": "no leader"})
    assert res["applied"] is False and "email" not in r.schema.indexed("users")


def test_validator_ddl():
    assert validator.index_ddl({"table": "t", "columns": ["a", "b"]}) == "CREATE INDEX idx_t_a_b ON t (a, b)"


def test_max_five_suggestions_cap():
    r = make_workload()
    many = {"indexes": [{"table": "users", "columns": ["email"], "type": "btree", "reason": "x"}] +
            [{"table": "ghost", "columns": ["a"], "type": "btree", "reason": "x"}] * 9}
    out = Optimizer(r, client=FakeLLM(json.dumps(many))).run()
    assert len(out["suggestions"]) + len(out["rejected"]) <= 5
