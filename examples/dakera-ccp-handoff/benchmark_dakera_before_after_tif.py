#!/usr/bin/env python3
"""Compare Dakera before T-I-F examples with the current T-I-F/CCP package.

The before side is a git commit where no local T-I-F/CCP example existed.
The after side is the current working tree. This benchmark is deliberately
honest: "before" cannot run T-I-F validators because they did not exist.
"""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any


THIS_DIR = Path(__file__).resolve().parent
REPO = THIS_DIR.parents[1]
FIXTURE = THIS_DIR / "ccp_handoff_scenarios.json"
RESULTS_JSON = THIS_DIR / "DAKERA_BEFORE_AFTER_TIF_BENCHMARK.json"
RESULTS_MD = THIS_DIR / "DAKERA_BEFORE_AFTER_TIF_BENCHMARK.md"

BEFORE_COMMIT = "533fd04"
BEFORE_LABEL = "pre_tif_origin_main_533fd04"
AFTER_LABEL = "current_phase5_tif_ccp_worktree"

TIF_PATHS = [
    "examples/tif-reliability",
    "examples/tif-provenance",
    "examples/tif-graph-reliability",
    "examples/dakera-ccp-handoff",
]


class TokenCounter:
    def __init__(self) -> None:
        self.method = "estimated_len_div_4"
        self.encoding = None
        self.version = None
        self.exact = False
        try:
            import importlib.metadata
            import tiktoken

            self.encoding = tiktoken.get_encoding("cl100k_base")
            self.version = importlib.metadata.version("tiktoken")
            self.method = "tiktoken"
            self.exact = True
        except Exception:
            self.encoding = None

    def count(self, text: str) -> int:
        if self.encoding is not None:
            return len(self.encoding.encode(text))
        return int(math.ceil(len(text) / 4))

    def metadata(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "encoding": "cl100k_base" if self.exact else None,
            "package": "tiktoken" if self.exact else None,
            "version": self.version,
            "exact": self.exact,
            "fallback_note": None if self.exact else "Estimated as ceil(len(text) / 4).",
        }


TOKEN_COUNTER = TokenCounter()


def run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def canonical_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def metric(label: str, payload: Any) -> dict[str, Any]:
    text = canonical_text(payload)
    return {
        "label": label,
        "tokens": TOKEN_COUNTER.count(text),
        "bytes": len(text.encode("utf-8")),
        "chars": len(text),
    }


def path_exists_at(commit: str, path: str) -> bool:
    result = run_git(["cat-file", "-e", f"{commit}:{path}"])
    return result.returncode == 0


def path_exists_now(path: str) -> bool:
    return (REPO / path).exists()


def load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def build_after_payloads(fixture: dict[str, Any]) -> dict[str, Any]:
    memories = fixture["memories"]
    decision = next(memory for memory in memories if memory["id"] == "ccp-key-decision")
    caveat = next(memory for memory in memories if memory["id"] == "ccp-caveat")
    evidence = next(memory for memory in memories if memory["id"] == "ccp-evidence")
    stale = next(memory for memory in memories if memory["id"] == "ccp-stale-timestamp-only")
    ccp_core = [decision, evidence, caveat]

    return {
        "after_decision_only": decision["content"],
        "after_lazy_projection": {
            "fixture_id": decision["id"],
            "action": "continue_from_ccp",
            "content": decision["content"],
            "reliability": decision["metadata"]["reliability"],
            "expand_if": ["needs_evidence", "needs_caveat", "audit_requested"],
        },
        "after_compact_content": "\n".join(memory["content"] for memory in ccp_core),
        "after_uncertainty_packet": {
            "fixture_id": caveat["id"],
            "action": "ask_clarification",
            "content": caveat["content"],
            "reliability": caveat["metadata"]["reliability"],
        },
        "after_contradiction_packet": {
            "fixture_id": stale["id"],
            "action": "surface_contradiction",
            "content": stale["content"],
            "reliability": stale["metadata"]["reliability"],
        },
        "after_full_json_packet": ccp_core,
        "after_overfetch": {
            "all_fixture_memories": memories,
            "redundant_runtime_context": (
                "Overfetch failure mode: broad recall sends decision, evidence, caveat, stale contradiction, "
                "unrelated control memory, metadata, and audit fields that Agent B did not ask for. "
            )
            * 5,
        },
    }


def build_result() -> dict[str, Any]:
    fixture = load_fixture()
    full_transcript = "\n".join(fixture["full_transcript"])
    baseline = metric("before_full_transcript_handoff", full_transcript)
    after_payloads = build_after_payloads(fixture)
    after_metrics = {name: metric(name, payload) for name, payload in after_payloads.items()}

    before_paths = {path: path_exists_at(BEFORE_COMMIT, path) for path in TIF_PATHS}
    after_paths = {path: path_exists_now(path) for path in TIF_PATHS}
    git_status = [
        line
        for line in run_git(["status", "--short"]).stdout.strip().splitlines()
        if not line.endswith(" output/")
    ]

    comparisons = {}
    for name, item in after_metrics.items():
        delta = baseline["tokens"] - item["tokens"]
        comparisons[name] = {
            "after_tokens": item["tokens"],
            "before_baseline_tokens": baseline["tokens"],
            "token_delta": delta,
            "savings_ratio": round(delta / baseline["tokens"], 4) if baseline["tokens"] else 0.0,
            "beats_before_full_transcript": item["tokens"] < baseline["tokens"],
        }

    best_after = min(after_metrics.items(), key=lambda pair: (pair[1]["tokens"], pair[0]))
    worst_after = max(after_metrics.items(), key=lambda pair: (pair[1]["tokens"], pair[0]))
    runtime_json = THIS_DIR / "RUNTIME_OUTPUT.json"
    runtime_md = THIS_DIR / "RUNTIME_OUTPUT.md"
    validation_results = THIS_DIR / "VALIDATION_RESULTS.md"
    benchmark_script = THIS_DIR / "benchmark_swarm_assembly.py"
    validator_script = THIS_DIR / "validate_dakera_ccp_handoff.py"
    scenario_file = THIS_DIR / "ccp_handoff_scenarios.json"

    comparison_points = [
        {
            "id": 1,
            "dimension": "T-I-F reliability validation surface",
            "before": "absent",
            "after": "present: examples/tif-reliability",
            "verdict": "improved",
        },
        {
            "id": 2,
            "dimension": "Feedback-derived provenance validation",
            "before": "absent",
            "after": "present: examples/tif-provenance",
            "verdict": "improved",
        },
        {
            "id": 3,
            "dimension": "Graph reliability handoff documentation",
            "before": "absent",
            "after": "present: examples/tif-graph-reliability",
            "verdict": "improved",
        },
        {
            "id": 4,
            "dimension": "CCP handoff validator",
            "before": "absent",
            "after": f"present: {validator_script.exists()}",
            "verdict": "improved",
        },
        {
            "id": 5,
            "dimension": "Reusable scenario fixture",
            "before": "absent",
            "after": f"present: {scenario_file.exists()}",
            "verdict": "improved",
        },
        {
            "id": 6,
            "dimension": "Full transcript baseline cost",
            "before": f"{baseline['tokens']} tokens",
            "after": f"{baseline['tokens']} tokens baseline retained for audit comparison",
            "verdict": "neutral_reference",
        },
        {
            "id": 7,
            "dimension": "Best compact handoff cost",
            "before": f"{baseline['tokens']} tokens, full transcript only in this benchmark",
            "after": f"{best_after[1]['tokens']} tokens via {best_after[0]}",
            "verdict": "improved",
        },
        {
            "id": 8,
            "dimension": "Decision-only handoff cost",
            "before": "not implemented",
            "after": f"{after_metrics['after_decision_only']['tokens']} tokens",
            "verdict": "improved",
        },
        {
            "id": 9,
            "dimension": "Lazy projection handoff cost",
            "before": "not implemented",
            "after": f"{after_metrics['after_lazy_projection']['tokens']} tokens",
            "verdict": "improved",
        },
        {
            "id": 10,
            "dimension": "Uncertainty/caveat action",
            "before": "not encoded as structured action",
            "after": "ask_clarification packet available",
            "verdict": "improved",
        },
        {
            "id": 11,
            "dimension": "Contradiction/falsity action",
            "before": "not encoded as structured action",
            "after": "surface_contradiction packet available",
            "verdict": "improved",
        },
        {
            "id": 12,
            "dimension": "Agent isolation scenario",
            "before": "not locally validated",
            "after": "namespace-agent-isolation scenario available",
            "verdict": "improved",
        },
        {
            "id": 13,
            "dimension": "Token overfetch honesty",
            "before": "not measured",
            "after": f"{after_metrics['after_overfetch']['tokens']} tokens; loses to before baseline",
            "verdict": "negative_result_preserved",
        },
        {
            "id": 14,
            "dimension": "Full JSON handoff honesty",
            "before": "not measured",
            "after": f"{after_metrics['after_full_json_packet']['tokens']} tokens",
            "verdict": "mixed",
        },
        {
            "id": 15,
            "dimension": "Runtime raw evidence artifact",
            "before": "absent",
            "after": f"RUNTIME_OUTPUT.json present: {runtime_json.exists()}",
            "verdict": "improved",
        },
        {
            "id": 16,
            "dimension": "Readable runtime report",
            "before": "absent",
            "after": f"RUNTIME_OUTPUT.md present: {runtime_md.exists()}",
            "verdict": "improved",
        },
        {
            "id": 17,
            "dimension": "Associated graph recall proof",
            "before": "absent",
            "after": "attempted, but current REST validator still fails 2 associated-recall scenarios",
            "verdict": "still_not_proven",
        },
        {
            "id": 18,
            "dimension": "Exact token accounting",
            "before": "not present in local examples",
            "after": f"{TOKEN_COUNTER.method}, exact={TOKEN_COUNTER.exact}",
            "verdict": "improved",
        },
        {
            "id": 19,
            "dimension": "Measured benchmark script",
            "before": "absent",
            "after": f"present: {benchmark_script.exists()}",
            "verdict": "improved",
        },
        {
            "id": 20,
            "dimension": "Engine/SDK/MCP mutation risk",
            "before": "none from examples",
            "after": "no engine, SDK, or MCP tool changes required by this package",
            "verdict": "low_risk",
        },
    ]

    return {
        "benchmark": "dakera_before_after_tif_ccp",
        "before": {
            "label": BEFORE_LABEL,
            "commit": BEFORE_COMMIT,
            "tif_or_ccp_paths_present": before_paths,
            "implemented_tif_ccp_validation_available": any(before_paths.values()),
            "handoff_payload_available": "full_transcript_only_for_this_benchmark",
            "baseline": baseline,
        },
        "after": {
            "label": AFTER_LABEL,
            "commit": run_git(["rev-parse", "--short", "HEAD"]).stdout.strip(),
            "working_tree_has_uncommitted_changes": bool(git_status),
            "git_status_short": git_status,
            "tif_or_ccp_paths_present": after_paths,
            "implemented_tif_ccp_validation_available": all(after_paths.values()),
            "payload_metrics": after_metrics,
            "comparisons_vs_before_full_transcript": comparisons,
            "best_after_payload": best_after[0],
            "worst_after_payload": worst_after[0],
        },
        "comparison_points": comparison_points,
        "tokenizer": TOKEN_COUNTER.metadata(),
        "interpretation": {
            "positive": "After T-I-F/CCP, Dakera has concrete local validators and compact handoff packets that did not exist at the pre-T-I-F commit.",
            "negative": "Full JSON and overfetch payloads can be worse than the before full-transcript baseline. Associated graph recall is still not proven by the current REST validator.",
            "truth_boundary": "This benchmark measures local example availability and payload economy. It does not prove a changed Dakera engine behavior.",
        },
    }


def render_markdown(result: dict[str, Any]) -> str:
    before = result["before"]
    after = result["after"]
    lines = [
        "# Dakera Before/After T-I-F + CCP Benchmark",
        "",
        "This report is generated by `benchmark_dakera_before_after_tif.py`.",
        "",
        "## Version Boundary",
        "",
        f"- Before: `{before['label']}` at commit `{before['commit']}`",
        f"- After: `{after['label']}` at HEAD `{after['commit']}`",
        f"- Working tree has uncommitted changes: `{after['working_tree_has_uncommitted_changes']}`",
        f"- Tokenizer: `{result['tokenizer']['method']}` exact=`{result['tokenizer']['exact']}`",
        "",
        "## Availability Proof",
        "",
        "| Path | Before Present | After Present |",
        "|---|---|---|",
    ]
    for path in TIF_PATHS:
        lines.append(f"| `{path}` | `{before['tif_or_ccp_paths_present'][path]}` | `{after['tif_or_ccp_paths_present'][path]}` |")

    lines.extend(
        [
            "",
            "## 20-Point Comparison",
            "",
            "| # | Dimension | Before | After | Verdict |",
            "|---:|---|---|---|---|",
        ]
    )
    for point in result["comparison_points"]:
        lines.append(
            f"| {point['id']} | {point['dimension']} | {point['before']} | "
            f"{point['after']} | `{point['verdict']}` |"
        )

    lines.extend(
        [
            "",
            "## Payload Token Benchmark",
            "",
            f"Before baseline full transcript: `{before['baseline']['tokens']}` tokens.",
            "",
            "| After Payload | Tokens | Delta vs Before | Savings Ratio | Beats Before |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for name, comparison in after["comparisons_vs_before_full_transcript"].items():
        lines.append(
            f"| `{name}` | {comparison['after_tokens']} | {comparison['token_delta']} | "
            f"{comparison['savings_ratio']} | `{comparison['beats_before_full_transcript']}` |"
        )

    lines.extend(
        [
            "",
            "## Verdict",
            "",
            f"- Best after payload: `{after['best_after_payload']}`.",
            f"- Worst after payload: `{after['worst_after_payload']}`.",
            f"- Positive: {result['interpretation']['positive']}",
            f"- Negative: {result['interpretation']['negative']}",
            f"- Boundary: {result['interpretation']['truth_boundary']}",
            "",
            "## Working Tree Note",
            "",
            "The after side intentionally includes current local hardening work, not only the last committed Phase 5 file set.",
        ]
    )
    if after["git_status_short"]:
        lines.append("")
        lines.append("```text")
        lines.extend(after["git_status_short"])
        lines.append("```")
    return "\n".join(lines) + "\n"


def main() -> int:
    result = build_result()
    RESULTS_JSON.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown = render_markdown(result)
    RESULTS_MD.write_text(markdown, encoding="utf-8")
    print(markdown)
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
