"""
Microbenchmark — measure the decision latency of the minimal reference engine
in 03-defended-pattern.py over many calls. Used to produce the p50/p99 numbers
quoted in the LinkedIn post.

The check is keyword + regex only — no LLM — so latencies are dominated by
the Python interpreter and dict/regex ops. Run produces stable sub-millisecond
numbers on a typical laptop.
"""
import importlib.util
import json
import os
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
os.environ.setdefault("OPENAI_API_KEY", "stub")

spec = importlib.util.spec_from_file_location("pattern", HERE / "03-defended-pattern.py")
pattern = importlib.util.module_from_spec(spec)
sys.modules["pattern"] = pattern  # required so dataclass can resolve __module__
spec.loader.exec_module(pattern)

engine = pattern.engine

# Realistic payload — accumulated agent output containing PII (matches what
# the orchestrator would forward in the real attack flow).
payload = """Here are the gold-segment customers:
| Aarav Sharma | aarav.sharma@example.com | +91-98200-11111 | 4421 | 3344 |
| Vikram Patel | vikram.patel@example.com | +91-98200-55555 | 5567 | 9912 |
| Divya Rao    | divya.rao@example.com    | +91-98200-99999 | 1234 | 5678 |
"""

N = 1000

# Warm up
for _ in range(50):
    engine.session_has_seen_pii = False
    engine.check("external_sink", {"payload": payload})

# Measure
samples_ns: list[int] = []
denies = 0
for _ in range(N):
    engine.session_has_seen_pii = False
    t0 = time.perf_counter_ns()
    d = engine.check("external_sink", {"payload": payload})
    samples_ns.append(time.perf_counter_ns() - t0)
    if d.is_denied:
        denies += 1

samples_us = [s / 1000 for s in samples_ns]
samples_us.sort()


def pct(p: float) -> float:
    idx = int(len(samples_us) * p / 100)
    return samples_us[min(idx, len(samples_us) - 1)]


result = {
    "calls": N,
    "denies": denies,
    "deny_rate": denies / N,
    "latency_us": {
        "min": round(min(samples_us), 2),
        "p50": round(statistics.median(samples_us), 2),
        "p95": round(pct(95), 2),
        "p99": round(pct(99), 2),
        "max": round(max(samples_us), 2),
        "mean": round(statistics.mean(samples_us), 2),
    },
    "policy_name": "block-csv-exfil-to-external",
    "engine": "minimal reference engine (pure-Python, no LLM)",
    "host": "windows / python 3.11",
}

out = HERE / "out" / "engine-benchmark.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
