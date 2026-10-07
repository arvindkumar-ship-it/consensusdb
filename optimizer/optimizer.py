import hashlib
import time

from . import cost, features as feat, prompt, rules, validator
from .llm_client import AnthropicClient, LLMError, parse_json_reply


class Optimizer:
    def __init__(self, recorder, group_of=None, client=None):
        self.recorder = recorder
        self.group_of = group_of
        self.client = client if client is not None else AnthropicClient()

    def run(self, since: float | None = None) -> dict:
        entries = self.recorder.snapshot(since)
        features = feat.extract(entries, self.recorder.schema, self.group_of)
        source, raw, error = "rules", None, None
        if getattr(self.client, "available", True):
            try:
                raw = parse_json_reply(self.client.complete(prompt.build(features)))
                source = "llm"
            except LLMError as e:
                error = str(e)
        if raw is None:
            raw = rules.suggest(features)

        good, rejected, seen = [], [], set()
        for s in raw.get("indexes", [])[:5]:
            ok, why = validator.validate_index(s, self.recorder.schema)
            if not ok:
                rejected.append({"suggestion": s, "reason": why})
                continue
            ddl = validator.index_ddl(s)
            if ddl in seen:
                continue
            seen.add(ddl)
            tf = features["tables"].get(s["table"], {})
            good.append({"id": hashlib.sha1(ddl.encode()).hexdigest()[:10], "ddl": ddl, **s,
                         "cost": cost.estimate(s, tf)})
        good.sort(key=lambda x: -(x["cost"]["est_speedup_x"] or 0))
        return {"source": source, "llm_error": error, "generated_at": time.time(),
                "suggestions": good, "rejected": rejected,
                "notes": [str(n) for n in raw.get("notes", [])][:10], "features": features}
