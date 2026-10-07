"""Har query ka log (JSONL) + in-memory buffer. Kafka ki jagah simple file: single machine pe wahi kaam, zero setup."""
import json
import os
import threading
import time
from collections import deque

from . import sqlinfo
from .schema import SchemaTracker


class WorkloadRecorder:
    def __init__(self, dir_path: str = "data/workload", max_mem: int = 20000, persist: bool = True):
        self.dir = dir_path
        self.persist = persist
        self.entries: deque = deque(maxlen=max_mem)
        self._lock = threading.Lock()
        self._fh = None
        if persist:
            os.makedirs(dir_path, exist_ok=True)
            self.log_path = os.path.join(dir_path, "queries.jsonl")
            self._load()
            # NOTE: yahan flush() hai, fsync() nahi. Query log best-effort hai. Raft wali galti (har tick fsync) dobara nahi.
            self._fh = open(self.log_path, "a", encoding="utf-8")
        self.schema = SchemaTracker(os.path.join(dir_path, "schema.json") if persist else None)

    def _load(self):
        if not os.path.exists(self.log_path):
            return
        with open(self.log_path, encoding="utf-8") as f:
            for line in f:
                try:
                    self.entries.append(json.loads(line))
                except ValueError:
                    pass  # aadhi likhi line (crash ke waqt) skip

    def record(self, sql: str, table: str | None, latency_ms: float, group: str | None = None,
               ok: bool = True, kind: str | None = None, bucket: str | None = None) -> dict:
        info = sqlinfo.parse(sql)
        main = info["table"] or (table or "").lower() or None
        self.schema.observe(sql, ok)
        entry = {
            "ts": time.time(),
            "sql": sql,
            "pattern": sqlinfo.normalize(sql),
            "kind": info["kind"] if info["kind"] != "other" else (kind or "other"),
            "table": main,
            "tables": info["tables"],
            "group": group,
            "latency_ms": round(float(latency_ms), 3),
            "ok": bool(ok),
            "where_cols": [list(x) for x in info["where_cols"]],
            "joins": [list(j) for j in info["joins"]],
            "join_cols": [list(x) for x in info["join_cols"]],
            "full_scan": self._is_full_scan(info),
            "bucket": bucket,
        }
        with self._lock:
            self.entries.append(entry)
            if self._fh:
                self._fh.write(json.dumps(entry) + "\n")
                self._fh.flush()
        return entry

    def _is_full_scan(self, info: dict) -> bool:
        if info["kind"] not in ("select", "update", "delete"):
            return False
        main = info["table"]
        if not info["has_where"]:
            return True
        if not self.schema.exists(main):
            return True  # schema pata nahi, to pessimistic maano
        idx = self.schema.indexed(main)
        return not any(t == main and c in idx for t, c in info["where_cols"])

    def snapshot(self, since: float | None = None) -> list[dict]:
        with self._lock:
            data = list(self.entries)
        return [e for e in data if since is None or e["ts"] >= since]

    def close(self):
        if self._fh:
            self._fh.close()
            self._fh = None
