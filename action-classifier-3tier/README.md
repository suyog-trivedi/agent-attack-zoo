# action-classifier-3tier

A 3-tier action classifier for AI agent tool calls — keyword → registry → LLM. Runnable benchmark over 10,000 synthetic tool calls. Real `gpt-4o-mini` latency measured on a 100-call sample for the LLM tier so the numbers are not assumed.

## Why this exists

If you're putting any kind of policy in front of agent tool calls, you need a classifier — *is this call READ, WRITE, SEND, or EXECUTE?* The default reach for most teams is "let an LLM decide every time." That works until the latency tail and bill hit you.

This is the cheapest classifier that still covers the long tail:

- **Tier 1 — keyword/regex on tool name.** Microseconds. Catches the obvious cases (`requests.post` is SEND, `shell.exec` is EXECUTE).
- **Tier 2 — registry lookup.** Sub-microsecond dict lookup against a small set of known tools (LangChain community, MCP servers, your own).
- **Tier 3 — LLM classifier.** Only fires for what the first two abstain on. gpt-4o-mini with a 4-token output cap.

## Benchmark numbers (10,000 calls, captured 2026-05-29)

| Tier | Coverage | p50 | p95 | p99 |
|---|---|---|---|---|
| 1 — keyword / regex | 78.25% | **1.9 µs** | 4.8 µs | 6.6 µs |
| 2 — registry | 14.69% | **0.7 µs** | 0.9 µs | 1.1 µs |
| 3 — gpt-4o-mini (100 real calls) | 7.06% | **~1.07 s** | ~1.93 s | ~15.9 s |
| End-to-end (weighted) | 100% | **~1.8 µs** | ~1.07 s | ~1.07 s |

Full JSON in [`out/bench-results.json`](out/bench-results.json).

The thing worth pausing on — gpt-4o-mini p50 is about *one full second* and p99 was ~16 seconds when called serially. The cascade keeps end-to-end p50 in microseconds, but the 7% escape rate puts a one-second tail at p95. Both numbers are real.

## Run it

```powershell
cd action-classifier-3tier
pip install -r requirements.txt
$env:OPENAI_API_KEY = "sk-..."   # only needed for the Tier 3 real numbers
python bench.py
```

Tier 1 and Tier 2 run in well under a second total. Tier 3 makes 100 real LLM calls and costs a fraction of a cent.

If you skip the API key, the benchmark still runs and reports Tier 1 + Tier 2; Tier 3 is marked `skipped` in the output JSON.

## Files

| File | What |
|---|---|
| [`classifier_engine.py`](classifier_engine.py) | The 3-tier reference engine. ~150 lines, no heavyweight deps. |
| [`workload.py`](workload.py) | Synthetic 10K-call generator with a realistic mix (80% Tier 1 / 15% Tier 2 / 5% Tier 3 escape). |
| [`bench.py`](bench.py) | Runs the cascade, reports per-tier and end-to-end percentiles, writes `out/bench-results.json`. |
| [`out/bench-results.json`](out/bench-results.json) | The actual numbers from the run shown above. |

## Caveats and where this would change

- **Synthetic workload.** Real production tool-call distributions vary a lot — single-agent / framework-heavy stacks look something like 78/15/7, but multi-agent and MCP-heavy stacks have a fatter Tier 3 tail.
- **No caching.** Production should cache Tier 3 results so the same novel tool name becomes a Tier 2 entry on second sight. This benchmark deliberately doesn't cache to show worst-case Tier 3 cost.
- **Tier 3 model choice.** gpt-4o-mini is the cheap reasonable default. A small fine-tuned classifier would beat it on latency by orders of magnitude — that's what you should actually run in production once your tool-call distribution stabilises.

## License

MIT. Same as the rest of the zoo.
