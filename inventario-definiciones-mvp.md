# Respuesta — Inventario de Definiciones para Iniciar el MVP

> **Proyecto:** Respuesta — Plataforma de FaceMatch para personas desaparecidas, terremoto Venezuela 2026
> **Fecha:** 2026-06-25 · **Actualizado:** 2026-06-26 (componentes 1-7 + contrato definidos; decisiones formalizadas en ADR-0006 a ADR-0011)
>
> **Formalización:** las decisiones de este inventario se registraron como ADRs en `docs/00-project/adr/`:
> ADR-0006 (residencia São Paulo), ADR-0007 (esquema/retención/auditoría SHA-256), ADR-0008 (bóveda Vault + identidad),
> ADR-0009 (auth Auth0), ADR-0010 (back office), ADR-0011 (contrato de eventos). Cascada propagada a charter,
> data-classification, glossary, architecture, threat-model, api-contracts, openapi, asyncapi y C4.
> **Propósito:** Inventario de las definiciones técnicas y de producto para arrancar la implementación, organizado por componente. Cada ítem está marcado como **Definido**, **Pendiente** o **Bloqueante**.

---

## Resumen ejecutivo

Estado tras las decisiones (componentes 1-7 + contrato de eventos definidos):

- ✅ **Sin bloqueantes.** Los 7 componentes funcionales y el contrato común de eventos (sección 9: `reporte.creado`, `match.evaluado`, `notificacion.estado_cambiado`) están definidos. Se puede paralelizar la implementación.
- 🟡 **Flecos abiertos (no bloqueantes):** modelo/versión de embeddings, contenido de la plantilla HSM, proceso del resumen diario de jornada, TTL de deduplicación, canal/plantilla de notificaciones delicadas, evento `match.resuelto` (firma del coordinador), broker/versionado de eventos, scoring solo-rostro vs compuesto, offline-first y cumplimiento legal Venezuela.

---

## 1. Infra de ingestión META / WhatsApp

| Definición | Estado | Detalle |
|---|---|---|
| Modelo de cuenta | ✅ Definido | WhatsApp Business. |
| Verificación del webhook | ✅ Definido | Se genera un JWT propio del bot, almacenado en Postgres. *Nota: el JWT cubre la auth interna; mantener además la validación de firma `X-Hub-Signature-256` de Meta y el `verify_token` del handshake del webhook, que son requisitos del lado de Meta.* |
| Idempotencia | ✅ Definido | Clave de deduplicación = `message.id` de Meta (prefijo `wamid.`). Falta fijar el TTL de la tabla de deduplicación. |
| Tipos de mensaje en MVP | ✅ Definido | Texto, imagen y ubicación. |
| Plantillas (HSM) | ✅ Definido | Una sola plantilla aprobada. Falta redactar el contenido y enviarla a aprobación de Meta. |
| Ventana de 24h | ✅ Definido (concepto) | Se mantiene abierta con notificaciones de anuncios generales de la jornada de rescate (resumen diario con indicadores). **Pendiente:** quién/qué genera ese resumen, qué indicadores incluye, horario y trigger del envío. |
| Rate limits y backpressure | ✅ Definido | Cola SQS con alerta si un mensaje permanece en cola > 10 min. |

---

## 2. Almacenamiento de reportes de desaparecidos

| Definición | Estado | Detalle |
|---|---|---|
| Esquema canónico del reporte | ✅ Definido | Esquema dinámico. **Obligatorios:** nombre completo, tipo de identificación, número de identificación. **Opcionales:** foto, última ubicación (coordenada o dirección), notas generales (p. ej. dolencias crónicas, medicamentos). Máquina de estados según `respuesta-state-machine`. |
| Modelo de datos biométricos | ✅ Definido | Se almacena la foto original + los embeddings usados en verificación. **Pendiente:** modelo generador de embeddings y su versión (los embeddings no son compatibles entre versiones → versionar el campo). |
| Clasificación y residencia | ✅ Definido (ADR-0006) | Toda la data tratada como sensible; cifrado con llaves individuales por usuario (Vault, ADR-0008); residencia en São Paulo (`sa-east-1`). Enmienda la región UE del ADR-0003 → LGPD con GDPR como listón interno; el cifrado por usuario pasa a ser la primera línea de blindaje. |
| Retención y borrado | ✅ Definido | Programado al cierre de la labor de rescate (indicado por el coordinador) + 12 meses de retención; el coordinador puede diferirlo. |
| Versionado / auditoría | ✅ Definido | Append-only en tabla inmutable para todas las operaciones, con verificación por SHA-256 (encadenamiento de hashes). |
| Motor de almacenamiento | ✅ Definido | Postgres + pgvector para embeddings. |

---

## 3. Workers de NeMo Guardrails (prompt injection)

| Definición | Estado | Detalle |
|---|---|---|
| Punto de inserción | ✅ Definido | Rails sobre el mensaje entrante del usuario y sobre la salida del LLM, con mecanismo de auditoría de la salida. |
| Política de rails | ✅ Definido | Bloquear: jailbreak, exfiltración de datos de otros reportes, instrucciones embebidas en mensajes. Mantener tono cordial y amable; no permitir insultos del interlocutor. |
| Acción ante detección | ✅ Definido | Al detectar coincidencia/evento se notifica al coordinador para ejecutar el match y la notificación posterior. En autoreporte o match 100% se notifica directamente según las instrucciones del rescatado. *Nota: separar "acción ante prompt injection detectado" de "acción ante match", que son flujos distintos — conviene aclararlo en el spec.* |
| SLA / latencia | ✅ Definido | < 1 minuto, objetivo 30–45 s. |
| Telemetría | ✅ Definido | Telemetría y logs en instancia de Signoz (seguimiento de peticiones y latencia interna) + tabla de auditoría que registra intentos de ejecutar acciones no permitidas con los datos del usuario. |

---

## 4. Worker de matching (rescatistas ↔ desaparecidos)

| Definición | Estado | Detalle |
|---|---|---|
| Algoritmo de similitud | ✅ Definido (alineado a ADR-0004) | Bandas: **< 65%** descarte; **65–85%** → revisión manual del coordinador; **> 85%** → fusión/enlace **solo con confirmación del coordinador** (el face-match nunca auto-confirma); **100% = autoreporte** → única vía automática. Reportes que matchean entre sí se unifican por persona; se avisa al que reporta que hay varios con el mismo reporte mostrando el opt-in de notificación a terceros; tras aceptación mutua se hace divulgación mutua. Menores/drift de edad → siempre a coordinador. |
| Pipeline de matching | ✅ Definido | Streaming on-insert; ante registros nuevos de rescatistas se compara contra la base completa de embeddings. |
| Combinación multi-señal | ✅ Definido | El match se hace por cara; la ubicación es información obligatoria del reporte (contexto, no scoring en MVP). |
| Manejo de N:M | ✅ Definido | Colisión de un rescatado con múltiples reportados como desaparecidos requiere intervención del coordinador para la notificación. |
| Salida del match | ✅ Definido | > 85% → fusión con confirmación del coordinador y notificación a quienes reportaron; 65–85% → verificación por coordinador; 100% autoreporte automático. Estructura del evento en el contrato (`match.evaluado` / `match.resuelto`, ADR-0011). |

---

## 5. Bóveda de llaves por usuario (por número de teléfono)

| Definición | Estado | Detalle |
|---|---|---|
| Modelo criptográfico | ✅ Definido | Se cifran los PII y los archivos de medios almacenados en S3, con llave por usuario. |
| Gestión de claves (KMS) | ✅ Definido | HashiCorp Vault para el manejo de secretos por usuario. |
| Derivación de identidad | ✅ Definido | Fase 1: verificación conjunta WhatsApp + email. Fase 2: KYC completo para asegurar la identidad de todos los actores. |
| Recuperación | ✅ Definido | Autogestión vía correo + WhatsApp; recuperación manual desde el back office. |
| Quién puede descifrar | ✅ Definido | El coordinador, desde el back office, puede ver la data en claro para la gestión del ciclo de vida de los reportes. *Nota: registrar cada acceso en claro en la tabla de auditoría append-only.* |

---

## 6. Dashboard (auth Google, "mis reportes")

| Definición | Estado | Detalle |
|---|---|---|
| Identidad federada | ✅ Definido | Onboarding web con WhatsApp + correo, integrado con Auth0 para social login (Gmail, Facebook, Hotmail). |
| Modelo de autorización | ✅ Definido | Un solo rol en MVP: el usuario administra sus reportes, ve reportes públicos y puede marcar los propios como públicos para la red. |
| OAuth | ✅ Definido | Integración con Auth0, un tenant para todo OAuth 2.0. |
| Qué muestra | ✅ Definido | Lista de reportes propios + timeline de eventos. |
| Stack del frontend | ✅ Definido | Nginx + NestJS + Redis + Postgres, en TypeScript. |

---

## 7. Back office (coordinador)

### 7.1 Matriz de roles y permisos ✅ Definido

| Módulo / Acción | Rescatista | Coordinador Verificado | Autoridad Civil/Médica |
|---|:---:|:---:|:---:|
| Reportar desaparecido (crear registro) | ✓ | ✓ | ✓ |
| Enviar información de rescatado (con/sin video *proof-of-life*) | ✓ | ✓ | ✓ |
| Registrar y certificar nuevos rescatistas | ✗ | ✓ | ✗ |
| Moderar y resolver colisiones (múltiples buscadores) | ✗ | ✓ | ✗ |
| Aprobar matches manuales (confianza < 85%) | ✗ | ✓ | ✗ |
| Confirmar estado de salud crítico / fallecimiento | ✗ | ✗ | ✓ |
| Autorizar notificaciones de personas inconscientes | ✗ | ✗ | ✓ |

### 7.2 Flujo de match manual ✅ Definido

UI de revisión de coincidencia (comparación lado a lado Entidad A = reporte de búsqueda vs Entidad B = reporte en terreno), con panel de resolución: **ES UN MATCH** (agrupa reportes y notifica a familiares) o **DESCARTAR** (separa entidades de forma permanente). Justificación obligatoria + firma del coordinador (usuario + ID) registrada en auditoría.

Contrato del evento de match (revisión manual):

```json
{
  "match_id": "match_550e8400",
  "confidence_score": 0.72,
  "status": "PENDING_REVIEW",
  "created_at": "2026-06-26T13:10:00Z",
  "entity_a_search": {
    "person_id": "per_search_1111",
    "first_name": "Alejandro José",
    "last_name": "Pérez Mendoza",
    "national_id": "V-18452931",
    "age": 34,
    "distinctive_features": "Tatuaje de cruz en antebrazo derecho",
    "last_seen_location": "Los Palos Grandes, Caracas",
    "reporter_relationship": "Hermana",
    "reporter_location": "Bogotá, Colombia"
  },
  "entity_b_found": {
    "person_id": "per_found_2222",
    "first_name": "Alejandro",
    "last_name": "Pérez M.",
    "national_id": null,
    "estimated_age": 32,
    "distinctive_features": "Tatuaje en el brazo derecho visible en video",
    "current_location": "Refugio San Agustín, Caracas",
    "rescued_by_user_id": "usr_rescatista_024",
    "proof_of_life_video_url": "https://storage.respuesta.org/videos/20260626_2222.mp4"
  }
}
```

*Nota: este esquema es la base del contrato de eventos (sección 8). Falta extenderlo con los estados resueltos (`MATCHED` / `DISCARDED`), la decisión y firma del coordinador, y el evento de "cambio de estado".*

### 7.3 Certificación de rescatistas ✅ Definido

Proceso en 3 fases: **(1) Registro & carga** — el rescatista ingresa datos + fotos; **(2) Verificación** — un Coordinador Verificado o Autoridad Civil/Médica evalúa la evidencia; **(3) Certificación** — activación de cuenta con emisión de token JWT.

Máquina de estados de la verificación:

```
[ PENDING ] --> [ CERTIFIED ] --> [ REVOKED ]
     |
     +--------> [ REJECTED ]
```

### 7.4 Validación de autoridades ✅ Definido

Modelo jerárquico de confianza en cascada, sembrado por un **Admin Global**:

- **Nivel 1 — Raíz (ADMIN):** modera la plataforma global; carga el listado inicial de autoridades nacionales y directores regionales (p. ej. Director Nacional de Protección Civil, directores de hospitales base).
- **Nivel 2 — Celdas regionales (confianza máxima):** autoridades gubernamentales validadas que sub-delegan a autoridades municipales o centros de salud dentro de su celda geográfica.
- **Nivel 3 — Nodos locales (centros médicos / refugios):** autoridades en terreno que certifican identidades y estados de salud in situ.

Flujo de alta: **(1) Pre-carga** de nómina oficial por el ADMIN (cédula + cargo) → **(2) Invitación segura** con credencial única vía canal seguro (email/satélite) → **(3) Validación en dos pasos** (OTP SMS/satélite + token gubernamental) y activación con firma criptográfica.

### 7.5 Notificación de información delicada ✅ Definido

Tres flujos restringidos a Autoridad Civil/Médica:

- **A. Certificación de deceso:** única vía para cambiar un perfil a `Confirmado Fallecido`. Exige adjuntar número de acta médica o foto de la planilla forense. Bloquea el perfil para edición pública y lo envía a la cola de notificaciones restringidas/humanitarias hacia buscadores con parentesco verificado.
- **B. Visibilidad de personas localizadas inconscientes / no identificadas:** perfiles de personas en shock, coma o menores que no pueden identificarse entran en estado oculto automático. Solo las Autoridades Civiles de la zona hexagonal correspondiente acceden a la base de "Anónimos Inconscientes" para cruzarla de forma controlada, evitando exposición pública de fotos de menores o personas vulnerables.
- **C. Autorización de notificación de impacto:** romper el secreto de datos y disparar notificaciones SMS/Push a buscadores de colisión requiere firma digital de la Autoridad. Hasta esa firma, los familiares solo ven `En Proceso de Localización`, impidiendo que reciban noticias médicas críticas sin confirmación oficial del centro de salud.

**Pendientes menores:** canal y plantilla concretos de cada notificación, y formato del registro de consentimiento/trazabilidad legal por cada firma de liberación.

---

## 8. Definiciones transversales

| Definición | Estado | Detalle |
|---|---|---|
| Identidad unificada | ✅ Definido | WhatsApp + email + Auth0 unifican usuario web y de bot en fase 1; KYC en fase 2. |
| Contratos de API / eventos | ✅ Definido | Esquema común de eventos definido (ver sección 9): metadata base + `reporte.creado`, `match.evaluado`, `notificacion.estado_cambiado`. |
| Consentimiento opt-in | 🟡 Parcial | Definido el opt-in de divulgación a terceros en matching; falta el modelo general de captura/almacenamiento/revocación de consentimiento por canal. |
| Estrategia offline-first | 🟡 Pendiente | Qué significa para cada componente en zona de desastre con conectividad intermitente. |
| Observabilidad | ✅ Definido | Signoz para telemetría, logs, latencia + tabla de auditoría de acciones no permitidas. |
| Entornos e infra base | 🟡 Pendiente | Cloud provider (región São Paulo ya fijada), IaC, CI/CD. Secrets vía Vault ya decidido. |
| Cumplimiento legal Venezuela 2026 | 🟡 Pendiente | Marco de protección de datos aplicable además de GDPR. |

---

## 9. Contrato común de eventos ✅ Definido

### 9.1 Sobre (metadata base)

Todo evento comparte el mismo sobre; el `payload` varía según `event_type`.

```json
{
  "event_id": "uuid-v4-universal",
  "event_type": "nombre.del.evento",
  "producer": "componente-origen",
  "timestamp": "2026-06-26T16:20:00Z",
  "version": "1.0.0",
  "payload": {}
}
```

### 9.2 Flujo

```
[Bot / Dashboard] ──(reporte.creado)──> [Matching Worker] ──(match.evaluado)──> [Back Office / Notificador] ──(notificacion.estado_cambiado)──>
```

### 9.3 Paso 1 — `reporte.creado`

```json
{
  "event_id": "evt_01hc37f8...",
  "event_type": "reporte.creado",
  "producer": "core-backend",
  "timestamp": "2026-06-26T16:21:00Z",
  "version": "1.0.0",
  "payload": {
    "reporte_id": "rep_992834",
    "tipo_fuente": "BOT_WHATSAPP",
    "rostro": {
      "embedding_dimension": 512,
      "embedding": [0.0123, -0.0456, "...", 0.1234],
      "calidad_captura": 0.92
    },
    "contexto_fusion": {
      "geo": {
        "latitud": 10.4806,
        "longitud": -66.9036,
        "confianza_geo": 1.0
      },
      "texto": {
        "metadatos_extraidos": "Masculino, aproximadamente 35 años, franela negra",
        "confianza_texto": 0.85
      }
    },
    "metadata_sujeto": {
      "edad_estimada": 35.0
    }
  }
}
```

### 9.4 Paso 2 — `match.evaluado`

```json
{
  "event_id": "evt_01hc37f9...",
  "event_type": "match.evaluado",
  "producer": "worker-matching-hnsw",
  "timestamp": "2026-06-26T16:21:02Z",
  "version": "1.0.0",
  "payload": {
    "reporte_id": "rep_992834",
    "evaluacion_timestamp": "2026-06-26T16:21:02Z",
    "match_encontrado": true,
    "score_fusion_final": 0.8945,
    "criterio_decision": {
      "umbral_drift_aplicado": 0.509,
      "distancia_coseno_rostro": 0.085,
      "pesos_efectivos_aplicados": {
        "rostro": 0.60,
        "geo": 0.25,
        "texto": 0.15
      }
    },
    "candidato_desaparecido": {
      "desaparecido_id": "desap_4412",
      "nombre_completo": "Nombre Resguardado",
      "edad_base_registro": 33,
      "age_gap_anos": 2
    }
  }
}
```

### 9.5 Paso 3 — `notificacion.estado_cambiado`

```json
{
  "event_id": "evt_01hc37f10...",
  "event_type": "notificacion.estado_cambiado",
  "producer": "notificator-service",
  "timestamp": "2026-06-26T16:21:03Z",
  "version": "1.0.0",
  "payload": {
    "reporte_id": "rep_992834",
    "desaparecido_id": "desap_4412",
    "nivel_alerta": "CRITICO",
    "estado_anterior": "PROCESANDO",
    "estado_nuevo": "ALERTA_MATCH_PENDIENTE",
    "canales_notificados": [
      {"canal": "DASHBOARD_WEBSOCKET", "status": "DELIVERED"},
      {"canal": "BOT_OPERADOR_WHATSAPP", "status": "SENT"}
    ],
    "mensaje_alerta": "ALERTA: Alta probabilidad de Match (89.45%) detectada para el reporte rep_992834 contra el registro desap_4412."
  }
}
```

### 9.6 Observaciones para normalizar

- **Canal del bot:** los ejemplos originales decían `BOT_TELEGRAM` / `BOT_OPERADOR_TELEGRAM`; se ajustó a WhatsApp para coherencia con la decisión del componente 1. Confirmar.
- **Tipografía de campos:** unificar `contexto_fusion` / `score_fusion_final` (sin la "c" extra de los borradores) en el esquema canónico.
- **Pesos multi-señal:** el evento `match.evaluado` ya incluye pesos rostro/geo/texto, lo que extiende la decisión "match solo por cara" del componente 4 hacia un scoring compuesto. Decidir si el MVP usa solo rostro (geo/texto en peso 0 o como contexto) o el compuesto completo.
- **Falta el evento de resolución manual** (`match.resuelto` con decisión + firma del coordinador) para cerrar el ciclo de la sección 7.2.
- Definir el **broker/transporte** (SQS ya elegido para ingestión) y la **política de versionado** del campo `version`.

---

## Próximos pasos sugeridos

Las decisiones ya están formalizadas en **ADR-0006 a ADR-0011** (`docs/00-project/adr/`) y propagadas
en cascada. Quedan como trabajo de implementación:

1. **Publicar el contrato de eventos como artefacto del repo** (JSON Schema por evento) y resolver las
   decisiones abiertas del [ADR-0011](docs/00-project/adr/0011-contrato-eventos.md): convención de
   nombres (ES vs EN) y broker (SQS del inventario vs AMQP/RabbitMQ del diseño existente — el ADR
   recomienda mantener AMQP).
2. **Decidir scoring del MVP:** solo-rostro vs compuesto rostro/geo/texto (el evento `match.evaluado`
   soporta pesos; ver [ADR-0004](docs/00-project/adr/0004-motor-de-matching.md)).
3. **Cerrar los flecos abiertos:** modelo/versión de embeddings, contenido de la plantilla HSM,
   proceso del resumen diario de jornada, TTL de deduplicación y canal/plantilla de las notificaciones
   delicadas.
4. **Definir transversales restantes:** estrategia offline-first por componente y base legal LGPD /
   cumplimiento Venezuela 2026 ([ADR-0006](docs/00-project/adr/0006-residencia-sao-paulo.md)).
5. Avanzar a la implementación por componente apoyándose en los ADRs y los contratos OpenAPI/AsyncAPI.
