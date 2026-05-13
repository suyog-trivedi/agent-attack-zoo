# agent-attack-zoo

A small, growing collection of real, runnable agent-misuse attacks — and the smallest defenses I could write that actually stop them.

Each subdirectory is one attack. Each one ships:

- A runnable attack script (`attack.py`) that reproduces the failure end-to-end.
- A policy file (`policy.yaml`) in a generic, vendor-neutral syntax.
- A defended pattern (`defended-pattern.py`) — a tiny reference policy engine plus a thin wrapper around the agent that stops the attack.
- Sample traces (`sample-traces/`) — sanitized JSON of what the attack looks like before and after the defense.

The point isn't to ship a guardrail product. It's to make these failure modes concrete, so anyone building agents can grep their own stack for the same shape and decide what to do.

## Index

| # | Attack | Where |
|---|---|---|
| 01 | CSV agent → multi-turn PII exfiltration to an external sink | [`exfil-csv-agent/`](exfil-csv-agent) |

More to come — roughly one a week.

## Run any of them

```powershell
cd <attack-folder>
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
