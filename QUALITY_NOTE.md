# Quality note: cost levers for AfyaPlus triage

Both levers cut cost. This note records where each one can make answers worse, what guards are in place, and what is not yet tested.

## Results (from `levers_bench.py`, stub backend)

| Lever | Before | After | Saving on $/1k |
|---|---|---|---|
| Response cache | 100 model calls, $0.2018/1k | 40 calls, 60% hit rate, $0.0807/1k | 60% |
| Batch queue (size 8) | 100 calls, $0.1052/1k | 13 calls, $0.0536/1k | 49% |

Load script: 40 unique fixture messages plus 60 repeats drawn with seed 7, 100 requests in total. $/1k covers API plus infra (ops excluded), priced from `afyaplus_cost_model.py`.

These figures were measured with a stub instead of a real model. Call counts, hit rate and $/1k are valid. p95 latency reflects local code only, and answer quality is not measured until the benchmark is rerun with `USE_LLM=1`.

## Lever 1: exact-match response cache

**Why it is lower risk than a semantic cache.** A cached answer is only returned for the same message text (after lowercasing and whitespace normalisation). It never serves an answer written for a *different* message, which is the main failure of semantic caches. The benchmark confirms that all 60 cache hits returned exactly the answer the model gave on the original request.

**Where it can still degrade answers:**

- **Stale answers after a prompt or model change.** Mitigated: the cache key includes the model name and `PROMPT_VERSION`. The benchmark confirms a version bump gives 0 hits. Whoever edits the prompt must bump the version.
- **Same words, different patient.** "Fever for two days" from a child and from an adult gets the same cached advice if age or history is not in the message. The cache cannot see context that is not in the key. If the triage call later includes patient context, that context must be added to the key.
- **A wrong answer is repeated.** If the model mis-triages a message, every repeat within the 10-minute TTL gets the same wrong answer. The short TTL limits this, and the prompt-version bump clears it after a fix.
- **Privacy.** Keys are hashed, but cached advice is stored in Redis. It must run inside the same trust boundary as the API, never on a shared or public instance.

**Hit rate is an assumption, not a forecast.** The 60% comes from the synthetic 60% repeat rate in the load script. Real patient messages are free text and rarely repeat word for word, so the real exact-match hit rate is likely much lower. Measure it from production logs before claiming the saving.

## Lever 2: batch queue

**Scope.** Only non-urgent summarisation jobs are batched. Patient triage is never batched, because queueing would delay emergency advice.

**Where it can degrade answers:**

- **Dropped or misaligned items.** One call returning eight summaries can skip or merge an item, shifting every summary after it onto the wrong job. Mitigated: if the number of summaries doesn't match the number of jobs, the whole batch is marked `failed` rather than saved.
- **Cross-item bleed.** Themes from one item can leak into another's summary. This is not tested yet; spot-check batched against unbatched summaries on the same inputs.
- **Latency.** Jobs wait until a batch is processed. This is acceptable for summaries, not for triage.

**Token assumptions.** The batch saving rests on stated assumptions in `levers_bench.py` (notes b1–b3): a 350-token system prompt within the 450-token baseline, 5 tokens of per-item overhead, and 40 tokens per summary. Replace them with tokenizer counts from the real prompt.

## Urgency labels

`fixtures/triage_labelled.json` now has 40 hand-assigned labels (7 emergency, 7 urgent, 26 routine). They replace the earlier position-based labels, which marked "Mild headache after missing lunch" as an emergency. They are the author's labels, not clinician-validated, and should be reviewed by a clinician before any accuracy figure is used outside the capstone.

## Not yet tested

- Urgency accuracy and emergency recall with a real model (`USE_LLM=1 python levers_bench.py` reports both).
- Real p95 latency with and without the cache.
- Real-traffic hit rate.
