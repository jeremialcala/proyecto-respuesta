#!/usr/bin/env bash
# Lanza el nodo de inferencia (ADR-0019) en vast.ai Secure Cloud, INTERRUPTIBLE, región Brasil, host
# verificado. Imagen privada en ECR sa-east-1: el token de login ECR (~12 h, corta vida) se usa SOLO al
# hacer pull en la creación; el contenedor en runtime no lleva credenciales de ECR (§4).
#
# Requisitos: `vastai` CLI autenticada (`vastai set api-key …`), `aws` CLI con permiso ecr:GetAuthorizationToken,
# y `env.vast` rellenado (copia de env.vast.example).
#
# Uso:
#   ECR_ACCOUNT=123456789012 TAG=0.1.0 BID=0.12 bash launch.sh            # busca ofertas
#   ECR_ACCOUNT=123456789012 TAG=0.1.0 BID=0.12 ASK_ID=987654 bash launch.sh   # crea en esa oferta
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REGION="${AWS_REGION:-sa-east-1}"
ECR_ACCOUNT="${ECR_ACCOUNT:?exporta ECR_ACCOUNT (id de cuenta AWS)}"
REPO="${REPO:-respuesta/matching-worker-inference}"
TAG="${TAG:-0.1.0}"
BID="${BID:-0.12}"            # precio de puja (interruptible). Ajusta según el mercado.
REGISTRY="${ECR_ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"
IMAGE="${REGISTRY}/${REPO}:${TAG}"

# Filtros: SECURE CLOUD (verified), región Brasil, reliability>0.90 (interruptible), 1 GPU con ≥12 GB.
QUERY="${QUERY:-verified=true rentable=true reliability>0.90 num_gpus=1 gpu_ram>=12 geolocation=BR}"

if [[ -z "${ASK_ID:-}" ]]; then
  echo "[vast] ofertas (Secure Cloud / verificadas / Brasil / interruptible) — elige un ID y reejecuta con ASK_ID=…"
  echo "       query: ${QUERY}"
  vastai search offers "${QUERY}" -o 'dph+' | head -20
  echo
  echo "Luego: ASK_ID=<id> ECR_ACCOUNT=${ECR_ACCOUNT} TAG=${TAG} BID=${BID} bash launch.sh"
  exit 0
fi

[[ -f "${HERE}/env.vast" ]] || { echo "falta ${HERE}/env.vast (copia de env.vast.example)"; exit 1; }
# Convierte env.vast en flags '-e VAR=val': descarta líneas de comentario/vacías, recorta comentarios
# en línea (' #…') y espacios sobrantes. Los comentarios deben ir en líneas propias (ver el ejemplo).
ENV_FLAGS="$(grep -vE '^\s*#|^\s*$' "${HERE}/env.vast" \
  | sed -e 's/[[:space:]]#.*$//' -e 's/[[:space:]]*$//' \
  | grep -vE '^\s*$' | sed 's/^/-e /' | tr '\n' ' ')"

echo "[vast] token ECR de corta vida (solo para el pull)…"
ECR_TOKEN="$(aws ecr get-login-password --region "${REGION}")"

echo "[vast] creando instancia interruptible ask=${ASK_ID} bid=\$${BID} imagen=${IMAGE}"
vastai create instance "${ASK_ID}" \
  --image "${IMAGE}" \
  --login "-u AWS -p ${ECR_TOKEN} https://${REGISTRY}" \
  --env "${ENV_FLAGS}" \
  --onstart-cmd "python3 -m matching_worker.inference_main" \
  --disk 20 \
  --bid "${BID}"

echo "[vast] listo. Monitorea: vastai show instances   ·   logs: vastai logs <instance_id>"
echo "      Lanza el harness desde en-región/tu equipo (ver ../README.md §B) apuntando al bus real."
echo "      Al terminar: bash teardown.sh <instance_id>   (minimización: destruye datos del nodo, §B.4)"
