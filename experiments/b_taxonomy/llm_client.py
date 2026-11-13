"""Minimal OpenAI-compatible chat client for the DeepSeek API, with a content-addressed cache,
resume, a spending cap and cost accounting. Standard library only (no `openai` package needed).

- API key: environment variable DEEPSEEK_API_KEY, or a line `DEEPSEEK_API_KEY=...` in the
  git-ignored repo-root `.env`. The key is never printed, logged or written to the cache.
- Cache: every successful response is appended to a JSONL file, keyed by the SHA-256 of the exact
  request body (model, messages, temperature, response format, extra body, max_tokens). A rerun with
  the same request is answered from the cache, so an interrupted run resumes where it stopped and a
  finished run can be reproduced offline without any API call.
- Cost: computed from the usage fields the API returns, using the prices in configs/taxonomy/llm_v1.json.
"""
import hashlib
import http.client
import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from paths import ROOT

CONFIG_PATH = ROOT / "configs" / "taxonomy" / "llm_v1.json"


class CacheMiss(Exception):
    pass


class BudgetExceeded(Exception):
    pass


def load_config(model=None, **overrides):
    cfg = json.loads(CONFIG_PATH.read_text())
    if model:
        cfg["model"] = model
    cfg.update({k: v for k, v in overrides.items() if v is not None})
    return cfg


def api_key(name="DEEPSEEK_API_KEY"):
    key = os.environ.get(name, "").strip()
    env = ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith(name + "="):
                key = line.split("=", 1)[1].strip().strip("'\"")
    if not key:
        raise SystemExit(f"{name} is not set. Put it in the environment or in the repo-root .env (git-ignored).")
    return key


def cost_of(usage, pricing):
    p = pricing["per_million_tokens"]
    hit = usage.get("prompt_cache_hit_tokens", 0)
    miss = usage.get("prompt_cache_miss_tokens", usage.get("prompt_tokens", 0) - hit)
    out = usage.get("completion_tokens", 0)
    return (hit * p["input_cache_hit"] + miss * p["input_cache_miss"] + out * p["output"]) / 1e6


class LLM:
    def __init__(self, cfg, cache_path, max_cost=None, offline=False):
        self.cfg, self.cache_path, self.offline = cfg, cache_path, offline
        self.max_cost = cfg["default_max_cost"] if max_cost is None else max_cost
        self.lock = threading.Lock()
        self.cache = {}
        self.spent = 0.0  # new (non-cached) spending in this session
        self.stats = dict(api_calls=0, cache_hits=0, prompt_cache_hit_tokens=0, prompt_cache_miss_tokens=0,
                          completion_tokens=0, reasoning_tokens=0)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if cache_path.exists():
            for line in cache_path.read_text().splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self.cache[rec["key"]] = rec
        self._key = None if offline else api_key(cfg.get("api_key_env", "DEEPSEEK_API_KEY"))

    def body(self, messages, max_tokens=None):
        b = {"model": self.cfg["model"], "messages": messages, "temperature": self.cfg["temperature"]}
        if self.cfg.get("response_format"):
            b["response_format"] = self.cfg["response_format"]
        if max_tokens:
            b["max_tokens"] = max_tokens
        b.update(self.cfg.get("extra_body") or {})
        return b

    @staticmethod
    def key_of(body):
        return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def _post(self, body):
        url = self.cfg["base_url"].rstrip("/") + "/chat/completions"
        data = json.dumps(body).encode()
        for attempt in range(self.cfg["max_retries"] + 1):
            req = urllib.request.Request(url, data=data, method="POST", headers={
                "Authorization": f"Bearer {self._key}", "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.cfg["timeout_s"]) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                msg = e.read().decode(errors="replace")[:500]
                if e.code in (429, 500, 502, 503, 504) and attempt < self.cfg["max_retries"]:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise RuntimeError(f"HTTP {e.code}: {msg}") from None
            except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException, OSError) as e:
                if attempt < self.cfg["max_retries"]:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise RuntimeError(f"network error: {e}") from None

    def chat(self, messages, meta=None, max_tokens=None):
        """Return the cache record for this request (content, usage, cost, ...); call the API on a cache miss."""
        body = self.body(messages, max_tokens)
        k = self.key_of(body)
        with self.lock:
            if k in self.cache:
                self.stats["cache_hits"] += 1
                return {**self.cache[k], "from_cache": True}
            if self.offline:
                raise CacheMiss(k)
            if self.max_cost is not None and self.spent >= self.max_cost:
                raise BudgetExceeded(f"spent {self.spent:.4f} >= cap {self.max_cost}")
        resp = self._post(body)
        choice = resp["choices"][0]
        usage = resp.get("usage", {})
        reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
        rec = dict(key=k, created=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   model_requested=body["model"], model_returned=resp.get("model"),
                   system_fingerprint=resp.get("system_fingerprint"), meta=meta or {},
                   content=choice["message"].get("content"), finish_reason=choice.get("finish_reason"),
                   usage={k2: usage.get(k2, 0) for k2 in ("prompt_tokens", "prompt_cache_hit_tokens",
                                                          "prompt_cache_miss_tokens", "completion_tokens")}
                   | {"reasoning_tokens": reasoning},
                   cost=round(cost_of(usage, self.cfg["pricing"]), 8),
                   currency=self.cfg["pricing"]["currency"])
        with self.lock:
            self.cache[k] = rec
            with open(self.cache_path, "a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self.spent += rec["cost"]
            self.stats["api_calls"] += 1
            for f2 in ("prompt_cache_hit_tokens", "prompt_cache_miss_tokens", "completion_tokens", "reasoning_tokens"):
                self.stats[f2] += rec["usage"][f2]
        return {**rec, "from_cache": False}

    def summary(self):
        return {**self.stats, "new_cost": round(self.spent, 6), "currency": self.cfg["pricing"]["currency"],
                "pricing_status": self.cfg["pricing"]["status"][:60], "model": self.cfg["model"]}


def list_models(cfg):
    req = urllib.request.Request(cfg["base_url"].rstrip("/") + "/models",
                                 headers={"Authorization": f"Bearer {api_key(cfg.get('api_key_env', 'DEEPSEEK_API_KEY'))}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return [m["id"] for m in json.loads(r.read()).get("data", [])]


def parse_json(text):
    """Parse a JSON object from model output (tolerates ```json fences)."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(t)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Check the API connection and list available model IDs.")
    ap.add_argument("--list-models", action="store_true")
    a = ap.parse_args()
    print(list_models(load_config()))
