# Environment Variable Reference

Reference for the Dakera server environment variables used by the v0.12.0 compose files and manifests (v0.11: the `release/0.11` branch). The authoritative list is the server's [env-vars.md](https://github.com/Dakera-AI/dakera/blob/main/docs/v0.12/env-vars.md); a name the server does not read is reported at startup (`dakera --check-config`). Set these in `docker/.env` (Docker Compose) or in your Kubernetes Secret/ConfigMap.

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
| `DAKERA_L1_CACHE_SIZE` | `536870912` (512MB) | In-memory L1 cache size in bytes |
| `DAKERA_DISK_CACHE_DIR` | — | Enables the L2 on-disk read cache (v0.11's `DAKERA_L2_CACHE_PATH` is no longer read) |
| `DAKERA_CACHE_DIR` | `{root}/cache/warm` | Warm-tier directory (tiered storage only) |

## Tiered Storage

Automatically moves data between hot (L1), warm (L2/RocksDB), and cold (L3/S3) tiers.

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_TIERED_STORAGE` | `false` | Enable tiered storage |
| `DAKERA_HOT_TO_WARM_SECS` | `3600` | Seconds before hot → warm tier transition |
| `DAKERA_WARM_TO_COLD_SECS` | `86400` | Seconds before warm → cold tier transition |
| `DAKERA_AUTO_TIER` | `false` | Enable automatic tier transitions |
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
| `DAKERA_REDIS_URL` | — | Redis URL for the distributed cache, rate-limit counters and SSE pub/sub (v0.11's `DAKERA_CACHE_REDIS_URL` is no longer read) |

## Models

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_MODEL` | `bge-large` | Embedding model. `bge-large` and the reranker ship in the image; any other model downloads into the model cache (`/app/models`) on first use or via `dakera models pull` |
| `DAKERA_ALLOW_MODEL_CHANGE` | — | Set `1` for ONE start to acknowledge that the store was embedded by another model (then re-embed with `POST /admin/namespaces/migrate-dimensions` and remove it) |
| `HF_TOKEN` | — | Hugging Face token for model downloads (optional) |

## Request Limits

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_MAX_BODY_SIZE` | `524288000` | Max request body size in bytes (500 MB) |
| `DAKERA_REQUEST_TIMEOUT` | `120` | Request timeout in seconds |

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

### HA Profile (`docker-compose.ha.yml`)

All HA ports use the `HA_` prefix to avoid conflicts with the default profile.

| Variable | Default | Service |
|----------|---------|---------|
| `HA_LB_HTTP_PORT` | `3100` | Traefik → Dakera REST API |
| `HA_LB_GRPC_PORT` | `50151` | Traefik → Dakera gRPC |
| `HA_TRAEFIK_PORT` | `8080` | Traefik dashboard |
| `HA_MINIO_API_PORT` | `9100` | MinIO S3 API |
| `HA_MINIO_CONSOLE_PORT` | `9101` | MinIO web console |
| `HA_REDIS_PORT` | `6480` | Redis |
| `HA_DASHBOARD_PORT` | `3202` | Dashboard UI |
| `HA_PROMETHEUS_PORT` | `9190` | Prometheus (monitoring profile) |
| `HA_GRAFANA_PORT` | `3203` | Grafana (monitoring profile) |
| `HA_JAEGER_UI_PORT` | `16787` | Jaeger UI (monitoring profile) |
