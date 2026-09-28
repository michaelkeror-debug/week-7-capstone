# Memo: API-hosted vs self-hosted OSS for AfyaPlus triage

**Recommendation: stay on the gpt-4o-mini API.** Self-hosting only breaks even at about **8.6M requests a month**, roughly **85.6x** our 100,000 baseline and well above our 10x spike case. Self-hosting was not run; every self-host figure here is an estimate.

## Workload

Patient triage messages: 450 prompt tokens and 180 completion tokens per request on average, baseline 100,000 requests a month (see `afyaplus_cost_model.py`). Replies classify urgency and give safe advice; the service must never diagnose and must catch emergencies.

## The two options

**API-hosted (measured shape, list prices).** gpt-4o-mini costs $0.000202 per request fully loaded (API plus 15% infra). No fixed cost: we pay only for what we use, and bursts are the vendor's problem.

**Self-hosted OSS (estimate, not run).** vLLM serving an open-weights model on one A10-class cloud GPU. Estimated fixed cost $1,300 a month: GPU $850, storage and observability $50, and $400 of extra on-call and ML engineering time for patching, capacity and model updates. Estimated variable cost $0.00005 per request for energy and egress. The GPU is paid for whether or not anyone sends a message.

## Monthly cost at different volumes

| Monthly requests | API | Self-host (estimate) | Cheaper |
|---|---|---|---|
| 100,000 | $20.18 | $1,305.00 | API |
| 1,000,000 | $201.82 | $1,350.00 | API |
| 5,000,000 | $1,009.12 | $1,550.00 | API |
| 10,000,000 | $2,018.25 | $1,800.00 | Self-host |
| 20,000,000 | $4,036.50 | $2,300.00 | Self-host |

At baseline, self-hosting costs about 65 times more than the API, almost entirely because of the fixed GPU and on-call cost.

## Break-even

Break-even volume = fixed self-host cost / (API cost per request - self-host variable cost per request)
= $1,300 / ($0.000202 - $0.00005) = **8,562,490 requests a month**, where both paths cost about $1,728.

This assumes one GPU can carry that load. At break-even the average rate is about 3.3 requests per second, and around 10 per second at an assumed 3x peak. Whether one A10-class GPU sustains that with acceptable p95 latency was **not measured**; it depends on model size, quantization and context length, and needs a vLLM load test. If it needs two GPUs, break-even roughly doubles (below).

## What would change the decision

| Scenario | Break-even (requests/month) | vs baseline | What it tests |
|---|---|---|---|
| Base case | 8.6M | 85.6x | estimates as stated |
| API price -50% | 25.5M | 255.3x | vendor cuts price |
| API price +50% | 5.1M | 51.4x | vendor raises price |
| GPU -40% (reserved/spot) | 6.3M | 63.2x | commitment discount [7] |
| 2 GPUs (capacity or HA) | 14.2M | 141.6x | one GPU is not enough or no failover |
| On-call x2 | 11.2M | 112.0x | GPU ops harder than planned |
| Cache 60% hit, both paths | 21.4M | 214.1x | levers_bench hit rate [8] |

No realistic scenario brings break-even near our current volume. The things that would move us towards self-hosting:

- **Sustained volume above ~8.6M/month**, from measured traffic, not forecasts.
- **An API price rise**, or a vendor outage or policy change that the API contract can't absorb.
- **A cheap committed GPU** (reserved or spot) with ops time already paid for by another workload.
- **Data residency or privacy requirements** that the API can't meet. This is a non-cost reason that could override the numbers; it needs a legal answer, not a cost model.

Things that push the other way: caching (a 60% hit rate on both paths raises break-even to about 21.4M, because it cuts API spend but not the GPU bill), needing a second GPU for capacity or failover, and GPU ops taking more people time than estimated.

## Quality is not a given

Cost only matters if the open model triages as safely as gpt-4o-mini. Before any migration, run both on `fixtures/triage_labelled.json` and compare urgency accuracy and, above all, **emergency recall**. A cheaper model that misses a chest-pain emergency is not cheaper. Quantization to fit a smaller GPU can lower quality further and would need the same check.

## Estimates and sources

[1] API prices and token counts: `afyaplus_cost_model.py` footnotes. List prices change; re-verify.
[2] GPU $850/month: ESTIMATE for one A10-class on-demand instance. Replace with a quote from your cloud, with date.
[3] Storage and observability $50/month: ESTIMATE.
[4] On-call $400/month: ESTIMATE of extra people time for GPU ops, on top of the ops line both paths already share.
[5] Variable $0.00005/request: ESTIMATE proxy for energy and egress.
[6] Peak-to-average 3x: ASSUMPTION; measure from logs.
[7] 40% GPU discount: ASSUMPTION for reserved or spot pricing; spot adds interruption risk.
[8] 60% hit rate: from the synthetic load in `levers_bench.py`, not real traffic.
