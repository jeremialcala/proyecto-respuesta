# ADR-0003: Hosting y responsable del tratamiento — Modelo A

- **Estado:** accepted — **región enmendada por [ADR-0006](0006-residencia-sao-paulo.md)** (UE → São Paulo)
- **Fecha:** 2026-06-25
- **Decisores:** Jeremi
- **Fase AI-DLC:** 02-design
- **Controles OWASP afectados:** A01 (access control), A02 (misconfiguration), A04 (cryptographic/data), A09 (logging)
- **Relacionado:** [ADR-0001](0001-llm-on-premises.md), [ADR-0006](0006-residencia-sao-paulo.md), `data-classification.md`, charter

> **Nota de enmienda (2026-06-26):** el **modelo de responsable** (operador humanitario
> internacional, gobierno fuera de la custodia) sigue vigente. La **región de hosting** se cambió de
> "UE / adecuación GDPR" a **São Paulo (`sa-east-1`)** en [ADR-0006](0006-residencia-sao-paulo.md);
> GDPR se conserva como **listón interno**, no como jurisdicción. Léase este ADR con esa enmienda.

## Contexto

Respuesta trata datos de máxima sensibilidad (biométricos, ubicaciones, datos de menores, estados
de fallecimiento) de personas vulnerables, en un contexto donde existe **riesgo real de que el
Estado quiera acceder al grafo de quién busca y quién aparece** (persecución). Venezuela **carece de
ley integral de protección de datos**: solo el habeas data constitucional (Art. 28) + derechos ARCO
ante tribunales, sin autoridad de control. Por tanto, **dónde vive el dato y quién es legalmente
responsable** es una decisión de seguridad, no solo de infraestructura.

## Decisión

Adoptamos el **Modelo A**:

- **Responsable del tratamiento:** un **operador humanitario internacional** —entidad del proyecto
  domiciliada en una jurisdicción con protección de datos fuerte—.
- **Hosting:** **nube en la UE** (o región con adecuación GDPR), bajo control de la entidad. Esa
  misma infraestructura aloja la **inferencia del LLM on-premises** (ADR-0001) y los **almacenes de
  datos restringidos**.
- **Gobierno venezolano:** **fuera de la custodia** de los datos sensibles. Solo se integra para
  **acreditar rescatistas** y, en Fase 2, para la verificación SAIME con **mínima divulgación**.
- **ICRC (Modelo D):** alianza a **explorar en paralelo**; si se concreta, sus privilegios e
  inmunidades reforzarían el blindaje del dato.

> **Reconciliación con ADR-0001:** "on-premises" significa infraestructura **bajo nuestro control**
> (no un SaaS de terceros), que reside dentro de este hosting UE del Modelo A. No es contradicción:
> el LLM corre en GPU/infra que administramos en la jurisdicción del Modelo A.

## Alternativas consideradas

| Opción | Pros | Contras | Riesgo de seguridad |
| :---- | :---- | :---- | :---- |
| **A. Operador internacional + hosting UE** ✅ | Máxima protección legal; GDPR nativo; **blindaje ante compulsión local**; infra resiliente; neutralidad; autonomía | Transferencia transfronteriza a gobernar; dependencia de proveedor cloud; **costo sin funding** (créditos/donaciones, GPU para el LLM); operar fuera del país de uso | Reduce exposición a acceso estatal (A01/A04); requiere endurecer config cloud (A02) |
| **B. ONG venezolana + hosting externo** | Control operativo local + datos fuera | El responsable local sigue **bajo jurisdicción venezolana** (compulsión/presión); habeas data débil | Responsable expuesto a coacción |
| **C. Entidad gubernamental + hosting nacional** | Mandato oficial; integración con autoridades; soberanía | **Mayor riesgo** para los buscadores (el Estado custodia la red de búsqueda); protección legal e infra débiles | Custodia estatal de datos sensibles = inaceptable para el objetivo |
| **D. Federado ICRC** | Privilegios e inmunidades (datos a menudo blindados frente a citaciones); marco RFL maduro; neutralidad | Menor autonomía; alinearse a procesos ICRC; montaje más lento | El más fuerte en protección; se mantiene como alianza paralela |

## Consecuencias

- **Positivas:** protección legal fuerte y blindaje frente a compulsión del Estado venezolano; GDPR
  como marco nativo (no adaptado); infraestructura resiliente frente a la fragilidad local que el
  propio sismo evidenció; neutralidad humanitaria; autonomía para operar.
- **Negativas / deuda asumida:** hay que **gobernar la transferencia transfronteriza** (datos
  capturados en Venezuela → hosting UE); **latencia** mayor para usuarios en el país (mitigada por
  offline-first y porque muchos buscadores están en la diáspora); dependencia de un proveedor cloud
  externo; **costo** difícil sin funding (créditos/donaciones, GPU para el LLM on-prem); complejidad
  de operar en una jurisdicción distinta a la de uso.
- **Impacto en threat model:**
  - **A01/A04:** los datos sensibles quedan fuera del alcance directo de la compulsión local y
    cifrados; el control de acceso por rol/clúster sigue siendo obligatorio.
  - **A02:** la responsabilidad de endurecer la configuración de la nube (redes, IAM, buckets) es
    nuestra.
  - **A09:** auditoría y logging viven bajo nuestra jurisdicción.

## Decisiones abiertas

- `<TODO>` Jurisdicción exacta de domicilio de la entidad responsable.
- `<TODO>` Proveedor cloud concreto y región UE; disponibilidad de GPU para el LLM (ADR-0001).
- `<TODO>` Mecanismo legal de **transferencia transfronteriza** (base de interés vital / cláusulas)
  para los datos capturados en Venezuela.

## Disparadores de revisión

- Se concreta la alianza ICRC (Modelo D) → reevaluar responsable/encargado.
- Aparece funding o infraestructura donada que cambie el balance costo/control.
- Cambia el marco legal venezolano (aparece una ley de datos con autoridad de control).
