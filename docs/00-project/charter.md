# Charter — Respuesta

> Proyecto: **Respuesta** · Fase AI-DLC: `00-project` · Estado: borrador vivo
> Última actualización: 2026-06-25

## Visión en una frase

Una plataforma que reconcilia información dispersa sobre personas desaparecidas y
encontradas tras el terremoto de Venezuela de 2026, agrupando los reportes en una sola
entidad por persona para que quienes la buscan tomen conciencia mutua, contribuyan a un
perfil compartido y reciban —con la confianza adecuada— el estado más cercano al tiempo
real posible.

## Contexto

El 24 de junio de 2026, un doblete sísmico superficial (Mw mayor, intensidad IX Mercalli)
en Yaracuy y Carabobo causó colapsos estructurales en la Gran Caracas y la franja costera,
con un saldo oficial de 100 fallecidos y 370 heridos, apagones masivos y caída casi total
de telefonía e internet en la capital y el occidente. En ese escenario, la información sobre
quién está desaparecido y quién ha sido encontrado queda fragmentada entre familias,
rescatistas, hospitales y refugios que no se comunican entre sí. **Respuesta** ataca esa
fragmentación: no busca reemplazar a los actores de rescate, sino ser la capa que cruza sus
datos.

## Problema y usuarios

El cuello de botella que el proyecto resuelve es el **cruce de datos dispersos**: hoy varias
personas buscan a la misma persona sin saberlo, los rescatistas registran hallazgos que no
llegan a las familias, y nadie tiene una vista única del estado de un individuo.

Usuarios y actores:

- **Buscador** (familiar/allegado): reporta a un desaparecido. Frecuentemente está fuera de
  la zona de apagón (otras ciudades o diáspora en Colombia/Brasil), por lo que suele tener
  mejor conectividad que el terreno.
- **Rescatado / persona localizada**: puede autorreportarse ("estoy a salvo") y, si está
  consciente y consiente, grabar un video de ~30 s para sus familiares.
- **Rescatista**: personal en terreno que registra hallazgos y captura el video de proof-of-life
  cuando es factible y consentido.
- **Coordinador verificado**: modera, confirma matches de alta confianza antes de notificar,
  e identifica/conecta buscadores en casos sensibles.
- **Autoridad civil/médica**: única fuente autorizada para confirmar estados de gravedad
  extrema o fallecimiento.
- **Sistemas externos**: estándar PFIF e iniciativas como ICRC (Trace the Face / Missing
  Persons Digital Matching) para federar registros en vez de crear un silo.

## Alcance (in-scope)

1. **Motor de resolución de entidades**: agrupa reportes en entidades-persona mediante un
   único motor con tres tipos de emparejamiento — DESAPARECIDO↔DESAPARECIDO (colisión),
   DESAPARECIDO↔ENCONTRADO (resolución), ENCONTRADO↔ENCONTRADO (deduplicación).
2. **Conciencia de red de búsqueda**: cuando varios buscadores convergen en la misma entidad,
   el sistema lo señala y combina sus aportes (fotos, descripciones) para enriquecer el perfil
   y mejorar la precisión del match.
3. **Generación automática de candidatos** en near-real-time, con **confirmación humana**
   (coordinador) antes de cualquier notificación de match.
4. **Taxonomía de estados** de persona y matriz de transiciones con autoridad por mecanismo
   (ver más abajo).
5. **Proof-of-life en video** (~30 s), opcional, consentido, como señal de identidad de máxima
   confianza y entrega emocional a la red opt-in.
6. **Modelo de privacidad opt-in** para la conexión entre buscadores, con mediación verificada
   para casos graves o de fallecimiento.
7. **Interoperabilidad PFIF** para intercambiar registros con sistemas existentes.
8. **Captura offline-first** con sincronización diferida (store-and-forward) y ruta SMS de
   respaldo.

## Fuera de alcance (no-scope)

- **Declaración automática de match o de fallecimiento.** El sistema nunca afirma por sí solo
  que dos registros son la misma persona ni que alguien ha muerto.
- **Reconocer/competir con los registros globales existentes.** Se interopera vía PFIF; no se
  reconstruye un ICRC.
- **Garantizar conectividad universal.** El acuerdo con telecoms (conectividad express para
  terreno) es un acelerador, no un requisito; el diseño no depende de que se concrete.
- **Exposición por defecto de identidades de buscadores.** Toda conexión es opt-in o mediada.
- **Diagnóstico médico o triage clínico.** El estado clínico lo fija la autoridad médica.

## Taxonomía de estados de persona

| Estado | Significado |
| :---- | :---- |
| `desaparecido` | Estado inicial. Alguien reporta que no encuentra a la persona. |
| `a_salvo` | La propia persona se autorreporta como segura. |
| `localizado_estable` | Encontrada con vida y en condición estable. |
| `localizado_critico` | Encontrada con vida en condición grave. |
| `fallecido` | Confirmado **solo** por autoridad civil/médica. |
| `no_identificado` | Persona encontrada cuya identidad aún se desconoce. |

`desaparecido` y `no_identificado` se mantienen separados a propósito: el primero es una
persona buscada sin localizar; el segundo es un cuerpo/persona localizada sin nombre. El
match entre ambos es justamente una de las resoluciones de mayor valor.

## Matriz de transiciones (quién puede mover el estado)

| Mecanismo | Autoridad | Cuándo aplica | Estados que puede fijar |
| :---- | :---- | :---- | :---- |
| 1. Autorreporte (video) | La propia persona | Consciente y con acceso | `a_salvo` |
| 2. Rescatista | Personal de terreno, con **consentimiento** del rescatado | Rescatado consciente que consiente | `localizado_estable` (+ video) |
| 3. Coordinador | Coordinador verificado | Rescatado **inconsciente pero identificado** | `localizado_estable` / `localizado_critico` (sin video) |
| 4. Autoridad civil/médica | Autoridad verificada | Rescatado **grave o fallecido** | `localizado_critico`, `fallecido` |

Reglas asociadas:

- El estado `fallecido` y la gravedad extrema solo entran por el mecanismo 4; el sistema
  únicamente **transmite** el estado confirmado, nunca lo deduce.
- El video de proof-of-life solo se captura con persona consciente y consentimiento explícito;
  para inconscientes, menores sin adulto o personas en shock, se usa la vía del coordinador
  (mecanismo 3), sin video.
- La notificación de fallecimiento la realiza un **mediador verificado** que identifica a los
  familiares y notifica siguiendo una jerarquía de parentesco verificado (próximo en la línea),
  no "el mejor perfil en la app". Se recomienda adoptar protocolos de notificación existentes
  (p. ej. Cruz Roja) en vez de improvisar.

## Modelo de privacidad (conciencia de red)

- **Base anónima agregada**: el sistema muestra que existe una red ("N personas buscan a esta
  entidad") y comparte el perfil combinado, **sin** revelar identidades ni contactos.
- **Conexión opt-in**: cada buscador decide si revela su contacto al resto del clúster.
  Granular, revocable incluso después de haberlo compartido. Nunca por defecto.
- **Mediación verificada** para casos de gravedad extrema o fallecimiento: un mediador
  identifica a los familiares y gestiona la conexión/notificación.

Motivación de seguridad: en el contexto venezolano, exponer quién busca a quién puede
habilitar vigilancia, acoso o persecución. Por eso la exposición directa entre familias nunca
es automática.

## Restricciones

- **Offline-first innegociable.** La carga más pesada (video de 30 s) ocurre en zona de
  apagón; obliga a grabar-offline / subir-cuando-haya-señal y compresión agresiva.
- **Seguridad de los activos sensibles.** Videos y fotos revelan rostro, ubicación y estado de
  personas vulnerables: acceso restringido al clúster verificado, control de reenvío, sin
  difusión pública.
- **Datos biométricos y de menores.** El reconocimiento facial rinde peor en pieles oscuras y
  en niños; nunca debe ser la única base para una decisión de alto costo.
- **Reversibilidad.** El merge de entidades debe poder deshacerse de forma trivial ante un
  agrupamiento erróneo.
- **Documentación en español, markdown versionable, concisa.**

## Métricas de éxito

- **Tiempo de resolución**: mediana entre el primer reporte `desaparecido` y la transición a un
  estado localizado/`a_salvo`.
- **Reducción de duplicidad**: proporción de buscadores que descubren que otros buscan a la
  misma persona (colisiones detectadas / reportes).
- **Precisión de match confirmado**: tasa de falsos positivos en matches que pasaron la
  confirmación humana (objetivo: tendiente a cero en notificaciones a familias).
- **Cobertura de proof-of-life**: porcentaje de localizaciones con vida que logran video o
  estado verificado entregado a la red.
- **Interoperabilidad**: volumen de registros intercambiados vía PFIF con sistemas externos.

## Riesgos de alto nivel

- **Falso positivo de match** notificado a una familia → daño emocional grave y desvío de la
  búsqueda real. Mitigación: confirmación humana + proof-of-life autoidentificado.
- **Filtración de identidades/ubicaciones** → vigilancia/persecución. Mitigación: opt-in,
  agregación anónima, control de acceso a activos.
- **Dependencia de conectividad** que no llega al terreno. Mitigación: offline-first + SMS,
  telecom como acelerador.
- **Reportes falsos/maliciosos o duplicados** en intake abierto. Mitigación: capa de
  coordinadores verificados, deduplicación temprana, señal de confianza por reporte.
- **Declarar una muerte por error.** Mitigación: estado `fallecido` exclusivo de autoridad;
  el sistema solo transmite.

## Acreditación y verificación de actores

**Rescatistas y coordinadores** se acreditan **en coordinación con las autoridades**: el
rescatista debe estar verificado y con su estado activo como rescatista comprobado contra el
registro de la autoridad correspondiente. Solo actores acreditados pueden mover estados por los
mecanismos 2, 3 y 4.

**Verificación de parentesco** (para conectar buscadores y para el orden de notificación de
fallecimiento), por fases:

- **Fase 1 — honor-based.** La integración con Facebook queda **descartada** por la restricción de
  la Graph API (no se puede acceder al grafo de parentescos de terceros). En su lugar, la filiación
  se confirma por **declaración de honor** del buscador hasta que exista la integración con SAIME.
  Es la verificación más débil del sistema: aumenta el peso de los guardarraíles de privacidad
  (agregado anónimo, opt-in) y del juicio humano del mediador, sobre todo en notificaciones de
  fallecimiento.
- **Fase 2 — SAIME.** El SAIME dispone de biometría de los venezolanos con cédula (~10 años en
  adelante), lo que permite verificación personal directa y exacta de datos filiatorios. Aporta la
  verificación más fuerte, pero introduce un **riesgo de privacidad muy alto**: vincula el grafo de
  búsqueda/hallazgo al sistema de identidad del Estado — el mismo riesgo de persecución que motivó
  el Modelo A. Por eso se difiere a Fase 2 y deberá diseñarse como **verificación de mínima
  divulgación** (consulta puntual, sin que el Estado registre quién pregunta por quién).

## Umbral de confianza del matching (parametrizable)

- **< 65 %** de confianza de identificación → descarte automático.
- **65 %–85 %** → enrutado a **coordinador** para revisión humana.
- **> 85 %** → enlazar/fusionar **solo con confirmación del coordinador** (no es automático por
  sí solo; el face-match nunca fusiona sin un humano).
- **100 % = autoreporte** (proof-of-life autoidentificado) → **única vía de verificación
  automática** sin coordinador.

Los umbrales son parametrizables. El umbral gobierna el **enlace de identidad** entre registros, no
la declaración de `fallecido` (exclusiva de la autoridad, mecanismo 4). Regla clave: ninguna fusión
basada en face-match ocurre sin confirmación humana; lo único que el sistema resuelve solo es el
autoreporte, porque la propia persona se identifica.

## Retención de datos

La plataforma se apega a la norma más rigurosa: **GDPR**. Implicaciones clave para datos
biométricos (categoría especial): base legal explícita (interés vital / consentimiento),
minimización de datos, **limitación de almacenamiento** (borrado al cerrar la emergencia),
derecho al borrado y cifrado. Venezuela no está bajo GDPR, pero se adopta como el listón.

**Cierre de la emergencia** (evento que gatilla el borrado de biométricos, ubicaciones y registro
de fallecimiento): *cuando todos los esfuerzos de búsqueda se dan por cerrados y se inicia la fase
de reconstrucción, **+ 12 meses***. Se gestiona en la plataforma con fecha y evidencias auditables.

**Responsable del tratamiento y jurisdicción** (Modelo A, decidido): operador humanitario
internacional como responsable —entidad domiciliada en jurisdicción con protección fuerte— con
hosting en **São Paulo (`sa-east-1`)** (región enmendada respecto a la UE original por menor latencia
hacia Venezuela/diáspora y costo; residencia bajo **LGPD** y **GDPR como listón interno**). El
gobierno no custodia datos sensibles; solo se le integra para acreditar rescatistas. Con la
residencia regional, el **control técnico** —cifrado por usuario con bóveda
([ADR-0008](adr/0008-boveda-llaves-identidad.md))— pasa a ser la primera línea de blindaje. ICRC
(Modelo D) queda como alianza a explorar en paralelo. Detalle, alternativas descartadas y
consecuencias en `data-classification.md`, [ADR-0003](adr/0003-hosting-modelo-a.md) y
[ADR-0006](adr/0006-residencia-sao-paulo.md).

## Arquitectura de despliegue (componentes)

El stack detallado se cierra en fase `02-design`; los componentes acordados son:

1. **Portal Web** — reporte y autoreporte; verificación de familiares/amigos desaparecidos. Auth con
   **Auth0** (OAuth 2.0, social login), rol único en MVP; stack Nginx + NestJS + Redis + Postgres
   (TypeScript). Ver [ADR-0009](adr/0009-dashboard-auth-auth0.md).
2. **Chatbot (canal principal)** — opera a través de **WhatsApp, Instagram, Messenger y Telegram**
   sobre un **LLM on-premises** (sin proveedor externo: la conversación con PII no sale de la
   frontera; serving con Ollama + worker, ver [ADR-0001](adr/0001-llm-on-premises.md)) que conversa
   y media el intercambio entre actores. Reglas: las **redes de mensajería**
   son los únicos procesadores externos del medio en tránsito (requieren DPA); la carga biométrica
   no se reenvía por el canal (se ingiere al almacén protegido) y el **proof-of-life se entrega
   como link asegurado por login**, no como video compartible en chat; el LLM **no es autoritativo**
   (no decide matches ni mueve estados) y respeta el opt-in en el relay. **Onboarding de baja
   fricción**: una vez certificado, el rescatista reporta vía WhatsApp **sin instalar app ni acceder
   a la web** — presiona enviar y la **cola nativa del dispositivo** retiene el mensaje hasta que
   haya conexión.
3. **Back office** — registro de rescatistas; los coordinadores hacen la identificación real de
   las personas; las autoridades realizan las notificaciones delicadas a familiares verificados.
   Matriz de roles, match manual con firma, certificación de rescatistas y validación jerárquica de
   autoridades en [ADR-0010](adr/0010-back-office-roles-flujos.md).
4. **Motor de matching (worker en segundo plano)** — implícito: ejecuta la resolución de entidades
   y la generación de candidatos en near-real-time que alimenta a los tres canales anteriores.

Datos y eventos transversales: esquema del reporte, retención y auditoría append-only (SHA-256) en
[ADR-0007](adr/0007-esquema-reporte-retencion-auditoria.md); contrato común de eventos en
[ADR-0011](adr/0011-contrato-eventos.md).

## Decisiones abiertas (Human-in-the-Loop)

- `<TODO>` Diseño de la integración SAIME de Fase 2 con **mínima divulgación** (que el Estado no
  registre quién consulta por quién); base legal y salvaguardas.
- `<TODO>` Mecanismo concreto de la declaración de honor en Fase 1 (texto, registro auditable,
  consecuencias de declaración falsa).
- `<TODO>` Stack técnico y modelo de despliegue de cada componente — fase `02-design`.
