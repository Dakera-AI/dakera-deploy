# Phase 5 Dakera CCP Handoff Validator

This local example validates Dakera as a Context Continuity Package runtime for
multi-agent handoffs.

Most swarm examples reach for a bee/queen metaphor. This validator uses a more
useful ant swarm assembly principle: agents do not wait for a central queen to
carry the whole state. They leave compact, typed traces in the environment, and
the next agent reassembles the working context from those traces.

It follows the CCP problem described in the OpenAI Swarm thread:

https://github.com/openai/swarm/issues/87#issuecomment-4701636167

The goal is not to invent a new continuity backend. The goal is to prove that
Dakera already provides the useful CCP primitives:

```text
Agent A stores compact decisions/findings
Dakera persists, indexes, links, and recalls them
Agent B retrieves relevant context without receiving the full transcript
```

In this framing, Dakera is the trace field. CCP packets are the ant-style
stigmergic traces. Session, recall, metadata, decay, and graph links are the
assembly surface that lets another agent continue without a transcript dump.

## What This Tests

The example uses Dakera's public REST API only:

- `POST /v1/sessions/start`
- `POST /v1/sessions/{session_id}/end`
- `GET /v1/sessions/{session_id}/memories`
- `POST /v1/memory/store`
- `POST /v1/memory/recall`
- `POST /v1/memories/{memory_id}/links`

It stays agent-side. Dakera stores and recalls continuity packets; the local
validator decides whether Agent B should continue, ask clarification, surface
contradiction, or reject unrelated agent context.

## CCP Packet Shape

Continuity packet metadata is stored under `metadata.ccp` and reliability under
the existing `metadata.reliability` pattern:

```json
{
  "metadata": {
    "ccp": {
      "version": "ccp-v0",
      "handoff_id": "phase5-agent-a-to-agent-b",
      "source_agent": "agent-a",
      "target_agent": "agent-b",
      "packet_role": "decision"
    },
    "reliability": {
      "t": 0.86,
      "i": 0.10,
      "f": 0.04
    }
  }
}
```

Decision priority:

```text
f >= 0.50 -> surface_contradiction
i >= 0.50 -> ask_clarification
t >= 0.70 and i <= 0.35 and f <= 0.35 -> continue_from_ccp
otherwise -> continue_with_caveat
```

These rules are validation rules only. They are not proposed as Dakera engine
behavior.

## Scenarios

| Scenario | Purpose |
|---|---|
| `basic-handoff` | Agent B recalls Agent A's key decision |
| `nuanced-decision` | Agent B preserves the caveat attached to the handoff |
| `stale-context` | timestamp-only CCP is treated as contradicted |
| `contradiction` | high-falsity context is surfaced, not hidden |
| `namespace-agent-isolation` | unrelated agent memory does not pollute Agent B recall |
| `token-economy` | CCP payload is smaller than full transcript transfer |

## Start Dakera

The existing T-I-F validation compose file runs Dakera on port `3200`, binds to
`127.0.0.1`, and disables auth only for local validation. Do not run it on a
shared or internet-facing host.

```bash
docker compose -f docker/docker-compose.tif-phase1.yml up -d
```

Stop:

```bash
docker compose -f docker/docker-compose.tif-phase1.yml down
```

## Run Structural Fixture Test

```bash
python examples/dakera-ccp-handoff/validate_dakera_ccp_handoff.py --self-test
```

This is a structural fixture consistency test. It checks the local scenario
logic without calling Dakera, so it must not be presented as empirical Dakera
validation.

## Run Five Proof Examples

These executable examples prove the local fixture behavior before touching a
Dakera runtime:

```bash
python examples/dakera-ccp-handoff/test_ccp_handoff_examples.py
```

They cover:

- ant swarm assembly framing instead of bee/queen control;
- basic Agent A to Agent B handoff;
- uncertainty/caveat preservation;
- contradicted stale context surfacing;
- agent isolation plus token economy.

## Benchmark Bee vs Ant Assembly

The benchmark compares two explicit models and one practical hybrid:

- Bee assembly: a queen/master relay sends or curates the full transcript/state.
- Ant assembly: agents leave compact CCP traces in Dakera and the next agent
  assembles context from recall, metadata, sessions, and links.
- Hybrid assembly: bee/queen controls routing policy, escalation, and full-audit
  fallback; ant assembly handles the low-token trace field.

```bash
python examples/dakera-ccp-handoff/benchmark_swarm_assembly.py
```

The benchmark is intentionally honest and payload-based. It no longer uses
subjective `bee_score` or `ant_score` constants. It measures byte size and token
count for the payloads that would be passed to the next agent.

When `tiktoken` is installed, token counts are exact for the configured
encoding. Without it, the scripts fall back to clearly labeled
`estimated_len_div_4` counts. The fallback is useful for local smoke tests, but
it is not strong enough for a public token-economy claim.

Bee assembly can still win small-context, full-JSON, and overfetch cases. Ant
assembly wins only when the handoff payload is compact enough. The recommended
shape is not "all bees" or "all ants"; it is bee control over ant trace
assembly.

In token terms, bee dancing is volatile intercommunication: every coordination
step can spend fresh tokens. Ant trace assembly is cheaper when it works because
the pheromone-like trace is persisted in Dakera and only recalled when relevant.

This package also includes `EXTERNAL_SWARM_BENCHMARK_RESULTS.md`, which records
the broader local comparison against Aden/Hive, Agent Squad, and an external
non-T/I/F LangGraph Swarm baseline. That comparison is intentionally not framed
as a Dakera-only win: LangGraph Swarm has the smallest compact payload in that
fixture, while Dakera carries explicit reliability metadata and still needs a
separate quality benchmark.

Token economy is tested at four levels:

- compact content payload: only the recalled CCP content Agent B needs;
- decision-only payload: the smallest viable next-action packet;
- lazy projection payload: decision first, caveat/evidence only when needed;
- full JSON packet payload: content plus metadata, which can erase savings on
  short transcripts;
- top-k overfetch payload: a failure mode where recall returns too much context;
- JSON break-even: the minimum transcript size where full JSON CCP becomes
  cheaper than sending the transcript.

## Run Empirical Runtime Validation

```bash
python examples/dakera-ccp-handoff/validate_dakera_ccp_handoff.py --api http://localhost:3200 --request-timeout 240 --output-json examples/dakera-ccp-handoff/RUNTIME_OUTPUT.json
```

The runtime validator fails if the expected memory is not recalled, session
memory proof is missing, associated recall does not return linked evidence, or
the CCP payload is not smaller than the full transcript estimate.

With `--output-json`, the validator preserves the live evidence package:

- health response and Dakera version;
- session start/end responses;
- every store, link, session-memory, and recall response;
- real runtime memory IDs;
- normalized recall rankings and scores when Dakera returns them;
- elapsed milliseconds per API call using Python `time.perf_counter()`;
- tokenizer metadata.

It also writes a same-stem Markdown report, for example
`RUNTIME_OUTPUT.md`, so the raw JSON can stay audit-grade while the summary
remains readable.

## Boundary

This Phase 5 package does not change:

- Dakera engine behavior;
- SDK schemas;
- MCP tool definitions;
- recall ranking;
- graph internals.

The fractal / pheromone routing idea should only be revisited after this CCP
baseline passes locally. If it returns, it should be treated as an ant-colony
trace-scoring layer over Dakera recall, not as a replacement memory backend.
