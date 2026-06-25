# Changelog

Todos los cambios notables de **Respuesta** se documentan en este archivo.

El formato se basa en [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
y el proyecto se adhiere a [Versionado Semántico](https://semver.org/lang/es/).

Tipos de cambio: `Added` (nuevo), `Changed` (cambios en lo existente), `Deprecated`
(a retirar pronto), `Removed` (retirado), `Fixed` (correcciones), `Security` (seguridad).

## [Unreleased]

### Added

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

### Changed

- **Verificación de parentesco**: integración con Facebook descartada (restricción de la Graph
  API). Fase 1 pasa a **honor-based** (filiación auto-declarada); Fase 2 se define como **SAIME**
  (biometría nacional), diferida por su alto riesgo de privacidad.
- **Umbral de confianza**: > 85 % ya no es verificación automática — ahora requiere **confirmación
  de coordinador**; la única vía automática es el autoreporte (100 %). Actualizado en charter,
  glosario, PRD (RF-06/RF-07) y memoria.

### Security

- Nuevos escenarios de abuso en el PRD: declaración de filiación falsa honor-based (AB-12) y fuga
  del grafo de consultas a SAIME (AB-13).
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
