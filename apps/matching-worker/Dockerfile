# syntax=docker/dockerfile:1.7
# Motor de matching — base CUDA para ArcFace/IResNet100 en GPU (ADR-0013/0001/0006/0014).
# Para CPU-fallback (SFace) usar una base python:3.11-slim y faiss-cpu (ver ADR-0013).
FROM nvidia/cuda:12.2.2-cudnn8-runtime-ubuntu22.04 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3.10 python3-pip libgl1 libglib2.0-0 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install --timeout=120 --retries=10 .
ENV PYTHONPATH=/app/src
# Worker sin puerto: consume SQS. Liveness por proceso (sin HTTP).
USER 10001
CMD ["python3","-m","matching_worker"]
