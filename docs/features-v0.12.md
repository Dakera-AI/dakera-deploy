# Features in Dakera v0.12.0: what to turn on, what it costs, how to check it

v0.12.0 upgrades in place and keeps its behaviour, so a deployment that sets nothing new runs
exactly as v0.11.108 did (apart from the fixes and behaviour changes in the server's
[UPGRADE.md](https://github.com/Dakera-AI/dakera/blob/main/docs/v0.12/UPGRADE.md)). Everything new is
**opt-in**: this page says, per feature, what it is, when to use it, which variables and which
files in this repository switch it on, what it costs in CPU, memory and disk, what it cannot be
combined with, and how to verify it is running.

Sources: the server's `docs/v0.12/RELEASE_NOTES.md`, `docs/multimodal.md`,
`docs/models-and-docker.md`, `docs/grpc.md`, `docs/v0.12/UPGRADE.md`, the CHANGELOG `[0.12.0]`
section, and `crates/config/src/known_env.rs` (the registry of every variable the server reads: a
`DAKERA_*` name that is not in it is reported at startup). Every variable here is in that registry.
Numbers are the server's own measurements; where a number is derived from them it says so, and
what is not measured yet says so too (see [What is not measured](#what-is-not-measured)).

- [Capability matrix](#capability-matrix)
- [How to switch a feature on in each deployment shape](#how-to-switch-a-feature-on)
- [Multilingual](#multilingual)
- [Multimodal: attachments, speech to text, image and page indexing](#multimodal)
- [Multi-vector records](#multi-vector-records)
- [Late interaction](#late-interaction)
- [RaBitQ search mode](#rabitq-search-mode)
- [Rerank controls](#rerank-controls)
- [The model store](#the-model-store)
- [Switching the embedding model](#switching-the-embedding-model)
- [What can be combined](#what-can-be-combined)
- [Security](#security)
- [Reliability](#reliability)
- [Observability](#observability)
- [Performance and sizing](#performance-and-sizing)
- [What is not measured](#what-is-not-measured)
- [Verifying a running server](#verifying-a-running-server)

---

## Capability matrix

All rows are **off by default**. "Overlay" is the compose file in `docker/` (add it with a second
`-f`); "K8s" is the Kustomize overlay in `k8s-features/overlays/`; "Helm" is the value block in the
[dakera-helm](https://github.com/Dakera-AI/dakera-helm) chart (`dakera.features.*`).

| Feature | Switch (compose overlay / K8s / Helm) | Variables | Resources | Constraints | Verify (`GET /v1/capabilities`) |
|---|---|---|---|---|---|
| **Multilingual** (bge-m3, per-language full-text, CJK bigrams, per-language query routing) | `docker-compose.multilingual.yml` / `overlays/multilingual` / `features.multilingual` | `DAKERA_MODEL=bge-m3`, `DAKERA_TIERED=0`, `DAKERA_FULLTEXT_LANGUAGE`, `DAKERA_FULLTEXT_CJK_BIGRAMS`, `DAKERA_QUERY_LANG`, `DAKERA_MAX_SEQ_LENGTH`; per request `lang` | bge-m3 ~570 MB download (+ an ORT-format copy), CPU ONNX only, 1024-d, truncation 2048 tokens by default | Fresh store or model-change migration; not with `DAKERA_TIERED=1`, GPU, Candle or the static backend; not with late interaction / vision; `dakera downgrade` refuses it | `default_model` = `bge-m3`; `fulltext_language`; `query_languages` |
| **Attachments** | `docker-compose.multimodal.yml` / `overlays/multimodal` / `features.multimodal` | `DAKERA_ATTACHMENTS`, `DAKERA_ATTACHMENT_MAX_BYTES` (25 MiB) | Stored per namespace, counted by quotas, backed up, replicated | `501 FEATURE_DISABLED` when off; upload over the limit is `413` | `attachments.enabled`, `attachments.max_bytes` |
| **Speech to text** | same overlay | `DAKERA_ATTACHMENTS`, `DAKERA_WHISPER_MODEL` (`whisper-tiny.en`) | ~151 MB download; one 30-second window of activations (128 MiB) reserved per job | English only, WAV only (PCM 8/16/24/32-bit or float); jobs are in memory only (lost on restart; the stored memory stays) | `attachments.transcription.model` |
| **Image / page indexing and visual recall** (colmodernvbert) | `docker-compose.vision.yml` / `overlays/vision` / `features.vision` | `DAKERA_VISION`, `DAKERA_ATTACHMENTS`, `DAKERA_SCORING_STRATEGY=late-interaction`, `DAKERA_TIERED=0`, `DAKERA_VISION_MODEL` | ~966 MB download (+ ORT copy), conversion reserves ~1 GB, ~10.7 s per page on CPU, one page at a time; image peak +1.9 GiB at 17 tiles | **A dedicated data root and bucket** (the namespaces hold 128-d page vectors); PNG only, at most 64 megapixels; not with text models; `dakera downgrade` refuses it | `vision.enabled`, `vision.model`, `scoring.late_interaction.lane` = `visual` |
| **Multi-vector records** | `docker-compose.records.yml` / `overlays/records` / `features.records` | `DAKERA_RECORDS`, `DAKERA_RECORD_MAX_VECTORS` (4096), `DAKERA_RECORD_MAX_BYTES` (8 MiB) | Extras are stored beside the primary vector (f32, f16 or i8) | At most 8 extra representations per record; over a limit is `413`; no record delete route (delete through the vector routes) | `records.enabled`, `records.max_*` |
| **Late interaction** (colbert-small, MaxSim) | `docker-compose.late-interaction.yml` / `overlays/late-interaction` / `features.lateInteraction` | `DAKERA_MODEL=colbert-small`, `DAKERA_SCORING_STRATEGY=late-interaction`, `DAKERA_TIERED=0` | ~34 MB model, 96-d token vectors; steady recall p50 0.10 s at 1k memories, 0.23 s at 10k | Fresh store or migration; **not with `DAKERA_TIERED=1`** (`501`); not with multilingual / vision; `dakera downgrade` refuses it | `scoring.late_interaction.enabled`, `.model_supported`, `.lane` = `text`; `late_interaction_stats` |
| **RaBitQ search mode** | `docker-compose.rabitq.yml` / `overlays/rabitq` / `features.rabitq` | `DAKERA_SEARCH_MODE=rabitq`, `DAKERA_RABITQ_BITS` (1) | **Saves latency, not memory**: codes sit next to the float vectors and are rebuilt after a restart | Any store; drop the setting to go back | `search_mode` = `rabitq` |
| **Rerank controls** | env only (all shapes) | `DAKERA_RERANK_MAX_CANDIDATES`; per request `rerank_candidates`; `rerank_report` in the answer | Cuts CPU per recall (the cost is per candidate) | Unset = the whole pool, as before | `rerank_report` on recall / search |
| **Model store** (`dakera models list / pull / prune`, baked images, proxies, mirror, offline) | the base files pass `HF_ENDPOINT`, `HF_HUB_OFFLINE`, `HTTPS_PROXY`, `HTTP_PROXY`, `ALL_PROXY`, `NO_PROXY`; K8s `models-cache` component; Helm `dakera.models.*` | `HF_HOME`, `HF_TOKEN`, `HF_ENDPOINT`, `HF_HUB_OFFLINE`, proxy variables, `DAKERA_MODEL_PATH` (+ `_WHISPER_`, `_VISION_`) | The image needs no volume; other models need a model volume | `https://` proxy URLs are not supported | `dakera models list`; `/health/ready`; `/health` `degraded` |
| **Security** (gRPC auth, scoped keys, keyring, cluster secret) | on by default (v0.12 behaviour); secrets in `.env`, `.env.ha`, K8s Secret | `DAKERA_AUTH_ENABLED`, `DAKERA_ENCRYPTION_KEY`, `DAKERA_CLUSTER_SECRET`, `DAKERA_CLUSTER_NODE_ID` | none | gRPC clients need a key; namespace-pinned keys lose node-wide routes | `/health` `config_warnings`; `GET /admin/encryption/status`; `/admin/cluster/status` |
| **Reliability** (RocksDB hot tier, WAL group commit, durable outbox, tombstones, bucket per node) | the base files (tiered storage on) | `DAKERA_ROCKSDB_SYNC`, `DAKERA_HOT_TIER`, `DAKERA_WAL*`, `DAKERA_CLUSTER_*` | fsync per write batch; the outbox is bounded at 64 MiB | One S3 bucket per cluster node; one server per data root | `/health` `degraded`; `/admin/cluster/status` |
| **Observability** | `monitoring/` (`--profile monitoring`), `k8s/monitoring/` | `/metrics` | one scrape: ~25 series per active agent | per-agent series grow with agents | Prometheus targets up; Grafana "Dakera Overview" |

---

## How to switch a feature on

**Docker Compose.** Each overlay sets the variables its feature needs, including the ones that must
change (`DAKERA_TIERED=0`). Add it after the base file:

```bash
cd docker
# single node
docker compose -f docker-compose.yml -f docker-compose.multilingual.yml up -d
# several features (combinable ones only, see the table below)
docker compose -f docker-compose.yml -f docker-compose.multilingual.yml \
  -f docker-compose.multimodal.yml -f docker-compose.records.yml up -d
# 3-node HA cluster: the ha.* twins, which set the same variables on all three nodes
docker compose -f docker-compose.ha.yml -f docker-compose.ha.multilingual.yml up -d
```

Tuning variables go in `.env` (see `docker/.env.example`, "v0.12 features"). Check any combination
before starting it: `docker compose -f ... config`.

**Kubernetes (raw manifests).** `k8s-features/` holds Kustomize *components* (one per feature) and
ready-made *overlays* that apply them to `k8s/`:

```bash
kubectl apply -k k8s-features/overlays/multilingual
kubectl apply -k k8s-features/overlays/multilingual-multimodal
kubectl apply -k k8s-features/overlays/vision        # its own namespace, MinIO and volumes
```

The `models-cache` component backs the model cache with a PVC (`dakera-models`, 10Gi) and adds an
init container running `dakera models pull configured`. Compose your own overlay from components
(`components: [../../components/models-cache, ../../components/multilingual]`).

**Helm.** The chart has a commented, off-by-default block per feature (`dakera.features.*`); see
the dakera-helm README.

**Before you switch on** a feature that changes the embedding model or the lane (multilingual, late
interaction, vision), read [Switching the embedding model](#switching-the-embedding-model): the
store records its model and refuses to start with another one.

---

## Multilingual

**What.** `bge-m3` is the multilingual embedding model (XLM-RoBERTa, 1024-d, CLS pooling). Full-text
(BM25) search gets a Snowball stemmer and stop words per language, character-bigram indexing of
unsegmented scripts (Chinese, Japanese, Korean, Thai: not indexed at all in v0.11), and dates and
temporal expressions are understood in seven query languages (`en`, `de`, `fr`, `es`, `it`, `pt`,
`nl`).

**When.** Your agents store or search text in languages other than English, or in several at once.
English-only deployments gain nothing from it: `bge-large` stays the default and is in the image.

| Variable | Default | Values | Effect |
|---|---|---|---|
| `DAKERA_MODEL` | `bge-large` | `bge-large`, `bge-m3`, `minilm`, `bge-small`, `e5-small`, `modernbert-embed-base`, `gte-modernbert-base`, `colbert-small` | The embedding model. An unrecognised name refuses a fresh install; on a deployment that holds data it is a warning and the model is `bge-large` (then the model guard refuses the start if the store used another) |
| `DAKERA_FULLTEXT_LANGUAGE` | `en` | an ISO 639-1 code or English name of a Snowball language (`de`, `french`, `pt-BR`, ...); `zh` / `ja` / `ko` / `th` or `none` / `multilingual` = no stemming | BM25 analyzer of **newly created** namespace indexes. The analyzer is stored with each index |
| `DAKERA_FULLTEXT_CJK_BIGRAMS` | on unless the language is `en` | `1/0`, `true/false`, `yes/no`, `on/off` | Index unsegmented scripts as character bigrams. Set `true` on an English deployment that also stores such text |
| `DAKERA_QUERY_LANG` | `en`, or `DAKERA_FULLTEXT_LANGUAGE` when that is a supported query language | `en`, `de`, `fr`, `es`, `it`, `pt`, `nl`, `auto` | Language of the query-routing patterns ("when", "how long ago", ...), temporal expressions and date extraction. `auto` detects per query and falls back to the deployment language |
| `DAKERA_MAX_SEQ_LENGTH` | model maximum (`bge-m3`: 2048) | integer, clamped to `[16, model maximum]` | Truncation in tokens. `bge-m3` supports 8192, but one 8192-token row needs about 4 GiB of attention scores per layer, so its default cap is 2048 |

**Per request.** `"lang": "de"` (the same codes, or a name or region form such as `pt-BR`) is accepted on
`POST /v1/memory/recall`, `/v1/memory/search`, `/v1/memory/store`, `/v1/memories/store/batch`,
`PUT /v1/memory/update/{id}`, `POST /v1/extract` and `/v1/memories/extract`. On recall and search it
selects the routing patterns and temporal expressions of the query (it does not translate or filter);
on a write it selects how the content's event date and date entities are parsed and is recorded on the
memory (`_dakera_lang`). An unsupported value is `400`. Omitted = the server-wide language.

**Switching an existing namespace's analyzer.** The analyzer is a property of each index.
`DAKERA_FULLTEXT_LANGUAGE` applies to new indexes; to re-analyse an existing namespace (global admin
key):

```bash
curl -X POST localhost:3000/admin/fulltext/reindex -H "X-API-Key: $ADMIN" \
  -H 'Content-Type: application/json' -d '{"namespace": "_dakera_agent_alice", "rebuild": true}'
# omit "namespace" for every agent namespace; "rebuild" is implied when the index was built
# under another analyzer. The answer lists, per namespace, rebuilt and analyzer_language.
```

**Constraints.**

- `bge-m3` runs on the **CPU ONNX backend only**: the static backend, the Candle backend and GPU mode
  (`DAKERA_USE_GPU`, the `:gpu` image) refuse it at startup instead of producing wrong vectors.
- With `DAKERA_TIERED=1` the tiered embedding engine **always embeds with bge-large and ignores
  `DAKERA_MODEL`** (a warning). The quick-start compose file and the Helm chart default to
  `DAKERA_TIERED=1`; the overlay sets it to `0`. All nodes sharing a store must agree on both values.
- The store records its model: use a fresh store or the [migration](#switching-the-embedding-model).
- v0.11 cannot read it: `dakera downgrade` refuses a store on `bge-m3` (move it to a v0.11 model
  under v0.12 first).
- `DAKERA_MAX_SEQ_LENGTH` applies to text models only (the visual model has its own 2048-token cap).

**Resources.** The model is not in the image. ~570 MB downloads into the model cache on first start
(the server answers `/health/live` meanwhile and `/health/ready` with `503` and the progress), is converted
once to an ORT-format copy next to it, then memory-mapped. Pre-pull it:
`docker compose run --rm dakera models pull bge-m3`. Measured (see "Measured in the deployment
validation"): ready 12 s after the container started, download included; 1.1 GB on the model volume (the
570 MB file and its ORT copy); container peak 1.29 GiB. Quality and latency of bge-m3 against
bge-large on your data are **not measured** in the release notes; measure before committing.

**Verify.**

```bash
curl -s localhost:3000/v1/capabilities -H "X-API-Key: $KEY" | jq '{default_model, fulltext_language, query_languages}'
curl -s localhost:3000/health | jq '{status, config_warnings, degraded}'
```

Create a namespace after the switch and store a memory in each language: an unknown `lang` is `400`;
`config_warnings` must not list `DAKERA_FULLTEXT_LANGUAGE` / `DAKERA_QUERY_LANG` as values that were not honoured.

---

## Multimodal

Off by default. A server that sets none of the variables answers the routes with `501
FEATURE_DISABLED` (naming the variable), loads none of the models and behaves as before. Switches use
the common boolean grammar (`1/true/yes/on`, `0/false/no/off`).

### Attachments (`DAKERA_ATTACHMENTS`)

Files an agent's memories can point at, stored content-addressed per namespace (`attachment_ref` =
`sha256:<hex>`), counted by namespace quotas, carried by backups, replicated in a cluster, and
removed with the last memory that references them.

| Route | Scope | Answer |
|---|---|---|
| `POST /v1/namespaces/{ns}/attachments` | write | upload (multipart `file`, or a raw body with its `Content-Type`): `201` with `attachment_ref`; `200` when the bytes were already there; `413` over `DAKERA_ATTACHMENT_MAX_BYTES` (default 26214400) |
| `GET /v1/namespaces/{ns}/attachments` | read | list (no bytes) |
| `GET /v1/namespaces/{ns}/attachments/{ref}` | read | the bytes (`ETag` = the hash) |
| `DELETE /v1/namespaces/{ns}/attachments/{ref}` | write | `204`; `409` while a memory references it |

A memory references one with `"attachment_ref": "sha256:..."` on `POST /v1/memory/store`; the
attachment must be in the memory's own namespace `_dakera_agent_{agent_id}` (otherwise `404`).
The request-body limit `DAKERA_MAX_BODY_SIZE` (the compose files set 500 MB, the server default is 10
MiB) also applies, so raise both when you raise `DAKERA_ATTACHMENT_MAX_BYTES`.

### Speech to text

`POST /v1/namespaces/{ns}/attachments/{ref}/transcribe` with `{"agent_id": "...", "tags": [...]}` answers
`202` with a `job_id`, `memory_id` and `status_url`; the job transcribes the audio and stores the
transcript as a memory through the normal write path (embedded, full-text indexed, `attachment_ref`
set). `whisper-tiny.en` is English-only; WAV only (PCM 8/16/24/32-bit or float, any channels and rate;
anything else is `400` before a job exists). Status: `GET .../transcribe/{job_id}` (or `/ops/jobs/{id}`
with an admin key): `Pending`, `Running` (2 % while the model loads, 5-80 % across 30-second windows,
85 % embedding, 95 % storing), `Completed`, `Failed` (with `error: {status, code}`). **Jobs live in
memory**: after a restart the status route answers `404 JOB_NOT_FOUND`; the memory a finished job
stored is kept (look it up by the `memory_id` of the `202`). On SIGTERM the stores already running are
waited for up to 15 s; a job still transcribing stores nothing and must be started again
(`terminationGracePeriodSeconds` is 30 in the manifests for this).

### Image and page indexing, visual recall (`DAKERA_VISION`)

`POST /v1/namespaces/{ns}/attachments/{ref}/index` (needs `DAKERA_ATTACHMENTS` too) embeds a PNG
(at most 64 megapixels) with `colmodernvbert` as a patch multivector plus a pooled primary vector, both
from the pixels; the optional `content` caption only feeds the full-text index. With
`DAKERA_SCORING_STRATEGY=late-interaction`, recall embeds the query with the visual model's text side
and searches the pages. Measured on ViDoRe nDCG@5: TabFQuAD 0.643, Shift Project 0.7705 (the other
ViDoRe sets are not measured yet).

- **A store of its own.** The agent namespaces then hold 128-d page vectors, not text embeddings. Use a
  deployment (data root **and bucket**) dedicated to it; never turn `DAKERA_VISION` on over an
  existing text store. `docker-compose.vision.yml` and `k8s-features/overlays/vision` do this.
- **One page at a time** (the model has one page session), in submission order, about **10.7 s per
  page on CPU** (release notes; 13.8 s measured for one 1000 x 1300 px page, 17 tiles, on 4 cores).
  Submit a whole document at once: up to 2 500 jobs wait; past that a new job is `503` +
  `Retry-After`. A page waits up to 30 s for each page ahead of it. At shutdown the queued pages end
  without running: start them again.
- Late interaction is refused (`501`) under `DAKERA_TIERED=1`, so the vision overlay sets
  `DAKERA_TIERED=0`.

### Memory is admitted, not assumed

Every media job (and every GLiNER entity-extraction pass on the store path) reserves its estimated peak
working memory before it decodes anything (audio: the samples + 128 MiB per 30-second window; image:
the raster and decode buffers read from its header + 128 MiB per tile, at most a 4x4 grid plus a
thumbnail) against the memory limit (the cgroup limit, else physical memory) x
`DAKERA_MEM_HIGH_WATER_FRACTION` (default 0.85). A job that does not fit waits up to **10 s** for running
jobs to give memory back, then the request is answered **`503` with `Retry-After`**. There is no fixed
job cap. `DAKERA_MEM_BACKPRESSURE=0` turns the refusals off (reservations are still counted).

- A model's **first load converts** its graph to the ORT format once; the conversion reserves its peak
  from the same budget (GLiNER ~780 MB, the visual model ~1 GB). If it never fits (a small memory
  limit), the job is `503` naming `dakera models pull <model>` and `/health` lists `speech_to_text`,
  `vision_model` or `entity_extraction` under `degraded`. Pull the model **outside the server** (init
  container, `models pull`, a derived image) or raise the memory limit.
- **Idle models leave memory**: whisper, the visual model and GLiNER unload after
  `DAKERA_HNSW_CACHE_TTI_SECS` (3600 s) and earlier under memory pressure; the next use reloads them from
  the local cache.
- **CPU is shared.** Every model draws from one pool of compute tokens (one per core): query-side work
  (query embeddings, rerank, visual queries) is served first; bulk work (document embeddings,
  transcription, image pages, entity extraction) uses at most `cores - 1` at once, so a transcription
  never takes the whole machine from recall.
- SDK clients time out at 30 s; the server answers its queueing `503` within 20 s so that the `503` +
  `Retry-After` arrives first: retry on `503`.

**Sizing the multimodal box.** The measured configuration is a **4-core / 8 GiB** container with every
model loaded: **530 MiB anonymous memory**, no out-of-memory kill; an image page peaked **+1.9 GiB at 17
tiles** (TRACKER V6). The compose files give the container 12G / 4 CPUs; the K8s multimodal and vision
components and the Helm blocks raise the base 4Gi limit to 8Gi. A small box can run everything, one
heavy job at a time: jobs that do not fit wait or get a `503`.

**Verify.**

```bash
curl -s localhost:3000/v1/capabilities -H "X-API-Key: $KEY" | jq '{attachments, vision, lane: .scoring.late_interaction.lane}'
curl -s localhost:3000/health | jq .degraded        # speech_to_text / vision_model when a model cannot load
```

---

## Multi-vector records

`DAKERA_RECORDS=1` turns on `POST /v1/namespaces/{ns}/records` and `GET /v1/namespaces/{ns}/records/{id}`: a
record is **one** vector (the primary, which is indexed and searched) plus up to **8** named extra
representations (`kind`: `dense`, `token_multivector`, `patch_multivector`; `store_as`: `f32`
(default, lossless), `f16`, `i8`), stored beside it by every backend and carried by snapshots,
export/import and replication. A read returns a manifest (name, kind, model, shape, dtype, bytes) and
the vectors only with `?include_vectors=true`.

| Variable | Default | Effect |
|---|---|---|
| `DAKERA_RECORD_MAX_VECTORS` | 4096 | Vectors in one representation; over it `413` |
| `DAKERA_RECORD_MAX_BYTES` | 8388608 (8 MiB) | Packed bytes of one record's extras; over it `413` |

There is no record delete route: delete the id through the ordinary vector routes. The raw vector APIs
and `GET .../records/{id}` return an agent memory's `content` in its at-rest form (`z64:` compressed or
`$enc$v2$` sealed): read memories through the memory API. Works on an existing store.
Verify: `jq .records` on `/v1/capabilities` (`enabled`, `max_representations`, `max_vectors`, `max_bytes`).

---

## Late interaction

`DAKERA_MODEL=colbert-small` (96-d token vectors, ~34 MB, the one model with a late-interaction recipe)
with `DAKERA_SCORING_STRATEGY=late-interaction`: recall shortlists candidates by each memory's
fixed-dimensional encoding, then reranks them with MaxSim over the query's and the memories' per-token
vectors. Memories are written with `colbert` / `colbert.fde` slots next to their primary vector.

- **Why it is opt-in.** On the same LoCoMo harness, colbert-small scored below bge-large; it is better only
  on multi-hop questions (server RELEASE_NOTES, "Known limitations"). Use it where token-level matching
  matters and measure on your own data.
- **Speed.** Steady recall p50 0.10 s at 1k memories and 0.23 s at 10k. A recall right after a bulk
  ingest is served by the dense first stage while the late-interaction stage rebuilds in the
  background (it reports `late_interaction_first_stage`: `dense_while_building` on the first recall of
  the validation, `fde_exact` from the next one).
- **Constraints.** Cannot be combined with `DAKERA_TIERED=1` (`501`, naming the settings); any other
  model answers stores and recalls with `503` naming the requirement; a fresh store or a
  [migration](#switching-the-embedding-model); `dakera downgrade` refuses it.

Verify: `jq .scoring.late_interaction` (`enabled`, `model_supported`, `lane` = `text`) and
`jq .late_interaction_stats` (`reranked` > 0 once searches ran: zero with searches > 0 means MaxSim never ran).

---

## RaBitQ search mode

`DAKERA_SEARCH_MODE=rabitq` walks the HNSW graph on RaBitQ codes (an unbiased distance estimator over a
randomly rotated, quantized vector), then re-ranks the shortlist with exact float distances.
`DAKERA_RABITQ_BITS` (1 to 8, default 1; out of range is clamped with a warning; 4 is the usual quality
point) is read only in this mode. Other values of `DAKERA_SEARCH_MODE`: `hybrid` (default), `binary`,
`float`, `scalar` (alias `sq`); an unknown value runs `hybrid`.

**It saves latency, not memory.** The codes are an in-memory side table built lazily next to the float
vectors, which stay resident, and are re-encoded on the first search after a restart. Do not choose it
to shrink RAM. For memory, v0.12 already stores HNSW node vectors in f16 (see
[Performance and sizing](#performance-and-sizing)). Works on an existing store.

---

## Rerank controls

The cross-encoder reranker is on by default and is the main CPU cost of a recall. v0.12 lets you bound it.

- `DAKERA_RERANK_MAX_CANDIDATES` (server-wide, unset = the whole candidate pool) and the per-request
  `rerank_candidates` cap how many candidates the cross-encoder scores; the best by retrieval score are
  scored, the rest keep their order below. A request's value is capped by the server's. Applies to
  `/v1/memory/recall` and `/v1/memory/search`.
- Recall and search answer `rerank_report: {applied, candidates, skipped}` (`skipped`: `disabled`,
  `no_query`, `bm25_routing`, `low_confidence`, ...); recall also carries the same object as `rerank`.
- `DAKERA_RERANK_WARMUP` (default on) loads the reranker in the background at boot (the exact words `0` /
  `false` load it on the first reranked recall instead). Until it is ready, reranked recalls are served without the rerank and
  `/health` lists `reranker` under `degraded`.
- `DAKERA_RERANKER_MODEL=bge-reranker-base` selects the smaller reranker (279 MB download);
  the default `bge-reranker-v2-m3` ships in the image.

The measured gain of v0.12 itself (4 CPU / 8 GiB container, `top_k` 16): 11.5 s / 45 CPU-s down to
6.2 s / 24 CPU-s. See [Performance and sizing](#performance-and-sizing) for what that means for capacity.

---

## The model store

The image ships **`bge-large`** (embedding, INT8) and **`bge-reranker-v2-m3`** (reranker, INT8) in a
model store next to the binary (`/usr/local/share/dakera/models`, already converted). A default start
needs **no network** (`--network none` works), downloads, converts and writes nothing, works with a
read-only root filesystem, and is not affected by anything mounted at `/app/models`. Image: 783 MB
(release notes, amd64; 1.24 GB unpacked in `docker images`), ready 4.4 s after start (release notes;
4.2 s measured in the deployment validation). The `:gpu` image (NVIDIA GPU required, ~4-5 GB) ships
FP32 models for CUDA.

Everything else downloads on first use into the **model cache** (`HF_HOME`, `/app/models`, a volume):

| Model | `dakera models` name | Turned on by | Download |
|---|---|---|---|
| bge-m3, colbert-small, gte-modernbert-base, ... | `bge-m3`, `colbert-small`, ... | `DAKERA_MODEL` | 23 MB to 570 MB |
| bge-reranker-base | `bge-reranker-base` | `DAKERA_RERANKER_MODEL` | 279 MB |
| whisper-tiny.en | `whisper` | `DAKERA_ATTACHMENTS` | ~151 MB |
| colmodernvbert | `vision` | `DAKERA_VISION` | ~966 MB |
| GLiNER (entity extraction) | `gliner` | per namespace (`extract_entities` + `entity_types`) | ~782 MB |

Each non-shipped model also keeps an ORT-format copy (disk about the model's size again). Every file is
checked against a pinned SHA-256; a corrupt file is deleted and fetched again once.

```bash
docker compose run --rm dakera models list            # what is on disk, how big, what prune would free
docker compose run --rm dakera models pull bge-m3 whisper vision
docker compose run --rm dakera models prune --dry-run  # then without --dry-run; --unused too
```

`pull` takes model names, `reranker`, `whisper`, `vision`, `default` (what the image ships) or
`configured` (what this environment loads), `--dir <root>` (fill another directory with the cache's
layout) and `--bake` (fill the image's own store, for a `RUN` in a Dockerfile).

**Baked images.** Your own image with models inside, no volume, no download:

```dockerfile
FROM ghcr.io/dakera-ai/dakera:0.12.0
RUN dakera models pull --bake whisper vision
```

Rebuild it when you move to a new Dakera version (a baked model is tied to the build that baked it).

**Behind a proxy or a mirror.** The downloader reads `HTTPS_PROXY` / `HTTP_PROXY` / `ALL_PROXY` /
`NO_PROXY` (either case; chosen as curl does; CIDR in `NO_PROXY` works), `HF_ENDPOINT` (a mirror of the
Hub) and `HF_TOKEN` (sent to the Hub's own origin only). Proxy URLs: `http://`, `socks4://`,
`socks4a://`, `socks5://`, `socks5h://`; an `https://` proxy URL (TLS to the proxy), another scheme or
an IPv6 proxy address is **not supported** and fails naming the variable. The base compose files pass all
of these from `.env` (empty = unset). Put the compose service names and loopback in `NO_PROXY`
(`127.0.0.1,localhost,minio,dakera-1,dakera-2,dakera-3`) so no other traffic of the container is
sent through the proxy; the container's own health check runs `curl` against `127.0.0.1`.

**Offline and air-gapped.** The default image needs nothing. For other models, on a connected machine:

```bash
docker run --rm -v "$PWD/models:/seed" ghcr.io/dakera-ai/dakera:0.12.0 \
  models pull --dir /seed bge-m3 whisper vision
```

Copy `models/` to the air-gapped host, mount it at `/app/models` (the `dakera-models` volume), and set
`HF_HUB_OFFLINE=1` (compose: `.env`) so a missing file fails at once naming it. The embedding model,
whisper and the vision model can also be read from an operator directory
(`DAKERA_MODEL_PATH`, `DAKERA_WHISPER_MODEL_PATH`, `DAKERA_VISION_MODEL_PATH`); the files are
SHA-256-checked unless `DAKERA_MODEL_PATH_SKIP_VERIFY=1`. A v0.11 model cache may hold another upstream
revision of the reranker or GLiNER: v0.12 replaces it at first load (a download), and under
`HF_HUB_OFFLINE=1` leaves it and fails naming the file, so seed the pinned files
(`models pull --dir ... reranker gliner`).

**Several replicas, one volume** (the three HA nodes share `dakera-models`): supported. A file one replica
is downloading is waited for by the others (taken over if it stalls for two minutes), a model is
converted once, and every file is published atomically. **Upgrading the image with a persisted volume**:
nothing to do; afterwards `models prune` frees what the old version left (a v0.11 volume holds ~0.9 GB of
copies of the models the image now ships; after pruning, a rollback to v0.11.108 downloads them again).

**When is the server ready?** `GET /health/live` answers `200` as soon as the port is bound;
`GET /health/ready` is `200` once the embedding model is loaded and storage answers (`503` with the
phase and every download's progress while starting). The reranker loads in the background; whisper and the
vision model are downloaded in the background right after ready. A store into a GLiNER namespace waits up
to 10 s for the model, then gets `503` + `Retry-After`. The compose health check starts counting after
600 s; the Kubernetes startup probe covers 10 minutes.

**Disk.** Plan the model volume from what each model takes once converted (measured: the download plus
its ORT copy): `bge-m3` 1.1 GB, `whisper` 367 MB (154 MB downloaded), `colbert-small` 66 MB, `vision`
1.9 GB. With GLiNER (not measured here; ~782 MB download, about twice that converted) the four text and
media models need about 5 GB. 10 GiB leaves room for upgrades.

---

## Switching the embedding model

The store records the model (and embedding recipe) that produced its vectors. If the server starts with
a different effective model it **refuses to start** (exit 1) and names both models, because serving would
mix two embedding spaces (`bge-large` and `bge-m3` are both 1024-d). A request whose `model` differs from
the server's is `400`. Two ways:

1. **A fresh store** (new volumes and bucket / a new host): start with the new model. This is what the
   compose overlays and Kustomize components assume.
2. **Migrate** an existing store: start once with `DAKERA_ALLOW_MODEL_CHANGE=1` (acknowledges the change,
   re-embeds nothing), pull the model first (`models pull bge-m3`), then re-embed (global admin key):

   ```bash
   curl -X POST localhost:3000/admin/namespaces/migrate-dimensions -H "X-API-Key: $ADMIN" \
     -H 'Content-Type: application/json' \
     -d '{"target_dimension": 1024, "reembed_same_dimension": true}'    # bge-large -> bge-m3 (both 1024-d)
   ```

   Until it has completed for every agent namespace, recall mixes old and new vectors and
   `/v1/capabilities` reports `"reembed_pending": true`. Vectors clients upserted directly are not
   re-embedded (Dakera never had their text). Then remove `DAKERA_ALLOW_MODEL_CHANGE`. Take a backup first.
   Re-embedding cost: the server's own migration of stored memories to the document side of
   `bge-large` took about 35 minutes per 10,000 memories (one worker, recall served throughout);
   there is no measurement yet for the move to bge-m3.

`DAKERA_TIERED=1` pins the default model: with it on, `DAKERA_MODEL` is ignored. The v0.12 first start
also re-embeds, once, in the background, the memories v0.11 embedded with the query instruction (about
35 minutes per 10,000 memories on `bge-large`; progress in `/health` `embed_migration` and
`GET /admin/reembed/migration`).

---

## What can be combined

| | multilingual | multimodal (attachments, speech) | vision | records | late interaction | RaBitQ |
|---|---|---|---|---|---|---|
| **multilingual** | - | yes | **no** | yes | **no** (two models) | yes |
| **multimodal** | yes | - | yes (vision needs attachments, and sets them) | yes | yes | yes |
| **vision** | **no** | yes | - | not documented | **no** | not documented |
| **records** | yes | yes | not documented | - | not documented | yes |
| **late interaction** | **no** | yes | **no** | not documented | - | yes |
| **RaBitQ** | yes | yes | not documented | yes | yes | - |

"yes": the server's documentation names no conflict (the features sit on different axes: model, scoring,
quantization, storage); "**no**": a hard conflict (both set `DAKERA_MODEL`, or the vision lane is a store of
its own); "not documented": not stated by the server, so test it before you rely on it. A compose merge
silently lets the last file win, so do not stack the "no" pairs. Speech to text is English-only whatever
the text model. Everything here also needs `DAKERA_TIERED=0` when it involves a model change or late
interaction; the quick-start's `DAKERA_TIERED=1` stays only for stacks without them.

---

## Security

- **gRPC requires an API key.** v0.11 had no authentication on the gRPC port. With `DAKERA_AUTH_ENABLED` on
  (the default), every RPC except `Health` needs a key in the call metadata (`x-api-key: <key>` or
  `authorization: Bearer <key>`), authorized per namespace like its REST twin (`UNAUTHENTICATED` /
  `PERMISSION_DENIED`). gRPC also draws on the server-wide rate limit (`DAKERA_RATE_LIMIT_RPS` / `_BURST`),
  is bounded by `DAKERA_REQUEST_TIMEOUT` and, for `Query`, by `query_timeout_ms`, fails `UNAVAILABLE` in
  maintenance mode and is audited. The service has seven RPCs over raw vectors and **no memory API**; `top_k`
  must be 1 to 10 000 (proto3 sends `0` when unset: `INVALID_ARGUMENT`). The HA compose file defaults `DAKERA_AUTH_ENABLED` to `false`: set it `true` in
  `.env.ha` for anything but a local trial, or gRPC stays open.
- **Scoped keys.** A key pinned to namespaces no longer reaches node-wide routes (`/admin/*` bar four
  per-namespace routes, `/ops/*`, `/v1/analytics/*`, `/v1/audit*`, `/v1/kpis`, ...): it gets `403`. Backup
  download, upload and restore need a global `super_admin` key (was `admin`). Check backup tooling and
  namespace-scoped admin keys before upgrading.
- **Encryption at rest** (`DAKERA_ENCRYPTION_KEY`: 64 hex characters or a passphrase of 8 or more; the same value on
  every node). Values are sealed with AES-256-GCM bound to their record (`$enc$v2$`). Keys live in a
  replicated **keyring** (reserved namespace `_dakera_keyring`, wrapped under a master derived from
  `DAKERA_ENCRYPTION_KEY`); old keys are kept so reads never break and old backups restore.
  Rotate one namespace at a time or all of them (admin scope):

  ```bash
  curl -X POST localhost:3000/admin/encryption/rotate-key -H "X-API-Key: $ADMIN" \
    -H 'Content-Type: application/json' -d '{"namespace": "_dakera_agent_alice"}'   # or {} for everything
  curl localhost:3000/admin/encryption/status -H "X-API-Key: $ADMIN"
  ```

  The server generates the new key; `DAKERA_ENCRYPTION_KEY` stays as it is. The re-seal runs in the
  background on every node (the call waits up to `wait_secs`, default 10). Existing `$enc$v1$` values are
  re-sealed in the background after the upgrade. To change the master itself, rotate with `new_key` set to
  the new value first, then set `DAKERA_ENCRYPTION_KEY` to it on every node and restart. Old ciphertext
  stays in WAL segments, snapshots, SST files until compaction, S3 object versions and backups until
  rewritten; it is all still ciphertext. Metrics: `dakera_encryption_*`; alert
  `DakeraEncryptionValuesUnreadable`.
- **The cluster secret.** `DAKERA_CLUSTER_SECRET` (at least 16 characters, identical on every node) authenticates
  every node-to-node request under `/internal/*` and HMACs gossip packets. A **fresh** cluster install
  without it, or without a stable `DAKERA_CLUSTER_NODE_ID`, is refused. An upgraded node without them
  starts as v0.11 did, `cluster_auth` degraded in `/health`. During a mixed v0.11 / v0.12 period leave it
  unset until every node runs v0.12. Keep it in `.env.ha` or a Secret, never in a ConfigMap.
- **With authentication off**, only loopback web origins may call the server and a state-changing request from
  another origin is `403 CROSS_ORIGIN_REQUEST_REFUSED`. Secrets are kept out of logs, the audit log and
  `/health`. Knowledge-graph edges are private to their agent. Imports, extractor responses and graph
  searches are bounded.
- **Telemetry**, when on: lifecycle events and a 6-hourly heartbeat; the machine's hostname is sent and
  PostHog keeps the connecting IP. Opt out with `DAKERA_TELEMETRY=0` or `DO_NOT_TRACK=1`.

---

## Reliability

- **RocksDB hot tier.** With tiered storage (`DAKERA_TIERED_STORAGE=true`, needs `DAKERA_STORAGE=s3`) the hot
  tier is RocksDB by default (`{root}/hot`) and every write, with the cold-flush journal mark that owes it
  to S3, is fsynced before it is acknowledged (`DAKERA_ROCKSDB_SYNC`, default `true`; one fsync covers a
  group of concurrent requests). Expect more write latency on slow disks. `DAKERA_HOT_TIER=memory` keeps
  the v0.11 in-memory tier. The copies owed to S3 survive a restart and an S3 outage: stores keep
  succeeding, recall is served from hot and warm, a circuit breaker opens after 3 consecutive cold
  failures (`dakera_tiered_cold_circuit_state`), and the backlog is bounded (past 1 000 000 owed writes
  new writes get `503`).
- **The write-ahead log** (`DAKERA_WAL`, default on; `DAKERA_WAL_SYNC` `everywrite` by default): write and
  fsync errors are returned, a checkpoint rotates and truncates the active segment, and concurrent writes
  to one agent share one fsync (group commit). `DAKERA_WAL_SYNC=periodic:0` refuses the boot.
- **Cluster replication** is versioned and merges instead of overwriting. Every record carries a version, every
  delete leaves a **tombstone** kept `DAKERA_CLUSTER_TOMBSTONE_RETENTION_SECS` (7 days; set it above the
  longest node outage you tolerate without wiping that node), changes a peer did not acknowledge wait in a
  **durable outbox** (`DAKERA_CLUSTER_OUTBOX_DIR`, default `{root}/cluster-outbox`, bounded at 64 MiB), and each
  node merges with the leader every 5 minutes. Keep node clocks NTP-synchronised well inside
  `DAKERA_CLUSTER_MAX_CLOCK_DRIFT_MS` (60 s). `DAKERA_ELECTION_LEASE_MS` (15000) drives every cluster timing.
- **One bucket per node.** Cluster nodes must not share one S3 bucket as their store (every node keeps a
  heartbeat marker in its bucket: a fresh shared bucket is refused, an old one is `shared_store` degraded).
  `docker-compose.ha.yml` gives each node its own (`dakera`, `dakera-2`, `dakera-3`) and one data root and
  volume set per node. One server per data root: a server locks it (`.dakera.lock`), so on Kubernetes the
  Deployment is `Recreate` and not autoscaled.
- **Health.** The port binds before the models load; `/health/live` and `/health/ready` are the probes.
  `/health` lists `degraded` components and `config_warnings`. `dakera --check-config` checks a
  configuration without starting (`0` would start, `78` would refuse).
- **Backups** now apply `encrypt` and `compression` (zstd), carry attachments and graph edges, and a stored
  schedule actually runs. Restore does not pause serving: restore in a maintenance window.
  **Going back**: `dakera downgrade` converts a stopped deployment to v0.11.108, but refuses one that uses
  `bge-m3`, `colbert-small` / late interaction or the visual lane.

---

## Observability

**Shipped in `monitoring/` and updated to what v0.12 emits.** Before this change the repository's alert
rules and dashboards read metrics v0.12 does not emit (`dakera_cache_*`, `dakera_l2_cache_*`,
`dakera_decay_*`, `dakera_total_vectors`, `dakera_cluster_nodes_total`, `dakera_memory_count`, ...), so those
alerts never fired and those panels stayed empty, and `dakera_replica_count` is a constant 1 in v0.12 (the
replica alerts fired on every node). Now:

| File | What |
|---|---|
| `monitoring/dakera.rules.yml` | The server's own alert rules (`prometheus/alerts/dakera.rules.yml`), loaded next to the older file. Group `dakera-signals`: config warnings, degraded components, WAL replay dropped entries, memory read failures, Redis cache failures, held cluster changes, WAL write failures, failed model loads, failed backups, unreadable encrypted values. Group `dakera-service`: down, 5xx ratio, 503 shedding, memory-budget refusals, cold-tier circuit and backlog, RocksDB write stop, dropped cluster changes, storage write stalls, clock skew, corrupt records |
| `monitoring/alerting-rules.yml` | The deploy-side rules (latency, memory, MinIO, Prometheus). Memory reads the server's `dakera_process_resident_bytes` against the 12 GiB compose limit (the earlier `process_resident_memory_bytes` / cAdvisor expression read series nothing here exports); the server exports no CPU metric, so there is no CPU alert. MinIO latency reads `minio_s3_requests_ttfb_seconds_distribution`. The cache, decay and replica alerts are removed; `DakeraDown` lives in `dakera.rules.yml` |
| `monitoring/alerting-rules.ha.yml`, `monitoring/prometheus.ha.yml` | HA: scrape dakera-1..3 as job `dakera` and alert on `count(up{job="dakera"} == 1) < 3` |
| `monitoring/grafana/.../dakera-overview.json` | The server's v0.12 dashboard: health and configuration, models and memory admission, recall / ingest stage latencies, derived caches and late interaction, tiered storage, cluster replication, encryption, RocksDB |
| `k8s/monitoring/prometheus.yaml` | Now loads `dakera.rules.yml` |

New metrics worth knowing: `dakera_model_loads_total{model,outcome}`,
`dakera_model_load_duration_seconds{model}`, `dakera_memory_budget_reserved_bytes`,
`dakera_component_degraded{component}`, `dakera_config_warnings`, `dakera_backups_total{outcome}`,
`dakera_wal_write_failures_total`, `dakera_storage_write_stalls_total`, `dakera_memory_read_failures_total`,
`dakera_late_interaction_first_stage_total{stage}`, `dakera_reembed_migration_*`, `dakera_rocksdb_*`,
`dakera_encryption_*`, the `dakera_cluster_*` set (outbox, tombstones, clock skew, reconciliation),
`dakera_tiered_*`. Refusals (`429`, `401` / `403`, `408`, `413`, `503`, unmatched paths) now appear in
`dakera_http_requests_total`; expect those statuses in dashboards after the upgrade. About **25 Prometheus
series per active agent** (server `docs/v0.12/scale-footprint.md`, derived; one agent that stored,
recalled and forgot measured 13 series families, 35 exposition lines): many thousands of agents make a
large scrape.

**Checked against a running 0.12.0 server.** Every rule file passes `promtool check rules`; Prometheus
(the `monitoring` profile) loads them all with health `ok` and scrapes `dakera`, `minio` and `prometheus`
(the MinIO target needs `MINIO_PROMETHEUS_AUTH_TYPE=public`, which the compose files and `k8s/minio` now
set: without it the target is down with 403 and `MinIODown` fires). Every metric the dashboards and rules
read is emitted by the server, but many only once their event has happened, so an idle server does not
list them in `/metrics` and their panels stay empty until then: the failure counters (`*_failures_total`,
`dakera_wal_write_failures_total`, `dakera_storage_*`, `dakera_tiered_cold_*_failures_total`), the cluster
series (only in cluster mode), the encryption series (only with `DAKERA_ENCRYPTION_KEY`), the Redis series
(only with `DAKERA_REDIS_URL`), `dakera_memory_budget_reserved_bytes` / `dakera_memory_reclaims_total`
(first media job), `dakera_late_interaction_cold_fallbacks_total`, `dakera_component_degraded` (first
degraded component), `dakera_errors_total` (first refused request), `dakera_namespace_vectors` (first
namespace listing) and `dakera_ingest_stage_duration_seconds` (first batch store).

Per feature, watch:

| Feature | Signals |
|---|---|
| Multimodal / vision / GLiNER | `/health` `degraded` (`speech_to_text`, `vision_model`, `entity_extraction`); `dakera_model_loads_total{outcome="failed"}`; `dakera_errors_total{type=~"memory_budget\|memory_backpressure"}`; `503` ratio (`DakeraShedding`) |
| Late interaction | `late_interaction_stats` on `/v1/capabilities`; `dakera_late_interaction_total`, `dakera_late_interaction_first_stage_total` |
| Model change | `reembed_pending` on `/v1/capabilities`; `dakera_reembed_migration_remaining`; `embed_migration` in `/health` |
| Encryption rotation | `dakera_encryption_reseal_running`, `dakera_encryption_values_unreadable`; `GET /admin/encryption/status` |
| Cluster | `dakera_cluster_sync_outbox_entries`, `_held_entries`, `dakera_cluster_clock_ahead_ms`; `GET /admin/cluster/status` |

---

## Performance and sizing

**Measured in the release notes** (the baseline is v0.11.108; "container" is 4 CPU / 8 GiB):

| What | Before | v0.12.0 |
|---|---|---|
| Recall with reranking, `top_k` 16 | 11.5 s, 45 CPU-s | 6.2 s, 24 CPU-s |
| Two concurrent reranked recalls | 19.6 s | 11.2 s |
| Container memory after reranking | 4.98 GB | 0.65 GB, flat across `top_k` 1-32 |
| Reranker load | 4.6 s | 0.6 s |
| HNSW memory per 1024-d vector (BEIR Quora 50k) | 4.81 KB | 2.76 KB (-43 %), same recall@10 (0.998) |
| HNSW search p50 / p95 (Quora 50k) | 1.07 / 1.44 ms | 0.87 / 1.17 ms |
| LoCoMo paired (3 conversations, 382 questions): recall p50 / ingest / memory | 3.8 s / 124 s / 2.4 GB | 1.8 s / 46 s / 0.97 GB |
| Docker image | - | 783 MB; ready 4.4 s after start |
| Every model loaded (I8) | - | 530 MiB anonymous memory |

An expired memory no longer forces an index rebuild (about 2 minutes at 50k memories before); ANN indexes are
saved and reloaded instead of rebuilt; concurrent writes share the log's fsync.

**Sizing guidance derived from them** (arithmetic on the numbers above, not new measurements):

- **Memory, base.** Plan **about 1 GB** for the server with the default models and a small corpus
  (0.65 GB measured after reranking, 0.97 GB for the paired LoCoMo run). The compose files' 12G limit and
  the chart's 4Gi leave room. On a limit as small as ~2 GiB with entity extraction (GLiNER), the model's
  one-time conversion (~780 MB reserved from the memory budget) may never fit: run `dakera models pull gliner`
  once, outside the server (the `models-cache` component and `dakera.models.pull` do this).
- **Memory, per vector.** The HNSW node vectors cost **2.76 KB per 1024-d vector** (`bge-large`, `bge-m3`):
  1 million vectors is about 2.8 GB for the graph's vectors alone, before the stored records, the full-text
  index and the caches. Measure RSS (`dakera_process_resident_bytes`) at 10 % of your corpus and extrapolate
  linearly; do not size from the 0.97 GB figure, which is three conversations.
- **CPU and rerank.** Reranking is CPU-bound: two concurrent recalls took 11.2 s, about twice one (5.6 s each).
  At `top_k` 16 a reranked recall costs **24 CPU-s**, so a 4-core container sustains roughly 1 reranked
  recall per 6 s (4 / 24 = 0.17 per second); capacity scales with cores. To serve more recalls on the same
  cores, lower `DAKERA_RERANK_MAX_CANDIDATES` (the cost is per candidate: an earlier spike scored 150 pairs in
  20.7 CPU-s, about 0.14 CPU-s per candidate, so capping at 50 candidates is estimated at about 7 CPU-s;
  an estimate, measure it on your data) or lower `top_k`. Recall queueing is derived from the core count (at most two
  recalls per core, at least four, run at once; the rest queue and answer `503` + `Retry-After` after 20 s).
- **Multimodal box.** 4 cores and 8 GiB is the measured configuration for every model; the image peak is
  +1.9 GiB at 17 tiles and a page reserves that working memory from the budget (limit x 0.85) before it
  starts: when it does not fit, it is answered `503` + `Retry-After`, so leave that headroom. Pages cost about
  10.7 s each, one at a time: 100 pages take about 18 minutes (derived). Transcription and indexing use at most `cores - 1` of the CPU.
- **Disk.** Model volume: see [The model store](#the-model-store) (10 GiB for every optional model). The data
  volume holds the WAL, the RocksDB hot tier, the warm tier, the knowledge graph (`graph.db`, a node-local file
  even on S3) and attachments: size it above your corpus, and keep it on persistent storage (the compose files and
  manifests default to 20Gi for the Kubernetes PVC).
- **First recall after a restart that follows a write** costs about 13 s at 10k memories while the ANN index is rebuilt
  (planned for 0.12.1); without a write the saved index loads. Schedule restarts accordingly.

## What is not measured

Stated by the release notes as pending: the 50k capacity re-run (E8), the embedder benchmark (E7), the
load sweep (F6) and durable writes per second (K20). No v0.12 ingest rate, no per-memory RAM figure at scale,
no bge-m3 versus bge-large quality or latency number, and no ViDoRe set other than TabFQuAD and Shift Project.

## Measured in the deployment validation

The compose files, the Kustomize manifests and the Helm chart were run against the v0.12.0 server
(an image built with the release Dockerfile from the release commit's CI binary; `server_version`
`0.12.0`) on one x86-64 host (8 cores; each container capped: 3 GiB / 4 CPUs for a single node,
1.5 GiB per HA node, 3.5 GiB for vision), with the Hugging Face Hub reachable over a fast link. Times are
from `docker compose up` (or pod creation) on fresh volumes; download times depend on your link.

| What | Measured |
|---|---|
| Single node, default | `/health/live` 200 after 0.5 s, `/health/ready` 200 after 4.2 s; 373 MiB at idle, 787 MiB RSS after a store / recall / backup round |
| Store, stop, `down` (volumes kept), `up` | the memory is recalled after the restart; graceful stop took 0.5 s |
| `--check-config` | exit 0 on the stack's configuration; exit 78 with a misspelled `DAKERA_*` name (it names the closest real one) |
| `downgrade` | stopped stack with data: exit 0, `completed: true`; while the server runs: exit 78, nothing changed; an empty store: exit 78, "no data found" |
| HA (3 nodes) | every node ready, leader elected about 30 s after start (HTTP vote), a write on any node visible on the two others within 0.1 s (all 6 pairs); about 450 MiB per node |
| Multilingual (`bge-m3`) | ready 12 s after start, download included; recall with `lang` (de, fr, es, it) and across languages; 1.29 GiB peak |
| Records | `POST .../records` 200, `GET .../records/{id}` returns the manifest, `?include_vectors=true` the vectors; `501 FEATURE_DISABLED` without the overlay |
| RaBitQ | `search_mode` `rabitq`; recall returns the expected memory |
| Attachments + speech to text | whisper fetched and converted 4 s after start (background); a 3.8 s WAV transcribed in 1.5 s and recalled; 749 MiB peak |
| Late interaction (`colbert-small`) | ready 3.2 s after start, download included; `late_interaction_first_stage` reported; 643 MiB peak |
| Vision (`colmodernvbert`) | fetched and converted 38 s after start (background); one page indexed in 13.8 s and recalled; 2.43 GiB peak (during the conversion) |
| Monitoring | rules load with health `ok`; targets `dakera`, `minio`, `prometheus` up (HA: the three nodes) |
| Kubernetes (`k8s/`, kind) | server Ready 34 s after `kubectl apply -k` (images present); store / recall; `overlays/multilingual` Ready in 27 s with the `models pull` init container (11 s for bge-m3); check-config Job "the configuration is valid" |

---

## Verifying a running server

```bash
KEY=...                                   # any key with Read scope for /v1/capabilities
curl -s localhost:3000/health/ready       # 200 once the embedding model is loaded, 503 + progress while starting
curl -s localhost:3000/health | jq        # status, degraded[], config_warnings[], embed_migration
curl -s localhost:3000/v1/capabilities -H "X-API-Key: $KEY" | jq '{server_version, default_model, search_mode,
  fulltext_language, query_languages, records, scoring, attachments, vision, reembed_pending}'
curl -s localhost:3000/metrics | grep -E 'dakera_(config_warnings|component_degraded|model_loads_total)'
```

Run `dakera --check-config` with the new image, your environment and your data volume before a rollout:
`docker compose run --rm --no-deps dakera --check-config`. Every `DAKERA_*` name in this repository's files
is in the server's registry (`known_env.rs`); an unknown name is reported at startup with the closest real name.
