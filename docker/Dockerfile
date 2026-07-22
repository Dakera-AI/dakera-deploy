# Dakera API Dockerfile
# Multi-stage build with dependency layer caching for fast rebuilds
#
# IMPORTANT: This Dockerfile builds Dakera from SOURCE — it is intended to be run from
# the root of the private dakera source repository (not from dakera-deploy alone).
# External users should use the pre-built GHCR image instead:
#   ghcr.io/dakera-ai/dakera:latest
# or docker-compose.local.yml which pulls the pre-built image directly.
#
# Build strategy:
#   1. Copy only Cargo manifests + create stub source files
#   2. Compile all dependencies (cached in Docker layer until Cargo.toml/lock change)
#   3. Copy real source and rebuild (only recompiles your code, deps already done)
#
# Build:
#   docker compose --profile ha build dakera-1
#   # or standalone (from dakera source repo root):
#   docker build -t dakera-api:latest -f deploy/Dockerfile .

# ============================================================================
# Build Stage
# ============================================================================
FROM rust:1.97-bookworm AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    cmake \
    clang \
    mold \
    libclang-dev \
    librocksdb-dev \
    libssl-dev \
    pkg-config \
    protobuf-compiler \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Override release profile for faster Docker builds:
# - thin LTO (90% of fat LTO benefit at ~2x less link time)
# - opt-level 2 (faster compile than 3, ~95% of runtime perf)
# - codegen-units 8 (parallel code generation)
ENV CARGO_PROFILE_RELEASE_LTO=thin
ENV CARGO_PROFILE_RELEASE_OPT_LEVEL=2
ENV CARGO_PROFILE_RELEASE_CODEGEN_UNITS=8
# Use mold linker (10-50x faster linking than default ld)
ENV RUSTFLAGS="-C linker=clang -C link-arg=-fuse-ld=mold"

# Optional: corporate proxy / Netskope CA certificate injection.
# Only used for internal Dakera builds behind a corporate MITM proxy.
# External users: leave NETSKOPE_CERT blank (the default) — no cert file needed.
# Internal users: place your CA bundle at certs/netskope-ca.crt, then:
#   docker build --build-arg NETSKOPE_CERT=1 ...
ARG NETSKOPE_CERT=0
COPY certs/ /tmp/certs/
WORKDIR /tmp
RUN mkdir -p /usr/local/share/ca-certificates/netskope && \
    if [ "${NETSKOPE_CERT}" = "1" ] && [ -f /tmp/certs/netskope-ca.crt ]; then \
        csplit -f netskope-cert- -b '%02d.crt' certs/netskope-ca.crt '/-----BEGIN CERTIFICATE-----/' '{*}' && \
        rm -f netskope-cert-00.crt && \
        mv netskope-cert-*.crt /usr/local/share/ca-certificates/netskope/ && \
        update-ca-certificates; \
    fi

# Set SSL cert environment variables for cargo
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_DIR=/etc/ssl/certs
ENV CARGO_HTTP_CAINFO=/etc/ssl/certs/ca-certificates.crt
# Force openssl-sys to dynamically link against system OpenSSL (not vendored/static)
ENV OPENSSL_NO_VENDOR=1

WORKDIR /usr/src/dakera

# ---------------------------------------------------------------------------
# Layer 1: Dependency compilation (cached unless Cargo.toml/lock change)
# ---------------------------------------------------------------------------

# Copy workspace manifests and vendored deps
COPY Cargo.toml Cargo.lock ./
COPY vendor ./vendor

# Copy all crate Cargo.toml files for workspace resolution
COPY crates/api/Cargo.toml crates/api/Cargo.toml
COPY crates/common/Cargo.toml crates/common/Cargo.toml
COPY crates/storage/Cargo.toml crates/storage/Cargo.toml
COPY crates/engine/Cargo.toml crates/engine/Cargo.toml
COPY crates/inference/Cargo.toml crates/inference/Cargo.toml
COPY crates/client/Cargo.toml crates/client/Cargo.toml
COPY crates/cli/Cargo.toml crates/cli/Cargo.toml
COPY crates/mcp/Cargo.toml crates/mcp/Cargo.toml
COPY crates/dashboard/Cargo.toml crates/dashboard/Cargo.toml

# Copy build.rs and proto files (needed by tonic_build during dep compilation)
COPY crates/api/build.rs crates/api/build.rs
COPY crates/api/proto crates/api/proto

# Create stub source files so cargo can resolve the workspace and compile deps
RUN mkdir -p crates/api/src && echo 'fn main() {}' > crates/api/src/main.rs && \
    mkdir -p crates/common/src && echo '' > crates/common/src/lib.rs && \
    mkdir -p crates/storage/src && echo '' > crates/storage/src/lib.rs && \
    mkdir -p crates/engine/src && echo '' > crates/engine/src/lib.rs && \
    mkdir -p crates/inference/src && echo '' > crates/inference/src/lib.rs && \
    mkdir -p crates/client/src && echo '' > crates/client/src/lib.rs && \
    mkdir -p crates/cli/src && echo 'fn main() {}' > crates/cli/src/main.rs && \
    mkdir -p crates/mcp/src && echo 'fn main() {}' > crates/mcp/src/main.rs && \
    mkdir -p crates/dashboard/src && echo '' > crates/dashboard/src/lib.rs

# Compile dependencies with stubs (this layer is cached until Cargo.toml/lock change)
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/usr/local/cargo/git \
    --mount=type=cache,target=/usr/src/dakera/target \
    cargo build --release --bin dakera 2>&1 || true

# ---------------------------------------------------------------------------
# Layer 2: Real source compilation (only your code recompiles)
# ---------------------------------------------------------------------------

# Copy real source (this invalidates the layer, but deps are already compiled above)
COPY crates ./crates

# Touch source files so cargo detects them as newer than stubs
RUN find crates -name "*.rs" -exec touch {} +

# Build the release binary with real source
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/usr/local/cargo/git \
    --mount=type=cache,target=/usr/src/dakera/target \
    cargo build --release --bin dakera && \
    cp /usr/src/dakera/target/release/dakera /usr/local/bin/dakera

# ============================================================================
# Runtime Stage
# ============================================================================
FROM debian:bookworm-slim AS runtime

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    librocksdb7.8 \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Copy custom CA certificates from builder (only populated when NETSKOPE_CERT=1)
ARG NETSKOPE_CERT=0
COPY --from=builder /usr/local/share/ca-certificates/netskope/ /usr/local/share/ca-certificates/netskope/
RUN update-ca-certificates

# Set SSL cert environment variables for runtime
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_DIR=/etc/ssl/certs
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV REQWEST_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

# Create non-root user
RUN useradd --create-home --shell /bin/bash dakera

# Copy the binary from builder
COPY --from=builder /usr/local/bin/dakera /usr/local/bin/dakera

# Create data directories
RUN mkdir -p /data/cache /data/rocksdb /data/vectors /data/models && \
    chown -R dakera:dakera /data

# Switch to non-root user
USER dakera
WORKDIR /home/dakera

# Environment variables
ENV RUST_LOG=info
ENV DAKERA_HOST=0.0.0.0
ENV DAKERA_PORT=3000
ENV DAKERA_GRPC_PORT=50051
ENV DAKERA_CACHE_DIR=/data/cache
ENV DAKERA_ROCKSDB_PATH=/data/rocksdb
ENV HF_HOME=/home/dakera/.cache/huggingface

# Expose ports
EXPOSE 3000 50051

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://127.0.0.1:3000/health || exit 1

CMD ["dakera"]
