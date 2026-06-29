# ADR-0016: Enrolamiento biométrico y desambiguación multi-rostro

- **Estado:** accepted — punto 3 (purga incondicional de rostros no seleccionados) **enmendado por [ADR-0021](0021-reporte-derivado-otros-rostros.md)**; notificaciones del ciclo en **[ADR-0020](0020-notificaciones-enrolamiento-reportante.md)**
- **Fecha:** 2026-06-27
- **Decisores:** Jeremi
- **Fase AI-DLC:** 02-design / 03-implementation
- **Controles OWASP afectados:** A01 (control de acceso entre entidades), A04 (datos biométricos de terceros), A08 (integridad del enrolamiento), A09 (auditoría/retención)
- **Relacionado:** RF-02 (captura de reporte con foto), RF-05 (matching), [ADR-0004](0004-motor-de-matching.md) (motor de matching), [ADR-0005](0005-webhook-manager-vault-worker.md) (bóveda de adjuntos), [ADR-0007](0007-esquema-reporte-retencion-auditoria.md) (retención/auditoría), [ADR-0008](0008-boveda-llaves-identidad.md) (identidad/cifrado), [ADR-0011](0011-contrato-eventos.md) (sobre de eventos), [ADR-0012](0012-broker-aws-sqs-sns.md) (broker SQS/SNS), [ADR-0013](0013-arcface-scoring-solo-rostro.md) (ArcFace 512-d), [ADR-0015](0015-memoria-conversacion-pgvector.md) (conversación del chatbot)

## Contexto

El reporte de una persona desaparecida llega con una **foto de referencia**: el reportante sube una
imagen del sujeto. El `IntakeService` ya persiste el reporte, crea una entidad provisional y publica
`report.ingested` con `media_ref` (el adjunto vive cifrado en la bóveda — ADR-0005/0008). Pero la
entidad provisional **todavía no tiene su huella biométrica en el índice**: el `ArcFaceMapper`
(`map_image`, 512-d, ADR-0013) y el `EmbeddingStore` (pgvector) existen, pero **falta el caso de uso
que enlaza el embedding del sujeto a su entidad**. Sin ese enlace, el motor de matching no puede
comparar reportes de "encontrado" contra ese desaparecido.

Hay dos complicaciones reales:

1. **Las fotos de referencia rara vez contienen un solo rostro.** Una foto familiar, de grupo o
   tomada en la calle puede traer varias caras. El sistema **no puede adivinar** cuál es el sujeto: si
   enrola la cara equivocada, contamina el índice y produce falsos positivos en un dominio donde el
   error tiene costo humano. La única fuente de verdad sobre "quién es el desaparecido" es **el
   reportante**.

2. **Los rostros que no son el sujeto son terceros que no han consentido** (transeúntes, familiares,
   posiblemente menores). Procesar y —peor— **retener** su biometría viola la minimización de datos
   (privacidad opt-in, principio de diseño del proyecto; A04). El enrolamiento debe tocar esos
   rostros de forma estrictamente transitoria y purgarlos.

Necesitamos un flujo que: (a) detecte y enrole automáticamente cuando hay **un** rostro claro, (b)
**pregunte al reportante** cuando hay **varios**, mostrándole los rostros para que elija, y (c)
descarte el resto sin retenerlo.

## Decisión

**1. Nuevo caso de uso `EnrollmentService` en el `matching-worker`.** Consume `report.ingested`,
resuelve `media_ref` → bytes de imagen (vía bóveda), ejecuta `FaceMapper.map_image` y ramifica por el
número de rostros que superan el umbral de calidad (`QualityThresholds`, ADR-0004):

| Rostros | Acción |
|---|---|
| **0** | Publica `enrollment.failed` (`reason=no_face`). El chatbot pide otra foto. |
| **1** | `EmbeddingStore.add_reference(entity_id, embedding)` → refresca el índice ANN → publica `entity.enrolled`. |
| **≥2** | **No enrola.** Recorta cada rostro, lo guarda efímero en la bóveda, crea un `PendingEnrollment` y publica `face.disambiguation.requested` hacia el chatbot. |

**2. La desambiguación viaja como evento al chatbot (no resolución automática, ADR-0001/0004).** El
worker publica `face.disambiguation.requested` con la lista de rostros (índice, `crop_ref`, `bbox`,
`det_score`) y un `disambiguation_id`. El `chatbot-gateway` reenvía la pregunta al reportante por su
canal (WhatsApp/Telegram) usando su `conversation_key` (ADR-0015), mostrando las **miniaturas
numeradas**. La respuesta vuelve como `face.disambiguation.resolved` (`selected_index` o
`action=none_of_these`).

**3. Al resolver, se enrola solo el rostro elegido y se purga el resto.** El `EnrollmentService`
consume `face.disambiguation.resolved`, valida el `PendingEnrollment` (existe, no expiró, índice en
rango), enrola **únicamente** el embedding seleccionado (`entity.enrolled`) y **borra
inmediatamente** los recortes y embeddings de los rostros no elegidos junto con el registro pendiente.
`none_of_these` → `enrollment.failed` (`reason=no_subject_in_photo`) y purga igual.

**4. `FaceMap` lleva geometría de detección.** Se extiende el modelo de dominio con `bbox`
(x1,y1,x2,y2) y `det_score`; hoy `_to_facemap` la descarta. Es lo mínimo para recortar y para que el
reportante ubique cada cara. El embedding sigue siendo 512-d normalizado (ADR-0013).

**5. Puertos nuevos (hexagonal).** `MediaGateway` (lee bytes por `media_ref`, guarda/borra recortes en
la bóveda) y `PendingEnrollmentStore` (persiste los `PendingEnrollment` en Postgres con TTL). El
recorte de rostros es una capacidad del adaptador de visión (`crop_faces(image_bytes, bboxes)`). Se
reutilizan `EmbeddingStore`, `AnnIndex` y `EventBus` ya existentes.

**6. Idempotencia y entrega at-least-once (ADR-0012).** `disambiguation_id` es la clave de
idempotencia: un `resolved` duplicado es no-op si el pendiente ya está resuelto. `add_reference` es
upsert por `entity_id`, así que reenrolar el mismo sujeto no duplica.

## Alternativas consideradas

| Opción | Pros | Contras | Riesgo de seguridad |
|---|---|---|---|
| A. Enrolar el rostro más grande/central automáticamente | Sin ida-y-vuelta | Adivina; enrola al sujeto equivocado en fotos de grupo → falsos positivos | Alto: contamina el índice |
| B. Enrolar **todos** los rostros bajo la misma entidad | No pierde al sujeto | Mezcla biometría de terceros en una identidad; imposible de limpiar | Alto: retención de PII sin consentimiento (A04) |
| C. Rechazar toda foto con >1 rostro | Simple | Inutiliza la mayoría de fotos reales (familiares/grupo) | Bajo pero inservible |
| **D. Desambiguación dirigida por el reportante + purga del resto (elegida)** | Precisa; respeta consentimiento; reutiliza chatbot/bóveda | Más piezas (pendiente, recortes, 4 eventos); depende de respuesta del usuario | Acotado: recortes efímeros, solo el sujeto persiste |

## Consecuencias

- **Positivas:** el índice solo contiene la biometría del sujeto correcto, validada por quien lo
  conoce; fotos de grupo dejan de ser inservibles; reutiliza la bóveda (ADR-0005/0008), el chatbot con
  estado (ADR-0015) y el sobre de eventos (ADR-0011); el LLM/visión **no** decide identidad (ADR-0001).
- **Negativas / deuda asumida:** cuatro eventos nuevos y dos tablas (`pending_enrollments`,
  recortes efímeros en bóveda); el enrolamiento queda **bloqueado** hasta que el reportante responde
  (mitigado con TTL + recordatorio); afinado pendiente del umbral de calidad para "rostro claro".
- **Impacto en threat model:** **nueva superficie de PII biométrica de terceros**. Mitigaciones:
  recortes cifrados en bóveda (ADR-0008) con **TTL corto**, purga inmediata al resolver/expirar, y
  **nunca** se persiste el embedding de un rostro no seleccionado al índice de largo plazo. Atención
  especial a menores entre los no-sujetos: no se retienen. Auditoría encadenada de cada enrolamiento
  y descarte (A08/A09). Aislamiento por `entity_id`/`disambiguation_id` (A01).

## Pendiente

- Umbral de calidad y tamaño mínimo para considerar un rostro "candidato" presentable (filtrar caras
  de fondo diminutas) — recalibrar en fase 04 junto a ADR-0013.
- TTL exacto del `PendingEnrollment` y política de recordatorio/expiración (alinear con la ventana de
  conversación de ADR-0015 y la retención de ADR-0007).
- Re-enganche del matching: al emitir `entity.enrolled`, reevaluar reportes de "encontrado" que
  llegaron antes de que el desaparecido tuviera huella.
- Detección/etiquetado de menores entre rostros no-sujeto para reforzar la no-retención.
- Soporte de **video** de referencia (map_video, ADR-0004) reusa el mismo flujo con probes agregados.
