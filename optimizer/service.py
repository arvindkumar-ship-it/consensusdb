"""Optimizer + suggestion store + 'apply' + before/after impact. Router isko use karta hai."""
import threading
import time

from abtest.stats import welch
from .optimizer import Optimizer


class OptimizerService:
    def __init__(self, recorder, group_of=None, client=None):
        self.recorder = recorder
        self.opt = Optimizer(recorder, group_of, client)
        self.store: dict[str, dict] = {}
        self._lock = threading.Lock()

    def generate(self) -> dict:
        out = self.opt.run()
        with self._lock:
            for s in out["suggestions"]:
                old = self.store.get(s["id"])
                s["applied_at"] = old.get("applied_at") if old else None
                self.store[s["id"]] = s
        return out

    def apply(self, sid: str, execute) -> dict:
        """execute(table, ddl) -> router ka raft-write result. DDL Raft se guzarta hai, to sab replicas pe lagta hai."""
        with self._lock:
            s = self.store.get(sid)
        if not s:
            return {"error": f"suggestion {sid} nahi mili, pehle /optimize/run chalao"}
        result = execute(s["table"], s["ddl"])
        failed = isinstance(result, dict) and "error" in result
        if not failed:
            self.recorder.schema.observe(s["ddl"], True)
            with self._lock:
                s["applied_at"] = time.time()
        return {"id": sid, "ddl": s["ddl"], "result": result, "applied": not failed}

    def impact(self, sid: str, min_samples: int = 30) -> dict:
        """Index lagne se pehle vs baad ki read latency (us table pe). Welch t-test se."""
        s = self.store.get(sid)
        if not s or not s.get("applied_at"):
            return {"error": "suggestion apply nahi hui"}
        t0, tbl = s["applied_at"], s["table"]
        col = set(s["columns"])
        before, after = [], []
        for e in self.recorder.snapshot():
            if e["table"] != tbl or e["kind"] != "select" or not e["ok"]:
                continue
            if not any(c in col for t, c in e["where_cols"]):
                continue  # sirf wahi queries jo is column pe filter karti hain
            (before if e["ts"] < t0 else after).append(e["latency_ms"])
        return {"id": sid, "table": tbl, "columns": s["columns"], **welch(before, after, min_samples)}
