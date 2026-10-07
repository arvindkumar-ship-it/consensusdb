import json

PROMPT = """You are a database performance engineer. A small SQL engine (B-tree on the primary key only,
supports CREATE INDEX on a single column) is sharded by table name across Raft groups.
Analyse the workload summary and suggest ONLY indexes. Do not invent tables or columns.

## Workload summary (JSON)
{features}

## Rules
- Only suggest a column that appears in a table's "columns" list and is NOT already in "indexed".
- Prefer columns with high share in "where_columns" on tables with high "full_scan_pct".
- Be careful with tables with high "write_pct": every index slows writes.
- If a join in "frequent_joins" has "cross_shard": true, add a note (not an index) saying it cannot work across shards.
- "hot_keys" lists single (table, column, value) hotspots. An index does NOT fix a hot key; if one has a big
  "share_pct", add a note (caching or read replicas), not an index.
- Return AT MOST 5 indexes. Return JSON only, no markdown, exactly this shape:

{{"indexes": [{{"table": "users", "columns": ["email"], "type": "btree", "reason": "..."}}],
  "notes": ["..."]}}
"""


def build(features: dict) -> str:
    return PROMPT.format(features=json.dumps(features, indent=1))