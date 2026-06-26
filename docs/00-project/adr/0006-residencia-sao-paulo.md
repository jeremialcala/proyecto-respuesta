# ADR-0006: Residencia de datos en São Paulo (enmienda la región de ADR-0003)

- **Estado:** accepted
- **Fecha:** 2026-06-26
- **Decisores:** Jeremi
- **Fase AI-DLC:** 02-design
- **Controles OWASP afectados:** A01 (control de acceso), A02 (misconfiguration), A04 (data), A09 (logging)
- **Relacionado:** [ADR-0003](0003-hosting-modelo-a.md) (enmendado — región), `data-classification.md`, charter, threat model T4/T7

## Contexto

El [ADR-0003](0003-hosting-modelo-a.md) adoptó el **Modelo A** (operador humanitario internacional
como responsable del tratamiento) con **hosting en nube de la UE / región con adecuación GDPR**,
cuyo objetivo era el blindaje legal frente a la compulsión del Estado venezolano y un marco GDPR
nativo. Tres fuerzas operativas obligan a revisar **la región** (no el modelo de responsable):

1. **Latencia hacia los usuarios.** Buena parte del tráfico se origina en Venezuela y la diáspora
   regional (Colombia, Brasil). La latencia transatlántica a la UE penaliza una operación que ya
   sufre conectividad degradada (offline-first mitiga, pero no elimina, el costo de la distancia).
2. **Costo y disponibilidad de infraestructura/GPU.** El servicio es masivo y sin funding; la
   disponibilidad de cómputo (incluida GPU para el LLM on-prem, ADR-0001) y el costo en una región
   suramericana resultan más manejables para el arranque.
3. **Proximidad regional.** São Paulo (`sa-east-1`) es el punto de presencia de nube más cercano con
   capacidad suficiente para el stack completo.

> Esta decisión **no revierte el Modelo A**: el responsable del tratamiento sigue siendo el operador
> humanitario internacional. Solo cambia **dónde residen los datos y se ejecuta el cómputo**.

## Decisión

Adoptamos **São Paulo (Brasil, `sa-east-1`) como región de hosting y residencia de datos**, bajo
control del operador humanitario internacional (responsable, sin cambio respecto a ADR-0003).

- Toda la infraestructura —LLM on-prem (ADR-0001), almacenes de datos restringidos, bóveda de medios,
  motor de matching, broker de eventos— reside en São Paulo.
- El marco regulatorio aplicable de residencia pasa a ser la **LGPD** (Lei Geral de Proteção de
  Dados, Brasil), que **mantenemos GDPR como listón interno** (categoría especial Art. 9 para
  biométricos): seguimos aplicando minimización, limitación de almacenamiento, cifrado y derecho al
  borrado al estándar GDPR aunque la jurisdicción de residencia sea Brasil.
- La integración con el gobierno venezolano sigue **fuera de la custodia** (solo acreditación de
  rescatistas y, en Fase 2, SAIME con mínima divulgación).

## Alternativas consideradas

| Opción | Pros | Contras | Riesgo de seguridad |
| :---- | :---- | :---- | :---- |
| **A. São Paulo (`sa-east-1`)** ✅ | Menor latencia a Venezuela y diáspora regional; costo/GPU más manejable; LGPD como marco de datos robusto en la región; proximidad operativa | **Brasil NO está en la lista de adecuación de la UE** → se pierde el blindaje GDPR nativo del ADR-0003; tratados de cooperación judicial regionales (MLAT) podrían exponer a requerimientos | Reduce latencia pero **debilita el blindaje anti-compulsión** que motivó el Modelo A (A01/A04); exige endurecer IAM/red en `sa-east-1` (A02) |
| **B. UE / región con adecuación GDPR** (ADR-0003 original) | Máximo blindaje legal; GDPR nativo; mayor distancia jurídica del riesgo regional | Latencia transatlántica; costo; transferencia transfronteriza a gobernar | El más fuerte en protección de datos |
| **C. Híbrido (sensibles en UE, operativos en São Paulo)** | Equilibra blindaje y latencia | Complejidad de gobierno del dato (clasificar y enrutar por región); dos jurisdicciones que mantener | Superficie de error de clasificación; más config que endurecer |

> **B** queda como ruta de reversión si el riesgo de compulsión regional se materializa o aparece
> funding que absorba la latencia/costo. **C** se reserva por si una sub-clase de datos (p. ej.
> biométricos de menores) requiere blindaje extra.

## Consecuencias

- **Positivas:** menor latencia para los usuarios reales; costo e infraestructura (incluida GPU)
  más alcanzables sin funding; LGPD aporta un marco de protección de datos exigible en la región;
  se conserva el resto del Modelo A (responsable internacional, gobierno fuera de la custodia).
- **Negativas / deuda asumida:** **se pierde la adecuación GDPR nativa** que era el pilar del
  blindaje del ADR-0003; aumenta la exposición teórica a cooperación judicial regional (MLAT) frente
  a un requerimiento; hay que **endurecer la configuración de `sa-east-1`** (IAM, redes, buckets) y
  documentar la base legal LGPD; el listón GDPR ahora es una **política interna**, no una obligación
  de jurisdicción → exige disciplina propia.
- **Impacto en threat model:**
  - **T4 (exfiltración / compulsión estatal):** el blindaje legal baja respecto al ADR-0003 original;
    se **compensa** reforzando los controles técnicos (cifrado por usuario con bóveda — ADR-0008,
    control de acceso RS-02/RS-03, minimización). El control técnico pasa a ser la primera línea, no
    la jurisdicción.
  - **T7 (misconfig / transferencia):** desaparece la transferencia transatlántica UE, pero la
    transferencia Venezuela→Brasil y el endurecimiento de `sa-east-1` siguen siendo responsabilidad
    propia (A02).
  - **A09:** auditoría y logging residen en São Paulo bajo control del operador.

## Decisiones abiertas

- `<TODO>` Base legal LGPD concreta para el tratamiento de categoría especial (biométricos) y para la
  transferencia Venezuela→Brasil.
- `<TODO>` Proveedor cloud concreto en `sa-east-1` y disponibilidad de GPU para el LLM (ADR-0001).
- `<TODO>` Evaluar si una sub-clase de datos (menores, fallecimiento) merece la opción híbrida (C).

## Disparadores de revisión

- Se materializa un requerimiento de cooperación judicial regional sobre los datos → reevaluar B o C.
- Aparece funding/infra que neutralice la latencia y el costo de la UE → revertir a ADR-0003 (B).
- Cambia el estatus de adecuación de Brasil ante la UE → reevaluar el blindaje.
