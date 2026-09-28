"""Before/after measurement for both cost levers.

Load script (stated, reproducible):
  Triage : 40 unique messages from fixtures/triage_messages.json
           + 60 repeats drawn with random.seed(7) = 100 requests, shuffled.
  Batch  : the same 100 texts enqueued as summarisation jobs.

For each lever it reports model calls, hit rate, USD per 1,000 requests
(API + infra, ops excluded) and p95 latency, then runs quality checks.
Writes results/levers_before_after.csv.

Cost basis: prices, token counts and infra overhead come from
afyaplus_cost_model.py. With USE_LLM=1, measured token usage replaces the
baseline token counts. Cache lookups are treated as free (see note [c]).
"""
import csv
import json
import math
import os
import random
import tempfile
import time
from pathlib import Path

import batch_worker as bw
import cache_triage as ct
from afyaplus_cost_model import (COMPLETION_TOKENS, INFRA_OVERHEAD,
                                 PRICE_COMPLETION_PER_M, PRICE_PROMPT_PER_M,
                                 PROMPT_TOKENS)

SEED = 7
N_REPEATS = 60

# Batch token assumptions (see notes [b1]-[b3])
SYSTEM_PROMPT_TOKENS = 350   # [b1] share of the 450-token baseline prompt
ITEM_TOKENS = 100            # [b1] the remaining 100 tokens: the message
ITEM_WRAPPER_TOKENS = 5      # [b2] numbering/separators per item in a batch
SUMMARY_TOKENS = 40          # [b3] one-line theme summary per item

OUT = Path("results/levers_before_after.csv")


def usd(prompt_tokens: float, completion_tokens: float) -> float:
    api = (prompt_tokens * PRICE_PROMPT_PER_M
           + completion_tokens * PRICE_COMPLETION_PER_M) / 1_000_000
    return api * (1.0 + INFRA_OVERHEAD)


def p95(values):
    s = sorted(values)
    return s[max(0, math.ceil(0.95 * len(s)) - 1)]


def build_calls():
    random.seed(SEED)
    msgs = json.load(open("fixtures/triage_messages.json"))
    assert len(msgs) == 40
    calls = list(msgs) + [random.choice(msgs) for _ in range(N_REPEATS)]
    random.shuffle(calls)
    return calls


# ---------------------------------------------------------------------------
# Lever 1: response cache
# ---------------------------------------------------------------------------
def run_triage(calls, use_cache: bool):
    ct.reset_cache()
    fn = ct.triage if use_cache else ct.triage.__wrapped__  # bypass cache
    latencies, outputs = [], []
    for m in calls:
        t0 = time.perf_counter()
        outputs.append(fn(m))
        latencies.append((time.perf_counter() - t0) * 1000)

    m = ct.metrics
    if m["prompt_tokens"]:  # measured usage from a real model
        total = usd(m["prompt_tokens"], m["completion_tokens"])
    else:                   # stub: baseline tokens per model call
        total = m["model_calls"] * usd(PROMPT_TOKENS, COMPLETION_TOKENS)

    return {
        "lever": "cache",
        "scenario": "after (cache on)" if use_cache else "before (no cache)",
        "requests": len(calls),
        "model_calls": m["model_calls"],
        "hit_rate": round(m["hits"] / len(calls), 2) if use_cache else 0.0,
        "usd_per_1k": round(1000 * total / len(calls), 4),
        "p95_ms": round(p95(latencies), 2),
        "backend": f"{ct.BACKEND}/{'llm' if ct.USE_LLM else 'stub'}",
    }, outputs


# ---------------------------------------------------------------------------
# Lever 2: batch queue
# ---------------------------------------------------------------------------
def run_batch(texts, batch_size: int):
    with tempfile.TemporaryDirectory() as tmp:
        conn = bw.init(Path(tmp) / "jobs.sqlite")
        for t in texts:
            bw.enqueue(conn, t)
        for k in bw.metrics:
            bw.metrics[k] = 0
        latencies = []
        while True:
            t0 = time.perf_counter()
            n = bw.process_once(conn, batch_size)
            if not n:
                break
            latencies.append((time.perf_counter() - t0) * 1000)
        conn.close()

    calls = bw.metrics["model_calls"]
    prompt = (calls * SYSTEM_PROMPT_TOKENS
              + len(texts) * (ITEM_TOKENS
                              + (ITEM_WRAPPER_TOKENS if batch_size > 1 else 0)))
    completion = len(texts) * SUMMARY_TOKENS
    total = usd(prompt, completion)

    return {
        "lever": "batch",
        "scenario": (f"after (batch of {batch_size})" if batch_size > 1
                     else "before (one call per job)"),
        "requests": len(texts),
        "model_calls": calls,
        "hit_rate": "",
        "usd_per_1k": round(1000 * total / len(texts), 4),
        "p95_ms": round(p95(latencies), 2),  # per model call, not per job
        "backend": f"sqlite/{'llm' if bw.USE_LLM else 'stub'}",
        "jobs_failed": bw.metrics["jobs_failed"],
    }


# ---------------------------------------------------------------------------
# Quality checks
# ---------------------------------------------------------------------------
def quality_checks(calls, cached_outputs):
    print("\n[QUALITY]")

    # 1. A cache HIT must return exactly what the model said on the MISS.
    first = {}
    same = total = 0
    for msg, out in zip(calls, cached_outputs):
        core = (out["urgency"], out["advice"])
        if out["_cache"] == "MISS":
            first[msg] = core
        else:
            total += 1
            same += core == first[msg]
    print(f"  hit answers identical to original miss: {same}/{total}")

    # 2. Bumping the prompt version must invalidate the cache.
    ct.reset_cache()
    unique = list(dict.fromkeys(calls))
    for m in unique:
        ct.triage(m)
    old = ct.PROMPT_VERSION
    ct.PROMPT_VERSION = old + "-bumped"
    ct.reset_metrics()
    for m in unique:
        ct.triage(m)
    print(f"  hits after prompt-version bump: {ct.metrics['hits']} "
          f"(expected 0)")
    ct.PROMPT_VERSION = old

    # 3. Accuracy vs hand labels: only meaningful with a real model.
    if not ct.USE_LLM:
        print("  urgency accuracy: SKIPPED (stub backend answers 'routine' "
              "for everything; run with USE_LLM=1)")
        return
    labelled = json.load(open("fixtures/triage_labelled.json"))
    ct.reset_cache()
    correct = em_total = em_caught = 0
    for row in labelled:
        got = ct.triage.__wrapped__(row["message"])["urgency"]
        correct += got == row["urgency"]
        if row["urgency"] == "emergency":
            em_total += 1
            em_caught += got == "emergency"
    print(f"  urgency accuracy vs labels: {correct}/{len(labelled)}")
    print(f"  emergency recall: {em_caught}/{em_total}")


def main():
    calls = build_calls()

    before_cache, _ = run_triage(calls, use_cache=False)
    after_cache, cached_outputs = run_triage(calls, use_cache=True)
    before_batch = run_batch(calls, batch_size=1)
    after_batch = run_batch(calls, batch_size=bw.BATCH_SIZE)
    rows = [before_cache, after_cache, before_batch, after_batch]

    cols = ["lever", "scenario", "requests", "model_calls", "hit_rate",
            "usd_per_1k", "p95_ms", "backend"]
    print(f"{'lever':<6} {'scenario':<26} {'calls':>5} {'hit':>5} "
          f"{'$/1k':>8} {'p95 ms':>8}  backend")
    for r in rows:
        print(f"{r['lever']:<6} {r['scenario']:<26} {r['model_calls']:>5} "
              f"{str(r['hit_rate']):>5} {r['usd_per_1k']:>8.4f} "
              f"{r['p95_ms']:>8.2f}  {r['backend']}")

    for name, b, a in [("cache", before_cache, after_cache),
                       ("batch", before_batch, after_batch)]:
        saving = 1 - a["usd_per_1k"] / b["usd_per_1k"]
        print(f"{name} saving on $/1k: {saving:.0%}")
    if after_batch["jobs_failed"]:
        print(f"WARNING: {after_batch['jobs_failed']} batched jobs failed "
              "the output-count guard")

    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {OUT}")

    quality_checks(calls, cached_outputs)

    if not ct.USE_LLM:
        print("\nNOTE: stub backend. Call counts, hit rate and $/1k are valid; "
              "p95 reflects local code only, not model latency.")


if __name__ == "__main__":
    main()

# NOTES
# [c]  Cache lookup cost (Redis memory/CPU) is treated as zero; it is
#      negligible next to a model call but not literally free.
# [b1] ASSUMPTION: the 450-token baseline prompt splits into ~350 system
#      prompt + ~100 message. Replace with a tokenizer count of your prompt.
# [b2] ASSUMPTION: ~5 tokens of numbering/separators per item when batched.
# [b3] ASSUMPTION: ~40 completion tokens per one-line summary, same whether
#      batched or not.
