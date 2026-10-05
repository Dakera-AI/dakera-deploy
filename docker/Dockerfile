# =============================================================================
# Dakera server image, built from SOURCE: a copy of the engine's own Dockerfile
# at tag v0.12.1 (github.com/Dakera-AI/dakera, Dockerfile), which builds the
# released ghcr.io/dakera-ai/dakera:0.12.1 image. Differences from upstream are
# hadolint-only: inline ignores for the pinned SHA-256 and TOKENIZER_URL build args
# (DL3064, read as secrets) and the `echo | sha256sum -c` pipes (DL4006), and the
# HEALTHCHECK in exec form (DL3025). Re-sync it on every server release.
#
# Run it from the root of a dakera checkout (the build context is the engine
# source, not this repository):
#   git clone --branch v0.12.1 https://github.com/Dakera-AI/dakera && cd dakera
#   docker build -f /path/to/dakera-deploy/docker/Dockerfile -t dakera:0.12.1 .
# Everyone else: use the published image, ghcr.io/dakera-ai/dakera:0.12.1
# (docker/docker-compose.yml pins it).
# =============================================================================

# =============================================================================
# Dakera Dockerfile - Optimized Multi-Stage Build
# =============================================================================
# Features:
#   - Multi-stage build for minimal final image (≤150 MB target post-CE-3)
#   - cargo-chef for dependency caching (fast rebuilds)
#   - Explicit strip stage (belt-and-suspenders with Cargo strip = "symbols")
#   - Non-root user for security
#   - HuggingFace model cache directory
#   - Health checks for Kubernetes readiness/liveness probes
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Chef - Prepare dependency recipe
# -----------------------------------------------------------------------------
FROM rust:1.95-slim-trixie AS chef

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
# to crates/engine/Cargo.toml, add its name here (the release image build will fail loudly
# with the missing name until then). DAK-9959.
RUN mkdir -p crates/engine/benches && \
    for b in concurrent_load index_comparison insert_benchmark query_benchmark scale_recall search_modes; do \
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
# Scope: only the default CPU INT8 quantized model is baked (337 MB,
# onnx/model_quantized.onnx @ Xenova/bge-large-en-v1.5). The GPU FP32 model
# (onnx/model.onnx, 1.34 GB) is a separate image-size decision and is still
# fetched at runtime (guarded by the DAK-5976 truncation check); baking the CPU
# file does NOT affect the GPU path — it reads a different filename.
FROM debian:trixie-slim AS model-fetch

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

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

# hadolint ignore=DL4006
RUN set -eux; \
    onnx_dir=/models/dakera/Xenova--bge-large-en-v1.5/onnx; \
    tok_dir=/models/dakera/BAAI--bge-large-en-v1.5; \
    mkdir -p "$onnx_dir" "$tok_dir"; \
    curl -fSL \
      --retry 20 --retry-all-errors --retry-delay 30 --retry-max-time 1800 \
      --connect-timeout 30 --max-time 600 \
      -o "$onnx_dir/model_quantized.onnx" "$ONNX_URL"; \
    echo "${ONNX_SHA256}  $onnx_dir/model_quantized.onnx" | sha256sum -c -; \
    curl -fSL \
      --retry 10 --retry-all-errors --retry-delay 10 --retry-max-time 300 \
      --connect-timeout 30 --max-time 60 \
      -o "$tok_dir/tokenizer.json" "$TOKENIZER_URL"; \
    echo "${TOKENIZER_SHA256}  $tok_dir/tokenizer.json" | sha256sum -c -

# DAK-7190: reranker (bge-reranker-v2-m3) bake — separate RUN so a re-pin of either
# model does not invalidate the other's build-cache layer.
# hadolint ignore=DL4006
RUN set -eux; \
    rr_onnx_dir=/models/dakera/onnx-community--bge-reranker-v2-m3-ONNX/onnx; \
    rr_dir=/models/dakera/onnx-community--bge-reranker-v2-m3-ONNX; \
    mkdir -p "$rr_onnx_dir"; \
    echo "Downloading reranker INT8 ONNX (~570 MB) …"; \
    curl -fSL \
      --retry 20 --retry-all-errors --retry-delay 30 --retry-max-time 1800 \
      --connect-timeout 30 --max-time 900 \
      -o "$rr_onnx_dir/model_int8.onnx" "$RERANKER_ONNX_URL"; \
    echo "${RERANKER_ONNX_SHA256}  $rr_onnx_dir/model_int8.onnx" | sha256sum -c -; \
    curl -fSL \
      --retry 10 --retry-all-errors --retry-delay 10 --retry-max-time 300 \
      --connect-timeout 30 --max-time 60 \
      -o "$rr_dir/tokenizer.json" "$RERANKER_TOKENIZER_URL"; \
    echo "${RERANKER_TOKENIZER_SHA256}  $rr_dir/tokenizer.json" | sha256sum -c -

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
      bge-large bge-reranker-v2-m3

# -----------------------------------------------------------------------------
# Stage 5: Runtime - Minimal production image
# -----------------------------------------------------------------------------
FROM debian:trixie-slim AS runtime

# Install runtime dependencies
# - ca-certificates: HTTPS for HuggingFace model downloads
# - libssl3: TLS support
# - curl: Health check support
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libssl3 \
    libstdc++6 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN groupadd --gid 1000 dakera && \
    useradd --uid 1000 --gid dakera --shell /bin/bash --create-home dakera

# Create the data root (DAKERA_STORAGE_PATH=/data: every local path — WAL,
# hot/warm tiers, knowledge graph, filesystem backend — derives from it), the
# model cache (HF_HOME: models downloaded on first use) and the image's model
# store (owned by the runtime user so a derived image can add to it:
# `RUN dakera models pull --bake whisper vision`)
# The data root's standard subdirectories exist in the image, owned by the
# runtime user: a named volume mounted on one of them (a compose file
# keeping the hot tier or warm cache on its own volume) is initialised from
# the image's directory and so owned by `dakera` too; a path the image lacks
# is created root-owned and the server cannot open it. Empty directories are
# not data: a fresh install stays fresh.
RUN mkdir -p /data/wal /data/wal-snapshots /data/hot /data/cache/warm /data/cluster-outbox /app/models /usr/local/share/dakera/models && \
    chown -R dakera:dakera /app /data /usr/local/share/dakera

# Copy the stripped binary
COPY --from=stripper /app/target/release/dakera /usr/local/bin/dakera
RUN chmod +x /usr/local/bin/dakera

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

# Switch to non-root user
USER dakera
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
# Uses DAKERA_PORT env var so the check works regardless of configured port.
# The port answers while the server starts (TRACKER H3): /health is 503
# "starting" until the models are loaded. The shipped models load in seconds;
# a model the image does not ship (DAKERA_MODEL=bge-m3, colbert-small, ...)
# downloads first unless it was pulled ahead. Failures inside the start period
# do not count, and the first success ends it, so a generous start period costs
# a fast start nothing.
HEALTHCHECK --interval=30s --timeout=5s --start-period=600s --retries=3 \
    CMD ["sh", "-c", "curl -f http://127.0.0.1:${DAKERA_PORT:-3000}/health || exit 1"]

# Volumes: the data root and the model cache. Before v0.12 the data root was
# /app/data; a server that finds data there and none under /data refuses to
# start and says how to move or pin it. A model volume kept from an earlier
# image holds that image's copies of the shipped models, which this image no
# longer reads: `dakera models prune` frees them.
VOLUME ["/data", "/app/models"]

# Default command
ENTRYPOINT ["dakera"]
CMD []
