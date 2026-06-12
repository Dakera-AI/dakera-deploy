# T-I-F Reliability Metadata Phase 1

This example validates the Phase 1 proposal from Dakera issue #161:

https://github.com/Dakera-AI/dakera-deploy/issues/161

The goal is not to prove that metadata can round-trip. The maintainer has
already confirmed that arbitrary JSON metadata is accepted and recalled by the
public API. The goal is to show that an agent can inspect T-I-F reliability
metadata and make a better decision than it would with importance/relevance
alone.

## What This Tests

The example stores real conversation-derived memories with:

```json
{
  "metadata": {
    "reliability": {
      "t": 0.95,
      "i": 0.03,
      "f": 0.01,
      "basis": "maintainer correction in Dakera issue #161",
      "source": "tif_decision_provenance"
    }
  }
}
```

The `t`, `i`, and `f` values are independent reliability components:

| Field | Meaning | Agent-side handling in this example |
|---|---|---|
| `t` | truth/support | reuse when high and contradiction/uncertainty are low |
| `i` | indeterminacy | ask for clarification or mark unresolved when high |
| `f` | falsity/contradiction | surface as contradiction evidence when high |

These rules are local agent logic only. They do not change Dakera ranking,
filters, engine schema, SDK models, or storage behavior.

## Start Dakera On Port 3200

This avoids conflicts with local services that may already use port `3000`.

```bash
cd docker
docker compose -f docker-compose.tif-phase1.yml up -d
```

Health check:

```bash
curl http://localhost:3200/health/ready
```

Stop:

```bash
cd docker
docker compose -f docker-compose.tif-phase1.yml down
```

## Run Self-Test

The self-test validates the agent-side decision rules without requiring a
running Dakera instance.

```bash
python examples/tif-reliability/validate_tif_reliability.py --self-test
```

## Run Runtime Validation

```bash
python examples/tif-reliability/validate_tif_reliability.py --api http://localhost:3200
```

The script will:

1. verify `/health/ready`;
2. create a unique runtime `agent_id` unless one is passed explicitly;
3. store issue-derived memories with `metadata.reliability`;
4. recall memories for Phase 1 scenarios;
5. compare a baseline importance/relevance-only decision with a T-I-F-aware decision;
6. fail if the expected high-`i` or high-`f` decision changes are not observed.

## Expected Decision Change

Baseline behavior:

```text
reuse_top_memory
```

T-I-F-aware behavior for a high-`f` memory:

```text
surface_contradiction
```

T-I-F-aware behavior for a high-`i` memory:

```text
ask_clarification
```

This is the Phase 1 evidence requested by the maintainer: the metadata is not
only preserved, it changes agent behavior in a reviewable way.
