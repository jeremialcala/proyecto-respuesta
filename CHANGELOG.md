# Changelog

Todos los cambios notables de **Respuesta** se documentan en este archivo.

El formato se basa en [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
y el proyecto se adhiere a [Versionado Semántico](https://semver.org/lang/es/).

Tipos de cambio: `Added` (nuevo), `Changed` (cambios en lo existente), `Deprecated`
(a retirar pronto), `Removed` (retirado), `Fixed` (correcciones), `Security` (seguridad).

## [Unreleased]

### Added

- **ADR-0014 + artefactos de despliegue** (`docs/00-project/adr/0014-contenedores-despliegue-eks.md`,
  `deploy/`): todas las apps **container-ready**. `Dockerfile` no-root por servicio (gateway
  python-slim; matching base CUDA para GPU); **`docker-compose.yml`** con Postgres+pgvector, Redis y
  LocalStack (SQS/SNS) para dev local; **`deploy/k8s`** (kustomize) para EKS con IRSA por workload,
  Ingress ALB + HPA (gateway), KEDA por profundidad de cola + nodos GPU (matching), Pod Security
  restricted y secretos vía External Secrets. YAML validado.
- **ADR-0012 y ADR-0013** (`docs/00-project/adr/`): broker de mensajería **AWS SQS/SNS** (0012,
  enmienda el transporte AMQP de ADR-0005/0011); **motor de embedding ArcFace/IResNet100 (512-d) y
  scoring solo-rostro en MVP** (0013, enmienda ADR-0004). Resueltas las decisiones de arranque:
  nombres de eventos en inglés, cloud AWS con GPU on-prem.
- **ADR-0006 a ADR-0011** (`docs/00-project/adr/`): residencia en São Paulo (0006, enmienda la región
  del 0003); esquema dinámico del reporte + retención + auditoría append-only SHA-256 (0007); bóveda de
  llaves por usuario con HashiCorp Vault + identidad WhatsApp+email/KYC (0008); auth del portal con
  Auth0/OAuth2 (0009); back office — roles, match manual con firma, certificación de rescatistas y
  validación jerárquica de autoridades (0010); contrato común de eventos con sobre estándar (0011).
- **Inventario de definiciones del MVP** (`inventario-definiciones-mvp.md`): componentes 1-7 + contrato
  de eventos, con estado definido/pendiente por componente.

### Changed

- **Residencia de datos: UE → São Paulo (`sa-east-1`)** propagada en cascada a charter,
  `data-classification.md`, `threat-model.md` (T4/T7), `architecture.md`, `openapi.yaml`,
  `asyncapi.yaml` y C4 de contenedores. GDPR pasa a ser listón interno (residencia bajo LGPD); el
  cifrado por usuario (Vault, ADR-0008) se vuelve la primera línea de blindaje.
- **Secrets manager concretado a HashiCorp Vault** (ADR-0005 "KMS" → ADR-0008) en C4 y docs.
- **Eventos**: sobre común (ADR-0011) y nuevo `match.resuelto` añadidos a `asyncapi.yaml`,
  `api-contracts.md`; endpoints de portal y back office añadidos a `api-contracts.md`.
- **Glosario**: términos de plataforma/eventos (Bóveda, Cifrado por usuario, Auditoría append-only,
  Certificación de rescatista, Cadena de confianza, Match manual, Sobre de evento).
- **Broker AMQP/RabbitMQ → AWS SQS/SNS** (ADR-0012) propagado a `asyncapi.yaml` (server sqs, DLQ por
  redrive), C4 de contenedores (relaciones SQS), `api-contracts.md`. Evento `match.resuelto` renombrado
  a **`match.resolved`** y catálogo de eventos unificado a **inglés** (ADR-0011).
- **Motor de matching SFace → ArcFace/IResNet100 (512-d)** y **scoring solo-rostro** (ADR-0013)
  reflejado en inventario y contratos; recalibración de umbrales pendiente (fase 04).
- **Hardware del MVP fijado: NVIDIA RTX 3090 (24 GB) on-prem**, compartida por el LLM (ADR-0001) y ArcFace (ADR-0013); registrado en ADR-0001/0006/0013.
- **`apps/matching-worker` reescrito a ArcFace + SQS/SNS** (ADR-0012/0013): adaptadores `arcface_facemapper`, `sqs_consumer`, `sqs_sns_event_bus`; `pgvector`/`faiss` a **512-d**; sobre de eventos (`application/events`) y payload `candidate.generated` alineados a ADR-0011; `amqp_consumer` deprecado; wiring en `__main__`. **32 tests en verde** (23 previos + envelope/config/payload).
- **`apps/meta-handler` nuevo (ingestión Meta, fase 03)**: 2.º eslabón de [ADR-0005](docs/00-project/adr/0005-webhook-manager-vault-worker.md) — consume `meta.received`, **normaliza** (object/contacto/tipo) y reparte a `inbound.text` (texto/ubicación, cuerpo JWE) o `inbound.media` (solo `media_id`, el binario no viaja). Clean Architecture/DDD; consumidor + publicador SQS; cipher JWE y Event store como placeholders (fase 03). Container-ready (Dockerfile, k8s+KEDA, compose). **11 tests en verde** (normalize + handler).
- **`apps/webhook-gateway` nuevo (ingestión Meta, fase 03)**: Webhook Gateway de [ADR-0005](docs/00-project/adr/0005-webhook-manager-vault-worker.md) sobre SQS — verificación handshake, firma `X-Hub-Signature-256`, idempotencia por `wamid.` (Redis) y publicación del crudo a `meta.received` (sobre ADR-0011). Clean Architecture/DDD; FastAPI + adaptadores Redis/SQS con deps perezosas. **15 tests en verde** (firma, payload, servicio con fakes).

- **Contratos formales 02-design**: `openapi.yaml` (OpenAPI 3.1 — 11 endpoints, 15 esquemas,
  seguridad bearer/JWT, errores RFC 7807, rate limit) y `asyncapi.yaml` (AsyncAPI 2.6 — 6 canales
  AMQP, payload del candidato alineado a ADR-0004). YAML validado; resuelve los TODO de `api-contracts.md`.
- **`apps/matching-worker` esqueletado (test-first, fase 03)**: Clean Architecture/DDD con dominio
  puro implementado y **23 tests en verde** — `drift` (bandas + invariante de no auto-confirmación),
  `fusion` (pesos dinámicos), `quality` y `tracking` (umbral de re-id estricto), más
  `MatchingService` con fakes. Adaptadores (OpenCV YuNet+SFace, pgvector, FAISS HNSW, AMQP) en
  esqueleto. Parámetros en `config.py` (τ0, M=32, efSearch=32…) para calibrar en fase 04.

- **PRD del flujo central** (`docs/01-requirements/flujo-central.md`): reporte → match →
  confirmación → notificación. Incluye escenarios positivos (EP-01…EP-04), escenarios
  negativos/de abuso (AB-01…AB-11), requisitos funcionales (RF-01…RF-13) y requisitos de
  seguridad mapeados a OWASP ASVS + Top 10:2025 (RS-01…RS-14). Avanza Gate 0.
- **Diagramas C4** (`docs/architecture/c4-context.md`, `c4-container.md`) en Mermaid: vista de
  Contexto (actores + PFIF/ICRC, telecom, SAIME Fase 2) y de Contenedores (web, chatbot, back
  office, API, motor de matching, cola offline-first, almacenes), con trust boundaries y
  superficies sensibles marcadas. Avanza Gate 1.
- **README.md** del proyecto: resumen, arquitectura, privacidad/seguridad, estructura de
  documentación AI-DLC y estado por fase.
- **Diagrama C4 de Componentes del chatbot** (`docs/architecture/c4-component-chatbot.md`):
  adaptadores de canal, orquestador LLM, intake, guarda de opt-in/relay e ingestor de medios.
- **ADR-0001 — LLM on-premises** (`docs/00-project/adr/0001-llm-on-premises.md`): decisión de
  servir el LLM con Ollama + worker frente a un proveedor gestionado, con pros/contras para un
  servicio masivo sin funding; ruta de evolución a vLLM/TGI. Avanza Gate 1 (ADRs).
- **ADR-0002 — NeMo Guardrails** (`docs/00-project/adr/0002-nemo-guardrails-prompt-injection.md`):
  capa anti prompt-injection (input/output/topical rails) sobre el LLM on-prem, como defensa en
  profundidad; heurísticos-primero por costo. Componente de rieles añadido al C4 del chatbot y
  trazado en RS-13.
- **ADR-0003 — Hosting Modelo A** (`docs/00-project/adr/0003-hosting-modelo-a.md`): formaliza el
  responsable humanitario internacional + hosting UE/grado GDPR, con alternativas B/C/D y la
  reconciliación con el LLM on-premises (infra bajo nuestro control en la jurisdicción del Modelo A).
- **Threat model STRIDE/DREAD** (`docs/02-design/threat-model.md`): STRIDE por componente + 12
  amenazas priorizadas con DREAD (T1…T12) trazadas a controles RS-xx y ADRs.
- **Diseño 02-design**: `architecture.md` (Clean/DDD, contextos acotados, patrones de seguridad) y
  `api-contracts.md` (endpoints REST + eventos AMQP, esqueleto).
- **Estructura AI-DLC completa**: `.ai-dlc/gates/` (Gate 0 y Gate 1 con estado), `.ai-dlc/templates/`
  (prd, threat-model, adr), placeholders de fases `03-06` y `apps/` (servicios ejecutables).
- **ADR-0004 — Motor de matching** (`docs/00-project/adr/0004-motor-de-matching.md`): pipeline
  facial OpenCV YuNet+SFace (face map por persona), tolerancia a drift de edad que empuja a revisión
  humana (no auto-acepta) y fusión multi-señal. C4 de componentes del motor
  (`docs/architecture/c4-component-matching.md`) y RF-04/RF-14/RF-15 en el PRD.
- **Gate 1 SUPERADO** (con deuda documentada): C4 + threat model + ADRs + contratos de API.

### Changed

- **Verificación de parentesco**: integración con Facebook descartada (restricción de la Graph
  API). Fase 1 pasa a **honor-based** (filiación auto-declarada); Fase 2 se define como **SAIME**
  (biometría nacional), diferida por su alto riesgo de privacidad.
- **Umbral de confianza**: > 85 % ya no es verificación automática — ahora requiere **confirmación
  de coordinador**; la única vía automática es el autoreporte (100 %). Actualizado en charter,
  glosario, PRD (RF-06/RF-07) y memoria.
- **Chatbot**: ahora opera sobre **WhatsApp, Instagram, Messenger y Telegram** con un **LLM
  autenticado** que conversa y media el intercambio entre actores. Propagado a charter, glosario,
  data-classification, PRD (RF-01) y los tres diagramas C4 (contexto, contenedores, componentes).
- **LLM on-premises**: el LLM pasa de proveedor externo a self-hosted dentro de la frontera (la PII
  conversacional ya no sale del sistema). Eliminado como sistema externo en los tres C4.
- **Proof-of-life** se entrega como **link asegurado por login**, no como video compartible en chat.
- **Onboarding de baja fricción**: el rescatista certificado reporta vía WhatsApp sin instalar app
  ni web; la cola nativa del dispositivo retiene el mensaje hasta tener señal (RF-02).
- **Motor de matching — parámetros resueltos** (ADR-0004): almacenamiento **pgvector** (fuente de
  verdad, borrado GDPR/merge) + **FAISS HNSWFlat** (M=32, efConstruction=128, efSearch=32) como
  índice ANN refrescado desde pgvector (HNSW no borra in-place); muestreo de video **Hierarchical
  Windowing** con tracking previo (umbral de agrupación ~0.40-0.45, más estricto que el match);
  función de tolerancia a drift (`τ0` + `Δ(edad, age_gap)` que empuja a coordinador) y **fusión de
  pesos dinámicos**. Reflejado en el C4 del motor.

### Security

- Nuevos escenarios de abuso en el PRD: declaración de filiación falsa honor-based (AB-12), fuga
  del grafo de consultas a SAIME (AB-13), exposición de datos en redes de mensajería de terceros
  (AB-14) y LLM tratado como autoritativo o relay sin opt-in (AB-15). Nuevo requisito RS-15
  (procesadores externos: DPA, sin biométricos por el canal, opción LLM self-hosted).
- AB-02 reforzado: el onboarding por número de WhatsApp es un autenticador débil (SIM swap) → se
  exige handshake de certificación y re-verificación. RS-15 actualizado a LLM on-premises.
- Matriz de abuso del flujo central trazada a OWASP (vigilancia de buscadores, suplantación de
  actores, falsos positivos de alto costo, exfiltración de biométricos, prompt injection en chatbot).

## [0.1.0] - 2026-06-25

Fase `00-project` (concepto y fundamentos de diseño) completa.

### Added

- **Charter del proyecto** (`docs/00-project/charter.md`): visión, contexto del terremoto del
  24-06-2026, alcance/no-scope, actores, restricciones, métricas de éxito y riesgos.
- **Taxonomía de estados** de persona (`desaparecido`, `a_salvo`, `localizado_estable`,
  `localizado_critico`, `fallecido`, `no_identificado`) y matriz de transiciones con autoridad por
  mecanismo (autorreporte/rescatista/coordinador/autoridad).
- **Glosario y lenguaje ubicuo** (`docs/00-project/glossary.md`): términos DDD en cinco contextos
  acotados (Intake, Identidad y Acreditación, Matching, Notificación y Privacidad, Interoperabilidad).
- **Clasificación de datos** (`docs/00-project/data-classification.md`): inventario de datos
  sensibles con clasificación, base GDPR, cifrado y retención.
- **Decisiones de diseño**: motor único de resolución de entidades (tres emparejamientos);
  generación automática de candidatos con confirmación humana; conciencia de red opt-in; video
  proof-of-life (~30 s) consentido; offline-first; interoperabilidad PFIF.
- **Acreditación de actores** en coordinación con autoridades; verificación de parentesco por fases
  (Fase 1 social vía Facebook, Fase 2 gubernamental).
- **Umbral de confianza** parametrizable: <65 % descarte, 65–85 % a coordinador, >85 % automático.
- **Definición de "cierre de la emergencia"**: cierre de búsqueda + inicio de reconstrucción + 12
  meses (con evidencias auditables), como gatillo del borrado de datos Restringidos.
- **Modelo de responsable del tratamiento y jurisdicción** (Modelo A): operador humanitario
  internacional + hosting nube UE / grado GDPR; gobierno fuera de la custodia de datos sensibles.

### Security

- Listón regulatorio **GDPR** adoptado (incl. categoría especial Art. 9 para biométricos).
- Guardarraíl: el estado `fallecido` solo lo fija la autoridad civil/médica; el sistema lo
  transmite, nunca lo deduce.
- Privacidad por diseño: identidades de buscadores no se exponen por defecto; conexión opt-in y
  revocable; control de acceso/reenvío sobre fotos y video.

[Unreleased]: https://example.com/respuesta/compare/v0.1.0...HEAD
[0.1.0]: https://example.com/respuesta/releases/tag/v0.1.0
