"""API-hosted vs self-hosted OSS break-even for AfyaPlus triage.

API side  : gpt-4o-mini, fully loaded per request (API + infra overhead),
            from afyaplus_cost_model.py.
Self-host : vLLM + open-weights model on one cloud GPU. Fixed monthly cost
            (GPU instance + storage/observability + on-call time) plus a small
            variable cost per request (energy/egress proxy).

Self-hosting was NOT run. Every self-host number below is an ESTIMATE and is
labelled as such. Writes breakeven_memo.md and results/breakeven.csv.
"""
import csv
from pathlib import Path

from afyaplus_cost_model import (COMPLETION_TOKENS, INFRA_OVERHEAD,
                                 PRICE_COMPLETION_PER_M, PRICE_PROMPT_PER_M,
                                 PROMPT_TOKENS, BASELINE_MONTHLY_REQUESTS)

# ---------------------------------------------------------------------------
# API side (measured shape, list prices) [1]
# ---------------------------------------------------------------------------
def api_usd_per_request(price_scale: float = 1.0) -> float:
    api = (PROMPT_TOKENS * PRICE_PROMPT_PER_M
           + COMPLETION_TOKENS * PRICE_COMPLETION_PER_M) / 1_000_000
    return api * price_scale * (1.0 + INFRA_OVERHEAD)


API_PER_REQ = api_usd_per_request()

# ---------------------------------------------------------------------------
# Self-host side: ALL ESTIMATES, replace with real cloud quotes [2]-[5]
# ---------------------------------------------------------------------------
GPU_INSTANCE_MONTHLY = 850.0     # [2] ESTIMATE: 1x A10-class, on-demand
STORAGE_OBS_MONTHLY = 50.0       # [3] ESTIMATE: weights, disk, logs, metrics
PEOPLE_ONCALL_MONTHLY = 400.0    # [4] ESTIMATE: extra SRE/ML time for GPU ops
SELFHOST_VAR_PER_REQ = 0.00005   # [5] ESTIMATE: energy/egress proxy
SELFHOST_FIXED = GPU_INSTANCE_MONTHLY + STORAGE_OBS_MONTHLY + PEOPLE_ONCALL_MONTHLY

SECONDS_PER_MONTH = 30 * 24 * 3600
PEAK_TO_AVERAGE = 3.0            # [6] ASSUMPTION: traffic peak vs average


def break_even_requests(api_cost: float, fixed: float, var: float,
                        miss_rate: float = 1.0) -> float:
    """Monthly incoming requests where both paths cost the same.

    miss_rate < 1 models a response cache in front of either path: only
    misses reach the model, so both variable costs shrink by the same factor.
    """
    margin = (api_cost - var) * miss_rate
    return fixed / margin if margin > 0 else float("inf")


def monthly(volume: int, fixed: float = 0.0, per_req: float = 0.0) -> float:
    return fixed + volume * per_req


SCENARIOS = [
    # name, api price scale, fixed monthly, var/req, miss rate, what it tests
    ("Base case", 1.0, SELFHOST_FIXED, SELFHOST_VAR_PER_REQ, 1.0,
     "estimates as stated"),
    ("API price -50%", 0.5, SELFHOST_FIXED, SELFHOST_VAR_PER_REQ, 1.0,
     "vendor cuts price"),
    ("API price +50%", 1.5, SELFHOST_FIXED, SELFHOST_VAR_PER_REQ, 1.0,
     "vendor raises price"),
    ("GPU -40% (reserved/spot)", 1.0,
     SELFHOST_FIXED - 0.4 * GPU_INSTANCE_MONTHLY, SELFHOST_VAR_PER_REQ, 1.0,
     "commitment discount [7]"),
    ("2 GPUs (capacity or HA)", 1.0,
     SELFHOST_FIXED + GPU_INSTANCE_MONTHLY, SELFHOST_VAR_PER_REQ, 1.0,
     "one GPU is not enough or no failover"),
    ("On-call x2", 1.0, SELFHOST_FIXED + PEOPLE_ONCALL_MONTHLY,
     SELFHOST_VAR_PER_REQ, 1.0, "GPU ops harder than planned"),
    ("Cache 60% hit, both paths", 1.0, SELFHOST_FIXED, SELFHOST_VAR_PER_REQ,
     0.4, "levers_bench hit rate [8]"),
]


def run():
    rows = []
    for name, scale, fixed, var, miss, why in SCENARIOS:
        api = api_usd_per_request(scale)
        n = break_even_requests(api, fixed, var, miss)
        rows.append({
            "scenario": name,
            "api_usd_per_req": round(api, 8),
            "selfhost_fixed_monthly": round(fixed, 2),
            "selfhost_var_per_req": var,
            "miss_rate": miss,
            "break_even_monthly_requests": round(n) if n != float("inf") else "never",
            "x_baseline_volume": round(n / BASELINE_MONTHLY_REQUESTS, 1)
            if n != float("inf") else "never",
            "monthly_usd_at_break_even": round(fixed + n * var * miss, 2)
            if n != float("inf") else "",
            "tests": why,
        })
    return rows


def fmt_m(n) -> str:
    return f"{n / 1e6:.1f}M" if isinstance(n, (int, float)) else str(n)


def write_memo(rows, path="breakeven_memo.md"):
    base = rows[0]
    n_star = base["break_even_monthly_requests"]
    avg_rps = n_star / SECONDS_PER_MONTH
    peak_rps = avg_rps * PEAK_TO_AVERAGE

    vols = [BASELINE_MONTHLY_REQUESTS, 10 * BASELINE_MONTHLY_REQUESTS,
            5_000_000, 10_000_000, 20_000_000]
    cost_table = "\n".join(
        f"| {v:,} | ${monthly(v, 0, API_PER_REQ):,.2f} | "
        f"${monthly(v, SELFHOST_FIXED, SELFHOST_VAR_PER_REQ):,.2f} | "
        f"{'API' if monthly(v, 0, API_PER_REQ) < monthly(v, SELFHOST_FIXED, SELFHOST_VAR_PER_REQ) else 'Self-host'} |"
        for v in vols)

    sens_table = "\n".join(
        f"| {r['scenario']} | {fmt_m(r['break_even_monthly_requests'])} | "
        f"{r['x_baseline_volume']}x | {r['tests']} |"
        for r in rows)

    memo = f"""# Memo: API-hosted vs self-hosted OSS for AfyaPlus triage

**Recommendation: stay on the gpt-4o-mini API.** Self-hosting only breaks even at about **{fmt_m(n_star)} requests a month**, roughly **{base['x_baseline_volume']}x** our {BASELINE_MONTHLY_REQUESTS:,} baseline and well above our 10x spike case. Self-hosting was not run; every self-host figure here is an estimate.

## Workload

Patient triage messages: {PROMPT_TOKENS} prompt tokens and {COMPLETION_TOKENS} completion tokens per request on average, baseline {BASELINE_MONTHLY_REQUESTS:,} requests a month (see `afyaplus_cost_model.py`). Replies classify urgency and give safe advice; the service must never diagnose and must catch emergencies.

## The two options

**API-hosted (measured shape, list prices).** gpt-4o-mini costs ${API_PER_REQ:.6f} per request fully loaded (API plus {INFRA_OVERHEAD:.0%} infra). No fixed cost: we pay only for what we use, and bursts are the vendor's problem.

**Self-hosted OSS (estimate, not run).** vLLM serving an open-weights model on one A10-class cloud GPU. Estimated fixed cost ${SELFHOST_FIXED:,.0f} a month: GPU ${GPU_INSTANCE_MONTHLY:,.0f}, storage and observability ${STORAGE_OBS_MONTHLY:,.0f}, and ${PEOPLE_ONCALL_MONTHLY:,.0f} of extra on-call and ML engineering time for patching, capacity and model updates. Estimated variable cost ${SELFHOST_VAR_PER_REQ:.5f} per request for energy and egress. The GPU is paid for whether or not anyone sends a message.

## Monthly cost at different volumes

| Monthly requests | API | Self-host (estimate) | Cheaper |
|---|---|---|---|
{cost_table}

At baseline, self-hosting costs about {monthly(BASELINE_MONTHLY_REQUESTS, SELFHOST_FIXED, SELFHOST_VAR_PER_REQ) / monthly(BASELINE_MONTHLY_REQUESTS, 0, API_PER_REQ):.0f} times more than the API, almost entirely because of the fixed GPU and on-call cost.

## Break-even

Break-even volume = fixed self-host cost / (API cost per request - self-host variable cost per request)
= ${SELFHOST_FIXED:,.0f} / (${API_PER_REQ:.6f} - ${SELFHOST_VAR_PER_REQ:.5f}) = **{n_star:,} requests a month**, where both paths cost about ${base['monthly_usd_at_break_even']:,.0f}.

This assumes one GPU can carry that load. At break-even the average rate is about {avg_rps:.1f} requests per second, and around {peak_rps:.0f} per second at an assumed {PEAK_TO_AVERAGE:.0f}x peak. Whether one A10-class GPU sustains that with acceptable p95 latency was **not measured**; it depends on model size, quantization and context length, and needs a vLLM load test. If it needs two GPUs, break-even roughly doubles (below).

## What would change the decision

| Scenario | Break-even (requests/month) | vs baseline | What it tests |
|---|---|---|---|
{sens_table}

No realistic scenario brings break-even near our current volume. The things that would move us towards self-hosting:

- **Sustained volume above ~{fmt_m(n_star)}/month**, from measured traffic, not forecasts.
- **An API price rise**, or a vendor outage or policy change that the API contract can't absorb.
- **A cheap committed GPU** (reserved or spot) with ops time already paid for by another workload.
- **Data residency or privacy requirements** that the API can't meet. This is a non-cost reason that could override the numbers; it needs a legal answer, not a cost model.

Things that push the other way: caching (a 60% hit rate on both paths raises break-even to about {fmt_m(rows[-1]['break_even_monthly_requests'])}, because it cuts API spend but not the GPU bill), needing a second GPU for capacity or failover, and GPU ops taking more people time than estimated.

## Quality is not a given

Cost only matters if the open model triages as safely as gpt-4o-mini. Before any migration, run both on `fixtures/triage_labelled.json` and compare urgency accuracy and, above all, **emergency recall**. A cheaper model that misses a chest-pain emergency is not cheaper. Quantization to fit a smaller GPU can lower quality further and would need the same check.

## Estimates and sources

[1] API prices and token counts: `afyaplus_cost_model.py` footnotes. List prices change; re-verify.
[2] GPU ${GPU_INSTANCE_MONTHLY:,.0f}/month: ESTIMATE for one A10-class on-demand instance. Replace with a quote from your cloud, with date.
[3] Storage and observability ${STORAGE_OBS_MONTHLY:,.0f}/month: ESTIMATE.
[4] On-call ${PEOPLE_ONCALL_MONTHLY:,.0f}/month: ESTIMATE of extra people time for GPU ops, on top of the ops line both paths already share.
[5] Variable ${SELFHOST_VAR_PER_REQ:.5f}/request: ESTIMATE proxy for energy and egress.
[6] Peak-to-average {PEAK_TO_AVERAGE:.0f}x: ASSUMPTION; measure from logs.
[7] 40% GPU discount: ASSUMPTION for reserved or spot pricing; spot adds interruption risk.
[8] 60% hit rate: from the synthetic load in `levers_bench.py`, not real traffic.
"""
    Path(path).write_text(memo)
    return memo


if __name__ == "__main__":
    rows = run()
    Path("results").mkdir(exist_ok=True)
    with open("results/breakeven.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"api_usd_per_req={API_PER_REQ:.6f}")
    print(f"selfhost_fixed_monthly={SELFHOST_FIXED:.2f} (ESTIMATE)")
    print(f"selfhost_var_per_req={SELFHOST_VAR_PER_REQ:.6f} (ESTIMATE)")
    print(f"\n{'scenario':<28} {'break-even/month':>17} {'x baseline':>11}")
    for r in rows:
        print(f"{r['scenario']:<28} {fmt_m(r['break_even_monthly_requests']):>17} "
              f"{str(r['x_baseline_volume']) + 'x':>11}")

    write_memo(rows)
    print("\nwrote breakeven_memo.md and results/breakeven.csv")
