#!/usr/bin/env bash
# Lanza el nodo de inferencia (ADR-0019) en vast.ai — variante "config local + GPU ON-DEMAND + bus por
# túnel". Diferencias vs launch.sh:
#   - ON-DEMAND (sin --bid): no lo reclaman; mide cold-start/throughput base limpios.
#   - BUS = tu LocalStack expuesto por túnel (vast/tunnel.sh): inyecta AWS_ENDPOINT_URL y la queue URL
#     derivadas de TUNNEL_URL, con credenciales DUMMY (env.vast.local). El nodo NO toca AWS real salvo
#     el pull de la imagen desde ECR (token de corta vida, solo en la creación; runtime sin creds ECR).
#
# Requisitos: `vastai` CLI autenticada; `aws` CLI con permiso ecr:GetAuthorizationToken; `env.vast.local`
# rellenado (copia de env.vast.local.example); túnel arriba (vast/tunnel.sh) → su URL en TUNNEL_URL.
#
# Uso:
#   ECR_ACCOUNT=123456789012 TAG=0.1.0 TUNNEL_URL=https://xxxx.trycloudflare.com bash launch-ondemand.sh
#       → lista ofertas verificadas/Brasil/ON-DEMAND; elige un ID
#   ECR_ACCOUNT=123456789012 TAG=0.1.0 TUNNEL_URL=https://xxxx.trycloudflare.com ASK_ID=987654 \
#       bash launch-ondemand.sh   → crea la instancia
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REGION="${AWS_REGION:-sa-east-1}"
ECR_ACCOUNT="${ECR_ACCOUNT:?exporta ECR_ACCOUNT (id de cuenta AWS para el pull de la imagen)}"
REPO="${REPO:-respuesta/matching-worker-inference}"
TAG="${TAG:-0.1.0}"
REGISTRY="${ECR_ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"
IMAGE="${REGISTRY}/${REPO}:${TAG}"

# Filtros: SECURE CLOUD (verified), Brasil, reliability>0.95 (on-demand exige más que interruptible),
# 1 GPU con >=12 GB. rentable=true para que aparezcan ofertas alquilables.
QUERY="${QUERY:-verified=true rentable=true reliability>0.95 num_gpus=1 gpu_ram>=12 geolocation=BR}"

if [[ -z "${ASK_ID:-}" ]]; then
  echo "[vast] ofertas ON-DEMAND (Secure Cloud / verificadas / Brasil) — elige un ID y reejecuta con ASK_ID=…"
  echo "       query: ${QUERY}"
  vastai search offers "${QUERY}" -o 'dph+' | head -20
  echo
  echo "Luego: ASK_ID=<id> ECR_ACCOUNT=${ECR_ACCOUNT} TAG=${TAG} TUNNEL_URL=<url> bash launch-ondemand.sh"
  exit 0
fi

TUNNEL_URL="${TUNNEL_URL:?exporta TUNNEL_URL (la URL https del túnel de vast/tunnel.sh)}"
TUNNEL_URL="${TUNNEL_URL%/}"   # sin barra final
[[ -f "${HERE}/env.vast.local" ]] || { echo "falta ${HERE}/env.vast.local (copia de env.vast.local.example)"; exit 1; }

# Construye flags '-e VAR=val' desde env.vast.local, EXCLUYENDO AWS_ENDPOINT_URL y SQS_EXTRACT_QUEUE_URL
# (se derivan de TUNNEL_URL para no depender del placeholder del archivo). Descarta comentarios/vacías y
# recorta comentarios en línea.
ENV_FLAGS="$(grep -vE '^\s*#|^\s*$' "${HERE}/env.vast.local" \
  | grep -vE '^\s*(AWS_ENDPOINT_URL|SQS_EXTRACT_QUEUE_URL)=' \
  | sed -e 's/[[:space:]]#.*$//' -e 's/[[:space:]]*$//' \
  | grep -vE '^\s*$' | sed 's/^/-e /' | tr '\n' ' ')"
# Inyecta el bus tuneleado (AWS_ENDPOINT_URL gana sobre el host de la queue URL en boto3):
ENV_FLAGS="${ENV_FLAGS} -e AWS_ENDPOINT_URL=${TUNNEL_URL} -e SQS_EXTRACT_QUEUE_URL=${TUNNEL_URL}/000000000000/face-extract-requested"

echo "[vast] token ECR de corta vida (solo para el pull de la imagen)…"
ECR_TOKEN="$(aws ecr get-login-password --region "${REGION}")"

echo "[vast] creando instancia ON-DEMAND ask=${ASK_ID} imagen=${IMAGE}"
echo "[vast] bus = ${TUNNEL_URL} (LocalStack por túnel, creds dummy)"
vastai create instance "${ASK_ID}" \
  --image "${IMAGE}" \
  --login "-u AWS -p ${ECR_TOKEN} https://${REGISTRY}" \
  --env "${ENV_FLAGS}" \
  --onstart-cmd "python3 -m matching_worker.inference_main" \
  --disk 20

echo "[vast] listo (on-demand). Monitorea: vastai show instances   ·   logs: vastai logs <instance_id>"
echo "      Mantén el túnel (vast/tunnel.sh) ARRIBA mientras corre. Lanza el harness desde tu PC"
echo "      apuntando a http://localhost:4566 (ver README-local-tunnel.md)."
echo "      Al terminar: bash teardown.sh <instance_id>  y  cierra el túnel (Ctrl-C)."
