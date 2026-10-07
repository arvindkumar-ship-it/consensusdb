"""SQL ko halka-phulka parse karna (full parser nahi, sirf wo cheezein jo workload analysis ko chahiye).

Kyun regex? Tera mkdb ka apna parser C++ me hai. Yahan hume sirf: kind, table, WHERE columns,
JOIN pairs chahiye. Poora SQL parser likhna overkill hai; regex 95% queries pakad leta hai.
"""
import re

_WS = re.compile(r"\s+")
_STR = re.compile(r"'(?:[^']|'')*'")
_NUM = re.compile(r"\b\d+(?:\.\d+)?\b")
_STOP = {"on", "where", "join", "inner", "left", "right", "outer", "group", "order", "limit", "set", "values"}
_TABLE_REF = re.compile(r"\b(?:from|join)\s+(\w+)(?:\s+(?:as\s+)?(\w+))?", re.I)
_JOIN_ON = re.compile(r"\bon\s+(?:(\w+)\.)?(\w+)\s*=\s*(?:(\w+)\.)?(\w+)", re.I)
_COND = re.compile(r"(?:(\w+)\.)?(\w+)\s*(?:=|<>|!=|<=|>=|<|>|\blike\b|\bin\b|\bbetween\b)", re.I)
_WHERE = re.compile(r"\bwhere\b(.*?)(?:\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)", re.I | re.S)


def clean(sql: str) -> str:
    return _WS.sub(" ", sql.strip().rstrip(";")).strip()


def normalize(sql: str) -> str:
    """Literals hata ke query ka 'shape' nikalna: WHERE id = 5 aur id = 9 ek hi pattern."""
    s = _STR.sub("?", clean(sql))
    return _NUM.sub("?", s).lower()


def parse(sql: str) -> dict:
    s = clean(sql)
    low = s.lower()
    info = {"kind": "other", "table": None, "tables": [], "where_cols": [], "joins": [], "join_cols": [], "has_where": False}

    if low.startswith("select"):
        info["kind"] = "select"
    elif low.startswith("insert"):
        info["kind"] = "insert"
        m = re.match(r"insert\s+into\s+(\w+)", s, re.I)
        if m:
            info["table"] = m.group(1).lower()
            info["tables"] = [info["table"]]
        return info
    elif low.startswith("update"):
        info["kind"] = "update"
        m = re.match(r"update\s+(\w+)", s, re.I)
        if m:
            info["tables"] = [m.group(1).lower()]
    elif low.startswith("delete"):
        info["kind"] = "delete"
    elif low.startswith("create table"):
        info["kind"] = "create_table"
        m = re.match(r"create\s+table\s+(?:if\s+not\s+exists\s+)?(\w+)", s, re.I)
        if m:
            info["table"] = m.group(1).lower()
            info["tables"] = [info["table"]]
        return info
    elif low.startswith("create index"):
        info["kind"] = "create_index"
        return info
    else:
        return info

    alias = {}
    if info["kind"] in ("select", "delete"):
        for t, a in _TABLE_REF.findall(s):
            t = t.lower()
            info["tables"].append(t)
            alias[t] = t
            if a and a.lower() not in _STOP:
                alias[a.lower()] = t
    else:
        for t in info["tables"]:
            alias[t] = t
    if info["tables"]:
        info["table"] = info["tables"][0]

    for a1, c1, a2, c2 in _JOIN_ON.findall(s):
        t1 = alias.get(a1.lower()) if a1 else None
        t2 = alias.get(a2.lower()) if a2 else None
        if t1 and t2 and t1 != t2:
            info["joins"].append(tuple(sorted((t1, t2))))
        for t, c in ((t1, c1), (t2, c2)):
            if t:
                info["join_cols"].append((t, c.lower()))

    m = _WHERE.search(s)
    if m:
        info["has_where"] = True
        for a, c in _COND.findall(m.group(1)):
            t = alias.get(a.lower()) if a else info["table"]
            if t:
                info["where_cols"].append((t, c.lower()))
    return info
