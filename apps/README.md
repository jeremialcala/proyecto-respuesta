# apps/ — Servicios ejecutables

Servicios runnable de Respuesta. Todos siguen **Clean Architecture / DDD** (dominio puro testeado +
puertos + adaptadores con deps perezosas), son **container-ready** (Dockerfile no-root) y tienen
manifiestos en `deploy/k8s/<servicio>` (ADR-0014). Mensajería **AWS SQS/SNS** con sobre de eventos
común (ADR-0011/0012).

| Servicio | Rol | Eventos | Tests |
| :---- | :---- | :---- | :---: |
| `webhook-gateway` | Borde de ingestión Meta (FastAPI): firma + idempotencia | → `meta.received` | 15 |
| `meta-handler` | Normaliza y reparte el crudo | `meta.received` → `inbound.text`/`inbound.media` | 11 |
| `vault-worker` | Descarga + escaneo AV/CSAM + cifrado de sobre por usuario | `inbound.media` → `media.stored` | 8 |
| `chatbot-gateway` | Canal principal: rieles + LLM on-prem **no autoritativo** | `inbound.text` → `outbound.reply`/`report.received` | 12 |
| `output-service` | Salida a Graph API (texto / plantilla HSM por ventana 24h) | `outbound.reply` → Meta | 5 |
| `core-backend` | API + orquestador: reportes, estados, **auditoría SHA-256** | `report.received` → `report.ingested`/`state.changed` | 16 |
| `matching-worker` | Motor de matching facial **ArcFace 512-d** (GPU) | `report.ingested`/`media.stored` → `candidate.generated` | 32 |
| `llm` | LLM on-premises (Ollama, GPU) — sin código propio | inferencia para `chatbot-gateway` | — |

**Total: 99 tests unitarios en verde.** Detalle por servicio en su `README.md` y `docs/design.md`.

Cada servicio hereda los controles del threat model (`docs/02-design/threat-model.md`) y de los ADRs
(`docs/00-project/adr/`). Dev local con `docker-compose.yml`; despliegue EKS con `deploy/k8s` (ADR-0014).
