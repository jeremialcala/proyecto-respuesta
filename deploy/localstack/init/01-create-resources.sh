#!/usr/bin/env bash
# Crea las colas SQS (con DLQ por redrive) y topics SNS del flujo central (ADR-0012).
set -euo pipefail
REGION=sa-east-1

create_queue_with_dlq() {
  local name="$1"
  awslocal sqs create-queue --queue-name "${name}-dlq" >/dev/null
  local dlq_arn
  dlq_arn=$(awslocal sqs get-queue-attributes \
    --queue-url "http://localhost:4566/000000000000/${name}-dlq" \
    --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)
  awslocal sqs create-queue --queue-name "${name}" \
    --attributes "{\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"${dlq_arn}\\\",\\\"maxReceiveCount\\\":\\\"5\\\"}\"}" >/dev/null
  echo "  cola ${name} (+ ${name}-dlq)"
}

echo "[init] creando recursos SQS/SNS en LocalStack..."
for q in meta-received inbound-text inbound-media media-stored outbound-reply report-received report-ingested; do
  create_queue_with_dlq "$q"
done

for t in report-ingested candidate-generated match-confirmed match-resolved state-changed notification-sent; do
  awslocal sns create-topic --name "$t" >/dev/null && echo "  topic ${t}"
done
for b in respuesta-media respuesta-quarantine; do
  awslocal s3 mb "s3://${b}" >/dev/null && echo "  bucket ${b}"
done
echo "[init] listo."
