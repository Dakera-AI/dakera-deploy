# Environment Variable Reference

Reference for the Dakera server environment variables used by the v0.12 compose files and manifests (Dakera v0.12.1) (v0.11: the `release/0.11` branch). The v0.12 features, their variables and constraints are in [docs/features-v0.12.md](../docs/features-v0.12.md). Compose passes to the container only the variables its `environment:` lists: a name in `.env` that no file passes never reaches the server (the base files pass the ones below and in `.env.example`; the overlays pass their feature's). The authoritative list is the server's [env-vars.md](https://github.com/Dakera-AI/dakera/blob/main/docs/v0.12/env-vars.md); a name the server does not read is reported at startup (`dakera --check-config`). Set these in `docker/.env` (Docker Compose) or in your Kubernetes Secret/ConfigMap.

## Required (Production)

| Variable | Description |
|----------|-------------|
| `DAKERA_ROOT_API_KEY` | Root API key. Generate with `openssl rand -hex 32`. The default compose refuses to start without this. |
| `MINIO_ROOT_USER` | MinIO admin username. Change from `minioadmin` in production. |
| `MINIO_ROOT_PASSWORD` | MinIO admin password. Change from `minioadmin` in production. |

## Core

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_HOST` | `0.0.0.0` | Bind address |
| `DAKERA_PORT` | `3000` | REST API port |
| `DAKERA_GRPC_PORT` | `50051` | gRPC API port |
| `DAKERA_STORAGE` | `memory` | Storage backend: `memory` (ephemeral), `filesystem` or `s3` (persistent) |
| `DAKERA_STORAGE_PATH` | `/data` | Data root. WAL, knowledge graph, filesystem backend, hot tier (`{root}/hot`) and warm tier (`{root}/cache/warm`) derive from it; mount the data volume here |
| `RUST_LOG` | `info` | Log verbosity (`error`, `warn`, `info`, `debug`, `trace`) |
| `DAKERA_AUTH_ENABLED` | `true` (prod) / `false` (local) | Require API key authentication |

## S3 / MinIO Storage

Required when `DAKERA_STORAGE=s3`.

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_S3_ENDPOINT` | — | S3-compatible endpoint (e.g. `http://minio:9000`) |
| `DAKERA_S3_BUCKET` | `dakera` | Storage bucket name |
| `DAKERA_S3_REGION` | `us-east-1` | S3 region |
| `AWS_ACCESS_KEY_ID` | — | S3 access key (`DAKERA_S3_ACCESS_KEY` is not read) |
| `AWS_SECRET_ACCESS_KEY` | — | S3 secret key (`DAKERA_S3_SECRET_KEY` is not read) |

## Cache

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_L1_CACHE_SIZE` | `100000` (vectors) | Hot-tier budget of tiered storage; no effect without `DAKERA_TIERED_STORAGE`. With a unit suffix (`512MB`, `1g`) it is bytes; a bare number below 10 million is a vector count (10 million or more: bytes, with a warning). The compose files use `512MB`, the ConfigMap `1GB` |
| `DAKERA_DISK_CACHE_DIR` | — | Enables the L2 on-disk read cache (v0.11's `DAKERA_L2_CACHE_PATH` is no longer read) |
| `DAKERA_CACHE_DIR` | `{root}/cache/warm` | Warm-tier directory (tiered storage only) |

## Tiered Storage

Automatically moves data between hot (L1), warm (L2/RocksDB), and cold (L3/S3) tiers.

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_TIERED_STORAGE` | `false` | Enable tiered storage (needs `DAKERA_STORAGE=s3`; the compose files and manifests turn it on). The hot tier is RocksDB by default in v0.12 (`DAKERA_HOT_TIER=memory` keeps the v0.11 tier; `DAKERA_ROCKSDB_SYNC=false` skips the per-write fsync) |
| `DAKERA_HOT_TO_WARM_SECS` | `3600` | Seconds before hot → warm tier transition |
| `DAKERA_WARM_TO_COLD_SECS` | `86400` | Seconds before warm → cold tier transition |
| `DAKERA_AUTO_TIER` | `true` | Automatic tier transitions |
| `DAKERA_TIER_CHECK_INTERVAL_SECS` | `300` | Interval between tier sweep checks |

## Cluster (HA Mode)

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_CLUSTER_MODE` | `false` | Enable cluster mode |
| `DAKERA_CLUSTER_ROLE` | — | Node role: `primary` or `replica` |
| `DAKERA_CLUSTER_SEEDS` | — | Comma-separated seed nodes (`host:port,host:port`) |
| `DAKERA_CLUSTER_SECRET` | — | **Required in cluster mode**: shared secret of node-to-node routes and gossip, >= 16 characters, identical on every node. Keep it in a Secret / `.env.ha`, never in a ConfigMap |
| `DAKERA_CLUSTER_NODE_ID` | generated once | Stable node identifier (`DAKERA_NODE_ID` is its legacy alias) |
| `DAKERA_GOSSIP_PORT` | `7946` | Gossip protocol port |
| `DAKERA_GOSSIP_BIND` | `0.0.0.0:7946` | Gossip bind address |
| `DAKERA_API_ADVERTISE` | — | Advertised API URL for the node |
| `DAKERA_REDIS_URL` | — | Redis URL for the L1.5 cache, rate-limit counters and SSE pub/sub (v0.11's `DAKERA_CACHE_REDIS_URL` is no longer read). Not set by the compose files: one Redis shared by the nodes of a v0.12.0 cluster kept replicated writes from being applied |

## Models

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_MODEL` | `bge-large` | Embedding model. `bge-large` and the reranker ship in the image; any other model downloads into the model cache (`/app/models`) on first use or via `dakera models pull` |
| `DAKERA_ALLOW_MODEL_CHANGE` | — | From 0.12.1 only needed where the background re-embed cannot run (`DAKERA_TIERED=1`, late-interaction scoring, the visual lane, a recorded model this build does not know): set `1` for ONE start to acknowledge that the store was embedded by another model, then re-embed with `POST /admin/namespaces/migrate-dimensions` and remove it. Otherwise a changed `DAKERA_MODEL` re-embeds the store in the background |
| `DAKERA_TIERED` | `false` (compose: `1`) | The tiered **embedding** engine (not tiered storage): it always embeds with `bge-large`, ignores `DAKERA_MODEL` and refuses late interaction. Identical on every node sharing a store |
| `DAKERA_MAX_SEQ_LENGTH` | model maximum (`bge-m3`: 2048) | Truncation length in tokens for text models |
| `HF_TOKEN` | — | Hugging Face token for model downloads (optional) |
| `HF_ENDPOINT` | `https://huggingface.co` | A Hugging Face mirror or internal proxy of the Hub |
| `HF_HUB_OFFLINE` | — | `1`: never download; a missing file fails at once naming it (air-gapped) |
| `HTTPS_PROXY` / `HTTP_PROXY` / `ALL_PROXY` / `NO_PROXY` | — | Proxy for model downloads (`http://` or `socks4/4a/5/5h://`; **not** `https://`). Include `127.0.0.1,localhost,minio` in `NO_PROXY` |
| `DAKERA_MODEL_PATH` / `DAKERA_WHISPER_MODEL_PATH` / `DAKERA_VISION_MODEL_PATH` | — | Operator directories holding the model files (offline); SHA-256-checked unless `DAKERA_MODEL_PATH_SKIP_VERIFY=1` |

## Multilingual (docker-compose.multilingual.yml)

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_FULLTEXT_LANGUAGE` | `en` (overlay: `multilingual`) | BM25 analyzer: an ISO 639-1 code or English name, or `zh`/`ja`/`ko`/`th`/`none`/`multilingual` (no stemming). Stored with each index; from 0.12.1 an existing index built with another analyzer is re-analysed in the background at the next start |
| `DAKERA_FULLTEXT_CJK_BIGRAMS` | follows the language (off for `en`) | Character-bigram indexing of unsegmented scripts |
| `DAKERA_QUERY_LANG` | `en` (overlay: `auto`) | `en`, `de`, `fr`, `es`, `it`, `pt`, `nl` or `auto`: query routing patterns, temporal expressions, date extraction. Per request: `lang` |

## Attachments, speech to text, vision (docker-compose.multimodal.yml, docker-compose.vision.yml)

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_ATTACHMENTS` | off | Attachment routes and speech to text; `501 FEATURE_DISABLED` when off |
| `DAKERA_ATTACHMENT_MAX_BYTES` | `26214400` | Largest upload; over it `413` |
| `DAKERA_WHISPER_MODEL` | `whisper-base` | Speech-to-text model (WAV only): `whisper-base` (multilingual, language auto-detected, default and recommended), `whisper-tiny.en` (English, lightest), `whisper-base.en` (English), `whisper-tiny` (multilingual, lightest) or `whisper-small` (multilingual, quality) |
| `DAKERA_VISION` | off | Image/page indexing and the visual recall lane (needs `DAKERA_ATTACHMENTS`; use a dedicated data root and bucket) |
| `DAKERA_VISION_MODEL` | `colmodernvbert` | The visual model |
| `DAKERA_MEM_HIGH_WATER_FRACTION` | `0.85` | Media jobs reserve memory against limit x this; waits up to 10 s, then `503` + `Retry-After` |
| `DAKERA_MEM_BACKPRESSURE` | on | `0` turns the memory refusals off |
| `DAKERA_HNSW_CACHE_TTI_SECS` | `3600` | Idle time after which whisper, the visual model and GLiNER are unloaded (also the ANN / full-text index idle horizon) |

## Records, late interaction, RaBitQ, rerank

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_RECORDS` | off | Record routes: one vector + named extra representations (`docker-compose.records.yml`) |
| `DAKERA_RECORD_MAX_VECTORS` / `DAKERA_RECORD_MAX_BYTES` | `4096` / `8388608` | Limits of one record's extras; over = `413` |
| `DAKERA_SCORING_STRATEGY` | `single-vector` | `late-interaction` (with `DAKERA_MODEL=colbert-small`, `DAKERA_TIERED=0`: `docker-compose.late-interaction.yml`) |
| `DAKERA_SEARCH_MODE` | `hybrid` | `hybrid`, `binary`, `float`, `scalar` (alias `sq`), `rabitq` (`docker-compose.rabitq.yml`; saves latency, not memory) |
| `DAKERA_RABITQ_BITS` | `1` | 1-8 bits per dimension, only in `rabitq` mode |
| `DAKERA_RERANK_MAX_CANDIDATES` | unset (whole pool) | Most candidates any recall sends to the cross-encoder; request field `rerank_candidates` is capped by it |
| `DAKERA_RERANK_WARMUP` | on | Load the reranker at boot (the exact words `0`/`false` load it on first use) |
| `DAKERA_RERANKER_MODEL` | `bge-reranker-v2-m3` | `bge-reranker-base` selects the smaller reranker |

## Security

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_ENCRYPTION_KEY` | — | AES-256-GCM at rest: 64 hex characters or a passphrase of at least 8; identical on every node. Rotation uses a keyring (`POST /admin/encryption/rotate-key`) and needs no change to this value |
| `DAKERA_CLUSTER_SECRET` | — | Cluster mode: >= 16 characters, identical on every node |
| `DAKERA_GRPC_ENABLED` | `true` | gRPC listener; v0.12 gRPC needs an API key in the call metadata when authentication is on |
| `DAKERA_CONFIG_LENIENT` | — | `1`: start on a fresh install although a value cannot be honoured or a `DAKERA_*` name is unknown (listed in `/health` `config_warnings`) |

## Request Limits

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_MAX_BODY_SIZE` | `10485760` (10 MiB) | Max request body size in bytes. The compose files and the ConfigMap set `524288000` (500 MB) |
| `DAKERA_REQUEST_TIMEOUT` | `300` | Request timeout in seconds, the outer ceiling. `docker-compose.yml` sets 600, `docker-compose.ha.yml` and the ConfigMap 120 |
| `DAKERA_RATE_LIMIT_RPS` / `DAKERA_RATE_LIMIT_BURST` / `DAKERA_RATE_LIMIT_ENABLED` | `100` / `50` / `true` | Server-wide rate limit (REST and gRPC). v0.11's `RATE_LIMIT_RPS` / `RATE_LIMIT_BURST` still work, deprecated |
| `DAKERA_HTTP_HEADER_READ_TIMEOUT_SECS` | `30` | Server v0.12.3. Seconds a client has to send a complete HTTP/1 request head on the REST port, counted from when the server waits for one (a new or an idle keep-alive connection, which is then closed); `[1, 86400]`. A proxy that keeps idle upstream connections longer (ingress-nginx 60 s, Traefik 90 s by default; `docker-compose.ha.yml`'s Traefik is set to 25 s) must be set below it, or this raised above the proxy's. From 0.12.3 it also closes an idle HTTP/2 connection that sends no request |
| `DAKERA_MAX_CONNECTIONS` | `10000` | Server 0.12.3. Most open REST connections, `[1, 1000000]`; one over the cap is closed at once. Keep it below the file-descriptor limit |
| `DAKERA_SHUTDOWN_DRAIN_SECS` | `8` | Server 0.12.3. Longest REST drain at shutdown, `[0, 3600]` (SSE streams end at the signal). Plus up to 15 s for media jobs: keep the sum below `stop_grace_period` / `terminationGracePeriodSeconds` (30 s here) |
| `DAKERA_ALLOWED_HOSTS` | — | Server 0.12.3, read only with `DAKERA_AUTH_ENABLED=false`: Host names accepted besides localhost, `*.localhost`, IPs and single-label names (comma list, `*` = any); others get `421 HOST_NOT_ALLOWED` (DNS-rebinding guard; `/health*`, `/internal/*` exempt). A stack without auth reached by a dotted name (Kubernetes service FQDN, public name) must set it |

## Recall (server v0.12.3)

The compose files pass these only when they are set (an older image reports a name it does not know).

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_NEIGHBORHOOD_MODE` | `inline` | Neighbourhood context of a recall that names no `neighborhood_mode`: `inline` (after the `top_k` results, marked `retrieval: "neighborhood"`), `separate` (in `context_memories`; `memories` holds at most `top_k`) or `off` |
| `DAKERA_NEIGHBORHOOD_EVENT_TIME` | off | Neighbourhood window on event time instead of ingest time |
| `DAKERA_RECALL_RANK_DEPTH` | `10` | Ranking depth floor `[1, 1000]`: the first `k` of a `top_k=k` recall equal the first `k` of a `top_k=10` recall |
| `DAKERA_RECALL_COLLAPSE_DERIVED` | off | One result per source memory (sentence sub-memories collapsed; `matched_text`, `matched_ids`) |
| `DAKERA_RECALL_EXCLUDE_SUMMARIES` | off | Session summaries left out unless a request sets `include_summaries: true` |
| `DAKERA_RECALL_SESSION_CAP` | `0` | At most N results of one session in the head of list / aggregation recalls (`0` = no cap) |
| `DAKERA_SENTENCE_DECOMP` | on | `0`: no sentence sub-memories derived on any write path |
| `DAKERA_SUPERSEDES_EVENT_TIME` | on | Supersedes edges ordered by the memories' event dates when both have one |

## Document import (server v0.12.3)

On by default. The compose files pass these only when set. Server guide: `docs/documents.md` in the server repository.

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_DOCUMENTS` | on | The document routes (`POST /v1/memory/documents`, `.../attachments/{ref}/document`, jobs, list, delete); off: `501 FEATURE_DISABLED` |
| `DAKERA_DOCUMENT_MAX_BYTES` | `26214400` (25 MiB) | Largest source document (`413`). A proxy in front must accept bodies this large (ingress-nginx: `proxy-body-size`, 1 MB by default; `k8s/ingress.yaml` sets 500 MB) |
| `DAKERA_DOCUMENT_MAX_TEXT_BYTES` | `20971520` (20 MiB) | Most extracted text (`413`) |
| `DAKERA_DOCUMENT_MAX_CHUNKS` | `5000` | Most chunks per document (`413`, before any write) |
| `DAKERA_DOCUMENT_CHUNK_TOKENS` | `400` | Default chunk budget, `[32, 8192]`, clamped to the model's cap |
| `DAKERA_DOCUMENT_CHUNK_OVERLAP_TOKENS` | `50` | Default overlap, `[0, 1024]` |
| `DAKERA_DOCUMENT_EXTRACT_TIMEOUT_SECS` | `60` | Wall clock of one PDF / DOCX extraction (`504 EXTRACTION_TIMEOUT` in the job) |
| `DAKERA_DOCUMENT_EXTRACT_MEMORY_MB` | `1024` | Address-space limit of one `dakera extract-text` child |
| `DAKERA_DOCUMENT_EXTRACT_CONCURRENCY` | `2` | Extractions at once. The container's memory limit must hold the server plus CONCURRENCY x MEMORY_MB (2 GB by default): 12G in `docker-compose.yml`, 4Gi in `k8s/` (lower the concurrency or raise the limit for PDF-heavy imports) |

## Docker Compose Port Overrides

The default and HA compose files expose different ports to allow co-deployment on the same host.

### Default Profile (`docker-compose.yml`)

| Variable | Default | Service |
|----------|---------|---------|
| `DAKERA_PORT` | `3000` | Dakera REST API |
| `DAKERA_GRPC_PORT` | `50051` | Dakera gRPC |
| `MINIO_API_PORT` | `9000` | MinIO S3 API |
| `MINIO_CONSOLE_PORT` | `9001` | MinIO web console |
| `PROMETHEUS_PORT` | `9090` | Prometheus (monitoring profile) |
| `GRAFANA_PORT` | `3003` | Grafana (monitoring profile) |
| `DASHBOARD_PORT` | `3002` | Dashboard UI (dashboard profile) |
| `DASHBOARD_IMAGE` | `ghcr.io/dakera-ai/dakera-dashboard:0.5.2` | Dashboard image |
| `DAKERA_SESSION_TTL_HOURS` | `12` | Dashboard 0.4.0+: longest an operator sign-in lasts (idle sessions end after 2 h) |
| `DAKERA_TRUSTED_PROXIES` | — | Dashboard 0.5.2: addresses / CIDRs (comma or space separated) of the reverse proxies whose `X-Forwarded-For` names the client (nginx `real_ip`; the sign-in throttle counts that address) |

### HA Profile (`docker-compose.ha.yml`)

All HA ports use the `HA_` prefix to avoid conflicts with the default profile.

| Variable | Default | Service |
|----------|---------|---------|
| `HA_LB_HTTP_PORT` | `3100` | Traefik → Dakera REST API |
| `HA_LB_GRPC_PORT` | `50151` | Traefik → Dakera gRPC |
| `HA_TRAEFIK_PORT` | `8080` | Traefik dashboard |
| `HA_MINIO_API_PORT` | `9100` | MinIO S3 API |
| `HA_MINIO_CONSOLE_PORT` | `9101` | MinIO web console |
| `HA_DASHBOARD_PORT` | `3202` | Dashboard UI |
| `HA_PROMETHEUS_PORT` | `9190` | Prometheus (monitoring profile) |
| `HA_GRAFANA_PORT` | `3203` | Grafana (monitoring profile) |
| `HA_JAEGER_UI_PORT` | `16787` | Jaeger UI (monitoring profile) |
