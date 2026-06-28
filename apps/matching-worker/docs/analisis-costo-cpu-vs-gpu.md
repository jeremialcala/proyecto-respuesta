# Análisis de costo: detección/embedding facial en CPU vs GPU (vast.ai)

Compara el **costo de ejecutar detección + embedding** (ArcFace/IResNet100 sobre InsightFace) en **CPU
in-region** frente a **GPU on-demand en vast.ai** (ADR-0019). Cierra con la **decisión** adoptada para el
worker local.

> El **matching** (búsqueda vectorial pgvector/FAISS + scoring) vive **siempre in-region** y es barato
> (ADR-0019 §4); lo costoso —y lo que se mide aquí— es **detección + embedding**.

Fecha: 2026-06-28. Mediciones: ver [`analisis-inference-cpu-gpu.md`](../../../deploy/poc-vastai/analisis-inference-cpu-gpu.md)
y los JSON [`results-cpu-ffhq.json`](../../../deploy/poc-vastai/results-cpu-ffhq.json) /
[`results-gpu-3090-ffhq.json`](../../../deploy/poc-vastai/results-gpu-3090-ffhq.json).

---

## 1. Productividad medida (FFHQ 256px, 1 worker, local sin túnel)

| Plataforma | throughput | img/hora |
| :-- | :-- | :-- |
| CPU (12 vCPU) | 2,19 img/s | 7.884 |
| GPU RTX 3090 | 6,23 img/s | 22.428 |

GPU ≈ **2,8×** la CPU, con idéntica precisión de detección (`detection_rate=1.0`). Se usa el RTX 3090
local como **proxy** de un 3090 en vast.ai (mismo silicio); un 4090 sería más rápido.

## 2. Costo por 1.000 imágenes

`$/1.000 = ($/hr) ÷ (img/s × 3,6)`. Precios GPU = **observados** en vast.ai (verificado, jun-2026).
Precios CPU AWS sa-east-1 son **aproximados — verificar** (prima ~1,3× sobre us-east-1).

| Opción | $/hr (sup.) | img/s | **$/1.000 img** | Nota |
| :-- | :-- | :-- | :-- | :-- |
| On-prem GPU 3090 (propio) | ~0,05 (luz) | 6,23 | **~0,002** | capex hundido, sin elasticidad |
| **vast.ai GPU 3090** | 0,13 | 6,23 | **~0,006** | precio verificado observado |
| AWS CPU spot (~16 vCPU) | ~0,30 | ~2,9 | **~0,029** | interrumpible |
| AWS CPU on-demand (~16 vCPU) | ~0,93 | ~2,9 | **~0,088** | in-region, gestionado |

**Costo de cómputo puro:** la **CPU no es más barata**. Por imagen, la GPU en vast.ai sale **~5× más
barata que CPU spot** y **~15× que CPU on-demand**: rinde 2,8× más a una fracción del precio/hora.

## 3. Costos no-monetarios que matizan a la GPU burst (observados en la PoC)

- **Cold-start / aprovisionamiento pagado:** el nodo tarda 1–10 min en bajar la imagen (~3,5 GB). Se
  amortiza en una **ola** grande; en trabajos chicos/intermitentes **se come la ventaja**.
- **Fiabilidad de hosts:** en la PoC, **5 de 6 hosts no-Brasil se atascaron en `loading`**. Poco costo en
  dinero (facturan poco), alto costo operativo.
- **Egress + latencia:** datos marginales (solo-vector, ~4,4 MB/250 img), pero la salida cruza frontera.
- **Gobernanza §6:** biometría real a un tercero → costo de **riesgo/legal**, no monetario, y es el
  factor que de verdad decide.

## 4. Cuándo conviene cada uno

| Escenario | Mejor opción | Por qué |
| :-- | :-- | :-- |
| Volumen bajo / flujo constante | **CPU in-region (siempre encendido)** | simple, cumple residencia (ADR-0006), costo absoluto trivial; sin overhead/gobernanza de burst |
| Ola post-evento (decenas de miles en minutos) | **GPU burst (vast.ai)** | drena la cola en minutos a costo marginal — caso de ADR-0019 |
| Capacidad fija ya comprada | **GPU on-prem** | costo marginal mínimo (luz), pero no absorbe picos |

## 5. Conclusión

En **costo de cómputo por imagen, la GPU es netamente superior a la CPU** — no hay caso donde la CPU sea
más barata por imagen. La CPU solo gana en dimensiones **no-costo**: residencia/compliance, cero
terceros, fiabilidad y simplicidad para volumen bajo/constante. Esto **valida** la arquitectura del
ADR-0019: **base in-region + burst GPU para las olas**, condicionado al gate legal §6.

## 6. Decisión

**Se mantiene el worker de inferencia local en configuración solo-CPU** (`ARCFACE_USE_GPU=false`, perfil
`poc` del compose) como **base in-region** del plano de inferencia. Fundamento:

- El volumen actual (pre-/MVP) es bajo y constante → la diferencia de costo absoluto es trivial y la CPU
  evita el overhead operativo (aprovisionamiento, fiabilidad de hosts), el egress de biometría y el
  **gate legal §6** de sacar datos a un tercero.
- Mantiene **residencia dura** (ADR-0006): nada de biometría sale de la frontera.
- **No cierra** la puerta al burst: la imagen es portable (CPU/GPU por configuración, ADR-0019 §2). La
  ruta GPU vast.ai queda **lista y validada** (imagen corregida `:0.1.2` GPU-real en ECR) para activarse
  cuando (a) haya olas que lo justifiquen y (b) se apruebe la validación legal §6.

> Caveats: precios AWS **estimados** (verificar sa-east-1); throughput GPU del 3090 local como proxy de
> vast.ai. Para un número empírico de GPU-en-vast.ai, relanzar con la imagen `:0.1.2` corregida.
