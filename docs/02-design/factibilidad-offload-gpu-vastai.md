# Factibilidad: offload de FaceMatch (imagen/video) a GPU on-demand (vast.ai)

**Proyecto:** Respuesta — FaceMatch desaparecidos, terremoto Venezuela 2026
**Fecha:** 2026-06-28
**Autor:** Jeremi (asistido)
**Estado:** Borrador para decisión / candidato a ADR

---

## 1. Resumen ejecutivo

El problema reportado —"el proceso de la LLM interfiere con el de facematching y se vuelve inescalable"— es, en el fondo, un problema de **contención de GPU compartida**: dos cargas con perfiles de uso opuestos (la LLM con sesiones largas y latencia conversacional; el facematch con ráfagas batch de detección + embedding) compiten por la misma GPU y se degradan mutuamente bajo carga.

La conclusión es doble:

1. **Desacoplar es obligatorio e independiente de vast.ai.** El facematch debe salir de la GPU de la LLM y convertirse en un *worker pool* propio, alimentado por tu broker de eventos (SQS/SNS, ADR de broker) y escalado por separado. Esto resuelve la contención por sí solo.
2. **Offload a vast.ai es factible** como destino de ese worker pool, **siempre que se use la capa "Secure Cloud" / hosts verificados (no el marketplace abierto)** y se apliquen los controles de privacidad descritos en §5. Dado tu postura "flexible con controles" sobre residencia, esto es viable; con la postura "restricción dura" no lo sería.

El offload **no se justifica principalmente por costo** (el volumen de cómputo es modesto y barato en cualquier proveedor), sino por **elasticidad ante picos** post-evento y por **eliminar la contención con la LLM**. La recomendación es una arquitectura **híbrida**: capacidad base en tu nube en-región (residencia dura, AWS sa-east-1) + *burst* a vast.ai Secure Cloud para absorber ráfagas.

**Veredicto de factibilidad: VIABLE, con condiciones.** Riesgo principal: residencia/privacidad de biometría en hosts de terceros. Mitigable, no eliminable.

---

## 2. Diagnóstico del cuello de botella actual

La causa raíz seleccionada es **GPU compartida**: LLM y facematch sobre la misma instancia/GPU.

Por qué se vuelve inescalable cuando conviven:

- **Perfiles de carga incompatibles.** La inferencia LLM mantiene memoria de GPU (KV-cache) ocupada durante toda la sesión y es sensible a latencia (token streaming). El facematch llega en **ráfagas** (una ola de reportes tras una réplica) y quiere saturar la GPU en batch. Cuando coinciden, o la LLM sufre jitter de latencia, o el facematch se queda sin VRAM y serializa.
- **Escalado acoplado.** Para dar más capacidad de facematch hay que escalar la instancia entera (incluida la LLM) y viceversa. No se puede dimensionar cada carga por su propia métrica.
- **Cold path vs. hot path mezclados.** El matching tolera segundos/minutos de cola (es batch). La LLM no. Mezclarlos obliga a dimensionar todo al SLA más estricto.

Implicación de diseño: **estas dos cargas deben vivir en planos de cómputo distintos**, conectadas solo por el bus de eventos. El facematch es el candidato natural a externalizarse porque es batch, tolerante a latencia y "embarrassingly parallel".

---

## 3. Qué es vast.ai y en qué modo es utilizable

vast.ai es un **marketplace** de GPU: hosts independientes publican capacidad y fijan precio por oferta/demanda en 40+ datacenters. Esto crea dos mundos muy distintos que hay que separar tajantemente para este proyecto:

| Característica | Marketplace abierto (hosts no verificados) | Secure Cloud (datacenters verificados) |
|---|---|---|
| Quién aloja | Mineros, rigs gaming, terceros sin auditar | DC con **ISO 27001** mínimo; muchos HIPAA/SOC/PCI/GDPR |
| Cumplimiento | Ninguno garantizado | DPA firmado, GDPR, vast.ai con **SOC 2 Type 2** |
| Fiabilidad | Variable (filtrar reliability > 0.95) | Uptime consistente, hardware enterprise |
| Precio H100 ref. | ~$0.90/hr | ~$1.50–1.87/hr |
| Apto para biometría PII | **No** | Sí, con controles |

Para Respuesta, **solo la capa Secure Cloud / hosts verificados es admisible**, e idealmente filtrando por **región Brasil** (vast.ai tiene presencia allí) para acercarse a tu frontera de residencia de São Paulo.

Modelo de aislamiento relevante: cada carga corre en un **contenedor Docker no privilegiado**, aislado de otros tenants, sin filesystem compartido, y **los datos se destruyen al eliminar la instancia**. Esto habilita un patrón de procesamiento **efímero** (ver §5).

### Tipos de instancia

- **On-Demand** (~$0.3/GPU/hr promedio; H100 más): uptime garantizado, apto para el pool caliente de inferencia.
- **Interruptible** (~$0.1/GPU/hr): el host puede **reclamar la GPU con pocos minutos de aviso**. Solo para batch tolerante a fallos con re-encolado idempotente. Útil para vaciar colas de baja prioridad a bajo costo.
- **Reserved** (~$0.2/GPU/hr): compromiso con descuento, para capacidad base predecible.
- Facturación **por segundo**, mínimo $5.

---

## 4. Modelo de impacto en performance

### 4.1 Costo de cómputo del pipeline FaceMatch

El pipeline ArcFace tiene tres etapas con perfiles muy distintos:

| Etapa | Dónde corre | Costo aprox. (GPU moderna, TensorRT + batch) |
|---|---|---|
| Detección + alineación (SCRFD/RetinaFace) | GPU | la etapa más cara; ~la mayor parte del tiempo |
| Extracción de embedding (ArcFace 512-d) | GPU | muy barato: ~17 ms en GPU vieja (Tesla M40); hasta ~820 fps en RTX 4090 con TensorRT |
| Matching (búsqueda vectorial ANN) | CPU/índice | <10 ms sobre ~1M caras con FAISS/HNSW — **no es cuello de GPU** |

Estimación conservadora del **pipeline completo** (detección + alineación + embedding) por GPU clase L4/A10/4090 con TensorRT y batching: **~50–150 imágenes/seg**. Para foto individual: **~20–50 ms** de GPU end-to-end.

Video (proof-of-life): no se procesan todos los frames. Muestreando a ~2 fps, un clip de 30 s ≈ 60 frames → **~1–2 s de GPU + decodificación** por clip.

### 4.2 Escenario de ola post-evento (ejemplo dimensional)

Supuesto: una ráfaga de **50.000 fotos** + **5.000 clips de video** entrando en una ventana corta.

| Carga | Cómputo | GPU-tiempo (1 GPU) |
|---|---|---|
| 50.000 fotos @ 100 img/s | 500 s | ~8 min |
| 5.000 clips @ 2 s/clip | 10.000 s | ~167 min |
| **Total** | | **~3 GPU-hora** |

Paralelizando en **10 GPUs**: ~**18 min de wall-clock** para drenar toda la ola.

### 4.3 Costo monetario

3 GPU-hora en vast.ai Secure Cloud (clase L4/A10, ~$0.5–1/hr) ≈ **$1.5–3 por ola completa**. En AWS sa-east-1 (g5.xlarge, on-demand) el mismo trabajo es del orden de **2–4× ese costo**. En ambos casos, **el costo de cómputo es marginal**: la decisión no es de costo, es de elasticidad y aislamiento.

### 4.4 Penalizaciones a contabilizar (lo que empeora el número ideal)

El impacto en performance **neto positivo** depende de gestionar estas fricciones:

- **Cold-start / aprovisionamiento.** Levantar una instancia vast.ai + *pull* de la imagen Docker (con motor TensorRT compilado) puede tomar **minutos**. Mitigación: imagen pre-horneada con engine ya compilado + **pool caliente mínimo** (1–2 GPUs reserved siempre activas) para latencia baja, y escalar el resto bajo demanda.
- **Transferencia de datos (egress/ingress).** Enviar imágenes/video fuera de tu nube añade latencia de red y, potencialmente, costo de egress en tu lado. Mitigación: enviar **cara ya recortada/redimensionada** (no la foto original completa), o incluso solo el frame relevante del video tras un pre-filtro barato en-región.
- **Interrupciones (instancias interruptible).** Pérdida de trabajo en vuelo. Mitigación: **idempotencia + re-encolado** desde SQS con visibility timeout; usar interruptible solo para prioridad baja.
- **Variabilidad de host.** Aun en Secure Cloud, filtrar por reliability > 0.95 (on-demand) y > 0.90 (interruptible).

**Resultado esperado:** con desacople + pool caliente + imagen pre-horneada, el facematch deja de competir con la LLM (la latencia conversacional se estabiliza) y la cola de matching se drena en minutos en vez de degradarse, escalando horizontalmente con la ola.

---

## 5. Privacidad y residencia (el riesgo central)

Postura declarada: **flexible con controles**. La biometría puede procesarse fuera de la frontera de residencia *si* hay mitigaciones. Esto hace el offload viable, pero exige diseño explícito porque **el facematch necesita la imagen real** para detectar y extraer el embedding —no se puede ofuscar el contenido sin perder la función—. Controles propuestos:

1. **Solo Secure Cloud, región Brasil.** Nada de marketplace abierto. Acerca el procesamiento a la residencia de São Paulo y mantiene la cadena de DPAs/ISO 27001/GDPR.
2. **Procesamiento efímero, sin persistencia.** El worker recibe la imagen, extrae embedding, **devuelve solo el vector 512-d** y se descarta la imagen; al destruir la instancia, vast.ai destruye los datos. Ninguna imagen se escribe a disco persistente del host.
3. **Minimización de datos enviados.** Pre-recortar la cara y/o pre-filtrar frames de video **en-región** antes de enviar; enviar el mínimo necesario para detección/embedding.
4. **Cifrado en tránsito** (TLS) y, si el flujo lo permite, el **matching y el almacenamiento de embeddings/galería se mantienen siempre en-región** (la Vault y el índice ANN no salen). vast.ai solo hace la transformación imagen→vector.
5. **Sin secretos en el host.** El worker no lleva credenciales a la Vault; recibe trabajo y devuelve resultado vía el broker con tokens de corta vida.
6. **Registro y consentimiento.** Documentar la sub-procesadora (vast.ai + DC) en tu DPA y base legal; alinear con tu ADR de residencia y retención GDPR.

Decisión de gobernanza pendiente: confirmar con tu marco legal si "procesamiento efímero de imagen + retorno de solo-vector en DC verificado GDPR fuera de São Paulo" cae dentro de "flexible con controles" o requiere consentimiento adicional. **Recomendado: validar con un piloto usando datos sintéticos/consentidos antes de tráfico real.**

---

## 6. Opciones comparadas

| Opción | Residencia | Elasticidad | Costo | Complejidad | Veredicto |
|---|---|---|---|---|---|
| **A. Status quo** (GPU compartida LLM+FM) | Dura ✅ | Mala ❌ | — | Baja | Insostenible (el problema actual) |
| **B. Desacople en-región** (worker GPU propio en AWS sa-east-1, autoscaling / SageMaker async) | Dura ✅ | Buena | Medio-alto | Media | **Base recomendada** |
| **C. Offload total a vast.ai** Secure Cloud | Flexible ⚠️ | Excelente | Bajo | Media-alta | Viable pero concentra riesgo de residencia |
| **D. Híbrido** (B como base + burst a C en picos) | Flexible ⚠️ | Excelente | Bajo-medio | Alta | **Recomendado objetivo** |

---

## 7. Recomendación

1. **Primero, desacoplar (no negociable).** Saca el facematch de la GPU de la LLM y conviértelo en un servicio worker independiente, consumiendo del broker SQS/SNS, escalado por profundidad de cola. Esto solo ya resuelve la contención reportada. Es la Opción B y es prerrequisito de todo lo demás.

2. **Diseñar el worker como portable (cloud-agnóstico).** Empaquetar el pipeline ArcFace en una **imagen Docker con TensorRT pre-compilado**, sin estado, que reciba trabajo y devuelva embeddings vía el broker. Si corre en AWS sa-east-1 o en vast.ai Secure Cloud debe ser solo configuración, no reescritura.

3. **Adoptar híbrido (Opción D) para picos.** Capacidad base en-región para cumplimiento y carga estable; *burst* a vast.ai Secure Cloud (región Brasil, hosts verificados) cuando la cola supere un umbral, con los controles de §5.

4. **Pilotar antes de producción.** Medir en vast.ai con **datos sintéticos**: cold-start real, throughput real del pipeline, latencia de transferencia y tasa de interrupción. Validar la postura legal de residencia con datos no reales.

5. **Formalizar como ADR.** Esta decisión (introducir un sub-procesador GPU de terceros para biometría) merece un ADR nuevo en tu serie, enlazado al ADR de residencia (São Paulo), al de broker y al de ArcFace.

---

## 8. Próximos pasos sugeridos

- [ ] Separar facematch en worker independiente alimentado por el broker (Opción B).
- [ ] Empaquetar pipeline ArcFace en imagen Docker portable con TensorRT.
- [ ] PoC en vast.ai Secure Cloud (Brasil) con datos sintéticos: medir cold-start, throughput, egress, interrupciones.
- [ ] Validación legal de residencia para procesamiento efímero fuera de São Paulo.
- [ ] Redactar ADR de offload GPU (sub-procesador, controles, base legal).

---

*Cifras de performance (820 fps ArcFace en RTX 4090 con TensorRT; ~17 ms embedding en GPU previa) y de pricing/seguridad de vast.ai (ISO 27001 / SOC 2 Type 2 / GDPR DPA; interruptible reclama con minutos de aviso) provienen de la documentación de InsightFace y vast.ai consultada el 2026-06-28; ver Fuentes en el mensaje de entrega. Las estimaciones de §4.2–4.3 son aproximaciones dimensionales para decisión, no benchmarks medidos: confírmense en el PoC.*
