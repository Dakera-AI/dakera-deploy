#!/usr/bin/env python3
"""Measured payload benchmark for Phase 5 bee-vs-ant context assembly."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import validate_dakera_ccp_handoff as validator


THIS_DIR = Path(__file__).resolve().parent
FIXTURE = THIS_DIR / "ccp_handoff_scenarios.json"


def ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def winner(baseline_tokens: int, candidate_tokens: int) -> str:
    if candidate_tokens < baseline_tokens:
        return "ant"
    if baseline_tokens < candidate_tokens:
        return "bee"
    return "tie"


def compact_projection(memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    projection = []
    for memory in memories:
        reliability = memory.get("metadata", {}).get("reliability", {})
        projection.append(
            {
                "fixture_id": memory["id"],
                "content": memory["content"],
                "reliability_action": validator.classify_ccp(memory)["action"],
                "t": reliability.get("t"),
                "i": reliability.get("i"),
                "f": reliability.get("f"),
            }
        )
    return projection


def metric(label: str, payload: Any) -> dict[str, Any]:
    return validator.payload_metrics(label, payload)


def token_case(case_id: str, meaning: str, bee_payload: Any, ant_payload: Any) -> dict[str, Any]:
    bee = metric(f"{case_id}_bee", bee_payload)
    ant = metric(f"{case_id}_ant", ant_payload)
    delta = bee["tokens"] - ant["tokens"]
    return {
        "id": case_id,
        "meaning": meaning,
        "bee_tokens": bee["tokens"],
        "ant_tokens": ant["tokens"],
        "token_delta": delta,
        "token_savings_ratio": ratio(delta, bee["tokens"]),
        "bee_bytes": bee["bytes"],
        "ant_bytes": ant["bytes"],
        "byte_delta": bee["bytes"] - ant["bytes"],
        "winner": winner(bee["tokens"], ant["tokens"]),
        "bee_payload_label": bee["label"],
        "ant_payload_label": ant["label"],
    }


def build_benchmark(fixture: dict[str, Any]) -> dict[str, Any]:
    full_transcript = "\n".join(fixture["full_transcript"])
    ccp_memories = [
        memory
        for memory in fixture["memories"]
        if memory["id"] in {"ccp-key-decision", "ccp-evidence", "ccp-caveat"}
    ]
    key_decision = [memory for memory in ccp_memories if memory["id"] == "ccp-key-decision"]
    ccp_content_payload = "\n".join(memory["content"] for memory in ccp_memories)
    key_content_payload = key_decision[0]["content"]
    full_json_payload = json.dumps(ccp_memories, sort_keys=True, separators=(",", ":"))
    top_k_overfetch_payload = json.dumps(fixture["memories"], sort_keys=True, separators=(",", ":"))
    projection_payload = json.dumps(compact_projection(ccp_memories), sort_keys=True, separators=(",", ":"))
    lazy_projection_payload = json.dumps(compact_projection(key_decision), sort_keys=True, separators=(",", ":"))

    cases = [
        token_case(
            "compact_content_payload",
            "Agent B receives only the compact CCP content needed for handoff.",
            full_transcript,
            ccp_content_payload,
        ),
        token_case(
            "decision_only_payload",
            "Agent B receives only the selected decision packet content; caveat/evidence are lazy-loaded later.",
            full_transcript,
            key_content_payload,
        ),
        token_case(
            "compact_projection_payload",
            "Agent B receives content plus minimal fixture/reliability/action projection, not full memory JSON.",
            full_transcript,
            projection_payload,
        ),
        token_case(
            "lazy_projection_payload",
            "Agent B receives one projected decision packet and expands evidence only when needed.",
            full_transcript,
            lazy_projection_payload,
        ),
        token_case(
            "full_json_packet_payload",
            "Agent B receives full CCP memory JSON including metadata.",
            full_transcript,
            full_json_payload,
        ),
        token_case(
            "top_k_overfetch_payload",
            "Recall overfetch returns all fixture memories instead of only needed CCP packets.",
            full_transcript,
            top_k_overfetch_payload,
        ),
    ]

    full_tokens = validator.token_count(full_transcript)
    full_json_tokens = validator.token_count(full_json_payload)
    break_even_case = {
        "id": "json_break_even",
        "meaning": "Full JSON CCP becomes cheaper only when the transcript exceeds this threshold.",
        "bee_tokens": full_json_tokens + 1,
        "ant_tokens": full_json_tokens,
        "token_delta": 1,
        "token_savings_ratio": ratio(1, full_json_tokens + 1),
        "bee_bytes": len(("x " * (full_json_tokens + 1)).encode("utf-8")),
        "ant_bytes": len(full_json_payload.encode("utf-8")),
        "byte_delta": None,
        "winner": "ant",
        "bee_payload_label": "synthetic_transcript_break_even",
        "ant_payload_label": "full_json_packet_payload",
    }
    cases.append(break_even_case)

    wins = {
        "bee": sum(1 for case in cases if case["winner"] == "bee"),
        "ant": sum(1 for case in cases if case["winner"] == "ant"),
        "tie": sum(1 for case in cases if case["winner"] == "tie"),
    }
    best_case = min(cases[:-1], key=lambda item: item["ant_tokens"])
    compact_case = next(item for item in cases if item["id"] == "compact_content_payload")
    remaining_after_compact = compact_case["ant_tokens"]
    half_cost_target = full_tokens * 0.5
    required_next_cut = max(0, remaining_after_compact - half_cost_target)
    required_next_cut_ratio = ratio(required_next_cut, remaining_after_compact)

    return {
        "benchmark": "phase5_bee_vs_ant_swarm_assembly_measured_payloads",
        "methodology": "measured payload/token benchmark; no subjective bee_score or ant_score constants",
        "tokenizer": validator.token_metadata(),
        "bee_definition": "central queen/master relay sends or curates the full transcript/state",
        "ant_definition": "distributed trace assembly stores compact CCP packets in Dakera and recalls only relevant traces",
        "hybrid_definition": "bee/queen controls routing policy and escalation; ant assembly leaves and follows compact Dakera traces",
        "full_transcript_tokens": full_tokens,
        "full_transcript_bytes": len(full_transcript.encode("utf-8")),
        "winner_counts": wins,
        "viability": "hybrid_bee_control_ant_trace_assembly",
        "cases": cases,
        "best_measured_ant_case": best_case["id"],
        "half_cost_feasibility": {
            "baseline_tokens": full_tokens,
            "half_cost_target_tokens": half_cost_target,
            "compact_content_tokens": compact_case["ant_tokens"],
            "compact_content_savings_ratio": compact_case["token_savings_ratio"],
            "additional_tokens_to_cut_from_compact": required_next_cut,
            "additional_remaining_cut_ratio_needed": required_next_cut_ratio,
            "best_case_tokens": best_case["ant_tokens"],
            "best_case_reaches_half_cost": best_case["ant_tokens"] <= half_cost_target,
        },
    }


def print_markdown(result: dict[str, Any]) -> None:
    print("# Bee vs Ant Swarm Assembly Benchmark")
    print()
    print(f"Methodology: {result['methodology']}")
    print(f"Tokenizer: `{result['tokenizer']['method']}`")
    print(f"Viability: `{result['viability']}`")
    print()
    print("| Case | Bee Tokens | Ant Tokens | Delta | Savings Ratio | Winner |")
    print("|---|---:|---:|---:|---:|---|")
    for case in result["cases"]:
        print(
            f"| `{case['id']}` | {case['bee_tokens']} | {case['ant_tokens']} | "
            f"{case['token_delta']} | {case['token_savings_ratio']} | `{case['winner']}` |"
        )
    print()
    feasibility = result["half_cost_feasibility"]
    print("## Half-Cost Feasibility")
    print()
    print(
        f"Baseline `{feasibility['baseline_tokens']}` tokens; half-cost target "
        f"`{feasibility['half_cost_target_tokens']}` tokens."
    )
    print(
        f"Compact content payload is `{feasibility['compact_content_tokens']}` tokens; "
        f"additional cut needed from that payload is "
        f"`{feasibility['additional_tokens_to_cut_from_compact']}` tokens "
        f"({feasibility['additional_remaining_cut_ratio_needed']})."
    )
    print(
        f"Best measured ant case `{result['best_measured_ant_case']}` reaches half-cost: "
        f"`{feasibility['best_case_reaches_half_cost']}`."
    )


def main() -> int:
    fixture = validator.load_fixture(FIXTURE)
    result = build_benchmark(fixture)
    print_markdown(result)
    print()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
