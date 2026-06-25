# Gate 1 — Design

Criterio de cierre de la fase 02-design. No marcar superado si queda un criterio sin fundamentar.

| Criterio | Estado | Evidencia |
| :---- | :---- | :---- |
| Arquitectura (Clean/DDD, contextos acotados) | ✅ | `docs/02-design/architecture.md` |
| C4 validado (contexto + contenedores) | ✅ | `docs/architecture/c4-context.md`, `c4-container.md`, `c4-component-chatbot.md` (validados) |
| Threat model STRIDE/DREAD del sistema | ✅ | `docs/02-design/threat-model.md` (T1…T12 priorizadas y trazadas) |
| ADRs de decisiones clave | ✅ | ADR-0001 (LLM on-prem), ADR-0002 (NeMo Guardrails), ADR-0003 (Modelo A) |
| Contratos de API (esqueleto) | ✅ | `docs/02-design/api-contracts.md` (OpenAPI/AsyncAPI detallado pendiente) |
| Patrones de seguridad por amenaza DREAD | ✅ | `architecture.md` (tabla) + trazabilidad en `threat-model.md` |

**Estado del Gate 1: SUPERADO con deuda documentada** (2026-06-25).

Deuda abierta (no bloqueante para Gate 1, a resolver en implementación):
- Especificación OpenAPI/AsyncAPI detallada.
- Mecanismo legal de transferencia transfronteriza (T7, ADR-0003).
- Diseño de mínima divulgación de SAIME (T8) antes de Fase 2.
- ADR del motor de matching (algoritmo, umbrales, sesgo).
