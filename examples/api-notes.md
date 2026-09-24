# REST API Integration Notes

Practical notes for building a client directly against the Dakera REST API (no SDK required — every endpoint is plain JSON over HTTP). This page collects the behaviors that most often surprise integrators. Verified against engine **v0.11.108**.

For the full endpoint-by-endpoint reference, see the API documentation shipped with the server. This page is the "gotchas" companion — the things worth knowing before you wire up recall, forget, or consolidate.

---

## Relevance scores are relative, not absolute

`POST /v1/memory/recall` and `POST /v1/memory/search` return three score fields per hit:

| Field | Meaning |
|-------|---------|
| `score` | Retrieval relevance. **Only `[0, 1]`-bounded for pure `vector` routing** (it is cosine similarity). |
| `weighted_score` | `score` after importance-weighted re-ranking. |
| `smart_score` | Compound score: `smart = w_vec·relevance + w_imp·importance + w_rec·recency + w_freq·frequency`. |

**On `bm25` and `hybrid`/`auto` routing the raw BM25 relevance is _not_ normalized to `[0, 1]` and can exceed `1.0`** — magnitudes of ~2–30 are normal on keyword-heavy queries. Because `smart_score` inherits that relevance term, it is likewise unbounded on those routes.

**What to do:** rank hits _within a single response_ by `smart_score`, falling back to `weighted_score`, then `score` — that ordering is authoritative. Do **not** compare raw score values across different queries, across `recall` and `search`, or treat them as calibrated probabilities. If you need min-max-normalized relevance across the candidate set, start the server with `DAKERA_NORMALIZE_RELEVANCE=1`.

---

## `forget` reports rows deleted, not memories requested

`POST /v1/memory/forget` responds with `{ "deleted_count": N }`. `deleted_count` is the number of **stored vector rows** the engine removed — which can be **larger than the number of `memory_ids` you supplied**. A single logical memory may be backed by more than one row (for example, sentence-level derived rows created when `DAKERA_BATCH_SENTENCE_DECOMP` is enabled).

**What to do:** treat `deleted_count > 0` as "the delete took effect." Do not assert `deleted_count == len(memory_ids)`.

At least one filter (`memory_ids`, `memory_type`, `session_id`, `tags`, or `below_importance`) is **required** — a filterless request is rejected so the endpoint can never accidentally wipe an entire namespace.

---

## `consolidate` — know which endpoint has a real dry-run

There are three related endpoints, and they differ on whether a preview is possible:

| Endpoint | `dry_run` | Behavior |
|----------|-----------|----------|
| `POST /v1/memory/consolidate` (simple) | **None** | Always merges **and deletes the source memories** (`memories_removed` in the response). It does not accept a `dry_run` field — sending one has no effect and the merge still happens. There is no preview mode. |
| `POST /v1/agents/{agent_id}/consolidate` (CE-6) | ✅ Yes | DBSCAN clustering with a real `dry_run: true` that returns the would-be result without writing. |
| `POST /v1/knowledge/deduplicate` | ✅ Yes | `dry_run: true` (default) reports duplicate groups with **Read scope and deletes nothing**; `dry_run: false` (Write scope) merges the groups. |

**What to do:** if you want to preview before mutating, use the CE-6 consolidate endpoint or `knowledge/deduplicate` with `dry_run: true`. Reach for the simple `/v1/memory/consolidate` path only once you have already decided to merge specific `memory_ids` — it is destructive and irreversible.

---

## Bi-temporal `valid_from` / `valid_to`

You may include `valid_from` / `valid_to` (Unix seconds) in a memory's `metadata` on store — the server preserves any caller-supplied values, so the store contract is stable across versions. These fields feed the bi-temporal validity component of recall scoring, which is **opt-in**: it only contributes when the server is started with `DAKERA_BITEMPORAL_INGEST` enabled (off by default). Without that flag the fields are stored but do not influence ranking.

---

## Timestamps are Unix seconds

Every timestamp field (`created_at`, `updated_at`, `last_accessed_at`, and the temporal fields above) is returned as **Unix seconds (a number)** on the wire, not an ISO-8601 string. Normalize once at your client boundary.
