# ADR-0020: Notificaciones del ciclo de enrolamiento al reportante (acuse + cierre con imagen)

- **Estado:** accepted
- **Fecha:** 2026-06-29
- **Decisores:** Jeremi
- **Fase AI-DLC:** 02-design → 03-implementation
- **Controles OWASP afectados:** A01 (aislamiento por sujeto), A02 (firma del token de imagen), A04 (exposición de PII/biometría), A05 (borde público de medios), A09 (auditoría/observabilidad)
- **Relacionado:** RF-16…RF-23 ([notificaciones-matching.md](../../01-requirements/notificaciones-matching.md)), [ADR-0011](0011-contrato-eventos.md) (sobre de eventos), [ADR-0012](0012-broker-aws-sqs-sns.md) (broker SQS/SNS), [ADR-0015](0015-memoria-conversacion-pgvector.md) (sesión del chatbot), [ADR-0016](0016-enrolamiento-biometrico-desambiguacion.md) (enrolamiento/desambiguación), [ADR-0017](0017-media-delivery-gateway.md) (entrega de medios por URL firmada). **Complementado por** [ADR-0021](0021-reporte-derivado-otros-rostros.md).

## Contexto

El `matching-worker` ya emite los eventos del ciclo de enrolamiento (`entity.enrolled`,
`enrollment.failed`, `face.disambiguation.requested` — ADR-0016) y el `media-gateway` ya sabe servir
un binario cifrado de la bóveda por **URL firmada** que Meta descarga y renderiza (ADR-0017). Lo que
**falta** es cerrar el lazo con el reportante: hoy sube su foto y el procesamiento es **silencioso**.
El requerimiento (RF-16…RF-19, RF-22, RF-23) pide tres comunicaciones de vuelta:

1. **Acuse de recepción y análisis** — apenas la foto entra al pipeline.
2. **Cierre con resumen + foto** — al enrolar al sujeto, un mensaje de **tipo imagen** con la foto
   entregada y el resumen del reporte (nombre, documento, última ubicación, info adicional).
3. **Solicitud de mejor foto** — cuando no hay rostro o la calidad es baja.

Hay tres fuerzas que condicionan el diseño:

- **El `OutboundReply` actual solo modela texto** (`jwe_body`): no existe forma de pedirle al servicio
  de salida que envíe un **mensaje de tipo imagen** con `link` + caption. Hay que extender el contrato.
- **La foto vive cifrada en la bóveda** (ADR-0008) y solo es renderizable vía token firmado del
  `media-gateway` (ADR-0017). La URL debe emitirse **en el momento del envío** (TTL mínimo), no al
  generar el evento.
- **El resumen requiere datos del reporte** (núcleo dinámico, ADR-0007) que el `matching-worker` no
  posee: el worker conoce `entity_id`/`report_id`, no el nombre ni el documento. Hay que decidir **quién
  arma el resumen**.

**Alcance temporal (decisión de producto).** El cierre se dispara al **enrolar** (`entity.enrolled`),
**no** al resolver un match contra la base. "Reporte completo" significa *"tu reporte quedó registrado
y tu persona entró al índice de búsqueda"*, no *"encontramos a tu persona"*. Las notificaciones de
resultado de matching quedan fuera de este ADR.

## Decisión

**1. El cierre se dispara con `entity.enrolled`, enriquecido con datos del reporte.** El
`matching-worker` ya publica `entity.enrolled` al enrolar al sujeto. Se **extiende su payload** con lo
mínimo para enrutar la notificación (`report_id`, `media_ref`, `contact_ref`, `bot_id`, `channel`) —
el worker ya recibe esos campos en `report.ingested` (ADR-0016) y solo los propaga. El **resumen no lo
arma el worker**: lo arma quien tiene el reporte en claro.

**2. Un nuevo paso de notificación traduce eventos de enrolamiento → mensajes al reportante.** La
lógica de "convertir un evento del ciclo en una conversación de vuelta" vive en el **plano de salida
del chatbot** (`chatbot-gateway`, que ya posee la sesión del reportante — ADR-0015 — y ya publica
`outbound.reply`). Suscribe `entity.enrolled`, `enrollment.failed` y `face.disambiguation.requested`
y, según el evento, compone el mensaje y publica `outbound.reply`:

| Evento de entrada | Notificación al reportante | RF |
|---|---|---|
| `report.ingested` (o ack temprano del intake) | **Acuse**: "Recibimos la foto y la estamos analizando." | RF-16 |
| `entity.enrolled` | **Cierre**: mensaje de **tipo imagen** (foto + resumen). | RF-17/RF-18 |
| `enrollment.failed` (`no_face`/`low_quality`) | **Mejor foto** con guía + motivo. | RF-19 |
| `face.disambiguation.requested` | Miniaturas numeradas para elegir (ADR-0016). | RF-20 |

El **resumen** (nombre, documento, última ubicación, info adicional) se obtiene del reporte: el
`chatbot-gateway` tiene el borrador acumulado de la sesión (ADR-0015) o lo consulta al core-backend por
`report_id`. Campos ausentes → "no especificado".

**3. Se extiende `OutboundReply` para mensajes de tipo imagen.** El contrato gana un modo imagen,
manteniendo retrocompatibilidad con el texto actual:

```yaml
OutboundReply:
  required: [bot_id, channel, contact_ref]
  properties:
    bot_id:      { type: string, format: uuid }
    channel:     { $ref: '#/components/schemas/MetaChannel' }
    contact_ref: { type: string }
    kind:        { type: string, enum: [text, image], default: text }   # NUEVO
    jwe_body:    { type: string, description: 'Texto/caption cifrado en JWE.' }
    media:                                                              # NUEVO (solo kind=image)
      type: object
      properties:
        media_ref: { type: string, description: 'Puntero en bóveda; el servicio de salida pide la URL firmada al media-gateway al enviar (ADR-0017).' }
```

El **servicio de salida** (no el productor del evento) pide la **concesión** al `media-gateway` en el
**instante del envío** (`POST /grants` sobre `media_ref`), obtiene `https://media…/m/{token}` y la
manda a Meta como *image message* con `link` + `caption` (el resumen). Así el TTL del token es mínimo
(RS-N2, A02/A04). El binario **no** se sube a la Graph API (ADR-0017).

**4. Idempotencia del cierre (RF-23).** Una notificación de cierre por reporte: clave de idempotencia
`entity_id` (o `report_id`) en el plano de notificación; un `entity.enrolled` reentregado
(*at-least-once*, ADR-0012) es no-op si ya se notificó. El acuse y la mejor-foto usan `event_id`.

**5. Auditoría (RF-22).** Cada notificación emitida publica `notification.sent` con `entity_id`,
`channel`, `purpose ∈ {ack, closing, better_photo, disambiguation}` y `sent_at`, y queda en la
auditoría encadenada (ADR-0007/ADR-0011). Se **extiende** `NotificationSent` con `purpose` y
`contact_ref` opcionales (el esquema actual apunta al clúster opt-in; aquí el destino es el reportante).

## Alternativas consideradas

| Opción | Pros | Contras | Riesgo de seguridad |
|---|---|---|---|
| A. El `matching-worker` arma y envía la notificación directo | Un solo servicio | El worker no tiene el reporte en claro ni la sesión del reportante; acoplaría matching con PII y canal | Alto: PII de reporte cruza al plano de matching |
| B. Subir la foto a la Graph API para el mensaje imagen | Sencillo de enviar | Replica PII de imagen a Meta; perdemos control/auditoría del render; contradice ADR-0017 | Alto: exfiltración de biometría |
| C. Cierre al **resolver match** (no al enrolar) | "Verificado contra BD" literal | El reportante espera sin señal hasta que haya candidatos; muchos reportes nunca matchean → nunca cierran | Medio: silencio prolongado, duplicados |
| **D. Notificación en el plano de salida del chatbot, cierre en `entity.enrolled`, imagen por URL firmada al enviar (elegida)** | Reusa sesión (ADR-0015), salida y media-gateway (ADR-0017); TTL mínimo; sin PII en el worker | Extiende `OutboundReply` y `entity.enrolled`/`NotificationSent`; un salto más | Acotado: token efímero, destino único |

## Consecuencias

- **Positivas:** se cierra el lazo con el reportante reutilizando lo ya construido (ADR-0015/0016/0017);
  la foto se entrega controladamente como mensaje imagen sin replicar PII a Meta; el `matching-worker`
  **no** toca datos de reporte en claro ni el canal (separación de responsabilidades); todo queda
  auditado (A09). El acuse temprano (RF-16) reduce reenvíos y duplicados.
- **Negativas / deuda asumida:** se modifican tres esquemas (`OutboundReply`, `entity.enrolled`,
  `NotificationSent`) y el `output-service` gana un modo imagen; el plano de salida del chatbot debe
  resolver el resumen (borrador de sesión o consulta al core). Falta definir el **texto exacto** de
  cada plantilla y el **límite de reintentos** de mejor-foto (RF-19, AB-N1).
- **Impacto en threat model:** nueva salida de PII (foto + resumen) hacia el canal. Mitigaciones:
  destino único = `contact_ref` del reportante originador (A01); imagen solo por token firmado opaco de
  TTL corto/uso limitado emitido al enviar (A02/A04, ADR-0017); resumen nunca difundido; idempotencia
  evita tormenta de notificaciones (AB-N5); auditoría encadenada de cada `notification.sent` (A09).
  Los rostros de terceros en fotos de grupo **no** entran en este cierre (se gobiernan en ADR-0021).

## Estado de implementación (2026-06-29)

Implementado (fase 03) y validado con tests por servicio:
- **Acuse (RF-16):** lo emite el **core-backend intake** al recibir la foto — `report.ingested` con
  `media_ref`, **o `media.stored` antes de completar el reporte** (`IntakeService._ack_photo`,
  idempotente **por `media_ref`**) — así el reportante siempre ve el resultado de la carga aunque el
  reporte aún no cierre; publica `outbound.reply` (acuse) + `notification.sent`.
- **Anti-alucinación (grounding):** el system prompt del LLM le prohíbe inventar un "registro" de
  reportes o mostrar reportes guardados; ante "muéstrame el reporte"/"a quién reporté" responde solo con
  lo capturado en **esta** conversación (perfil de sesión) o pide lo que falta.
- **Cierre imagen+resumen (RF-17/18):** el `matching-worker` propaga `media_ref` en `entity.enrolled`;
  el `chatbot-gateway` arma el **resumen desde el borrador de sesión** (ADR-0015) y publica
  `outbound.reply` **kind=image**; el `output-service` pide la concesión al media-gateway al enviar y
  manda el *image message* con caption. **Degradación:** si no hay plano de medios accesible (sin
  media-gateway o falla la concesión), el `output-service` entrega el **resumen como texto** para que el
  reportante siempre lo vea.
- **Mejor-foto (RF-19):** `chatbot-gateway` cuenta reintentos (`photo_retry_count`) y deriva a
  coordinador tras `MAX_PHOTO_RETRIES` (default 3).
- **Ubicación:** campo nuevo de punta a punta (LLM → `ReportDraft`/`SessionProfile` → resumen; también
  en `report.received`/`report.ingested`).
- **Auditoría (RF-22):** `notification.sent` con `purpose ∈ {ack, closing, better_photo, disambiguation}`.
- **Contratos:** `asyncapi.yaml` actualizado (`OutboundReply.kind/media`, `EntityEnrolled.media_ref`,
  `NotificationSent.purpose/contact_ref`, `ReportIngested.location`).

## Pendiente

- Texto/plantillas exactas (UX-copy) finas por canal; valor definitivo de `MAX_PHOTO_RETRIES`.
- **Persistencia** de `notification.sent` en la auditoría encadenada: hoy se emite el evento al bus;
  falta el consumidor que lo escriba en `audit_log` (o emitir desde el core con `ChainedAudit`).
- Plantilla HSM específica de cierre fuera de la ventana de 24h (hoy degrada a la HSM genérica).
- **Imagen real del cierre:** requiere el **plano público del media-gateway** alcanzable por Meta
  (ADR-0017). No funciona desde localhost (Meta descarga el `link`); en dev/local el cierre llega como
  **texto**. Para validar la imagen: levantar el media-gateway (interno+público) con una **clave HMAC en
  KMS** y exponer el plano público (túnel/dominio); pendiente añadirlo al `docker-compose`.
