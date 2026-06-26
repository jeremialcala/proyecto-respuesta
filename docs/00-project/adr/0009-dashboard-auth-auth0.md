# ADR-0009: Autenticación del dashboard con Auth0 (OAuth 2.0) y stack del portal

- **Estado:** accepted
- **Fecha:** 2026-06-26
- **Decisores:** Jeremi
- **Fase AI-DLC:** 02-design
- **Controles OWASP afectados:** A01 (control de acceso), A07 (identificación/autenticación), A02 (misconfiguration)
- **Relacionado:** RS-01, RS-02, AB-01, [ADR-0008](0008-boveda-llaves-identidad.md), [ADR-0006](0006-residencia-sao-paulo.md), charter (Portal Web)

## Contexto

El **Portal Web** ("mis reportes") deja que un buscador administre sus reportes y vea reportes
públicos. Necesita autenticación de baja fricción para ciudadanos (no actores acreditados). El
charter ya define que el onboarding del usuario web combina **WhatsApp + correo** (ADR-0008), pero
falta fijar el **proveedor de identidad federada** y el **stack** del portal. Tensión de privacidad:
el social login implica un IdP externo (Auth0 + Google/Facebook/Microsoft) que ve metadatos de
acceso — aceptable para el rol ciudadano del portal, pero a vigilar bajo el objetivo anti-vigilancia
del proyecto (AB-01).

## Decisión

**1. Identidad federada con Auth0 (un tenant) para todo OAuth 2.0 / OIDC.** Social login con
**Google, Facebook y Microsoft (Hotmail/Outlook)**, además del onboarding WhatsApp + correo
(ADR-0008). Auth0 emite el JWT que consume la API (compatible con el `bearerAuth` del OpenAPI).

**2. Modelo de autorización — un solo rol en MVP.** El usuario del portal puede: administrar **sus**
reportes, ver **reportes públicos**, y **marcar sus reportes propios como públicos** para que el
resto de la red los vea. Los roles acreditados (rescatista/coordinador/autoridad) viven en el back
office (ADR-0010), no en este portal. Scoping: el usuario solo accede a lo suyo + lo público
(RS-02). El opt-in de conexión entre buscadores (charter) sigue siendo explícito y revocable.

**3. Stack del portal.** **Nginx** (reverse proxy/TLS) + **NestJS** (backend) + **Redis** (sesión/
caché) + **Postgres** (datos), en **TypeScript**. Reside en São Paulo (ADR-0006).

## Alternativas consideradas

| Opción | Pros | Contras | Riesgo de seguridad |
| :---- | :---- | :---- | :---- |
| **A. Auth0 (un tenant, OAuth2/OIDC) + social login** ✅ | Time-to-market; MFA, gestión de sesiones y federación listas; estándar OIDC; integra con JWT de la API | Dependencia de IdP externo (metadatos de acceso fuera); costo a escala; el IdP ve el grafo de acceso | El IdP externo conoce quién accede (A01 — mitigable, rol ciudadano); config de tenant a endurecer (A02) |
| **B. IdP self-hosted (Keycloak)** | Sin tercero (alinea privacidad/ADR-0006); control total | Operar y endurecer Keycloak; más carga sin funding | Buen encaje de privacidad pero más superficie propia que asegurar |
| **C. Auth propia (sesiones/JWT a mano)** | Cero dependencias | Reinventar MFA, federación, recuperación; alto riesgo de errores | Históricamente la mayor fuente de fallos de auth (A07) |

> **B (Keycloak)** queda como ruta de evolución si la dependencia de Auth0 (costo o privacidad) se
> vuelve un problema; el estándar OIDC hace la migración acotada. **C** descartada por riesgo.

## Consecuencias

- **Positivas:** autenticación robusta y federada con esfuerzo mínimo; MFA y recuperación
  delegadas; JWT estándar que encaja con la API existente; el rol único mantiene el MVP simple; stack
  TypeScript homogéneo (NestJS) y desplegable en São Paulo.
- **Negativas / deuda asumida:** **dependencia de un IdP externo** (Auth0) que ve metadatos de acceso
  — tensión con el objetivo anti-vigilancia, acotada porque el portal es el rol **ciudadano** (no el
  grafo sensible de acreditados); **costo de Auth0** a escala; el social login traslada parte de la
  confianza a Google/Facebook/Microsoft; hay que **endurecer la config del tenant** (callbacks,
  scopes mínimos, MFA).
- **Impacto en threat model:**
  - **A07/RS-01:** autenticación fuerte delegada a un IdP probado; reduce errores de auth propios.
  - **A01/AB-01:** el rol único + scoping evita que un usuario vea más que lo suyo y lo público; el
    grafo de búsqueda sensible no se expone (conciencia de red sigue siendo agregada y opt-in).
  - **A02:** configuración del tenant Auth0 (callbacks, CORS, scopes) pasa a ser superficie propia.

## Decisiones abiertas

- `<TODO>` Mapeo entre la identidad Auth0 (social) y el anclaje WhatsApp+email (ADR-0008): cómo se
  vincula la misma persona a través de ambos para "mis reportes".
- `<TODO>` Scopes/claims mínimos del JWT y política de expiración/refresh.
- `<TODO>` Residencia de los datos de Auth0 y exposición de metadatos (revisar contra ADR-0006).

## Disparadores de revisión

- El costo de Auth0 o su exposición de metadatos se vuelve crítico → migrar a Keycloak (B).
- El MVP necesita más de un rol en el portal → ampliar el modelo de autorización.
- Se introduce KYC (Fase 2, ADR-0008) → reconciliar con el flujo de identidad del portal.
