# ADR-0004: Motor de matching facial (OpenCV YuNet + SFace) con tolerancia a drift de edad

- **Estado:** accepted
- **Fecha:** 2026-06-25
- **Decisores:** Jeremi
- **Fase AI-DLC:** 02-design
- **Controles OWASP afectados:** A04 (datos biométricos), A06 (insecure design), `ai-sec` (sesgo)
- **Relacionado:** RF-04, RS-13, threat model T2/T10, [ADR-0001](0001-llm-on-premises.md), [ADR-0003](0003-hosting-modelo-a.md)

## Contexto

El motor de matching debe: (1) por cada **reporte de desaparecido**, generar un "mapa del rostro"
de cada persona en la foto; (2) cuando un rescatista envía una **foto o video**, comparar contra
esos mapas para proponer candidatos. Condiciones reales: fotos de referencia viejas, imágenes de
terreno con polvo/lesiones/mala luz, varias personas por foto, y **drift por edad** (la cara cambia
con el tiempo, sobre todo en menores). Todo on-premises (ADR-0001/0003) y para un servicio masivo
sin funding.

## Decisión

**Pipeline facial con OpenCV (DNN, OpenCV Zoo):**

- **Detección:** **YuNet** (`cv2.FaceDetectorYN`) detecta **todos** los rostros de una imagen.
- **Embedding ("mapa del rostro"):** **SFace** (`cv2.FaceRecognizerSF`) genera un embedding
  (~128-d) por rostro alineado.
- **Compuerta de calidad:** se descartan rostros de baja calidad (tamaño mínimo, blur, pose
  extrema) → degradación elegante en vez de embeddings basura.

**Flujo:**

- Al **ingerir un reporte de desaparecido**: mapear todos los rostros; el buscador **designa** cuál
  es la persona buscada; el/los embeddings de referencia se guardan en un **índice vectorial** por
  entidad, enriquecido por todo el clúster (varios buscadores → varias referencias).
- Para **foto/video del rescatista**: detectar rostros y generar embeddings (en video, **muestrear
  frames** y agregar/elegir los de mejor calidad); buscar por **similitud** (coseno/L2) contra los
  embeddings de referencia del clúster. Umbrales de SFace como punto de partida a **calibrar**
  (coseno ≈ 0.36 / L2 ≈ 1.13 de referencia).

**Tolerancia a drift de edad (principio de seguridad):** se captura la **fecha de la foto de
referencia** y la **edad estimada**; a mayor `age_gap` (y más si es menor) se **amplía la
tolerancia pero empujando el resultado a la banda de coordinador (65-85)**, nunca a auto-aceptación.
Menores o brechas grandes → siempre revisión humana y mayor peso a señales no faciales. El
face-match **nunca auto-confirma**; lo único automático es el autoreporte (100 %).

**Fusión multi-señal:** la confianza final combina (ponderado) similitud facial ajustada por drift
+ proximidad geográfica + coincidencia textual/demográfica. La cara es la señal más fuerte, no la
única. Esa confianza alimenta el enrutamiento por umbral del flujo central.

## Alternativas consideradas

| Opción | Pros | Contras | Riesgo de seguridad |
| :---- | :---- | :---- | :---- |
| **A. OpenCV YuNet + SFace (DNN)** ✅ | Cumple "usando OpenCV"; moderno; ligero (CPU/on-prem, alinea ADR-0001/0003); embeddings reutilizables en índice vectorial | Precisión por debajo de SOTA (ArcFace); requiere operar índice vectorial | Embeddings = biométrico (A04); sesgo persiste (ai-sec) |
| **B. OpenCV clásico (LBPH/Eigen/Fisher)** | Muy simple, sin DNN | **Baja robustez** en condiciones de desastre; obsoleto | Falsos positivos altos |
| **C. InsightFace / ArcFace (dlib)** | Precisión SOTA | Más pesado y más dependencias; mayor costo de operar | Igual A, más superficie |
| **D. API de reconocimiento gestionada (Rekognition, etc.)** | Cero ops, alta precisión | **Biométricos a un tercero** → contradice on-prem/Modelo A; costo por llamada | Exposición de biométricos (A04) — inaceptable |

> C queda como **ruta de evolución** si la precisión de A resulta insuficiente con datos reales.

## Consecuencias

- **Positivas:** honra el requisito OpenCV con un pipeline moderno; on-premises (alinea privacidad y
  Modelo A); ligero para un servicio sin funding; los embeddings forman un índice reutilizable que
  el clúster enriquece; la fusión multi-señal robustece frente a una sola foto mala.
- **Negativas / deuda asumida:** SFace está por debajo de ArcFace (aceptable, evolucionable a C); el
  **sesgo demográfico** (pieles oscuras, menores) persiste — mitigado porque el face-match nunca
  auto-confirma y el drift empuja a revisión humana; la imagen de desastre degrada la detección
  (compuerta de calidad + degradación); hay que **operar un índice vectorial** (pgvector/FAISS).
- **Impacto en threat model:**
  - **T2 (falso positivo):** el drift y el sesgo se contienen enrutando a coordinador, no
    auto-aceptando; refuerza RF-07/RS-09.
  - **T10 (merge erróneo):** la fusión multi-señal y el merge reversible (RF-11) lo acotan.
  - **A04 / `ai-sec`:** los embeddings son biométricos (Restringido) y el modelo arrastra sesgo →
    calibración y red-teaming en fase 04-testing.

## Parámetros y calibración

**Almacenamiento + match: pgvector (verdad) + FAISS (índice).**

- **pgvector** (extensión Postgres) es la **fuente de verdad** de los embeddings: durable,
  transaccional, con metadatos por entidad y **borrado** real (GDPR / cierre de emergencia) y
  merge/unmerge reversible.
- **FAISS** es el **índice ANN en memoria** para el match rápido (prioriza rendimiento):
  `IndexIDMap2(IndexHNSWFlat(d, M=32))`, métrica **coseno** (vectores normalizados).
  Parámetros: **M=32** (biometría — grafo denso, reduce falsos negativos), **efConstruction=128**
  (calidad del índice), **efSearch=32** (recall/latencia en runtime).
- **Sincronía:** FAISS se construye/refresca **desde pgvector**. `IndexHNSWFlat` **no soporta
  borrado in-place**, así que las bajas se aplican en pgvector y el índice FAISS se **reconstruye/
  refresca** (o se filtran IDs tombstoned en consulta). pgvector = verdad; FAISS = índice derivado.
  Trade-off asumido: dos sistemas en sincronía a cambio de durabilidad+borrado (pgvector) y
  velocidad de match (FAISS).

**Muestreo de video: Hierarchical Windowing.**
1. **Detección + tracking** de rostros entre frames → agrupar por *track* (= misma persona; un video
   puede traer varias). Sin este paso se promediarían caras de personas distintas.
2. Ventanas **jerárquicas**: segmentos temporales gruesos → refinamiento dentro de los de mayor
   calidad/actividad.
3. Por ventana, el mejor frame según la **compuerta de calidad** (tamaño/blur/pose) → embedding.
4. **Agregación** por track: media ponderada por calidad (o medoid) → conjunto de probes robusto.

**Política de tracking (video).** Las detecciones se asocian en *tracks* combinando **continuidad
espacial** (IoU/centroid del bbox entre frames adyacentes, p. ej. IoU > 0.3) y **re-identificación
por embedding** para cerrar huecos. **Umbral de agrupación más estricto que el match cruzado**: una
detección se une a un track si la distancia coseno a su representativo es **< ~0.40–0.45** (vs.
`τ0 ≈ 0.6` del match) — así no se funden dos personas distintas en un mismo track, lo que
contaminaría el probe agregado. Se exige una **longitud mínima** de track (p. ej. ≥ N frames de
calidad) antes de generar probe; los tracks cortos/de baja calidad se descartan.

**Tolerancia a drift (función).** Distancia coseno `d ∈ [0,1]` (0 = idéntico). Umbral base
`τ0 ≈ 0.6` (clase ArcFace; el equivalente para SFace se **calibra**, es específico del modelo).
Margen de drift:

```
Δ(edad, age_gap) = min( Δ_max , α · age_gap_años + β · [es_menor] )
```

con `α` ≈ 0.01–0.02/año, `β` ≈ +0.10 (bump para menores), `Δ_max` ≈ 0.15 (tope). Bandas por señal
facial:

- `d ≤ τ0` → match facial **fuerte** (entra a fusión normal).
- `τ0 < d ≤ τ0 + Δ` → match **tolerado por drift → fuerza coordinador** (nunca auto).
- `d > τ0 + Δ` → **descarte** de la señal facial.

Invariante: los menores van **siempre** a coordinador; el drift amplía el conjunto de candidatos,
no la auto-aceptación.

**Fusión multi-señal (pesos dinámicos).**

```
                W_face · S_face + W_geo · S_geo + W_text · S_text
Score_Final = ───────────────────────────────────────────────────
                       W_face + W_geo + W_text
```

con `S_face = 1 − d` (o mapeo calibrado), `S_geo`, `S_text ∈ [0,1]`. Los pesos son **dinámicos**:
cada `W` se escala por la **disponibilidad/calidad** de su señal (sin ubicación → `W_geo → 0`; baja
calidad facial → baja `W_face`), de modo que la ausencia de una señal no rompe el score.
`Score_Final` alimenta el enrutamiento por umbral del flujo central (65-85 → coordinador; 100 =
autoreporte), respetando que el face-match **nunca confirma solo**.

## Decisiones abiertas

- `<TODO>` Calibración con datos reales (fase 04-testing): `τ0` por modelo, `α/β/Δ_max`, pesos base
  de fusión, y los valores finos de tracking (IoU, umbral de re-identificación ~0.40–0.45, longitud
  mínima de track).
- `<TODO>` Cadencia de refresco/reconstrucción del índice FAISS desde pgvector (latencia de baja).

## Disparadores de revisión

- Precisión insuficiente de SFace con datos reales → migrar a InsightFace/ArcFace (Opción C).
- Volumen de embeddings supera el índice elegido → índice vectorial dedicado/escalado.
- Auditoría de sesgo revela disparidad inaceptable → recalibrar y reforzar señales no faciales.
