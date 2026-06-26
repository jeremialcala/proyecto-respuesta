# Diseño del Sistema — Respuesta

- **Fase AI-DLC:** 02-design
- **Estado:** draft

## Estilo arquitectónico

**Clean Architecture / hexagonal** con **DDD**. El dominio (entidades-persona, reportes, estados,
matching) es el núcleo y no depende de frameworks; los canales (web, chatbot, back office), los
almacenes y los sistemas externos (PFIF, SAIME, redes de mensajería, LLM) son **adaptadores** en la
periferia. Regla de dependencia: hacia adentro. El **motor de matching** es un worker que consume de
la cola (event-driven), desacoplado de la captura para absorber picos.

## Contextos acotados (DDD)

| Bounded Context | Responsabilidad | Entidades núcleo |
| :---- | :---- | :---- |
| **Intake** | Captura multicanal y normalización de reportes | Reporte, Canal |
| **Identidad y Acreditación** | Quién es quién y quién puede actuar | Buscador, Rescatista, Coordinador, Autoridad, Acreditación |
| **Resolución de Entidades (Matching)** | Agrupar reportes en personas; candidatos | Entidad-persona, Candidato, Match, Clúster |
| **Notificación y Privacidad** | Estados, opt-in, proof-of-life, mediación | Estado, Notificación, Proof-of-life |
| **Interoperabilidad** | Federación con sistemas externos | Registro PFIF |

## Vista C4

Ver [`docs/architecture/c4-context.md`](../architecture/c4-context.md),
[`c4-container.md`](../architecture/c4-container.md) y
[`c4-component-chatbot.md`](../architecture/c4-component-chatbot.md). Los trust boundaries y las
superficies sensibles están marcados ahí.

## Decisiones de arquitectura (ADR)

- [ADR-0001](../00-project/adr/0001-llm-on-premises.md) — LLM on-premises (Ollama + worker).
- [ADR-0002](../00-project/adr/0002-nemo-guardrails-prompt-injection.md) — NeMo Guardrails.
- [ADR-0003](../00-project/adr/0003-hosting-modelo-a.md) — Hosting Modelo A (región enmendada por ADR-0006).
- [ADR-0004](../00-project/adr/0004-motor-de-matching.md) — Motor de matching (OpenCV YuNet+SFace, drift).
- [ADR-0005](../00-project/adr/0005-webhook-manager-vault-worker.md) — Ingestión de Meta asíncrona.
- [ADR-0006](../00-project/adr/0006-residencia-sao-paulo.md) — Residencia de datos en São Paulo.
- [ADR-0007](../00-project/adr/0007-esquema-reporte-retencion-auditoria.md) — Esquema del reporte, retención y auditoría SHA-256.
- [ADR-0008](../00-project/adr/0008-boveda-llaves-identidad.md) — Bóveda de llaves por usuario e identidad (Vault).
- [ADR-0009](../00-project/adr/0009-dashboard-auth-auth0.md) — Autenticación del portal (Auth0/OAuth2).
- [ADR-0010](../00-project/adr/0010-back-office-roles-flujos.md) — Back office: roles y flujos.
- [ADR-0011](../00-project/adr/0011-contrato-eventos.md) — Contrato común de eventos.

## Contratos de API

Esqueleto en [`api-contracts.md`](api-contracts.md) (endpoints REST + eventos SQS/SNS). Detalle
OpenAPI/AsyncAPI pendiente.

## Patrones de seguridad seleccionados (por amenaza DREAD priorizada)

| Amenaza | Patrón / Control | OWASP |
| :---- | :---- | :---- |
| T1 Vigilancia | Agregado anónimo + opt-in; scoping por clúster | A01 |
| T2 Falso positivo | Human-in-the-loop para acciones de alto costo | A06 |
| T3 DoS/abuso | Rate limiting + idempotencia + cola amortiguadora | A10 |
| T4 Exfiltración | Cifrado + control de acceso + Modelo A (datos fuera de jurisdicción de riesgo) | A04, A01 |
| T5 Prompt injection | NeMo Guardrails + LLM no autoritativo | A05 |
| T6 Suplantación | Acreditación + MFA + handshake de número | A07 |
| T7 Misconfig cloud | IaC endurecido, IAM mínimo, escaneo de config | A02 |
| T11 Repudio | Logging inmutable de transiciones | A09 |
| T12 Supply chain | Verificación de pesos + lockfiles + SCA | A03 |

## Principios transversales

Seguridad por diseño, test-first, **human-in-the-loop** (ninguna acción de alto costo sin un
humano), observabilidad continua y conciencia de cadena de suministro (ver `ai-dlc-overview`).
