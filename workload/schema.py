"""Router se guzarne wale DDL/INSERT dekh ke schema ka andaza rakhna (table, columns, pk, index, row count)."""
import json
import os
import re
import threading

from .sqlinfo import clean

_CONSTRAINT = {"primary", "foreign", "unique", "key", "constraint", "check", "index"}


def _split_top(s: str):
    out, depth, cur = [], 0, []
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if cur:
        out.append("".join(cur))
    return [x.strip() for x in out if x.strip()]


class SchemaTracker:
    def __init__(self, path: str | None = None):
        self.path = path
        self.tables: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._dirty_inserts = 0
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    raw = json.load(f)
                for t, d in raw.items():
                    d["indexes"] = set(d.get("indexes", []))
                    self.tables[t] = d
            except (OSError, ValueError):
                pass

    # ---- queries ----
    def exists(self, table: str) -> bool:
        return table in self.tables

    def columns(self, table: str) -> list[str]:
        return list(self.tables.get(table, {}).get("columns", []))

    def pk(self, table: str):
        return self.tables.get(table, {}).get("pk")

    def indexed(self, table: str) -> set:
        d = self.tables.get(table)
        if not d:
            return set()
        return set(d["indexes"]) | ({d["pk"]} if d.get("pk") else set())

    def rows(self, table: str) -> int:
        return int(self.tables.get(table, {}).get("rows", 0))

    # ---- updates ----
    def observe(self, sql: str, ok: bool = True):
        if not ok:
            return
        s = clean(sql)
        low = s.lower()
        with self._lock:
            if low.startswith("create table"):
                self._create_table(s)
                self._save()
            elif low.startswith("create index"):
                m = re.match(r"create\s+(?:unique\s+)?index\s+\w+\s+on\s+(\w+)\s*\(([^)]*)\)", s, re.I)
                if m and m.group(1).lower() in self.tables:
                    cols = [c.strip().lower() for c in m.group(2).split(",")]
                    if len(cols) == 1:
                        self.tables[m.group(1).lower()]["indexes"].add(cols[0])
                    self._save()
            elif low.startswith("insert"):
                m = re.match(r"insert\s+into\s+(\w+)", s, re.I)
                if m and m.group(1).lower() in self.tables:
                    self.tables[m.group(1).lower()]["rows"] += 1 + low.count("),(") + low.count("), (")
                    self._dirty_inserts += 1
                    if self._dirty_inserts >= 50:
                        self._save()

    def _create_table(self, s: str):
        m = re.match(r"create\s+table\s+(?:if\s+not\s+exists\s+)?(\w+)\s*\((.*)\)\s*$", s, re.I | re.S)
        if not m:
            return
        name, body = m.group(1).lower(), m.group(2)
        cols, pk = [], None
        for part in _split_top(body):
            first = part.split()[0].lower()
            if first in _CONSTRAINT:
                mm = re.search(r"primary\s+key\s*\((\w+)", part, re.I)
                if mm:
                    pk = mm.group(1).lower()
                continue
            cols.append(first)
            if re.search(r"primary\s+key", part, re.I):
                pk = first
        if cols:
            self.tables[name] = {"columns": cols, "pk": pk or cols[0], "indexes": set(), "rows": 0}

    def _save(self):
        self._dirty_inserts = 0
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        raw = {t: {**d, "indexes": sorted(d["indexes"])} for t, d in self.tables.items()}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(raw, f)
        os.replace(tmp, self.path)  # atomic rename: half-written file kabhi nahi dikhega
