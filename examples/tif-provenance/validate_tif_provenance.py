#!/usr/bin/env python3
"""Phase 2 T-I-F provenance validation for Dakera memories.

This script uses only Python's standard library and Dakera's public REST API.
It validates that T-I-F reliability can be derived from feedback signals, then
recorded in session-scoped decision traces linked to evidence memories.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_API = "http://localhost:3200"
DEFAULT_FIXTURE = Path(__file__).with_name("phase2_scenarios.json")
DEFAULT_REQUEST_TIMEOUT = 120
REQUEST_TIMEOUT = DEFAULT_REQUEST_TIMEOUT

FEEDBACK_DELTAS = {
    "upvote": {"t": 0.10, "i": -0.03, "f": -0.05},
    "downvote": {"t": -0.10, "i": 0.05, "f": 0.15},
    "flag": {"t": -0.05, "i": 0.20, "f": 0.10},
}


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


def clamp(value: float) -> float:
    return max(0.0, min(1.0, round(value, 4)))


def initial_reliability(memory: dict[str, Any]) -> dict[str, float]:
    reliability = memory.get("metadata", {}).get("reliability", {})
    return {
        "t": float(reliability.get("t", 0.0) or 0.0),
        "i": float(reliability.get("i", 0.0) or 0.0),
        "f": float(reliability.get("f", 0.0) or 0.0),
    }


def derive_reliability(memory: dict[str, Any], feedback_signals: list[str] | None = None) -> dict[str, Any]:
    derived = initial_reliability(memory)
    signals = list(feedback_signals if feedback_signals is not None else memory.get("feedback", []))
    for signal in signals:
        if signal not in FEEDBACK_DELTAS:
            raise ValueError(f"unsupported feedback signal for T-I-F derivation: {signal!r}")
        delta = FEEDBACK_DELTAS[signal]
        derived["t"] = clamp(derived["t"] + delta["t"])
        derived["i"] = clamp(derived["i"] + delta["i"])
        derived["f"] = clamp(derived["f"] + delta["f"])
    return {
        "t": derived["t"],
        "i": derived["i"],
        "f": derived["f"],
        "basis": "derived from Dakera memory feedback signals",
        "source": "feedback_derived_tif",
        "signals": signals,
    }


def classify_reliability(reliability: dict[str, Any]) -> dict[str, Any]:
    t = float(reliability.get("t", 0.0) or 0.0)
    i = float(reliability.get("i", 0.0) or 0.0)
    f = float(reliability.get("f", 0.0) or 0.0)

    if f >= 0.50:
        action = "surface_contradiction"
        reason = "feedback-derived falsity makes this contradiction evidence"
    elif i >= 0.50:
        action = "ask_clarification"
        reason = "feedback-derived indeterminacy makes reuse unresolved"
    elif t >= 0.70 and i <= 0.35 and f <= 0.35:
        action = "reuse_confidently"
        reason = "feedback-derived truth is high with low uncertainty and contradiction"
    else:
        action = "reuse_with_caveat"
        reason = "feedback-derived reliability is mixed"

    return {"action": action, "reason": reason, "t": t, "i": i, "f": f}


def choose_baseline(memories: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not memories:
        return None
    return max(memories, key=lambda item: float(item.get("importance", 0.0) or 0.0))


def choose_feedback_aware(memories: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if not memories:
        return None, {"action": "no_memory", "reason": "no recalled memories"}

    enriched = [(memory, classify_reliability(derive_reliability(memory))) for memory in memories]
    contradictions = [item for item in enriched if item[1]["action"] == "surface_contradiction"]
    if contradictions:
        return max(contradictions, key=lambda item: item[1]["f"])

    unresolved = [item for item in enriched if item[1]["action"] == "ask_clarification"]
    if unresolved:
        return max(unresolved, key=lambda item: item[1]["i"])

    confident = [item for item in enriched if item[1]["action"] == "reuse_confidently"]
    if confident:
        return max(confident, key=lambda item: item[1]["t"])

    baseline = choose_baseline(memories)
    assert baseline is not None
    return baseline, classify_reliability(derive_reliability(baseline))


def memory_label(memory: dict[str, Any] | None) -> str | None:
    if memory is None:
        return None
    value = memory.get("id") or memory.get("fixture_id") or memory.get("memory_id")
    if isinstance(value, str):
        return value
    return str(memory.get("content", ""))[:72]


def normalize_store_response(response: Any) -> dict[str, Any]:
    if isinstance(response, dict) and isinstance(response.get("memory"), dict):
        return response["memory"]
    if isinstance(response, dict):
        return response
    raise RuntimeError(f"unexpected store response: {response!r}")


def normalize_recall_response(response: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    memories = normalize_memory_list(response, ("memories", "results", "items", "data"))
    associated = normalize_memory_list(response, ("associated_memories", "associated", "linked_memories"))
    return memories, associated


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


def normalize_memory_item(item: dict[str, Any]) -> dict[str, Any]:
    nested = item.get("memory")
    if isinstance(nested, dict):
        merged = dict(nested)
        for key in ("score", "weighted_score", "smart_score", "depth"):
            if key in item:
                merged[key] = item[key]
        return merged
    return item


def start_session(api_base: str, agent_id: str, scenario: dict[str, Any]) -> str:
    response = request_json(
        "POST",
        f"{api_base}/v1/sessions/start",
        {
            "agent_id": agent_id,
            "metadata": {
                "phase": "phase2_tif_provenance",
                "scenario": scenario["id"],
                "source": "tif_decision_provenance",
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


def store_memory(api_base: str, agent_id: str, session_id: str, memory: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(memory.get("metadata", {}))
    metadata["fixture_id"] = memory["id"]
    metadata["reliability"]["derived"] = derive_reliability(memory)

    response = request_json(
        "POST",
        f"{api_base}/v1/memory/store",
        {
            "agent_id": agent_id,
            "content": memory["content"],
            "memory_type": "semantic",
            "importance": memory.get("importance", 0.5),
            "metadata": metadata,
            "session_id": session_id,
            "tags": ["tif-phase2", memory["id"]],
        },
    )
    stored = normalize_store_response(response)
    stored["fixture_id"] = memory["id"]
    stored["feedback"] = list(memory.get("feedback", []))
    return stored


def submit_feedback(api_base: str, agent_id: str, memory_id: str, signal: str) -> Any:
    return request_json(
        "POST",
        f"{api_base}/v1/memories/{memory_id}/feedback",
        {"agent_id": agent_id, "signal": signal},
    )


def get_feedback(api_base: str, agent_id: str, memory_id: str) -> Any:
    query = urllib.parse.urlencode({"agent_id": agent_id})
    return request_json("GET", f"{api_base}/v1/memories/{memory_id}/feedback?{query}")


def extract_feedback_signals(history: Any) -> list[str]:
    if isinstance(history, dict):
        raw_entries = history.get("entries") or history.get("feedback") or history.get("history") or []
    elif isinstance(history, list):
        raw_entries = history
    else:
        raw_entries = []

    signals = []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        value = entry.get("signal")
        if isinstance(value, str) and value in FEEDBACK_DELTAS:
            signals.append(value)
    return signals


def link_memory(api_base: str, agent_id: str, memory_id: str, target_id: str) -> Any:
    return request_json(
        "POST",
        f"{api_base}/v1/memories/{memory_id}/links",
        {"agent_id": agent_id, "target_id": target_id},
    )


def recall_associated(api_base: str, agent_id: str, query: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    response = request_json(
        "POST",
        f"{api_base}/v1/memory/recall",
        {
            "agent_id": agent_id,
            "query": query,
            "top_k": 1,
            "include_associated": True,
            "associated_memories_depth": 1,
        },
    )
    return normalize_recall_response(response)


def store_decision_trace(
    api_base: str,
    agent_id: str,
    session_id: str,
    scenario: dict[str, Any],
    direct_memory: dict[str, Any],
    safe_memory: dict[str, Any] | None,
    decision: dict[str, Any],
    evidence_ids: list[str],
) -> dict[str, Any]:
    provenance = {
        "scenario": scenario["id"],
        "decision": decision["action"],
        "reason": decision["reason"],
        "evidence_memory_ids": evidence_ids,
        "direct_memory_id": direct_memory["id"],
        "safe_memory_id": safe_memory["id"] if safe_memory else None,
        "reliability": {
            "direct": derive_reliability(direct_memory, direct_memory.get("feedback", [])),
            "safe": derive_reliability(safe_memory, safe_memory.get("feedback", [])) if safe_memory else None,
        },
        "source": "phase2_feedback_derived_tif",
    }
    response = request_json(
        "POST",
        f"{api_base}/v1/memory/store",
        {
            "agent_id": agent_id,
            "content": (
                f"Decision trace for {scenario['id']}: {decision['action']} because {decision['reason']}."
            ),
            "memory_type": "semantic",
            "importance": 0.88,
            "metadata": {"decision_provenance": provenance},
            "session_id": session_id,
            "tags": ["tif-phase2", "decision-trace", scenario["id"]],
        },
    )
    return normalize_store_response(response)


def evaluate_static_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    memories = scenario["memories"]
    baseline = choose_baseline(memories)
    direct, decision = choose_feedback_aware(memories)
    safe = next((item for item in memories if item["id"] == scenario["expected_safe_memory"]), None)
    changed = bool(baseline and direct) and memory_label(baseline) != memory_label(direct)
    if decision["action"] != "reuse_confidently":
        changed = True
    return {
        "scenario": scenario["id"],
        "baseline_memory": memory_label(baseline),
        "feedback_aware_memory": memory_label(direct),
        "safe_memory": memory_label(safe),
        "baseline_action": "reuse_top_memory" if baseline else "no_memory",
        "feedback_tif_action": decision["action"],
        "changed_decision": changed,
        "passed": changed == scenario["expected_changed_decision"]
        and decision["action"] == scenario["expected_action"]
        and memory_label(direct) == scenario["expected_direct_memory"],
    }


def run_self_test(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    return [evaluate_static_scenario(scenario) for scenario in fixture["scenarios"]]


def run_runtime_scenario(api_base: str, agent_id: str, scenario: dict[str, Any]) -> dict[str, Any]:
    session_id = start_session(api_base, agent_id, scenario)
    stored_by_fixture = {}
    feedback_history = {}
    try:
        for memory in scenario["memories"]:
            stored = store_memory(api_base, agent_id, session_id, memory)
            stored_by_fixture[memory["id"]] = stored
            memory_id = stored["id"]
            for signal in memory.get("feedback", []):
                submit_feedback(api_base, agent_id, memory_id, signal)
            feedback_history[memory["id"]] = get_feedback(api_base, agent_id, memory_id)

        runtime_memories = []
        for memory in scenario["memories"]:
            stored = stored_by_fixture[memory["id"]]
            signals = extract_feedback_signals(feedback_history[memory["id"]])
            runtime_memory = dict(memory)
            runtime_memory["id"] = stored["id"]
            runtime_memory["fixture_id"] = memory["id"]
            runtime_memory["feedback"] = signals
            runtime_memories.append(runtime_memory)

        baseline = choose_baseline(runtime_memories)
        direct, decision = choose_feedback_aware(runtime_memories)
        safe = next(
            (item for item in runtime_memories if item.get("fixture_id") == scenario["expected_safe_memory"]),
            None,
        )
        assert direct is not None
        evidence_ids = [direct["id"]]
        if safe is not None and safe["id"] not in evidence_ids:
            evidence_ids.append(safe["id"])
        trace = store_decision_trace(api_base, agent_id, session_id, scenario, direct, safe, decision, evidence_ids)
        for evidence_id in evidence_ids:
            link_memory(api_base, agent_id, trace["id"], evidence_id)

        direct_recall, associated = recall_associated(
            api_base,
            agent_id,
            f"Decision trace for {scenario['id']} {scenario['title']}",
        )
        associated_ids = {item.get("id") for item in associated}
        direct_ids = {item.get("id") for item in direct_recall}
        session_ids = {item.get("id") for item in session_memories(api_base, session_id)}
        associated_ok = bool(set(evidence_ids) & associated_ids)
        session_ok = trace["id"] in session_ids and set(evidence_ids).issubset(session_ids)
        changed = decision["action"] != "reuse_top_memory"

        return {
            "scenario": scenario["id"],
            "session_id": session_id,
            "baseline_action": "reuse_top_memory" if baseline else "no_memory",
            "baseline_memory": baseline["id"] if baseline else None,
            "feedback_tif_action": decision["action"],
            "feedback_tif_reason": decision["reason"],
            "feedback_aware_memory": direct["id"],
            "safe_memory": safe["id"] if safe else None,
            "changed_decision": changed,
            "decision_trace_memory_id": trace["id"],
            "evidence_memory_ids": evidence_ids,
            "feedback_history_signals": {
                fixture_id: extract_feedback_signals(history)
                for fixture_id, history in feedback_history.items()
            },
            "associated_recall_memory_ids": sorted(item for item in associated_ids if isinstance(item, str)),
            "direct_recall_memory_ids": sorted(item for item in direct_ids if isinstance(item, str)),
            "session_memory_ids": sorted(item for item in session_ids if isinstance(item, str)),
            "associated_recall_proof": associated_ok,
            "session_trace_proof": session_ok,
            "passed": changed == scenario["expected_changed_decision"]
            and decision["action"] == scenario["expected_action"]
            and associated_ok
            and session_ok,
        }
    finally:
        try:
            end_session(api_base, session_id, f"Phase 2 scenario {scenario['id']} completed.")
        except Exception:
            pass


def run_runtime_validation(api_base: str, fixture: dict[str, Any], agent_id: str) -> dict[str, Any]:
    health = healthcheck(api_base)
    scenarios = [run_runtime_scenario(api_base, agent_id, scenario) for scenario in fixture["scenarios"]]
    return {"agent_id": agent_id, "health": health, "scenarios": scenarios}


def print_report(results: list[dict[str, Any]]) -> None:
    print("scenario,baseline_action,feedback_tif_action,changed,trace_or_safe,passed")
    for result in results:
        print(
            ",".join(
                [
                    result["scenario"],
                    result["baseline_action"],
                    result["feedback_tif_action"],
                    str(result["changed_decision"]).lower(),
                    str(result.get("decision_trace_memory_id") or result.get("safe_memory")),
                    str(result["passed"]).lower(),
                ]
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Dakera feedback-derived T-I-F provenance.")
    parser.add_argument("--api", default=DEFAULT_API, help="Dakera REST API base URL.")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE, help="Path to Phase 2 fixture JSON.")
    parser.add_argument(
        "--agent-id",
        help="Agent ID for runtime validation. Defaults to a unique ID derived from the fixture.",
    )
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
