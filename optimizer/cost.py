"""Bahut simple cost model. Ye sach ka prediction nahi, ek ROUGH estimate hai taaki suggestions ko rank kar sakein.

Full scan : latency ~ rows * io_cost
B-tree    : latency ~ (log2(rows) + matches) * io_cost
Write cost: har index pe insert thoda mehnga (maan liya +15% per index, tuning ke liye constant).
"""
import math

DEFAULT_IO_MS_PER_ROW = 0.002
WRITE_PENALTY_PER_INDEX = 0.15


def calibrate_io_cost(tfeat: dict) -> float:
    """Observed full-scan latency / row_count se io cost nikaalo, warna default."""
    rows = tfeat.get("row_count", 0)
    if rows >= 100 and tfeat.get("avg_latency_ms", 0) > 0 and tfeat.get("full_scan_pct", 0) >= 50:
        return tfeat["avg_latency_ms"] / rows
    return DEFAULT_IO_MS_PER_ROW


def estimate(s: dict, tfeat: dict, selectivity: float = 0.01) -> dict:
    rows = max(int(tfeat.get("row_count", 0)), 1)
    io = calibrate_io_cost(tfeat)
    before = rows * io
    matches = max(1.0, rows * selectivity)
    after = (math.log2(rows + 1) + matches) * io
    write_pct = tfeat.get("write_pct", 0.0) / 100.0
    write_penalty_pct = round(100 * WRITE_PENALTY_PER_INDEX * write_pct, 1)
    return {
        "est_before_ms": round(before, 4),
        "est_after_ms": round(after, 4),
        "est_speedup_x": round(before / after, 1) if after else None,
        "est_write_slowdown_pct": write_penalty_pct,
        "assumptions": f"rows={rows}, io={io:.5f}ms/row, selectivity={selectivity}",
    }
