#!/usr/bin/env python3
"""Benchmark bee-style vs ant-style context assembly for Phase 5 CCP."""

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


def score_winner(bee_score: float, ant_score: float) -> str:
    if bee_score > ant_score:
        return "bee"
    if ant_score > bee_score:
        return "ant"
    return "tie"


def token_winner(full_tokens: int, candidate_tokens: int) -> str:
    if full_tokens < candidate_tokens:
        return "bee"
    if candidate_tokens < full_tokens:
        return "ant"
    return "tie"


def memory_json_tokens(memories: list[dict[str, Any]]) -> int:
    return validator.token_estimate(json.dumps(memories, sort_keys=True, separators=(",", ":")))


def build_benchmark(fixture: dict[str, Any]) -> dict[str, Any]:
    full_transcript = "\n".join(fixture["full_transcript"])
    ccp_memories = [
        memory
        for memory in fixture["memories"]
        if memory["id"] in {"ccp-key-decision", "ccp-evidence", "ccp-caveat"}
    ]
    ccp_payload = "\n".join(memory["content"] for memory in ccp_memories)
    full_tokens = validator.token_estimate(full_transcript)
    ant_tokens = validator.token_estimate(ccp_payload)
    ant_json_tokens = memory_json_tokens(ccp_memories)
    top_k_overfetch_tokens = memory_json_tokens(fixture["memories"])
    token_savings = full_tokens - ant_tokens
    token_savings_ratio = ratio(token_savings, full_tokens)
    json_token_delta = full_tokens - ant_json_tokens
    top_k_overfetch_delta = full_tokens - top_k_overfetch_tokens
    break_even_transcript_tokens = ant_json_tokens + 1

    benchmark_cases = [
        {
            "id": "tiny_single_turn_context",
            "question": "When the whole context is tiny, is a queen-style bee relay simpler?",
            "bee_score": 0.90,
            "ant_score": 0.62,
            "bee_rationale": "One short transcript transfer has minimal overhead and preserves everything.",
            "ant_rationale": "Trace assembly adds metadata and recall ceremony that may not pay off.",
        },
        {
            "id": "multi_agent_long_handoff",
            "question": "When Agent B needs only key continuity from a larger run, which approach is cheaper?",
            "bee_score": 1.0 - token_savings_ratio,
            "ant_score": min(1.0, 0.55 + token_savings_ratio),
            "bee_rationale": "The queen relay sends the full transcript to avoid missing details.",
            "ant_rationale": f"Ant trace assembly avoids {token_savings} estimated tokens in this fixture.",
        },
        {
            "id": "uncertainty_and_contradiction",
            "question": "Which approach makes caveats and contradictions explicit before reuse?",
            "bee_score": 0.55,
            "ant_score": 0.88,
            "bee_rationale": "Transcript relay can contain caveats, but they are unstructured and easy to miss.",
            "ant_rationale": "T-I-F reliability metadata makes high indeterminacy and falsity actionable.",
        },
        {
            "id": "agent_scope_isolation",
            "question": "Which approach avoids unrelated agent memory polluting the handoff?",
            "bee_score": 0.58,
            "ant_score": 0.86,
            "bee_rationale": "A central relay can manually filter, but scope is convention-based.",
            "ant_rationale": "Agent-scoped recall makes the isolation boundary executable.",
        },
        {
            "id": "full_audit_reconstruction",
            "question": "When a reviewer needs every detail, which approach is more complete?",
            "bee_score": 0.92,
            "ant_score": 0.70,
            "bee_rationale": "The full transcript is the most complete audit artifact.",
            "ant_rationale": "Trace assembly is compact by design and may need session memory expansion.",
        },
    ]

    for case in benchmark_cases:
        case["winner"] = score_winner(case["bee_score"], case["ant_score"])

    wins = {
        "bee": sum(1 for case in benchmark_cases if case["winner"] == "bee"),
        "ant": sum(1 for case in benchmark_cases if case["winner"] == "ant"),
        "tie": sum(1 for case in benchmark_cases if case["winner"] == "tie"),
    }
    viability = "hybrid_bee_control_ant_trace_assembly" if wins["ant"] >= wins["bee"] else "bee_preferred_for_this_fixture"

    return {
        "benchmark": "phase5_bee_vs_ant_swarm_assembly",
        "bee_definition": "central queen/master relay sends or curates the full transcript/state",
        "ant_definition": "distributed trace assembly stores compact CCP packets in Dakera and recalls only relevant traces",
        "hybrid_definition": "bee/queen controls routing policy and escalation; ant assembly leaves and follows compact Dakera traces",
        "full_transcript_tokens": full_tokens,
        "ant_ccp_payload_tokens": ant_tokens,
        "ant_ccp_json_tokens": ant_json_tokens,
        "top_k_overfetch_tokens": top_k_overfetch_tokens,
        "token_savings": token_savings,
        "token_savings_ratio": token_savings_ratio,
        "token_economy_tests": [
            {
                "id": "compact_content_payload",
                "bee_tokens": full_tokens,
                "ant_tokens": ant_tokens,
                "delta": token_savings,
                "winner": token_winner(full_tokens, ant_tokens),
                "meaning": "Agent B receives only compact CCP content.",
            },
            {
                "id": "full_json_packet_payload",
                "bee_tokens": full_tokens,
                "ant_tokens": ant_json_tokens,
                "delta": json_token_delta,
                "winner": token_winner(full_tokens, ant_json_tokens),
                "meaning": "Agent B receives full memory JSON including metadata.",
            },
            {
                "id": "top_k_overfetch_payload",
                "bee_tokens": full_tokens,
                "ant_tokens": top_k_overfetch_tokens,
                "delta": top_k_overfetch_delta,
                "winner": token_winner(full_tokens, top_k_overfetch_tokens),
                "meaning": "Recall returns all fixture memories instead of only the needed CCP packet.",
            },
            {
                "id": "json_break_even",
                "bee_tokens": break_even_transcript_tokens,
                "ant_tokens": ant_json_tokens,
                "delta": 1,
                "winner": "ant",
                "meaning": "Full JSON CCP becomes cheaper only when the transcript is longer than this threshold.",
            },
        ],
        "winner_counts": wins,
        "viability": viability,
        "cases": benchmark_cases,
    }


def print_markdown(result: dict[str, Any]) -> None:
    print("# Bee vs Ant Swarm Assembly Benchmark")
    print()
    print(f"Viability: `{result['viability']}`")
    print()
    print("| Case | Bee | Ant | Winner |")
    print("|---|---:|---:|---|")
    for case in result["cases"]:
        print(f"| `{case['id']}` | {case['bee_score']:.2f} | {case['ant_score']:.2f} | `{case['winner']}` |")
    print()
    print(
        f"Token estimate: full transcript `{result['full_transcript_tokens']}`, "
        f"ant CCP payload `{result['ant_ccp_payload_tokens']}`, "
        f"savings `{result['token_savings']}`."
    )
    print()
    print("| Token Test | Bee Tokens | Ant Tokens | Delta | Winner |")
    print("|---|---:|---:|---:|---|")
    for item in result["token_economy_tests"]:
        print(f"| `{item['id']}` | {item['bee_tokens']} | {item['ant_tokens']} | {item['delta']} | `{item['winner']}` |")


def main() -> int:
    fixture = validator.load_fixture(FIXTURE)
    result = build_benchmark(fixture)
    print_markdown(result)
    print()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
