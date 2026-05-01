# S20.1 — Piper TTS HTTP wrapper.
#
# Upstream Piper (https://github.com/rhasspy/piper) ships only a CLI binary,
# so we wrap it with a minimal FastAPI service. Voices are downloaded on
# first use and cached under /models (volume-mounted in compose).
#
# License: MIT (Piper) — attribution lives in docs/legal/THIRD_PARTY_LICENSES.md.

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# piper-tts pulls the onnxruntime + espeak-ng-data wheels.
RUN pip install --no-cache-dir \
        "fastapi>=0.115" \
        "uvicorn[standard]>=0.30" \
        "piper-tts==1.2.0"

COPY server.py /app/server.py

EXPOSE 5002
ENV ABS_PIPER_MODEL_DIR=/models

HEALTHCHECK --interval=20s --timeout=5s --retries=5 \
  CMD curl -fsS http://127.0.0.1:5002/health || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "5002"]
