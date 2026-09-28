"""AfyaPlus token sensitivity sweep.

Computes USD per 1,000 requests (API + infra, no ops) for every combination
of prompt and completion token counts in the grids below, prints the grid,
and writes the results to token_sweep.csv.
"""

import csv

from afyaplus_cost_model import (
    PRICE_PROMPT_PER_M,
    PRICE_COMPLETION_PER_M,
    INFRA_OVERHEAD,
)

PROMPT_GRID = [300, 450, 900]        # short, baseline, doubled prompt
COMPLETION_GRID = [80, 180, 360]     # short, baseline, doubled completion
BASELINE = (450, 180)                # from usage logs, see cost model [2]
CSV_PATH = "token_sweep.csv"


def usd_per_request(prompt_tokens: int, completion_tokens: int) -> float:
    api = (prompt_tokens * PRICE_PROMPT_PER_M
           + completion_tokens * PRICE_COMPLETION_PER_M) / 1_000_000
    return api * (1.0 + INFRA_OVERHEAD)


def cost_per_1k(prompt_tokens: int, completion_tokens: int) -> float:
    return 1000.0 * usd_per_request(prompt_tokens, completion_tokens)


if __name__ == "__main__":
    base = cost_per_1k(*BASELINE)
    rows = []

    # Print the grid: one row per prompt size, one column per completion size
    print(f'{"prompt":>8}  ' + "  ".join(f"c={c:<5}" for c in COMPLETION_GRID))
    for p in PROMPT_GRID:
        cells = []
        for c in COMPLETION_GRID:
            per_1k = cost_per_1k(p, c)
            cells.append(f"{per_1k:7.4f}")
            rows.append({
                "prompt_tokens": p,
                "completion_tokens": c,
                "usd_per_request": round(usd_per_request(p, c), 8),
                "usd_per_1k": round(per_1k, 4),
                "delta_vs_baseline_usd_per_1k": round(per_1k - base, 4),
                "is_baseline": (p, c) == BASELINE,
            })
        print(f"{p:>8}  " + "  ".join(cells))

    # Write the same results to CSV (one row per grid cell)
    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print("\nbaseline $/1k", round(base, 4))
    print("double prompt 450->900 @180:", round(cost_per_1k(900, 180) - base, 4))
    print("double completion 180->360 @450:", round(cost_per_1k(450, 360) - base, 4))
    print(f"\nwrote {len(rows)} rows to {CSV_PATH}")
    print(f"assumptions: infra_overhead={INFRA_OVERHEAD}, "
          f"price_prompt_per_m={PRICE_PROMPT_PER_M}, "
          f"price_completion_per_m={PRICE_COMPLETION_PER_M}, ops excluded")
