# syntax=docker/dockerfile:1.7
# Media Delivery Gateway — imagen OCI no-root (ADR-0008/0014/0017).
# Misma imagen para ambos planos; el CMD por defecto sirve el PÚBLICO. El Deployment del plano
# interno override-a el CMD a `media_gateway.internal_main:app` (Service sin Ingress).
FROM python:3.11-slim AS build
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout=120 --retries=10 .

FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# Usuario no-root
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser
WORKDIR /app
COPY --from=build /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=build /usr/local/bin /usr/local/bin
COPY --from=build /app/src /app/src
ENV PYTHONPATH=/app/src
EXPOSE 8080
USER 10001
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=2).status==200 else 1)"
# Plano público por defecto; el escalado horizontal real lo da K8s (HPA).
CMD ["uvicorn","media_gateway.public_main:app","--host","0.0.0.0","--port","8080","--workers","2"]
