# PRD — Notificaciones del servicio de Matching al reportante

- **Fase AI-DLC:** 01-requirements
- **Estado:** draft
- **Cierra:** Gate 0 (este PRD)
- **Última actualización:** 2026-06-29
- **Origen:** requerimiento de producto "Comunicar al reportador la recepción y análisis de su fotografía"
- **Satisfecho en diseño por:** [ADR-0020](../00-project/adr/0020-notificaciones-enrolamiento-reportante.md) (notificaciones de ciclo de enrolamiento + cierre con imagen), [ADR-0021](../00-project/adr/0021-reporte-derivado-otros-rostros.md) (reporte derivado de otros rostros)
- **Relacionado:** [flujo-central.md](flujo-central.md) (RF-10 notificación, RF-14 mapeo facial), [ADR-0016](../00-project/adr/0016-enrolamiento-biometrico-desambiguacion.md) (enrolamiento/desambiguación), [ADR-0017](../00-project/adr/0017-media-delivery-gateway.md) (entrega de medios por URL firmada)

## Problema y contexto

Cuando una persona reporta a un desaparecido por el chatbot ([ADR-0001](../00-project/adr/0001-llm-on-premises.md)/[ADR-0015](../00-project/adr/0015-memoria-conversacion-pgvector.md)), sube una **foto de referencia** que viaja a la bóveda cifrada ([ADR-0005](../00-project/adr/0005-webhook-manager-vault-worker.md)/[ADR-0008](../00-project/adr/0008-boveda-llaves-identidad.md)) y dispara el pipeline de enrolamiento del `matching-worker` ([ADR-0016](../00-project/adr/0016-enrolamiento-biometrico-desambiguacion.md)). Hoy ese procesamiento es **silencioso para el reportante**: sube la foto y no recibe señal de que llegó, de que se está analizando, ni de que su reporte quedó completo. En una emergencia —réplica de terremoto, conectividad intermitente, alta ansiedad— ese silencio se interpreta como falla: el reportante reenvía la foto, abre reportes duplicados o abandona el canal.

El sistema ya **emite los eventos** del ciclo de enrolamiento (`entity.enrolled`, `enrollment.failed`, `face.disambiguation.requested`), pero **no los traduce en una conversación de vuelta clara y accionable** hacia quien reportó. Este PRD especifica las **notificaciones que cierran el lazo** con el reportante en el servicio de Matching: confirmar recepción/análisis, confirmar cierre con un resumen verificable de lo entregado (con la foto adjunta), y guiar al reportante cuando la foto no sirve o trae varias caras.

No introduce un motor nuevo; especifica **qué se comunica, cuándo y con qué contenido**, reutilizando el chatbot como canal de salida ([ADR-0015](../00-project/adr/0015-memoria-conversacion-pgvector.md)), el servicio de salida (`outbound.reply`) y el `media-gateway` para servir la foto como **mensaje de tipo imagen** ([ADR-0017](../00-project/adr/0017-media-delivery-gateway.md)). Ver `docs/00-project/charter.md`, `glossary.md`, `data-classification.md`.

## Objetivos / No-objetivos

**Objetivos**

- Confirmar al reportante, de forma inmediata, que su fotografía **se recibió y entró en análisis**.
- Al completar el enrolamiento, notificar que el **reporte está completo** con un **resumen de los datos entregados** (nombre, documento, última ubicación, información adicional) **acompañado de la foto** entregada, como mensaje de tipo imagen.
- Cuando la foto **no tiene calidad suficiente o no se detecta un rostro**, pedir explícitamente **una mejor foto**, indicando el motivo en lenguaje claro.
- Cuando la foto trae **más de un rostro**, pedir al reportante que **identifique cuál** es el desaparecido (miniaturas numeradas) y **consultar si las otras personas detectadas también se van a reportar**.
- Mantener trazabilidad: cada notificación enviada queda auditada y observable.

**No-objetivos**

- No define las notificaciones **delicadas** a familiares verificados (deceso, inconsciencia) — eso es del back office y autoridades (RF-10, [ADR-0010](../00-project/adr/0010-back-office-roles-flujos.md)).
- No notifica **resultados de matching** (candidatos/confirmaciones) en esta entrega; el cierre se dispara al **enrolar** el reporte, no al resolver un match (decisión de alcance — ver ADR-0020).
- No cambia el motor de matching, los umbrales ni el modelo de embeddings ([ADR-0004](../00-project/adr/0004-motor-de-matching.md)/[ADR-0013](../00-project/adr/0013-arcface-scoring-solo-rostro.md)).
- No habilita reenvío de biométricos por el canal ni video en chat (principio de diseño del proyecto).

## Usuarios y escenarios

**Actor principal:** el **reportante** (familiar, conocido o rescatista certificado) que envía una foto del desaparecido por el chatbot (WhatsApp principal; también Instagram/Messenger/Telegram).

### Escenarios positivos

1. **Recepción y análisis.** El reportante envía la foto. En segundos recibe un acuse: "Recibimos la foto de *{nombre}* y la estamos analizando." No tiene que reenviar nada.
2. **Cierre con resumen + imagen (un rostro).** El enrolamiento detecta un rostro claro y enrola al sujeto. El reportante recibe un mensaje de **tipo imagen** con la foto entregada y, como pie/cuerpo, el resumen:
   ```
   Reporte completo. Esto fue lo que registramos:

   Nombre: {Nombre completo del desaparecido}
   Documento de identidad: {Documento de identidad}
   Dónde fue visto por última vez: {Última ubicación}
   Información adicional: {Información adicional}
   ```
3. **Multi-rostro resuelto.** La foto trae 3 caras. El reportante recibe las miniaturas numeradas, elige la #2, y el sistema cierra el reporte de esa persona con el resumen+imagen. Acto seguido se le pregunta si las otras personas detectadas también se reportan (ver ADR-0021).

### Escenarios negativos / abuso (requerido por Gate 0)

- **AB-N1 Foto inservible repetida.** El reportante envía fotos sin rostro detectable una y otra vez. Mitigación: mensaje claro de "mejor foto" con guía (rostro de frente, buena luz) y **límite de reintentos** con derivación a coordinador, evitando bucle infinito y abuso del canal.
- **AB-N2 Inyección de PII de terceros.** Una foto de grupo trae menores y transeúntes que no consintieron. Mitigación: el cierre y el resumen se emiten **solo** del sujeto seleccionado; los demás rostros se tratan como efímeros y **no se retiene su biometría** salvo reporte derivado explícito y consentido (ADR-0021, A04).
- **AB-N3 Filtración por la notificación.** La imagen de cierre podría exponer la foto a quien no debe. Mitigación: la imagen se sirve por **URL firmada opaca, de vida corta y uso limitado** ([ADR-0017](../00-project/adr/0017-media-delivery-gateway.md)); el resumen se envía **solo al `contact_ref` del reportante** que originó el reporte, nunca difundido.
- **AB-N4 Suplantación del reportante (SIM swap).** El número es un autenticador débil. Mitigación: la notificación se dirige al `conversation_key`/`contact_ref` de la sesión que originó el reporte; los datos sensibles delicados no viajan por este flujo (quedan al back office).
- **AB-N5 Tormenta de notificaciones.** Reintentos *at-least-once* del broker ([ADR-0012](../00-project/adr/0012-broker-aws-sqs-sns.md)) podrían reenviar el cierre varias veces. Mitigación: idempotencia por `event_id`/`entity_id`; una notificación de cierre por reporte.

## Requisitos funcionales

Numeración continúa la de `flujo-central.md` (último: RF-15).

- **RF-16 Acuse de recepción y análisis.** Al recibir la foto de referencia de un reporte, el sistema envía al reportante, de forma asíncrona y pronta, un acuse de que la imagen **se recibió y entró en análisis**. Es no bloqueante y tolerante a offline (store-and-forward, RF-02).
- **RF-17 Notificación de reporte completo.** Al **enrolar** con éxito al sujeto (`entity.enrolled`), el sistema notifica al reportante que el **reporte está completo** e incluye el **resumen** con: `Nombre`, `Documento de identidad`, `Dónde fue visto por última vez` e `Información adicional`. Los campos ausentes se muestran como "no especificado".
- **RF-18 Adjuntar la foto como mensaje de tipo imagen.** La notificación de cierre se entrega como **mensaje de tipo imagen** (WhatsApp *image message*), con la foto entregada por el reportante y el resumen como cuerpo/pie. La foto se sirve por URL firmada ([ADR-0017](../00-project/adr/0017-media-delivery-gateway.md)); el binario **no** se sube a la Graph API.
- **RF-19 Solicitud de mejor foto.** Cuando no se detecta rostro o la calidad es insuficiente (`enrollment.failed` con `reason ∈ {no_face, low_quality}`), el sistema pide al reportante **otra foto** con guía breve (encuadre, luz, una sola persona si es posible) y motivo en lenguaje claro. Aplica un **límite de reintentos** antes de derivar a coordinador (AB-N1).
- **RF-20 Desambiguación multi-rostro.** Cuando hay ≥2 rostros (`face.disambiguation.requested`), el sistema presenta al reportante las **miniaturas numeradas** y le pide **elegir** cuál es el desaparecido. Reusa el flujo de [ADR-0016](../00-project/adr/0016-enrolamiento-biometrico-desambiguacion.md).
- **RF-21 Consulta por otras personas detectadas.** Tras resolver la desambiguación, el sistema **pregunta** si las **otras personas detectadas** también se van a reportar. Por cada confirmación, **inicia un reporte derivado** con su propio consentimiento y captura de datos; si no, **purga** los recortes restantes (ADR-0021, minimización A04).
- **RF-22 Auditoría de notificación.** Cada notificación enviada al reportante (acuse, cierre, mejor-foto, desambiguación, consulta) se registra como evento auditable (`notification.sent`) con `entity_id`, canal, propósito y timestamp ([ADR-0011](../00-project/adr/0011-contrato-eventos.md), RF-13).
- **RF-23 Idempotencia de cierre.** El sistema envía **una sola** notificación de cierre por reporte, aun bajo entrega *at-least-once* del broker (AB-N5).

## Requisitos de seguridad (mapeados a OWASP)

- **RS-N1 (A01) Aislamiento por sujeto.** La notificación y su resumen se dirigen exclusivamente al reportante originador (`contact_ref`/`conversation_key`); nunca a terceros.
- **RS-N2 (A02/A04) Entrega de imagen controlada.** La foto se expone solo vía token firmado, opaco, de TTL corto y uso limitado, revocable ([ADR-0017](../00-project/adr/0017-media-delivery-gateway.md)); descifrado al vuelo desde la bóveda, solo `scan=clean`.
- **RS-N3 (A04) Minimización de terceros.** No se retiene biometría de rostros no seleccionados salvo reporte derivado explícito y consentido (ADR-0021); atención especial a menores.
- **RS-N4 (A09) Trazabilidad.** Toda notificación queda en la auditoría encadenada ([ADR-0007](../00-project/adr/0007-esquema-reporte-retencion-auditoria.md)) y observable en telemetría.
- **RS-N5 (A05) Borde de salida.** El plano público de medios se sirve tras ALB+WAF con allowlist de fetchers ([ADR-0017](../00-project/adr/0017-media-delivery-gateway.md)/[ADR-0014](../00-project/adr/0014-contenedores-despliegue-eks.md)).

## Métricas de éxito

- **Tiempo a acuse** (foto recibida → acuse entregado) p95 dentro de la ventana conversacional aceptable.
- **Cobertura de cierre:** % de reportes con foto que reciben notificación de cierre con resumen+imagen.
- **Reducción de duplicados:** caída de reportes duplicados por reenvío de foto tras introducir el acuse (RF-16).
- **Tasa de recuperación de "mejor foto":** % de `enrollment.failed(no_face/low_quality)` que terminan en enrolamiento exitoso tras la solicitud.
- **Cero filtraciones:** ninguna imagen de cierre accesible fuera del token firmado / fuera de TTL.

## Dependencias y riesgos

- **Depende de** [ADR-0016](../00-project/adr/0016-enrolamiento-biometrico-desambiguacion.md) (eventos de enrolamiento), [ADR-0017](../00-project/adr/0017-media-delivery-gateway.md) (entrega de imagen), [ADR-0015](../00-project/adr/0015-memoria-conversacion-pgvector.md) (sesión del chatbot) y [ADR-0012](../00-project/adr/0012-broker-aws-sqs-sns.md) (broker).
- **Riesgo:** el `OutboundReply` actual solo modela texto/JWE; se requiere extenderlo a mensaje de tipo imagen (decisión en ADR-0020).
- **Riesgo:** la consulta por otras personas (RF-21) tensiona la purga incondicional de ADR-0016; se resuelve con ADR-0021 (consentimiento explícito antes de retener biometría de terceros).
- **Riesgo:** dependencia de respuesta del reportante (desambiguación / mejor foto) → mitigado con TTL y recordatorio alineados a la ventana de conversación (ADR-0015) y la retención (ADR-0007).

## Estado de Gate 0

| Ítem | Estado |
|---|---|
| Problema y contexto | ✅ |
| Objetivos / No-objetivos | ✅ |
| Escenarios positivos | ✅ |
| Escenarios negativos / abuso | ✅ AB-N1…AB-N5 |
| Requisitos funcionales | ✅ RF-16…RF-23 |
| Requisitos de seguridad | ✅ RS-N1…RS-N5 |
| Métricas de éxito | ✅ |
| Satisfecho en diseño por | ✅ ADR-0020, ADR-0021 |
