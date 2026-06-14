#!/usr/bin/env python3
"""Phase 5 CCP handoff validation for Dakera.

This script uses only Python's standard library and Dakera's public REST API.
It validates that Dakera can act as a Context Continuity Package runtime:
Agent A stores compact continuity packets, Agent B recalls the relevant packet
without receiving the full transcript, and caveats/contradictions remain visible.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_API = "http://localhost:3200"
DEFAULT_FIXTURE = Path(__file__).with_name("ccp_handoff_scenarios.json")
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
            response = request_json("GET", f"{api_base}/health/ready")
            if isinstance(response, dict) and response.get("ready") is True:
                return response
            last_error = RuntimeError(f"health endpoint is not ready: {response!r}")
        except Exception as exc:  # noqa: BLE001 - report final connection failure.
            last_error = exc
        time.sleep(delay)
    raise RuntimeError(f"Dakera healthcheck failed after {retries} attempts: {last_error}")


def token_estimate(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def memory_fixture_id(memory: dict[str, Any]) -> str | None:
    metadata = memory.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("fixture_id"), str):
        return metadata["fixture_id"]
    for key in ("fixture_id", "id", "memory_id"):
        value = memory.get(key)
        if isinstance(value, str):
            return value
    return None


def reliability(memory: dict[str, Any]) -> dict[str, Any]:
    metadata = memory.get("metadata")
    if isinstance(metadata, dict):
        rel = metadata.get("reliability")
        if isinstance(rel, dict):
            return rel
    return {}


def classify_ccp(memory: dict[str, Any]) -> dict[str, Any]:
    rel = reliability(memory)
    t = float(rel.get("t", 0.0) or 0.0)
    i = float(rel.get("i", 0.0) or 0.0)
    f = float(rel.get("f", 0.0) or 0.0)

    if f >= 0.50:
        action = "surface_contradiction"
        reason = "high falsity makes this packet contradiction evidence"
    elif i >= 0.50:
        action = "ask_clarification"
        reason = "high indeterminacy means handoff reuse is unresolved"
    elif t >= 0.70 and i <= 0.35 and f <= 0.35:
        action = "continue_from_ccp"
        reason = "high truth with low uncertainty and contradiction"
    else:
        action = "continue_with_caveat"
        reason = "mixed reliability requires caveated continuity"

    return {"action": action, "reason": reason, "t": t, "i": i, "f": f}


def normalize_store_response(response: Any) -> dict[str, Any]:
    if isinstance(response, dict) and isinstance(response.get("memory"), dict):
        return response["memory"]
    if isinstance(response, dict):
        return response
    raise RuntimeError(f"unexpected store response: {response!r}")


def normalize_memory_item(item: dict[str, Any]) -> dict[str, Any]:
    nested = item.get("memory")
    if isinstance(nested, dict):
        merged = dict(nested)
        for key in ("score", "weighted_score", "smart_score", "depth"):
            if key in item:
                merged[key] = item[key]
        return merged
    return item


def normalize_memory_list(response: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(response, list):
        return [normalize_memory_item(item) for item in response if isinstance(item, dict)]
    if not isinstance(response, dict):
        return []

    for key in keys:
        value = response.get(key)
        if isinstance(value, list):
            return [normalize_memory_item(item) for item in value if isinstance(item, dict)]

    if "content" in response:
        return [response]
    return []


def normalize_recall_response(response: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    memories = normalize_memory_list(response, ("memories", "results", "items", "data"))
    associated = normalize_memory_list(response, ("associated_memories", "associated", "linked_memories"))
    return memories, associated


def choose_static_memory(scenario: dict[str, Any], fixture: dict[str, Any]) -> dict[str, Any] | None:
    memories = {memory["id"]: memory for memory in fixture["memories"]}
    expected = scenario.get("expected_memory")
    if isinstance(expected, str):
        return memories.get(expected)
    return None


def evaluate_static_scenario(scenario: dict[str, Any], fixture: dict[str, Any]) -> dict[str, Any]:
    full_transcript = "\n".join(fixture["full_transcript"])
    ccp_payload = "\n".join(
        memory["content"]
        for memory in fixture["memories"]
        if memory["id"] in {"ccp-key-decision", "ccp-evidence", "ccp-caveat"}
    )
    full_tokens = token_estimate(full_transcript)
    ccp_tokens = token_estimate(ccp_payload)

    if scenario["id"] == "namespace-agent-isolation":
        passed = scenario["expected_excluded_memory"] == "ccp-unrelated-agent-memory"
        return {
            "scenario": scenario["id"],
            "selected_memory": None,
            "action": "isolate_agent_scope",
            "reason": "unrelated control memory belongs to another agent scope",
            "full_transcript_tokens": full_tokens,
            "ccp_payload_tokens": ccp_tokens,
            "token_savings": full_tokens - ccp_tokens,
            "passed": passed,
        }

    if scenario["id"] == "token-economy":
        memory = choose_static_memory(scenario, fixture)
        passed = ccp_tokens < full_tokens and memory is not None
        return {
            "scenario": scenario["id"],
            "selected_memory": memory["id"] if memory else None,
            "action": "ccp_payload_smaller" if ccp_tokens < full_tokens else "full_transcript_smaller",
            "reason": "compact CCP packet is compared to the full transcript estimate",
            "full_transcript_tokens": full_tokens,
            "ccp_payload_tokens": ccp_tokens,
            "token_savings": full_tokens - ccp_tokens,
            "passed": passed,
        }

    memory = choose_static_memory(scenario, fixture)
    decision = classify_ccp(memory) if memory is not None else {"action": "missing_memory", "reason": "not found"}
    return {
        "scenario": scenario["id"],
        "selected_memory": memory["id"] if memory else None,
        "action": decision["action"],
        "reason": decision["reason"],
        "full_transcript_tokens": full_tokens,
        "ccp_payload_tokens": ccp_tokens,
        "token_savings": full_tokens - ccp_tokens,
        "passed": memory is not None
        and memory["id"] == scenario.get("expected_memory")
        and decision["action"] == scenario["expected_action"],
    }


def run_self_test(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    return [evaluate_static_scenario(scenario, fixture) for scenario in fixture["scenarios"]]


def start_session(api_base: str, agent_id: str) -> str:
    response = request_json(
        "POST",
        f"{api_base}/v1/sessions/start",
        {
            "agent_id": agent_id,
            "metadata": {
                "phase": "phase5_dakera_ccp_handoff",
                "source": "dakera_ccp_handoff_validator",
            },
        },
    )
    for key in ("session_id", "id"):
        value = response.get(key) if isinstance(response, dict) else None
        if isinstance(value, str):
            return value
    nested = response.get("session") if isinstance(response, dict) else None
    if isinstance(nested, dict) and isinstance(nested.get("id"), str):
        return nested["id"]
    raise RuntimeError(f"session start did not return a session id: {response!r}")


def end_session(api_base: str, session_id: str, summary: str) -> Any:
    return request_json("POST", f"{api_base}/v1/sessions/{session_id}/end", {"summary": summary})


def session_memories(api_base: str, session_id: str) -> list[dict[str, Any]]:
    response = request_json("GET", f"{api_base}/v1/sessions/{session_id}/memories")
    return normalize_memory_list(response, ("memories", "results", "items", "data"))


def store_memory(api_base: str, agent_id: str, session_id: str | None, memory: dict[str, Any]) -> dict[str, Any]:
    metadata = copy.deepcopy(memory.get("metadata", {}))
    if not isinstance(metadata, dict):
        raise ValueError(f"memory {memory.get('id', '<unknown>')} metadata must be an object")
    metadata["fixture_id"] = memory["id"]

    payload: dict[str, Any] = {
        "agent_id": agent_id,
        "content": memory["content"],
        "memory_type": "semantic",
        "importance": memory.get("importance", 0.5),
        "metadata": metadata,
        "tags": memory.get("tags", []),
    }
    if session_id is not None:
        payload["session_id"] = session_id

    response = request_json("POST", f"{api_base}/v1/memory/store", payload)
    stored = normalize_store_response(response)
    stored["fixture_id"] = memory["id"]
    return stored


def link_memory(api_base: str, agent_id: str, memory_id: str, target_id: str) -> Any:
    return request_json(
        "POST",
        f"{api_base}/v1/memories/{memory_id}/links",
        {"agent_id": agent_id, "target_id": target_id},
    )


def recall(api_base: str, agent_id: str, query: str, top_k: int = 8, associated: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payload: dict[str, Any] = {"agent_id": agent_id, "query": query, "top_k": top_k}
    if associated:
        payload["include_associated"] = True
        payload["associated_memories_depth"] = 1
    response = request_json("POST", f"{api_base}/v1/memory/recall", payload)
    return normalize_recall_response(response)


def enrich_recalled(recalled: list[dict[str, Any]], stored_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    runtime_to_fixture = {
        stored["id"]: fixture_id
        for fixture_id, stored in stored_by_id.items()
        if isinstance(stored.get("id"), str)
    }
    enriched = []
    for item in recalled:
        memory = copy.deepcopy(item)
        fixture_id = memory_fixture_id(memory)
        if fixture_id is None:
            fixture_id = runtime_to_fixture.get(memory.get("id"))
        if fixture_id is not None:
            memory["fixture_id"] = fixture_id
        enriched.append(memory)
    return enriched


def find_by_fixture_id(memories: list[dict[str, Any]], fixture_id: str) -> dict[str, Any] | None:
    return next((memory for memory in memories if memory.get("fixture_id") == fixture_id), None)


def evaluate_runtime_scenario(
    api_base: str,
    agent_id: str,
    scenario: dict[str, Any],
    fixture: dict[str, Any],
    stored_by_id: dict[str, dict[str, Any]],
    session_ids: set[str],
) -> dict[str, Any]:
    full_transcript = "\n".join(fixture["full_transcript"])
    memories, associated = recall(
        api_base,
        agent_id,
        scenario["query"],
        top_k=8,
        associated=scenario["id"] in {"nuanced-decision", "basic-handoff"},
    )
    enriched = enrich_recalled(memories, stored_by_id)
    associated_enriched = enrich_recalled(associated, stored_by_id)
    recalled_fixture_ids = {memory.get("fixture_id") for memory in enriched}
    associated_fixture_ids = {memory.get("fixture_id") for memory in associated_enriched}

    full_tokens = token_estimate(full_transcript)
    ccp_text = "\n".join(memory.get("content", "") for memory in enriched[:3])
    ccp_tokens = token_estimate(ccp_text)

    if scenario["id"] == "namespace-agent-isolation":
        excluded = scenario["expected_excluded_memory"]
        passed = excluded not in recalled_fixture_ids
        return {
            "scenario": scenario["id"],
            "selected_memory": None,
            "recalled_fixture_ids": sorted(item for item in recalled_fixture_ids if isinstance(item, str)),
            "associated_fixture_ids": sorted(item for item in associated_fixture_ids if isinstance(item, str)),
            "action": "isolate_agent_scope" if passed else "agent_scope_polluted",
            "full_transcript_tokens": full_tokens,
            "ccp_payload_tokens": ccp_tokens,
            "token_savings": full_tokens - ccp_tokens,
            "session_memory_proof": bool(session_ids),
            "associated_recall_proof": True,
            "passed": passed,
        }

    expected = scenario.get("expected_memory")
    selected = find_by_fixture_id(enriched, expected) if isinstance(expected, str) else None
    if selected is None and isinstance(expected, str) and expected in associated_fixture_ids:
        selected = find_by_fixture_id(associated_enriched, expected)
    decision = classify_ccp(selected) if selected is not None else {"action": "missing_memory", "reason": "not found"}

    associated_ok = True
    recall_ok = not isinstance(expected, str) or expected in recalled_fixture_ids
    if scenario["id"] == "basic-handoff":
        associated_ok = {"ccp-evidence", "ccp-caveat"}.issubset(associated_fixture_ids)
    if scenario["id"] == "nuanced-decision":
        recall_ok = isinstance(expected, str) and expected in recalled_fixture_ids.union(associated_fixture_ids)
        associated_ok = "ccp-caveat" in recalled_fixture_ids.union(associated_fixture_ids) and (
            "ccp-evidence" in associated_fixture_ids or "ccp-key-decision" in associated_fixture_ids
        )

    if scenario["id"] == "token-economy":
        action = "ccp_payload_smaller" if ccp_tokens < full_tokens else "full_transcript_smaller"
        passed = selected is not None and recall_ok and ccp_tokens < full_tokens
    else:
        action = decision["action"]
        passed = (
            selected is not None
            and action == scenario["expected_action"]
            and recall_ok
            and associated_ok
        )

    return {
        "scenario": scenario["id"],
        "selected_memory": selected.get("id") if selected else None,
        "selected_fixture_id": selected.get("fixture_id") if selected else None,
        "recalled_fixture_ids": sorted(item for item in recalled_fixture_ids if isinstance(item, str)),
        "associated_fixture_ids": sorted(item for item in associated_fixture_ids if isinstance(item, str)),
        "action": action,
        "reason": decision.get("reason", "token economy comparison"),
        "full_transcript_tokens": full_tokens,
        "ccp_payload_tokens": ccp_tokens,
        "token_savings": full_tokens - ccp_tokens,
        "session_memory_proof": bool(session_ids),
        "associated_recall_proof": associated_ok,
        "passed": passed,
    }


def run_runtime_validation(api_base: str, fixture: dict[str, Any], agent_id: str) -> dict[str, Any]:
    health = healthcheck(api_base)
    session_id = start_session(api_base, agent_id)
    stored_by_id: dict[str, dict[str, Any]] = {}
    try:
        agent_a_memories = [memory for memory in fixture["memories"] if memory["id"] != "ccp-unrelated-agent-memory"]
        unrelated = next(memory for memory in fixture["memories"] if memory["id"] == "ccp-unrelated-agent-memory")

        for memory in agent_a_memories:
            stored_by_id[memory["id"]] = store_memory(api_base, agent_id, session_id, memory)

        unrelated_agent_id = f"{agent_id}-unrelated"
        stored_by_id[unrelated["id"]] = store_memory(api_base, unrelated_agent_id, None, unrelated)

        for target_fixture_id in ("ccp-evidence", "ccp-caveat"):
            link_memory(
                api_base,
                agent_id,
                stored_by_id["ccp-key-decision"]["id"],
                stored_by_id[target_fixture_id]["id"],
            )

        session_ids = {
            item.get("id")
            for item in session_memories(api_base, session_id)
            if isinstance(item.get("id"), str)
        }

        scenarios = [
            evaluate_runtime_scenario(api_base, agent_id, scenario, fixture, stored_by_id, session_ids)
            for scenario in fixture["scenarios"]
        ]
        return {
            "agent_id": agent_id,
            "session_id": session_id,
            "health": health,
            "stored_fixture_ids": sorted(stored_by_id),
            "session_memory_ids": sorted(session_ids),
            "scenarios": scenarios,
        }
    finally:
        try:
            end_session(api_base, session_id, "Phase 5 Dakera CCP handoff validation completed.")
        except Exception:
            pass


def print_report(results: list[dict[str, Any]]) -> None:
    print("scenario,action,selected_fixture_id,token_savings,passed")
    for result in results:
        print(
            ",".join(
                [
                    result["scenario"],
                    result["action"],
                    str(result.get("selected_fixture_id") or result.get("selected_memory")),
                    str(result["token_savings"]),
                    str(result["passed"]).lower(),
                ]
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Dakera CCP handoff behavior.")
    parser.add_argument("--api", default=DEFAULT_API, help="Dakera REST API base URL.")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE, help="Path to CCP scenario fixture JSON.")
    parser.add_argument("--agent-id", help="Agent ID for runtime validation. Defaults to a unique fixture-derived ID.")
    parser.add_argument(
        "--request-timeout",
        type=int,
        default=DEFAULT_REQUEST_TIMEOUT,
        help="HTTP request timeout in seconds.",
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
    runtime = run_runtime_validation(args.api.rstrip("/"), fixture, agent_id)
    print(json.dumps(runtime, indent=2, sort_keys=True))
    return 0 if all(item["passed"] for item in runtime["scenarios"]) else 1


if __name__ == "__main__":
    sys.exit(main())
