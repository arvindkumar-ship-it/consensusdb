"""LLM ka output kabhi blindly trust nahi karna. Ye sirf SUGGESTION hai, hum jaanch ke baad hi aage badhte hain.

Sabse zaroori: identifiers regex se check hote hain, kyunki ye text aage chalke CREATE INDEX SQL me jayega.
LLM se aaya 'users; DROP TABLE users' warna SQL injection ban jaata.
"""
import re

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
ALLOWED_TYPES = {"btree", "hash"}


def validate_index(s: dict, schema) -> tuple[bool, str]:
    if not isinstance(s, dict):
        return False, "suggestion dict nahi hai"
    table = str(s.get("table", "")).lower()
    cols = s.get("columns")
    typ = str(s.get("type", "btree")).lower()
    if not IDENT.match(table):
        return False, f"table naam invalid: {table!r}"
    if not isinstance(cols, list) or not (1 <= len(cols) <= 3):
        return False, "columns 1 se 3 ki list honi chahiye"
    cols = [str(c).lower() for c in cols]
    if not all(IDENT.match(c) for c in cols):
        return False, f"column naam invalid: {cols}"
    if typ not in ALLOWED_TYPES:
        return False, f"index type {typ!r} allowed nahi"
    if not schema.exists(table):
        return False, f"table {table!r} schema me nahi mila"
    known = set(schema.columns(table))
    missing = [c for c in cols if c not in known]
    if missing:
        return False, f"columns {missing} table me nahi hain"
    if len(cols) == 1 and cols[0] in schema.indexed(table):
        return False, f"{table}.{cols[0]} pe index pehle se hai (pk ya existing)"
    s["table"], s["columns"], s["type"] = table, cols, typ
    return True, "ok"


def index_ddl(s: dict) -> str:
    return f"CREATE INDEX idx_{s['table']}_{'_'.join(s['columns'])} ON {s['table']} ({', '.join(s['columns'])})"
