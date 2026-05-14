# Dakera Quickstart Guide

Get Dakera running and store your first memory in under 5 minutes.

## Prerequisites

- [Docker](https://docs.docker.com/get-started/get-docker/) (v20.10+)
- [Docker Compose](https://docs.docker.com/compose/install/) (v2.0+)
- `curl` (for testing)

## Step 1: Clone and Start

```bash
git clone https://github.com/dakera-ai/dakera-deploy
cd dakera-deploy/docker
docker compose -f docker-compose.local.yml up -d
```

This starts Dakera in **in-memory mode** — no external dependencies, no config files needed.

## Step 2: Verify Health

```bash
curl http://localhost:3000/health
```

Expected response:
```json
{"status":"ok"}
```

## Step 3: Store a Memory

```bash
curl -X POST http://localhost:3000/v1/memories \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "my-agent",
    "content": "The user prefers dark mode and uses VS Code."
  }'
```

## Step 4: Recall Memories

```bash
curl -X POST http://localhost:3000/v1/memories/recall \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "my-agent",
    "query": "What IDE does the user prefer?"
  }'
```

Dakera returns semantically relevant memories ranked by similarity.

## Step 5: Stop

```bash
docker compose -f docker-compose.local.yml down
```

## Next Steps

| Goal | Guide |
|------|-------|
| Persist data across restarts | Use `docker compose up -d` (default profile with MinIO) |
| Enable authentication | See [environment-variables.md](environment-variables.md) |
| Production deployment | See [production-checklist.md](production-checklist.md) |
| High availability | See the [HA section](../README.md#high-availability-3-node-cluster) in the README |
| Use an SDK | [Python](https://github.com/dakera-ai/dakera-py) · [TypeScript](https://github.com/dakera-ai/dakera-js) · [Go](https://github.com/dakera-ai/dakera-go) · [Rust](https://github.com/dakera-ai/dakera-rs) |
