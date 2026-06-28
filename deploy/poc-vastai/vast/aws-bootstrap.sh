#!/usr/bin/env bash
# Crea los recursos del bus para el PoC en AWS REAL sa-east-1 (espejo del init local de LocalStack).
# Idempotente. Requiere awscli con credenciales de administrador (solo para esta preparación; el nodo
# de inferencia NO usa estas credenciales — ver iam-inference-policy.json). Imprime URLs/ARNs para el env.
#
# Uso:  AWS_REGION=sa-east-1 bash aws-bootstrap.sh
set -euo pipefail
REGION="${AWS_REGION:-sa-east-1}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
echo "[bootstrap] cuenta=${ACCOUNT} región=${REGION}"

create_queue_with_dlq() {
  local name="$1"
  aws sqs create-queue --region "$REGION" --queue-name "${name}-dlq" >/dev/null 2>&1 || true
  local dlq_url dlq_arn
  dlq_url="$(aws sqs get-queue-url --region "$REGION" --queue-name "${name}-dlq" --query QueueUrl --output text)"
  dlq_arn="$(aws sqs get-queue-attributes --region "$REGION" --queue-url "$dlq_url" \
            --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)"
  aws sqs create-queue --region "$REGION" --queue-name "${name}" \
    --attributes "{\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"${dlq_arn}\\\",\\\"maxReceiveCount\\\":\\\"5\\\"}\"}" \
    >/dev/null 2>&1 || true
  aws sqs get-queue-url --region "$REGION" --queue-name "${name}" --query QueueUrl --output text
}

subscribe_raw() {  # topic queue
  local t_arn q_arn q_url
  t_arn="arn:aws:sns:${REGION}:${ACCOUNT}:$1"
  q_url="$(aws sqs get-queue-url --region "$REGION" --queue-name "$2" --query QueueUrl --output text)"
  q_arn="$(aws sqs get-queue-attributes --region "$REGION" --queue-url "$q_url" \
          --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)"
  # Permite que el topic publique en la cola.
  aws sqs set-queue-attributes --region "$REGION" --queue-url "$q_url" --attributes "{\"Policy\":\"{\\\"Version\\\":\\\"2012-10-17\\\",\\\"Statement\\\":[{\\\"Effect\\\":\\\"Allow\\\",\\\"Principal\\\":{\\\"Service\\\":\\\"sns.amazonaws.com\\\"},\\\"Action\\\":\\\"sqs:SendMessage\\\",\\\"Resource\\\":\\\"${q_arn}\\\",\\\"Condition\\\":{\\\"ArnEquals\\\":{\\\"aws:SourceArn\\\":\\\"${t_arn}\\\"}}}]}\"}" >/dev/null
  aws sns subscribe --region "$REGION" --topic-arn "$t_arn" --protocol sqs \
    --notification-endpoint "$q_arn" --attributes RawMessageDelivery=true --return-subscription-arn >/dev/null
}

EXTRACT_TOPIC="$(aws sns create-topic --region "$REGION" --name face-extract-requested --query TopicArn --output text)"
EMBEDDED_TOPIC="$(aws sns create-topic --region "$REGION" --name face-embedded --query TopicArn --output text)"
EXTRACT_QUEUE="$(create_queue_with_dlq face-extract-requested)"
REPLY_QUEUE="$(create_queue_with_dlq face-embedded-reply)"
subscribe_raw face-extract-requested face-extract-requested   # → inference-worker
subscribe_raw face-embedded         face-embedded-reply        # → harness/in-region

cat <<EOF

[bootstrap] listo. Exporta esto para el harness y el env del nodo:

  export SNS_FACE_EXTRACT_TOPIC_ARN="${EXTRACT_TOPIC}"
  export SNS_FACE_EMBEDDED_ARN="${EMBEDDED_TOPIC}"
  export SQS_EXTRACT_QUEUE_URL="${EXTRACT_QUEUE}"
  export SQS_FACE_EMBEDDED_REPLY_URL="${REPLY_QUEUE}"
EOF
