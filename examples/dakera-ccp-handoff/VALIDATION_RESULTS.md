# Phase 5 Dakera CCP Handoff Validation Results

Date: 2026-06-14

Status: structural fixture proof and measured benchmark pass. Empirical runtime
validation partially fails: direct recall, session proof, isolation,
contradiction handling, and compact token economy pass, but associated graph
recall is not proven by the current REST response.

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

Structural fixture consistency test:

```bash
python examples/dakera-ccp-handoff/validate_dakera_ccp_handoff.py --self-test
```

Five proof examples:

```bash
python examples/dakera-ccp-handoff/test_ccp_handoff_examples.py
```

Measured bee vs ant assembly benchmark:

```bash
python examples/dakera-ccp-handoff/benchmark_swarm_assembly.py
```

Runtime validation:

```bash
docker compose -f docker/docker-compose.tif-phase1.yml up -d
python examples/dakera-ccp-handoff/validate_dakera_ccp_handoff.py --api http://localhost:3200 --request-timeout 240 --output-json examples/dakera-ccp-handoff/RUNTIME_OUTPUT.json
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

Local result: good for structural fixture proof, examples, and measured
payload/token benchmark.

Runtime result: mixed. Dakera `0.11.90` is healthy and direct recall works, but
the current runtime did not return linked memories under the normalized
associated-recall fields.

Runtime evidence artifacts:

```text
examples/dakera-ccp-handoff/RUNTIME_OUTPUT.json
examples/dakera-ccp-handoff/RUNTIME_OUTPUT.md
```

The JSON artifact preserves raw health, session, store, link, session-memory,
recall, normalized recall, runtime IDs, scores/ranks when returned, and per-call
latency captured with `time.perf_counter()`.

Command status:

| Command | Result |
|---|---|
| `python -m py_compile examples/dakera-ccp-handoff/validate_dakera_ccp_handoff.py examples/dakera-ccp-handoff/test_ccp_handoff_examples.py examples/dakera-ccp-handoff/benchmark_swarm_assembly.py` | pass |
| `python examples/dakera-ccp-handoff/validate_dakera_ccp_handoff.py --self-test` | pass: structural fixture consistency |
| `python examples/dakera-ccp-handoff/test_ccp_handoff_examples.py` | pass |
| `python examples/dakera-ccp-handoff/benchmark_swarm_assembly.py` | pass |
| `docker version` | pass: Docker Desktop 4.77.0 / engine 29.5.3 |
| `http://localhost:3200/health/ready` | pass: ready true, Dakera 0.11.90 |
| `python examples/dakera-ccp-handoff/validate_dakera_ccp_handoff.py --api http://localhost:3200 --request-timeout 240 --output-json examples/dakera-ccp-handoff/RUNTIME_OUTPUT.json` | fail as expected: 4/6 scenarios passed |

Tokenizer:

```text
method=tiktoken
encoding=cl100k_base
version=0.11.0
fallback=estimated_len_div_4 only if tiktoken is unavailable
```

Structural fixture test:

| Scenario | Action | Selected Fixture | Token Savings | Passed |
|---|---|---|---:|---|
| `basic-handoff` | `continue_from_ccp` | `ccp-key-decision` | 101 | true |
| `nuanced-decision` | `ask_clarification` | `ccp-caveat` | 101 | true |
| `stale-context` | `surface_contradiction` | `ccp-stale-timestamp-only` | 101 | true |
| `contradiction` | `surface_contradiction` | `ccp-stale-timestamp-only` | 101 | true |
| `namespace-agent-isolation` | `isolate_agent_scope` | none | 101 | true |
| `token-economy` | `ccp_payload_smaller` | `ccp-key-decision` | 101 | true |

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

Measured payload benchmark:

| Case | Bee Tokens | Ant Tokens | Delta | Saving Ratio | Winner |
|---|---:|---:|---:|---:|---|
| `compact_content_payload` | 222 | 121 | 101 | 0.4550 | `ant` |
| `decision_only_payload` | 222 | 42 | 180 | 0.8108 | `ant` |
| `compact_projection_payload` | 222 | 239 | -17 | -0.0766 | `bee` |
| `lazy_projection_payload` | 222 | 83 | 139 | 0.6261 | `ant` |
| `full_json_packet_payload` | 222 | 535 | -313 | -1.4099 | `bee` |
| `top_k_overfetch_payload` | 222 | 846 | -624 | -2.8108 | `bee` |
| `json_break_even` | 536 | 535 | 1 | 0.0019 | `ant` |

Methodology: measured payload/token benchmark; no subjective `bee_score` or
`ant_score` constants.

Viability decision: `hybrid_bee_control_ant_trace_assembly`.

This is not a clean "ant always wins" result. Bee assembly wins whenever the ant
payload is over-expanded:

- `compact_projection_payload`: metadata projection is bigger than this short
  fixture transcript.
- `full_json_packet_payload`: full memory JSON destroys the savings.
- `top_k_overfetch_payload`: broad recall overfetch is worse than a transcript
  dump in this fixture.

Ant assembly wins only for compact or lazy packets:

- compact content saves 101 exact tokens in this fixture;
- decision-only saves 180 exact tokens;
- lazy projection saves 139 exact tokens.

Conclusion: hybrid assembly is the viable shape. Bee/queen control decides when
to use compact ant traces and when to fall back to full transcript/session audit.
Ant assembly is viable for compact CCP handoff, but not as a blind "ship all
memory JSON" strategy. The implementation should keep Agent B's prompt payload
compact and use full session/transcript expansion only for audit or short-context
cases where bee assembly wins.

Token economy is not good if the system sends too much:

- full JSON packets lose by 313 exact tokens in this fixture;
- top-k overfetch loses by 624 exact tokens in this fixture;
- full JSON CCP only becomes cheaper after the transcript reaches roughly 536
  tokens.

Half-cost feasibility:

```text
baseline full transcript: 222 tokens
half-cost target: 111 tokens
compact content payload: 121 tokens
additional cut needed from compact content: 10 tokens
decision-only payload: 42 tokens
lazy projection payload: 83 tokens
best case reaches half cost: true
```

Interpretation: the first compact CCP cut already saves more than one third.
Cutting another third of the remaining compact payload is feasible only with
projection discipline: decision-first or lazy expansion. It is not feasible if
the system sends full memory JSON or uncontrolled top-k recall payloads.

## Runtime Validation

Runtime health:

```text
ready=true
version=0.11.90
storage=ok
embedding_engine=ok
tiered_engine=disabled
tokenizer=tiktoken cl100k_base 0.11.0
```

Runtime IDs:

```text
agent_id=dakera-ccp-phase5-1781473840
session_id=sess_18b91107c66f4e5d
ccp-key-decision=mem_18b911084e95ff9c
ccp-evidence=mem_18b91108daf39acd
ccp-caveat=mem_18b9110968002903
ccp-stale-timestamp-only=mem_18b91109f51d0373
ccp-unrelated-agent-memory=mem_18b9110a8f893bb5
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
- Real recall scores/ranks are present in the raw output and Markdown summary.
- The first store -> recall round trip is visible in `RUNTIME_OUTPUT.md`.

What is not good:

- `include_associated=true` with `associated_memories_depth=1` did not populate
  `associated_memories`, `associated`, or `linked_memories` in the normalized
  response.
- Because of that, the validator cannot yet prove linked evidence/caveat recall
  through graph expansion.
- The first runtime recall after cold start was slow in logs; later recall calls
  were faster, but this should be tracked if benchmarking latency.
- The two associated-recall failures are real runtime failures in this validator,
  not documentation mistakes.

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
