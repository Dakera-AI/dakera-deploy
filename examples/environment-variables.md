# Environment Variable Reference

Reference for the Dakera server environment variables used by the v0.12.0 compose files and manifests (v0.11: the `release/0.11` branch). The v0.12 features, their variables and constraints are in [docs/features-v0.12.md](../docs/features-v0.12.md). Compose passes to the container only the variables its `environment:` lists: a name in `.env` that no file passes never reaches the server (the base files pass the ones below and in `.env.example`; the overlays pass their feature's). The authoritative list is the server's [env-vars.md](https://github.com/Dakera-AI/dakera/blob/main/docs/v0.12/env-vars.md); a name the server does not read is reported at startup (`dakera --check-config`). Set these in `docker/.env` (Docker Compose) or in your Kubernetes Secret/ConfigMap.

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
| `DAKERA_ALLOW_MODEL_CHANGE` | — | Set `1` for ONE start to acknowledge that the store was embedded by another model (then re-embed with `POST /admin/namespaces/migrate-dimensions` and remove it) |
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
| `DAKERA_FULLTEXT_LANGUAGE` | `en` (overlay: `multilingual`) | BM25 analyzer of new namespace indexes: an ISO 639-1 code or English name, or `zh`/`ja`/`ko`/`th`/`none`/`multilingual` (no stemming). Existing namespaces: `POST /admin/fulltext/reindex` with `rebuild` |
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
| `DASHBOARD_IMAGE` | `ghcr.io/dakera-ai/dakera-dashboard:0.4.0` | Dashboard image |
| `DAKERA_SESSION_TTL_HOURS` | `12` | Dashboard 0.4.0: longest an operator sign-in lasts (idle sessions end after 2 h) |

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
