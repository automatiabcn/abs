FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

FROM base AS builder
# Build deps for the chromadb rust binding + patch_engine.
# curl + ca-certificates for the sops + age binaries.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libsqlite3-dev patch curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# sops + age (for the encrypted secrets vault).
ARG SOPS_VERSION=3.9.4
ARG AGE_VERSION=1.2.1
RUN curl -fsSL "https://github.com/getsops/sops/releases/download/v${SOPS_VERSION}/sops-v${SOPS_VERSION}.linux.amd64" \
        -o /usr/local/bin/sops && \
    chmod +x /usr/local/bin/sops && \
    curl -fsSL "https://github.com/FiloSottile/age/releases/download/v${AGE_VERSION}/age-v${AGE_VERSION}-linux-amd64.tar.gz" \
        | tar -xzC /tmp && \
    mv /tmp/age/age /tmp/age/age-keygen /usr/local/bin/ && \
    rm -rf /tmp/age && \
    chmod +x /usr/local/bin/age /usr/local/bin/age-keygen

COPY pyproject.toml ./
COPY app/ ./app/
COPY setup.py ./
RUN pip install --prefix=/install .

# IP hardening — compile license-critical modules to .so.
# R3 — when compile is on, delete the matching .py files so only the
# binary `.so` survives in the builder's app/ tree. The runtime stage
# copies that tree, so the production image cannot leak source for
# verifier / fingerprint / quota_monitor.
ARG ABS_COMPILE_CYTHON=0
RUN if [ "${ABS_COMPILE_CYTHON}" = "1" ]; then \
        pip install cython>=3.0 && \
        ABS_COMPILE_CYTHON=1 python setup.py build_ext --inplace && \
        echo "[build] cython compiled" && \
        find app -name "*.c" -delete && \
        rm -f app/licensing/verifier.py \
              app/licensing/fingerprint.py \
              app/observability/quota_monitor.py && \
        echo "[build] license-critical .py source removed" && \
        sha256sum app/licensing/verifier.cpython-*.so | cut -c1-64 > /tmp/verifier.hash && \
        echo "[build] verifier.so hash: $(cat /tmp/verifier.hash)"; \
    else \
        echo "[build] cython skipped (ABS_COMPILE_CYTHON!=1)" && \
        : > /tmp/verifier.hash; \
    fi

FROM base AS runtime
# IP hardening — build hash embedded at image build time.
# scripts/release.sh sets BUILD_HASH=<git-short>-<source-sha256>;
# phone_home.py sends this to the activation server which can refuse
# tampered images by comparing against the known-good registry.
ARG BUILD_HASH=unknown
ENV ABS_BUILD_HASH=${BUILD_HASH}
LABEL abs.build.hash="${BUILD_HASH}" \
      org.opencontainers.image.title="abs-backend" \
      org.opencontainers.image.vendor="Automatia BCN"
# The apply_patch tool needs the `patch` binary at runtime.
# The sops/age binaries are copied from the builder — a small binary beats an apt install.
RUN apt-get update && apt-get install -y --no-install-recommends patch ca-certificates \
    && rm -rf /var/lib/apt/lists/*
# Audit R6 — upgrade pip+wheel (build tooling) past CVE-2025-8869 /
# CVE-2026-1703/3219/6357 (pip) + CVE-2026-24049 (wheel). Build-time only
# (uvicorn runs the app, pip is not used at runtime) but keeps the image
# scan clean. App runtime deps had zero advisories.
RUN pip install --no-cache-dir --upgrade "pip>=26.1" "wheel>=0.46.2"
COPY --from=builder /usr/local/bin/sops /usr/local/bin/sops
COPY --from=builder /usr/local/bin/age /usr/local/bin/age
COPY --from=builder /usr/local/bin/age-keygen /usr/local/bin/age-keygen
COPY --from=builder /install /usr/local
# copy app from builder (post-Cython), NOT from host. This
# guarantees the production image never sees the .py source files for
# license-critical modules when ABS_COMPILE_CYTHON=1.
COPY --from=builder /app/app /app/app
# Patch A (P1, 2026-05-08) — verifier.so hash, written by the builder
# stage RUN block above. Empty file when ABS_COMPILE_CYTHON=0 (dev
# images skip the tamper gate). tamper_check.py reads this file at
# boot; an attacker who edits the .so flips its sha256 and the gate
# panics. Path is hard-coded in app/licensing/tamper_check.py.
COPY --from=builder /tmp/verifier.hash /etc/abs.verifier.hash
# Image-baked manifest public key. When this file
# is present, the entrypoint skips self-generation of /app/data/{pub,priv}.pem
# so that licenses minted by the founder (signed with the founder's private
# key, held offline) verify against this same pubkey on every customer install.
# Pre-fix every container generated its own keypair on first boot, which
# meant every customer rejected the founder's mint with "signature invalid".
# Copy from the tracked path under app/update/.
# Sibling core/backend/manifest_pubkey.pem is gitignored (`*.pem` rule),
# so it was present locally but missing on CI checkout, breaking
# release.yml publish-images.
COPY app/update/manifest_pubkey.pem /etc/abs/manifest_pubkey.pem
RUN chmod 644 /etc/abs/manifest_pubkey.pem
ENV ABS_PUBLIC_KEY_PATH=/etc/abs/manifest_pubkey.pem

# CJ-006 — first-boot RSA keypair + demo license bootstrap
COPY scripts/entrypoint.sh /usr/local/bin/abs-entrypoint
RUN chmod +x /usr/local/bin/abs-entrypoint && \
    mkdir -p /app/data /app/vault-key && \
    useradd --create-home --uid 1000 abs && \
    chown -R abs:abs /app
USER abs

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)" || exit 1

ENTRYPOINT ["/usr/local/bin/abs-entrypoint"]
# Honour X-Forwarded-Proto so trailing-slash
# 307 redirects from Caddy preserve HTTPS instead of falling back to http://.
# --proxy-headers tells Uvicorn to read Forwarded / X-Forwarded-* from the
# upstream reverse proxy; --forwarded-allow-ips="*" trusts every hop in the
# docker network (Caddy is the only thing in front of us inside the stack).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
