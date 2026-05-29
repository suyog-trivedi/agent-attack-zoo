"""
3-tier action classifier — reference engine.

Vendor-neutral. ~150 lines. Pure Python, no heavyweight deps.

Tier 1 — keyword/regex on (tool_name, args). Microseconds. Catches the
         long tail of obvious cases (file writes, http calls, shell exec, etc.).
Tier 2 — registry lookup. Fingerprint of known tools → pre-classified label.
         Tens of microseconds.
Tier 3 — LLM fallback. Only fires if Tier 1 AND Tier 2 abstain.
         Hundreds of milliseconds. The classifier you wish you could avoid.

ActionType vocabulary:
  READ     — observes data, no side effect
  WRITE    — mutates local/internal state
  SEND     — egresses data (network, email, webhook)
  EXECUTE  — runs code or shell commands
  UNKNOWN  — only when ALL tiers abstain (should be rare)
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class ActionType(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    SEND = "SEND"
    EXECUTE = "EXECUTE"
    UNKNOWN = "UNKNOWN"


@dataclass
class ToolCall:
    tool_name: str
    args: dict = field(default_factory=dict)


@dataclass
class Classification:
    action_type: ActionType
    tier: int                     # 1, 2, or 3
    confidence: float             # 0.0 .. 1.0
    matched_rule: Optional[str] = None
    latency_us: float = 0.0       # filled in by the engine


# -----------------------------------------------------------------------------
# Tier 1 — keyword/regex. The cheapest possible signal.
# -----------------------------------------------------------------------------
# Ordered: more specific patterns first.

_TIER1_PATTERNS: list[tuple[re.Pattern, ActionType, str]] = [
    # SEND — network egress, email, webhook
    (re.compile(r"^(requests?\.|httpx\.|urllib\.|aiohttp\.|fetch).*post|put|patch|delete", re.I), ActionType.SEND, "http-mutating-verb"),
    (re.compile(r"^(smtp|email|sendmail|mailgun|sendgrid|ses)\.", re.I), ActionType.SEND, "email-egress"),
    (re.compile(r"^(webhook|slack|discord|teams|pagerduty)\.", re.I), ActionType.SEND, "webhook-egress"),
    (re.compile(r"^(s3\.upload|gcs\.upload|blob\.upload|ftp\.)", re.I), ActionType.SEND, "object-store-upload"),
    (re.compile(r"^external_sink|^publish_", re.I), ActionType.SEND, "explicit-sink"),

    # EXECUTE — code / shell
    (re.compile(r"^(shell|bash|sh|cmd|powershell|os\.system|subprocess\.)", re.I), ActionType.EXECUTE, "shell-exec"),
    (re.compile(r"^(exec|eval|python_repl|code_interpreter|run_python)", re.I), ActionType.EXECUTE, "code-eval"),

    # WRITE — local mutation
    (re.compile(r"^(write_file|file_write|open_w|fs\.write|edit_file|patch_file)", re.I), ActionType.WRITE, "fs-write"),
    (re.compile(r"^(insert_|update_|delete_|drop_|truncate_).*", re.I), ActionType.WRITE, "db-mutating"),
    (re.compile(r"^git_(commit|push|merge|rebase|reset)", re.I), ActionType.WRITE, "git-mutating"),

    # READ — pretty much anything starts-with read/get/list/query without an HTTP-mutating verb
    (re.compile(r"^(read_|get_|list_|query_|search_|fetch_|describe_|head_)", re.I), ActionType.READ, "read-verb"),
    (re.compile(r"^(requests?\.|httpx\.|urllib\.|aiohttp\.|fetch).*get", re.I), ActionType.READ, "http-get"),
    (re.compile(r"^(s3\.list|gcs\.list|blob\.list|s3\.get|gcs\.get|blob\.get)", re.I), ActionType.READ, "object-store-read"),
    (re.compile(r"^select_|^count_|^aggregate_", re.I), ActionType.READ, "db-read"),
]


def tier1_classify(call: ToolCall) -> Optional[Classification]:
    name = call.tool_name
    for pat, action, rule in _TIER1_PATTERNS:
        if pat.match(name):
            return Classification(action_type=action, tier=1, confidence=0.95, matched_rule=rule)
    return None


# -----------------------------------------------------------------------------
# Tier 2 — registry lookup. Pre-classified fingerprints of known tools.
# In production this is loaded from YAML / DB; here we hard-code a small sample.
# -----------------------------------------------------------------------------

_TIER2_REGISTRY: dict[str, tuple[ActionType, str]] = {
    # Common LangChain / community tool names
    "csv_agent.query":               (ActionType.READ,    "registered-langchain-csv"),
    "csv_agent.python_repl_ast":     (ActionType.EXECUTE, "registered-langchain-csv-repl"),
    "tavily_search_results_json":    (ActionType.READ,    "registered-tavily"),
    "duckduckgo_search":             (ActionType.READ,    "registered-ddg"),
    "wikipedia.run":                 (ActionType.READ,    "registered-wikipedia"),
    "wolfram_alpha.run":             (ActionType.READ,    "registered-wolfram"),
    "google_drive.upload":           (ActionType.SEND,    "registered-gdrive-upload"),
    "notion.create_page":            (ActionType.WRITE,   "registered-notion-write"),
    "linear.create_issue":           (ActionType.WRITE,   "registered-linear-write"),
    "jira.create_issue":             (ActionType.WRITE,   "registered-jira-write"),
    "github.create_pull_request":    (ActionType.WRITE,   "registered-github-pr"),
    "github.merge_pull_request":     (ActionType.WRITE,   "registered-github-merge"),
    "stripe.create_charge":          (ActionType.SEND,    "registered-stripe-charge"),
    "twilio.send_sms":               (ActionType.SEND,    "registered-twilio-sms"),
    # MCP-style fingerprints
    "mcp.filesystem.read":           (ActionType.READ,    "registered-mcp-fs-read"),
    "mcp.filesystem.write":          (ActionType.WRITE,   "registered-mcp-fs-write"),
    "mcp.git.commit":                (ActionType.WRITE,   "registered-mcp-git-commit"),
}


def tier2_classify(call: ToolCall) -> Optional[Classification]:
    hit = _TIER2_REGISTRY.get(call.tool_name)
    if hit:
        action, rule = hit
        return Classification(action_type=action, tier=2, confidence=0.99, matched_rule=rule)
    return None


# -----------------------------------------------------------------------------
# Tier 3 — LLM classifier. Real call if OPENAI_API_KEY is set; otherwise stub.
# -----------------------------------------------------------------------------

_TIER3_SYS = (
    "Classify the agent tool call into one of: READ, WRITE, SEND, EXECUTE.\n"
    "READ = observes data, no side effect.\n"
    "WRITE = mutates local/internal state (file, db, repo).\n"
    "SEND = egresses data outside the system (network, email, webhook).\n"
    "EXECUTE = runs code or shell commands.\n"
    "Respond with ONE word only."
)


def tier3_classify_real(call: ToolCall) -> Classification:
    """Real Tier 3 — uses OpenAI gpt-4o-mini. Caller must ensure key is set."""
    from openai import OpenAI  # lazy import
    client = OpenAI()
    user_msg = f"tool_name: {call.tool_name}\nargs_keys: {list(call.args.keys())}"
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": _TIER3_SYS},
                  {"role": "user",   "content": user_msg}],
        temperature=0,
        max_tokens=4,
    )
    raw = (resp.choices[0].message.content or "").strip().upper()
    try:
        action = ActionType(raw)
    except ValueError:
        action = ActionType.UNKNOWN
    return Classification(action_type=action, tier=3, confidence=0.80, matched_rule="llm-classifier")


def tier3_classify_stub(call: ToolCall) -> Classification:
    """Stub used when no API key — classification by best-guess, latency NOT realistic."""
    return Classification(action_type=ActionType.UNKNOWN, tier=3, confidence=0.0, matched_rule="stub-no-key")


# -----------------------------------------------------------------------------
# Engine — runs the cascade and measures per-tier latency.
# -----------------------------------------------------------------------------

@dataclass
class CascadeEngine:
    use_real_tier3: bool = False

    def classify(self, call: ToolCall) -> Classification:
        # Tier 1
        t0 = time.perf_counter_ns()
        r = tier1_classify(call)
        if r is not None:
            r.latency_us = (time.perf_counter_ns() - t0) / 1_000.0
            return r

        # Tier 2
        r = tier2_classify(call)
        if r is not None:
            r.latency_us = (time.perf_counter_ns() - t0) / 1_000.0
            return r

        # Tier 3
        if self.use_real_tier3 and os.getenv("OPENAI_API_KEY"):
            r = tier3_classify_real(call)
        else:
            r = tier3_classify_stub(call)
        r.latency_us = (time.perf_counter_ns() - t0) / 1_000.0
        return r
