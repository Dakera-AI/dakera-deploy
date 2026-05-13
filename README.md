# Dakera Deployment

[![CI](https://github.com/Dakera-AI/dakera-deploy/actions/workflows/ci.yml/badge.svg)](https://github.com/Dakera-AI/dakera-deploy/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Dakera-AI/dakera-deploy)](https://github.com/Dakera-AI/dakera-deploy/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED)](https://docs.docker.com/)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-Ready-326CE5)](https://kubernetes.io/)
[![Helm](https://img.shields.io/github/v/release/Dakera-AI/dakera-helm?label=Helm&color=0F1689)](https://github.com/dakera-ai/dakera-helm)

Deployment configurations for Dakera — the AI agent memory platform. Persistent, session-aware, cross-agent memory for your AI agents.

This repository contains Docker configurations, high-availability clustering, load balancing, and monitoring setup for running Dakera in development and production environments.

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

> **Version pinning**: The default image tags are pinned to the latest stable release.
> To run a specific version, set `DAKERA_IMAGE` and `DASHBOARD_IMAGE` in your `.env`:
> ```bash
> DAKERA_IMAGE=ghcr.io/dakera-ai/dakera:0.9.9
> DASHBOARD_IMAGE=ghcr.io/dakera-ai/dakera-dashboard:0.3.28
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

Production HA deployment with Traefik load balancer, 3 Dakera nodes, gossip-based clustering, and shared MinIO storage.

```bash
cd docker
docker compose -f docker-compose.ha.yml up -d
```

- REST API (load balanced): http://localhost:3000
- gRPC API (load balanced): localhost:50051
- Traefik Dashboard: http://localhost:8080
- MinIO Console: http://localhost:9001
- Cluster status: http://localhost:3000/admin/cluster/status

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
│   │   └── hpa.yaml                 # Horizontal Pod Autoscaler
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
| `DAKERA_STORAGE` | `memory` | Storage backend (`memory`, `s3`) |
| `DAKERA_LOG_LEVEL` / `RUST_LOG` | `info` | Log verbosity level |

### S3/MinIO Storage

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_S3_ENDPOINT` | - | S3-compatible endpoint URL |
| `DAKERA_S3_BUCKET` | `dakera` | Storage bucket name |
| `DAKERA_S3_REGION` | `us-east-1` | S3 region |
| `DAKERA_S3_ACCESS_KEY` / `AWS_ACCESS_KEY_ID` | - | S3 access key |
| `DAKERA_S3_SECRET_KEY` / `AWS_SECRET_ACCESS_KEY` | - | S3 secret key |

### Cache Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_L1_CACHE_SIZE` | `1073741824` (1GB) | In-memory L1 cache size in bytes |
| `DAKERA_L2_CACHE_PATH` | `/data/rocksdb` | RocksDB L2 cache directory |
| `DAKERA_CACHE_DIR` | `/data/cache` | General cache directory |

### Cluster (HA Mode)

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_CLUSTER_MODE` | `false` | Enable cluster mode |
| `DAKERA_CLUSTER_ROLE` | - | Node role (`primary`, `replica`) |
| `DAKERA_CLUSTER_SEEDS` | - | Comma-separated seed nodes (`host:port`) |
| `DAKERA_NODE_ID` | - | Unique node identifier |
| `DAKERA_GOSSIP_PORT` | `7946` | Gossip protocol port |
| `DAKERA_GOSSIP_BIND` | `0.0.0.0:7946` | Gossip bind address |
| `DAKERA_API_ADVERTISE` | - | Advertised API URL for the node |

### Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `DAKERA_AUTH_ENABLED` | `false` | Enable API authentication |
| `DAKERA_ROOT_API_KEY` | - | Root API key (change in production) |

## HA Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │              Client Applications            │
                    └──────────────────┬──────────────────────────┘
                                       │
                              ┌────────▼────────┐
                              │   Traefik LB    │
                              │  :3000 (HTTP)   │
                              │  :50051 (gRPC)  │
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
                         │ (shared S3)   │                 │
                         │ :9000 / :9001 │                 │
                         └───────────────┘                 │
                                                           │
                    ┌──────────────────────────────────────┘
                    │         Monitoring (optional)
                    │
              ┌─────▼──────┐    ┌────────────┐
              │ Prometheus  │───▶│  Grafana   │
              │   :9090     │    │   :3001    │
              └─────────────┘    └────────────┘
```

**Key HA Features:**

- **Load Balancing**: Traefik distributes HTTP and gRPC traffic across all healthy nodes
- **Health Checks**: Automatic removal of unhealthy nodes from the load balancer pool
- **Gossip Protocol**: Nodes discover and monitor each other via port 7946
- **Shared Storage**: All nodes share MinIO for persistent vector data
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

# 2. Edit ingress hostnames
# Edit k8s/ingress.yaml — replace yourdomain.com with your real domain

# 3. Apply all resources
kubectl apply -k k8s/

# 4. Verify pods are running
kubectl get pods -n dakera

# 5. Check Dakera health
kubectl port-forward -n dakera svc/dakera 3000:3000
curl http://localhost:3000/health
```

### Option B: Helm

The Helm chart has moved to the dedicated **[dakera-helm](https://github.com/dakera-ai/dakera-helm)** repository, which publishes to ArtifactHub and GHCR OCI. Helm 3.8+ required.

```bash
# Install from GHCR OCI
helm install dakera oci://ghcr.io/dakera-ai/dakera-helm/dakera --version 0.11.55 \
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
| Dakera server | 500m | 512Mi | 1 (HPA: 1–5) |
| Dashboard | 100m | 64Mi | 1 |
| MCP server | 50m | 64Mi | 1 |
| MinIO | 250m | 256Mi | 1 (StatefulSet) |
| Prometheus | 250m | 256Mi | 1 |
| Grafana | 100m | 128Mi | 1 |

### Production Tips

- **Use native S3** (AWS S3, GCS) instead of MinIO in cloud environments: set `DAKERA_S3_ENDPOINT` to your provider's endpoint and disable MinIO (`minio.enabled=false` in Helm)
- **Enable autoscaling**: the HPA scales Dakera pods 1–5 based on CPU/memory. Set `minReplicas: 3` for HA
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

See [CONFIGURATION.md](https://github.com/dakera-ai/dakera-docs/blob/main/CONFIGURATION.md) for the full authentication reference.

## Related Repositories

| Repository | Description |
|------------|-------------|
| [dakera-mcp](https://github.com/dakera-ai/dakera-mcp) | MCP Server for AI agent memory (83 tools) |
| [dakera-cli](https://github.com/dakera-ai/dakera-cli) | Command-line interface |
| [dakera-py](https://github.com/dakera-ai/dakera-py) | Python SDK |
| [dakera-js](https://github.com/dakera-ai/dakera-js) | TypeScript/JavaScript SDK |
| [dakera-go](https://github.com/dakera-ai/dakera-go) | Go SDK |
| [dakera-rs](https://github.com/dakera-ai/dakera-rs) | Rust SDK |
| [dakera-helm](https://github.com/dakera-ai/dakera-helm) | Helm chart |
| [dakera-bench](https://github.com/dakera-ai/dakera-bench) | Benchmarks |

## License

Copyright 2026 Dakera AI. See [LICENSE](LICENSE) for details.
