# Production Deployment Checklist

Use this checklist before exposing Dakera to the internet or handling real workloads.

## Security

- [ ] **Set a strong API key**: `DAKERA_ROOT_API_KEY=$(openssl rand -hex 32)`
- [ ] **Enable authentication**: `DAKERA_AUTH_ENABLED=true` (default in production compose)
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

- [ ] **Set resource limits**: The default compose includes memory (4G) and CPU (2.0) limits — adjust based on your workload
- [ ] **Tune L1 cache**: `DAKERA_L1_CACHE_SIZE` defaults to 512MB — increase for memory-heavy workloads
- [ ] **Enable tiered storage**: Set `DAKERA_TIERED_STORAGE=true` to automatically tier hot/warm/cold data
- [ ] **Monitor MinIO**: If using MinIO, set `MINIO_API_REQUESTS_MAX` (default 6000) based on your concurrency

## High Availability

- [ ] **Use the HA profile** for production: `docker compose -f docker-compose.ha.yml up -d`
- [ ] **Deploy 3+ nodes**: The HA compose includes 3 Dakera nodes by default
- [ ] **Set `DAKERA_CLUSTER_SECRET`**: required in cluster mode, >= 16 characters, identical on every node (keep it in `.env.ha` / a Secret)
- [ ] **One bucket per node**: nodes must not share one S3 bucket as their store (the HA compose gives each its own)
- [ ] **Set up Redis**: Required for HA mode — distributed cache, rate-limit counters, SSE fan-out
- [ ] **Configure seed nodes**: Each node needs `DAKERA_CLUSTER_SEEDS` pointing to other nodes
- [ ] **Test failover**: Stop one node and verify traffic routes to remaining nodes

## Monitoring

- [ ] **Enable the monitoring profile**: `docker compose -f docker-compose.ha.yml --profile monitoring up -d`
- [ ] **Check dashboards**: Grafana at the configured port has pre-built Dakera dashboards
- [ ] **Set up alerts**: Configure Prometheus alerting rules for health check failures and high latency
- [ ] **Monitor `/metrics`**: Dakera exposes Prometheus metrics at `GET /metrics`

## Kubernetes-Specific

- [ ] **Use External Secrets**: Don't store secrets in YAML — use External Secrets Operator or HashiCorp Vault
- [ ] **Do not autoscale one data root**: a server locks its data root and the volume is ReadWriteOnce, so the HPA is not applied by default in v0.12; scale out with cluster mode (one release per node)
- [ ] **Probes**: liveness `/health/live` (+ startup probe), readiness `/health/ready` (the manifests do this)
- [ ] **Add cert-manager**: Annotate the ingress for automatic TLS certificate management
- [ ] **Use native S3**: In cloud environments (AWS, GCP), use native S3/GCS instead of MinIO
