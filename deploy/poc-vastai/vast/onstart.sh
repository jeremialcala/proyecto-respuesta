#!/usr/bin/env bash
# On-start del nodo de inferencia en vast.ai (ADR-0019). Lo ejecuta vast al arrancar el contenedor;
# el env (AWS_*, SQS_*, SNS_*) lo inyecta `vastai create --env`. Stateless: procesa y publica vectores.
set -euo pipefail
echo "[vast] arrancando inference-worker (ADR-0019) — solo-vector, sin secretos a Vault"
exec python3 -m matching_worker.inference_main
