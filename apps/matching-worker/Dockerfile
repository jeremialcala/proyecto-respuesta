# syntax=docker/dockerfile:1.7
# Motor de matching — base CUDA para ArcFace/IResNet100 en GPU (ADR-0013/0001/0006/0014).
# Para CPU-fallback (SFace) usar una base python:3.11-slim y faiss-cpu (ver ADR-0013).
FROM nvidia/cuda:12.2.2-cudnn8-runtime-ubuntu22.04 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3.10 python3-pip python3-dev build-essential libgl1 libglib2.0-0 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
# La base CUDA trae setuptools 59 (no lee el [project] de PEP 621 → wheel vacío sin deps). Forzamos
# pip/setuptools/wheel modernos para que `pip install .` resuelva las dependencias del pyproject.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install --upgrade pip "setuptools>=68" wheel \
    && pip3 install --timeout=120 --retries=10 .
ENV PYTHONPATH=/app/src
# Directorio de modelos escribible por el usuario no-root: InsightFace descarga aquí buffalo_l
# (ArcFace+SCRFD) en el primer map_image. Montar un volumen en /models evita re-descargar (~300 MB).
RUN mkdir -p /models && chown -R 10001:10001 /models
ENV ARCFACE_MODEL_ROOT=/models/insightface
# Worker sin puerto: consume SQS. Liveness por proceso (sin HTTP).
USER 10001
CMD ["python3","-m","matching_worker"]
