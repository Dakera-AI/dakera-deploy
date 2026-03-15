# Dakera Deployment

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED)](https://docs.docker.com/)

Deployment configurations for Dakera -- a high-performance vector database built for AI agent memory.

This repository contains Docker configurations, high-availability clustering, load balancing, and monitoring setup for running Dakera in development and production environments.

## Deployment Profiles

| Profile | Description | Use Case |
|---------|-------------|----------|
| **local** | Single instance, in-memory storage | Quick testing, no dependencies |
| **dev** | MinIO storage backend for development | Local development with persistence |
| **default** | Dakera + MinIO with full configuration | Staging / single-node production |
| **ha** | 3-node cluster with Traefik load balancer | Production high availability |
| **monitoring** | Prometheus + Grafana observability stack | Metrics and dashboards |

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

```bash
cd docker
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
# Start Dakera with monitoring
cd docker
docker compose up -d

# Start monitoring stack
cd ../monitoring
docker compose up -d  # (if using a separate monitoring compose)
```

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3001 (admin/admin)

Pre-configured dashboards include request rates, latency percentiles, cache hit ratios, storage metrics, and cluster health.

## Directory Structure

```
dakera-deploy/
├── docker/                          # Docker deployment configs
│   ├── Dockerfile                   # Production multi-stage build
│   ├── Dockerfile.dev               # Dev build with fast incremental compilation
│   ├── Dockerfile.local             # Lightweight build from pre-built binary
│   ├── docker-compose.yml           # Default: Dakera + MinIO
│   ├── docker-compose.dev.yml       # Dev: MinIO only (run Dakera locally)
│   ├── docker-compose.local.yml     # Local: single instance, in-memory
│   ├── docker-compose.ha.yml        # HA: 3-node cluster + Traefik LB
│   └── traefik-dynamic.yml          # Traefik routing and load balancer config
├── monitoring/                      # Observability stack
│   ├── prometheus.yml               # Prometheus scrape configuration
│   └── grafana/                     # Grafana provisioning
│       └── provisioning/
│           ├── datasources/
│           │   └── datasources.yml  # Prometheus + Jaeger datasources
│           └── dashboards/
│               ├── dashboards.yml   # Dashboard auto-provisioning config
│               └── json/
│                   └── dakera-overview.json  # Pre-built overview dashboard
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

## Related Repositories

| Repository | Description |
|------------|-------------|
| [dakera](https://github.com/dakera-ai/dakera) | Core vector database engine (Rust) |
| [dakera-py](https://github.com/dakera-ai/dakera-py) | Python SDK |
| [dakera-js](https://github.com/dakera-ai/dakera-js) | TypeScript/JavaScript SDK |
| [dakera-go](https://github.com/dakera-ai/dakera-go) | Go SDK |
| [dakera-rs](https://github.com/dakera-ai/dakera-rs) | Rust SDK |
| [dakera-cli](https://github.com/dakera-ai/dakera-cli) | Command-line interface |
| [dakera-mcp](https://github.com/dakera-ai/dakera-mcp) | MCP Server for AI agent memory |
| [dakera-dashboard](https://github.com/dakera-ai/dakera-dashboard) | Admin dashboard (Leptos/WASM) |
| [dakera-docs](https://github.com/dakera-ai/dakera-docs) | Documentation |
| [dakera-cortex](https://github.com/dakera-ai/dakera-cortex) | Flagship demo with AI agents |

## License

Copyright 2025 Dakera AI. See [LICENSE](LICENSE) for details.
