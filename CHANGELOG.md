# Changelog

All notable changes to the Dakera deployment configurations will be documented in this file.

## [Unreleased]

## [0.3.1] - 2026-04-06

### Changed

- Bump dakera server image: `0.9.12` → `0.9.13` in docker-compose, docker-compose.ha, and k8s/dakera/deployment.yaml
  - v0.9.13: Security patch — DAK-1596 untrack .mcp.json + add to .gitignore; CVSS-gated cargo-audit + embedding warm-up (DAK-1629)
- Bump dashboard image: `0.3.28` → `0.3.29` in docker-compose, docker-compose.ha, and k8s/dashboard/deployment.yaml
  - v0.3.29: KPI metrics panel at /observe/kpis (DAK-1578)

## [0.3.0] - 2026-04-01

### Changed

- Bump dakera server image: `0.9.8` → `0.9.9` in docker-compose, docker-compose.ha, and k8s/dakera/deployment.yaml
  - v0.9.9: SEC-5 per-namespace rate limiting for store/recall ops (MemoryPolicy)

## [0.2.9] - 2026-04-01

### Changed

- Bump k8s dakera server image: `0.8.3` → `0.9.8` (k8s manifests were drifted from docker-compose)
- Bump k8s dashboard image: `0.3.22` → `0.3.28`
- Pin k8s mcp image: `latest` → `0.9.1` (reproducible deployments)

## [0.2.8] - 2026-04-01

### Changed

- Bump dakera server default image: `0.9.7` → `0.9.8`
  - v0.9.8: KG-3 Deep Associative Recall — configurable N-hop knowledge graph traversal on recall

## [0.2.7] - 2026-03-31

### Changed

- Bump dakera server default image: `0.9.6` → `0.9.7`
  - v0.9.7: CE-7 Time-Window Recall (since/until on recall), COG-3 Proactive Memory Consolidation (background DBSCAN per namespace)

## [0.2.6] - 2026-03-31

### Changed

- Bump dakera server default image: `0.8.6` → `0.9.6` (weekly batch)
  - v0.9.0: CE-4 full-text search, CE-5 Knowledge Graph, OPS-2 vector primitives, OPS-3 batch upsert, ODE integration REST API
  - v0.9.1: SEC-3 zero-downtime encryption key rotation fix
  - v0.9.2: SEC-4 HMAC-SHA256 webhook auth
  - v0.9.3: Docker Debian Trixie (glibc 2.40, ORT ARM64 fix)
  - v0.9.4: ODE-2 GLiNER entity extraction
  - v0.9.5: ODE webhook HMAC security patch
  - v0.9.6: COG-1 memory lifecycle (MemoryPolicy), COG-2 associative recall, KG-2 graph query/export

## [0.2.5] - 2026-03-24

### Fixed

- Scope HA compose stack ports to `HA_` prefix — prevents port binding conflicts when single-node and HA stacks run on same host (DAK-833)
- Add explicit `name: dakera-ha` to `docker-compose.ha.yml` and `name: dakera` to `docker-compose.yml` — prevents Compose project name collision that caused MinIO container eviction from the network when starting the HA stack alongside the single-node stack (DAK-829)

### Changed

- Bump `dakera-dashboard` default image: `0.3.23` → `0.3.24` → `0.3.25`

## [0.2.4] - 2026-03-24

### Fixed

- Bump dakera image: `0.8.1` → `0.8.2` (DAK-720 SSE connected event, DAK-729 reposition as AI agent memory platform) (DAK-767)
- Bump dakera-dashboard: `0.3.22` → `0.3.23` (DAK-722 live feed idle-state, DAK-571 health badge)
- Configure GitHub Actions deploy secrets (`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`) — fixes silent deploy failures since v0.8.1 (DAK-767)

## [0.2.3] - 2026-03-23

### Fixed

- Bump dakera image: `0.8.0` → `0.8.1` (DAK-679 optional vector in hybrid search, INFRA-2 release deploy fix, DAK-664 integration tests) (#33)

## [0.2.2] - 2026-03-22

### Fixed

- Bump dakera-dashboard: `0.3.6` → `0.3.7` → `0.3.8` → `0.3.10` → `0.3.12` (UTF-8 WASM panic fix — Memory Network graph render) → `0.3.13` (nginx WASM gzip fix) → `0.3.14` (regression fixes) → `0.3.16` (WASM size reduction via fat LTO + panic=abort) → `0.3.18` (WASM permanent load fix) → `0.3.20` (DX improvements) → `0.3.21` → `0.3.22` (DAK-571 health badge + key sync) (#22, #23, #25, #26, #27, #28, #29)

## [0.2.1] - 2026-03-21

### Fixed

- Bump dakera-dashboard: `0.3.3` → `0.3.4` → `0.3.5` (DAK-353 critical fixes) → `0.3.6` (#20, #21)
- Bump HA compose dakera image: `0.6.3` → `0.6.4`

## [0.2.0] - 2026-03-21

### Added

- VS Code / Cursor devcontainer for one-command local dev stack (#8)
- Pinned default images to versioned tags in all compose files — dakera `0.6.4`, dakera-dashboard `0.3.3` (#9)

### Fixed

- Remove broken Docker publish workflow; add valid no-op release workflow (#6, #7)
- Remove `v` prefix from GHCR image tags — GHCR publishes `0.6.x` not `v0.6.x` (#10)
- Bump dakera image: `0.6.0` → `0.6.2` (Memory Network fix) → `0.6.3` (rustls security patch) → `0.6.4` (SSE query-param auth) (#12, #14, #17)
- Bump dakera-dashboard: `0.3.0` → `0.3.1` (Safari black screen fix) → `0.3.2` (WASM + mobile nav fix) → `0.3.3` (SSE api_key fix)
- Sync HA compose image versions to match standard compose configs

### Security

- Add explicit `GITHUB_TOKEN` permissions to CI workflow (#5)

## [0.1.1] - 2026-03-18

### Security — SA-2026-001 (Critical)

Three critical insecure-default vulnerabilities were found in the default Docker Compose configuration
and fixed in [dakera-deploy PR #1](https://github.com/Dakera-AI/dakera-deploy/pull/1).

**Affected versions:** v0.1.0 and any deployment using the default `docker-compose.yml` without
overriding the affected variables.

**Vulnerabilities fixed:**

1. **Auth disabled by default** (`DAKERA_AUTH_ENABLED=false`): The default Compose config shipped
   with authentication disabled, leaving the API open with no key enforcement. Fixed: default is
   now `true`; the env var is also required (startup fails if unset).

2. **Public MinIO bucket**: The `minio-setup` init container set the storage bucket policy to
   anonymous download (`mc anonymous set download`), exposing all stored vector data to
   unauthenticated reads. Fixed: anonymous access policy removed.

3. **Hardcoded dev API key fallback** (`dk_dev_root_key_change_in_production`): The root API key
   fell back to a well-known dev string if not overridden. Fixed: the variable is now required with
   no default; containers refuse to start until a real key is supplied in `.env`.

**Action required for existing deployments:**

See [Security Advisory SA-2026-001](https://github.com/Dakera-AI/dakera-docs/blob/main/SECURITY.md#sa-2026-001)
in dakera-docs for the full advisory, impact assessment, and remediation steps.

### Changed

- `docker-compose.yml`: `DAKERA_AUTH_ENABLED` default changed from `false` to `true`
- `docker-compose.yml`: `DAKERA_ROOT_API_KEY` is now required (no default fallback)
- `docker-compose.yml`: MinIO bucket anonymous-download policy removed
- `docker-compose.yml`: Resource limits added for `dakera` and `minio` services
- `docker/.env.example`: Restructured with required fields prominently at top
- `README.md`: Security section added with production hardening requirements

## [0.1.0] - 2025-03-15

### Added
- Docker deployment configurations (production, dev, local)
- High availability setup with 3-node cluster and Traefik load balancer
- Traefik dynamic routing configuration for HTTP and gRPC load balancing
- Prometheus scrape configuration for Dakera, MinIO, and self-monitoring
- Grafana provisioning with Prometheus datasource and Dakera overview dashboard
- Comprehensive deployment documentation with architecture diagrams
