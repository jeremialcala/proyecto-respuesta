#!/usr/bin/env bash
# Expone el bus LocalStack local (puerto 4566) a internet para que el nodo de inferencia REMOTO en
# vast.ai pueda alcanzarlo (PoC ADR-0019, variante "config local + GPU on-demand").
#
# Topología:
#   [tu PC] LocalStack:4566  ──(este túnel, https público)──▶  [vast.ai] inference-worker (CUDA)
# El nodo remoto pone AWS_ENDPOINT_URL=<URL del túnel> y habla SQS/SNS contra tu LocalStack.
#
# Usa cloudflared (quick tunnel, sin cuenta) si está disponible; si no, ngrok. Imprime la URL pública;
# pásala a launch-ondemand.sh como TUNNEL_URL.
#
# REQUISITO PREVIO: `docker compose up -d localstack` corriendo (init crea face-extract-requested /
# face-embedded / face-embedded-reply). Verifícalo con: curl -s http://localhost:4566/_localstack/health
#
# Uso:
#   bash tunnel.sh                 # túnel a localhost:4566
#   PORT=4566 bash tunnel.sh
#
# GOBERNANZA (ADR-0019 §5/§6): esto abre tu bus al exterior mientras dure el túnel. Mantenlo arriba SOLO
# durante la corrida y ciérralo (Ctrl-C) al terminar. Con dataset real (FairFace/FFHQ) hay egress de
# biometría a un tercero → requiere tu validación legal previa.
set -euo pipefail
PORT="${PORT:-4566}"
TARGET="http://localhost:${PORT}"

echo "[tunnel] verificando LocalStack en ${TARGET} ..."
if ! curl -fsS "${TARGET}/_localstack/health" >/dev/null 2>&1; then
  echo "[tunnel] AVISO: LocalStack no responde en ${TARGET}. Levántalo: docker compose up -d localstack"
fi

if command -v cloudflared >/dev/null 2>&1; then
  echo "[tunnel] cloudflared quick tunnel → ${TARGET}"
  echo "[tunnel] copia la URL https://<...>.trycloudflare.com y úsala como TUNNEL_URL en launch-ondemand.sh"
  echo "[tunnel] (Ctrl-C para cerrar el túnel al terminar la corrida)"
  exec cloudflared tunnel --url "${TARGET}"
elif command -v ngrok >/dev/null 2>&1; then
  echo "[tunnel] ngrok http ${PORT} (requiere authtoken configurado: ngrok config add-authtoken <token>)"
  echo "[tunnel] toma la 'Forwarding' URL https://<...>.ngrok-free.app y úsala como TUNNEL_URL"
  exec ngrok http "${PORT}"
else
  echo "[tunnel] ERROR: no encuentro cloudflared ni ngrok."
  echo "  cloudflared (recomendado, sin cuenta):"
  echo "    winget install --id Cloudflare.cloudflared      # Windows"
  echo "    brew install cloudflared                        # macOS"
  echo "  ngrok: https://ngrok.com/download (requiere authtoken gratuito)"
  exit 1
fi
