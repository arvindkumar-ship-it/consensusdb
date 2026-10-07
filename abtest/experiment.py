import hashlib
import threading
import time

from .stats import welch


class TrafficSplitter:
    """Same key -> hamesha same bucket (hash se), random nahi. Isse ek user ko kabhi control kabhi treatment nahi milta."""

    def __init__(self, name: str, treatment_pct: int = 50):
        if not 0 <= treatment_pct <= 100:
            raise ValueError("treatment_pct 0..100")
        self.name, self.pct = name, treatment_pct

    def bucket(self, key: str) -> str:
        h = int(hashlib.sha256(f"{self.name}:{key}".encode()).hexdigest(), 16) % 100
        return "treatment" if h < self.pct else "control"


class ExperimentManager:
    def __init__(self):
        self.active: dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(self, name: str, treatment_pct: int = 50):
        with self._lock:
            self.active[name] = {"splitter": TrafficSplitter(name, treatment_pct), "control": [], "treatment": [],
                                 "errors": {"control": 0, "treatment": 0}, "started": time.time()}

    def stop(self, name: str):
        with self._lock:
            self.active.pop(name, None)

    def assign(self, key: str) -> dict:
        return {n: e["splitter"].bucket(key) for n, e in list(self.active.items())}

    def record(self, name: str, bucket: str, latency_ms: float, ok: bool = True):
        with self._lock:
            e = self.active.get(name)
            if not e:
                return
            e[bucket].append(latency_ms)
            if not ok:
                e["errors"][bucket] += 1

    def report(self, name: str) -> dict:
        with self._lock:
            e = self.active.get(name)
            if not e:
                return {"error": f"experiment {name} nahi mila"}
            c, t = list(e["control"]), list(e["treatment"])
            errs = dict(e["errors"])
        out = welch(c, t)
        out["error_rate_control"] = round(errs["control"] / len(c), 4) if c else 0
        out["error_rate_treatment"] = round(errs["treatment"] / len(t), 4) if t else 0
        return out
