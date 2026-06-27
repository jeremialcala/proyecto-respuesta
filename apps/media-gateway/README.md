# media-gateway

Único endpoint **público de salida de medios** de Respuesta — espejo del
[webhook-gateway](../webhook-gateway) (que es el único de **entrada**). Implementa
[ADR-0017](../../docs/00-project/adr/0017-media-delivery-gateway.md) sobre EKS/ALB
([ADR-0014](../../docs/00-project/adr/0014-contenedores-despliegue-eks.md)), región São Paulo
([ADR-0006](../../docs/00-project/adr/0006-residencia-sao-paulo.md)).

**Responsabilidad única:** entregar un binario que vive **cifrado** en la bóveda
([ADR-0008](../../docs/00-project/adr/0008-boveda-llaves-identidad.md)) bajo una **concesión
verificada**, para que Meta lo descargue por `link` y lo renderice en el chat. **No** conoce el
dominio de reporte. Lo usan todos los canales y propósitos: desambiguación de rostros
([ADR-0016](../../docs/00-project/adr/0016-enrolamiento-biometrico-desambiguacion.md)), foto del
desaparecido en el back office, prueba de vida, cualquier adjunto.

## Convención clave

- **No** sirve nada sin concesión. La URL es opaca (`/m/{token}`), firmada (HMAC), de **TTL corto**,
  **uso limitado** y **revocable** — el ledger (Postgres) es la autoridad del estado.
- Descifra **al vuelo** desde S3 con el *encryption context* del sujeto; solo sirve `scan=clean`.
- Toda descarga, emisión y revocación se **auditan** (cadena SHA-256, ADR-0007) y se **rate-limitan**.

## Planos

- **Público** (tras ALB+WAF): `GET /m/{token}`, `HEAD /m/{token}` — lo tocan Meta y demás fetchers.
- **Interno** (mesh privado, IRSA/mTLS): `POST /grants`, `DELETE /grants/{token_id}`,
  `POST /grants:revoke-by-ref` — los llaman `output-service`, `chatbot-gateway` y el back office.

Diseño completo en [`docs/design.md`](docs/design.md).
