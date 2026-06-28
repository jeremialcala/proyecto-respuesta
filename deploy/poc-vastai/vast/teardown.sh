#!/usr/bin/env bash
# Destruye la instancia de inferencia en vast.ai (ADR-0019 §B.4: minimización — al destruir, vast.ai
# elimina los datos del nodo). Revoca también las credenciales STS/usuario IAM si las creaste para el PoC.
set -euo pipefail
INSTANCE_ID="${1:?uso: bash teardown.sh <instance_id>}"
echo "[vast] destruyendo instancia ${INSTANCE_ID}…"
vastai destroy instance "${INSTANCE_ID}" -y    # -y: sin -y la CLI cuelga en el prompt [y/N]
echo "[vast] hecho. Recuerda: revocar las credenciales del nodo y archivar results-*.json en la plantilla."
echo "[vast] cierra también el túnel (Ctrl-C en vast/tunnel.sh) si usaste el bus por túnel."
