# ADR-0010: Back office — roles, match manual, certificación y validación de autoridades

- **Estado:** accepted
- **Fecha:** 2026-06-26
- **Decisores:** Jeremi
- **Fase AI-DLC:** 02-design
- **Controles OWASP afectados:** A01 (control de acceso), A07 (autenticación), A08 (integridad), A09 (no repudio)
- **Relacionado:** RF-06/07/08/10/13, RS-01/02/06/09, AB-02/04/12, charter (matriz de transiciones, notificación delicada), [ADR-0004](0004-motor-de-matching.md), [ADR-0007](0007-esquema-reporte-retencion-auditoria.md), [ADR-0011](0011-contrato-eventos.md)

## Contexto

El back office es donde el humano cierra el lazo: confirma matches que el motor no auto-resuelve
(ADR-0004: el face-match **nunca** auto-confirma), certifica rescatistas, valida autoridades y
autoriza la notificación de información delicada. El charter ya fija la matriz de transiciones de
estado por mecanismo; falta formalizar **quién hace qué en la herramienta**, el **flujo de match
manual con firma**, el **ciclo de certificación** y la **cadena de confianza de autoridades**.

## Decisión

**1. Matriz de roles y permisos.**

| Módulo / Acción | Rescatista | Coordinador Verificado | Autoridad Civil/Médica |
| :---- | :---: | :---: | :---: |
| Reportar desaparecido (crear registro) | ✓ | ✓ | ✓ |
| Enviar información de rescatado (con/sin video *proof-of-life*) | ✓ | ✓ | ✓ |
| Registrar y certificar nuevos rescatistas | ✗ | ✓ | ✗ |
| Moderar y resolver colisiones (múltiples buscadores) | ✗ | ✓ | ✗ |
| Aprobar matches manuales (banda 65–85 %) | ✗ | ✓ | ✗ |
| Confirmar estado de salud crítico / fallecimiento | ✗ | ✗ | ✓ |
| Autorizar notificaciones de personas inconscientes | ✗ | ✗ | ✓ |

Coherente con la matriz de transiciones del charter (mecanismos 2/3/4) y con los umbrales del
ADR-0004 (65–85 % → coordinador; >85 % fusiona solo con confirmación humana; 100 % autoreporte es la
única vía automática).

**2. Flujo de match manual.** UI de comparación lado a lado (Entidad A = reporte de búsqueda vs
Entidad B = reporte en terreno) con panel de resolución: **ES UN MATCH** (agrupa reportes y notifica
a familiares) o **DESCARTAR** (separa entidades de forma permanente). **Justificación obligatoria** +
**firma del coordinador** (usuario + ID). La decisión emite el evento `match.resolved` (ADR-0011) y
se registra en la auditoría append-only con encadenamiento SHA-256 (ADR-0007). El merge sigue siendo
reversible (RF-11).

**3. Certificación de rescatistas.** Proceso en tres fases: **(1) Registro & carga** (el rescatista
sube datos + fotos), **(2) Verificación** (un Coordinador Verificado o Autoridad evalúa la
evidencia), **(3) Certificación** (activación de cuenta con emisión de token JWT). Máquina de estados:

```
[ PENDING ] --> [ CERTIFIED ] --> [ REVOKED ]
     |
     +--------> [ REJECTED ]
```

La revocación es un estado de primera clase (un rescatista comprometido se revoca, no se borra), y
toda transición queda auditada.

**4. Validación de autoridades — cadena de confianza jerárquica.** Sembrada por un **Admin Global**:
- **Nivel 1 — Raíz (ADMIN):** carga el listado inicial de autoridades nacionales y directores
  regionales (Protección Civil, directores de hospitales base).
- **Nivel 2 — Celdas regionales (confianza máxima):** sub-delegan a autoridades municipales o
  centros de salud dentro de su celda geográfica.
- **Nivel 3 — Nodos locales (centros médicos/refugios):** certifican identidades y estados de salud
  in situ.

Alta de autoridad: **(1) Pre-carga** de nómina oficial por el ADMIN (cédula + cargo) → **(2)
Invitación segura** con credencial única por canal seguro (email/satélite) → **(3) Validación en dos
pasos** (OTP SMS/satélite + token gubernamental) y activación con firma criptográfica.

**5. Notificación de información delicada** (exclusiva de Autoridad Civil/Médica):
- **A. Certificación de deceso** — única vía a `fallecido`; exige adjuntar nº de acta médica o foto
  de planilla forense; bloquea el perfil para edición pública y lo envía a la cola de notificaciones
  restringidas hacia buscadores con parentesco verificado.
- **B. Visibilidad de inconscientes / no identificados** — perfiles de personas en shock, coma o
  menores no identificables entran en **estado oculto automático**; solo la Autoridad Civil de la
  zona accede a la base de "Anónimos Inconscientes" para cruzarla de forma controlada, evitando
  exposición pública de fotos de menores/vulnerables.
- **C. Autorización de notificación de impacto** — disparar notificaciones a buscadores de colisión
  requiere **firma digital** de la Autoridad; hasta esa firma, los familiares solo ven
  `En Proceso de Localización`.

## Alternativas consideradas

| Opción | Pros | Contras | Riesgo de seguridad |
| :---- | :---- | :---- | :---- |
| **A. RBAC por rol + cadena de confianza jerárquica + firma por acción** ✅ | Refleja la realidad organizativa del rescate; separación de poderes (coordinador ≠ autoridad); delegación geográfica acotada; toda acción de alto costo firmada y auditada | Más complejo de modelar y operar; la cadena depende de un ADMIN raíz de máxima confianza | Compromiso del ADMIN raíz = riesgo sistémico → endurecer (A01); pero acota el blast radius por celda |
| **B. Roles planos sin jerarquía** | Simple | No modela la delegación regional ni la confianza en cascada; el ADMIN tendría que cargar cada nodo local | Cuellos de botella y permisos demasiado amplios |
| **C. Confianza implícita por institución (sin firma por acción)** | Menos fricción | Sin no repudio de las acciones delicadas (AB-10); riesgo de abuso | Repudio/abuso de notificación delicada (A08/A09) |

## Consecuencias

- **Positivas:** la separación coordinador/autoridad refleja el charter y evita que un solo rol mueva
  estados de alto costo; la cadena jerárquica permite escalar la validación de autoridades sin un
  cuello de botella central, acotando el blast radius por celda geográfica; cada acción delicada
  (match, certificación, deceso, liberación de información) lleva **firma + auditoría** (no repudio);
  la revocación de primera clase contiene rescatistas comprometidos (AB-02).
- **Negativas / deuda asumida:** el **ADMIN raíz** es un punto de confianza crítico (su compromiso es
  sistémico → MFA fuerte, 4-eyes, auditoría reforzada); la cadena de confianza exige **gobierno
  organizativo** (mantener nóminas, revocaciones, delegaciones); el flujo en dos pasos para
  autoridades depende de canales (SMS/satélite) frágiles en desastre; modelar y operar el RBAC
  jerárquico es más costoso que roles planos.
- **Impacto en threat model:**
  - **A01/A07 (control de acceso/suplantación):** RBAC + cadena de confianza + activación con firma
    criptográfica; revocación contiene cuentas comprometidas (T6/AB-02).
  - **A08/A09 (integridad/no repudio):** firma por acción + auditoría SHA-256 (ADR-0007) cubre el
    match manual, la certificación de deceso y la liberación de información (AB-10).
  - **T2/AB-04 (falso positivo):** el match manual con justificación + firma y la exclusividad de la
    autoridad para `fallecido` mantienen el human-in-the-loop (RS-09).
  - **AB-11 (menores):** el estado oculto automático para inconscientes/menores evita exposición
    pública.

## Decisiones abiertas

- `<TODO>` ¿Doble control (4-eyes) para certificación de deceso y acceso a "Anónimos Inconscientes"?
- `<TODO>` Procedimiento de recuperación/rotación del ADMIN raíz y de las celdas regionales.
- `<TODO>` Canal de respaldo cuando SMS/satélite no están disponibles para la validación en dos pasos.
- `<TODO>` Plantilla y registro de consentimiento/trazabilidad legal por cada firma de liberación de
  información delicada.

## Disparadores de revisión

- Abuso o compromiso de una celda regional → revisar la delegación y la auditoría de esa rama.
- El volumen de matches en banda 65–85 % satura a los coordinadores → recalibrar umbral (ADR-0004).
- Aparece la integración SAIME (Fase 2) → reforzar la validación de autoridades/identidad con ella.
