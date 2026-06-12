#!/usr/bin/env python3
"""Phase 1 T-I-F reliability validation for Dakera memories.

This script uses only Python's standard library and Dakera's public REST API.
It deliberately keeps T-I-F interpretation agent-side: Dakera stores and
recalls metadata; the local evaluator decides whether to reuse, caveat,
surface contradiction, or ask for clarification.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_API = "http://localhost:3200"
DEFAULT_FIXTURE = Path(__file__).with_name("phase1_memories.json")
DEFAULT_REQUEST_TIMEOUT = 120
REQUEST_TIMEOUT = DEFAULT_REQUEST_TIMEOUT


def load_fixture(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def request_json(method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            raw = response.read().decode("utf-8")
            if not raw:
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc}") from exc


def healthcheck(api_base: str, retries: int = 120, delay: float = 2.0) -> Any:
    last_error: Exception | None = None
    for _ in range(retries):
        try:
            return request_json("GET", f"{api_base}/health/ready")
        except Exception as exc:  # noqa: BLE001 - report final connection failure.
            last_error = exc
            time.sleep(delay)
    raise RuntimeError(f"Dakera healthcheck failed after {retries} attempts: {last_error}")


def store_memory(api_base: str, agent_id: str, memory: dict[str, Any]) -> Any:
    payload = {
        "agent_id": agent_id,
        "content": memory["content"],
        "memory_type": "semantic",
        "importance": memory.get("importance", 0.5),
        "metadata": memory.get("metadata", {}),
    }
    return request_json("POST", f"{api_base}/v1/memory/store", payload)


def recall_memories(api_base: str, agent_id: str, query: str, top_k: int) -> list[dict[str, Any]]:
    response = request_json(
        "POST",
        f"{api_base}/v1/memory/recall",
        {"agent_id": agent_id, "query": query, "top_k": top_k},
    )
    return normalize_recall_response(response)


def normalize_recall_response(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, list):
        return [item for item in response if isinstance(item, dict)]
    if not isinstance(response, dict):
        return []

    for key in ("memories", "results", "items", "data"):
        value = response.get(key)
        if isinstance(value, list):
            normalized = []
            for item in value:
                if not isinstance(item, dict):
                    continue
                memory = item.get("memory")
                if isinstance(memory, dict):
                    merged = dict(memory)
                    for score_key in ("score", "weighted_score", "smart_score"):
                        if score_key in item:
                            merged[score_key] = item[score_key]
                    normalized.append(merged)
                else:
                    normalized.append(item)
            return normalized

    if "content" in response:
        return [response]

    return []


def reliability(memory: dict[str, Any]) -> dict[str, Any]:
    metadata = memory.get("metadata")
    if isinstance(metadata, dict):
        value = metadata.get("reliability")
        if isinstance(value, dict):
            return value
    return {}


def memory_id(memory: dict[str, Any]) -> str:
    value = memory.get("id") or memory.get("memory_id") or memory.get("uuid")
    if isinstance(value, str):
        return value

    content = str(memory.get("content", ""))
    return content[:72]


def choose_baseline(memories: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not memories:
        return None
    return max(memories, key=lambda item: float(item.get("importance", 0.0) or 0.0))


def classify_tif(memory: dict[str, Any]) -> dict[str, Any]:
    rel = reliability(memory)
    t = float(rel.get("t", 0.0) or 0.0)
    i = float(rel.get("i", 0.0) or 0.0)
    f = float(rel.get("f", 0.0) or 0.0)

    if f >= 0.50:
        action = "surface_contradiction"
        reason = "high falsity means the memory is diagnostic contradiction evidence"
    elif i >= 0.50:
        action = "ask_clarification"
        reason = "high indeterminacy means reuse is unresolved"
    elif t >= 0.70 and i <= 0.35 and f <= 0.35:
        action = "reuse_confidently"
        reason = "high truth with low uncertainty and contradiction"
    else:
        action = "reuse_with_caveat"
        reason = "mixed reliability requires caveated reuse"

    return {"action": action, "reason": reason, "t": t, "i": i, "f": f}


def choose_tif_aware(memories: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if not memories:
        return None, {"action": "no_memory", "reason": "no recalled memories"}

    contradiction = [item for item in memories if classify_tif(item)["action"] == "surface_contradiction"]
    if contradiction:
        candidate = max(contradiction, key=lambda item: classify_tif(item)["f"])
        return candidate, classify_tif(candidate)

    unresolved = [item for item in memories if classify_tif(item)["action"] == "ask_clarification"]
    if unresolved:
        candidate = max(unresolved, key=lambda item: classify_tif(item)["i"])
        return candidate, classify_tif(candidate)

    candidate = choose_baseline(memories)
    assert candidate is not None
    return candidate, classify_tif(candidate)


def evaluate_scenario(scenario: dict[str, Any], memories: list[dict[str, Any]]) -> dict[str, Any]:
    baseline = choose_baseline(memories)
    tif_memory, tif_decision = choose_tif_aware(memories)
    baseline_action = "reuse_top_memory" if baseline else "no_memory"
    same_memory = memory_id(baseline) == memory_id(tif_memory) if baseline and tif_memory else False
    equivalent_reuse = same_memory and tif_decision["action"] == "reuse_confidently"
    changed = baseline_action != tif_decision["action"] and not equivalent_reuse

    return {
        "scenario": scenario["id"],
        "query": scenario["query"],
        "baseline_action": baseline_action,
        "baseline_memory": memory_id(baseline) if baseline else None,
        "tif_action": tif_decision["action"],
        "tif_reason": tif_decision["reason"],
        "tif_memory": memory_id(tif_memory) if tif_memory else None,
        "changed_decision": changed,
        "expected_changed_decision": scenario["expected_changed_decision"],
        "expected_action": scenario["expected_action"],
        "passed": changed == scenario["expected_changed_decision"]
        and tif_decision["action"] == scenario["expected_action"],
    }


def fixture_memories_for_scenario(fixture: dict[str, Any], scenario: dict[str, Any]) -> list[dict[str, Any]]:
    memories = {memory["id"]: memory for memory in fixture["memories"]}

    def by_id(memory_id: str) -> dict[str, Any]:
        try:
            return memories[memory_id]
        except KeyError as exc:
            raise KeyError(f"fixture memory id not found: {memory_id}") from exc

    if scenario["id"] == "obsolete-roundtrip-plan":
        return [by_id("phase1-obsolete-roundtrip-plan"), by_id("phase1-maintainer-target")]
    if scenario["id"] == "high-falsity-contradiction":
        return [by_id("phase1-high-falsity-handling"), by_id("phase1-maintainer-target")]
    if scenario["id"] == "high-indeterminacy-clarification":
        return [by_id("phase1-high-indeterminacy-handling"), by_id("phase1-maintainer-target")]
    return [by_id("phase1-maintainer-target"), by_id("phase1-developer-facing-name")]


def run_self_test(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for scenario in fixture["scenarios"]:
        memories = fixture_memories_for_scenario(fixture, scenario)
        results.append(evaluate_scenario(scenario, memories))
    return results


def run_runtime_validation(
    api_base: str, fixture: dict[str, Any], top_k: int, agent_id: str
) -> dict[str, Any]:
    health = healthcheck(api_base)

    store_results = []
    for memory in fixture["memories"]:
        store_results.append({"id": memory["id"], "response": store_memory(api_base, agent_id, memory)})

    scenario_results = []
    for scenario in fixture["scenarios"]:
        scenario_top_k = int(scenario.get("top_k", top_k))
        recalled = recall_memories(api_base, agent_id, scenario["query"], scenario_top_k)
        scenario_results.append(evaluate_scenario(scenario, recalled))

    return {"agent_id": agent_id, "health": health, "stored": store_results, "scenarios": scenario_results}


def print_report(results: list[dict[str, Any]]) -> None:
    print("scenario,baseline_action,tif_action,changed,passed")
    for result in results:
        print(
            ",".join(
                [
                    result["scenario"],
                    result["baseline_action"],
                    result["tif_action"],
                    str(result["changed_decision"]).lower(),
                    str(result["passed"]).lower(),
                ]
            )
        )
        print(f"  baseline_memory: {result['baseline_memory']}")
        print(f"  tif_memory: {result['tif_memory']}")
        print(f"  reason: {result['tif_reason']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Dakera T-I-F reliability metadata behavior.")
    parser.add_argument("--api", default=DEFAULT_API, help="Dakera REST API base URL.")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE, help="Path to Phase 1 fixture JSON.")
    parser.add_argument("--top-k", type=int, default=8, help="Recall top_k value.")
    parser.add_argument(
        "--agent-id",
        help="Agent ID for runtime validation. Defaults to a unique ID derived from the fixture.",
    )
    parser.add_argument(
        "--request-timeout",
        type=int,
        default=DEFAULT_REQUEST_TIMEOUT,
        help="HTTP request timeout in seconds. Startup and first recall can be slow while ONNX warms up.",
    )
    parser.add_argument("--self-test", action="store_true", help="Run local evaluator test without Dakera.")
    args = parser.parse_args()

    global REQUEST_TIMEOUT
    REQUEST_TIMEOUT = args.request_timeout

    fixture = load_fixture(args.fixture)
    if args.self_test:
        results = run_self_test(fixture)
        print_report(results)
        return 0 if all(result["passed"] for result in results) else 1

    agent_id = args.agent_id or f"{fixture['agent_id']}-{int(time.time())}"
    runtime = run_runtime_validation(args.api.rstrip("/"), fixture, args.top_k, agent_id)
    print(json.dumps(runtime, indent=2, sort_keys=True))
    return 0 if all(item["passed"] for item in runtime["scenarios"]) else 1


if __name__ == "__main__":
    sys.exit(main())
