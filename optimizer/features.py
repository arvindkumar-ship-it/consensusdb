"""Raw query log -> chhota structured summary (LLM ko poora log nahi dena, tokens aur paisa dono jalte hain)."""
from collections import Counter, defaultdict

from workload import hotkeys


def percentile(values, p):
    if not values:
        return 0.0
    v = sorted(values)
    k = (len(v) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def extract(entries, schema=None, group_of=None, slow_n: int = 5) -> dict:
    per = defaultdict(lambda: {"lat": [], "reads": 0, "writes": 0, "scans": 0, "sel": 0, "cols": Counter(), "errors": 0})
    joins = Counter()
    slow = {}
    for e in entries:
        t = e.get("table")
        if not t:
            continue
        d = per[t]
        d["lat"].append(e["latency_ms"])
        if not e.get("ok", True):
            d["errors"] += 1
        if e["kind"] == "select":
            d["reads"] += 1
        elif e["kind"] in ("insert", "update", "delete"):
            d["writes"] += 1
        if e["kind"] in ("select", "update", "delete"):
            d["sel"] += 1
            if e.get("full_scan"):
                d["scans"] += 1
            for tt, c in e.get("where_cols", []):
                if tt == t:
                    d["cols"][c] += 1
        for j in e.get("joins", []):
            joins[tuple(j)] += 1
        if e["kind"] in ("select", "update", "delete"):
            p = e["pattern"]
            if p not in slow or slow[p]["latency_ms"] < e["latency_ms"]:
                slow[p] = {"pattern": p, "latency_ms": e["latency_ms"], "table": t, "full_scan": e.get("full_scan", False)}

    total = sum(len(d["lat"]) for d in per.values()) or 1
    tables = {}
    for t, d in per.items():
        n = len(d["lat"])
        tables[t] = {
            "queries": n,
            "share_pct": round(100 * n / total, 1),
            "reads": d["reads"],
            "writes": d["writes"],
            "write_pct": round(100 * d["writes"] / n, 1),
            "avg_latency_ms": round(sum(d["lat"]) / n, 3),
            "p95_latency_ms": round(percentile(d["lat"], 95), 3),
            "full_scan_pct": round(100 * d["scans"] / d["sel"], 1) if d["sel"] else 0.0,
            "where_columns": dict(d["cols"].most_common(5)),
            "error_count": d["errors"],
            "row_count": schema.rows(t) if schema else 0,
            "columns": schema.columns(t) if schema else [],
            "indexed": sorted(schema.indexed(t)) if schema else [],
            "group": group_of(t) if group_of else None,
        }
    top_joins = []
    for (a, b), c in joins.most_common(5):
        cross = bool(group_of) and group_of(a) != group_of(b)
        top_joins.append({"tables": [a, b], "count": c, "cross_shard": cross})
    slowest = sorted(slow.values(), key=lambda x: -x["latency_ms"])[:slow_n]
    return {"total_queries": len(entries), "tables": tables, "frequent_joins": top_joins, "slow_queries": slowest,
            "hot_keys": hotkeys.detect(entries)}