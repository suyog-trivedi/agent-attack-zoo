"""
Benchmark the 3-tier classifier.

  - Run Tier 1 + Tier 2 over all 10,000 generated calls (cheap, no LLM).
  - For Tier 3 (the ~5% that escape), do REAL LLM calls capped at TIER3_REAL_N
    so we have honest latency numbers without burning the API budget.
  - Aggregate per-tier latency, end-to-end (weighted) latency,
    coverage per tier, and cost.

Reads OPENAI_API_KEY from env; if missing, Tier 3 latency is reported as
"skipped" (stub) and end-to-end stats are computed only for Tiers 1+2.
"""

from __future__ import annotations

import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

# Allow `python bench.py` from this folder OR from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from classifier_engine import CascadeEngine, ToolCall, tier1_classify, tier2_classify, tier3_classify_real
import workload

N = 10_000
TIER3_REAL_N = 100        # cap real LLM calls (~$0.005 worth)
OUT_PATH = Path(__file__).resolve().parent / "out" / "bench-results.json"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)


def pct(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    xs2 = sorted(xs)
    k = (len(xs2) - 1) * p
    f = math.floor(k); c = math.ceil(k)
    if f == c:
        return xs2[int(k)]
    return xs2[f] + (xs2[c] - xs2[f]) * (k - f)


def measure_tier1_only(calls: list[ToolCall]) -> tuple[list[float], list[ToolCall]]:
    lats, misses = [], []
    for c in calls:
        t = time.perf_counter_ns()
        r = tier1_classify(c)
        elapsed = (time.perf_counter_ns() - t) / 1_000.0
        if r is not None:
            lats.append(elapsed)
        else:
            misses.append(c)
    return lats, misses


def measure_tier2_only(calls: list[ToolCall]) -> tuple[list[float], list[ToolCall]]:
    lats, misses = [], []
    for c in calls:
        t = time.perf_counter_ns()
        r = tier2_classify(c)
        elapsed = (time.perf_counter_ns() - t) / 1_000.0
        if r is not None:
            lats.append(elapsed)
        else:
            misses.append(c)
    return lats, misses


def measure_tier3_real(calls: list[ToolCall], cap: int) -> list[float]:
    """Real LLM calls. Latency in MILLISECONDS, returned in microseconds for uniformity."""
    sampled = calls[:cap]
    lats_us = []
    for c in sampled:
        t = time.perf_counter()
        try:
            _ = tier3_classify_real(c)
        except Exception as e:
            print(f"  Tier 3 LLM call failed: {e}", file=sys.stderr)
            continue
        lats_us.append((time.perf_counter() - t) * 1_000_000.0)
    return lats_us


def summarize(lats_us: list[float]) -> dict:
    if not lats_us:
        return {"n": 0}
    return {
        "n": len(lats_us),
        "min_us": round(min(lats_us), 2),
        "p50_us": round(pct(lats_us, 0.50), 2),
        "p95_us": round(pct(lats_us, 0.95), 2),
        "p99_us": round(pct(lats_us, 0.99), 2),
        "max_us": round(max(lats_us), 2),
        "mean_us": round(statistics.mean(lats_us), 2),
    }


def main() -> int:
    print(f"Generating workload of {N:,} tool calls...")
    calls = workload.generate(N)

    # --- Tier 1 ---
    print("Measuring Tier 1 (keyword/regex) over all calls...")
    t1_lats, after_t1 = measure_tier1_only(calls)
    print(f"  Tier 1 hits: {len(t1_lats):,} / {N:,} ({100*len(t1_lats)/N:.1f}%)")

    # --- Tier 2 over the misses ---
    print("Measuring Tier 2 (registry) over Tier-1 misses...")
    t2_lats, after_t2 = measure_tier2_only(after_t1)
    print(f"  Tier 2 hits: {len(t2_lats):,} / {N:,} ({100*len(t2_lats)/N:.1f}%)")
    print(f"  Escape to Tier 3: {len(after_t2):,} / {N:,} ({100*len(after_t2)/N:.1f}%)")

    # --- Tier 3 real LLM (capped) ---
    t3_summary = {"n": 0, "skipped": True, "reason": "OPENAI_API_KEY not set"}
    if os.getenv("OPENAI_API_KEY"):
        n_real = min(TIER3_REAL_N, len(after_t2))
        print(f"Measuring Tier 3 (LLM, gpt-4o-mini) on {n_real} real calls...")
        t3_lats = measure_tier3_real(after_t2, n_real)
        t3_summary = summarize(t3_lats)
        t3_summary["skipped"] = False
    else:
        print("OPENAI_API_KEY not set — skipping real Tier 3 LLM calls.")

    # --- End-to-end weighted (uses Tier 3 only if measured) ---
    weighted_e2e = None
    if not t3_summary.get("skipped"):
        # Synthesize an end-to-end distribution by mixing per-tier
        # latencies with their actual coverage weights.
        all_e2e = (
            t1_lats
            + t2_lats
            # Tier 3 sample's median latency stamped on each remaining call
            + [t3_summary["p50_us"]] * len(after_t2)
        )
        weighted_e2e = summarize(all_e2e)

    results = {
        "config": {"N": N, "tier3_real_cap": TIER3_REAL_N},
        "coverage": {
            "tier1_hit": len(t1_lats),
            "tier2_hit": len(t2_lats),
            "tier3_escape": len(after_t2),
            "tier1_pct": round(100*len(t1_lats)/N, 2),
            "tier2_pct": round(100*len(t2_lats)/N, 2),
            "tier3_pct": round(100*len(after_t2)/N, 2),
        },
        "tier1_latency_us": summarize(t1_lats),
        "tier2_latency_us": summarize(t2_lats),
        "tier3_latency_us": t3_summary,
        "end_to_end_weighted_us": weighted_e2e,
    }

    with open(OUT_PATH, "w") as f:
        json.dump(results, f, indent=2)

    print("\n=== RESULTS ===")
    print(json.dumps(results, indent=2))
    print(f"\nWrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
