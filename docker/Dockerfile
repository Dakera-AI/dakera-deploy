# =============================================================================
# Dakera server image, built from SOURCE: a copy of the engine's own Dockerfile
# at tag v0.12.4 (github.com/Dakera-AI/dakera, Dockerfile), which builds the
# released ghcr.io/dakera-ai/dakera:0.12.4 image. Differences from upstream are
# hadolint-only: inline ignores for the pinned SHA-256 and *TOKENIZER_URL build args
# (DL3064, read as secrets). Re-sync it on every server release.
#
# Run it from the root of a dakera checkout (the build context is the engine
# source, not this repository):
#   git clone --branch v0.12.4 https://github.com/Dakera-AI/dakera && cd dakera
#   docker build -f /path/to/dakera-deploy/docker/Dockerfile -t dakera:0.12.4 .
# Everyone else: use the published image, ghcr.io/dakera-ai/dakera:0.12.4
# (docker/docker-compose.yml pins it).
# =============================================================================

# =============================================================================
# Dakera Dockerfile - Optimized Multi-Stage Build
# =============================================================================
# Features:
#   - Multi-stage build for minimal final image (≤150 MB target post-CE-3)
#   - cargo-chef for dependency caching (fast rebuilds)
#   - Explicit strip stage (belt-and-suspenders with Cargo strip = "symbols")
#   - Non-root user for security (uid/gid 1000 `dakera`)
#   - HuggingFace model cache directory
#   - Health checks for Kubernetes readiness/liveness probes
#   - Distroless runtime (gcr.io/distroless/cc-debian13): glibc, libstdc++,
#     libssl3 and CA certificates, plus Debian's dash as /bin/sh — no curl, no
#     package manager, no coreutils
#
# Base images are pinned by digest (tag@digest; the tag is documentation, the
# digest is what is pulled). Bump a digest with
#   docker buildx imagetools inspect <image>:<tag>
# and re-run a trivy scan of the runtime image (docs/v0.12/docker-models.md).
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Chef - Prepare dependency recipe
# -----------------------------------------------------------------------------
# rust:1.98-slim-trixie
FROM rust:1.98-slim-trixie@sha256:4cd829461bd5c4d511c32e269da9cb8929223b666519d8004e35fc8d1d771ab7 AS chef

RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    libssl-dev \
    libclang-dev \
    clang \
    cmake \
    make \
    g++ \
    libstdc++-13-dev \
    protobuf-compiler \
    && rm -rf /var/lib/apt/lists/*

# Install cargo-chef for dependency caching
RUN cargo install cargo-chef --locked

WORKDIR /app

# -----------------------------------------------------------------------------
# Stage 2: Planner - Analyze dependencies
# -----------------------------------------------------------------------------
FROM chef AS planner

# Copy workspace manifests and source
COPY Cargo.toml Cargo.lock ./
COPY crates/ crates/
COPY config/ config/

# Create recipe.json (list of dependencies)
RUN cargo chef prepare --recipe-path recipe.json

# -----------------------------------------------------------------------------
# Stage 3: Builder - Build dependencies + application
# -----------------------------------------------------------------------------
FROM chef AS builder

# Copy recipe and build dependencies (cached layer)
COPY --from=planner /app/recipe.json recipe.json

# Compute platform-aware RUSTFLAGS once so cook + build use identical flags
# (cache invalidation occurs if flags differ between the two steps).
# - link-arg=-lstdc++: explicit C++ runtime for ORT __cxa_call_terminate
#   (panic=abort + lto=fat omit libstdc++ from default link set — GH#99)
# - target-feature=+fp16: aarch64 only; ENV RUSTFLAGS overrides
#   .cargo/config.toml [target.aarch64-unknown-linux-gnu] rustflags
RUN ARCH="$(uname -m)" && \
    if [ "$ARCH" = "aarch64" ]; then \
      printf 'export RUSTFLAGS="-C link-arg=-lstdc++ -C target-feature=+fp16"\n' > /etc/cargo_rustflags.sh; \
    else \
      printf 'export RUSTFLAGS="-C link-arg=-lstdc++"\n' > /etc/cargo_rustflags.sh; \
    fi

# Cap concurrent rustc processes — 7.5GB x64 runner OOMs with 3+ parallel rustc (DAK-5851)
ENV CARGO_BUILD_JOBS=2

# cargo-chef 0.1.78 does not stub `[[bench]]` targets when reconstructing the cook
# skeleton from recipe.json, so `cargo chef cook` fails to parse crates/engine/Cargo.toml
# ("can't find <name> bench at benches/<name>.rs") once explicit [[bench]] entries exist
# (added in #893). The real bench sources are intentionally excluded from the image
# context (.dockerignore: crates/**/benches/), so create empty stubs for each declared
# engine bench purely to satisfy manifest validation — `cargo build` never compiles
# benches, and this dir is not carried into the runtime image. If a [[bench]] is added
# to crates/engine/Cargo.toml, add its name here and in Dockerfile.gpu; PR Guardrails
# (scripts/check_dockerfile_bench_stubs.py) fails until both list it. DAK-9959.
RUN mkdir -p crates/engine/benches && \
    for b in concurrent_load graph_edges index_comparison insert_benchmark query_benchmark scale_recall search_modes; do \
      printf 'fn main() {}\n' > "crates/engine/benches/$b.rs"; \
    done && \
    . /etc/cargo_rustflags.sh && cargo chef cook --release --recipe-path recipe.json

# Copy source code and build the application
COPY Cargo.toml Cargo.lock ./
COPY crates/ crates/
COPY config/ config/

# Embed git SHA so /health can identify the exact build for hotfix deploys (DAK-6265)
ARG BUILD_SHA=dev
# The release binary. It also bakes the models (stage 4c: `dakera models pull
# --bake`), so the ORT-format copies are named by the very binary that maps
# them (same build, same ONNX Runtime).
RUN . /etc/cargo_rustflags.sh && cargo build --release --bin dakera

# Verify binary exists and is executable
RUN ls -la /app/target/release/dakera && \
    /app/target/release/dakera --help || true

# -----------------------------------------------------------------------------
# Stage 4: Stripper - Belt-and-suspenders binary strip
# -----------------------------------------------------------------------------
# Cargo.toml already sets strip = "symbols", but explicitly running strip
# here ensures the binary is fully stripped even in cross-compilation scenarios
# and makes the intent clear for auditing purposes.
FROM builder AS stripper

RUN apt-get update && apt-get install -y --no-install-recommends \
    binutils \
    && rm -rf /var/lib/apt/lists/*

RUN strip --strip-all /app/target/release/dakera

# -----------------------------------------------------------------------------
# Stage 4b: Model fetch - bake the CPU embedding model into the image (DAK-6229)
# -----------------------------------------------------------------------------
# Previously the bge-large ONNX model + tokenizer were downloaded from HuggingFace
# at CONTAINER STARTUP into an empty /app/models. That runtime download was
# intermittently corrupted ("Protobuf parsing failed"), so the embedding engine
# warm-up failed and the DAK-6181 fail-loud readiness gate aborted — repeatedly
# killing the Option A bench gate (e.g. dakera-bench run 26829877646). Baking the
# artifact at BUILD time with a pinned SHA-256 makes a corrupt download fail the
# BUILD (never the runtime) and removes the runtime network dependency entirely
# (self-contained, DAK-6203). Verified-existing upstream repos only.
#
# The layout is the model cache's (model_files::model_cache_dir,
# <root>/dakera/<repo with '/'->'--'>/...), which the image's model store
# shares, so stage 4c and the loaders find the files where they look.
#
# Scope: the models a default CPU start uses — the embedding model (INT8,
# 337 MB, onnx/model_quantized.onnx @ Xenova/bge-large-en-v1.5), the reranker
# (INT8, 570 MB), GLiNER for entity extraction (gliner-bi-small, 118 MB, and
# gliner-x-small, 189 MB, Dakera's int8 builds) and the forget-request
# detector's encoder (INT8, 118 MB); `default_image_models()` in
# crates/inference/src/model_catalog.rs is the list. Opt-in models (whisper,
# vision, gliner-multi, other embedding rows) are pulled on first use or baked
# by a derived image. The GPU FP32 model
# (onnx/model.onnx, 1.34 GB) is a separate image-size decision and is still
# fetched at runtime (guarded by the DAK-5976 truncation check); baking the CPU
# file does NOT affect the GPU path — it reads a different filename.
# debian:trixie-slim — build-only stage (curl fetches the models); never shipped
FROM debian:trixie-slim@sha256:62bd423aeee912639ca8ee681c2b762cb3e25137e0a92b20be455898a9f034ad AS model-fetch

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Every file comes from Dakera's copy (huggingface.co/DakeraAI) first, then
# from its own repository, and is kept only with its pinned SHA-256.
COPY scripts/docker/fetch-model.sh /usr/local/bin/fetch-model

# Pinned content hashes (LFS oid / sha256sum) — bump these when the upstream
# artifact legitimately changes; a mismatch fails the build loudly by design.
# DAK-6272: ONNX_SHA256 is the SAME pin as EmbeddingModel::expected_onnx_sha256
# (crates/inference/src/models.rs) — the runtime startup integrity guard verifies
# the baked/cached file against this exact hash and re-fetches once if it is
# corrupt. Keep the two values in sync when bumping the upstream artifact.
ARG ONNX_URL=https://huggingface.co/Xenova/bge-large-en-v1.5/resolve/main/onnx/model_quantized.onnx
# hadolint ignore=DL3064
ARG ONNX_SHA256=4842b56e233be1cc74770f57f63b1ebb6cf357cca3dd73fcdec35c019f8a5d6e
# hadolint ignore=DL3064
ARG TOKENIZER_URL=https://huggingface.co/BAAI/bge-large-en-v1.5/resolve/main/tokenizer.json
# hadolint ignore=DL3064
ARG TOKENIZER_SHA256=d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66

# DAK-7190 (CE-C): bake the cross-encoder reranker (bge-reranker-v2-m3 INT8) too.
# The runtime reranker download of this 570 MB model from HuggingFace timed out
# during container startup, so the server never became ready and both CE-C bench
# runs failed (purely infra, code was fine). Baking it at BUILD time — same
# pinned-SHA pattern as the embedding model — removes the startup network fetch
# entirely. Layout mirrors the reranker's `download_reranker_files` cache resolver
# (`$HF_HOME/dakera/<repo '/'->'--'>/...`), which is now HF_HOME-aware, so the
# engine finds the file in cache and skips the download. SHAs are the upstream LFS
# oids (verified live in-session). Only the two files the Rust tokenizers loader
# consumes are baked (tokenizer.json + model_int8.onnx).
ARG RERANKER_ONNX_URL=https://huggingface.co/onnx-community/bge-reranker-v2-m3-ONNX/resolve/main/onnx/model_int8.onnx
# hadolint ignore=DL3064
ARG RERANKER_ONNX_SHA256=912fc1215c2dbff6499700534bd8d31253af01573861abbfc43afd1fab6cce5d
# hadolint ignore=DL3064
ARG RERANKER_TOKENIZER_URL=https://huggingface.co/onnx-community/bge-reranker-v2-m3-ONNX/resolve/main/tokenizer.json
# hadolint ignore=DL3064
ARG RERANKER_TOKENIZER_SHA256=8bf8afbfd11306bd872018c53bfdf2e160a56f8edbcf49933324404791c148d3

RUN set -eux; \
    fetch-model /models/dakera/Xenova--bge-large-en-v1.5/onnx/model_quantized.onnx \
      "$ONNX_SHA256" "$ONNX_URL" 600; \
    fetch-model /models/dakera/BAAI--bge-large-en-v1.5/tokenizer.json \
      "$TOKENIZER_SHA256" "$TOKENIZER_URL" 60

# DAK-7190: reranker (bge-reranker-v2-m3) bake — separate RUN so a re-pin of either
# model does not invalidate the other's build-cache layer.
RUN set -eux; \
    fetch-model /models/dakera/onnx-community--bge-reranker-v2-m3-ONNX/onnx/model_int8.onnx \
      "$RERANKER_ONNX_SHA256" "$RERANKER_ONNX_URL" 900; \
    fetch-model /models/dakera/onnx-community--bge-reranker-v2-m3-ONNX/tokenizer.json \
      "$RERANKER_TOKENIZER_SHA256" "$RERANKER_TOKENIZER_URL" 60

# Entity extraction (GLiNER: the English default, gliner-bi-small, and the
# multilingual one a multilingual embedding model selects, gliner-x-small —
# Dakera's int8 builds, scripts/gliner_compact) and the forget-request
# detector's own encoder (multilingual-minilm INT8,
# crates/api/src/forget_intent.rs). Both used to be downloaded on first use:
# the first store into a namespace with entity extraction waited for the
# model, a first request to forget for a 118 MB one, and an air-gapped
# container never got either. Same pinned-SHA pattern; the pins are the
# registry's (GlinerSpec in crates/inference/src/ner.rs, the
# multilingual-minilm row in crates/core-types/src/model.rs;
# `container_image_models.rs` checks them). The tokenizers are pinned by
# sha256sum of the files.
ARG GLINER_ONNX_URL=https://huggingface.co/DakeraAI/gliner-bi-small-v2.0-int8/resolve/main/onnx/model.onnx
# hadolint ignore=DL3064
ARG GLINER_ONNX_SHA256=1fa420c63c757863c3296a450e00d9ec155597dffb57771a15d77e416e2bc379
# hadolint ignore=DL3064
ARG GLINER_TOKENIZER_URL=https://huggingface.co/DakeraAI/gliner-bi-small-v2.0-int8/resolve/main/tokenizer.json
# hadolint ignore=DL3064
ARG GLINER_TOKENIZER_SHA256=2315a8bea85452f3c4e8ce980f7853cac013820238e7776a4e48159037a5f164
ARG GLINER_LABELS_ONNX_URL=https://huggingface.co/DakeraAI/gliner-bi-small-v2.0-int8/resolve/main/onnx/labels_encoder.onnx
# hadolint ignore=DL3064
ARG GLINER_LABELS_ONNX_SHA256=b3e1fb9a10335c72d96d320b0af0292840c3cbee7b4868e3f24c9a81794d078a
# hadolint ignore=DL3064
ARG GLINER_LABELS_TOKENIZER_URL=https://huggingface.co/DakeraAI/gliner-bi-small-v2.0-int8/resolve/main/labels_tokenizer.json
# hadolint ignore=DL3064
ARG GLINER_LABELS_TOKENIZER_SHA256=91f1def9b9391fdabe028cd3f3fcc4efd34e5d1f08c3bf2de513ebb5911a1854
ARG GLINER_MULTI_ONNX_URL=https://huggingface.co/DakeraAI/gliner-x-small-int8/resolve/main/onnx/model.onnx
# hadolint ignore=DL3064
ARG GLINER_MULTI_ONNX_SHA256=2f6f0a848f9210d0fb7c30f1b35a952509afa198edf872aaab7f19527a33cede
# hadolint ignore=DL3064
ARG GLINER_MULTI_TOKENIZER_URL=https://huggingface.co/DakeraAI/gliner-x-small-int8/resolve/main/tokenizer.json
# hadolint ignore=DL3064
ARG GLINER_MULTI_TOKENIZER_SHA256=fa84928bec4c38fdf40a153724857ba1ba86aa3789d9801251bed82c8eaa033d
ARG FORGET_ONNX_URL=https://huggingface.co/Xenova/paraphrase-multilingual-MiniLM-L12-v2/resolve/main/onnx/model_int8.onnx
# hadolint ignore=DL3064
ARG FORGET_ONNX_SHA256=d6ea442ff6a891daefed7c83b2f596fc5dc66bf697e4d006236f64f34bbcf4c8
# hadolint ignore=DL3064
ARG FORGET_TOKENIZER_URL=https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2/resolve/main/tokenizer.json
# hadolint ignore=DL3064
ARG FORGET_TOKENIZER_SHA256=2c3387be76557bd40970cec13153b3bbf80407865484b209e655e5e4729076b8

RUN set -eux; \
    g=/models/dakera/DakeraAI--gliner-bi-small-v2.0-int8; \
    fetch-model "$g/onnx/model.onnx" "$GLINER_ONNX_SHA256" "$GLINER_ONNX_URL" 600; \
    fetch-model "$g/tokenizer.json" "$GLINER_TOKENIZER_SHA256" "$GLINER_TOKENIZER_URL" 60; \
    fetch-model "$g/onnx/labels_encoder.onnx" "$GLINER_LABELS_ONNX_SHA256" "$GLINER_LABELS_ONNX_URL" 300; \
    fetch-model "$g/labels_tokenizer.json" "$GLINER_LABELS_TOKENIZER_SHA256" "$GLINER_LABELS_TOKENIZER_URL" 60; \
    m=/models/dakera/DakeraAI--gliner-x-small-int8; \
    fetch-model "$m/onnx/model.onnx" "$GLINER_MULTI_ONNX_SHA256" "$GLINER_MULTI_ONNX_URL" 900; \
    fetch-model "$m/tokenizer.json" "$GLINER_MULTI_TOKENIZER_SHA256" "$GLINER_MULTI_TOKENIZER_URL" 120

RUN set -eux; \
    fetch-model /models/dakera/Xenova--paraphrase-multilingual-MiniLM-L12-v2/onnx/model_int8.onnx \
      "$FORGET_ONNX_SHA256" "$FORGET_ONNX_URL" 600; \
    fetch-model /models/dakera/sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2/tokenizer.json \
      "$FORGET_TOKENIZER_SHA256" "$FORGET_TOKENIZER_URL" 60

# -----------------------------------------------------------------------------
# Stage 4c: the image's model store, in final form
# -----------------------------------------------------------------------------
# `dakera models pull --bake` — the server's own code — verifies the fetched
# files against the registry's pins (the same as the ARGs above), converts each
# graph to the ORT-format copy the CPU sessions memory-map (named for THIS
# build and ONNX Runtime), and keeps only that copy: a start finds it by the
# pinned hash, without the ONNX original, and converts nothing (the original
# would only be needed to convert again, which this build never does — half
# the models' share of the image). HF_HUB_OFFLINE: the files are the ones
# fetched above, never a second download.
#
# The store is installed at /usr/local/share/dakera/models (stage 5), NOT in the
# model cache /app/models: a volume mounted there (a named volume kept across
# upgrades, a bind mount, a Kubernetes volume) can no longer hide or outdate
# what the image ships (see crates/inference/src/model_store.rs).
FROM builder AS model-convert
COPY --from=model-fetch /models /models
RUN HF_HUB_OFFLINE=1 /app/target/release/dakera models pull --bake --dir /models \
      bge-large bge-reranker-v2-m3 gliner-bi-small gliner-x-small multilingual-minilm

# -----------------------------------------------------------------------------
# Stage 5a: Runtime base
# -----------------------------------------------------------------------------
# Distroless cc (Debian 13, the release the binary is built on): glibc,
# libgcc, libstdc++ (ONNX Runtime is linked in statically but is C++),
# libssl3, zlib, zstd, CA certificates and tzdata. No package manager and no
# curl (issue #920 F6): the image's HEALTHCHECK, and any probe run inside the
# container, is `dakera healthcheck [PATH]`; Kubernetes uses httpGet probes.
# One addition (stage 5b): Debian's dash as /bin/sh, so `CMD-SHELL` health
# checks and `docker exec … sh` keep working — the deployed compose files use
# a CMD-SHELL check that runs on images with and without curl.
# gcr.io/distroless/cc-debian13:nonroot
FROM gcr.io/distroless/cc-debian13:nonroot@sha256:3ee00291cf386ec52a552e6a858d555debd74776eb4bfa53fa3df2cd6677515e AS runtime-base

# -----------------------------------------------------------------------------
# Stage 5b: Runtime filesystem skeleton (build-only, never shipped)
# -----------------------------------------------------------------------------
# The user entry, the directories it owns and the shell are prepared here (in
# the model-fetch stage's Debian 13) and copied in: the `dakera` entries are
# appended to the base's own /etc/passwd and /etc/group; /usr/bin/dash (needs
# only libc) with /usr/bin/sh -> dash, and dash's dpkg record in
# /var/lib/dpkg/status.d (distroless's package database), so image scanners
# and the SBOM see the shell and its version. uid/gid 1000 `dakera` is unchanged
# from the earlier Debian image: volumes created by it stay writable.
# The data root's standard subdirectories exist in the image, owned by the
# runtime user: a named volume mounted on one of them (a compose file keeping
# the hot tier or warm cache on its own volume) is initialised from the
# image's directory and so owned by `dakera` too; a path the image lacks is
# created root-owned and the server cannot open it. Empty directories are not
# data: a fresh install stays fresh. The image's model store is owned by the
# runtime user so a derived image can add to it (`RUN dakera models pull
# --bake whisper vision`).
FROM model-fetch AS runtime-fs
COPY --from=runtime-base /etc/passwd /etc/group /rootfs/etc/
RUN groupadd --gid 1000 dakera && \
    useradd --uid 1000 --gid dakera --shell /sbin/nologin --home-dir /home/dakera --no-create-home dakera && \
    grep '^dakera:' /etc/passwd >> /rootfs/etc/passwd && \
    grep '^dakera:' /etc/group >> /rootfs/etc/group
RUN mkdir -p /rootfs/usr/bin /rootfs/var/lib/dpkg/status.d && \
    cp /usr/bin/dash /rootfs/usr/bin/dash && \
    ln -s dash /rootfs/usr/bin/sh && \
    dpkg-query --status dash > /rootfs/var/lib/dpkg/status.d/dash && \
    cp /var/lib/dpkg/info/dash.md5sums /rootfs/var/lib/dpkg/status.d/dash.md5sums
RUN mkdir -p /data/wal /data/wal-snapshots /data/hot /data/cache/warm /data/cluster-outbox /app/models /usr/local/share/dakera/models /home/dakera && \
    chown -R dakera:dakera /app /data /usr/local/share/dakera /home/dakera

# -----------------------------------------------------------------------------
# Stage 5: Runtime - Minimal production image (distroless, see stage 5a)
# -----------------------------------------------------------------------------
FROM runtime-base AS runtime

# The base's users plus `dakera` (uid/gid 1000); root-owned, like the base's.
COPY --from=runtime-fs --chown=0:0 /rootfs/etc/passwd /rootfs/etc/group /etc/
# /bin/sh (dash) and its dpkg record; /bin is a link to /usr/bin in the base.
COPY --from=runtime-fs --chown=0:0 /rootfs/usr/bin/ /usr/bin/
COPY --from=runtime-fs --chown=0:0 /rootfs/var/lib/dpkg/status.d/ /var/lib/dpkg/status.d/
# The data root (DAKERA_STORAGE_PATH=/data: every local path — WAL, hot/warm
# tiers, knowledge graph, filesystem backend — derives from it), the model
# cache (HF_HOME: models downloaded on first use), the image's model store and
# the user's home, all owned by `dakera`.
COPY --from=runtime-fs --chown=dakera:dakera /data /data
COPY --from=runtime-fs --chown=dakera:dakera /app /app
COPY --from=runtime-fs --chown=dakera:dakera /usr/local/share/dakera /usr/local/share/dakera
COPY --from=runtime-fs --chown=dakera:dakera /home/dakera /home/dakera

# Copy the stripped binary (root-owned, mode 0755)
COPY --from=stripper --chown=0:0 /app/target/release/dakera /usr/local/bin/dakera

# DAK-6203: The DAK-6129 "bundle vocab_matrix.bin from dakera-ai/bge-large-model2vec-256d"
# step was removed. That HuggingFace repo (and the entire dakera-ai HF org) never existed
# — the build-arg download was a hallucinated fix for a phantom 401/404. The Model2Vec
# StaticBackend now loads its matrix from a local file named by DAKERA_MODEL2VEC_PATH; if
# unset, TieredEngine cleanly falls back to the ONNX transformer for writes. No HF_TOKEN
# build arg is required.

# The models the image ships (DAK-6229 / DAK-7190 / D11), in the image's model
# store: the default embedding model and the reranker as the ORT-format copies
# the CPU sessions map, plus their tokenizers. Read before the model cache by
# every loader, so a default start needs no network, converts nothing and
# writes nothing — whatever is mounted at /app/models, read-only root included.
COPY --from=model-convert --chown=dakera:dakera /models/dakera /usr/local/share/dakera/models/dakera

# Switch to the non-root user (numeric, so Kubernetes `runAsNonRoot` can verify
# it without a `runAsUser`; it is `dakera` in /etc/passwd)
USER 1000:1000
WORKDIR /app

# Environment variables
# - HF_HOME: the model cache — models the image does not ship, downloaded on
#   first use (or pulled ahead: `dakera models pull <model>`)
# - DAKERA_STORAGE_PATH: the data root; mount ONE volume here
# - RUST_LOG: Default logging level
# - RUST_BACKTRACE: Enable backtraces for debugging
# - SSL_CERT_*: TLS certificates for HuggingFace/HTTPS model downloads
ENV HF_HOME=/app/models \
    DAKERA_STORAGE_PATH=/data \
    RUST_LOG=info \
    RUST_BACKTRACE=1 \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_DIR=/etc/ssl/certs \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

# Expose ports
# - 3000: REST API (default; override with DAKERA_PORT env var)
# - 50051: gRPC API (if enabled)
EXPOSE 3000 50051

# Health check - verify API is responsive
# `dakera healthcheck` (no shell, no curl) sends GET /health to 127.0.0.1 (or
# DAKERA_HOST when it is a specific address) on DAKERA_PORT (default 3000), so
# the check works regardless of the configured port; it exits 0 only on 200.
# The port answers while the server starts (TRACKER H3): /health is 503
# "starting" until the models are loaded. The shipped models load in seconds;
# a model the image does not ship (DAKERA_MODEL=bge-m3, colbert-small, ...)
# downloads first unless it was pulled ahead. Failures inside the start period
# do not count, and the first success ends it, so a generous start period costs
# a fast start nothing.
HEALTHCHECK --interval=30s --timeout=5s --start-period=600s --retries=3 \
    CMD ["dakera", "healthcheck"]

# Volumes: the data root and the model cache. Before v0.12 the data root was
# /app/data; a server that finds data there and none under /data refuses to
# start and says how to move or pin it. A model volume kept from an earlier
# image holds that image's copies of the shipped models, which this image no
# longer reads: `dakera models prune` frees them.
VOLUME ["/data", "/app/models"]

# Default command
ENTRYPOINT ["dakera"]
CMD []
