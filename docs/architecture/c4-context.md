# C4 — Diagrama de Contexto · Respuesta

> **C4 — Context view · AI-DLC Fase 02 (Design)**
>
> El sistema como una sola caja, rodeado de los actores que lo usan y los sistemas externos con
> los que interactúa. El trust boundary marca lo que vive bajo el operador humanitario internacional
> (Modelo A). SAIME aparece en rojo: es de Fase 2 y de alto riesgo de privacidad.

```mermaid
C4Context
    title Diagrama de contexto del sistema — Respuesta

    Person(buscador, "Buscador", "Familiar/allegado que reporta a un desaparecido; suele estar fuera de la zona de apagón")
    Person(rescatado, "Rescatado", "Persona localizada; puede autorreportarse y grabar proof-of-life")
    Person(rescatista, "Rescatista", "Personal de terreno acreditado")
    Person(coordinador, "Coordinador", "Verifica identidad y confirma matches")
    Person(autoridad, "Autoridad civil/médica", "Única fuente de gravedad/fallecimiento")
    Person(mediador, "Mediador", "Gestiona notificaciones delicadas")

    Enterprise_Boundary(b1, "Operador humanitario internacional — Modelo A (hosting UE)") {
        System(respuesta, "Respuesta", "Cruza reportes dispersos en entidades-persona; genera y confirma matches; notifica")
    }

    System_Ext(pfif, "Red PFIF / ICRC", "Federación de registros (Trace the Face / MPDM)")
    System_Ext(telecom, "Operadores telecom", "Conectividad express para terreno")
    System_Ext(saime, "SAIME — Fase 2", "Verificación biométrica nacional; alto riesgo de privacidad")
    System_Ext(messaging, "Redes de mensajería", "WhatsApp, Instagram, Messenger, Telegram")

    Rel(buscador, respuesta, "Reporta desaparecido, verifica, decide opt-in", "Web/HTTPS")
    Rel(rescatado, respuesta, "Autoreporte (a salvo) y proof-of-life", "Web·Chatbot/HTTPS")
    Rel(rescatista, respuesta, "Registra encontrado + video (offline-first)", "Chatbot/HTTPS·SMS")
    Rel(coordinador, respuesta, "Identifica y confirma matches", "Back office/HTTPS")
    Rel(autoridad, respuesta, "Confirma gravedad/fallecimiento", "Back office/HTTPS")
    Rel(mediador, respuesta, "Realiza notificaciones delicadas", "Back office/HTTPS")

    BiRel(respuesta, pfif, "Federa registros de persona y notas", "PFIF/HTTPS")
    Rel(respuesta, telecom, "Coordina conectividad express en terreno", "")
    Rel(respuesta, saime, "Verifica filiación con mínima divulgación — Fase 2", "HTTPS")
    Rel(respuesta, messaging, "Opera el chatbot a través de", "API de cada red")

    UpdateElementStyle(saime, $bgColor="#7a1f1f", $fontColor="#ffffff", $borderColor="#b30000")
    UpdateElementStyle(messaging, $borderColor="#b30000")
    UpdateRelStyle(respuesta, saime, $textColor="#b30000", $lineColor="#b30000", $offsetX="-40")
    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

## Relaciones clave

El buscador suele estar conectado (otra ciudad o diáspora) mientras el rescatista opera en la zona
de apagón: por eso la captura del rescatista es **offline-first** y depende de la conectividad
express de los operadores telecom como acelerador, no como requisito. La federación con la red PFIF
es **bidireccional**: Respuesta no es un silo, sino una capa que intercambia con ICRC y similares.
SAIME se relega a Fase 2 y se modela con **mínima divulgación** porque vincular el grafo de
búsqueda al Estado reintroduce el riesgo de persecución que motivó el Modelo A.

El chatbot opera a través de varias **redes de mensajería** (WhatsApp, Instagram, Messenger,
Telegram) sobre un **LLM on-premises** —parte del sistema, sin proveedor externo— que conversa y
media el intercambio entre actores. Las redes de mensajería son los únicos procesadores externos
del medio en tránsito; la regla es no exponerles la carga biométrica: el canal lleva intake y
notificaciones, el proof-of-life se entrega como **link asegurado por login** (no como video en
chat), y el LLM nunca decide matches ni estados. El detalle interno está en el
[C4 de componentes del chatbot](c4-component-chatbot.md).
