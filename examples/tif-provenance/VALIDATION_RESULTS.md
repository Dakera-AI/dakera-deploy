# Phase 2 Validation Results

Date: 2026-06-12 17:07:47 -04:00

Status: passed local runtime validation.

## Target Runtime

```text
Dakera image: ghcr.io/dakera-ai/dakera:0.11.90
REST: http://127.0.0.1:3200
gRPC: 127.0.0.1:51051
Storage: in-memory
Auth: disabled for local validation only
```

The validation compose binds ports to localhost only.

## Commands

```powershell
python -m py_compile examples\tif-provenance\validate_tif_provenance.py
python examples\tif-provenance\validate_tif_provenance.py --self-test
docker compose -f docker\docker-compose.tif-phase1.yml down
docker compose -f docker\docker-compose.tif-phase1.yml up -d
python examples\tif-provenance\validate_tif_provenance.py --api http://localhost:3200 --request-timeout 240
docker compose -f docker\docker-compose.tif-phase1.yml down
```

## Acceptance Criteria

- all three scenarios pass;
- feedback endpoints accept `upvote`, `downvote`, and `flag`;
- feedback history is readable;
- feedback-derived T-I-F changes at least one decision per scenario;
- decision trace memory is stored with `metadata.decision_provenance`;
- session memories include the trace and evidence memories;
- associated recall returns linked evidence or contradiction memories;
- no engine code is modified;
- no first-class recall filters are added.

## Result Summary

All three scenarios passed against Dakera `0.11.90`.

Runtime health reported:

```json
{
  "ready": true,
  "version": "0.11.90",
  "checks": {
    "embedding_engine": "ok",
    "storage": "ok",
    "tiered_engine": "disabled"
  }
}
```

Scenario outcomes:

| Scenario | Baseline action | Feedback-derived T-I-F action | Decision changed | Session proof | Associated recall proof |
| --- | --- | --- | --- | --- | --- |
| coding-assistant | `reuse_top_memory` | `surface_contradiction` | yes | yes | yes |
| research-agent | `reuse_top_memory` | `ask_clarification` | yes | yes | yes |
| customer-support | `reuse_top_memory` | `surface_contradiction` | yes | yes | yes |

The runtime accepted feedback signals `upvote`, `downvote`, and `flag`; feedback history was readable for every seeded memory; each scenario stored a decision trace with `metadata.decision_provenance`; session memory listing included the trace and evidence memories; associated recall returned linked evidence memories when recalling the decision trace with `include_associated=true` and `associated_memories_depth=1`.

Runtime contract notes observed on Dakera `0.11.90`:

- `POST /v1/sessions/start` returns the session id as `session.id`.
- `POST /v1/memories/{memory_id}/feedback` requires `agent_id`.
- `GET /v1/memories/{memory_id}/feedback` requires `agent_id` as a query parameter.
- `POST /v1/memories/{memory_id}/links` requires `agent_id`.

No engine code was modified. No first-class recall filters were added.
