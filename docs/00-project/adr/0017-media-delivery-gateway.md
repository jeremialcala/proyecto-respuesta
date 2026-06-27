# ADR-0017: Media Delivery Gateway (entrega de medios por URL firmada)

- **Estado:** accepted
- **Fecha:** 2026-06-27
- **Decisores:** Jeremi
- **Fase AI-DLC:** 02-design / 03-implementation
- **Controles OWASP afectados:** A01 (control de acceso al objeto), A02 (firma/criptografía del token), A04 (exposición de datos sensibles), A05 (mala configuración del borde público), A09 (auditoría/observabilidad)
- **Relacionado:** RF-04/07, [ADR-0005](0005-webhook-manager-vault-worker.md) (ingestión Meta y bóveda), [ADR-0006](0006-residencia-sao-paulo.md) (residencia São Paulo), [ADR-0007](0007-esquema-reporte-retencion-auditoria.md) (auditoría/retención), [ADR-0008](0008-boveda-llaves-identidad.md) (cifrado de sobre por sujeto), [ADR-0011](0011-contrato-eventos.md) (eventos), [ADR-0012](0012-broker-aws-sqs-sns.md) (broker), [ADR-0014](0014-contenedores-despliegue-eks.md) (EKS/ALB), [ADR-0016](0016-enrolamiento-biometrico-desambiguacion.md) (desambiguación multi-rostro)

## Contexto

La desambiguación multi-rostro (ADR-0016) necesita que el **reportante vea los rostros** en el chat
para elegir cuál es el desaparecido. Meta (WhatsApp/Messenger/Instagram) renderiza una imagen en el
chat de dos maneras: (a) recibiendo un `media_id` que **subimos** a su Graph API, o (b) recibiendo un
**`link` HTTPS** que **los servidores de Meta descargan** y renderizan. Pero nuestros medios **no son
servibles tal cual**: viven **cifrados** en S3 con sobre DEK por sujeto (ADR-0008), tras escaneo
AV/CSAM (ADR-0005), y residen en São Paulo (ADR-0006). El `media_ref` es un puntero interno
(`s3://…`), no una URL renderizable.

Además esto **no es exclusivo de la desambiguación**: mostrar la foto del desaparecido a un
coordinador en el back office, reenviar una prueba de vida, o renderizar cualquier adjunto en
cualquier canal, comparte la misma necesidad — **exponer de forma controlada un binario que está
cifrado en la bóveda**. Hoy el `output-service` solo envía texto/plantilla; no hay ningún punto que
sirva medios. Mezclar esa función dentro del flujo de reporte o del core acoplaría una **superficie
pública de alto riesgo** (PII de imágenes) con la lógica de negocio.

## Decisión

**1. Componente independiente `media-gateway`.** Un servicio nuevo, espejo de salida del
`webhook-gateway` (ADR-0005): mientras el webhook-gateway es el **único endpoint público de
entrada**, el media-gateway es el **único endpoint público de salida de medios**. No conoce el
dominio de reporte; su única responsabilidad es **entregar un binario de la bóveda bajo una concesión
verificada**. Lo usan todos los canales y propósitos (desambiguación, foto en back office, prueba de
vida).

**2. Entrega por URL firmada que Meta descarga (no subir a Graph).** El componente que va a mostrar el
medio pide al gateway una **concesión** (`grant`) sobre un `media_ref` y obtiene una URL pública
opaca `https://media.respuesta.example/m/{token}`. Esa URL se manda a Meta como `link`; los servidores
de Meta la descargan y renderizan. Se descarta subir el binario a la Graph API (replicaría PII a Meta
y nos quitaría control y auditoría del render).

**3. La URL es opaca, firmada, de vida corta, de uso limitado y revocable.** El `token` no contiene
`media_ref` ni PII. Lleva un `token_id` aleatorio + HMAC (clave en KMS/Vault) para rechazo barato de
manipulación; un **ledger** (Postgres, sa-east-1) es la autoridad del estado: `expires_at` (minutos),
`max_uses` (pequeño) y `revoked_at`. **Importante sobre "un solo uso":** Meta suele descargar el
`link` **más de una vez** (previsualización + render + reintentos), por lo que el uso estricto de 1
rompería el render; se modela como **uso limitado configurable** (por defecto un N bajo) + TTL corto,
y como Meta **cachea** el medio en su CDN tras la primera descarga, el efecto al usuario final es de
**entrega única**. Casos sensibles pueden fijar `max_uses=1`.

**4. Descifrado al vuelo, solo medios limpios.** El gateway lee el ciphertext de S3 por `media_ref`,
**desenvuelve la DEK** vía KMS con el *encryption context* del sujeto (ADR-0008), descifra AES-GCM y
**transmite** los bytes. Solo sirve objetos con `scan=clean`. Reutiliza los puertos de lectura de la
bóveda (`MediaStore`, `EnvelopeCipher`).

**5. Dos planos.** Un plano **público** (`GET /m/{token}`, `HEAD`) que tocan Meta y otros fetchers,
endurecido tras ALB+WAF (ADR-0014). Un plano **interno** (mesh privado, IRSA/mTLS) para emitir y
revocar concesiones (`POST /grants`, `DELETE /grants/{token_id}`), que llaman `output-service`,
`chatbot-gateway` y el back office. La URL firmada se emite **en el momento del envío**, no cuando se
genera el evento, para que su TTL sea mínimo.

**6. Allowlist por audiencia + auditoría + rate-limit.** Cada concesión declara su **audiencia**:
`meta_fetchers` (restringe por rango IP/User-Agent de Meta), `authenticated_session` (back office) u
`open_token`. Cada descarga y cada emisión/revocación se registran en la **auditoría encadenada**
(ADR-0007). Rate-limit por token, por IP y global (Redis, ya en el stack del output-service) → 429.

## Alternativas consideradas

| Opción | Pros | Contras | Riesgo de seguridad |
|---|---|---|---|
| A. Subir binario a Graph API (`media_id`) | Sin endpoint público propio | Replica PII a Meta; retención de Meta opaca; sin auditoría del render; subida por canal | Medio: PII fuera de residencia (ADR-0006) |
| B. Presigned URL de S3 directo | Trivial | S3 guarda **ciphertext** → serviría datos cifrados inútiles; sin allowlist/uso-único/auditoría a nivel app; expone el bucket | Alto: borde sin control |
| C. Servir desde la API central autenticada | Reutiliza auth | Meta **no** puede autenticarse con bearer; acopla ancho de banda de imágenes al core; solo sirve back office | Alto acoplamiento |
| **D. media-gateway dedicado, URL firmada, TTL corto, uso limitado, allowlist, descifrado al vuelo (elegida)** | Aísla la superficie pública; reutilizable por todo canal/propósito; control y auditoría totales; residente en SP | Componente y ledger nuevos; ligera latencia de descifrado | Acotado: opaco, efímero, auditado |

## Consecuencias

- **Positivas:** la desambiguación (ADR-0016) puede mostrar rostros en el chat; cualquier canal
  renderiza medios por el mismo camino; la PII de imágenes **nunca** sale de São Paulo salvo la
  descarga puntual de Meta sobre una URL efímera y auditada; la superficie pública queda **aislada**
  del core y del flujo de reporte; escala independiente (ancho de banda de imagen) bajo HPA (ADR-0014).
- **Negativas / deuda asumida:** nuevo borde público que endurecer (WAF, allowlist); ledger de
  concesiones (Postgres) + contadores en Redis; el `output-service` gana `send_image(link)`; el
  render exige tolerar **multi-descarga** de Meta (`max_uses` > 1).
- **Impacto en threat model:** **nueva superficie de exposición de PII**. Mitigaciones: token opaco
  sin PII + HMAC (A01/A02), TTL de minutos y uso limitado/revocable (A04), allowlist de fetchers de
  Meta (A05), solo `scan=clean`, *encryption context* por sujeto (A08/ADR-0008), auditoría de toda
  descarga y rate-limit (A09). No hay SSRF (el gateway no busca URLs del usuario). Enumeración mitigada
  por `token_id` aleatorio de 128 bits.

## Pendiente

- Fuente y refresco del allowlist de fetchers de Meta (rangos IP / `facebookexternalhit` / fetcher de
  WhatsApp) — pueden cambiar; mantener por config.
- Calibrar `max_uses` y TTL por propósito (crop de desambiguación vs foto de back office vs prueba de
  vida).
- Soporte de **HTTP Range** para video (prueba de vida) y límites de tamaño por canal (p. ej. imagen
  ≤ 5 MB en WhatsApp).
- ¿CDN firmado (CloudFront) por delante? Se pospone por residencia/PII; reevaluar post-MVP.
- Revocación masiva por `report_id`/`entity_id` al purgar (enlazar con la minimización de ADR-0016).
