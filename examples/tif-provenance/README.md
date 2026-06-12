# T-I-F Feedback Provenance Phase 2

This example validates Phase 2 of the Dakera T-I-F decision provenance RFC:

https://github.com/Dakera-AI/dakera-deploy/issues/161

Phase 1 proved that `metadata.reliability` survives store and recall and can
change agent-side decisions. Phase 2 tests the next maintainer-requested
question: can T-I-F scores be derived from real agent interaction signals and
used in a session-scoped decision trace?

## What This Tests

The example uses Dakera's public REST API only:

- `POST /v1/memory/store`
- `POST /v1/memory/recall`
- `POST /v1/memories/{memory_id}/feedback`
- `GET /v1/memories/{memory_id}/feedback`
- `POST /v1/sessions/start`
- `GET /v1/sessions/{session_id}/memories`
- `POST /v1/memories/{memory_id}/links`

The validation remains agent-side. Dakera stores memories, feedback, sessions,
and links. The local script computes T-I-F from feedback and stores a decision
trace under `metadata.decision_provenance`.

Dakera `v0.11.90` requires `agent_id` when submitting feedback, reading
feedback history, and creating memory links. The validator keeps those
requirements explicit instead of hiding them behind an SDK.

## Feedback-Derived T-I-F Rules

```text
upvote:   t + 0.10, i - 0.03, f - 0.05
downvote: t - 0.10, i + 0.05, f + 0.15
flag:     t - 0.05, i + 0.20, f + 0.10
```

Scores are clamped to `[0.0, 1.0]`.

Decision priority:

```text
f >= 0.50 -> surface_contradiction
i >= 0.50 -> ask_clarification
t >= 0.70 and i <= 0.35 and f <= 0.35 -> reuse_confidently
otherwise -> reuse_with_caveat
```

These thresholds are validation rules only. They are not proposed as Dakera
engine behavior.

## Scenarios

The fixture covers three developer-recognizable workflows:

| Scenario | Purpose |
|---|---|
| `coding-assistant` | feedback corrects an obsolete endpoint decision |
| `research-agent` | weak-source feedback raises indeterminacy |
| `customer-support` | outdated policy is surfaced as contradiction evidence |

Each scenario records:

- baseline importance-only decision;
- feedback-derived T-I-F decision;
- decision trace memory;
- session ID;
- linked evidence memory IDs;
- associated recall proof.

## Start Dakera

The shared T-I-F compose file defaults to Dakera `v0.11.90`, binds to
`127.0.0.1`, and disables auth only for local validation. Do not run it on a
shared or internet-facing host.

```bash
docker compose -f docker/docker-compose.tif-phase1.yml up -d
```

Stop:

```bash
docker compose -f docker/docker-compose.tif-phase1.yml down
```

## Run Self-Test

```bash
python examples/tif-provenance/validate_tif_provenance.py --self-test
```

## Run Runtime Validation

```bash
python examples/tif-provenance/validate_tif_provenance.py --api http://localhost:3200 --request-timeout 240
```

The script fails if feedback history, session trace storage, or associated
recall proof is missing.
