# apps/ — Servicios ejecutables

Servicios runnable de Respuesta. Todos siguen **Clean Architecture / DDD** (dominio puro testeado +
puertos + adaptadores con deps perezosas), son **container-ready** (Dockerfile no-root) y tienen
manifiestos en `deploy/k8s/<servicio>` (ADR-0014). Mensajería **AWS SQS/SNS** con sobre de eventos
común (ADR-0011/0012).

| Servicio | Rol | Eventos | Tests |
| :---- | :---- | :---- | :---: |
| `webhook-gateway` | Borde de ingestión Meta (FastAPI): firma + idempotencia | → `meta.received` | 14 |
| `meta-handler` | Normaliza y reparte el crudo (texto, imagen y **respuestas interactivas** de botón/lista) | `meta.received` → `inbound.text`/`inbound.media` | 13 |
| `vault-worker` | Descarga + escaneo AV/CSAM + cifrado de sobre por usuario (**passthrough en dev**) | `inbound.media` → `media.stored` | 8 |
| `chatbot-gateway` | Canal principal: rieles + LLM on-prem **no autoritativo** + memoria pgvector + desambiguación | `inbound.text` → `outbound.reply`/`report.received`/`face.disambiguation.resolved` | 33 |
| `output-service` | Salida a Graph API: texto / plantilla HSM (ventana 24h) + **imagen y botón de opciones** (desambiguación) | `outbound.reply` → Meta | 10 |
| `media-gateway` | **Entrega de medios por URL firmada** (ADR-0017): dos planos (público `GET /m/{token}` + interno `POST /grants`) | `POST /grants` → URL firmada | 28 |
| `core-backend` | API + orquestador: reportes, estados, **auditoría SHA-256** | `report.received` → `report.ingested`/`state.changed` | 21 |
| `matching-worker` | Motor facial **ArcFace 512-d** (pool GPU dedicado, ADR-0018) + enrolamiento/desambiguación + revocación + **idempotente por `event_id`** + extractor **local/remoto** (ADR-0019) | `report.ingested` → `entity.enrolled`/`enrollment.failed`/`face.disambiguation.requested` | 59 |
| `inference-worker` | **Plano de inferencia stateless** (imagen OCI dedicada del matching-worker, ADR-0019): imagen → embedding 512-d, **sin secretos**, portable (EKS/on-prem/vast.ai) | `face.extract.requested` → `face.embedded` (solo-vector) | — |
| `llm` | LLM on-premises (Ollama, **pool GPU dedicado** separado del facematch, ADR-0018) — sin código propio | inferencia para `chatbot-gateway` | — |

**Total: 186 tests unitarios en verde.** Detalle por servicio en su `README.md` y `docs/design.md`.

Cada servicio hereda los controles del threat model (`docs/02-design/threat-model.md`) y de los ADRs
(`docs/00-project/adr/`). Dev local con `docker-compose.yml`; despliegue EKS con `deploy/k8s` (ADR-0014).
