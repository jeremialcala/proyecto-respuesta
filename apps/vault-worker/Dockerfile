# syntax=docker/dockerfile:1.7
# Worker de Bóveda — worker sin estado, imagen OCI no-root (ADR-0005/0008/0012/0014).
FROM python:3.11-slim AS build
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout=120 --retries=10 .

FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
# clamav opcional para escaneo AV real (fase 03); en MVP el scanner es un port inyectable.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser
WORKDIR /app
COPY --from=build /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=build /usr/local/bin /usr/local/bin
COPY --from=build /app/src /app/src
USER 10001
CMD ["python","-m","vault_worker"]
