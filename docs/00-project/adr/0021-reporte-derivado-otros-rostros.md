# ADR-0021: Reporte derivado de otros rostros detectados (consulta tras desambiguación)

- **Estado:** proposed
- **Fecha:** 2026-06-29
- **Decisores:** Jeremi
- **Fase AI-DLC:** 02-design
- **Controles OWASP afectados:** A01 (aislamiento entre entidades), A04 (biometría de terceros sin consentimiento), A08 (integridad del enrolamiento), A09 (auditoría/retención)
- **Relacionado:** RF-21 ([notificaciones-matching.md](../../01-requirements/notificaciones-matching.md)), [ADR-0016](0016-enrolamiento-biometrico-desambiguacion.md) (enrolamiento/desambiguación — **este ADR lo enmienda**), [ADR-0020](0020-notificaciones-enrolamiento-reportante.md) (notificaciones), [ADR-0007](0007-esquema-reporte-retencion-auditoria.md) (esquema/retención), [ADR-0008](0008-boveda-llaves-identidad.md) (cifrado/bóveda), [ADR-0011](0011-contrato-eventos.md) (eventos), [ADR-0015](0015-memoria-conversacion-pgvector.md) (sesión del chatbot)

## Contexto

[ADR-0016](0016-enrolamiento-biometrico-desambiguacion.md) resolvió la desambiguación multi-rostro: si
una foto trae ≥2 rostros, se le pregunta al reportante **cuál** es el desaparecido, se enrola ese y se
**purgan incondicionalmente** los recortes/embeddings de los demás (minimización GDPR, A04). Esa purga
es correcta como **default seguro**, pero deja una oportunidad real desatendida: en una catástrofe,
una sola foto de familia o de grupo puede contener a **varias personas desaparecidas**. Hoy el sistema
descarta esa señal y obliga a reabrir cada caso desde cero.

El requerimiento (RF-21) pide que, **tras** identificar al sujeto, el sistema **pregunte si las otras
personas detectadas también se van a reportar**. Esto introduce una tensión directa con ADR-0016: ya
no se puede purgar siempre y de inmediato; hay un caso en el que el reportante quiere reportar a otro
de los rostros.

La fuerza dominante sigue siendo la **privacidad opt-in**: los rostros no seleccionados son **terceros
que no consintieron** (transeúntes, posibles menores). No podemos retener su biometría "por si acaso".
La pregunta no autoriza por sí sola la retención: solo un **reporte formal y consentido** de esa
persona justifica enrolarla. Necesitamos un mecanismo que aproveche la señal **sin** debilitar la
minimización.

## Decisión

**1. La purga de ADR-0016 deja de ser incondicional: se vuelve el default tras una ventana de
consulta.** Al resolverse la desambiguación (`face.disambiguation.resolved` con `selected_index`), el
`EnrollmentService` enrola al sujeto elegido (ADR-0016) y, **antes de purgar el resto**, conserva los
recortes restantes en la **bóveda efímera** (cifrados, TTL corto — ADR-0008) y publica un evento de
consulta hacia el chatbot. **La purga se ejecuta igualmente** al expirar la ventana o ante una
respuesta negativa. Esto **enmienda** el punto 3 de ADR-0016 (que purgaba de inmediato).

**2. El chatbot pregunta por las otras personas y recoge la decisión.** El `chatbot-gateway` (ADR-0015)
presenta al reportante las miniaturas de los rostros restantes y pregunta, por cada uno, si **también
lo va a reportar**. La respuesta vuelve como evento con, por cada rostro, `report_it: true|false`.

**3. Cada "sí" inicia un reporte derivado con su propio consentimiento y captura.** Un `report_it=true`
**no** enrola directamente el recorte. Dispara un **flujo de reporte nuevo** (intake), vinculado por
procedencia al reporte origen, que **recaptura los datos mínimos** de esa persona (nombre, tipo, nº de
documento — obligatorios de ADR-0007) y registra el **consentimiento** del reportante para procesar esa
biometría. Solo entonces el recorte conservado se promueve a foto de referencia de la **nueva entidad**
y entra al pipeline normal de enrolamiento (ADR-0016) → su propio acuse y cierre (ADR-0020).

**4. Todo rostro sin "sí" se purga inmediatamente.** `report_it=false`, sin respuesta al expirar la
ventana, o `none_of_these`: se borran recortes y cualquier embedding transitorio y se cierra el
`PendingEnrollment` (minimización A04, igual que ADR-0016). **Nunca** se persiste al índice de largo
plazo el embedding de un rostro no promovido a reporte propio.

**5. Salvaguardas reforzadas para terceros.** La biometría de un tercero solo persiste si existe (a)
una **decisión explícita** del reportante de reportarlo y (b) un **reporte derivado con datos +
consentimiento**. Ausente cualquiera de las dos, se purga. Atención especial a **menores** entre los
no-sujetos: el flujo no debe facilitar retención de biometría de menores sin la vía de consentimiento/
verificación correspondiente; ante duda, se purga y se deriva a coordinador.

**6. Idempotencia y procedencia.** El `disambiguation_id` sigue siendo la clave de idempotencia
(ADR-0016). Cada reporte derivado lleva `origin_report_id`/`origin_entity_id` para trazar la
procedencia y para `merge` reversible si luego colisiona con otro reporte (RF-11, ADR-0007).

## Alternativas consideradas

| Opción | Pros | Contras | Riesgo de seguridad |
|---|---|---|---|
| A. Mantener ADR-0016: purgar siempre, no preguntar | Máxima minimización; simple | Pierde personas desaparecidas presentes en la misma foto; obliga a reabrir cada caso | Bajo (pero pierde señal de vida) |
| B. Al confirmar, **enrolar el recorte directo** como nueva entidad | Pocos pasos | Enrola biometría de tercero **sin datos ni consentimiento formal**; entidad sin nombre/documento | Alto: retención de PII de terceros (A04) |
| C. Preguntar pero **solo registrar la intención** (sin retener recorte) | Conserva minimización estricta | El reportante tiene que volver a subir la foto de esa persona; fricción y pérdida de la foto original | Bajo |
| **D. Conservar recorte efímero, preguntar, y promover a reporte derivado con datos+consentimiento; purgar el resto (elegida)** | Aprovecha la señal sin saltarse el consentimiento; reusa intake y enrolamiento; procedencia trazable | Más estados (ventana de consulta, recortes con TTL); enmienda ADR-0016; depende de respuesta del usuario | Acotado: retención solo tras consentimiento + datos; purga por default |

## Consecuencias

- **Positivas:** una foto de grupo puede originar **varios reportes legítimos** sin perder la señal;
  la biometría de terceros solo persiste **con consentimiento y datos** (no por inercia); reusa el
  intake (ADR-0007), el chatbot con estado (ADR-0015) y el enrolamiento (ADR-0016); procedencia
  trazable habilita `merge` reversible (RF-11).
- **Negativas / deuda asumida:** la purga de ADR-0016 deja de ser inmediata y se vuelve "default tras
  ventana", lo que **alarga la vida de recortes efímeros de terceros** (mitigado con TTL corto y purga
  garantizada); más eventos y estados; el enrolamiento de los derivados queda bloqueado hasta que el
  reportante aporte datos. Falta definir el TTL exacto de la ventana de consulta.
- **Impacto en threat model:** **amplía la ventana de retención de biometría de terceros** respecto a
  ADR-0016. Mitigaciones: recortes cifrados con TTL corto (ADR-0008), purga garantizada por expiración/
  negativa, persistencia al índice **solo** tras consentimiento + datos (A04/A08), tratamiento especial
  de menores, y auditoría encadenada de cada consulta, promoción y purga (A08/A09). Aislamiento por
  `entity_id`/`disambiguation_id`/`origin_report_id` (A01).

## Pendiente

- TTL exacto de la ventana de consulta y política de recordatorio/expiración (alinear con ADR-0015 y
  la retención de ADR-0007).
- Mecanismo de **consentimiento** del reportante para procesar biometría de un tercero (texto, registro,
  base legal LGPD) y su tratamiento reforzado para **menores**.
- Esquema de los eventos nuevos (consulta de otros rostros + respuesta con `report_it` por índice) y su
  propagación a `asyncapi.yaml`.
- Definir el vínculo de procedencia (`origin_report_id`) en el modelo de datos (ADR-0007) y su uso en
  `merge` reversible (RF-11).
