# Threat Model — Sistema Respuesta

- **Alcance:** sistema completo (web, chatbot+LLM, back office, API, motor de matching, almacenes,
  federación PFIF, SAIME Fase 2)
- **Fecha / versión:** 2026-06-25 · v0.1
- **Clasificación de datos:** ver [`docs/00-project/data-classification.md`](../00-project/data-classification.md)
- **Metodología:** STRIDE por componente + priorización DREAD; cada amenaza trazada a un control
  (RS-xx del PRD) y/o ADR.

## Diagrama de flujo de datos

Los DFD y los **trust boundaries** están en los diagramas C4:
[contexto](../architecture/c4-context.md), [contenedores](../architecture/c4-container.md)
(System_Boundary del Modelo A + "Zona de datos restringidos") y
[componentes del chatbot](../architecture/c4-component-chatbot.md). Las superficies sensibles
(almacén de medios, motor de matching, rieles del chatbot, SAIME, redes de mensajería) están
marcadas en rojo en esos diagramas.

## Análisis STRIDE por componente

| Componente | Spoofing | Tampering | Repudiation | Info Disclosure | DoS | Elevation |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| **Portal Web** | Sesión robada (T6) | Alterar reporte en tránsito | — | XSS/fuga de PII | Flood de formularios (T3) | Saltarse rol (T?) |
| **Pasarela de chatbot** | Suplantar nº WhatsApp (T6) | Manipular intención del mensaje | Negar envío | Adjunto sensible por canal de terceros (T4) | Flood de mensajes (T3) | — |
| **Orquestador + LLM on-prem** | — | **Prompt injection** (T5) | — | Fuga de PII en respuesta | Inferencia satura GPU (T3) | LLM ejecuta acción (mitigado: no autoritativo) |
| **Rieles (NeMo Guardrails)** | — | Bypass de riel | Falta de log de disparo | — | Rieles con LLM añaden carga | — |
| **API / Backend** | Token falsificado (T6) | Manipular transición de estado | **Repudio de transición** (T12) | Acceso cruzado entre clústeres (T1) | — | Escalada de rol |
| **Cola offline-first** | — | Reordenar/duplicar mensajes | — | — | Saturación de cola (T3) | — |
| **Motor de matching** | — | Envenenar candidatos | — | Sesgo/exposición | Carga de matching (T3) | Merge erróneo (T10) |
| **Almacén de entidades (PII)** | — | Alterar estados | — | **Exfiltración** (T4) | — | — |
| **Almacén de medios (biométrico)** | — | Sustituir media | — | **Exfiltración / proof-of-life filtrado** (T4, T9) | — | — |
| **Federación PFIF** | Repositorio falso | Registro manipulado | — | Sobre-compartir datos | — | — |
| **Redes de mensajería (ext)** | Cuenta tomada (T6) | — | — | Procesan el medio (T4) | Caída del canal | — |
| **SAIME (ext, Fase 2)** | — | — | — | **Fuga del grafo de consultas** (T8) | — | — |

## Amenazas priorizadas (DREAD)

Escala 1-10 por factor (D=Damage, R=Reproducibility, E=Exploitability, A=Affected users,
D=Discoverability). Score = promedio. Ordenadas de mayor a menor.

| ID | Amenaza | D | R | E | A | D | Score | Control / ADR |
| :-- | :---- | :-: | :-: | :-: | :-: | :-: | :-: | :---- |
| **T1** | Vigilancia: reportar a alguien solo para **descubrir quién más lo busca** (AB-01) | 8 | 7 | 7 | 6 | 6 | **6.8** | RS-02; conciencia de red anónima + opt-in; mediación |
| **T2** | **Falso positivo de match** notificado a una familia (hallazgo/muerte equivocada; agravado por drift de edad y sesgo) (AB-04) | 9 | 6 | 5 | 7 | 5 | **6.4** | RS-09, RF-07 (confirmación humana), proof-of-life; `fallecido` solo autoridad; drift/sesgo enrutan a coordinador (ADR-0004) |
| **T3** | Inundación de reportes falsos / **DoS** al motor y a coordinadores (AB-03) | 6 | 7 | 7 | 6 | 6 | **6.4** | RS-05 (rate limiting, dedup, anti-abuso) |
| **T4** | **Exfiltración de biométricos/ubicaciones** (acceso no autorizado o compulsión estatal) (AB-05, AB-14) | 10 | 5 | 4 | 9 | 4 | **6.4** | ADR-0003 (Modelo A); **residencia São Paulo (ADR-0006) baja el blindaje legal → se compensa con cifrado por usuario/Vault (ADR-0008)** como primera línea; RS-03 (cifrado), RS-02; no biométricos por el canal |
| **T5** | **Prompt injection** que desvía el LLM del chatbot (AB-07, AB-15) | 6 | 7 | 7 | 5 | 6 | **6.2** | ADR-0002 (NeMo Guardrails), RS-13; LLM no autoritativo (backstop) |
| **T6** | **Suplantación de rescatista/coordinador** (nº WhatsApp / SIM swap) (AB-02) | 8 | 5 | 6 | 6 | 5 | **6.0** | RS-01 (acreditación + MFA); handshake de certificación + re-verificación |
| **T7** | **Misconfiguración cloud** / transferencia transfronteriza insegura (A02) | 8 | 4 | 4 | 8 | 5 | **5.8** | RS-11; endurecer IAM/redes/buckets de `sa-east-1` (ADR-0006); base legal LGPD + transferencia VE→BR (`<TODO>`) |
| **T8** | **Fuga del grafo de consultas a SAIME** (Fase 2): el Estado deduce quién busca/aparece (AB-13) | 9 | 4 | 3 | 8 | 3 | **5.4** | Mínima divulgación; diferido a Fase 2 con salvaguardas |
| **T9** | **Filtración del proof-of-life** (reenvío/difusión) (AB-06) | 8 | 4 | 4 | 4 | 4 | **4.8** | RF-09 (link por login), RS-08 (control de reenvío) |
| **T10** | **Merge erróneo/malicioso** que une a dos personas distintas (AB-09) | 6 | 5 | 4 | 4 | 4 | **4.6** | RF-11 (merge reversible), umbral, revisión de coordinador |
| **T11** | **Repudio** de una transición de estado (AB-10) | 5 | 5 | 5 | 4 | 5 | **4.8** | RS-06 (logging inmutable con actor + timestamp) |
| **T12** | **Supply chain**: pesos del modelo o deps del worker comprometidos (A03) | 6 | 3 | 3 | 6 | 3 | **4.2** | RS-12; verificar origen/integridad de pesos, lockfiles, SCA |

> Nota: el DREAD es una priorización relativa para enfocar el diseño, no una métrica absoluta. Los
> datos de menores (AB-11) elevan el Damage de T2/T4 cuando aplican.

## Controles y trazabilidad

Cada amenaza prioritaria está cubierta por un control trazable:

- **T1, T8** → privacidad por diseño: opt-in, agregado anónimo, mínima divulgación (charter; AB-01/AB-13).
- **T2** → human-in-the-loop obligatorio para acciones de alto costo (RF-07, RS-09); `fallecido` solo autoridad.
- **T3** → defensa anti-abuso e idempotencia (RS-05); la cola absorbe picos sin perder mensajes.
- **T4, T7** → Modelo A ([ADR-0003](../00-project/adr/0003-hosting-modelo-a.md)); con residencia en
  São Paulo ([ADR-0006](../00-project/adr/0006-residencia-sao-paulo.md)) el blindaje legal baja y el
  **cifrado por usuario/Vault** ([ADR-0008](../00-project/adr/0008-boveda-llaves-identidad.md)) pasa a
  ser la primera línea; + control de acceso (RS-02/RS-03); hardening cloud (RS-11).
- **T5** → NeMo Guardrails ([ADR-0002](../00-project/adr/0002-nemo-guardrails-prompt-injection.md)) + LLM no autoritativo (RS-13).
- **T6** → acreditación + MFA + handshake (RS-01); identidad doble canal / KYC ([ADR-0008](../00-project/adr/0008-boveda-llaves-identidad.md)); revocación de rescatistas ([ADR-0010](../00-project/adr/0010-back-office-roles-flujos.md)).
- **T9** → proof-of-life como link por login (RF-09, RS-08).
- **T10, T11** → merge reversible (RF-11) + **auditoría append-only con SHA-256** ([ADR-0007](../00-project/adr/0007-esquema-reporte-retencion-auditoria.md)); firma por acción en el back office ([ADR-0010](../00-project/adr/0010-back-office-roles-flujos.md)).
- **T12** → supply chain del LLM on-prem ([ADR-0001](../00-project/adr/0001-llm-on-premises.md)) y deps (RS-12).

## Decisiones abiertas

- `<TODO>` Base legal LGPD y transferencia VE→BR (T7) — ver [ADR-0006](../00-project/adr/0006-residencia-sao-paulo.md).
- `<TODO>` Diseño de mínima divulgación de SAIME (T8) antes de habilitar Fase 2.
- `<TODO>` Política de calibración de umbral y rate limiting (T3) con datos reales.
