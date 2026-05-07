FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

FROM base AS builder
# 010 — chromadb rust binding + patch_engine için build deps
# 013 — sops + age binary'leri için curl + ca-certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libsqlite3-dev patch curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 013 — sops + age (encrypted secrets vault için)
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

# Q12 IP-Hardening R5 — compile license-critical modules to .so.
# Gated behind ABS_COMPILE_CYTHON=1; default builds keep .py for fast
# rebuilds + readable tracebacks during dev.
ARG ABS_COMPILE_CYTHON=0
RUN if [ "${ABS_COMPILE_CYTHON}" = "1" ]; then \
        pip install cython>=3.0 && \
        ABS_COMPILE_CYTHON=1 python setup.py build_ext --inplace && \
        echo "[build] cython compiled" && \
        find app -name "*.c" -delete; \
    else \
        echo "[build] cython skipped (ABS_COMPILE_CYTHON!=1)"; \
    fi

FROM base AS runtime
# Q12 IP-Hardening R3 — build hash embedded at image build time.
# scripts/build_with_hash.sh sets BUILD_HASH=<git-short>-<source-sha256>;
# phone_home.py sends this to the activation server which can refuse
# tampered images by comparing against the known-good registry.
ARG BUILD_HASH=unknown
ENV ABS_BUILD_HASH=${BUILD_HASH}
# 010 — apply_patch tool runtime'da `patch` binary'sine ihtiyaç duyar
# 013 — sops/age binary'leri builder'dan kopyalanır (apt-install yerine küçük binary)
RUN apt-get update && apt-get install -y --no-install-recommends patch ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /usr/local/bin/sops /usr/local/bin/sops
COPY --from=builder /usr/local/bin/age /usr/local/bin/age
COPY --from=builder /usr/local/bin/age-keygen /usr/local/bin/age-keygen
COPY --from=builder /install /usr/local
COPY app/ ./app/
# Q7 — Neo4j integration (explicit pin alongside the broad COPY)
COPY app/api/graph.py /app/app/api/graph.py
COPY app/integrations/neo4j_client.py /app/app/integrations/neo4j_client.py
# Q7 — Marketplace hardening
COPY app/marketplace/sandbox.py /app/app/marketplace/sandbox.py
COPY app/marketplace/cosign_verify.py /app/app/marketplace/cosign_verify.py
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
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
