#!/usr/bin/env bash
# Crea los recursos de mensajería del flujo central en LocalStack (ADR-0012):
#   - Colas SQS Standard con DLQ por redrive (maxReceiveCount=5).
#   - Topics SNS para el fan-out (varios consumidores).
#   - Suscripciones SNS -> SQS con RawMessageDelivery (el worker recibe el sobre tal cual).
#   - Buckets S3 y KMS key de la bóveda.
# Las URLs/ARNs resultantes deben coincidir con las variables del docker-compose.yml.
set -euo pipefail
REGION=sa-east-1
ACCOUNT=000000000000
ENDPOINT=http://localhost:4566

# awslocal usa us-east-1 por defecto; forzamos sa-east-1 (ADR-0006) para que las colas/topics
# vivan en la MISMA región que los servicios (AWS_REGION=sa-east-1). LocalStack es region-aware:
# una cola creada en otra región da QueueDoesNotExist al consultarla desde sa-east-1.
export AWS_DEFAULT_REGION="${REGION}"
export AWS_REGION="${REGION}"

queue_url() { echo "${ENDPOINT}/${ACCOUNT}/$1"; }
queue_arn() { echo "arn:aws:sqs:${REGION}:${ACCOUNT}:$1"; }
topic_arn() { echo "arn:aws:sns:${REGION}:${ACCOUNT}:$1"; }

# Cola SQS Standard + su DLQ por redrive policy.
create_queue_with_dlq() {
  local name="$1"
  awslocal sqs create-queue --queue-name "${name}-dlq" >/dev/null
  local dlq_arn
  dlq_arn=$(awslocal sqs get-queue-attributes \
    --queue-url "$(queue_url "${name}-dlq")" \
    --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)
  awslocal sqs create-queue --queue-name "${name}" \
    --attributes "{\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"${dlq_arn}\\\",\\\"maxReceiveCount\\\":\\\"5\\\"}\"}" >/dev/null
  echo "  cola ${name} (+ ${name}-dlq)"
}

# Suscribe una cola SQS existente a un topic SNS con entrega cruda (sin sobre SNS).
# Idempotente: con persistencia el init re-corre en cada arranque; sin esta guarda se acumularían
# suscripciones duplicadas → entrega múltiple del mismo evento.
subscribe_queue_to_topic() {
  local topic="$1" queue="$2" t_arn q_arn
  t_arn="$(topic_arn "${topic}")"
  q_arn="$(queue_arn "${queue}")"
  if awslocal sns list-subscriptions-by-topic --topic-arn "${t_arn}" \
       --query "Subscriptions[?Endpoint=='${q_arn}'].SubscriptionArn" --output text 2>/dev/null | grep -q ":"; then
    echo "  sub ${topic} -> ${queue} (ya existe)"
    return
  fi
  awslocal sns subscribe \
    --topic-arn "${t_arn}" \
    --protocol sqs \
    --notification-endpoint "${q_arn}" \
    --attributes RawMessageDelivery=true \
    --return-subscription-arn >/dev/null
  echo "  sub ${topic} -> ${queue} (raw)"
}

echo "[init] creando recursos SQS/SNS en LocalStack..."

# 1) Colas alimentadas por un productor directo (patrón cola+worker, SendMessage a la cola).
DIRECT_QUEUES=(meta-received inbound-text inbound-media outbound-reply report-received)

# 2) Colas de consumidor alimentadas vía SNS (fan-out). Una por (topic, consumidor):
#    state-changed se entrega a Notificación Y Auditoría (fan-out del ADR-0012) -> 2 colas.
FANOUT_QUEUES=(
  report-ingested        # matching-worker (enrolamiento, ADR-0016)
  media-stored           # matching-worker (imagen/video, C4)
  media-stored-intake    # core-backend (correlación foto↔reporte, ADR-0016)
  candidate-generated    # back office / core-backend (enrutado por umbral)
  match-confirmed        # core-backend / notificación
  match-resolved         # core-backend / auditoría
  state-changed          # notificación
  state-changed-audit    # auditoría (segundo consumidor de state-changed)
  notification-sent      # auditoría
  # Enrolamiento biométrico y desambiguación (ADR-0016)
  face-disambiguation-requested  # chatbot-gateway (muestra miniaturas al reportante)
  face-disambiguation-resolved   # matching-worker (enrola el rostro elegido)
  enrollment-failed              # chatbot-gateway (pide otra foto)
  entity-enrolled                # re-matching / auditoría (consumidor futuro)
)

# 3) Topics SNS (catálogo canónico del ADR-0011/0016).
TOPICS=(media-stored report-ingested candidate-generated match-confirmed match-resolved
        state-changed notification-sent
        entity-enrolled enrollment-failed face-disambiguation-requested face-disambiguation-resolved)

# 4) Pares "topic queue" de suscripción SNS -> SQS.
SUBSCRIPTIONS=(
  "report-ingested report-ingested"
  "media-stored media-stored"
  "media-stored media-stored-intake"
  "candidate-generated candidate-generated"
  "match-confirmed match-confirmed"
  "match-resolved match-resolved"
  "state-changed state-changed"
  "state-changed state-changed-audit"
  "notification-sent notification-sent"
  "face-disambiguation-requested face-disambiguation-requested"
  "face-disambiguation-resolved face-disambiguation-resolved"
  "enrollment-failed enrollment-failed"
  "entity-enrolled entity-enrolled"
)

for q in "${DIRECT_QUEUES[@]}" "${FANOUT_QUEUES[@]}"; do
  create_queue_with_dlq "$q"
done

for t in "${TOPICS[@]}"; do
  awslocal sns create-topic --name "$t" >/dev/null && echo "  topic ${t}"
done

for pair in "${SUBSCRIPTIONS[@]}"; do
  # shellcheck disable=SC2086
  subscribe_queue_to_topic $pair
done

# Buckets S3 de la bóveda (vault-worker). Idempotente: con persistencia ya existen tras el restore.
for b in respuesta-media respuesta-quarantine; do
  if awslocal s3 ls "s3://${b}" >/dev/null 2>&1; then
    echo "  bucket ${b} (ya existe)"
  else
    awslocal s3 mb "s3://${b}" >/dev/null && echo "  bucket ${b}"
  fi
done

# KMS key + alias para el cifrado de la bóveda (KMS_KEY_ID=alias/respuesta-vault).
# Idempotente y CRÍTICO: re-crear la key cambiaría el key id → la DEK envuelta de las fotos ya
# guardadas no se podría desenvolver. Solo se crea si el alias aún no existe.
if awslocal kms describe-key --key-id alias/respuesta-vault >/dev/null 2>&1; then
  echo "  kms alias/respuesta-vault (ya existe)"
else
  key_id=$(awslocal kms create-key --query 'KeyMetadata.KeyId' --output text)
  awslocal kms create-alias --alias-name alias/respuesta-vault --target-key-id "${key_id}" >/dev/null
  echo "  kms alias/respuesta-vault (${key_id})"
fi

echo "[init] listo."
