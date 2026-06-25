# apps/ — Servicios ejecutables

Servicios runnable de Respuesta (scaffolding pendiente; convención `src/`, pirámide `tests/`, `docs/`):

| Servicio | Rol | Notas |
| :---- | :---- | :---- |
| `api-backend` | API/Backend REST | Orquesta reportes, estados, auth y federación PFIF |
| `chatbot-gateway` | Pasarela de chatbot | Adaptadores WhatsApp/IG/Messenger/Telegram + rieles NeMo + orquestador |
| `matching-worker` | Motor de matching | Worker AMQP: resolución de entidades + candidatos (cola+worker, ADR-0001). **Esqueletado test-first** (dominio + tests en verde; adaptadores pendientes) |
| `llm` | LLM on-premises | Ollama self-hosted (ADR-0001); evolución a vLLM/TGI según throughput |

> Cada servicio sigue Clean Architecture / DDD (ver `docs/02-design/architecture.md`) y hereda los
> controles del threat model.
