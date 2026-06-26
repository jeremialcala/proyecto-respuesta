# ADR-0005: Ingestión de Meta asíncrona (Webhook Gateway delgado + Meta Handler + Worker de Bóveda)

- **Estado:** accepted
- **Fecha:** 2026-06-25
- **Decisores:** Jeremi
- **Fase AI-DLC:** 02-design
- **Controles OWASP afectados:** A01 (control de acceso), A02 (fallos criptográficos), A04 (insecure design / biométricos), A05 (misconfig), A08 (integridad de datos/eventos)
- **Relacionado:** RF-01, RF-02, RS-03, RS-06, RS-08, RS-13, AB-07, threat model T1/T11, [ADR-0001](0001-llm-on-premises.md), [ADR-0003](0003-hosting-modelo-a.md), [C4 de componentes del webhook](../../architecture/c4-component-webhook.md)
- **Base de implementación:** sección de webhooks del repo `wh-python-fastapi-messenger` (FastAPI: handshake `hub.challenge`, `EventTransport`/`EventAction`, publicación AMQP con cuerpo JWE)

## Contexto

La ingestión de mensajes de Meta (WhatsApp Business / Messenger / Instagram) era hasta ahora una
responsabilidad implícita dentro de la **Pasarela de Chatbot**. Tres fuerzas obligan a separarla:

1. **Superficie pública no confiable.** El webhook es el único endpoint que Meta golpea desde
   internet; mezclarlo con el LLM on-prem y el almacén de medios amplía el blast radius de un
   compromiso del borde.
2. **Naturaleza distinta del texto y los adjuntos.** El texto alimenta la conversación (LLM); los
   adjuntos (foto/audio/video) son **biométricos potenciales** que no deben reenviarse por la red
   social y exigen escaneo, cifrado y almacenamiento controlado (RS-03/RS-08).
3. **Requisitos operativos de Meta.** El webhook exige **ACK rápido** (o Meta reintenta), **firma
   HMAC** verificable y **idempotencia** frente a reintegros — propiedades de un servicio sin estado
   y escalable horizontalmente, no de un orquestador conversacional con estado.

El repo de referencia ya provee el esqueleto: handshake `hub.challenge`, creación de `Event` con
`EventAction` por paso, identificación de `object` (`page` vs. `whatsapp_business_account`) y
publicación a una cola AMQP con el cuerpo cifrado en **JWE**. Le falta validación de firma e
idempotencia, que esta decisión incorpora.

## Decisión

**Convención de la arquitectura: el webhook nunca toca los workers ni el almacén directamente; toda
la cadena de ingestión se mueve por eventos asíncronos vía AMQP.** El borde solo recibe y publica el
**mensaje crudo**; un **Meta Handler** lo procesa y reparte. La ingestión queda en **tres servicios**
detrás de un **edge/reverse proxy**:

**1. Webhook Gateway** (servicio FastAPI, sin estado, único expuesto a Meta):

- **Verificación** del handshake `GET` (`hub.mode`/`hub.verify_token`/`hub.challenge`) por bot.
- **Recepción** `POST` con **ACK 200 inmediato**, para respetar el timeout de Meta.
- **Validación de firma** `X-Hub-Signature-256` (HMAC del app secret) — **endurecimiento** sobre el
  repo de referencia.
- **Guarda de idempotencia** (Redis) por `message_id` con TTL, para descartar reintentos de Meta.
- **Publica el payload crudo** a `meta.received` y **nada más**: no resuelve contactos, no identifica
  tipos, no crea el evento de negocio, no toca el almacén. Superficie pública mínima.

**2. Meta Handler** (worker, sin exposición pública) — *procesa el mensaje crudo*:

- Consume `meta.received`; **crea el `Event`** y emite `EventAction` por paso (`ctr_create_event` +
  `ctr_notify_action`), con **JWK por evento** para cifrar los cuerpos.
- **Normaliza** el payload: identifica `object` (`page` = Messenger, `whatsapp_business_account` =
  WhatsApp) y resuelve el contacto (`fbId`/`waId`).
- **Dispatcher de tipo** → publica a la cola correspondiente: texto → `inbound.text` (JWE); adjunto →
  `inbound.media` con `media_id`+`mime` (el binario **no** viaja; solo su id).

**3. Worker de Control de Bóveda** (worker, dentro de la zona de datos restringidos):

- Consume `inbound.media`, **descarga** el binario de la Graph API por `media_id`.
- **Escanea** AV + hashing **CSAM** antes de tocar el almacén (child-safety).
- **Cifra con sobre** (DEK por objeto envuelta por **KMS**) y **persiste** en el almacén de medios.
- Emite **`media.stored`** con el `media_ref`; el motor de matching consume imagen/video.

Cada salto entre servicios es una **cola AMQP** (`meta.received` → `inbound.text`/`inbound.media` →
`media.stored`), de modo que ningún componente público invoca a un worker de forma síncrona.

**4. DLQ universal + Gestor de DLQ.** **Toda cola se declara con un dead-letter exchange (DLX)** que
enruta a su cola muerta `*.dlq`. Un mensaje cae a la DLQ cuando el consumidor lo nack-ea sin requeue
tras **N reintentos** (backoff), excede su **TTL**, o falla la validación/normalización (`object`
desconocido, contacto irresoluble, adjunto que no descarga, escaneo que lo rechaza). Un **Gestor de
DLQ** consume todas las `*.dlq` y **gestiona el estado del evento**: localiza el `Event` por
`event_id` y registra un `EventAction` en estado **ERR** con el motivo, la cola de origen y el conteo
de reintentos; desde ahí dispara **alerta** y habilita **reproceso** selectivo (re-publicar a la cola
original corregida la causa). Ningún mensaje inprocesable se descarta en silencio.

**Infraestructura de soporte** (para completar el diseño distribuido): edge/reverse proxy (TLS/WAF),
broker AMQP con **DLQ + reintentos**, store de idempotencia (Redis), store de eventos, **secrets
manager** (tokens de Meta + claves JWE/KMS) y **servicio de salida** que consume `outbound.reply` y
responde por la Graph API (equivale a `ctr_send_wa_message`).

## Alternativas consideradas

| Opción | Pros | Contras | Riesgo de seguridad |
| :---- | :---- | :---- | :---- |
| **A. Gateway delgado + Meta Handler + Vault Worker (todo por AMQP)** ✅ | El borde solo publica crudo; el procesamiento vive en workers sin exposición pública; cada salto es una cola (desacople total, reintentos, escala por etapa) | Más servicios y colas que operar; consistencia eventual; un hop extra de latencia (crudo→handler) | Mínimo blast radius (A01/A04); firma+idempotencia cierran T1/T11 antes de encolar |
| **B. Webhook "gordo" que procesa y enruta él mismo a los workers** | Una pieza y un hop menos | El endpoint público resuelve PII, lee tokens de medios y publica a varias colas: más lógica en la superficie expuesta | Mayor superficie en el borde (A01/A04); viola la convención de no procesar en el webhook |
| **C. Todo dentro de la Pasarela de Chatbot** | Menos piezas; un solo despliegue | El endpoint público comparte proceso con el LLM y el acceso a medios; difícil de escalar y endurecer | Compromiso del borde alcanza LLM y binarios (A04) — inaceptable |
| **D. iPaaS / webhook gestionado (Zapier, etc.)** | Cero ops de ingestión | Los mensajes (PII) pasan por un tercero; contradice on-prem/Modelo A | Exposición de PII a procesador externo (A01/A04) |
| **E. Gateway separado pero la bóveda baja el binario en el propio webhook** | Una pieza menos | El binario entra a la superficie pública; el ACK se bloquea por la descarga | Biométricos en la zona expuesta (A04) |

> **B** queda descartada por la convención del proyecto: el webhook **no procesa** ni invoca workers,
> solo publica el crudo. **E** por no llevar binarios a la superficie pública; **D** por la regla de
> minimización de procesadores externos de [ADR-0001](0001-llm-on-premises.md).

## Consecuencias

- **Positivas:** el **webhook no toca workers ni almacén** — su única salida es publicar el crudo, así
  que un compromiso del borde no expone PII, tokens ni binarios; el procesamiento (PII, evento,
  normalización) vive en el **Meta Handler** sin exposición pública; cada etapa escala y se endurece
  por separado y absorbe picos con reintentos; el ACK rápido respeta a Meta sin bloquear; la bóveda
  vive dentro del trust boundary con escaneo CSAM y cifrado de sobre; la trazabilidad por
  `EventAction` se conserva del repo de referencia; reutiliza el patrón cola+worker (ADR-0001) y el
  cifrado JWE de cuerpos; **ningún mensaje inprocesable se pierde**: cae a su DLQ y el Gestor de DLQ
  lo audita a nivel de evento.
- **Negativas / deuda asumida:** más servicios y colas que operar (mitigado con DLQ + reintentos y
  observabilidad); un **hop extra de latencia** (`meta.received` → Meta Handler) a cambio del
  desacople; **consistencia eventual** entre la recepción del mensaje y el `media.stored`
  (el chatbot puede recibir el texto antes de que el medio esté en bóveda → se correlaciona por
  `event_id`/`media_ref`); dependencia operativa de Redis (idempotencia) y del secrets manager.
- **Impacto en threat model:**
  - **T1/T11 (suplantación de webhook / replay):** la validación HMAC `X-Hub-Signature-256` y la
    guarda de idempotencia descartan payloads falsos y reintegros antes de crear eventos.
  - **A04 (biométricos):** el binario nunca toca la superficie pública ni se reenvía por la red
    social; entra a la bóveda cifrada vía el worker.
  - **A02 (cripto):** cifrado de sobre (DEK+KMS) y claves en el secrets manager; ni el operador del
    object store lee los medios.
  - **Child-safety:** el escaneo CSAM es obligatorio antes de persistir (relevante por menores en
    personas desaparecidas).
  - **A08 (integridad / observabilidad):** la DLQ universal y el Gestor de DLQ garantizan que todo
    fallo queda auditado en el `Event` (EventAction ERR) y es alertado/reprocesable, sin pérdida
    silenciosa (RS-06).

## Decisiones abiertas

- `<TODO>` Motor concreto de escaneo CSAM/AV y proveedor de listas de hashes (legal + operativo).
- `<TODO>` Política de retención y borrado de medios crudos vs. embeddings (alinear con GDPR/RS-08).
- `<TODO>` TTL de idempotencia y estrategia de correlación texto↔medio cuando el adjunto tarda.
- `<TODO>` ¿El servicio de salida comparte despliegue con el manager o es worker independiente?
- `<TODO>` Parámetros de la DLQ: número de reintentos `N`, curva de backoff, TTL por cola, y
  política de reproceso (manual vs. automático tras corrección).

## Disparadores de revisión

- Volumen de webhooks supera la capacidad sin estado → autoescalado / partición por bot.
- Falsos positivos del escáner bloquean medios legítimos → ajustar política y revisión humana.
- Cambios en la firma o el formato de webhooks de Meta (Graph API) → actualizar validador y DTOs.
- Crecimiento sostenido de una `*.dlq` → señal de fallo sistémico aguas arriba; revisar causa raíz.
- Latencia de descarga de medios degrada el matching → prefetch / colas dedicadas por tipo.
