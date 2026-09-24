# REST API Integration Guide

A practical, self-contained guide to building a client directly against the Dakera REST API — no SDK required, every endpoint is plain JSON over HTTP. It covers authentication, the request/response conventions, the memory lifecycle (store → recall → update → forget), sessions, agents, the knowledge/consolidation family, error handling, and a worked minimal-client example. It closes with a **gotchas** section — the behaviors that most often surprise first-time integrators.

Verified against engine **v0.11.108**. Where behavior is gated by a version or an env flag, that is called out inline.

---

## Base URL & versioning

```
http://localhost:3000
```

- All application endpoints are under the `/v1/...` prefix (e.g. `/v1/memory/store`).
- Health and metrics endpoints are unversioned (`/health`, `/metrics`).
- Default ports: REST `3000` (`DAKERA_PORT`), gRPC `50051` (`DAKERA_GRPC_PORT`). Bind host is `DAKERA_HOST` (default `0.0.0.0`).

---

## Authentication & scopes

Authentication is on when `DAKERA_AUTH_ENABLED=true` (the production default). The **local** compose profile ships with auth disabled for convenience, so a bare `curl` works out of the box — turn it on before exposing the server.

Supply your key with **either** header (both are accepted; `X-API-Key` takes precedence, then `Authorization: Bearer`):

```
X-API-Key: dk_your_key_here
# or
Authorization: Bearer dk_your_key_here
```

(An `?api_key=` query parameter is also honored, but only as a fallback for `EventSource`/SSE clients that can't set headers. Prefer a header everywhere else.)

**Scopes** are hierarchical — `read` ⊂ `write` ⊂ `admin` ⊂ `super_admin`:

| Scope | Grants |
|-------|--------|
| `read` | recall, search, get, list, stats, graph reads, session get/list |
| `write` | everything in `read` + store, update, forget, consolidate, feedback, session start/end |
| `admin` | key management, ops metrics, diagnostics |
| `super_admin` | all namespaces, no expiry |

The root key from `DAKERA_ROOT_API_KEY` is a `super_admin` key. Additional scoped keys are minted through the `/v1/admin/keys` endpoints or per-namespace via `/v1/namespaces/{ns}/keys`. Keys are stored only as SHA-256 hashes; the plaintext (`dk_<hex>`) is shown once at creation. A key may be restricted to specific namespaces; a request outside its allowed set returns `403`.

---

## Conventions

**Content type.** All request and response bodies are `application/json`.

**Timestamps are Unix seconds** (integers) on the wire — `created_at`, `last_accessed_at`, `updated_at`, `ended_at`, `valid_from`/`valid_to`, etc. They are *not* ISO-8601 strings, despite what some SDK models imply. Normalize once at your client boundary.

**The agent is the unit of isolation.** Every memory belongs to an `agent_id`, which maps to an internal namespace (`_dakera_agent_{agent_id}`). Memories under different `agent_id`s cannot see each other. Sessions live in a shared reserved namespace (`_dakera_sessions`).

**IDs.** Memory IDs look like `mem_<hex>` and session IDs like `sess_<hex>`; both are auto-generated when you omit them, or you may supply your own.

**The `Memory` object** (returned by store, recall hits' `.memory`, get, list, etc.):

| Field | Type | Notes |
|-------|------|-------|
| `id` | `string` | `mem_<hex>` |
| `content` | `string` | the memory text |
| `agent_id` | `string` | owner |
| `memory_type` | `string` | `episodic` (default) · `semantic` · `procedural` · `working` |
| `importance` | `float` | `0.0`–`1.0` (default `0.5`) |
| `tags` | `string[]` | categorical tags |
| `metadata` | `object \| null` | arbitrary JSON |
| `session_id` | `string \| null` | associated session |
| `created_at` | `int` | Unix seconds |
| `last_accessed_at` | `int` | Unix seconds |
| `access_count` | `int` | see the memory-model note below |

**Memory types & decay.** Each type decays at a different rate (relative multipliers: `working` 3.0, `episodic` 1.0, `semantic` 0.5, `procedural` 0.3) — durable knowledge lives longer than scratch state. A memory's `importance` moves in three ways: (1) explicit [feedback](#feedback) (`upvote` adds `0.05–0.10`, `downvote` subtracts `0.15`, `flag` accelerates decay); (2) background decay; and (3) **recall itself** — every `POST /v1/memory/recall` fires a background task that increments the returned memories' `access_count`, refreshes `last_accessed_at`, and applies an importance *boost* (spaced repetition), writing the raised value back. Because recalled memories drift upward, **`min_importance` is a soft floor, not a fixed cutoff** — a memory can rise above a threshold it previously sat below simply by being recalled often.

**Request limits** (all configurable):

| Limit | Value | Env |
|-------|-------|-----|
| Max request body | 10 MB | `DAKERA_MAX_BODY_SIZE` |
| Request timeout | 300 s → `408` | `DAKERA_REQUEST_TIMEOUT` |
| Max `top_k` | 10 000 | — |
| Max batch (store / query) | 1 000 items | — |
| Max metadata fields | 100 | — |

Memory `content` is bounded by the 10 MB body limit; keep individual memories well under that.

---

## Error handling

There are **two** error shapes, depending on where the error is raised:

Handler / domain errors (most endpoints):

```json
{ "error": "human message", "code": "SCREAMING_SNAKE_CASE", "status": 400, "details": "optional" }
```

Auth-middleware errors (a `401`/`403` rejected before the handler runs):

```json
{ "error": "authentication_error", "message": "human message" }
```

So parse defensively: read `error` always, and fall back between `code`/`message`.

**Status codes you'll actually hit:**

| Status | Meaning |
|--------|---------|
| `400` | Invalid request (empty content, importance out of range, missing required field) |
| `401` | Missing / invalid / expired API key |
| `403` | Key lacks the required scope or namespace |
| `404` | Namespace or memory not found |
| `413` | Namespace vector quota exceeded |
| `429` | Rate limited — see below |
| `503` | Embedding engine unavailable, or inference queue full (`v0.11.63+`, transient — retry with backoff) |

### Rate limiting & retries

Two independent limiters can return `429`, each with a `Retry-After` header (seconds) plus `X-RateLimit-Limit` / `X-RateLimit-Remaining` / `X-RateLimit-Reset`:

- **Global** token bucket — `RATE_LIMIT_RPS` (default 100), `RATE_LIMIT_BURST` (default 50). Sends `Retry-After: 1`.
- **Per-namespace, per-operation** (store/recall) — configured through a namespace's memory policy. Sends `Retry-After: 60`.

Recommended client behavior: on `429`, honor `Retry-After` when present, otherwise back off exponentially. On `503` (inference queue full), retry with exponential backoff — it is transient. Cap `Retry-After` at a sane ceiling so a misconfigured header can't park your client for minutes.

---

## Health & readiness

| Endpoint | Auth | Use |
|----------|------|-----|
| `GET /health` | none | basic liveness; returns `{status, build_sha}` — check `build_sha` in deploy pipelines |
| `GET /health/live` | none | liveness probe; returns `uptime_seconds` |
| `GET /health/ready` | none | readiness probe; `200` when storage + embedding engine are up, else `503` |
| `GET /metrics` | none | Prometheus metrics |
| `GET /v1/ops/metrics` | admin | Prometheus metrics (scoped) |
| `GET /v1/ops/stats` | read | cluster/ops summary |

---

## Writing memories

### Store one — `POST /v1/memory/store` (write)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `agent_id` | `string` | ✓ | — |
| `content` | `string` | ✓ | — |
| `memory_type` | `string` | | `episodic` |
| `importance` | `float` | | `0.5` |
| `tags` | `string[]` | | `[]` |
| `session_id` | `string` | | active session, if any |
| `metadata` | `object` | | `null` |
| `ttl_seconds` | `int` | | `null` (relative auto-expiry) |
| `expires_at` | `int` | | `null` (absolute; wins over `ttl_seconds`) |
| `id` | `string` | | auto `mem_<hex>` |

```bash
curl -sX POST http://localhost:3000/v1/memory/store \
  -H "X-API-Key: $DAKERA_API_KEY" -H "Content-Type: application/json" \
  -d '{"agent_id":"my-agent","content":"User prefers concise replies","memory_type":"semantic","importance":0.8,"tags":["preference"]}'
```

Response: `{ "memory": { ...Memory }, "embedding_time_ms": 12 }`.

> **Auto date extraction (`v0.11.73+`):** if `content` contains a recognisable date, the server extracts the event date into `metadata._dakera_content_date` (Unix seconds) at write time and uses it for temporal-proximity scoring. Supply the field yourself to override.

### Store many — `POST /v1/memories/store/batch` (write, `v0.11.57+`)

Prefer this whenever you have ≥2 memories: the server embeds the whole batch in a single inference pass (≥100× the throughput of N single stores). Body: `{ "agent_id": "...", "memories": [ {content, memory_type?, importance?, tags?, ...}, ... ] }` — 1 to 1 000 items. Response: `{ "stored": [Memory...], "stored_count": N, "total_embedding_time_ms": M }`. The `stored` array preserves request order.

---

## Reading memories

### Recall — `POST /v1/memory/recall` (read)

Semantic + lexical retrieval optimised for precision. Key fields:

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `query` | `string` | ✓ | natural-language query |
| `agent_id` | `string` | ✓ | |
| `top_k` | `int` | `10` | |
| `memory_type` | `string` | `null` | filter |
| `tags` | `string[]` | `null` | all-match filter |
| `min_importance` | `float` | `null` | soft floor — recall nudges importance upward (see memory model) |
| `routing` | `string` | `auto` | `auto` · `vector` · `bm25` · `hybrid` |
| `rerank` | `bool` | `true` | cross-encoder rerank; degrades gracefully under load |
| `since` / `until` | ISO-8601 | `null` | created-at time window |
| `include_associated` | `bool` | `false` | traverse the knowledge graph for neighbours |

```bash
curl -sX POST http://localhost:3000/v1/memory/recall \
  -H "X-API-Key: $DAKERA_API_KEY" -H "Content-Type: application/json" \
  -d '{"agent_id":"my-agent","query":"how does the user like replies","top_k":5}'
```

Response: `{ "memories": [ {memory, score, weighted_score, smart_score}, ... ], "query_embedding_time_ms": ..., "search_time_ms": ... }`. See [Scoring](#scoring-relevance-scores-are-relative-not-absolute) — the scores are **not** absolute across queries.

### Search — `POST /v1/memory/search` (read)

Built for browsing/analysis rather than precision recall: filter by type, tags, session, importance range, and time window, with or without a `query`. Extra knobs include `sort_by` (`created_at`/`last_accessed_at`/`importance`/`access_count`), `min_importance`/`max_importance`, `created_after`/`created_before`, and `top_k` (default 10). Response: `{ "memories": [...], "total_count": N }`. Same score caveats as recall. Unlike recall, `search` does **not** apply the access boost — it is a read-only browse.

### Get by ID — `GET /v1/memory/get/{id}?agent_id={agent_id}` (read)

Returns a single `Memory`. `404` if absent.

### Batch recall — `POST /v1/memories/recall/batch` (read)

Filter-only listing (no semantic query). Body: `{ "agent_id", "filter": BatchMemoryFilter, "limit": 100 }`. `BatchMemoryFilter` accepts `tags` (**all**-match), `min_importance`/`max_importance`, `created_after`/`created_before`, `memory_type`, `session_id` — all optional; an omitted filter matches everything (there is no safety guard here, unlike batch-forget). Response: `{ "memories": [...], "total": <raw namespace count>, "filtered": <matched before limit>, "truncated": <bool> }`.

### List an agent's memories — `GET /v1/agents/{agent_id}/memories` (read)

Paginated, newest-first. Query: `limit` (default 50, capped 1000), `offset` (default 0). **Returns a bare JSON array of `Memory` objects — no envelope, no total.** Treat a result of exactly `limit` as possibly truncated and page with `offset`.

---

## Scoring — relevance scores are relative, not absolute

Recall and search return three score fields per hit:

| Field | Meaning |
|-------|---------|
| `score` | Retrieval relevance. **Only `[0,1]`-bounded on pure `vector` routing** (cosine similarity). |
| `weighted_score` | `score` after importance-weighted re-ranking. |
| `smart_score` | Compound: `smart = w_vec·relevance + w_imp·importance + w_rec·recency + w_freq·frequency`. |

**On `bm25` and `hybrid`/`auto` routing the raw BM25 relevance is _not_ normalized to `[0,1]` and can exceed `1.0`** — magnitudes of ~2–30 are normal on keyword-heavy queries. `smart_score` inherits that term, so it is likewise unbounded on those routes.

**What to do:** rank hits _within a single response_ by `smart_score` → `weighted_score` → `score`; that ordering is authoritative. Do **not** compare raw score values across queries, across recall vs search, or treat them as calibrated probabilities. Start the server with `DAKERA_NORMALIZE_RELEVANCE=1` if you need min-max-normalized relevance across the candidate set.

---

## Updating memories

- **`PUT /v1/memory/update/{id}?agent_id={agent_id}`** (write) — update `content` (re-embeds), `importance`, `tags`, `metadata`, or `memory_type`; omitted fields are left unchanged. `agent_id` is a **query parameter**, not body. Returns the updated `Memory`.
- **`POST /v1/memory/importance`** (write) — set importance directly without touching other fields.
- **[Feedback](#feedback) `POST /v1/memories/{memory_id}/feedback`** (write) — the only path that *nudges* importance: `upvote` (+0.05–0.10), `downvote` (−0.15), `flag` (accelerate decay).

---

## Deleting memories

### `POST /v1/memory/forget` (write)

Delete by filter. At least one of `memory_ids`, `memory_type`, `session_id`, `tags`, or `below_importance` is **required** — a filterless request is rejected so you can never wipe a whole namespace by accident. Response: `{ "deleted_count": N }`. Note the tag semantics here: `forget`'s `tags` deletes memories carrying **any** listed tag, whereas the `BatchMemoryFilter` used by the batch endpoints requires **all** listed tags — don't assume they match.

> **`deleted_count` counts vector rows removed, not the number of `memory_ids` you sent.** It can be *larger* than `len(memory_ids)` because one logical memory may be backed by multiple rows (e.g. sentence-level derived rows when `DAKERA_BATCH_SENTENCE_DECOMP` is enabled). Treat `deleted_count > 0` as "the delete took effect" — do not assert `deleted_count == len(memory_ids)`.

### `DELETE /v1/memories/forget/batch` (write)

Bulk delete by predicate. Body is `{ "agent_id", "filter": BatchMemoryFilter }` and the `filter` **must contain at least one predicate** (same safety guard). Note the `filter` envelope: the predicates go *inside* a `filter` object, not at the top level — a common integration snag. Response: `{ "deleted_count": N }`.

---

## Sessions

Sessions group memories for a conversation or task. Memories keep their `session_id` after the session ends.

- **`POST /v1/sessions/start`** (write) — body `{ agent_id, metadata?, id? }`. Returns `{ "session": { id, agent_id, started_at, memory_count, metadata } }`. If you omit `id`, the server mints `sess_<hex>`.
- **`POST /v1/sessions/{id}/end`** (write) — body optional `{ summary? }`. **Idempotent (`v0.9.12+`):** ending an unknown/already-ended session returns `200`, not an error — safe to retry.
  > **`end` is not read-only.** On close, the server runs DBSCAN over the session's memories and **soft-deprecates** near-duplicates (sets `expires_at ≈ now + 30d`), keeping the highest-importance anchor of each cluster, and writes an auto-summary memory when the session has >3 memories. Expect the agent's memory set to change as a side effect. (An `auto_summarize` request field exists but is currently ignored.)
- **`GET /v1/sessions/{id}`** (read) — one `Session`. `404` if absent.
- **`GET /v1/sessions?agent_id=...&limit=50&active_only=false`** (read) — enveloped: `{ "sessions": [...], "total": N }`, newest-first. `limit` capped at 1000.
- **`GET /v1/sessions/{id}/memories`** (read) — `{ session, memories, total? }`; `limit` default 50 (cap 500), `count_only` supported.

---

## Agents

- **`GET /v1/agents`** (read) — bare array of agent summaries.
- **`GET /v1/agents/{agent_id}/stats`** (read) — `{ total_memories, memories_by_type, total_sessions, active_sessions, avg_importance, oldest_memory_at, newest_memory_at }`.
- **`GET /v1/agents/{agent_id}/sessions`** (read) — bare array of `Session` (newest-first, paginated).

> Several agent list endpoints return **bare arrays** (no `{ "...": [...] }` envelope, no total): `GET /v1/agents`, `/v1/agents/{id}/memories`, `/v1/agents/{id}/sessions`. Session *list* (`GET /v1/sessions`) is the exception — it is enveloped with `total`.

---

## Knowledge & consolidation

Four related endpoints merge or de-duplicate memories. They differ sharply in destructiveness and whether a safe preview exists — this is the single most error-prone corner of the API, so read the table before wiring any of them.

| Endpoint | Preview? | What it does |
|----------|----------|--------------|
| `POST /v1/knowledge/summarize` (write) | n/a — non-destructive | Creates a **new** summary memory (`mem_summary_*`) that concatenates ≥2 sources (`\n\n---\n\n`), importance = max of sources, tags = union. **Sources are kept.** |
| `POST /v1/memory/consolidate` (write) | **none** | Merges into a new `mem_consolidated_*` and **hard-deletes the source memories**. Needs ≥2 sources; auto-picks the top 5 by importance if `memory_ids` is omitted. There is no `dry_run` — sending one has no effect. Destructive and irreversible. |
| `POST /v1/agents/{agent_id}/consolidate` (write) | **none** (takes no request body) | Runs DBSCAN using the agent's **server-side** consolidation config (set via `PATCH /v1/agents/{agent_id}/consolidation/config`), **soft-deprecating** duplicates (sets `expires_at`) and keeping anchors. Returns `{ memories_scanned, clusters_found, memories_deprecated, anchor_ids, deprecated_ids }`, or `{ skipped: true }` if disabled. |
| `POST /v1/knowledge/deduplicate` (read on preview / write on apply) | **yes, but you must ask for it** | `dry_run` **defaults to `false`** — the default call **HARD-DELETES** the duplicate rows in each group, keeping the `canonical_id`. Send **`dry_run: true`** for a Read-scope preview that deletes nothing. |

**To preview safely before mutating**, use `POST /v1/knowledge/deduplicate` with `dry_run: true`. That is the only endpoint with a request-level preview; the CE-6 agent-consolidate endpoint has no per-request preview (its behavior is governed by the stored config), and the simple `/v1/memory/consolidate` has none at all.

**`deduplicate` response field names** (easy to get wrong):

```json
{
  "groups": [ { "canonical_id": "mem_a", "duplicate_ids": ["mem_b","mem_c"], "avg_similarity": 0.96 } ],
  "duplicates_found": 2,
  "duplicates_merged": 0
}
```

- The kept memory is `canonical_id` (not `representative_id`).
- The count of duplicates is `duplicates_found` (excludes canonicals) — not `total_duplicates`.
- `duplicates_merged` is the number actually deleted — `0` on a `dry_run`.

---

## Bi-temporal `valid_from` / `valid_to`

Include `valid_from` / `valid_to` (Unix seconds) in a memory's `metadata` on store — the server preserves any caller-supplied values, so the store contract is stable across versions and you can safely send them today. These feed the bi-temporal validity component of recall scoring, which is **opt-in**: it only contributes when the server runs with `DAKERA_BITEMPORAL_INGEST` enabled. Without that flag the fields are stored but do not affect ranking.

---

## Worked example — a minimal memory client

A typical agent integration does two things: **recall relevant context at the start of a turn**, and **retain new facts at the end**. In plain `curl`:

```bash
API=http://localhost:3000
KEY=$DAKERA_API_KEY
AGENT=my-agent

# 1. Start a session for this conversation.
SID=$(curl -sX POST $API/v1/sessions/start \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d "{\"agent_id\":\"$AGENT\",\"metadata\":{\"task\":\"chat\"}}" | jq -r .session.id)

# 2. Recall context before answering.
curl -sX POST $API/v1/memory/recall \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d "{\"agent_id\":\"$AGENT\",\"query\":\"what do we know about the user\",\"top_k\":5}" \
  | jq '.memories | sort_by(-.smart_score) | .[].memory.content'

# 3. Retain what you learned (batch it if you have several).
curl -sX POST $API/v1/memories/store/batch \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d "{\"agent_id\":\"$AGENT\",\"memories\":[
        {\"content\":\"User is migrating from Pinecone\",\"memory_type\":\"semantic\",\"importance\":0.8,\"tags\":[\"profile\"],\"session_id\":\"$SID\"}
      ]}"

# 4. End the session (idempotent; runs auto-consolidation).
curl -sX POST $API/v1/sessions/$SID/end \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"summary":"Discussed migration plan"}'
```

Client patterns worth adopting: rank recall hits by `smart_score`; batch your writes; on `429`/`503` honor `Retry-After` (capped) then exponential backoff; treat `forget`'s `deleted_count` as a success flag, not a per-ID receipt.

---

## Gotchas quick-reference

1. **Scores are relative, not absolute** — rank within a response by `smart_score`; BM25/hybrid scores are unnormalized (can exceed 1.0) unless `DAKERA_NORMALIZE_RELEVANCE=1`.
2. **`forget` `deleted_count` = rows removed**, which can exceed `len(memory_ids)`.
3. **`deduplicate` defaults to `dry_run: false` and HARD-DELETES** — always send `dry_run: true` to preview.
4. **`/v1/memory/consolidate` is destructive with no dry-run**; **CE-6 `/v1/agents/{id}/consolidate` takes no body** (config is server-side, soft-deprecates); **`summarize` is non-destructive**.
5. **`deduplicate` fields are `canonical_id` / `duplicates_found` / `duplicates_merged`** — not `representative_id` / `total_duplicates`.
6. **Ending a session mutates memories** (soft-deprecation + auto-summary) — it isn't read-only.
7. **Agent list endpoints return bare arrays** (no envelope/total); session *list* is the exception.
8. **`valid_from`/`valid_to`** go in `metadata` and are preserved, but only score when `DAKERA_BITEMPORAL_INGEST` is on.
9. **Timestamps are Unix seconds**, and **recalling a memory raises its importance** (a spaced-repetition access boost) and bumps `access_count`/`last_accessed_at` — so `min_importance` is a soft floor. `search` does not apply this boost.
10. **Two error shapes** — handler errors carry `code`; auth-middleware errors carry `message`. Parse `error` first.
