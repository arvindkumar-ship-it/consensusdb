"""Hot key detector: kaunsi (table, column, value) pe sabse zyada equality lookups aa rahe hain.

Recorder har entry me raw sql rakhta hai, isliye recorder/sqlinfo badalne ki zaroorat nahi:
yahan sql se WHERE ke `col = literal` nikalte hain. Sirf equality (`=`). IN/range/LIKE nahi.
Join queries me sirf main table ke columns (unqualified ya table.col) gine jaate hain,
alias wale chhod diye jaate hain (galat table me ginne se behtar hai na ginna).
"""
import re
from collections import Counter, defaultdict

from . import sqlinfo

_EQ = re.compile(r"(?:(\w+)\.)?(\w+)\s*=\s*('(?:[^']|'')*'|-?\d+(?:\.\d+)?)", re.I)


def _lit(tok: str) -> str:
    return tok[1:-1].replace("''", "'") if tok.startswith("'") else tok


def lookups(entry: dict) -> list[tuple[str, str, str]]:
    """Ek query se [(table, column, value), ...]. Select/update/delete ke WHERE se."""
    if entry.get("kind") not in ("select", "update", "delete") or not entry.get("ok", True):
        return []
    table = entry.get("table")
    sql = entry.get("sql") or ""
    m = sqlinfo._WHERE.search(sqlinfo.clean(sql))
    if not table or not m:
        return []
    out = []
    for q, col, tok in _EQ.findall(m.group(1)):
        if q and q.lower() != table:
            continue
        out.append((table, col.lower(), _lit(tok)))
    return out


def detect(entries, top_n: int = 5, min_count: int = 20, min_share_pct: float = 10.0) -> list[dict]:
    """Top hot keys. Share = us (table, column) ke total equality lookups me is value ka hissa."""
    per_col: dict = defaultdict(Counter)
    for e in entries:
        for t, c, v in lookups(e):
            per_col[(t, c)][v] += 1
    hot = []
    for (t, c), vals in per_col.items():
        total = sum(vals.values())
        for v, n in vals.most_common(3):
            share = 100.0 * n / total
            if n >= min_count and share >= min_share_pct:
                hot.append({"table": t, "column": c, "value": v, "count": n,
                            "share_pct": round(share, 1), "distinct_values": len(vals)})
    hot.sort(key=lambda h: (-h["count"], h["table"], h["column"], h["value"]))
    return hot[:top_n]