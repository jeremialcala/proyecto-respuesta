# Respuesta

**Plataforma de cruce de datos de personas desaparecidas y encontradas tras el terremoto de
Venezuela de 2026.** Reconcilia reportes dispersos (familias, rescatistas, hospitales, refugios)
en una sola entidad por persona, para que quienes buscan tomen conciencia mutua, contribuyan a un
perfil compartido y reciban el estado más cercano al tiempo real posible.

> Contexto: doblete sísmico del 24-06-2026 (Yaracuy/Carabobo, intensidad IX), con apagones y caída
> de telecom en la capital y el occidente. La información de desaparecidos/encontrados quedó
> fragmentada; Respuesta es la capa que la cruza. No reemplaza a los actores de rescate ni a los
> registros globales: **interopera vía PFIF** con iniciativas como ICRC.

## Qué hace

- **Captura multicanal y offline-first** de reportes (desaparecido / encontrado / autoreporte) con
  foto, ubicación y descripción, desde web, **chatbot** (canal principal, sobre WhatsApp/Instagram/
  Messenger/Telegram con un LLM autenticado) y back office.
- **Motor de resolución de entidades**: agrupa reportes con un único motor y tres emparejamientos
  — colisión (buscador↔buscador), resolución (desaparecido↔encontrado) y deduplicación.
- **Conciencia de red opt-in**: detecta cuando varios buscan a la misma persona, sin exponer
  identidades por defecto.
- **Proof-of-life en video** (~30 s, consentido): la señal de identidad más fuerte del sistema.
- **Matching con confirmación humana**: ninguna fusión por face-match se confirma sin un humano;
  lo único automático es el autoreporte.

## Estados de una persona

`desaparecido` (inicial) · `a_salvo` · `localizado_estable` · `localizado_critico` ·
`fallecido` (solo autoridad) · `no_identificado`. Las transiciones tienen autoridad por mecanismo
(autorreporte / rescatista / coordinador / autoridad). Detalle en el [charter](docs/00-project/charter.md).

## Arquitectura

Cuatro componentes: **Portal Web**, **Chatbot**, **Back office** y **Motor de matching** (worker),
sobre un backend que orquesta reportes, estados y federación. Hosting bajo el **Modelo A** (operador
humanitario internacional, nube UE / grado GDPR). Ver los diagramas C4:

- [C4 — Contexto](docs/architecture/c4-context.md)
- [C4 — Contenedores](docs/architecture/c4-container.md)
- [C4 — Componentes: Pasarela de Chatbot](docs/architecture/c4-component-chatbot.md)
- [C4 — Componentes: Motor de Matching](docs/architecture/c4-component-matching.md)

## Privacidad y seguridad

- **GDPR** como listón regulatorio (Venezuela carece de ley integral de datos).
- Datos biométricos, video, ubicaciones y datos de menores tratados como **Restringido**.
- Guardarraíles: el estado `fallecido` solo lo fija la autoridad; identidades de buscadores no se
  exponen por defecto; borrado al **cierre de la emergencia** (cierre de búsqueda + reconstrucción
  + 12 meses).
- Verificación de parentesco: Fase 1 honor-based; Fase 2 SAIME con mínima divulgación (diferida por
  su alto riesgo de privacidad).

## Metodología y documentación

El proyecto sigue **AI-DLC** (seguridad por diseño, test-first, human-in-the-loop). Estructura de
documentos:

```
.ai-dlc/
├── gates/                      Checklists Gate 0 (✅) y Gate 1 (✅ con deuda)
└── templates/                  Plantillas reutilizables: prd, threat-model, adr
apps/                           Servicios ejecutables (api, chatbot, matching-worker, llm) — scaffolding
docs/
├── 00-project/
│   ├── charter.md              Visión, alcance, estados, restricciones, riesgos
│   ├── glossary.md             Lenguaje ubicuo (DDD) y contextos acotados
│   ├── data-classification.md  Inventario de datos sensibles y retención (GDPR)
│   └── adr/
│       ├── 0001-llm-on-premises.md                  ADR: Ollama + worker vs. proveedor gestionado
│       ├── 0002-nemo-guardrails-prompt-injection.md ADR: NeMo Guardrails anti prompt-injection
│       ├── 0003-hosting-modelo-a.md                 ADR: responsable internacional + hosting UE
│       └── 0004-motor-de-matching.md                ADR: OpenCV YuNet+SFace, drift de edad, fusión
├── 01-requirements/
│   └── flujo-central.md        PRD: reporte→match→confirmación→notificación (Gate 0)
├── 02-design/
│   ├── architecture.md         Clean/DDD, contextos acotados, patrones de seguridad
│   ├── threat-model.md         STRIDE por componente + amenazas DREAD priorizadas (T1…T12)
│   ├── api-contracts.md        Resumen de endpoints REST + eventos AMQP
│   ├── openapi.yaml            OpenAPI 3.1 (REST)
│   └── asyncapi.yaml           AsyncAPI 2.6 (eventos AMQP)
├── 03-implementation/          Fase 03 (Gate 2) — pendiente
├── 04-testing/                 Fase 04 (Gate 3) — pendiente
├── 05-deployment/              Fase 05 (Gate 4) — pendiente
├── 06-monitoring/              Fase 06 (Gate 5) — pendiente
└── architecture/
    ├── c4-context.md             Diagrama C4 de Contexto
    ├── c4-container.md           Diagrama C4 de Contenedores
    ├── c4-component-chatbot.md   Diagrama C4 de Componentes (chatbot)
    └── c4-component-matching.md  Diagrama C4 de Componentes (motor de matching)
```

## Estado

| Fase | Gate | Estado |
| :---- | :---- | :---- |
| 00 · Project | — | ✅ Charter, glosario, clasificación de datos |
| 01 · Requirements | Gate 0 | ✅ PRD del flujo central con escenarios de abuso y OWASP |
| 02 · Design | Gate 1 | ✅ C4, threat model STRIDE/DREAD, ADR-0001…0003 y esqueleto de API (deuda documentada) |
| 03 · Implementation | Gate 2 | 🚧 `apps/matching-worker` esqueletado test-first (dominio + 23 tests en verde; adaptadores pendientes) |
| 04-06 | Gates 3-5 | ⬜ Pendiente (estructura creada) |

Los cambios se registran en [CHANGELOG.md](CHANGELOG.md) (formato Keep a Changelog 1.1.0 +
Versionado Semántico). Versión actual: **0.1.0**.
