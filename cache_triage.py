"""Lever 1: exact-match response cache for AfyaPlus triage.

- Key = sha256(model | prompt version | normalised message). Changing the
  model or bumping PROMPT_VERSION invalidates every cached answer.
- Backend: Redis if REDIS_URL is reachable, else an in-process dict.
- Model: set USE_LLM=1 (plus LLM_API_KEY, optional LLM_BASE_URL/LLM_MODEL)
  to call a real OpenAI-compatible endpoint. Otherwise a stub answers,
  which is enough to measure hit rate and model-call counts, but NOT
  latency or answer quality.
"""
import hashlib
import json
import os
import time
from functools import wraps

MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
PROMPT_VERSION = os.getenv("PROMPT_VERSION", "triage-v1")  # bump on prompt change
USE_LLM = os.getenv("USE_LLM") == "1"
CACHE_TTL_S = 600
URGENCY_LEVELS = {"emergency", "urgent", "routine"}

SYSTEM_PROMPT = (
    "You are a triage assistant for a Kenyan clinic network. Classify the "
    "patient's message as emergency, urgent or routine and give brief safe "
    "advice. Never diagnose. For emergency, tell them to seek care now. "
    'Reply only with JSON: {"urgency": "...", "advice": "..."}'
)

try:
    import redis
    r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"),
                             decode_responses=True)
    r.ping()
    BACKEND = "redis"
except Exception:
    r = None
    BACKEND = "memory"
_MEM = {}

metrics = {"hits": 0, "misses": 0, "model_calls": 0,
           "prompt_tokens": 0, "completion_tokens": 0}


def _key(message: str) -> str:
    norm = " ".join(message.strip().lower().split())
    raw = f"{MODEL}|{PROMPT_VERSION}|{norm}"
    return "triage:" + hashlib.sha256(raw.encode()).hexdigest()


def _get(key):
    if BACKEND == "redis":
        raw = r.get(key)
        return json.loads(raw) if raw else None
    row = _MEM.get(key)
    if not row:
        return None
    exp, val = row
    return val if exp > time.time() else None


def _set(key, value, ttl_s):
    if BACKEND == "redis":
        r.setex(key, ttl_s, json.dumps(value))
    else:
        _MEM[key] = (time.time() + ttl_s, value)


def reset_metrics():
    for k in metrics:
        metrics[k] = 0


def reset_cache():
    """Empty the cache and metrics so every measurement starts cold."""
    if BACKEND == "redis":
        for k in r.scan_iter("triage:*"):
            r.delete(k)
    _MEM.clear()
    reset_metrics()


def cache_response(ttl_s=CACHE_TTL_S):
    def deco(fn):
        @wraps(fn)
        def wrapper(message: str):
            key = _key(message)
            hit = _get(key)
            if hit is not None:
                metrics["hits"] += 1
                return {**hit, "_cache": "HIT", "_backend": BACKEND}
            out = fn(message)
            _set(key, out, ttl_s)
            metrics["misses"] += 1
            return {**out, "_cache": "MISS", "_backend": BACKEND}
        return wrapper
    return deco


def hit_rate():
    total = metrics["hits"] + metrics["misses"]
    return (metrics["hits"] / total) if total else 0.0


def _call_model(message: str) -> dict:
    metrics["model_calls"] += 1
    if not USE_LLM:
        return {"urgency": "routine",
                "advice": "Rest and hydrate. Seek clinic care if symptoms worsen.",
                "_source": "stub"}

    from openai import OpenAI
    client = OpenAI(base_url=os.getenv("LLM_BASE_URL") or None,
                    api_key=os.getenv("LLM_API_KEY"))
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": message}],
    )
    if resp.usage:
        metrics["prompt_tokens"] += resp.usage.prompt_tokens
        metrics["completion_tokens"] += resp.usage.completion_tokens
    try:
        data = json.loads(resp.choices[0].message.content)
    except (json.JSONDecodeError, TypeError):
        data = {}
    urgency = str(data.get("urgency", "")).strip().lower()
    return {"urgency": urgency if urgency in URGENCY_LEVELS else "unparsed",
            "advice": data.get("advice", ""),
            "_source": "llm"}


@cache_response()
def triage(message: str) -> dict:
    return _call_model(message)
