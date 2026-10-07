# ConsensusDB: workload analyzer + optimizer + A/B + bench

Sab stdlib. Koi nayi pip dependency nahi.

## Naye folders
- `workload/`  : query log (JSONL), SQL parse, schema tracker
- `optimizer/` : features -> prompt -> LLM (ya rules fallback) -> validator -> cost -> service
- `abtest/`    : traffic splitter + Welch t-test
- `bench/`     : load test (router pe)
- `router.py`  : purane routes same, naye: /stats /optimize/run /optimize/apply /optimize/impact /ab/start /ab/report /ab/stop

## Chalana
    $env:USE_MKDB = "1"
    .\start_all.ps1
    python router.py          # agar start_all.ps1 pehle se router chalata hai to ye mat chalao

Optional LLM:  `$env:ANTHROPIC_API_KEY = "sk-ant-..."` (bina key ke rules fallback chalta hai)

## Flow
    POST /sql   {"table":"users","sql":"CREATE TABLE users (id INT, email TEXT)"}
    ... inserts + selects ...
    POST /optimize/run                      -> suggestions (id, ddl, cost estimate)
    POST /optimize/apply  {"id":"..."}      -> CREATE INDEX Raft se sab replicas pe
    POST /optimize/impact {"id":"..."}      -> before/after latency, p-value

## Tests
    python -m pytest tests -q
