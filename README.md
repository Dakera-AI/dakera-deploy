<p align="center">
  <a href="https://dakera.ai">
    <img src="assets/logo.png" alt="Dakera AI" width="120" />
  </a>
</p>

<h1 align="center">Dakera Deployment</h1>

<p align="center">
  <strong>Deploy AI agent memory anywhere — Docker, Kubernetes, or Helm.</strong><br>
  Production-ready infrastructure for the Dakera memory platform.
</p>

<p align="center">
  <a href="https://dakera.ai"><img src="https://img.shields.io/badge/dakera.ai-website-22c55e?style=for-the-badge" alt="Website" /></a>
  <a href="https://dakera.ai/docs"><img src="https://img.shields.io/badge/docs-dakera.ai%2Fdocs-3b82f6?style=for-the-badge" alt="Docs" /></a>
  <a href="https://dakera.ai/benchmark"><img src="https://img.shields.io/badge/benchmark-88.2%25_LoCoMo-D4A843?style=for-the-badge" alt="Benchmark" /></a>
  <a href="https://dakera.ai/playground"><img src="https://img.shields.io/badge/playground-try%20it-ff6b35?style=for-the-badge" alt="Playground" /></a>
</p>

<p align="center">
  <a href="https://github.com/Dakera-AI/dakera-deploy/actions/workflows/ci.yml"><img src="https://github.com/Dakera-AI/dakera-deploy/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="https://github.com/Dakera-AI/dakera-deploy/releases"><img src="https://img.shields.io/github/v/release/Dakera-AI/dakera-deploy" alt="Release" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT" /></a>
  <a href="https://docs.docker.com/"><img src="https://img.shields.io/badge/Docker-Ready-2496ED" alt="Docker" /></a>
  <a href="https://kubernetes.io/"><img src="https://img.shields.io/badge/Kubernetes-Ready-326CE5" alt="Kubernetes" /></a>
  <a href="https://github.com/dakera-ai/dakera-helm"><img src="https://img.shields.io/github/v/release/Dakera-AI/dakera-helm?label=Helm&color=0F1689" alt="Helm" /></a>
</p>

---

## Versions

| | Dakera server | Where |
|---|---|---|
| **Latest (this branch, `main`)** | **v0.12.0** | `main`: compose files, Kubernetes manifests and guides in this repo target v0.12.0 |
| Previous | v0.11.x (last: v0.11.108) | the [`release/0.11`](https://github.com/Dakera-AI/dakera-deploy/tree/release/0.11) branch, kept unchanged |

**On v0.11?** Use the [`release/0.11`](https://github.com/Dakera-AI/dakera-deploy/tree/release/0.11)
branch (`git clone -b release/0.11 https://github.com/Dakera-AI/dakera-deploy`): everything in it
keeps working as before. Its Helm counterpart is the `0.11.x` chart on the
[`release/0.11`](https://github.com/Dakera-AI/dakera-helm/tree/release/0.11) branch of dakera-helm.

**Moving to v0.12.0?** Follow [Upgrading from v0.11](#upgrading-from-v011-to-v0120). Going back is
supported ([Rolling back to v0.11](#rolling-back-to-v011)).

---

## Why Dakera?

Dakera is the **agent-native memory platform** — purpose-built for AI agents that need persistent, session-aware, cross-agent memory. A single self-hosted Rust binary gives you vector search, hybrid retrieval (BM25 + HNSW), knowledge graphs, session management, and built-in embeddings. No external dependencies. Your data stays on your infrastructure.

**88.2% on the [LoCoMo benchmark](https://dakera.ai/benchmark)** — 1,540 questions testing long-conversation memory across temporal reasoning, multi-hop retrieval, and event ordering. This is the highest score for a self-hosted memory system.

---

## Used For

| Use Case | What Dakera Provides |
|----------|---------------------|
| **Multi-agent pipelines** | Shared cross-agent memory, session isolation per agent, importance-ranked recall |
| **RAG with long-term context** | Hybrid BM25 + vector search over agent history; knowledge graph for entity relationships |
| **Code review / DevOps agents** | Persistent memory of past decisions, PR patterns, and repo-specific context across runs |
| **Customer support bots** | Per-user session history, conversation continuity, semantic recall of past resolutions |
| **Personal AI assistants** | Long-term preference and context storage, temporal decay, knowledge graph connections |
| **Research / data agents** | Cross-session fact accumulation, importance-weighted memory, structured entity extraction |

All use cases deploy identically — the profiles below configure storage backend and scale.

---

## Zero to Running in 5 Minutes

No config required. Dakera runs in-memory by default — great for local testing and development.

```bash
git clone https://github.com/dakera-ai/dakera-deploy
cd dakera-deploy/docker
docker compose -f docker-compose.local.yml up -d
```

That's it. Dakera is now running at **http://localhost:3000**.

```bash
# Verify it's healthy
curl http://localhost:3000/health
```

To persist data across restarts, use the [Development profile](#development-with-minio-storage) (MinIO-backed) or the [Default profile](#default-full-single-node) (production-grade).

For IDE-integrated development, see the [VS Code / Cursor Devcontainer](#vs-code--cursor-devcontainer-recommended) below.

## VS Code / Cursor Devcontainer (Recommended)

The fastest way to get a full Dakera dev environment — no local installs required.

**Prerequisites:** [Docker](https://docs.docker.com/get-started/get-docker/) + [VS Code](https://code.visualstudio.com/) with the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers), or [Cursor](https://www.cursor.com/).

```bash
git clone https://github.com/dakera-ai/dakera-deploy
# Open the folder in VS Code / Cursor, then:
# "Reopen in Container" when prompted (or Ctrl+Shift+P → Dev Containers: Reopen in Container)
```

That's it. The container build will:
1. Pull the Dakera server image and MinIO
2. Initialize the storage bucket
3. Install Python, Node, Go, and Rust SDKs
4. Open VS Code/Cursor with Rust Analyzer, REST Client, and other extensions pre-configured

**Service endpoints (available on localhost):**

| Service | URL | Notes |
|---------|-----|-------|
| Dakera REST API | http://localhost:3000 | Main API |
| Dakera gRPC | localhost:50051 | gRPC endpoint |
| MinIO Console | http://localhost:9001 | `minioadmin` / `minioadmin` |
| MinIO S3 API | http://localhost:9000 | S3-compatible |

Auth is disabled for local dev. See [docker-compose deployment](#default-full-single-node) for production auth setup.

---

## Deployment Profiles

| Profile | Description | Use Case |
|---------|-------------|----------|
| **devcontainer** | VS Code/Cursor one-click setup | SDK development, local testing |
| **local** | Single instance, in-memory storage | Quick testing, no dependencies |
| **dev** | MinIO storage backend for development | Local development with persistence |
| **default** | Dakera + MinIO with full configuration | Staging / single-node production |
| **ha** | 3-node cluster with Traefik load balancer | Production high availability |
| **monitoring** | Prometheus + Grafana observability stack | Metrics and dashboards |
| **kubernetes** | kubectl manifests or Helm chart | Production (cloud-native) |

## Quick Start

### Local (Single Instance, In-Memory)

Fastest way to get Dakera running. No external dependencies.

```bash
cd docker
docker compose -f docker-compose.local.yml up -d
```

- REST API: http://localhost:3000
- gRPC API: localhost:50051
- Health check: http://localhost:3000/health

### Development (With MinIO Storage)

Includes MinIO for S3-compatible persistent storage.

```bash
cd docker
docker compose -f docker-compose.dev.yml up -d
```

- MinIO Console: http://localhost:9001 (minioadmin/minioadmin)

### Default (Full Single-Node)

Production-grade single-node deployment with MinIO, caching, and health checks.

> **Version pinning**: The default Dakera image tag is pinned to v0.12.0 (v0.11: `release/0.11`).
> To run a specific version, set `DAKERA_IMAGE` and `DASHBOARD_IMAGE` in your `.env`:
> ```bash
> DAKERA_IMAGE=ghcr.io/dakera-ai/dakera:0.12.0
> DASHBOARD_IMAGE=ghcr.io/dakera-ai/dakera-dashboard:0.3.29
> ```
> Pinning to explicit versions prevents unexpected upgrades in production.

**First-time setup — configure credentials before starting:**

```bash
cd docker
cp .env.example .env
# Edit .env — set DAKERA_ROOT_API_KEY and MinIO credentials
# Generate a strong key: openssl rand -hex 32
```

```bash
docker compose up -d
```

- REST API: http://localhost:3000
- gRPC API: localhost:50051
- MinIO Console: http://localhost:9001

### High Availability (3-Node Cluster)

Production HA deployment with Traefik load balancer, 3 Dakera nodes, gossip-based clustering, and MinIO storage (one bucket per node).

```bash
cd docker
docker compose -f docker-compose.ha.yml up -d
```

- REST API (load balanced): http://localhost:3100
- gRPC API (load balanced): localhost:50151
- Traefik Dashboard: http://localhost:8080
- MinIO Console: http://localhost:9101
- Cluster status: http://localhost:3100/admin/cluster/status

Set `DAKERA_CLUSTER_SECRET` (>= 16 characters, `openssl rand -hex 32`) in `.env.ha` first; the file
refuses to start without it. Each node uses its own MinIO bucket.

### Monitoring (Prometheus + Grafana)

Add observability to any deployment profile.

```bash
# Start Dakera with monitoring (standalone monitoring compose)
cd docker
docker compose up -d

cd ..
docker compose -f docker/docker-compose.yml -f monitoring/docker-compose.yml up -d
```

Or use the monitoring profile in the HA stack:

```bash
cd docker
docker compose -f docker-compose.ha.yml --profile monitoring up -d
```

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3003 (admin/dakera)

Pre-configured dashboards include request rates, latency percentiles, cache hit ratios, storage metrics, cluster health, and memory decay metrics (v0.8.0+).

### Kubernetes

Production deployment via kubectl or Helm. See [Kubernetes Deployment](#kubernetes-deployment) below.

## Client Tools

Once Dakera is running, connect with the official CLI and MCP server:

```bash
# dk CLI — inspect memory, run queries, manage namespaces
brew install dakera-ai/tap/dk            # macOS
# or: curl -fsSL https://dakera-ai.github.io/apt-repo/install.sh | sh   # Linux
dk store --namespace myagent "User prefers concise replies"
dk recall --namespace myagent "communication style"

# dakera-mcp — expose Dakera tools to AI agents via Model Context Protocol
npx @dakera-ai/dakera-mcp               # zero-install, latest version
# or: brew install dakera-ai/tap/dakera-mcp
# Add to Claude Desktop: { "mcpServers": { "dakera": { "command": "npx", "args": ["@dakera-ai/dakera-mcp"] } } }
```

See [dakera-cli](https://github.com/dakera-ai/dakera-cli) and [dakera-mcp](https://github.com/dakera-ai/dakera-mcp) for full documentation.

## Upgrading from v0.11 to v0.12.0

An unchanged v0.11.108 deployment upgrades in place: stop v0.11, start v0.12.0 on the same data and
the same environment. It starts, keeps its data and answers as before, except for the defects v0.12
fixes on purpose. The full guide is the server's
[docs/v0.12/UPGRADE.md](https://github.com/Dakera-AI/dakera/blob/main/docs/v0.12/UPGRADE.md)
(release notes: [RELEASE_NOTES.md](https://github.com/Dakera-AI/dakera/blob/main/docs/v0.12/RELEASE_NOTES.md)).
Summary for the files in this repo:

1. **Back up** (`POST /admin/backups`).
2. **Check the configuration with the new image**, against your environment and data volumes. It
   lists every warning the first start will give, starts nothing, and exits `0` (would start) or `78`
   (would refuse):
   ```bash
   cd docker
   docker compose run --rm --no-deps dakera --check-config      # single node
   docker compose -f docker-compose.ha.yml run --rm --no-deps dakera-1 --check-config   # HA
   ```
3. **Take the new files** (`git pull` on `main`) and review what changed for your setup:
   - image `ghcr.io/dakera-ai/dakera:0.12.0`;
   - `DAKERA_L2_CACHE_PATH` is gone (v0.12 reads no such name; an upgraded deployment warns, a fresh
     install refuses): the data root is `DAKERA_STORAGE_PATH` (`/data`), and every local path derives
     from it. The compose files mount the data volume there and keep your old volumes where the
     tiers expect them (`/data/cache` for the warm tier, `/data/hot` for the hot tier);
   - `DAKERA_CACHE_REDIS_URL` is gone (use `DAKERA_REDIS_URL`), `DAKERA_NODE_ID` is now
     `DAKERA_CLUSTER_NODE_ID` (the old name is still honoured as an alias),
     `DAKERA_S3_ACCESS_KEY`/`DAKERA_S3_SECRET_KEY` are not read (use
     `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`), `DAKERA_LOG_LEVEL` is not read (use `RUST_LOG`);
   - health checks read `/health/ready` with a 10-minute start period (the port answers while models
     load; Kubernetes uses `/health/live` for liveness and `/health/ready` for readiness);
   - a **model volume** (`dakera-models` at `/app/models`): the image ships bge-large and the reranker
     itself; any other model downloads there on first use. A model volume kept from v0.11 can be
     freed with `docker compose run --rm dakera models prune` once you are staying on v0.12;
   - **clusters** (`docker-compose.ha.yml`): set `DAKERA_CLUSTER_SECRET` (>= 16 characters, the same
     on every node; the file refuses to start without it). Each node now has its **own bucket**
     (`dakera`, `dakera-2`, `dakera-3`); nodes sharing one bucket are refused on a fresh install.
     `dakera-1` keeps `dakera`; `dakera-2`/`dakera-3` fill from their peers at start. During a mixed
     v0.11/v0.12 period (rolling upgrade) leave the secret unset until every node runs v0.12.0.
4. **Things to know before the first start**: gRPC clients need an API key when authentication is on;
   keys pinned to namespaces lose node-wide routes; namespace quotas are now enforced; a stored,
   enabled backup schedule starts running; clients that cut on `smart_score` should re-check their
   threshold. Details: the server UPGRADE.md, "Before you upgrade".
5. **Start v0.12.0**: `docker compose pull && docker compose up -d` (Kubernetes: `kubectl apply -k k8s/`).
   Watch `GET /health` (`config_warnings`, `embed_migration`).

## Rolling back to v0.11

Going back from v0.12.0 to v0.11.108 is supported (every v0.11 embedding model, encrypted or not).
`dakera downgrade` converts the data back, and must run as a one-off job **after** the server has
stopped (it refuses, exit 78 with nothing changed, while a server runs on the data):

```bash
cd docker
docker compose stop dakera-watchdog dakera
docker compose run --rm dakera downgrade        # JSON report on stdout; exit 0 = data is v0.11.108's
# then start v0.11.108 with the v0.11 files (git checkout release/0.11):
DAKERA_IMAGE=ghcr.io/dakera-ai/dakera:0.11.108 docker compose up -d
```

- Exit `0`: done. Exit `1`: not yet (do not start v0.11; fix the cause and rerun). Exit `78`: refused.
- Kubernetes: `kubectl apply -f k8s/dakera/downgrade-job.yaml` after scaling the Deployment to 0.
- Docker run: `docker run --rm <same env and volumes> ghcr.io/dakera-ai/dakera:0.12.0 downgrade`.
- Clusters: roll back the whole cluster, not one node (HA recipe in the header of
  `docker/docker-compose.ha.yml`).
- Air-gapped, after `dakera models prune`: re-seed the model volume first (server UPGRADE.md, "Going back to v0.11").

## Deployment Guides

Step-by-step guides in the [`examples/`](examples/) directory:

- **[Quickstart](examples/quickstart.md)** — Store and recall your first memory in 5 minutes
- **[REST API Integration Guide](examples/api-notes.md)** — Building a client directly against the API: auth & scopes, conventions, the full memory lifecycle (store/recall/update/forget), sessions, the consolidation family, scoring, error/retry handling, and a worked example
- **[Environment Variables](examples/environment-variables.md)** — Complete reference for all configuration options
- **[Production Checklist](examples/production-checklist.md)** — Security, storage, HA, and monitoring checklist
- **[Backup & Restore](examples/backup-restore.md)** — MinIO backup procedures and disaster recovery

## Directory Structure

```
dakera-deploy/
├── .devcontainer/                   # VS Code / Cursor devcontainer
│   ├── devcontainer.json            # Container config (extensions, ports, env)
│   └── docker-compose.yml           # Dakera + MinIO dev services
├── docker/                          # Docker deployment configs
│   ├── Dockerfile                   # Production multi-stage build
│   ├── Dockerfile.dev               # Dev build with fast incremental compilation
│   ├── Dockerfile.local             # Lightweight build from pre-built binary
│   ├── docker-compose.yml           # Default: Dakera + MinIO
│   ├── docker-compose.dev.yml       # Dev: MinIO only (run Dakera locally)
│   ├── docker-compose.local.yml     # Local: single instance, in-memory
│   ├── docker-compose.ha.yml        # HA: 3-node cluster + Traefik LB
│   └── traefik-dynamic.yml          # Traefik routing and load balancer config
├── k8s/                             # Kubernetes manifests (production)
│   ├── namespace.yaml               # dakera namespace
│   ├── configmap.yaml               # Non-secret server configuration
│   ├── secret.example.yaml          # Secret template (never commit secrets)
│   ├── dakera/                      # Dakera server
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── hpa.yaml                 # Horizontal Pod Autoscaler (not applied by default in v0.12)
│   │   ├── check-config-job.yaml    # One-off: pre-upgrade `dakera --check-config`
│   │   └── downgrade-job.yaml       # One-off: rollback `dakera downgrade`
│   ├── dashboard/                   # Dashboard UI
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   ├── mcp/                         # MCP server (AI agent memory tools)
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   ├── minio/                       # MinIO (use native S3 in cloud)
│   │   ├── statefulset.yaml
│   │   └── service.yaml
│   ├── monitoring/                  # Prometheus + Grafana
│   │   ├── prometheus.yaml
│   │   └── grafana.yaml
│   ├── ingress.yaml                 # Nginx ingress (edit hostnames)
│   └── kustomization.yaml           # kubectl apply -k k8s/
├── monitoring/                      # Observability stack
│   ├── docker-compose.yml           # Standalone monitoring compose
│   ├── prometheus.yml               # Prometheus scrape configuration
│   └── grafana/                     # Grafana provisioning
│       └── provisioning/
│           ├── datasources/
│           │   └── datasources.yml  # Prometheus + Jaeger datasources
│           └── dashboards/
│               ├── dashboards.yml   # Dashboard auto-provisioning config
│               └── json/
│                   └── dakera-overview.json  # Overview + decay dashboards
├── examples/                        # Deployment guides and references
│   ├── quickstart.md                # Zero-to-running tutorial
│   ├── environment-variables.md     # Complete env var reference
│   ├── production-checklist.md      # Pre-production checklist
│   └── backup-restore.md           # Backup and restore procedures
├── LICENSE
├── CHANGELOG.md
└── README.md
```

## Environment Variables

### Core Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_HOST` | `0.0.0.0` | Bind address for the server |
| `DAKERA_PORT` | `3000` | REST API port |
| `DAKERA_GRPC_PORT` | `50051` | gRPC API port |
| `DAKERA_STORAGE` | `memory` | Storage backend (`memory`, `filesystem`, `s3`) |
| `DAKERA_STORAGE_PATH` | `/data` | Data root: write-ahead log, knowledge graph, filesystem backend, hot and warm tiers all derive from it |
| `RUST_LOG` | `info` | Log verbosity level |
| `DAKERA_TELEMETRY` | `enabled` | Anonymous operational telemetry. Set to `0`/`off` to disable (see [Telemetry](#telemetry)) |

### Telemetry

Dakera sends **anonymous operational telemetry** by default — engine version, OS family, and deployment type — approximately once per uptime interval, to help us understand which platforms to support. **Your memory contents, agent outputs, and personal data are never transmitted**, and there is no license check against a remote server.

To disable it, set either of:

```bash
DAKERA_TELEMETRY=off   # or 0 / false / no
DO_NOT_TRACK=1         # honored as an unconditional opt-out
```

Fully air-gapped operation is supported. Inspect the exact payload before it is sent with `DAKERA_TELEMETRY_DEBUG=1`.

### S3/MinIO Storage

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_S3_ENDPOINT` | - | S3-compatible endpoint URL |
| `DAKERA_S3_BUCKET` | `dakera` | Storage bucket name |
| `DAKERA_S3_REGION` | `us-east-1` | S3 region |
| `AWS_ACCESS_KEY_ID` | - | S3 access key (there is no `DAKERA_S3_ACCESS_KEY`) |
| `AWS_SECRET_ACCESS_KEY` | - | S3 secret key (there is no `DAKERA_S3_SECRET_KEY`) |

### Cache Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_L1_CACHE_SIZE` | `1073741824` (1GB) | In-memory L1 cache size in bytes |
| `DAKERA_DISK_CACHE_DIR` | - | Enables the L2 on-disk read cache (replaces v0.11's ignored `DAKERA_L2_CACHE_PATH`) |
| `DAKERA_CACHE_DIR` | `{root}/cache/warm` | The warm tier's directory (tiered storage only) |

### Models

The image ships `bge-large` and the reranker and loads them in seconds with no network. Any other
model (`DAKERA_MODEL=bge-m3`, whisper, vision, GLiNER) downloads on first use into the model cache
(`/app/models`, the `dakera-models` volume). Pre-pull / air-gapped:
`docker compose run --rm dakera models pull <model>`; inspect with `models list`; free space with
`models prune`. See the server's [models-and-docker.md](https://github.com/Dakera-AI/dakera/blob/main/docs/models-and-docker.md).

### Cluster (HA Mode)

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_CLUSTER_MODE` | `false` | Enable cluster mode |
| `DAKERA_CLUSTER_ROLE` | - | Node role (`primary`, `replica`) |
| `DAKERA_CLUSTER_SEEDS` | - | Comma-separated seed nodes (`host:port`) |
| `DAKERA_CLUSTER_SECRET` | - | Shared secret of the node-to-node routes and gossip: **required** in cluster mode, >= 16 characters, identical on every node |
| `DAKERA_CLUSTER_NODE_ID` | generated once | Stable node identifier (`DAKERA_NODE_ID` is its legacy alias) |
| `DAKERA_GOSSIP_PORT` | `7946` | Gossip protocol port |
| `DAKERA_GOSSIP_BIND` | `0.0.0.0:7946` | Gossip bind address |
| `DAKERA_API_ADVERTISE` | - | Advertised API URL for the node |

### Tiered Storage

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_TIERED_STORAGE` | `false` | Enable L1→L2→L3 tiered storage |
| `DAKERA_HOT_TO_WARM_SECS` | `3600` | Seconds before hot data moves to warm (RocksDB) |
| `DAKERA_WARM_TO_COLD_SECS` | `86400` | Seconds before warm data moves to cold (S3) |
| `DAKERA_AUTO_TIER` | `false` | Automatic tier promotion/demotion |
| `DAKERA_TIER_CHECK_INTERVAL_SECS` | `300` | Interval for tier check sweep |

### Request Limits

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_MAX_BODY_SIZE` | `524288000` | Max request body size in bytes (500MB) |
| `DAKERA_REQUEST_TIMEOUT` | `120` | Request timeout in seconds |

### Redis (HA Mode)

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_REDIS_URL` | - | Redis URL for the distributed cache, rate-limit counters and SSE fan-out (replaces `DAKERA_CACHE_REDIS_URL`, which v0.12 no longer reads) |

### Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_AUTH_ENABLED` | `true` | Enable API authentication (default on; server refuses to start if enabled with no keys configured) |
| `DAKERA_ROOT_API_KEY` | - | Root API key (**required** in production compose) |
| `DAKERA_ENCRYPTION_KEY` | - | AES-256-GCM key for at-rest memory encryption (32-byte hex) |

### gRPC

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_GRPC_ENABLED` | `true` | Enable the gRPC endpoint |

## HA Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │              Client Applications            │
                    └──────────────────┬──────────────────────────┘
                                       │
                              ┌────────▼────────┐
                              │   Traefik LB    │
                              │  :3100 (HTTP)   │
                              │  :50151 (gRPC)  │
                              │  :8080 (Admin)  │
                              └───┬────┬────┬───┘
                                  │    │    │
                    ┌─────────────┼────┼────┼─────────────┐
                    │             │    │    │              │
              ┌─────▼─────┐ ┌────▼────▼┐ ┌▼──────────┐   │
              │ Dakera-1  │ │ Dakera-2 │ │ Dakera-3  │   │
              │ (primary) │ │ (replica)│ │ (replica) │   │
              │  :3000    │ │  :3000   │ │  :3000    │   │
              │  :50051   │ │  :50051  │ │  :50051   │   │
              │  :7946    │ │  :7946   │ │  :7946    │   │
              └─────┬─────┘ └────┬─────┘ └─────┬─────┘   │
                    │            │              │          │
                    │     Gossip Protocol       │          │
                    │    (cluster membership)   │          │
                    │            │              │          │
                    └────────────┼──────────────┘          │
                                 │                         │
                         ┌───────▼───────┐                 │
                         │    MinIO      │                 │
                         │ (bucket/node) │                 │
                         │ :9000 / :9001 │                 │
                         └───────────────┘                 │
                                                           │
                    ┌──────────────────────────────────────┘
                    │         Monitoring (optional)
                    │
              ┌─────▼──────┐    ┌────────────┐
              │ Prometheus  │───▶│  Grafana   │
              │   :9190     │    │   :3203    │
              └─────────────┘    └────────────┘
```

**Key HA Features:**

- **Load Balancing**: Traefik distributes HTTP and gRPC traffic across all healthy nodes
- **Health Checks**: Automatic removal of unhealthy nodes from the load balancer pool
- **Gossip Protocol**: Nodes discover and monitor each other via port 7946
- **Per-Node Storage**: each node keeps its own bucket and data root; writes are replicated to the peers (nodes must not share one bucket)
- **Per-Node Caching**: Each node maintains independent L1 (memory) and L2 (RocksDB) caches
- **Automatic Failover**: Traefik routes around failed nodes transparently

## Dockerfiles

| Dockerfile | Base Image | Purpose |
|------------|-----------|---------|
| `Dockerfile` | `rust:1.92-bookworm` | Production build with dependency layer caching |
| `Dockerfile.dev` | `rustlang/rust:nightly-bookworm` | Dev build with BuildKit cache for fast incremental rebuilds (~30-120s after first build) |
| `Dockerfile.local` | `debian:bookworm-slim` | Lightweight runtime from pre-built binary |

## Common Operations

### Check cluster health

```bash
curl http://localhost:3000/health
curl http://localhost:3000/admin/cluster/status
```

### View logs

```bash
# All services
docker compose -f docker-compose.ha.yml logs -f

# Specific node
docker compose -f docker-compose.ha.yml logs -f dakera-1
```

### Scale down / up

```bash
docker compose -f docker-compose.ha.yml stop dakera-3
docker compose -f docker-compose.ha.yml start dakera-3
```

### Rebuild after code changes (dev)

```bash
docker compose -f docker-compose.dev.yml up -d --build
```

## Kubernetes Deployment

Production-grade deployment on Kubernetes. Covers Dakera server, Dashboard, and MCP server. Use **docker-compose** for local/development; use **Kubernetes** for production.

### Prerequisites

- Kubernetes 1.27+
- kubectl configured for your cluster
- [nginx ingress controller](https://kubernetes.github.io/ingress-nginx/) (for external access)
- [Helm 3](https://helm.sh/) (optional — for Helm-based deploy)

### Option A: Raw manifests (kubectl + Kustomize)

```bash
# 1. Create secrets (replace values)
kubectl create namespace dakera
kubectl create secret generic dakera-secrets \
  --from-literal=DAKERA_ROOT_API_KEY=$(openssl rand -hex 32) \
  --from-literal=MINIO_ROOT_USER=minioadmin \
  --from-literal=MINIO_ROOT_PASSWORD=$(openssl rand -hex 16) \
  --from-literal=AWS_ACCESS_KEY_ID=minioadmin \
  --from-literal=AWS_SECRET_ACCESS_KEY=<minio-password> \
  --namespace dakera
# Cluster mode only: add --from-literal=DAKERA_CLUSTER_SECRET=$(openssl rand -hex 32)

# 2. Edit ingress hostnames
# Edit k8s/ingress.yaml — replace yourdomain.com with your real domain

# 3. Apply all resources
kubectl apply -k k8s/

# 4. Verify pods are running
kubectl get pods -n dakera

# 5. Check Dakera health
kubectl port-forward -n dakera svc/dakera 3000:3000
curl http://localhost:3000/health/ready   # 503 while models load, then 200
```

### Option B: Helm

The Helm chart has moved to the dedicated **[dakera-helm](https://github.com/dakera-ai/dakera-helm)** repository, which publishes to ArtifactHub and GHCR OCI. Helm 3.8+ required.

```bash
# Install from GHCR OCI
helm install dakera oci://ghcr.io/dakera-ai/dakera-helm/dakera --version 0.12.0 \
  --namespace dakera --create-namespace \
  --set dakera.rootApiKey=$(openssl rand -hex 32) \
  --set minio.rootPassword=$(openssl rand -hex 16)

# Install from ArtifactHub index
helm repo add dakera https://dakera-ai.github.io/dakera-helm
helm install dakera dakera/dakera \
  --namespace dakera --create-namespace \
  --set dakera.rootApiKey=$(openssl rand -hex 32) \
  --set minio.rootPassword=$(openssl rand -hex 16)

# Upgrade to a new version
helm upgrade dakera oci://ghcr.io/dakera-ai/dakera-helm/dakera --version <new-version> --reuse-values

# Uninstall
helm uninstall dakera -n dakera
```

See [dakera-ai/dakera-helm](https://github.com/dakera-ai/dakera-helm) for chart source and full documentation.

### Resource Summary

| Component | CPU Request | Memory Request | Default Replicas |
|-----------|------------|---------------|-----------------|
| Dakera server | 500m | 512Mi | 1 (one server per data root; no HPA) |
| Dashboard | 100m | 64Mi | 1 |
| MCP server | 50m | 64Mi | 1 |
| MinIO | 250m | 256Mi | 1 (StatefulSet) |
| Prometheus | 250m | 256Mi | 1 |
| Grafana | 100m | 128Mi | 1 |

### Production Tips

- **Use native S3** (AWS S3, GCS) instead of MinIO in cloud environments: set `DAKERA_S3_ENDPOINT` to your provider's endpoint and disable MinIO (`minio.enabled=false` in Helm)
- **Scaling**: a server locks its data root and the volume is ReadWriteOnce, so one Deployment is one server and `k8s/dakera/hpa.yaml` is not applied by default. Scale out with cluster mode (one release per node: own bucket, own volume, shared `DAKERA_CLUSTER_SECRET`)
- **TLS**: add cert-manager annotations to `k8s/ingress.yaml` or `ingress.annotations` in Helm values
- **Secrets management**: use an external secrets operator (External Secrets, Vault) instead of `kubectl create secret` for production
- **Metrics**: Dakera exposes Prometheus metrics at `GET /metrics` — pods have `prometheus.io/scrape: "true"` annotations for auto-discovery

## Security

Before deploying to a production or internet-facing environment:

| Requirement | How |
|-------------|-----|
| Enable authentication | `DAKERA_AUTH_ENABLED=true` (default in production compose) |
| Set a strong root API key | `DAKERA_ROOT_API_KEY=$(openssl rand -hex 32)` |
| Change MinIO credentials | Set `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` in `.env` |
| Network isolation | Do **not** expose MinIO ports (9000, 9001) publicly |
| TLS termination | Use a reverse proxy (nginx, Traefik, Caddy) with HTTPS |

See the [Configuration Reference](https://dakera.ai/docs) for the full authentication and security documentation.

## Related Repositories

| Repository | Description |
|------------|-------------|
| [dakera-docs](https://github.com/dakera-ai/dakera-docs) | Full documentation |
| [dakera-mcp](https://github.com/dakera-ai/dakera-mcp) | MCP Server for AI agent memory (14 core tools, 86+ via profiles) |
| [dakera-cli](https://github.com/dakera-ai/dakera-cli) | Command-line interface |
| [dakera-py](https://github.com/dakera-ai/dakera-py) | Python SDK |
| [dakera-js](https://github.com/dakera-ai/dakera-js) | TypeScript/JavaScript SDK |
| [dakera-go](https://github.com/dakera-ai/dakera-go) | Go SDK |
| [dakera-rs](https://github.com/dakera-ai/dakera-rs) | Rust SDK |
| [dakera-helm](https://github.com/dakera-ai/dakera-helm) | Helm chart |

### Framework Integrations

| Package | Framework | Install |
|---------|-----------|---------|
| [langchain-dakera](https://github.com/dakera-ai/dakera-langchain) | LangChain (Python) | `pip install langchain-dakera` |
| [@dakera-ai/langchain](https://github.com/dakera-ai/dakera-langchain-js) | LangChain.js | `npm install @dakera-ai/langchain` |
| [crewai-dakera](https://github.com/dakera-ai/dakera-crewai) | CrewAI | `pip install crewai-dakera` |
| [autogen-dakera](https://github.com/dakera-ai/dakera-autogen) | AutoGen | `pip install autogen-dakera` |
| [llamaindex-dakera](https://github.com/dakera-ai/dakera-llamaindex) | LlamaIndex | `pip install llamaindex-dakera` |

See the [integration guides on dakera.ai](https://dakera.ai/integrations/) for setup walkthroughs.

---

<p align="center">
  <a href="https://dakera.ai">dakera.ai</a> · <a href="https://dakera.ai/docs">Documentation</a> · <a href="https://dakera.ai/benchmark">Benchmarks</a>
  <br><br>
  Copyright 2026 Dakera AI · <a href="LICENSE">MIT License</a>
</p>
