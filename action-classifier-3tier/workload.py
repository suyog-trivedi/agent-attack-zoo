"""
Workload generator for the 3-tier classifier benchmark.

Builds a list of ToolCall objects with a realistic mix:

  ~80%  → Tier 1 hits (common verbs / prefixes seen across LangChain, etc.)
  ~15%  → Tier 2 hits (named tools from a small registry)
  ~5%   → Tier 3 only (novel / vendor-specific names neither tier knows)

These ratios mirror what we see in real production tool-call distributions for
single-agent workflows; multi-agent and MCP-heavy stacks shift the mix.
"""

from __future__ import annotations

import random
from classifier_engine import ToolCall

_T1_NAMES = [
    "requests.post", "httpx.post", "requests.put", "smtp.send",
    "webhook.post", "s3.upload", "external_sink", "publish_event",
    "shell.exec", "bash.run", "os.system", "subprocess.run",
    "python_repl", "code_interpreter",
    "write_file", "file_write", "edit_file", "patch_file",
    "git_commit", "git_push",
    "insert_user", "update_invoice", "delete_record", "drop_table",
    "read_file", "get_user", "list_objects", "query_db",
    "search_index", "fetch_url", "describe_table",
    "requests.get", "httpx.get", "s3.list", "s3.get",
    "select_top_n", "count_orders",
]

_T2_NAMES = list({
    "csv_agent.query", "csv_agent.python_repl_ast",
    "tavily_search_results_json", "duckduckgo_search",
    "wikipedia.run", "wolfram_alpha.run",
    "google_drive.upload", "notion.create_page",
    "linear.create_issue", "jira.create_issue",
    "github.create_pull_request", "github.merge_pull_request",
    "stripe.create_charge", "twilio.send_sms",
    "mcp.filesystem.read", "mcp.filesystem.write", "mcp.git.commit",
})

# Tier-3-only — names that look plausible but neither tier matches.
# These are the realistic "long tail" — custom internal tools, niche MCP servers,
# vendor-specific names with non-obvious verbs.
_T3_NAMES = [
    "acme_internal.dispatch_v2",
    "redstone_metrics.snapshot",
    "vendor_x.sync_ledger",
    "kafka_topic.flush",
    "vector_db.upsert_partition",
    "ml_pipeline.trigger_run",
    "internal_tool.frobnicate",
    "neo4j.cypher_run",
    "snowflake.task_invoke",
    "airflow_dag.trigger",
    "modal_function.invoke",
    "ray_task.submit",
]


def generate(n: int = 10_000, seed: int = 42) -> list[ToolCall]:
    rng = random.Random(seed)
    calls: list[ToolCall] = []
    for _ in range(n):
        r = rng.random()
        if r < 0.80:
            name = rng.choice(_T1_NAMES)
        elif r < 0.95:
            name = rng.choice(_T2_NAMES)
        else:
            name = rng.choice(_T3_NAMES)
        calls.append(ToolCall(tool_name=name, args={"k": rng.randint(1, 9)}))
    return calls
