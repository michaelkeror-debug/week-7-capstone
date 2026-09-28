# AfyaPlus Cost-Optimised Deployment & Executive Brief

A cost model, deployment, cost-saving levers, build-vs-buy analysis and executive brief for **AfyaPlus triage**, an AI assistant that classifies patient messages as emergency, urgent or routine and gives safe advice. It never diagnoses.

**Recommendation: Go, as a pilot on the hosted gpt-4o-mini API, with conditions.** See the [executive brief](exec/Afyaplus%20Cost%20Memo.pdf).

---


## 1. Cost model

`cost_model.py` prices each request from prompt and completion tokens separately, adds a 15% infra overhead, and a fixed monthly people/ops line (clinician review plus on-call). It reports $/1k at baseline and at a 10x spike, where the spike assumes 5% retries and infra overhead rising to 25%.

`sensitivity.py` sweeps prompt and completion sizes across a 3x3 grid (`token_sweep.csv`). Doubling the reply adds more cost than doubling the prompt, because completion tokens cost four times as much.

## 2. Deployment and budgets

- **`docker-compose.cost.yml`** runs the triage API with CPU and memory limits, a health check and FinOps labels: `afyaplus.service`, `afyaplus.version`, `afyaplus.cost-center`.
- **Label-to-tag mapping:** the Docker label `afyaplus.service` corresponds to the Azure tag `service` and the AWS cost-allocation tag `user:service`, all set to `triage-api`.
- **`azure_budget_triage.json`** and **`aws_budget.json`** set a $400/month budget on that tag, alerting at 80% of actual spend and when spend is forecast to pass 100%.
- **No paid cloud was used.** Budgets are submitted as configuration; local run evidence is in `deploy/capstone week 7 evidence`.

## 3. Cost levers

| Lever | File | How it saves |
|---|---|---|
| Response cache | `cache_triage.py` | Identical messages within 10 minutes reuse the stored answer. Key includes model and prompt version. Redis, or in-memory fallback. |
| Batch queue | `batch_worker.py` | Non-urgent summary jobs go to the model 8 per call, paying the system prompt once per batch. Triage is never batched. |

Load script: 40 fixture messages plus 60 repeats, seed 7, 100 requests. Results in `results/levers_before_after.csv`.

**Quality note** (`QUALITY_NOTE.md`): exact-match caching never serves an answer written for a different message; all 60 cache hits matched the original answer, and a prompt-version change clears the cache. Remaining risks are stated honestly: the 60% hit rate is synthetic, and urgency accuracy with the real model is untested until run with `USE_LLM=1`.

## 4. Break-even memo

`breakeven.py` compares the API against vLLM on one cloud GPU (about $1,300/month fixed: GPU, storage, on-call). It generates `breakeven_memo.md` with a sensitivity table covering API price changes, reserved GPUs, a second GPU and caching. **Self-hosting was not run; all self-host figures are labelled estimates.**

## 5. Executive brief

One page in business language: cost per 1,000 requests, the spike plan, both levers, the key risk (a missed emergency) and its mitigation, and go/no-go conditions covering budgets, response-time targets (p95 defined), fallbacks and stop triggers.

---

## Assumptions and limits

- Model prices are gpt-4o-mini list prices; recheck before any external quote.
- Hosting overhead, staff time, spike retries and all self-hosting costs are **estimates**, footnoted in each script.
- The cache hit rate comes from a synthetic load, not live traffic.
- Urgency labels in `fixtures/triage_labelled.json` are hand-assigned by the author and **not clinician-validated**.
- Cost and hit-rate results use a stub model; latency and answer quality need a run with `USE_LLM=1`.
