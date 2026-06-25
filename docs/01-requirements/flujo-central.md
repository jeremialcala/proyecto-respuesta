# PRD — Flujo central: reporte → match → confirmación → notificación

- **Fase AI-DLC:** 01-requirements
- **Estado:** draft
- **Cierra:** Gate 0
- **Última actualización:** 2026-06-25

## Problema y contexto

Tras el doblete sísmico del 24-06-2026, la información sobre desaparecidos y encontrados está
fragmentada entre familias, rescatistas, hospitales y refugios. El flujo central de **Respuesta**
debe convertir reportes dispersos en una resolución confiable y cercana al tiempo real: capturar un
reporte, agruparlo en la entidad-persona correcta, proponer y confirmar coincidencias, y notificar
con el cuidado que exige el contexto (datos biométricos, menores, riesgo de persecución). Ver
`docs/00-project/charter.md`, `glossary.md` y `data-classification.md`.

## Objetivos / No-objetivos

**Objetivos**

- Capturar reportes (desaparecido / encontrado / autoreporte) desde web, chatbot y back office,
  con foto, ubicación y descripción, funcionando **offline-first**.
- Agrupar reportes en entidades-persona y detectar colisiones entre buscadores.
- Generar candidatos de match en near-real-time con una puntuación de confianza.
- Enrutar por umbral (descarte / coordinador / automático) y producir un **match confirmado**.
- Notificar al clúster respetando opt-in, proof-of-life y la ruta de mediador para casos delicados.

**No-objetivos**

- Declarar automáticamente un fallecimiento o un match de alto costo sin la autoridad/persona que
  corresponda (ver guardarraíles).
- Diagnóstico clínico o triage médico.
- Reconstruir registros globales: se interopera vía PFIF.

## Usuarios y escenarios

Actores: Buscador, Rescatado, Rescatista, Coordinador, Autoridad civil/médica, Mediador (ver
glosario).

### Escenarios positivos

- **EP-01 Resolución por hallazgo.** Una madre reporta a su hijo como `desaparecido` con foto. Un
  rescatista acreditado registra un `encontrado` con foto en terreno. El motor genera un candidato
  con confianza > 85 %; se confirma el match (auto o por coordinador) y, si el hijo está consciente
  y consiente, graba un proof-of-life que llega al clúster opt-in.
- **EP-02 Autoreporte.** La persona se marca `a_salvo` desde el portal; resuelve su entidad sin
  necesidad de face-match y notifica a quienes la buscan.
- **EP-03 Colisión enriquecedora.** Dos familiares reportan por separado a la misma persona. El
  sistema detecta la colisión, forma un clúster, combina sus fotos/descripciones y mejora la
  precisión del match contra una foto de terreno de baja calidad.
- **EP-04 Inconsciente identificado.** Un rescatista halla a una persona inconsciente pero con
  documento; un coordinador realiza la identificación y fija `localizado_estable` sin video.

### Escenarios negativos / abuso (requerido por Gate 0)

| ID | Escenario de abuso | Mitigación | OWASP |
| :---- | :---- | :---- | :---- |
| **AB-01** | Alguien reporta a una persona como desaparecida solo para descubrir **quién más la busca** (vigilancia/acoso). | Conciencia de red anónima agregada; identidades no expuestas por defecto; conexión solo opt-in. | A01 |
| **AB-02** | Suplantación de un rescatista/coordinador/autoridad para mover estados o leer datos. Onboarding por WhatsApp ata identidad a un número, que es débil (SIM swap / robo de cuenta). | Acreditación verificada con autoridad; handshake de certificación que vincula el número, re-verificación periódica; acciones de alto costo con verificación adicional. | A07, A01 |
| **AB-03** | Inundación de reportes falsos (envenenamiento de datos / saturación de coordinadores). | Rate limiting, deduplicación temprana, señal de confianza por reporte, captcha/verificación. | A10, A06 |
| **AB-04** | Falso positivo de match notificado a una familia (hallazgo o muerte equivocada). | Confirmación humana para acciones de alto costo; proof-of-life autoidentificado; `fallecido` solo por autoridad. | A06 |
| **AB-05** | Exfiltración de biométricos/ubicaciones por acceso no autorizado o compulsión estatal. | Cifrado en reposo/tránsito; control de acceso; hosting fuera de Venezuela (Modelo A). | A04, A01 |
| **AB-06** | Reenvío o filtración del video proof-of-life. | Acceso restringido al clúster, control de reenvío, marca de agua, sin difusión pública. | A01, A04 |
| **AB-07** | Inyección en campos de texto o **prompt injection** en el chatbot. | Validación de esquema, sanitización, separación de instrucciones/datos en el chatbot. | A05 |
| **AB-08** | Manipular la **intención** del reporte (marcar un encontrado como desaparecido) para confundir. | Validación de transición, autoría firmada, auditoría. | A08, A06 |
| **AB-09** | Merge malicioso o erróneo que une a dos personas distintas. | Merge **reversible**, umbral de confianza, revisión de coordinador. | A06 |
| **AB-10** | Un actor niega haber movido un estado (repudio). | Logging de seguridad inmutable de toda transición, con actor y timestamp. | A09 |
| **AB-11** | Explotación de datos de menores. | Tratamiento Restringido, acceso mínimo, face-match nunca como única base de decisión. | A01, A04 |
| **AB-12** | Declaración de filiación falsa (honor-based, Fase 1) para acceder a un caso o conectar con un clúster. | Registro auditable de la declaración, consecuencias por falsedad, mediación humana en casos delicados, guardarraíles de privacidad reforzados. | A01, A06 |
| **AB-13** | Fuga del grafo de consultas a SAIME (Fase 2): el Estado deduce quién busca/aparece. | Verificación de mínima divulgación, sin que el Estado registre el origen de la consulta; base legal y salvaguardas antes de habilitar. | A01, A09 |
| **AB-14** | Datos sensibles (foto, ubicación, video) expuestos al transitar por redes de mensajería de terceros (Meta/Telegram). | No reenviar biométricos por el canal; ingerir adjuntos al almacén protegido; DPA y minimización; cifrado en reposo. | A04, A01 |
| **AB-15** | El LLM se trata como autoritativo (decide un match/estado), alucina, o su relay conecta actores sin opt-in. | LLM no decide matches ni estados; guarda de opt-in en el relay; validación de salidas; humano confirma acciones de alto costo. | A06, A01 |

## Requisitos funcionales

- **RF-01 Captura multicanal.** El sistema acepta reportes desde web, **chatbot** (canal principal,
  operado sobre WhatsApp/Instagram/Messenger/Telegram con un LLM autenticado) y back office, con
  tipo/intención (`desaparecido`/`encontrado`/`autoreporte`), foto, ubicación y descripción libre.
  Los adjuntos entrantes se ingieren al almacén protegido y no se reenvían por la red de mensajería.
  El LLM es **on-premises** (sin proveedor externo). **Onboarding de baja fricción**: el rescatista
  certificado reporta vía WhatsApp sin instalar app ni acceder a la web.
- **RF-02 Offline-first.** La captura funciona sin conexión (store-and-forward). En el canal
  chatbot esto se apoya en la **cola nativa del dispositivo** (p. ej. WhatsApp retiene el mensaje
  hasta que haya señal), sin requerir una app propia; en web/back office, cola local. El video se
  sube de forma diferida y comprimida.
- **RF-03 Entidad-persona.** Cada reporte se asocia (o crea) una entidad-persona; el sistema
  mantiene el perfil combinado (todas las fotos/descripciones de la entidad).
- **RF-04 Motor de matching.** Genera candidatos en near-real-time cruzando señales facial +
  geográfica + textual, con una puntuación de confianza por candidato.
- **RF-05 Detección de colisión.** Reconoce cuando varios reportes `desaparecido` apuntan a la
  misma entidad y forma un clúster de búsqueda.
- **RF-06 Enrutamiento por umbral (parametrizable).** < 65 % descarte; 65–85 % a coordinador;
  > 85 % fusión/enlace **con confirmación de coordinador**; 100 % (autoreporte) verificación
  automática. Ninguna fusión por face-match ocurre sin un humano.
- **RF-07 Confirmación.** Un candidato se convierte en **match** solo tras confirmación: por
  coordinador (≥ 65 %) o de forma automática **únicamente** cuando es un autoreporte
  autoidentificado (100 %). Las acciones de alto costo siempre llevan respaldo humano o proof-of-life.
- **RF-08 Transiciones de estado.** Mueve el estado de la persona según la matriz de autoridad
  (autorreporte/rescatista/coordinador/autoridad). `fallecido` solo por autoridad; el sistema lo
  transmite, no lo deduce.
- **RF-09 Proof-of-life.** Permite grabar y adjuntar un video de ~30 s, solo con persona consciente
  y consentimiento explícito; se entrega al clúster opt-in como **link asegurado por login** (no
  como video compartible en chat).
- **RF-10 Notificación.** Notifica al clúster respetando el opt-in; las notificaciones delicadas
  (gravedad/fallecimiento) las gestiona un mediador con jerarquía de parentesco verificado.
- **RF-11 Merge reversible.** Fusiona y **deshace** la fusión de entidades de forma trivial ante un
  agrupamiento erróneo.
- **RF-12 Interoperabilidad PFIF.** Exporta/importa registros de persona y notas en formato PFIF.
- **RF-13 Auditoría.** Registra toda transición de estado y todo match con actor, timestamp y
  evidencia.

## Requisitos de seguridad (mapeados a OWASP ASVS)

| Req | Descripción | ASVS | Nivel | OWASP Top 10:2025 |
| :---- | :---- | :---- | :---- | :---- |
| **RS-01** | Autenticación fuerte (MFA) de rescatistas, coordinadores y autoridad; acreditación verificada con la autoridad. | V2 | L2 | A07 |
| **RS-02** | Autorización por rol y **scoping por clúster**: cada actor ve solo lo que su rol y caso permiten. | V4 | L2 | A01 |
| **RS-03** | Cifrado en reposo y en tránsito de biométricos, video y ubicaciones. | V6, V9 | L2 | A04 |
| **RS-04** | Validación de esquema y sanitización de todas las entradas (web, chatbot, API). | V5 | L2 | A05 |
| **RS-05** | Rate limiting, deduplicación y anti-abuso en el intake. | V11 | L2 | A10, A06 |
| **RS-06** | Logging de seguridad **inmutable** de transiciones de estado y matches (no repudio). | V7 | L2 | A09 |
| **RS-07** | Minimización, retención y **borrado** al cierre de la emergencia; derecho al borrado. | V8 | L2 | A04 |
| **RS-08** | Control de acceso y de reenvío del proof-of-life (marca de agua, sin difusión pública). | V8, V12 | L3 | A01, A04 |
| **RS-09** | Diseño seguro: **confirmación humana obligatoria** para acciones de alto costo (insecure design guardrail). | V1 | L2 | A06 |
| **RS-10** | Integridad y firma de los intercambios (PFIF, webhooks de federación). | V10 | L2 | A08 |
| **RS-11** | Gestión segura de secretos y configuración; sin secretos en código. | V14 | L2 | A02 |
| **RS-12** | Conciencia de cadena de suministro: SCA y lockfiles para deps del motor y el chatbot. | V14 | L2 | A03 |
| **RS-13** | Controles de IA: la entrada por mensajería es no confiable → mitigar **prompt injection** (separar instrucciones de datos, limitar tool-use del LLM); LLM **no autoritativo**; **sesgo biométrico** (pieles oscuras, menores); face-match nunca única base de decisión. | V1 + `ai-security-controls` | L2 | A05, A06 |
| **RS-14** | Manejo de condiciones excepcionales (offline, señal baja, datos parciales) sin fuga de información ni estados inconsistentes. | V7 | L2 | A10 |
| **RS-15** | **LLM on-premises** (sin proveedor externo: PII no sale de la frontera). Las redes de mensajería siguen siendo procesadores del medio en tránsito: DPA, minimización, sin biométricos por el canal; proof-of-life como link por login. | V1, V8 | L2 | A04, A03 |

## Métricas de éxito

- **Latencia de candidatos**: tiempo desde que entra un reporte hasta que el motor emite candidatos
  (objetivo near-real-time).
- **Tiempo de resolución**: mediana entre el primer `desaparecido` y un estado localizado/`a_salvo`.
- **Falsos positivos en notificación**: tendiente a cero en matches notificados a familias.
- **Reducción de duplicidad**: colisiones detectadas / reportes.
- **Cobertura de proof-of-life**: % de localizaciones con vida con video o estado verificado entregado.
- **Carga de coordinador**: % de reportes que caen en el rango 65–85 % (calibración del umbral).

## Dependencias y riesgos

- **Motor de reconocimiento facial** y su **sesgo** en pieles oscuras y menores → mitigado por
  confirmación humana y proof-of-life (RS-13, RF-07).
- **Conectividad** en zona de apagón → mitigado por offline-first (RF-02); acuerdo telecom es
  acelerador, no requisito.
- **Acreditación con autoridades** (RS-01) → dependencia organizativa externa.
- **Parentesco honor-based (Fase 1)** → verificación débil; sube el peso de los guardarraíles de
  privacidad y del mediador. **SAIME (Fase 2)** → verificación exacta pero riesgo de privacidad muy
  alto (vínculo con el Estado); diseñar con mínima divulgación.
- **Falsos positivos de alto costo** → el riesgo más grave del producto; gobernado por RF-07, AB-04.

## Estado de Gate 0

| Criterio Gate 0 | Estado |
| :---- | :---- |
| Charter y glosario | ✅ `docs/00-project/` |
| Clasificación de datos | ✅ `docs/00-project/data-classification.md` |
| Requisitos funcionales | ✅ RF-01…RF-13 |
| Requisitos de seguridad → OWASP ASVS | ✅ RS-01…RS-15 |
| Escenarios negativos / abuso | ✅ AB-01…AB-15 |
| Threat assessment | ✅ Matriz de abuso AB-01…AB-15 trazada a OWASP (el threat model formal STRIDE/DREAD se hace en 02-design, Gate 1) |
