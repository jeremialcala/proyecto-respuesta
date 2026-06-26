# ADR-0008: Bóveda de llaves por usuario e identidad (Vault + WhatsApp/email, KYC en Fase 2)

- **Estado:** accepted
- **Fecha:** 2026-06-26
- **Decisores:** Jeremi
- **Fase AI-DLC:** 02-design
- **Controles OWASP afectados:** A01 (control de acceso), A02 (fallos criptográficos), A04 (data), A07 (identificación/autenticación)
- **Relacionado:** RS-01, RS-03, RS-11, AB-02, AB-05, threat model T4/T6, [ADR-0005](0005-webhook-manager-vault-worker.md) (consolida "KMS"), [ADR-0003](0003-hosting-modelo-a.md)/[ADR-0006](0006-residencia-sao-paulo.md), [ADR-0007](0007-esquema-reporte-retencion-auditoria.md)

## Contexto

El [ADR-0005](0005-webhook-manager-vault-worker.md) introdujo el cifrado de sobre (DEK por objeto
envuelta por **KMS**) para los medios, dejando "KMS" como pieza genérica. Dos necesidades obligan a
concretarla y a anclar la identidad:

1. **Confidencialidad por sujeto.** Con la residencia en São Paulo (ADR-0006) el blindaje legal baja,
   así que el **control técnico pasa a ser la primera línea** contra exfiltración/compulsión (T4): el
   dato debe estar cifrado con **llaves por usuario**, no con una única llave global.
2. **Anclaje de identidad.** El usuario entra por WhatsApp (número de teléfono), que es un
   identificador **débil** (reciclaje, SIM swap — AB-02/T6). Hay que definir cómo se verifica la
   identidad y cómo se recupera el acceso.

## Decisión

**1. Gestor de secretos: HashiCorp Vault.** Vault es el KMS/secrets manager concreto que el
ADR-0005 dejó genérico. Custodia: tokens de Meta, claves JWE por evento, y la **jerarquía de llaves
por usuario**.

**2. Cifrado por usuario.** Se cifran los **PII** (en Postgres) y los **archivos de medios** (en S3,
`sa-east-1`). Esquema de sobre por sujeto: una **clave de datos por usuario (DEK)** cifra sus
reportes y medios; la DEK se **envuelve con una KEK** gestionada por Vault (Transit/KMS). Comprometer
el object store o la base sin Vault no revela datos en claro.

**3. Identidad por fases.**
- **Fase 1 (MVP):** verificación conjunta **WhatsApp + email** (doble canal: OTP por WhatsApp + OTP
  por email) para anclar la cuenta a algo más que un número. Mitiga parcialmente SIM swap (AB-02).
- **Fase 2:** **KYC completo** para asegurar la identidad de todos los actores (alineado con la
  verificación SAIME de mínima divulgación del charter).

**4. Recuperación de acceso.** Autogestión vía **correo + WhatsApp** (ambos canales); recuperación
**manual desde el back office** por un coordinador (operación auditada en la cadena SHA-256 —
ADR-0007). No existe recuperación que rompa el cifrado por usuario sin pasar por Vault.

**5. Acceso en claro.** El **coordinador**, desde el back office, puede ver datos en claro para la
gestión del ciclo de vida de los reportes. Cada acceso en claro se **registra en la auditoría
append-only** (ADR-0007) con actor, sujeto y timestamp.

## Alternativas consideradas

| Opción | Pros | Contras | Riesgo de seguridad |
| :---- | :---- | :---- | :---- |
| **A. Vault + cifrado por usuario (DEK por sujeto, KEK en Vault)** ✅ | Compromiso del store no revela datos; granularidad por sujeto; reúne secretos y llaves en una pieza self-hostable (alinea ADR-0006) | Operar Vault (HA, sellado/unseal, rotación); más latencia por envoltura; complejidad de gestión de llaves | Minimiza T4 (exfiltración); Vault es objetivo crítico → endurecer (A02) |
| **B. Cifrado con llave global única** | Simple | Una llave compromete todo; sin granularidad | Blast radius total ante fuga de la llave |
| **C. KMS gestionado del proveedor cloud** | Cero ops de KMS | Llaves bajo el proveedor (y su jurisdicción) → choca con el objetivo anti-compulsión del Modelo A | El proveedor (o un requerimiento) podría acceder a las llaves (A01/A04) |
| **Identidad: solo número WhatsApp** | Fricción mínima | SIM swap / reciclaje → suplantación | AB-02/T6 sin mitigar |
| **Identidad: WhatsApp + email (F1) → KYC (F2)** ✅ | Doble canal sube el costo del ataque; KYC fuerte cuando se pueda | Email también es atacable; KYC añade fricción y datos | Reduce AB-02; KYC introduce más PII a proteger |

## Consecuencias

- **Positivas:** el cifrado por usuario convierte el control técnico en la primera línea de defensa
  (clave tras São Paulo, ADR-0006), acotando T4; Vault unifica secretos y llaves en una pieza bajo
  control del operador; la identidad doble canal sube el listón frente a SIM swap; la recuperación
  tiene una vía de autogestión y un backstop humano auditado; todo acceso en claro queda trazado.
- **Negativas / deuda asumida:** **operar Vault** (alta disponibilidad, política de unseal, rotación
  de KEK) es carga real; la envoltura por sujeto añade **latencia** en lectura/escritura; el email
  como segundo factor también es atacable; el KYC de Fase 2 **introduce más PII** que proteger; el
  acceso en claro del coordinador es un **punto de poder** que depende de la disciplina de auditoría.
- **Impacto en threat model:**
  - **T4 (exfiltración/compulsión):** sin Vault no hay datos en claro aunque se tome el store; bajo
    São Paulo esto es la mitigación principal, no la jurisdicción.
  - **T6/AB-02 (suplantación / SIM swap):** doble canal en Fase 1, KYC en Fase 2.
  - **A02:** Vault pasa a ser activo crítico → endurecimiento, unseal seguro, rotación.
  - **A01/A09:** acceso en claro del coordinador minimizado por rol y auditado (ADR-0007).

## Decisiones abiertas

- `<TODO>` Topología de Vault (HA, auto-unseal con KMS del cloud vs. Shamir), política de rotación de
  KEK y de revocación de DEK por usuario al borrado (RS-07).
- `<TODO>` Proveedor de KYC para Fase 2 y su residencia (no debe reintroducir el riesgo de ADR-0006).
- `<TODO>` Endurecer email como 2º factor (anti-phishing, dominios, expiración corta de OTP).
- `<TODO>` ¿El acceso en claro del coordinador requiere doble control (4-eyes) para datos de menores?

## Disparadores de revisión

- Incidente de SIM swap real → adelantar KYC o reforzar el doble canal.
- La latencia de envoltura degrada el SLO → caché de DEK con TTL corto en memoria protegida.
- Vault se vuelve cuello de botella operativo → evaluar HSM gestionado bajo control del operador.
