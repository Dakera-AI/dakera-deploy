# Phase 5 Dakera CCP Handoff Validation Results

Date: 2026-06-14

Status: local proof and benchmark pass. Runtime validation partially fails:
direct recall, session proof, isolation, contradiction handling, and compact
token economy pass, but associated graph recall is not proven by the current
REST response.

Framing note: this Phase 5 package uses a hybrid swarm model. The bee/queen
layer controls orchestration policy, escalation, and full-audit fallback. The
ant layer handles distributed trace assembly: Agent A leaves compact continuity
traces in Dakera, and Agent B reassembles the needed context from recall,
metadata, sessions, and links.

## Target Runtime

```text
Dakera image: ghcr.io/dakera-ai/dakera:0.11.90 or newer
REST: http://127.0.0.1:3200
Storage: in-memory
Auth: disabled for local validation only
```

## Commands

Self-test:

```bash
python examples/dakera-ccp-handoff/validate_dakera_ccp_handoff.py --self-test
```

Five proof examples:

```bash
python examples/dakera-ccp-handoff/test_ccp_handoff_examples.py
```

Bee vs ant assembly benchmark:

```bash
python examples/dakera-ccp-handoff/benchmark_swarm_assembly.py
```

Runtime validation:

```bash
docker compose -f docker/docker-compose.tif-phase1.yml up -d
python examples/dakera-ccp-handoff/validate_dakera_ccp_handoff.py --api http://localhost:3200 --request-timeout 240
docker compose -f docker/docker-compose.tif-phase1.yml down
```

## Acceptance Criteria

- Agent A session stores compact CCP memories.
- Agent B recalls the expected CCP packet by semantic query.
- Agent B does not receive the full transcript.
- linked evidence/caveat packets are returned through associated recall.
- session memory listing includes the continuity packets.
- unrelated agent memory does not pollute Agent B recall.
- high falsity surfaces contradiction.
- high indeterminacy asks clarification.
- CCP payload estimate is smaller than full transcript estimate.
- no engine, SDK, MCP, or ranking behavior is changed.

## Result Summary

## Fresh Run Verdict

Local result: good for static proof, examples, and benchmark.

Runtime result: mixed. Dakera `0.11.90` is healthy and direct recall works, but
the current runtime did not return linked memories under the normalized
associated-recall fields.

Command status:

| Command | Result |
|---|---|
| `python -m py_compile examples/dakera-ccp-handoff/validate_dakera_ccp_handoff.py examples/dakera-ccp-handoff/test_ccp_handoff_examples.py examples/dakera-ccp-handoff/benchmark_swarm_assembly.py` | pass |
| `python examples/dakera-ccp-handoff/validate_dakera_ccp_handoff.py --self-test` | pass |
| `python examples/dakera-ccp-handoff/test_ccp_handoff_examples.py` | pass |
| `python examples/dakera-ccp-handoff/benchmark_swarm_assembly.py` | pass |
| `docker version` | pass: Docker Desktop 4.77.0 / engine 29.5.3 |
| `http://localhost:3200/health/ready` | pass: ready true, Dakera 0.11.90 |
| `python examples/dakera-ccp-handoff/validate_dakera_ccp_handoff.py --api http://localhost:3200 --request-timeout 240` | fail: 4/6 scenarios passed |

Self-test:

| Scenario | Action | Selected Fixture | Token Savings | Passed |
|---|---|---|---:|---|
| `basic-handoff` | `continue_from_ccp` | `ccp-key-decision` | 133 | true |
| `nuanced-decision` | `ask_clarification` | `ccp-caveat` | 133 | true |
| `stale-context` | `surface_contradiction` | `ccp-stale-timestamp-only` | 133 | true |
| `contradiction` | `surface_contradiction` | `ccp-stale-timestamp-only` | 133 | true |
| `namespace-agent-isolation` | `isolate_agent_scope` | none | 133 | true |
| `token-economy` | `ccp_payload_smaller` | `ccp-key-decision` | 133 | true |

Five proof examples plus honesty guard:

```text
Ran 6 tests in 0.002s
OK
```

The proof examples cover five requested points plus one honesty guard:

- ant swarm assembly framing is explicit;
- Agent A to Agent B handoff continues from a CCP packet;
- uncertainty is preserved before reuse;
- contradicted stale context is surfaced;
- agent scope and token economy hold for compact packets;
- bee wins are reported honestly in the benchmark.

Bee vs ant assembly benchmark:

| Case | Bee | Ant | Winner |
|---|---:|---:|---|
| `tiny_single_turn_context` | 0.90 | 0.62 | `bee` |
| `multi_agent_long_handoff` | 0.55 | 1.00 | `ant` |
| `uncertainty_and_contradiction` | 0.55 | 0.88 | `ant` |
| `agent_scope_isolation` | 0.58 | 0.86 | `ant` |
| `full_audit_reconstruction` | 0.92 | 0.70 | `bee` |

Viability decision: `hybrid_bee_control_ant_trace_assembly`.

This is not a clean "ant always wins" result. Bee assembly wins two modeled
cases:

- `tiny_single_turn_context`: bee wins because a tiny transcript is simpler than
  building and recalling traces.
- `full_audit_reconstruction`: bee wins because the full transcript is the most
  complete audit artifact.

Token economy subtests:

| Token Test | Bee Tokens | Ant Tokens | Delta | Winner |
|---|---:|---:|---:|---|
| `compact_content_payload` | 293 | 160 | 133 | `ant` |
| `full_json_packet_payload` | 293 | 498 | -205 | `bee` |
| `top_k_overfetch_payload` | 293 | 778 | -485 | `bee` |
| `json_break_even` | 499 | 498 | 1 | `ant` |

Conclusion: hybrid assembly is the viable shape. Bee/queen control decides when
to use compact ant traces and when to fall back to full transcript/session audit.
Ant assembly is viable for compact CCP handoff, but not as a blind "ship all
memory JSON" strategy. The implementation should keep Agent B's prompt payload
compact and use full session/transcript expansion only for audit or short-context
cases where bee assembly wins.

Token economy is not good if the system sends too much:

- full JSON packets lose by 205 estimated tokens in this fixture;
- top-k overfetch loses by 485 estimated tokens in this fixture;
- full JSON CCP only becomes cheaper after the transcript exceeds 498 estimated
  tokens.

## Runtime Validation

Runtime health:

```text
ready=true
version=0.11.90
storage=ok
embedding_engine=ok
tiered_engine=disabled
```

Runtime scenario result:

| Scenario | Runtime Action | Direct Recall | Associated Proof | Passed |
|---|---|---|---|---|
| `basic-handoff` | `continue_from_ccp` | yes | no | false |
| `nuanced-decision` | `ask_clarification` | yes | no | false |
| `stale-context` | `surface_contradiction` | yes | n/a | true |
| `contradiction` | `surface_contradiction` | yes | n/a | true |
| `namespace-agent-isolation` | `isolate_agent_scope` | yes | n/a | true |
| `token-economy` | `ccp_payload_smaller` | yes | n/a | true |

What is good:

- The runtime accepted all CCP packet stores.
- `metadata.fixture_id`, `metadata.ccp`, and `metadata.reliability` survived
  recall.
- Semantic recall found the expected decision/caveat/stale packets.
- The unrelated agent memory did not pollute recall.
- Compact runtime CCP payload remained smaller than full transcript estimate.

What is not good:

- `include_associated=true` with `associated_memories_depth=1` did not populate
  `associated_memories`, `associated`, or `linked_memories` in the normalized
  response.
- Because of that, the validator cannot yet prove linked evidence/caveat recall
  through graph expansion.
- The first runtime recall after cold start was slow in logs; later recall calls
  were faster, but this should be tracked if benchmarking latency.

Runtime validation command to rerun once Docker Desktop is running:

```bash
docker compose -f docker/docker-compose.tif-phase1.yml up -d
python examples/dakera-ccp-handoff/validate_dakera_ccp_handoff.py --api http://localhost:3200 --request-timeout 240
docker compose -f docker/docker-compose.tif-phase1.yml down
```

## Novelty Scan

Do not pitch this as the first ant-swarm agent system. External research already
contains ant-colony, pheromone, and stigmergy approaches for multi-agent AI,
including LLM routing and blackboard-style pheromone signals.

Safer pitch:

```text
Phase 5 introduces a Dakera-specific CCP handoff validator for hybrid bee-control
and ant-trace continuity: queen/bee orchestration decides policy and fallback,
while Dakera stores low-token pheromone-like continuity traces for later agents.
```

This is a stronger and more defensible claim than "first ant swarm".
