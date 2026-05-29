# agent-attack-zoo

A small, growing collection of real, runnable artifacts on AI agent runtime security — attacks with the smallest defenses I could write that stop them, plus engine deep-dives with measured numbers.

Each subdirectory is one piece. Attack folders ship a runnable `attack.py`, a vendor-neutral `policy.yaml`, a `defended-pattern.py`, and sample before/after traces. Engine folders ship the reference code plus a runnable benchmark and the JSON it produced.

The point isn't to ship a guardrail product. It's to make these patterns concrete, so anyone building agents can grep their own stack for the same shape and decide what to do.

## Index

| # | Topic | Where |
|---|---|---|
| 01 | CSV agent → multi-turn PII exfiltration to an external sink | [`exfil-csv-agent/`](exfil-csv-agent) |
| 02 | 3-tier action classifier (keyword → registry → LLM) + latency benchmark | [`action-classifier-3tier/`](action-classifier-3tier) |

More to come — roughly one a week. Topics rotate between runnable attacks, engine deep-dives, and OSS-agent audits.

## Run any of them

Pick one from the Index above and follow its own README. As an example, the current one:

```powershell
cd exfil-csv-agent
# install deps as listed in that folder's README
$env:OPENAI_API_KEY = "sk-..."
python attack.py
python defended-pattern.py
```

## Repo conventions

- Attacks use cheap models (`gpt-4o-mini` etc.) so a full repro costs cents, not dollars.
- All "customer data" is synthetic. Names, emails, phones, IDs — all fabricated.
- Policies are written against a small, generic schema (`action_type`, `tool_name`, `risk_signals.*`). The same policy file should be portable to any policy engine that supports field/operator/value matching.
- Defended patterns include a 50–100 line reference engine inline so you don't have to install anything extra to see the mechanics.

## Why this exists

I write about agent runtime security every week. This repo is where the runnable artifacts for those posts live.

## License

MIT. Use, fork, lift the policies into your own stack, no attribution needed.

## Contact

If you reproduced an attack and want to share what your stack did (or didn't) catch, open an issue. I read all of them.

---

*Opinions and code here are my own, not my employer's.*
