# Changelog

All notable changes to the Dakera deployment configurations will be documented in this file.

## [Unreleased]

### Changed: Dakera server v0.12.1, Dashboard 0.5.0, dakera-mcp 0.12.0

- Default Dakera image `0.12.0` -> `0.12.1` (compose files, `.env` examples, devcontainer, playground, `k8s/`
  including the `check-config` and `downgrade` Jobs, the `models-cache` component, README and guides).
- Dashboard image `0.4.0` -> `0.5.0` (both compose files, `k8s/dashboard/`, `.env` examples, README). Deployment is
  unchanged from 0.4.0 (same variables, port `3000`, healthcheck `/_session/healthz`); every 0.4 URL redirects.
- `k8s/mcp/deployment.yaml` (not applied by `kustomization.yaml`): `dakera-mcp` `0.10.8` -> `0.12.0` (distroless
  image, uid 65532, no shell; `securityContext` set to match).
- **Breaking for clusters: v0.12.1 requires `DAKERA_CLUSTER_SECRET` on every cluster node**, upgraded or not (exit 78
  without it). `docker-compose.ha.yml` already refused to start without it; its comments, `.env.ha.example`,
  `k8s/secret.example.yaml`, the production checklist and the features guide no longer say to leave it unset during
  a mixed-version period: generate it with `openssl rand -hex 32` and upgrade every node in one window.
- Full-text indexes: v0.12.1 re-analyses v0.11-built indexes at startup, so the v0.12.0 manual
  `POST /admin/fulltext/reindex {"rebuild": true}` step is no longer required (README section rewritten; kept for
  deployments still on v0.12.0; `scripts/post-upgrade-reindex.sh` kept).
- Embedding model: a changed `DAKERA_MODEL` is re-embedded in the background on v0.12.1 (multilingual overlays,
  `.env` examples, environment reference, features guide); late interaction and vision still need a fresh store or
  the manual migration.

### Added: v0.12.1

- README: "Upgrading from v0.12.0 to v0.12.1" (backup, cluster secret and the one-window procedure, what the first
  start does by itself, the memory / session totals that change meaning); "Dashboard 0.5.0".
- `examples/api-notes.md`: v0.12.1 memory and session totals. The Prometheus rules and Grafana dashboards read none
  of those fields and no metric name changed between v0.12.0 and v0.12.1: `monitoring/` is unchanged.

### Changed: Dashboard 0.4.0

- Dashboard `ghcr.io/dakera-ai/dakera-dashboard` `0.3.30` (single node) / `0.3.29` (HA, `k8s/`, README) -> `0.4.0`
  (`docker/docker-compose.yml` profile `dashboard`, `docker/docker-compose.ha.yml`, `k8s/dashboard/`).
- **Breaking for deployments: dashboard 0.4.0 signs operators in with a server-side session.**
  `DAKERA_API_KEY` is removed from the dashboard service in both compose files and from `k8s/dashboard/` (the
  `DAKERA_ROOT_API_KEY` secret reference is gone; the image ignores `DAKERA_API_KEY` and `DAKERA_CLIENT_URL` with a
  warning). Operators sign in at `/login` with their own key. **Rotate any key the old dashboard carried**: it was
  written into every page the dashboard served (#296). `DAKERA_API_UPSTREAM` is unchanged.
- Dashboard healthcheck / probes use `/_session/healthz` (compose `healthcheck`, Kubernetes liveness and readiness).

### Added: Dashboard 0.4.0

- Optional `DAKERA_SESSION_TTL_HOURS` (default `12`) passed to the dashboard in both compose files; documented in
  `.env.example`, `.env.ha.example`, `examples/environment-variables.md` and as a commented env var in `k8s/`.
- README: "Dashboard 0.4.0" section (upgrade steps, in-memory sessions and the single-replica note, TLS in front with
  `X-Forwarded-Proto` and `Host`, Caddy and nginx snippets); ingress comment about forwarding those headers.

## [0.12.0] - Dakera server v0.12.0

v0.11 is preserved on the `release/0.11` branch; `main` targets v0.12.0 from here on.

### Changed

- Default Dakera image `:latest` / `0.11.x` -> `0.12.0` (compose files, devcontainer, `k8s/`).
- Speech to text: the multimodal overlays pass `DAKERA_WHISPER_MODEL`, default `whisper-base` (multilingual, language
  auto-detected), not English-only `whisper-tiny.en`: a deployment that enables the overlay and sets no
  `DAKERA_WHISPER_MODEL` transcribes with `whisper-base`. Set `whisper-tiny.en` to keep the lightest English model.
- Health checks: `/health` -> `/health/ready` (compose) and `/health/live` + `/health/ready` + a startup
  probe (Kubernetes); start period 10 minutes: the port answers while models load.
- One data root: `DAKERA_STORAGE_PATH=/data`. The data volume (`dakera-data`) is mounted there; the old
  warm-tier volume (`dakera-cache`) stays at `/data/cache`, the old RocksDB volume (`dakera-rocksdb`)
  moves to `/data/hot`. HA nodes: `dakera-N-data` at `/data`, `dakera-N-rocksdb` at `/data/hot`,
  `dakera-N-cache` at `/data/cache/warm`.
- HA: each node has its own bucket (`dakera`, `dakera-2`, `dakera-3`; created by `minio-setup`); nodes
  sharing one bucket are refused by v0.12 on a fresh install. `DAKERA_NODE_ID` -> `DAKERA_CLUSTER_NODE_ID`.
- Kubernetes: `Recreate` strategy, `fsGroup: 1000`, data PVC (name kept: `dakera-rocksdb`) mounted at
  `/data`; the HPA is no longer applied by `kustomization.yaml` (one server per data root).
- Playground compose: removed `DAKERA_L2_CACHE_PATH`, data root volume, readiness health check.

### Added

- `DAKERA_CLUSTER_SECRET` (required in cluster mode) in `docker-compose.ha.yml`, `.env.ha.example`,
  `k8s/secret.example.yaml`.
- Model volume `dakera-models` at `/app/models` (HF_HOME); `models pull` / `prune` recipes.
- `docker compose run --rm dakera --check-config` (pre-upgrade) and `... downgrade` (rollback) recipes;
  Kubernetes one-off Jobs `k8s/dakera/check-config-job.yaml` and `k8s/dakera/downgrade-job.yaml`.
- README: "Versions", "Upgrading from v0.11 to v0.12.0", "Rolling back to v0.11".

### Added: v0.12 features, all opt-in (docs/features-v0.12.md)

- `docs/features-v0.12.md`: "Features in v0.12.0": a capability matrix (feature, switch, variables, resources,
  constraints, how to verify) and per-feature sections: multilingual (bge-m3, per-language full-text, CJK
  bigrams, `DAKERA_QUERY_LANG`, per-request `lang`, the full-text reindex route), multimodal (attachments, speech to
  text with a choice of five Whisper models (default `whisper-base`, multilingual with auto-detected language), image / page indexing and the visual lane, memory admission and `503` + `Retry-After`), multi-vector
  records, late interaction, RaBitQ, rerank controls, the model store (`dakera models list / pull / prune`,
  baked images, proxies, a Hugging Face mirror, offline and air-gapped installs), switching the embedding
  model, which features can be combined, security (gRPC authentication, scoped keys, the encryption keyring and
  rotation, the cluster secret), reliability, observability, and sizing derived from the release notes' measurements.
- Compose overlays, each opt-in and validated with `docker compose config`: `docker-compose.{multilingual,
  multimodal,vision,late-interaction,records,rabitq}.yml` and the HA twins `docker-compose.ha.{multilingual,
  multimodal,late-interaction,records,rabitq}.yml`.
- `k8s-features/`: Kustomize components (`models-cache`, `multilingual`, `multimodal`, `vision`, `records`,
  `late-interaction`, `rabitq`) and overlays; `models-cache` adds a model-cache PVC and a `dakera models pull configured`
  init container; the `vision` overlay is a dedicated stack in its own namespace.
- `docker/.env.example`, `.env.ha.example`: sections per feature, model downloads (mirror, proxy, offline), encryption.
- `examples/production-checklist.md`, `examples/environment-variables.md`: v0.12 features, security, sizing.
- CI validates the HA file, every overlay (single node and HA) and every Kustomize overlay.

### Changed: observability

- `monitoring/` follows what v0.12 emits. Added `monitoring/dakera.rules.yml` (the server's alert rules, loaded by
  Prometheus in the compose files and in `k8s/monitoring/prometheus.yaml`) and replaced the Grafana overview with
  the server's v0.12 dashboard. Removed the alerts and panels that read metrics v0.12 does not emit
  (`dakera_cache_*`, `dakera_l2_cache_*`, `dakera_decay_*`, `dakera_total_vectors`, `dakera_cluster_nodes_total`,
  `dakera_memory_count`, ...) and the replica-count alerts (`dakera_replica_count` is a constant 1 in v0.12, so they
  fired on every node). The HA stack now scrapes `dakera-1..3` as job `dakera` (`monitoring/prometheus.ha.yml`; it
  scraped the non-existent `dakera:3000`) and alerts on the node count.

### Fixed

Found by running every stack against the v0.12.0 server (see docs/features-v0.12.md, "Measured in the
deployment validation"):

- **MinIO images**: `minio/minio` and `minio/mc` are no longer published on Docker Hub (both repositories
  are gone), so a fresh `docker compose pull` / `up` and the `k8s/minio` StatefulSet failed to pull. Every
  file now uses `cgr.dev/chainguard/minio:latest` (it ships `mc`, which `minio-setup` and the health check
  use), run as root like the old image so an existing `minio-data` volume stays writable (checked: a volume
  written by the old image is read and written by the new one).
- **`k8s/minio`**: the bucket was created by an init container that waited for the MinIO of its own pod,
  which starts only after init containers finish: the pod never started. A `postStart` hook creates it now.
- **HA replication**: with the three nodes sharing one Redis (`DAKERA_REDIS_URL`), v0.12.0 reported
  replicated writes as applied but stored nothing on some peers (`written=0`; 3 of 6 node pairs never
  converged in 300 s). The HA file no longer wires Redis (the `redis` service is removed): all 6 pairs then
  converge within 0.1 s. Leader election does not use Redis.
- **HA authentication** defaulted to off (`DAKERA_AUTH_ENABLED:-false`) on a load balancer published on every
  interface; it now defaults to `true` like `docker-compose.yml`.
- **Monitoring**: the MinIO scrape target was down (403: MinIO metrics need `MINIO_PROMETHEUS_AUTH_TYPE=public`,
  now set), so `MinIODown` fired permanently; the memory and CPU alerts read `process_*` and
  `container_spec_memory_limit_bytes`, which nothing scraped here exports (memory now reads
  `dakera_process_resident_bytes`; there is no CPU metric, so no CPU alert); `MinIOHighLatency` read a metric
  MinIO does not export (now `minio_s3_requests_ttfb_seconds_distribution`).
- **`k8s/mcp`** is no longer applied: `dakera-mcp` speaks MCP over stdio only and crash-looped as a pod
  (it also read `DAKERA_API_URL`, not the `DAKERA_URL` the manifest set: fixed in the manifest).
- `docker-compose.local.yml`: the MinIO health check used `curl`, which the MinIO image does not ship.
- README: the server does not refuse to start with authentication on and no key (it starts and rejects
  every authenticated request); `downgrade` also exits 78 when it finds no data; its JSON report is alone
  on stdout only without a TTY (`run -T`).

- Compose files passed to the container only the variables they list, so most of what `docker/.env.example` offered
  (`DAKERA_ENCRYPTION_KEY`, the search and ranking levers, the tiering settings, `DAKERA_MAX_BODY_SIZE`, ...) had no
  effect: encryption stayed off with a key in `.env`. They are now passed (empty = the server default).
- `minio-setup` did not receive `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`, so bucket creation failed once the
  credentials were changed as `.env.example` asks (single node and HA).
- `.env.example`: `DAKERA_SEARCH_MODE` accepts `hybrid`, `binary`, `float`, `scalar`, `rabitq` (not `vector` / `text`);
  `DAKERA_HYBRID_FETCH_MULT` is an integer (default 5x); the defaults of `DAKERA_BM25_DELTA` (1.0), `DAKERA_NAME_BOOST`
  (0.3), `DAKERA_ADAPTIVE_WVEC_THRESHOLD` (0.15), `DAKERA_REQUEST_TIMEOUT` (300) and `DAKERA_MAX_BODY_SIZE` (10 MiB);
  `DAKERA_ONNX_POOL_SIZE` is gone (it applies to the GPU path only).
- `DAKERA_L1_CACHE_SIZE`: the hot-tier budget of tiered storage (default 100000 vectors); a bare byte count at or above
  10 million is read as bytes with a warning, so the compose files use `512MB` and the ConfigMap `1GB`. The devcontainer
  and playground files no longer set it (no tiered storage there, so it only produced a warning).
- Compose `stop_grace_period` is 30 s (the default 10 s killed the server during its graceful shutdown).
- README: the telemetry paragraph (hostname and IP are sent), the defaults of `DAKERA_AUTO_TIER`, `DAKERA_MAX_BODY_SIZE`,
  `DAKERA_REQUEST_TIMEOUT`, `DAKERA_ENCRYPTION_KEY`, and the rollback section (a store on bge-m3, colbert-small or the
  visual lane cannot be downgraded). `examples/production-checklist.md` said the default limits were 4G / 2 CPUs
  (compose: 12G / 4).
- Grafana: the memory-API dashboard referred to a datasource uid that was never provisioned; panels over
  metrics v0.12 does not emit were removed.

### Removed

- `DAKERA_L2_CACHE_PATH` (v0.12 reads no such name), `DAKERA_CACHE_REDIS_URL` (use `DAKERA_REDIS_URL`).
  `DAKERA_S3_ACCESS_KEY` / `DAKERA_S3_SECRET_KEY` / `DAKERA_LOG_LEVEL` are not read either (docs corrected).

## [0.9.0] - 2026-06-25

### Changed

- **Bump default Dakera image to `:latest` across all deployment configs** — removes the stale pinned tags (`optA-baked-ec6ef91` and `0.11.81`) that were 13–30+ server releases behind. All files now default to `ghcr.io/dakera-ai/dakera:latest` which tracks the current stable release automatically. CTO confirmed: all official images since `v0.11.89+` (DAK-6224) include ONNX embedding files — the cold-boot concern that motivated the original pin is resolved.
  - `docker/docker-compose.yml`: `optA-baked-ec6ef91` → `:latest` ([#243](https://github.com/Dakera-AI/dakera-deploy/pull/243))
  - `docker/docker-compose.ha.yml`: `optA-baked-ec6ef91` → `:latest`
  - `docker/docker-compose.local.yml`: `0.11.81` → `:latest`
  - `k8s/dakera/deployment.yaml`: `optA-baked-ec6ef91` → `:latest`

  Operators who need a pinned version can still override via `DAKERA_IMAGE=ghcr.io/dakera-ai/dakera:v0.11.94` in their `.env` file. The `${DAKERA_IMAGE:-...}` pattern is preserved in all compose files.

## [0.8.0] - 2026-05-29

### Changed

- Bump default dakera image `0.11.61` → `0.11.66` across all compose files (docker-compose.yml, docker-compose.ha.yml, docker-compose.local.yml), k8s deployment.yaml, README examples, and production-checklist.md
  - v0.11.62: text_lengths rank fix (DAK-5826)
  - v0.11.63–v0.11.64: async metric recording, pipeline instrumentation
  - v0.11.65: cross-encoder session pool (RERANKER_POOL_SIZE=2, batch reranking Phase 3)
  - v0.11.66: batch ONNX cross-encoder inference (Phase 3 complete, ~2× rerank speedup)

## [0.7.0] - 2026-05-27

### Fixed

- Dakera image default: `0.11.55` → `0.11.59` in docker-compose.yml, docker-compose.ha.yml, docker-compose.local.yml (all three were stale; production was already running 0.11.59)

### Added

- `scripts/runner/runner-health-monitor.sh` — systemd-managed health monitor for all `actions.runner.*` services on ARM/x64 runners. Fires every 5min, auto-restarts failed/OOM-killed runners, sends Telegram alerts. Deployed to both runners (DAK-5764).
- `scripts/runner/runner-disk-cleanup.sh` — automated Rust `target/` directory cleanup for runner work dirs. Cleans stale build artifacts, runs docker prune if disk >80%, alerts Telegram if disk remains >85% after cleanup. ARM: every 6h via cron. x64: every 4h (DAK-5764).
- `scripts/runner/runner-health-monitor.service` + `runner-health-monitor.timer` — systemd unit files for runner health monitoring on runner hosts.
- `scripts/runner/install.sh` — one-command installer for all runner automation on a new runner host.

## [0.6.0] - 2026-05-21

### Fixed

- K8s MCP deployment image: `0.9.2` → `0.10.8` (14 versions behind — aligns with latest release)
- K8s Dashboard version labels: `0.3.28` → `0.3.29` (label/image mismatch)
- Dockerfile: replace invalid `COPY --if=` syntax with valid ARG-gated conditional (`NETSKOPE_CERT=0` default, `COPY certs/ /tmp/certs/` + `RUN if` pattern)
- Dockerfile.dev: apply same ARG-gated Netskope cert pattern as production Dockerfile
- docker-compose.yml ODE sidecar image: `0.9.0` → `0.2.0` (only available tag on GHCR)
- k8s configmap: add `DAKERA_REQUEST_TIMEOUT: "120"` and `DAKERA_MAX_BODY_SIZE: "524288000"` (present in docker-compose, missing in k8s)

### Added

- .env.example: `DAKERA_ENCRYPTION_KEY` (AES-256-GCM at-rest encryption), `DAKERA_REQUEST_TIMEOUT`, `DAKERA_GRPC_ENABLED`
- Dockerfile: source-build notice at top — Dockerfile requires dakera source repo as build context; external users should use pre-built GHCR image or docker-compose.local.yml
- Dockerfile.dev: comment explaining why `rustlang/rust:nightly-bookworm` is used (custom `docker` Cargo profile with unstabilised flags)
- README: "Client Tools" section — `dk` CLI and `npx @dakera-ai/dakera-mcp` quickstart

## [0.5.0] - 2026-05-14

### Security

- **HA compose**: Remove `mc anonymous set download` from MinIO setup — HA stack still had the SA-2026-001 anonymous bucket vulnerability that was fixed in the default compose
- **HA compose**: Replace hardcoded `dk_dev_root_key_change_in_production` fallback in dashboard with required env var (`DAKERA_ROOT_API_KEY` is now required, matching the default compose behavior)

### Changed

- Bump dakera server image: `0.11.48` → `0.11.55` in docker-compose, docker-compose.ha, and k8s deployment
  - v0.11.49–v0.11.55: CE-111 through CE-117 recall improvements, ML classifier tuning, temporal inference, smart scoring weights
- Bump k8s dakera deployment: align version labels (`0.11.40` → `0.11.55`) and image tag (`0.11.42` → `0.11.55`)
- Fix docker-compose.local.yml: replace `build` context (required dakera source) with pre-built GHCR image — the "Zero to Running in 5 Minutes" quickstart now works without cloning the server repo
- Remove deprecated `version: "3.8"` from docker-compose.dev.yml

### Added

- `examples/` directory with deployment guides:
  - `quickstart.md` — store and recall first memory in 5 minutes
  - `environment-variables.md` — complete env var reference including tiered storage, Redis, request limits, and HA port overrides
  - `production-checklist.md` — security, storage, HA, and monitoring checklist
  - `backup-restore.md` — MinIO backup procedures and disaster recovery

### Fixed

- README: HA section listed wrong ports (3000/50051/9001) — corrected to actual HA defaults (3100/50151/9101)
- README: HA architecture diagram showed wrong Prometheus (:9090) and Grafana (:3001) ports — corrected to :9190/:3203
- README: Remove private repo link (`dakera-cli`) from Related Repositories
- README: Add missing environment variable sections (tiered storage, request limits, Redis)
- README: Update version pinning example from v0.9.9 to v0.11.55

## [0.4.2] - 2026-04-25

### Changed

- Bump dakera server image: `0.11.30` → `0.11.34` in docker-compose, Helm chart, k8s deployment, and values.yaml
  - v0.11.31: parallel S3/Minio reads (DAK-2432)
  - v0.11.32: parallel S3 reads fix
  - v0.11.33: HNSW cache invalidation + session-aware recall (DAK-2434) — 82.4% benchmark recall
  - v0.11.34: rustls-webpki RUSTSEC-2026-0104 security patch
- Bump Helm chart version: `0.11.30` → `0.11.34` (Chart.yaml + values.yaml)

## [0.4.1] - 2026-04-13

### Changed

- Bump dakera server image: `0.10.0` → `0.10.1` in docker-compose, docker-compose.ha, Helm chart, and k8s/dakera/deployment.yaml
  - v0.10.1: bge-large-en-v1.5 embedding (1024-dim) + cross-encoder reranking (DAK-1823)
- Bump Helm chart version: `0.10.0` → `0.10.1` (Chart.yaml + values.yaml)

## [0.4.0] - 2026-04-13

### Changed

- Bump dakera server image: `0.9.15` → `0.10.0` in docker-compose, docker-compose.ha, Helm chart, and k8s/dakera/deployment.yaml
  - v0.10.0: CE-10 Memory Compression + CE-12 Smart Routing + BENCH-1 LoCoMo benchmark
- Bump Helm chart version: `0.9.15` → `0.10.0` (Chart.yaml + values.yaml)
- Align docker-compose.ha.yml image tag (was 0.9.14, now 0.10.0)

## [0.3.2] - 2026-04-07

### Changed

- Bump dakera server image: `0.9.13` → `0.9.14` in docker-compose, docker-compose.ha, docker/.env, and k8s/dakera/deployment.yaml
  - v0.9.14: CVSS-gated cargo-audit CI (DAK-1629) + embedding engine warm-up at startup (eliminates cold-start p99 outlier)

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
