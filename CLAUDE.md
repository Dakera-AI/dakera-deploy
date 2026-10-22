# dakera-deploy

Deployment infrastructure for the Dakera AI platform — Docker Compose configs, raw K8s manifests
(kustomize), and the Prometheus/Grafana monitoring stack. The Helm chart is NOT in this repository:
it lives in Dakera-AI/dakera-helm (`charts/dakera`), which publishes it.

## Key Commands
```bash
docker compose -f docker/docker-compose.yml config --quiet   # Validate (CI mirror; needs DAKERA_ROOT_API_KEY set)
docker compose -f docker/docker-compose.yml up -d            # Local Docker deployment
kustomize build k8s/                                         # Render the raw manifests (CI mirror)
```

## Architecture
- `docker/` — Docker Compose configs for dev/prod (production redeploys `docker compose --profile dashboard up -d`
  from `docker/` on every engine merge, with the `:edge` image: keep `main` working with the current image)
- `k8s/` — Raw Kubernetes manifests (non-Helm); `k8s-features/` — kustomize components / overlays
- `monitoring/` — Prometheus scrape configs + Grafana dashboard JSONs

## Conventions
- Helm chart: Dakera-AI/dakera-helm, published as `oci://ghcr.io/dakera-ai/dakera-helm/dakera` and
  https://dakera-ai.github.io/dakera-helm; keep its values in step with the compose files here
- Deploy version bumps are batched weekly unless a security patch requires immediate redeploy
