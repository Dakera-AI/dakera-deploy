# External Swarm Continuity Benchmark Results

This report adds the broader comparison data used to check whether the Phase 5
Dakera CCP handoff result was accidentally biased toward Dakera.

It is a deterministic payload benchmark. It does not run the external tools as
live agent systems, and it does not measure final answer quality. It measures
the handoff payload that each architecture would send for the same continuity
fixture.

## Methodology

- Benchmark: `neutrosophic_swarm_continuity_payload_benchmark`
- Method: deterministic payload benchmark
- Tokenizer: `tiktoken`
- Exact token counts: `true`
- Full transcript baseline: `154` tokens, `879` bytes

The benchmark compares:

- Dakera CCP ant-trace handoff
- Aden/Hive Queen-worker T/I/F report
- Agent Squad neutrosophic supervisor
- LangGraph Swarm non-T/I/F baseline

LangGraph Swarm is used as an external non-neutrosophic control. It is not a
modified local T/I/F system.

## Summary Table

| Tool | Compact | Lazy | Uncertainty | Contradiction | Full Runtime | Overfetch | Best | Worst |
|---|---:|---:|---:|---:|---:|---:|---|---|
| Dakera CCP ant-trace handoff | 79 | 63 | 66 | 64 | 199 | 637 | `lazy_projection` | `overfetch` |
| Aden/Hive Queen-worker T/I/F report | 61 | 63 | 65 | 65 | 161 | 566 | `compact_decision` | `overfetch` |
| Agent Squad neutrosophic supervisor | 49 | 58 | 53 | 54 | 127 | 493 | `compact_decision` | `overfetch` |
| LangGraph Swarm non-T/I/F baseline | 39 | 37 | 43 | 41 | 94 | 435 | `lazy_projection` | `overfetch` |

## Compact Packet vs Full Transcript

| Tool | Compact Tokens | Delta | Savings Ratio | Beats Full Transcript |
|---|---:|---:|---:|---|
| Dakera CCP ant-trace handoff | 79 | 75 | 0.487 | `true` |
| Aden/Hive Queen-worker T/I/F report | 61 | 93 | 0.6039 | `true` |
| Agent Squad neutrosophic supervisor | 49 | 105 | 0.6818 | `true` |
| LangGraph Swarm non-T/I/F baseline | 39 | 115 | 0.7468 | `true` |

## Rankings

- `compact_decision`: LangGraph Swarm non-T/I/F (39 tokens), Agent Squad (49 tokens), Aden/Hive (61 tokens), Dakera (79 tokens)
- `lazy_projection`: LangGraph Swarm non-T/I/F (37 tokens), Agent Squad (58 tokens), Dakera (63 tokens), Aden/Hive (63 tokens)
- `uncertainty`: LangGraph Swarm non-T/I/F (43 tokens), Agent Squad (53 tokens), Aden/Hive (65 tokens), Dakera (66 tokens)
- `contradiction`: LangGraph Swarm non-T/I/F (41 tokens), Agent Squad (54 tokens), Dakera (64 tokens), Aden/Hive (65 tokens)
- `full_runtime`: LangGraph Swarm non-T/I/F (94 tokens), Agent Squad (127 tokens), Aden/Hive (161 tokens), Dakera (199 tokens)
- `overfetch`: LangGraph Swarm non-T/I/F (435 tokens), Agent Squad (493 tokens), Aden/Hive (566 tokens), Dakera (637 tokens)

## Negative Results

- Dakera does not win the smallest compact payload in this fixture.
- LangGraph Swarm non-T/I/F wins compact payload size, partly because it does
  not carry explicit T/I/F reliability semantics.
- Dakera full runtime envelope is heavier than the transcript baseline in this
  fixture.
- Dakera overfetch is heavier than the transcript baseline in this fixture.
- Aden/Hive full runtime envelope is also heavier than the transcript baseline.
- Overfetch is bad for all compared systems.

## Engineering Diagnosis

The strongest supported claim is narrow:

```text
Compact typed continuity packets can reduce inter-agent handoff payload versus
full transcript transfer if the system avoids full JSON and broad overfetch.
```

The strongest negative finding is equally important:

```text
If the handoff sends full memory JSON or broad top-k overfetch, the token
economy collapses.
```

## Decision

Do not frame one system as globally better.

- Dakera is strongest when continuity can be externalized into compact recalled
  traces with reliability metadata.
- Aden/Hive is strongest as a Queen-worker runtime pattern with recovery and
  observability.
- Agent Squad is strongest as a compact supervisor/routing baseline.
- LangGraph Swarm is strongest as the external non-neutrosophic payload
  baseline in this fixture.

The practical direction is hybrid:

```text
Queen/control-plane policy + compact ant-style trace assembly + lazy expansion
+ full transcript fallback for audit.
```

