# C4 — Diagrama de Componentes: Pasarela de Chatbot · Respuesta

> **C4 — Component view · AI-DLC Fase 02 (Design)**
>
> Cómo se construye por dentro el canal principal. El chatbot opera a través de varias redes de
> mensajería y un LLM autenticado que conversa y media el intercambio entre actores. Reglas de
> diseño marcadas en rojo: el LLM **no es autoritativo** (no decide matches ni estados), los medios
> entrantes se ingieren al almacén protegido y **no se reenvían** por la red social, y el relay
> entre actores respeta el opt-in.

```mermaid
C4Component
    title Diagrama de componentes — Pasarela de Chatbot

    Person(actor, "Actor", "Buscador/rescatista/coordinador desde su app de mensajería")
    System_Ext(messaging, "Redes de mensajería", "WhatsApp, Instagram, Messenger, Telegram")
    Container(llm, "LLM on-premises", "Modelo self-hosted", "Sin proveedor externo; PII no sale de la frontera")

    Container_Boundary(cb, "Pasarela de Chatbot") {
        Component(adapters, "Adaptadores de canal", "WhatsApp/Telegram/Meta API", "Normalizan mensajes entrantes y salientes de cada red")
        Component(guardrails, "Rieles de guardarraíles", "NeMo Guardrails (Colang)", "Input/output/topical rails: anti prompt-injection y validación de salida")
        Component(orchestrator, "Orquestador LLM", "LLM autenticado", "Conversa y media; NO decide matches ni estados")
        Component(intake, "Manejador de intake", "Validación de esquema", "Convierte la conversación en reportes estructurados")
        Component(relayguard, "Guarda de opt-in / relay", "Política", "Aplica el boundary de privacidad al intercambio entre actores")
        Component(mediapuller, "Ingestor de medios", "—", "Extrae fotos/video al almacén protegido; no los reenvía por el canal")
    }

    Container(api, "API / Backend", "REST", "Reportes, estados y federación")
    ContainerDb(media, "Almacén de medios", "Object store", "Fotos/video/embeddings (Restringido)")

    Rel(actor, messaging, "Conversa, reporta, recibe notificaciones", "App")
    Rel(messaging, adapters, "Entrega mensajes (webhooks)", "HTTPS")
    Rel(adapters, guardrails, "Input rails (anti prompt-injection)", "")
    Rel(guardrails, orchestrator, "Mensaje saneado", "")
    Rel(orchestrator, guardrails, "Output rails: valida la respuesta", "")
    Rel(orchestrator, llm, "Inferencia (on-prem)", "")
    Rel(orchestrator, intake, "Extrae reporte estructurado", "")
    Rel(orchestrator, relayguard, "Solicita relay entre actores", "")
    Rel(relayguard, adapters, "Entrega solo mensajes permitidos (opt-in)", "")
    Rel(adapters, mediapuller, "Entrega adjuntos entrantes", "")
    Rel(mediapuller, media, "Guarda cifrado", "TLS")
    Rel(intake, api, "Crea reportes y notificaciones", "JSON/HTTPS")

    UpdateElementStyle(orchestrator, $bgColor="#7a1f1f", $fontColor="#ffffff", $borderColor="#b30000")
    UpdateElementStyle(mediapuller, $bgColor="#7a1f1f", $fontColor="#ffffff", $borderColor="#b30000")
    UpdateElementStyle(relayguard, $bgColor="#7a1f1f", $fontColor="#ffffff", $borderColor="#b30000")
    UpdateElementStyle(guardrails, $bgColor="#7a1f1f", $fontColor="#ffffff", $borderColor="#b30000")
    UpdateElementStyle(messaging, $borderColor="#b30000")
    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

## Notas de seguridad

Toda entrada por mensajería es **superficie no confiable**: alimenta el orquestador LLM, por lo que
el manejo de prompt injection es obligatorio (RS-13, AB-07 → OWASP A05). Los **rieles de
guardarraíles (NeMo Guardrails)** aplican input rails (anti-jailbreak), topical/dialogue rails y
output rails alrededor del LLM — ver [ADR-0002](../00-project/adr/0002-nemo-guardrails-prompt-injection.md).
Es **defensa en profundidad, no garantía**: el backstop sigue siendo que el LLM no es autoritativo y
no puede mover estados. El **ingestor de medios** materializa la regla de no
exponer biométricos: extrae los adjuntos al almacén protegido y nunca los reenvía por la red social;
el proof-of-life se reproduce en el portal mediante un **link asegurado por login**, nunca como
video compartible en el chat. La **guarda de opt-in/relay** evita que el intercambio mediado por el
LLM filtre identidades o conecte actores sin consentimiento (AB-01). El **LLM es on-premises**, así
que la conversación con PII no sale de la frontera. Las **redes de mensajería** (Meta, Telegram)
siguen siendo procesadores externos del medio en tránsito: requieren DPA y no se les reenvía la
carga biométrica. La cola **nativa del dispositivo** (p. ej. WhatsApp) sostiene el envío offline
del rescatista certificado sin necesidad de instalar una app.
