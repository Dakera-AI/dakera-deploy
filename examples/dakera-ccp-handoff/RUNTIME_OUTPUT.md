# Phase 5 Runtime Output

This file is generated from a live Dakera runtime validation run.

## Runtime

- Agent ID: `dakera-ccp-phase5-1781473840`
- Session ID: `sess_18b91107c66f4e5d`
- Health ready: `True`
- Dakera version: `0.11.90`
- Tokenizer: `tiktoken`
- Scenarios passed: `4/6`

## Store Responses

| Fixture ID | Runtime Memory ID |
|---|---|
| `ccp-key-decision` | `mem_18b911084e95ff9c` |
| `ccp-evidence` | `mem_18b91108daf39acd` |
| `ccp-caveat` | `mem_18b9110968002903` |
| `ccp-stale-timestamp-only` | `mem_18b91109f51d0373` |
| `ccp-unrelated-agent-memory` | `mem_18b9110a8f893bb5` |

## Scenario Results

| Scenario | Action | Selected Fixture | Token Savings | Passed |
|---|---|---|---:|---|
| `basic-handoff` | `continue_from_ccp` | `ccp-key-decision` | 119 | `False` |
| `nuanced-decision` | `ask_clarification` | `ccp-caveat` | 101 | `False` |
| `stale-context` | `surface_contradiction` | `ccp-stale-timestamp-only` | 101 | `True` |
| `contradiction` | `surface_contradiction` | `ccp-stale-timestamp-only` | 119 | `True` |
| `namespace-agent-isolation` | `isolate_agent_scope` | `None` | 119 | `True` |
| `token-economy` | `ccp_payload_smaller` | `ccp-key-decision` | 101 | `True` |

## Example Store -> Recall Round Trip

- Scenario: `basic-handoff`
- Selected fixture: `ccp-key-decision`

| Rank | Runtime ID | Fixture ID | Score | Weighted | Smart | Content Tokens |
|---:|---|---|---:|---:|---:|---:|
| 1 | `mem_18b911084e95ff9c` | `ccp-key-decision` | 0.99402 | 0.9791097 | 1.1181183 | 42 |
| 2 | `mem_18b911087cf553f6` | `mem_18b911087cf553f6` | 0.99219537 | 0.858249 | 0.93516976 | 26 |
| 3 | `mem_18b9110968002903` | `ccp-caveat` | 0.4560159 | 0.43412715 | 0.7883076 | 35 |
| 4 | `mem_18b91108daf39acd` | `ccp-evidence` | 0.0005374385 | 0.0005180907 | 0.5696582 | 44 |
| 5 | `mem_18b911087059b80b` | `mem_18b911087059b80b` | 0.003121256 | 0.0026998864 | 0.32373172 | 16 |
| 6 | `mem_18b91109f51d0373` | `ccp-stale-timestamp-only` | 0.00031702573 | 0.0002504503 | 0.23511155 | 25 |

## API Timing

| Method | URL | Status | Elapsed ms |
|---|---|---:|---:|
| `GET` | `http://localhost:3200/health/ready` | 200 | 2069.031 |
| `POST` | `http://localhost:3200/v1/sessions/start` | 200 | 2250.599 |
| `POST` | `http://localhost:3200/v1/memory/store` | 200 | 2447.482 |
| `POST` | `http://localhost:3200/v1/memory/store` | 200 | 2458.332 |
| `POST` | `http://localhost:3200/v1/memory/store` | 200 | 2315.622 |
| `POST` | `http://localhost:3200/v1/memory/store` | 200 | 2700.21 |
| `POST` | `http://localhost:3200/v1/memory/store` | 200 | 2232.819 |
| `POST` | `http://localhost:3200/v1/memories/mem_18b911084e95ff9c/links` | 200 | 2040.421 |
| `POST` | `http://localhost:3200/v1/memories/mem_18b911084e95ff9c/links` | 200 | 2066.797 |
| `GET` | `http://localhost:3200/v1/sessions/sess_18b91107c66f4e5d/memories` | 200 | 2086.117 |
| `POST` | `http://localhost:3200/v1/memory/recall` | 200 | 63193.371 |
| `POST` | `http://localhost:3200/v1/memory/recall` | 200 | 3270.434 |
| `POST` | `http://localhost:3200/v1/memory/recall` | 200 | 3374.592 |
| `POST` | `http://localhost:3200/v1/memory/recall` | 200 | 4036.434 |
| `POST` | `http://localhost:3200/v1/memory/recall` | 200 | 2979.22 |
| `POST` | `http://localhost:3200/v1/memory/recall` | 200 | 3715.809 |
| `POST` | `http://localhost:3200/v1/sessions/sess_18b91107c66f4e5d/end` | 200 | 3836.278 |
