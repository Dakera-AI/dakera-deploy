# Production Deployment Checklist

Use this checklist before exposing Dakera to the internet or handling real workloads.

## Security

- [ ] **Set a strong API key**: `DAKERA_ROOT_API_KEY=$(openssl rand -hex 32)`
- [ ] **Enable authentication**: `DAKERA_AUTH_ENABLED=true` (default in `docker-compose.yml`; **`docker-compose.ha.yml` defaults to `false`**: set it `true` in `.env.ha`). v0.12 gRPC needs an API key in the call metadata (`x-api-key` or `authorization: Bearer`) whenever authentication is on, and was open in v0.11
- [ ] **Give gRPC clients a key** and check keys pinned to namespaces: they get `403` on node-wide routes (`/admin/*`, `/ops/*`, `/v1/analytics/*`, ...); backup download, upload and restore need a global `super_admin` key
- [ ] **Encryption at rest** (optional): `DAKERA_ENCRYPTION_KEY` (64 hex characters or a passphrase of 8+), the same on every node, set in `.env` (the compose files pass it). Rotate with `POST /admin/encryption/rotate-key`, check `GET /admin/encryption/status`
- [ ] **Change MinIO credentials**: Replace `minioadmin`/`minioadmin` with strong credentials
- [ ] **Do NOT expose MinIO ports publicly**: Ports 9000/9001 should only be accessible within the Docker network
- [ ] **Enable TLS**: Use a reverse proxy (Traefik, nginx, Caddy) with HTTPS certificates
- [ ] **Restrict network access**: Use firewall rules to limit who can reach the API

## Storage

- [ ] **Use persistent storage**: Use the default profile (MinIO-backed) or native S3, not in-memory mode
- [ ] **Pin image versions**: Set `DAKERA_IMAGE=ghcr.io/dakera-ai/dakera:0.12.0` explicitly — never use `latest` in production
- [ ] **Mount volumes**: Ensure the `dakera-data` (data root: WAL, knowledge graph), `dakera-cache`, `dakera-rocksdb`, `dakera-models` and `minio-data` volumes are on reliable storage
- [ ] **Configure backups**: See [backup-restore.md](backup-restore.md) for backup procedures
- [ ] **Know your way back**: `docker compose run --rm dakera downgrade` (server stopped first) returns v0.12.0 data to v0.11.108; see README "Rolling back to v0.11"
- [ ] **Run `--check-config` before every upgrade**: `docker compose run --rm --no-deps dakera --check-config` (exit 0 = would start, 78 = would refuse)

## Performance

- [ ] **Set resource limits**: `docker-compose.yml` limits the server to 12G memory and 4 CPUs (the Kubernetes manifests: 4Gi and 2 CPUs; the Helm chart: 4Gi and 2) — adjust to your workload. The measured configuration for every optional model is 4 cores / 8 GiB; reranking is CPU-bound (24 CPU-s per `top_k` 16 recall): see [sizing](../docs/features-v0.12.md#performance-and-sizing)
- [ ] **Tune the hot tier**: `DAKERA_L1_CACHE_SIZE` sizes the tiered-storage hot tier (the compose files use `512MB`; a bare number below 10 million is a vector count) — increase for memory-heavy workloads
- [ ] **Cap rerank cost if recall CPU is the limit**: `DAKERA_RERANK_MAX_CANDIDATES` (see the features guide)
- [ ] **Tiered storage**: on in the compose files and manifests (`DAKERA_TIERED_STORAGE=true`, needs `DAKERA_STORAGE=s3`); the hot tier is RocksDB with fsynced writes (`DAKERA_ROCKSDB_SYNC`), expect more write latency on slow disks
- [ ] **Monitor MinIO**: If using MinIO, set `MINIO_API_REQUESTS_MAX` (default 6000) based on your concurrency

## Optional v0.12 features

Everything below is off by default; see [docs/features-v0.12.md](../docs/features-v0.12.md).

- [ ] **Decide per feature, before the first start**: multilingual (`bge-m3`), late interaction (`colbert-small`) and the visual lane change the embedding model or the lane. The store records its model and refuses to start with another: use a **fresh store**, or `DAKERA_ALLOW_MODEL_CHANGE=1` for one start plus `POST /admin/namespaces/migrate-dimensions`. They are one-way for v0.11 (`dakera downgrade` refuses them)
- [ ] **Do not stack the exclusive overlays**: multilingual, late-interaction and vision set different models/lanes; the last file would win silently
- [ ] **`DAKERA_TIERED=0`** with multilingual, late interaction or vision (the tiered embedding engine pins `bge-large` and refuses late interaction); identical on every node
- [ ] **Vision is a dedicated store** (data root and bucket of its own); never turn it on over a text store
- [ ] **Model volume**: `dakera-models` on persistent storage, ~10 GiB for every optional model (the image ships only `bge-large` and the reranker); pre-pull (`models pull bge-m3 whisper vision`) so the first start does not wait on a download; air-gapped hosts seed it with `models pull --dir` and set `HF_HUB_OFFLINE=1`
- [ ] **Behind a proxy or mirror**: `HTTPS_PROXY` (an `http://` or `socks5h://` URL, never `https://`), `NO_PROXY=127.0.0.1,localhost,minio,...`, `HF_ENDPOINT`
- [ ] **Memory for media**: at least 8 GiB for transcription and image pages (measured: 530 MiB anonymous with every model loaded, +1.9 GiB image peak); clients retry `503` + `Retry-After`
- [ ] **Verify**: `GET /v1/capabilities` shows the feature on (and `default_model`), `GET /health` has no unexpected `degraded` or `config_warnings`

## High Availability

- [ ] **Use the HA profile** for production: `docker compose -f docker-compose.ha.yml up -d`
- [ ] **Deploy 3+ nodes**: The HA compose includes 3 Dakera nodes by default
- [ ] **Set `DAKERA_CLUSTER_SECRET`**: required in cluster mode, >= 16 characters, identical on every node (keep it in `.env.ha` / a Secret)
- [ ] **One bucket per node**: nodes must not share one S3 bucket as their store (the HA compose gives each its own)
- [ ] **No shared Redis for an HA cluster**: with one Redis shared by the nodes, v0.12.0 did not apply replicated writes on some nodes (measured); `docker-compose.ha.yml` sets no `DAKERA_REDIS_URL`. Rate limits are then per node
- [ ] **Configure seed nodes**: Each node needs `DAKERA_CLUSTER_SEEDS` pointing to other nodes
- [ ] **Test failover**: Stop one node and verify traffic routes to remaining nodes

## Monitoring

- [ ] **Enable the monitoring profile**: `docker compose -f docker-compose.ha.yml --profile monitoring up -d`
- [ ] **Check dashboards**: Grafana at the configured port has the v0.12 "Dakera Overview" dashboard (every panel reads a metric the server emits)
- [ ] **Alerts**: the server's rules (`monitoring/dakera.rules.yml`: config warnings, degraded components, WAL, model loads, backups, cold tier, RocksDB, cluster replication) and the deploy-side rules (`monitoring/alerting-rules.yml`) are loaded by the monitoring profile; route them with Alertmanager. Alert on `dakera_config_warnings > 0` and `dakera_component_degraded == 1`
- [ ] **Monitor `/metrics`**: Dakera exposes Prometheus metrics at `GET /metrics`

## Kubernetes-Specific

- [ ] **Use External Secrets**: Don't store secrets in YAML — use External Secrets Operator or HashiCorp Vault
- [ ] **Features**: `kubectl apply -k k8s-features/overlays/<name>` (the `models-cache` component backs the model cache with a PVC and pre-pulls the configured models); `vision` deploys its own namespace
- [ ] **Do not autoscale one data root**: a server locks its data root and the volume is ReadWriteOnce, so the HPA is not applied by default in v0.12; scale out with cluster mode (one release per node)
- [ ] **Probes**: liveness `/health/live` (+ startup probe), readiness `/health/ready` (the manifests do this)
- [ ] **Add cert-manager**: Annotate the ingress for automatic TLS certificate management
- [ ] **Use native S3**: In cloud environments (AWS, GCP), use native S3/GCS instead of MinIO
