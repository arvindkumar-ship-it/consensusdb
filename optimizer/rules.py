"""LLM ke bina chalne wala fallback. Seedha heuristics."""


def suggest(features: dict, min_queries: int = 20, scan_threshold: float = 30.0, col_share: float = 0.3) -> dict:
    indexes, notes = [], []
    for t, f in features["tables"].items():
        if f["queries"] < min_queries or f["full_scan_pct"] < scan_threshold:
            continue
        total_filters = sum(f["where_columns"].values()) or 1
        for col, cnt in f["where_columns"].items():
            if col in f["indexed"] or (f["columns"] and col not in f["columns"]):
                continue
            share = cnt / total_filters
            if share >= col_share:
                indexes.append({"table": t, "columns": [col], "type": "btree",
                                "reason": f"{f['full_scan_pct']}% selects full scan, {round(100 * share)}% filters {col} pe"})
                break  # ek table pe ek hi best index
    for j in features["frequent_joins"]:
        if j["cross_shard"]:
            a, b = j["tables"]
            notes.append(f"JOIN {a} x {b}: tables alag shard-groups me hain, router isko execute nahi kar sakta. "
                         f"Dono tables ko ek group me rakho ya app-side join karo.")
    for h in features.get("hot_keys", []):
        if h["share_pct"] >= 20:
            notes.append(f"Hot key: {h['table']}.{h['column']} = {h['value']} pe {h['share_pct']}% lookups ({h['count']} queries). "
                         f"Index se ye theek nahi hoga, cache ya read replica soch.")
    return {"indexes": indexes, "notes": notes}