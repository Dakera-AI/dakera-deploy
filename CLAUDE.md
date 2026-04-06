# dakera-deploy

Kubernetes + Helm deployment infrastructure for the Dakera AI platform — Helm charts, Docker
Compose configs, raw K8s manifests, and Prometheus/Grafana monitoring stack.

## Key Commands
```bash
helm lint charts/dakera                         # Lint Helm chart
helm install dakera charts/dakera               # Install to current K8s context
helm upgrade dakera charts/dakera               # Upgrade existing release
helm package charts/dakera                      # Package chart (.tgz)
docker-compose -f docker/docker-compose.yml up  # Local Docker deployment
gh workflow run "Publish Helm Chart"            # Push chart to GHCR OCI registry
```

## Architecture
- `charts/dakera/` — Helm chart: Chart.yaml, values.yaml, templates/
- `docker/` — Docker Compose configs for dev/prod
- `k8s/` — Raw Kubernetes manifests (non-Helm)
- `monitoring/` — Prometheus scrape configs + Grafana dashboard JSONs

## Conventions
- Helm chart OCI package lives at `oci://ghcr.io/dakera-ai/charts/dakera` (public)
- Requires `GH_PAT_PACKAGES` secret for Helm publish workflow
- Deploy version bumps are batched weekly unless a security patch requires immediate redeploy
- `Set Helm Chart GHCR Visibility` workflow must run after initial publish to make package public
