"""LLM se baat. ANTHROPIC_API_KEY set ho to Claude API, warna optimizer rule-based fallback pe chalega (offline bhi chalta hai)."""
import json
import os
import re
import urllib.request


class LLMError(Exception):
    pass


class AnthropicClient:
    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: float = 30.0):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model or os.environ.get("CONSENSUSDB_LLM_MODEL", "claude-sonnet-5-5")
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def complete(self, prompt: str) -> str:
        if not self.api_key:
            raise LLMError("ANTHROPIC_API_KEY set nahi hai")
        body = json.dumps({"model": self.model, "max_tokens": 1000,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", body, {
            "content-type": "application/json", "x-api-key": self.api_key, "anthropic-version": "2023-06-01"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read())
        except Exception as e:  # network, HTTP error, timeout - sab ko ek hi error me lapet do
            raise LLMError(str(e)) from e
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def parse_json_reply(text: str) -> dict:
    """LLM kabhi ```json fence ya extra baat laga deta hai. Pehla {...} block nikaalo."""
    text = re.sub(r"```(?:json)?", "", text)
    start = text.find("{")
    if start < 0:
        raise LLMError("reply me JSON nahi mila")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    out = json.loads(text[start:i + 1])
                except ValueError as e:
                    raise LLMError(f"JSON kharab: {e}") from e
                if not isinstance(out, dict):
                    raise LLMError("JSON object nahi hai")
                return out
    raise LLMError("JSON adhura hai")
