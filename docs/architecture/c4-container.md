# C4 — Diagrama de Contenedores · Respuesta

> **C4 — Container view · AI-DLC Fase 02 (Design)**
>
> Las unidades desplegables dentro del sistema y cómo se comunican. Todo vive bajo el hosting del
> Modelo A (UE). La zona de datos restringidos (almacén de medios, motor de matching, almacén de
> entidades) se marca como trust boundary interno. En rojo: superficies sensibles (biométricos,
> autenticación, modelo facial, SAIME).

```mermaid
C4Container
    title Diagrama de contenedores — Respuesta

    Person(buscador, "Buscador", "Reporta y verifica")
    Person(rescatista, "Rescatista", "Registra hallazgos en terreno")
    Person(coordinador, "Coordinador", "Identifica y confirma")
    Person(autoridad, "Autoridad civil/médica", "Confirma fallecimiento")

    System_Boundary(sys, "Respuesta — hosting UE (Modelo A)") {
        Container(web, "Portal Web", "SPA", "Reporte/autoreporte, verificación, opt-in, reproducción de proof-of-life")
        Container(chatbot, "Pasarela de chatbot", "Multi-red", "Canal principal vía WhatsApp/Instagram/Messenger/Telegram; intake y notificaciones con enlaces al portal (ver C4 de componentes)")
        Container(llm, "LLM on-premises", "Modelo self-hosted", "Conversa y media; sin proveedor externo; NO decide matches ni estados")
        Container(backoffice, "Back office", "Web app", "Registro de rescatistas, identificación, notificaciones delicadas")
        Container(api, "API / Backend", "REST", "Orquesta reportes, estados, auth y federación")
        ContainerQueue(queue, "Cola offline-first", "Mensajería", "Store-and-forward y sincronización diferida")

        Boundary(restringida, "Zona de datos restringidos", "trust-boundary") {
            Container(matcher, "Motor de matching", "Worker", "Resolución de entidades + candidatos near-real-time")
            ContainerDb(db, "Almacén de entidades", "BD", "Reportes, entidades, estados, parentesco (PII)")
            ContainerDb(media, "Almacén de medios", "Object store", "Fotos, video y embeddings biométricos (Restringido)")
        }
    }

    System_Ext(pfif, "Red PFIF / ICRC", "Federación de registros")
    System_Ext(saime, "SAIME — Fase 2", "Verificación biométrica nacional")
    System_Ext(messaging, "Redes de mensajería", "WhatsApp, Instagram, Messenger, Telegram")

    Rel(buscador, web, "Reporta, verifica, opt-in", "JSON/HTTPS")
    Rel(rescatista, messaging, "Registra encontrado + proof-of-life (offline)", "WhatsApp/Telegram")
    Rel(messaging, chatbot, "Entrega mensajes (webhooks)", "HTTPS")
    Rel(chatbot, llm, "Inferencia conversacional (on-prem)", "")
    Rel(coordinador, backoffice, "Identifica y confirma matches", "JSON/HTTPS")
    Rel(autoridad, backoffice, "Confirma gravedad/fallecimiento", "JSON/HTTPS")

    Rel(web, api, "Llama", "JSON/HTTPS")
    Rel(chatbot, api, "Envía reportes y notificaciones", "JSON/HTTPS")
    Rel(backoffice, api, "Gestiona casos y transiciones", "JSON/HTTPS")

    Rel(api, queue, "Encola reportes (offline-first)", "AMQP")
    Rel(queue, matcher, "Entrega reportes para resolución", "AMQP")
    Rel(api, db, "Lee/escribe reportes, estados y parentesco", "TLS")
    Rel(api, media, "Guarda fotos y video cifrados", "TLS")
    Rel(matcher, db, "Lee/escribe entidades y candidatos", "TLS")
    Rel(matcher, media, "Lee fotos y embeddings", "TLS")

    BiRel(api, pfif, "Federa registros", "PFIF/HTTPS")
    Rel(api, saime, "Verifica filiación — Fase 2, mínima divulgación", "HTTPS")

    UpdateElementStyle(media, $bgColor="#7a1f1f", $fontColor="#ffffff", $borderColor="#b30000")
    UpdateElementStyle(matcher, $bgColor="#7a1f1f", $fontColor="#ffffff", $borderColor="#b30000")
    UpdateElementStyle(saime, $bgColor="#7a1f1f", $fontColor="#ffffff", $borderColor="#b30000")
    UpdateElementStyle(messaging, $borderColor="#b30000")
    UpdateRelStyle(api, saime, $textColor="#b30000", $lineColor="#b30000")
    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

## Notas de seguridad por contenedor

La **API/Backend** concentra autenticación y autorización por rol y por clúster (RS-01, RS-02 →
OWASP A07/A01): ningún canal toca los datos directamente. La **cola offline-first** materializa el
patrón store-and-forward (RF-02) que sostiene la captura en zona de apagón. La **zona de datos
restringidos** agrupa lo que nunca debe salir sin control: el **almacén de medios** (biométricos y
video, cifrado — RS-03/RS-08 → A04) y el **motor de matching**, marcado como superficie de IA por
el riesgo de sesgo facial (RS-13 → `ai-sec`); por eso ninguna fusión por face-match se confirma sin
un humano. La verificación **SAIME** queda fuera del boundary y en rojo: es Fase 2 y se invoca con
mínima divulgación para no filtrar al Estado quién consulta por quién (AB-13).
