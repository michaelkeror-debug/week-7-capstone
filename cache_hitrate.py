"""Course check: cache hit rate on the fixed load script.

Load: 40 unique fixture messages + 60 repeats drawn with seed 7 = 100 calls.
Because every repeat is a message already seen, the expected hit rate is
exactly 60/100 = 0.60. That figure reflects this synthetic repeat rate, not
real AfyaPlus traffic.
"""
import json
import random
import sys

import cache_triage as ct

random.seed(7)
msgs = json.load(open("fixtures/triage_messages.json"))[:40]
assert len(msgs) == 40
calls = list(msgs) + [random.choice(msgs) for _ in range(60)]
random.shuffle(calls)

ct.reset_cache()  # start cold, even if Redis kept keys from a previous run

hits = misses = 0
for m in calls:
    out = ct.triage(m if isinstance(m, str) else m["message"])
    if out.get("_cache") == "HIT":
        hits += 1
    else:
        misses += 1

rate = hits / len(calls)
print(f"backend={ct.BACKEND} hits={hits} misses={misses} hit_rate={rate:.2f}")
if rate < 0.55:
    sys.exit(1)
