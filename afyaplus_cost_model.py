"""AfyaPlus triage: USD per 1,000 requests estimator.

Covers three cost lines:
  1. Model tokens (prompt vs completion, priced separately)
  2. Infra (compute, logs, egress) as an overhead on API spend
  3. People/ops (clinician review, on-call/support) as a fixed monthly cost

Reports cost per 1,000 requests and monthly totals at a baseline volume and
at a 10x spike, with every spike-specific assumption stated explicitly.

Every numeric input carries a footnote [n]; see FOOTNOTES at the bottom.
Values marked ASSUMPTION are placeholders: replace them with real figures
(and update the footnote) before using this in a board pack or partner quote.
"""

# ---------------------------------------------------------------------------
# 1. Model pricing: gpt-4o-mini, USD per 1M tokens
# ---------------------------------------------------------------------------
MODEL = "gpt-4o-mini"
PRICE_PROMPT_PER_M = 0.15        # [1]
PRICE_COMPLETION_PER_M = 0.60    # [1]

# ---------------------------------------------------------------------------
# 2. Request shape (from usage logs)
# ---------------------------------------------------------------------------
PROMPT_TOKENS = 450              # [2] system prompt + patient message
COMPLETION_TOKENS = 180          # [2] advice + disclaimer (never diagnose)

# ---------------------------------------------------------------------------
# 3. Infra overhead on API spend
# ---------------------------------------------------------------------------
INFRA_OVERHEAD = 0.15            # [3] +15% for compute, logs, egress

# ---------------------------------------------------------------------------
# 4. People / ops (fixed monthly, does not scale with volume)
# ---------------------------------------------------------------------------
CLINICIAN_REVIEW_HOURS = 4       # [4] ASSUMPTION: monthly sample audit of responses
CLINICIAN_RATE_USD = 50.0        # [4] ASSUMPTION: hourly rate
ONCALL_SUPPORT_HOURS = 4         # [5] ASSUMPTION: monthly incident/support time
ONCALL_RATE_USD = 50.0           # [5] ASSUMPTION: hourly rate

OPS_MONTHLY_USD = (CLINICIAN_REVIEW_HOURS * CLINICIAN_RATE_USD
                   + ONCALL_SUPPORT_HOURS * ONCALL_RATE_USD)

# ---------------------------------------------------------------------------
# 5. Volume and spike assumptions
# ---------------------------------------------------------------------------
BASELINE_MONTHLY_REQUESTS = 100_000   # [6]
SPIKE_MULTIPLIER = 10                 # [7]
SPIKE_RETRY_RATE = 0.05               # [8] ASSUMPTION: extra calls from timeouts/retries
SPIKE_INFRA_OVERHEAD = 0.25           # [9] ASSUMPTION: burst-capacity premium

REQUESTS_PER_UNIT = 1_000


# ---------------------------------------------------------------------------
# Cost functions
# ---------------------------------------------------------------------------
def api_usd(prompt_tokens: int = PROMPT_TOKENS,
            completion_tokens: int = COMPLETION_TOKENS) -> float:
    """Raw model API cost for one request."""
    return (prompt_tokens * PRICE_PROMPT_PER_M
            + completion_tokens * PRICE_COMPLETION_PER_M) / 1_000_000


def variable_usd_per_request(overhead: float = INFRA_OVERHEAD,
                             retry_rate: float = 0.0) -> float:
    """API + infra cost per successful request, including retries."""
    return api_usd() * (1.0 + overhead) * (1.0 + retry_rate)


def scenario(monthly_requests: int,
             overhead: float = INFRA_OVERHEAD,
             retry_rate: float = 0.0) -> dict:
    """Full cost breakdown for one month at a given volume."""
    api_month = monthly_requests * api_usd() * (1.0 + retry_rate)
    infra_month = api_month * overhead
    ops_month = OPS_MONTHLY_USD
    total_month = api_month + infra_month + ops_month
    per_1k = REQUESTS_PER_UNIT * total_month / monthly_requests
    return {
        "monthly_requests": monthly_requests,
        "api_usd": api_month,
        "infra_usd": infra_month,
        "ops_usd": ops_month,
        "total_usd": total_month,
        "usd_per_1k": per_1k,
        "usd_per_1k_variable_only":
            REQUESTS_PER_UNIT * variable_usd_per_request(overhead, retry_rate),
    }


def print_scenario(label: str, s: dict) -> None:
    print(f"\n[{label}]")
    print(f"  monthly_requests          {s['monthly_requests']:>12,}")
    print(f"  api_usd                   {s['api_usd']:>12.2f}")
    print(f"  infra_usd                 {s['infra_usd']:>12.2f}")
    print(f"  ops_usd                   {s['ops_usd']:>12.2f}")
    print(f"  total_usd                 {s['total_usd']:>12.2f}")
    print(f"  usd_per_1k (fully loaded) {s['usd_per_1k']:>12.4f}")
    print(f"  usd_per_1k (API + infra)  {s['usd_per_1k_variable_only']:>12.4f}")


if __name__ == "__main__":
    baseline = scenario(BASELINE_MONTHLY_REQUESTS)
    spike = scenario(BASELINE_MONTHLY_REQUESTS * SPIKE_MULTIPLIER,
                     overhead=SPIKE_INFRA_OVERHEAD,
                     retry_rate=SPIKE_RETRY_RATE)

    print(f"model={MODEL}")
    print(f"prompt_tokens={PROMPT_TOKENS} completion_tokens={COMPLETION_TOKENS}")
    print(f"price_prompt_per_m={PRICE_PROMPT_PER_M} "
          f"price_completion_per_m={PRICE_COMPLETION_PER_M}")
    print(f"api_usd_per_request={api_usd():.6f}")
    print(f"ops_monthly_usd={OPS_MONTHLY_USD:.2f}")

    print_scenario("BASELINE", baseline)
    print_scenario(f"SPIKE {SPIKE_MULTIPLIER}x "
                   f"(retry +{SPIKE_RETRY_RATE:.0%}, "
                   f"infra +{SPIKE_INFRA_OVERHEAD:.0%})", spike)


# ---------------------------------------------------------------------------
# FOOTNOTES
# ---------------------------------------------------------------------------
# [1] OpenAI API pricing page for gpt-4o-mini, <URL>, checked <YYYY-MM-DD>.
#     List prices change; re-verify before any external use.
# [2] AfyaPlus usage logs, <date range>, N = <sample size>, <mean or p50>.
# [3] Basis for 15%: <e.g. last month's hosting + logging bill / API spend>.
# [4] Clinician review: ASSUMPTION of 4 hrs/month at $50/hr to audit a sample
#     of triage responses for safety (no diagnosis, correct escalation).
#     Replace with actual contracted hours and rate.
# [5] On-call / support: ASSUMPTION of 4 hrs/month at $50/hr for incidents,
#     prompt fixes, and user support. Replace with actual figures.
# [6] Baseline volume: <source, e.g. pilot clinic traffic or partner forecast>.
# [7] 10x spike: stated stress-test assumption (e.g. outbreak or campaign
#     launch), not a forecast.
# [8] Retry rate under load: ASSUMPTION of 5% extra API calls from timeouts
#     and rate-limit retries. Replace with load-test data if available.
# [9] Burst infra premium: ASSUMPTION that overhead rises from 15% to 25%
#     under spike load (autoscaling headroom, higher log volume).
# Ops cost is held flat at 10x. If a spike needs extra clinician review or
# support hours, raise OPS_MONTHLY_USD for the spike scenario.
