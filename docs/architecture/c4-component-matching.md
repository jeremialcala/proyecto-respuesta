# C4 — Diagrama de Componentes: Motor de Matching · Respuesta

> **C4 — Component view · AI-DLC Fase 02 (Design)**
>
> Cómo se construye por dentro el motor de matching. Por cada reporte de desaparecido se mapea el
> rostro (OpenCV YuNet + SFace) y se guardan los embeddings de referencia; cuando llega una foto o
> video del rescatista se busca por similitud contra el clúster, se **ajusta por drift de edad**
> (empujando a coordinador, no auto-aceptando) y se fusiona con señales no faciales. En rojo: las
> superficies biométricas/sesgo. Decisión en [ADR-0004](../00-project/adr/0004-motor-de-matching.md).

```mermaid
C4Component
    title Diagrama de componentes — Motor de matching

    ContainerQueue(queue, "Cola offline-first", "Mensajería", "Reportes ingeridos")
    ContainerDb(media, "Almacén de medios", "Object store", "Fotos/video (Restringido)")
    ContainerDb(db, "Almacén de entidades", "BD", "Entidades, candidatos, estados")

    Container_Boundary(me, "Motor de matching") {
        Component(facemapper, "Mapeador de rostros", "OpenCV YuNet + SFace", "Detecta rostros y genera el embedding por persona; en video, tracking + Hierarchical Windowing")
        Component(quality, "Compuerta de calidad", "Heurística", "Descarta rostros de baja calidad (tamaño/blur/pose)")
        ComponentDb(estore, "Almacén de embeddings", "pgvector", "Fuente de verdad; borrado/merge (GDPR)")
        Component(vindex, "Índice ANN", "FAISS HNSWFlat (M=32)", "En memoria para match rápido; refrescado desde pgvector")
        Component(similarity, "Búsqueda de similitud", "coseno (FAISS)", "Compara el embedding de terreno contra el clúster")
        Component(drift, "Ajuste por drift de edad", "Política", "Modula tolerancia por age_gap; empuja a coordinador, no auto-acepta")
        Component(fusion, "Fusión multi-señal", "Scoring", "Combina rostro + geo + texto → confianza")
    }

    Rel(queue, facemapper, "Entrega reporte ingerido", "SQS")
    Rel(facemapper, media, "Lee foto / frames de video", "TLS")
    Rel(facemapper, quality, "Rostros + embeddings", "")
    Rel(quality, estore, "Guarda embeddings de referencia (desaparecido)", "")
    Rel(estore, vindex, "Refresca/reconstruye el índice ANN", "")
    Rel(quality, similarity, "Embedding de terreno (encontrado)", "")
    Rel(similarity, vindex, "Busca por similitud (ANN)", "")
    Rel(similarity, drift, "Similitud cruda", "")
    Rel(drift, fusion, "Similitud ajustada por drift", "")
    Rel(fusion, db, "Candidato con confianza (enruta por umbral)", "TLS")

    UpdateElementStyle(facemapper, $bgColor="#7a1f1f", $fontColor="#ffffff", $borderColor="#b30000")
    UpdateElementStyle(estore, $bgColor="#7a1f1f", $fontColor="#ffffff", $borderColor="#b30000")
    UpdateElementStyle(vindex, $bgColor="#7a1f1f", $fontColor="#ffffff", $borderColor="#b30000")
    UpdateElementStyle(drift, $borderColor="#b30000")
    UpdateElementStyle(media, $borderColor="#b30000")
    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

## Notas de seguridad

El **mapeador de rostros** (OpenCV YuNet + SFace) y el **almacén/índice de embeddings** (pgvector
como verdad + FAISS HNSW como índice) son superficies biométricas: los embeddings son datos
**Restringido** (A04) y el modelo arrastra **sesgo
demográfico** (`ai-sec`, RS-13) — peor en pieles oscuras y menores. Por eso el **ajuste por drift de
edad** está diseñado para **empujar a revisión de coordinador** (banda 65-85), nunca a
auto-aceptación: a mayor brecha de edad o menor edad del sujeto, más tolerancia pero más revisión
humana, no más confianza automática. La **fusión multi-señal** evita depender solo del rostro
(suma geo y texto), y la **compuerta de calidad** degrada con elegancia ante imágenes de desastre en
vez de generar embeddings basura. El face-match **nunca confirma solo** (RF-07); lo único automático
es el autoreporte (100 %).
