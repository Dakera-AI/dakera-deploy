#!/usr/bin/env python3
"""Five local proof examples for the Dakera CCP handoff fixture."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

import validate_dakera_ccp_handoff as validator  # noqa: E402
import benchmark_swarm_assembly as benchmark  # noqa: E402


class DakeraCcpHandoffExamples(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = validator.load_fixture(THIS_DIR / "ccp_handoff_scenarios.json")
        cls.results = {
            result["scenario"]: result
            for result in validator.run_self_test(cls.fixture)
        }
        cls.memories = {
            memory["id"]: memory
            for memory in cls.fixture["memories"]
        }

    def test_01_ant_trace_framing_is_explicit(self) -> None:
        framing = self.fixture["swarm_framing"].lower()
        decision = self.memories["ccp-key-decision"]["content"].lower()

        self.assertIn("ant swarm assembly", framing)
        self.assertIn("traces", framing)
        self.assertIn("ant-style assembly traces", decision)

    def test_02_basic_handoff_continues_from_ccp_packet(self) -> None:
        result = self.results["basic-handoff"]
        decision = self.memories["ccp-key-decision"]

        self.assertTrue(result["passed"])
        self.assertEqual(result["action"], "continue_from_ccp")
        self.assertEqual(result["selected_memory"], "ccp-key-decision")
        self.assertEqual(decision["metadata"]["ccp"]["packet_role"], "decision")

    def test_03_caveat_preserves_uncertainty_before_reuse(self) -> None:
        result = self.results["nuanced-decision"]
        caveat = self.memories["ccp-caveat"]

        self.assertTrue(result["passed"])
        self.assertEqual(result["action"], "ask_clarification")
        self.assertGreaterEqual(caveat["metadata"]["reliability"]["i"], 0.50)

    def test_04_contradicted_stale_context_is_surfaced(self) -> None:
        stale = self.results["stale-context"]
        contradiction = self.results["contradiction"]
        memory = self.memories["ccp-stale-timestamp-only"]

        self.assertTrue(stale["passed"])
        self.assertTrue(contradiction["passed"])
        self.assertEqual(stale["action"], "surface_contradiction")
        self.assertGreaterEqual(memory["metadata"]["reliability"]["f"], 0.50)

    def test_05_agent_scope_and_token_economy_hold(self) -> None:
        isolation = self.results["namespace-agent-isolation"]
        economy = self.results["token-economy"]

        self.assertTrue(isolation["passed"])
        self.assertTrue(economy["passed"])
        self.assertEqual(isolation["action"], "isolate_agent_scope")
        self.assertEqual(economy["action"], "ccp_payload_smaller")
        self.assertGreater(economy["token_savings"], 0)

    def test_06_benchmark_reports_bee_wins_honestly(self) -> None:
        result = benchmark.build_benchmark(self.fixture)
        bee_wins = [case for case in result["cases"] if case["winner"] == "bee"]
        ant_wins = [case for case in result["cases"] if case["winner"] == "ant"]
        cases = {
            item["id"]: item
            for item in result["cases"]
        }

        self.assertGreaterEqual(len(bee_wins), 1)
        self.assertGreaterEqual(len(ant_wins), 1)
        self.assertEqual(result["winner_counts"]["bee"], len(bee_wins))
        self.assertEqual(result["winner_counts"]["ant"], len(ant_wins))
        self.assertEqual(result["viability"], "hybrid_bee_control_ant_trace_assembly")
        self.assertEqual(cases["compact_content_payload"]["winner"], "ant")
        self.assertIn(cases["full_json_packet_payload"]["winner"], {"bee", "ant", "tie"})
        self.assertIn(cases["top_k_overfetch_payload"]["winner"], {"bee", "ant", "tie"})
        self.assertNotIn("bee_score", cases["compact_content_payload"])
        self.assertNotIn("ant_score", cases["compact_content_payload"])
        self.assertIn("half_cost_feasibility", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
