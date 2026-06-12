# Phase 1 Validation Results

Date: 2026-06-12

Dakera image:

```text
ghcr.io/dakera-ai/dakera:0.11.81
```

Local runtime:

```text
REST: http://localhost:3200
gRPC: localhost:51051
Storage: in-memory
Auth: disabled for local validation only
```

## Commands

Start:

```bash
docker compose -f docker/docker-compose.tif-phase1.yml up -d
```

Health:

```bash
curl http://localhost:3200/health/ready
```

Self-test:

```bash
python examples/tif-reliability/validate_tif_reliability.py --self-test
```

Runtime validation:

```bash
python examples/tif-reliability/validate_tif_reliability.py --api http://localhost:3200
```

## Result Summary

Health returned ready:

```json
{"ready":true,"version":"0.11.81","checks":{"storage":{"status":"ok","message":null}}}
```

Runtime validation passed all scenarios:

| Scenario | Baseline action | T-I-F-aware action | Changed | Passed |
|---|---|---|---|---|
| `obsolete-roundtrip-plan` | `reuse_top_memory` | `surface_contradiction` | true | true |
| `high-falsity-contradiction` | `reuse_top_memory` | `surface_contradiction` | true | true |
| `high-indeterminacy-clarification` | `reuse_top_memory` | `ask_clarification` | true | true |
| `safe-reuse-maintainer-target` | `reuse_top_memory` | `reuse_confidently` | false | true |

## Evidence

The store response preserved `metadata.reliability`:

```json
{
  "metadata": {
    "reliability": {
      "t": 0.95,
      "i": 0.03,
      "f": 0.01,
      "basis": "ferhimedamine Phase 1 instruction in Dakera issue #161",
      "source": "tif_decision_provenance"
    }
  }
}
```

Recall returned the same metadata under recalled memory objects. The local evaluator then used that metadata agent-side.

High `f` behavior:

```text
baseline: reuse_top_memory
T-I-F aware: surface_contradiction
```

High `i` behavior:

```text
baseline: reuse_top_memory
T-I-F aware: ask_clarification
```

## Conclusion

Phase 1 confirms the maintainer's requested evidence target:

- metadata is accepted through the public store endpoint;
- `metadata.reliability` survives recall;
- T-I-F remains agent-side and does not change Dakera engine behavior;
- high falsity and high indeterminacy produce measurably different agent decisions than importance/relevance alone.
