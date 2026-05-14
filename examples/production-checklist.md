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
- [ ] **Pin image versions**: Set `DAKERA_IMAGE=ghcr.io/dakera-ai/dakera:0.11.55` explicitly — never use `latest` in production
- [ ] **Mount volumes**: Ensure `dakera-cache`, `dakera-rocksdb`, and `minio-data` volumes are on reliable storage
- [ ] **Configure backups**: See [backup-restore.md](backup-restore.md) for backup procedures

## Performance

- [ ] **Set resource limits**: The default compose includes memory (4G) and CPU (2.0) limits — adjust based on your workload
- [ ] **Tune L1 cache**: `DAKERA_L1_CACHE_SIZE` defaults to 512MB — increase for memory-heavy workloads
- [ ] **Enable tiered storage**: Set `DAKERA_TIERED_STORAGE=true` to automatically tier hot/warm/cold data
- [ ] **Monitor MinIO**: If using MinIO, set `MINIO_API_REQUESTS_MAX` (default 6000) based on your concurrency

## High Availability

- [ ] **Use the HA profile** for production: `docker compose -f docker-compose.ha.yml up -d`
- [ ] **Deploy 3+ nodes**: The HA compose includes 3 Dakera nodes by default
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
- [ ] **Configure HPA**: The included HPA scales Dakera pods 1–5 based on CPU; set `minReplicas: 3` for HA
- [ ] **Add cert-manager**: Annotate the ingress for automatic TLS certificate management
- [ ] **Use native S3**: In cloud environments (AWS, GCP), use native S3/GCS instead of MinIO
