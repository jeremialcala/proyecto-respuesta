# Clasificación de Datos — Respuesta

> Proyecto: **Respuesta** · Fase AI-DLC: `00-project` · Estado: borrador vivo
> Última actualización: 2026-06-25

Inventario de los datos que maneja la plataforma, su sensibilidad y su tratamiento. Alimenta
directamente el **threat model** (fase 02-design). Listón regulatorio adoptado: **GDPR** (incluida
la categoría especial del Art. 9 para datos biométricos y de salud), aunque Venezuela no esté bajo
su jurisdicción.

## Niveles de clasificación

| Nivel | Significado |
| :---- | :---- |
| **Público** | Puede divulgarse sin daño. |
| **Interno** | Solo para operación del sistema; sin PII directa. |
| **Confidencial** | PII o datos cuya exposición causa daño a la persona. |
| **Restringido** | Datos de máxima sensibilidad (biométricos, menores, ubicación de vulnerables, fallecimiento). Daño grave o irreversible si se exponen. |

## Inventario de datos

| Dato | Clasificación | Regulación / Categoría | Cifrado | Retención | Notas |
| :---- | :---- | :---- | :---- | :---- | :---- |
| **Foto de referencia del desaparecido** | Restringido | GDPR Art. 9 (biométrico) | En reposo y tránsito | Hasta cierre de emergencia | Aportada por el buscador; base del face-match. |
| **Foto/captura del rescatado** | Restringido | GDPR Art. 9 (biométrico) | En reposo y tránsito | Hasta cierre de emergencia | Tomada en terreno; mala calidad esperable. |
| **Video Proof-of-life (~30 s)** | Restringido | GDPR Art. 9 (biométrico + voz) | En reposo y tránsito | Hasta cierre de emergencia | Revela rostro, voz y ubicación; se entrega como **link asegurado por login**, no como video en chat; control de reenvío, sin difusión pública. |
| **Plantilla/embedding biométrico facial** | Restringido | GDPR Art. 9 (biométrico) | En reposo y tránsito | Borrar con la foto origen | Derivado; tratar con el mismo rigor que la imagen. |
| **Datos de menores (cualquier categoría)** | Restringido | GDPR Art. 8 + Art. 9 | En reposo y tránsito | Mínimo imprescindible | Face-match menos fiable en niños; nunca única base de decisión. |
| **Ubicación última conocida / de hallazgo** | Restringido | GDPR (dato personal sensible por contexto) | En reposo y tránsito | Hasta cierre de emergencia | En el contexto venezolano puede habilitar vigilancia/persecución. |
| **Estado de la persona** (`a_salvo`…`fallecido`) | Confidencial | GDPR Art. 9 si refleja salud | En reposo | Hasta cierre de emergencia | `fallecido` solo lo fija la autoridad. |
| **Nombre y datos de identificación de la persona** | Confidencial | GDPR Art. 6 (PII) | En reposo | Hasta cierre de emergencia | |
| **Datos de contacto del buscador** | Confidencial | GDPR Art. 6 (PII) | En reposo | Hasta cierre de emergencia | Solo se comparte con el clúster vía opt-in revocable. |
| **Declaración de filiación (honor-based, Fase 1)** | Confidencial | GDPR Art. 6 | En reposo | Hasta cierre de emergencia | Filiación auto-declarada (Facebook descartado); registro auditable; verificación débil. |
| **Verificación biométrica SAIME (Fase 2)** | Restringido | GDPR Art. 9 (biométrico) + habeas data | En reposo y tránsito | No persistir resultado más de lo necesario | Verificación exacta contra biometría estatal; **riesgo de privacidad muy alto**; diseñar con mínima divulgación (que el Estado no registre quién consulta por quién). |
| **Mensajes vía redes de mensajería** | Restringido | GDPR Art. 6/9 (transitan por procesador externo) | En tránsito (proveedor) + en reposo (nuestro) | Hasta cierre de emergencia | WhatsApp/IG/Messenger/Telegram procesan el mensaje; no reenviar biométricos por el canal; ingerir adjuntos al almacén protegido. Requiere DPA. |
| **Contexto de conversación procesado por el LLM** | Confidencial | GDPR Art. 6/9 | En reposo (interno) | No persistir más de lo necesario | **LLM on-premises**: la PII no sale de la frontera (sin proveedor externo). Minimizar lo que se retiene del turno conversacional. |
| **Relación de parentesco** | Confidencial | GDPR Art. 6/9 | En reposo | Hasta cierre de emergencia | Define el orden de notificación delicada. |
| **Acreditación de rescatistas/coordinadores** | Confidencial | GDPR Art. 6 (PII laboral) | En reposo | Mientras esté activo | Verificada con autoridades. |
| **Registro de notificación de fallecimiento** | Restringido | GDPR Art. 9 | En reposo | Cierre de emergencia + 12 meses | Acto sensible; trazabilidad del mediador. |
| **Logs / metadatos de matching y auditoría** | Interno | GDPR (si contienen IDs) | En reposo | Limitada; seudonimizar | Necesarios para reversibilidad y auditoría; minimizar PII. |
| **Puntuaciones de confianza / candidatos** | Interno | — | En reposo | Transitoria | No exponer fuera del back office. |
| **Contenido público de campañas/avisos** | Público | — | No requerido | — | Solo material explícitamente destinado a difusión. |

## Principios de tratamiento (GDPR)

- **Base legal**: interés vital (Art. 6.1.d) durante la emergencia y/o consentimiento explícito
  (Art. 9.2.a) para biométricos y Proof-of-life. Documentar cuál aplica a cada dato.
- **Minimización**: capturar solo lo necesario para localizar y reunir; nada "por si acaso".
- **Limitación de almacenamiento**: borrado de biométricos y ubicaciones al **cierre de la
  emergencia**. El cierre se define como: *cuando todos los esfuerzos de búsqueda se dan por
  cerrados y se inicia la fase de reconstrucción* **+ 12 meses**. El evento, su fecha y las
  evidencias que lo sustentan se gestionan dentro de la plataforma (registro auditable). El mismo
  criterio aplica al **registro de notificación de fallecimiento**.
- **Derecho al borrado**: un buscador o persona puede solicitar la eliminación de sus datos.
- **Control de acceso**: activos Restringidos solo accesibles a actores acreditados y al clúster
  verificado; sin reenvío libre del Proof-of-life. El acceso en claro del coordinador queda auditado
  (ver abajo).
- **Cifrado por usuario**: PII y medios se cifran con **llave por usuario** (DEK por sujeto envuelta
  por KEK en HashiCorp Vault) — [ADR-0008](adr/0008-boveda-llaves-identidad.md). Comprometer el store
  sin Vault no revela datos en claro (control técnico de primera línea tras la residencia regional).
- **Auditoría append-only (SHA-256)**: toda operación sobre datos sensibles (incluido el acceso en
  claro y el diferimiento de retención) se registra en una tabla inmutable con encadenamiento de
  hashes — [ADR-0007](adr/0007-esquema-reporte-retencion-auditoria.md).
- **Seudonimización** de logs y metadatos siempre que sea posible.

## Definición: cierre de la emergencia

El **cierre de la emergencia** es el evento que gatilla el borrado de los datos Restringidos
(biométricos, ubicaciones) y del registro de notificación de fallecimiento. Se define como:

> Cuando todos los esfuerzos de búsqueda se dan por cerrados **y** se inicia la fase de
> reconstrucción, **más 12 meses**.

El evento se gestiona dentro de la plataforma con su fecha y **evidencias** que lo sustenten,
en un registro auditable. El borrado se ejecuta automáticamente al cumplirse el plazo.

## Decisiones abiertas

- `<TODO>` Encargado del tratamiento (procesador) y proveedor de hosting concreto en `sa-east-1`.
- `<TODO>` Base legal LGPD y mecanismo de transferencia para datos capturados en Venezuela hacia el
  hosting de **São Paulo** (cláusulas contractuales / base legal de interés vital). Ver
  [ADR-0006](adr/0006-residencia-sao-paulo.md).

## Responsable del tratamiento y jurisdicción — **Decisión: Modelo A (región enmendada)**

> Formalizado en [ADR-0003](adr/0003-hosting-modelo-a.md); **región enmendada a São Paulo** en
> [ADR-0006](adr/0006-residencia-sao-paulo.md).


**Adoptado:** operador humanitario internacional como responsable del tratamiento —entidad del
proyecto domiciliada en una jurisdicción con protección de datos fuerte— con **hosting en São Paulo
(`sa-east-1`, Brasil)**. Originalmente se decidió hosting en la UE (adecuación GDPR); la región se
**enmendó a São Paulo** por menor latencia hacia Venezuela/diáspora y costo/disponibilidad de
infraestructura. Implicación: residencia bajo **LGPD** (Brasil), con **GDPR como listón interno** —
se siguen aplicando minimización, limitación de almacenamiento, cifrado y borrado al estándar GDPR
aunque no sea la jurisdicción. Como el blindaje legal baja respecto a la UE, el **control técnico**
(cifrado por usuario con bóveda Vault — [ADR-0008](adr/0008-boveda-llaves-identidad.md)) pasa a ser la
primera línea contra exfiltración/compulsión. La integración con autoridades se mantiene **solo** para
acreditar rescatistas, no para custodiar datos. Marco legal venezolano débil (sin ley integral; solo
habeas data Art. 28 + ARCO).

Alternativas consideradas y descartadas (registradas para trazabilidad):

> Aviso: esto no es asesoría legal. Conviene validar con un abogado de protección de datos y, dado
> el mandato humanitario, explorar una alianza con la Cruz Roja (ICRC) por sus privilegios e
> inmunidades sobre los datos.

Factores que pesan: protección frente a acceso/compulsión gubernamental (riesgo de persecución a
los buscadores), resiliencia de infraestructura (el sismo tumbó energía y telecom en el país),
GDPR como listón (y posibles titulares en la diáspora UE), y legitimidad/neutralidad humanitaria.

| Modelo | Responsable | Hosting | Pros | Contras |
| :---- | :---- | :---- | :---- | :---- |
| **A. Operador humanitario internacional** | Entidad del proyecto domiciliada en jurisdicción con protección fuerte, o alianza ICRC | Nube UE / región con adecuación | Máxima protección legal, GDPR nativo, blindaje ante compulsión local, infra resiliente, neutralidad | Gobernanza de transferencia transfronteriza; dependencia de proveedor externo |
| **B. ONG/asociación civil venezolana** | ONG local | Nube fuera del país (UE/neutral) | Control operativo local + datos protegidos fuera | El responsable local sigue bajo jurisdicción venezolana (compulsión/presión); habeas data débil |
| **C. Entidad gubernamental** | Protección Civil u órgano oficial | Nacional | Mandato oficial, integración con autoridades, soberanía | **Mayor riesgo** para los buscadores (el gobierno custodia la red de búsqueda); protección legal e infra débiles |
| **D. Federado ICRC** | ICRC como responsable/encargado bajo su marco RFL | Infraestructura ICRC | Privilegios e inmunidades (datos a menudo blindados frente a citaciones), marco RFL maduro, neutralidad | Menor autonomía; alinearse a procesos ICRC; montaje más lento |

El modelo **D (ICRC)** queda como alianza a explorar en paralelo: si se concreta, sus privilegios e
inmunidades reforzarían el blindaje del dato. Los modelos **B** y **C** se descartan como custodios
de los datos sensibles por dejar al responsable bajo jurisdicción venezolana (riesgo de
compulsión/persecución).
