# Glosario y Lenguaje Ubicuo — Respuesta

> Proyecto: **Respuesta** · Fase AI-DLC: `00-project` · Estado: borrador vivo
> Última actualización: 2026-06-25

Este glosario fija el **lenguaje ubicuo** (DDD) del dominio: los términos que se usan igual en
las conversaciones, el código, la API y la documentación. Cada término se ubica en su **bounded
context** (contexto acotado). Donde un término del mundo coloquial significa algo preciso aquí,
se marca para evitar ambigüedad.

## Contextos acotados (bounded contexts)

- **Intake (Captura)** — entrada de reportes desde web, chatbot y autoreporte.
- **Identidad y Acreditación** — quién es quién y quién tiene permiso para actuar.
- **Resolución de Entidades (Matching)** — agrupar reportes en personas reales.
- **Notificación y Privacidad** — qué se comunica, a quién y bajo qué consentimiento.
- **Interoperabilidad** — intercambio con sistemas externos.

## Términos

### Intake (Captura)

| Término | Definición | Notas |
| :---- | :---- | :---- |
| **Reporte** | Una pieza de información sobre una persona, enviada por un actor. No es una persona: es una *pista* sobre una. | Tres intenciones: desaparecido, encontrado, autoreporte. |
| **Reporte de desaparecido** | Reporte cuya intención es "busco a esta persona". | Lo crea un Buscador. |
| **Reporte de encontrado** | Reporte cuya intención es "tengo información de / encontré a esta persona". | Lo crea un Rescatista (o coordinador). |
| **Autoreporte** | Reporte que hace la propia persona sobre sí misma ("estoy a salvo"). | Señal más limpia; puede incluir Proof-of-life. |
| **Canal** | Medio por el que entra un reporte: Portal Web, Chatbot (canal principal) o Back office. | |

### Identidad y Acreditación

| Término | Definición | Notas |
| :---- | :---- | :---- |
| **Persona** | El ser humano real del mundo, objetivo último de toda búsqueda. | Distinta de Reporte y de Entidad-persona. |
| **Buscador** | Familiar o allegado que reporta a un desaparecido. | Suele estar fuera de la zona de apagón (diáspora incluida). |
| **Rescatado / Persona localizada** | Persona encontrada con vida. | Puede autorreportarse o consentir un Proof-of-life. |
| **Rescatista** | Personal de terreno acreditado que registra hallazgos y captura el Proof-of-life cuando es factible y consentido. | Mueve estados por mecanismo 2. |
| **Coordinador** | Actor verificado que modera, confirma matches de confianza media e identifica personas inconscientes. | Mueve estados por mecanismo 3; revisa el rango 65–85 %. |
| **Autoridad civil/médica** | Única fuente autorizada para confirmar gravedad extrema o fallecimiento. | Mueve estados por mecanismo 4. |
| **Mediador (verificado)** | Actor que identifica a los familiares y gestiona notificaciones delicadas (fallecimiento) y conexiones sensibles. | Sigue protocolo de notificación. |
| **Acreditación** | Verificación, en coordinación con autoridades, de que un rescatista/coordinador está activo y autorizado. | Requisito para mover estados (mec. 2–4). |
| **Parentesco verificado** | Vínculo familiar comprobado. Fase 1: **declaración de honor** del buscador (integración Facebook descartada). Fase 2: **SAIME** (biometría nacional, verificación exacta). | Verificación débil en Fase 1; fuerte pero de alto riesgo de privacidad en Fase 2. |
| **Declaración de honor** | Afirmación auto-declarada de filiación, sin verificación externa, usada en Fase 1. | Registro auditable; consecuencias por declaración falsa. |

### Resolución de Entidades (Matching)

| Término | Definición | Notas |
| :---- | :---- | :---- |
| **Entidad-persona** | Agrupación de uno o más reportes que el sistema cree que se refieren a la misma Persona real. | El objeto central del matching. |
| **Motor de matching** | Componente (worker en segundo plano) que agrupa reportes en entidades-persona y genera candidatos en near-real-time. | Un solo motor, tres emparejamientos. |
| **Candidato** | Coincidencia propuesta por el motor entre dos reportes/entidades, con una puntuación de confianza. | No es un match confirmado. |
| **Match** | Candidato **confirmado**: por coordinador (≥65 %) o automáticamente solo si es un autoreporte (100 %). | Solo un match dispara acciones. |
| **Colisión** | Caso en que dos o más reportes de desaparecido apuntan a la misma entidad: varios buscadores convergen. | Habilita la Conciencia de red. |
| **Merge / Fusión** | Unir dos reportes/entidades en una sola entidad-persona. **Reversible.** | Enriquece el perfil biométrico. |
| **Umbral de confianza** | Parámetro que decide la acción: <65 % descarte; 65–85 % a coordinador; >85 % fusión **con confirmación de coordinador**; 100 % (autoreporte) automático. | Ninguna fusión por face-match sin humano; solo el autoreporte resuelve solo. |
| **Perfil combinado** | Conjunto de fotos y descripciones aportadas por todos los reportes de una entidad. | Más referencias = mejor precisión de match. |

### Notificación y Privacidad

| Término | Definición | Notas |
| :---- | :---- | :---- |
| **Estado** | Situación actual de una persona: `desaparecido`, `a_salvo`, `localizado_estable`, `localizado_critico`, `fallecido`, `no_identificado`. | Ver charter para la matriz de transiciones. |
| **Proof-of-life** | Video de ~30 s en que la persona consciente se identifica y deja un mensaje. | Señal de identidad de máxima confianza; consentido. |
| **Conciencia de red** | Que un buscador sepa que existen otros buscando a la misma entidad, sin revelar identidades por defecto. | Base anónima agregada. |
| **Opt-in** | Decisión explícita y revocable de un buscador de revelar su contacto al resto del clúster. | Nunca por defecto. |
| **Clúster (de búsqueda)** | Conjunto de buscadores asociados a una misma entidad-persona. | Producto de una colisión. |
| **Notificación delicada** | Comunicación de fallecimiento o gravedad extrema, gestionada por un Mediador. | Jerarquía de parentesco verificado. |

### Interoperabilidad

| Término | Definición | Notas |
| :---- | :---- | :---- |
| **PFIF** | *People Finder Interchange Format*: estándar abierto (registros de persona + notas) para intercambiar datos de desaparecidos entre sistemas. | Base de interoperabilidad con ICRC y otros. |
| **Federación** | Intercambio de registros con repositorios externos (ICRC Trace the Face / MPDM, etc.) sin crear un silo. | Vía PFIF. |
| **Store-and-forward** | Patrón offline-first: capturar sin conexión, encolar y sincronizar al recuperar señal. | Crítico para el video en zona de apagón. |

## Reglas de uso del lenguaje

- **Reporte ≠ Persona ≠ Entidad-persona.** Un reporte es una pista; varias pistas forman una
  entidad; la entidad representa a una persona real. No mezclar los tres en el código ni en la API.
- **Candidato ≠ Match.** Solo un match (confirmado) puede disparar notificaciones.
- **`fallecido` es especial:** lo fija únicamente la autoridad; el sistema lo transmite, no lo deduce.
